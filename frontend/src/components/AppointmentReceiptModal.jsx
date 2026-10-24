import { useState, useEffect } from "react";
import Modal from "./Modal";
import { formatMoney, apiRequest } from "../services/api";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

// Accessible in-page receipt dialog displaying consultation fees, clinician/patient info, and download/print actions.
export default function AppointmentReceiptModal({
  isOpen,
  onClose,
  appointment,
  token,
  language = "en",
  user,
  patient,
}) {
  const hi = language === "hi";
  const [downloading, setDownloading] = useState(false);
  const [invoice, setInvoice] = useState(null);
  const [downloadError, setDownloadError] = useState("");

  // Fetch full invoice record if available for rich billing details
  useEffect(() => {
    if (!isOpen || !appointment) {
      setInvoice(null);
      setDownloadError("");
      return;
    }

    if (appointment.invoice_id && token) {
      let isMounted = true;
      apiRequest("/billing/invoices", token)
        .then((invoices) => {
          if (!isMounted || !Array.isArray(invoices)) return;
          const matched = invoices.find(
            (inv) => inv.id === appointment.invoice_id || inv.appointment_id === appointment.id
          );
          if (matched) setInvoice(matched);
        })
        .catch(() => {
          // Fallback to appointment data if invoice list request fails
        });

      return () => {
        isMounted = false;
      };
    }
  }, [isOpen, appointment, token]);

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
  const formattedDate = dateValue
    ? `${new Date(dateValue).toLocaleString(hi ? "hi-IN" : "en-IN")} IST`
    : "—";

  const txnRef = appointment.payment_transaction_id || invoice?.payment_intent_id || `TXN-${appointment.id}`;

  const patientName = user?.full_name || patient?.full_name || (hi ? "पंजीकृत रोगी" : "Registered Patient");
  const patientHealthId = patient?.carevoice_id || (user?.id ? `CV-${String(user.id).padStart(6, "0")}` : "CV-000003");

  // Authenticated binary download for PDF receipt
  async function handleDownloadPdf() {
    const invoiceId = invoice?.id || appointment.invoice_id;
    if (!invoiceId || !token) {
      // If no server invoice exists yet, use browser print
      window.print();
      return;
    }

    setDownloading(true);
    setDownloadError("");
    try {
      // Primary: receipt PDF endpoint
      let resp = await fetch(`${API_BASE}/billing/receipts/${invoiceId}/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      // Fallback: invoice PDF endpoint if receipt specific endpoint 404s
      if (!resp.ok && resp.status === 404) {
        resp = await fetch(`${API_BASE}/billing/invoices/${invoiceId}/pdf`, {
          headers: { Authorization: `Bearer ${token}` },
        });
      }

      if (!resp.ok) {
        throw new Error(hi ? `डाउनलोड विफल रहा (${resp.status})` : `Download failed with status ${resp.status}`);
      }

      const blob = await resp.blob();
      const objUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objUrl;
      anchor.download = `receipt-${receiptId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objUrl);
    } catch (err) {
      setDownloadError(err.message || (hi ? "रसीद डाउनलोड करने में त्रुटि।" : "Could not download receipt PDF."));
    } finally {
      setDownloading(false);
    }
  }

  function handlePrint() {
    window.print();
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={hi ? "अपॉइंटमेंट भुगतान रसीद" : "Consultation Payment Receipt"}
      size="medium"
      language={language}
    >
      <div className="cv-modal-receipt-content cv-appointment-receipt-modal" id="appointment-receipt-view">
        {isDemo && (
          <div className="cv-demo-badge" role="status">
            {hi
              ? "डेमो भुगतान · कोई वास्तविक वित्तीय लेन-देन नहीं"
              : "DEMO PAYMENT · Not a real financial transaction"}
          </div>
        )}

        <div className="cv-receipt-header">
          <div>
            <span className="eyebrow">{hi ? "रसीद संख्या" : "RECEIPT NUMBER"}</span>
            <h3 data-testid="receipt-id">{receiptId}</h3>
            <span className="cv-subtle" style={{ fontSize: "11px" }}>
              {hi ? "अपॉइंटमेंट ID" : "Appointment ID"}: <strong>#{appointmentId}</strong>
            </span>
          </div>
          <div className="cv-receipt-amount">
            <span className="eyebrow">{hi ? "कुल शुल्क" : "CONSULTATION FEE"}</span>
            <strong>{formatMoney(amountMinor, currency)}</strong>
          </div>
        </div>

        {downloadError && (
          <div className="cv-modal-error" role="alert">
            {downloadError}
          </div>
        )}

        {/* Patient and Clinician Details */}
        <div className="cv-modal-grid">
          <div className="cv-modal-section">
            <span className="eyebrow">{hi ? "रोगी विवरण" : "PATIENT DETAILS"}</span>
            <p><strong>{patientName}</strong></p>
            <p className="cv-modal-meta">Health ID: <code>{patientHealthId}</code></p>
            {user?.email && <p className="cv-modal-meta">{user.email}</p>}
          </div>

          <div className="cv-modal-section">
            <span className="eyebrow">{hi ? "चिकित्सक / अस्पताल" : "CLINICIAN & FACILITY"}</span>
            <p><strong>{appointment.doctor_name || (hi ? "परामर्शदाता चिकित्सक" : "Consultant Physician")}</strong></p>
            <p className="cv-modal-meta">{appointment.specialty || (hi ? "सामान्य चिकित्सा" : "General Medicine")}</p>
            <p className="cv-modal-meta">{appointment.hospital_name || "CareVoice Health Center"}</p>
          </div>
        </div>

        {/* Payment & Schedule Metadata */}
        <div className="cv-modal-grid">
          <div className="cv-modal-section">
            <span className="eyebrow">{hi ? "भुगतान स्थिति" : "PAYMENT STATUS"}</span>
            <div>
              <span className={`cv-status cv-status-${status.toLowerCase()}`}>
                {status.toLowerCase() === "paid"
                  ? (hi ? "भुगतान हुआ (सत्यापित)" : "Paid (Verified)")
                  : status}
              </span>
            </div>
            <p className="cv-modal-meta" style={{ marginTop: "6px" }}>
              {hi ? "दिनांक" : "Date"}: {formattedDate}
            </p>
          </div>

          <div className="cv-modal-section">
            <span className="eyebrow">{hi ? "लेनदेन संदर्भ" : "TRANSACTION REFERENCE"}</span>
            <p><code>{txnRef}</code></p>
            <p className="cv-modal-meta">
              {hi ? "परामर्श प्रकार" : "Consultation"}: {appointment.consultation_type ? appointment.consultation_type.replace("_", " ") : "In person"}
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="cv-modal-actions cv-no-print" style={{ display: "flex", gap: "10px", marginTop: "16px", flexWrap: "wrap" }}>
          <button
            className="cv-button cv-button-primary"
            style={{ flex: 1, minWidth: "160px" }}
            type="button"
            disabled={downloading}
            onClick={handleDownloadPdf}
            title={hi ? "सत्यापित PDF रसीद डाउनलोड करें" : "Download verified PDF receipt"}
          >
            📥 {downloading ? (hi ? "डाउनलोड हो रहा है…" : "Downloading…") : (hi ? "PDF रसीद डाउनलोड" : "Download PDF receipt")}
          </button>

          <button
            className="cv-button cv-button-secondary"
            style={{ flex: 1, minWidth: "140px" }}
            type="button"
            onClick={handlePrint}
            title={hi ? "रसीद प्रिंट करें" : "Print receipt"}
          >
            🖨️ {hi ? "रसीद प्रिंट करें" : "Print receipt"}
          </button>

          <button
            className="cv-button cv-button-quiet"
            style={{ flex: "0 0 100px" }}
            type="button"
            onClick={onClose}
          >
            {hi ? "बंद करें" : "Close"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
