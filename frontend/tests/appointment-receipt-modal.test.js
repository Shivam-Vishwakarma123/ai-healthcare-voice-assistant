import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Helper mimicking the metadata extraction logic of AppointmentReceiptModal
function getReceiptMetadata({ appointment, invoice, user, patient }) {
  if (!appointment) return null;

  const isDemo = Boolean(
    appointment.payment_is_demo ||
    invoice?.payment_is_demo ||
    (appointment.payment_transaction_id && appointment.payment_transaction_id.startsWith("demo_"))
  );

  const receiptId = invoice?.invoice_number || (appointment.invoice_id ? `REC-INV-${appointment.invoice_id}` : `REC-APT-${appointment.id}`);
  const appointmentId = `APT-${appointment.id}`;
  const amountMinor = invoice?.amount_minor ?? appointment.fee_minor ?? 0;
  const currency = invoice?.currency || "INR";
  const status = invoice?.status || appointment.payment_status || "paid";

  const dateValue = invoice?.paid_at || invoice?.created_at || appointment.scheduled_for;
  const txnRef = appointment.payment_transaction_id || invoice?.payment_intent_id || `TXN-${appointment.id}`;
  const patientName = user?.full_name || patient?.full_name || "Registered Patient";
  const patientHealthId = patient?.carevoice_id || (user?.id ? `CV-${String(user.id).padStart(6, "0")}` : "CV-000003");

  return {
    isDemo,
    receiptId,
    appointmentId,
    amountMinor,
    currency,
    status,
    dateValue,
    txnRef,
    patientName,
    patientHealthId,
  };
}

test("Appointment Receipt Modal: Generates correct receipt ID hierarchy", () => {
  // 1. When invoice has explicit invoice_number
  const withInvoiceNumber = getReceiptMetadata({
    appointment: { id: 101, invoice_id: 42 },
    invoice: { id: 42, invoice_number: "INV-2026-0042" },
  });
  assert.equal(withInvoiceNumber.receiptId, "INV-2026-0042");

  // 2. When appointment has invoice_id but no invoice object fetched yet
  const withInvoiceId = getReceiptMetadata({
    appointment: { id: 101, invoice_id: 42 },
    invoice: null,
  });
  assert.equal(withInvoiceId.receiptId, "REC-INV-42");

  // 3. When legacy appointment has no invoice_id
  const withoutInvoice = getReceiptMetadata({
    appointment: { id: 101 },
    invoice: null,
  });
  assert.equal(withoutInvoice.receiptId, "REC-APT-101");
  assert.equal(withoutInvoice.appointmentId, "APT-101");
});

test("Appointment Receipt Modal: Detects demo payment badges accurately", () => {
  // Case A: payment_is_demo flag on appointment
  const demoA = getReceiptMetadata({
    appointment: { id: 1, payment_is_demo: true },
  });
  assert.equal(demoA.isDemo, true);

  // Case B: payment_is_demo flag on invoice
  const demoB = getReceiptMetadata({
    appointment: { id: 2 },
    invoice: { id: 10, payment_is_demo: true },
  });
  assert.equal(demoB.isDemo, true);

  // Case C: transaction ID prefix 'demo_'
  const demoC = getReceiptMetadata({
    appointment: { id: 3, payment_transaction_id: "demo_txn_987654" },
  });
  assert.equal(demoC.isDemo, true);

  // Case D: real live transaction
  const live = getReceiptMetadata({
    appointment: { id: 4, payment_transaction_id: "pay_Kjh892Jk31" },
  });
  assert.equal(live.isDemo, false);
});

test("Appointment Receipt Modal: Resolves patient identity and CareVoice Health ID", () => {
  // Case 1: Patient record with carevoice_id
  const meta1 = getReceiptMetadata({
    appointment: { id: 1 },
    patient: { full_name: "Anita Sharma", carevoice_id: "CV-000003" },
  });
  assert.equal(meta1.patientName, "Anita Sharma");
  assert.equal(meta1.patientHealthId, "CV-000003");

  // Case 2: User record with numerical ID padding
  const meta2 = getReceiptMetadata({
    appointment: { id: 2 },
    user: { id: 42, full_name: "Vikram Malhotra" },
  });
  assert.equal(meta2.patientName, "Vikram Malhotra");
  assert.equal(meta2.patientHealthId, "CV-000042");

  // Case 3: Fallback when user / patient records are minimal
  const meta3 = getReceiptMetadata({
    appointment: { id: 3 },
  });
  assert.equal(meta3.patientName, "Registered Patient");
  assert.equal(meta3.patientHealthId, "CV-000003");
});

test("Appointment Receipt Modal: Invariant - AppointmentsPage retains route and does not navigate to Billing", () => {
  const portalScreensPath = path.resolve(__dirname, "../src/components/PortalScreens.jsx");
  const portalCode = fs.readFileSync(portalScreensPath, "utf8");

  // Verify AppointmentsPage imports AppointmentReceiptModal
  assert.match(portalCode, /import\s+AppointmentReceiptModal\s+from\s+["']\.\/AppointmentReceiptModal["']/);

  // Verify AppointmentsPage has selectedReceiptAppointment state
  assert.match(portalCode, /const\s+\[selectedReceiptAppointment,\s*setSelectedReceiptAppointment\]\s*=\s*useState\(null\)/);

  // Verify View receipt button sets the local state instead of onNavigate("Billing")
  assert.match(portalCode, /onClick=\{?\(\)\s*=>\s*setSelectedReceiptAppointment\(appointment\)\}?/);

  // Verify AppointmentReceiptModal is rendered with isOpen bound to selectedReceiptAppointment
  assert.match(portalCode, /<AppointmentReceiptModal[\s\S]*?isOpen=\{Boolean\(selectedReceiptAppointment\)\}/);
});

test("Appointment Receipt Modal: Print stylesheet includes #appointment-receipt-view in printable rules", () => {
  const cssPath = path.resolve(__dirname, "../src/healthcare.css");
  const cssCode = fs.readFileSync(cssPath, "utf8");

  // Verify #appointment-receipt-view is targeted for print visibility
  assert.match(cssCode, /#appointment-receipt-view,\s*#appointment-receipt-view\s*\*\s*\{\s*visibility:\s*visible\s*!important;/);

  // Verify #appointment-receipt-view has print formatting applied
  assert.match(cssCode, /#appointment-receipt-view\s*\{[\s\S]*?position:\s*absolute\s*!important;[\s\S]*?background:\s*#ffffff\s*!important;/);
});
