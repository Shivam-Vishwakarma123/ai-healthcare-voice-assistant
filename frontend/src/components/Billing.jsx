import { useEffect, useRef, useState } from "react";
import { apiRequest, formatMoney } from "../services/api";
import Modal from "./Modal";
import InvoiceReceiptModal from "./InvoiceReceiptModal";
import { useToast } from "./ToastProvider";
import { razorpayPaymentDisplayConfig } from "../services/razorpayCheckoutConfig";

let razorpaySdkPromise;

function loadRazorpay() {
  if (typeof window.Razorpay === "function") return Promise.resolve();
  if (razorpaySdkPromise) return razorpaySdkPromise;
  razorpaySdkPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = () => {
      if (typeof window.Razorpay !== "function") {
        reject(new Error("Razorpay Checkout loaded without its constructor. Reload the page and try again."));
        return;
      }
      resolve();
    };
    script.onerror = () => reject(new Error("Could not load Razorpay Checkout. Check your internet connection and try again."));
    document.head.appendChild(script);
  }).catch((error) => {
    razorpaySdkPromise = null;
    throw error;
  });
  return razorpaySdkPromise;
}

export default function Billing({ token, user, language = "en", target, onTargetHandled }) {
  const [invoices, setInvoices] = useState([]);
  const [payments, setPayments] = useState([]);
  const [refunds, setRefunds] = useState([]);
  const [billableAppointments, setBillableAppointments] = useState([]);
  const [checkoutEnabled, setCheckoutEnabled] = useState(false);
  const [providerCheckoutEnabled, setProviderCheckoutEnabled] = useState(false);
  const [providerTestMode, setProviderTestMode] = useState(false);
  const [paymentMode, setPaymentMode] = useState("live");
  const [demoCheckout, setDemoCheckout] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [creatingInvoice, setCreatingInvoice] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const handledTargetRef = useRef(null);
  const paymentActionBusyRef = useRef(false);
  const [selectedReceipt, setSelectedReceipt] = useState(null);
  const [invoiceForm, setInvoiceForm] = useState({ patient_user_id: "", appointment_id: "", description: "", amount: "" });
  const hi = language === "hi";
  const toast = useToast();
  const isStaff = ["hospital_staff", "hospital_admin", "platform_admin"].includes(user?.role);

  async function load() {
    setLoading(true);
    setLoaded(false);
    try {
      const [rows, config, paymentRows, refundRows, appointmentRows] = await Promise.all([
        apiRequest("/billing/invoices", token),
        apiRequest("/billing/config", token),
        apiRequest("/billing/payments", token),
        apiRequest("/billing/refunds", token),
        isStaff ? apiRequest("/billing/billable-appointments", token) : Promise.resolve([]),
      ]);
      setInvoices(rows);
      setPayments(paymentRows);
      setRefunds(refundRows);
      setBillableAppointments(appointmentRows);
      setCheckoutEnabled(config.checkout_enabled ?? config.online_payment_enabled);
      setProviderCheckoutEnabled(config.provider_checkout_enabled ?? config.online_payment_enabled);
      setProviderTestMode(config.provider_test_mode === true);
      setPaymentMode(config.payment_mode);
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load().catch(() => toast(hi ? "बिलिंग जानकारी लोड नहीं हो सकी। फिर से प्रयास करें।" : "Billing information could not be loaded. Please try again.", "error")); }, [token]);

  async function createInvoice(event) {
    event.preventDefault();
    if (creatingInvoice) return;
    setCreatingInvoice(true);
    try {
      await apiRequest("/billing/invoices", token, {
        method: "POST",
        body: JSON.stringify({
          patient_user_id: Number(invoiceForm.patient_user_id),
          description: invoiceForm.description,
          amount_minor: Math.round(Number(invoiceForm.amount) * 100),
          ...(invoiceForm.appointment_id ? { appointment_id: Number(invoiceForm.appointment_id) } : {}),
        }),
      });
      setInvoiceForm({ patient_user_id: "", appointment_id: "", description: "", amount: "" });
      toast(hi ? "इनवॉइस बनाया गया।" : "Invoice created.", "success");
      await load();
    } catch (reason) {
      toast(hi ? "इनवॉइस नहीं बन सका। कृपया विवरण जाँचें और फिर प्रयास करें।" : "Invoice could not be created. Check the details and try again.", "error");
    } finally {
      setCreatingInvoice(false);
    }
  }

  async function payInvoice(invoice) {
    if (paymentActionBusyRef.current) return;
    paymentActionBusyRef.current = true;
    let checkoutClosed = false;
    setBusyId(invoice.id);
    try {
      const order = await apiRequest("/billing/checkout", token, {
        method: "POST",
        body: JSON.stringify({ invoice_id: invoice.id }),
      });
      if (order.mode === "demo") {
        setDemoCheckout(order);
        return;
      }
      if (!order.key_id || !order.order_id?.startsWith("order_") || !Number.isInteger(order.amount_minor) || order.amount_minor <= 0 || !order.currency) {
        console.error("Razorpay checkout order response is incomplete", {
          hasKeyId: Boolean(order.key_id),
          validOrderId: Boolean(order.order_id?.startsWith("order_")),
          amountMinor: order.amount_minor,
          currency: order.currency,
        });
        throw new Error("Razorpay returned incomplete checkout details. No payment was started; please contact support.");
      }
      console.info("Razorpay checkout order ready", {
        orderId: order.order_id,
        amountMinor: order.amount_minor,
        currency: order.currency,
      });
      await loadRazorpay();
      console.info("Razorpay Checkout SDK loaded");
      if (typeof window.Razorpay !== "function") {
        throw new Error("Razorpay Checkout could not initialize. Reload the page and try again.");
      }
      const checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount_minor,
        currency: order.currency,
        name: "CareVoice Health",
        description: order.description,
        order_id: order.order_id,
        // Note: "method" is NOT a valid top-level Razorpay option.
        // Payment methods available depend on Razorpay account checkout settings.
        // Explicitly request UPI with the existing methods; Razorpay still
        // filters this list against methods enabled for the merchant account.
        config: razorpayPaymentDisplayConfig(),
        prefill: { name: user.full_name, email: user.email, ...(user.phone_number ? { contact: user.phone_number } : {}) },
        theme: { color: "#167b6b" },
        handler: async (response) => {
          checkoutClosed = true;
          try {
            await apiRequest("/billing/verify", token, {
              method: "POST",
              body: JSON.stringify({
                invoice_id: invoice.id,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
              }),
            });
            toast(hi ? "भुगतान सत्यापित हुआ। इनवॉइस का भुगतान हो गया है।" : "Payment verified. Your invoice is paid.", "success");
            try { await load(); } catch {
              toast(hi ? "भुगतान सत्यापित है, लेकिन बिलिंग सूची रीफ़्रेश नहीं हुई। रीफ़्रेश बटन दबाएँ।" : "Payment is verified, but Billing could not refresh. Use the Refresh button.", "info");
            }
          } catch (reason) {
            console.error("Razorpay payment verification failed", { message: reason.message });
            toast(hi ? "भुगतान की पुष्टि अभी नहीं हो सकी। स्थिति देखने के लिए बिलिंग रीफ़्रेश करें।" : "Payment could not be confirmed yet. Refresh Billing to check its status.", "error");
          } finally {
            paymentActionBusyRef.current = false;
            setBusyId(null);
          }
        },
        modal: { ondismiss: () => {
          setBusyId(null);
          paymentActionBusyRef.current = false;
          if (!checkoutClosed) toast(hi ? "भुगतान रद्द हुआ। जब चाहें फिर से प्रयास कर सकते हैं।" : "Payment cancelled. You can try again whenever you're ready.", "info");
        } },
      });
      if (!checkout || typeof checkout.open !== "function" || typeof checkout.on !== "function") {
        throw new Error("Razorpay Checkout could not initialize. Reload the page and try again.");
      }
      checkout.on("payment.failed", (event) => {
        checkoutClosed = true;
        console.warn("Razorpay reported a payment failure", {
          code: event.error?.code,
          reason: event.error?.reason,
        });
        const reason = event.error?.reason;
        if (reason === "payment_cancelled") {
          toast(hi ? "भुगतान रद्द हुआ। जब चाहें फिर से प्रयास कर सकते हैं।" : "Payment cancelled. You can try again whenever you're ready.", "info");
          return;
        }
        const detail = reason === "payment_timed_out" ? "The payment timed out. Your invoice remains unpaid; you can try again." : reason === "insufficient_fund" ? "The payment was declined for insufficient funds. Your invoice remains unpaid." : reason === "card_declined" ? "The bank declined the payment. Your invoice remains unpaid; try another method." : "Payment was not completed. Your invoice remains unpaid; you can try again.";
        toast(hi ? "भुगतान पूरा नहीं हुआ। इनवॉइस बकाया है; आप फिर से प्रयास कर सकते हैं।" : detail, "error");
      });
      checkout.open();
      console.info("Razorpay Checkout opened", { orderId: order.order_id });
    } catch (reason) {
      console.error("Razorpay checkout could not be started", { message: reason.message });
      toast(hi ? "सुरक्षित भुगतान शुरू नहीं हो सका। भुगतान सेटिंग जाँचें और फिर प्रयास करें।" : "Secure checkout could not start. Check payment setup and try again.", "error");
      setBusyId(null);
      paymentActionBusyRef.current = false;
    }
  }

  useEffect(() => {
    if (!target?.invoiceId || !loaded || loading) return;
    const targetKey = `${target.action}:${target.invoiceId}`;
    if (handledTargetRef.current === targetKey) return;
    handledTargetRef.current = targetKey;
    const invoice = invoices.find((item) => item.id === target.invoiceId);
    if (target.action === "pay" && invoice?.status === "unpaid") {
      payInvoice(invoice);
    } else if (target.action === "receipt") {
      document.getElementById(`invoice-${target.invoiceId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      if (invoice) {
        const payment = payments.find((item) => item.invoice_id === invoice.id);
        setSelectedReceipt({ invoice, payment });
      }
    }
    onTargetHandled?.();
  }, [target, loaded, loading, invoices]);

  async function completeDemoPayment(outcome) {
    if (!demoCheckout) return;
    setBusyId(demoCheckout.order_id);
    try {
      const result = await apiRequest("/billing/demo/complete", token, {
        method: "POST",
        body: JSON.stringify({ order_id: demoCheckout.order_id, outcome }),
      });
      const messages = {
        success: `DEMO / NOT A REAL PAYMENT — simulated reference ${result.transaction_id}; invoice ${result.invoice_number} is paid in this development database.`,
        failed: `DEMO / NOT A REAL PAYMENT — simulated failure recorded (${result.transaction_id}); invoice remains unpaid.`,
        cancelled: `DEMO / NOT A REAL PAYMENT — checkout cancelled (${result.transaction_id}); invoice remains unpaid.`,
      };
      toast(messages[outcome], outcome === "success" ? "success" : outcome === "failed" ? "error" : "info");
      setDemoCheckout(null);
      await load();
    } catch (reason) {
      toast("Demo payment could not be completed.", "error");
    } finally {
      paymentActionBusyRef.current = false;
      setBusyId(null);
    }
  }

  async function requestRefund(payment) {
    const reason = window.prompt("Record the administrator-approved refund reason:");
    if (!reason || reason.trim().length < 3) return;
    setBusyId(`refund-${payment.id}`);
    try {
      const key = globalThis.crypto?.randomUUID?.() || `refund-${payment.id}-${Date.now()}`;
      await apiRequest("/billing/refunds", token, {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({ payment_id: payment.id, amount_minor: payment.amount_minor, reason: reason.trim() }),
      });
      toast("Refund request submitted. Its status remains pending until Razorpay confirms it.", "info");
      await load();
    } catch (reason) {
      toast("Refund request could not be submitted. Please try again.", "error");
    } finally {
      setBusyId(null);
    }
  }

  function selectAppointment(appointmentId) {
    const appointment = billableAppointments.find((item) => String(item.appointment_id) === appointmentId);
    setInvoiceForm((current) => ({
      ...current,
      appointment_id: appointmentId,
      patient_user_id: appointment ? String(appointment.patient_user_id) : current.patient_user_id,
      description: appointment ? `Consultation with ${appointment.doctor_name}` : current.description,
      amount: appointment ? (appointment.fee_minor / 100).toFixed(2) : current.amount,
    }));
  }

  const dueMinor = invoices.filter((invoice) => invoice.status === "unpaid").reduce((sum, invoice) => sum + invoice.amount_minor, 0);
  const paidMinor = invoices.filter((invoice) => invoice.status === "paid").reduce((sum, invoice) => sum + invoice.amount_minor, 0);

  return (
    <>
      <div className="page-title"><span className="eyebrow">{hi ? "आपका खाता" : "YOUR ACCOUNT"}</span><h1>{hi ? "बिलिंग और भुगतान" : "Billing & payments"}</h1><p>{hi ? "अपने इनवॉइस देखें और बकाया राशि का सुरक्षित भुगतान करें।" : "Review your invoices and securely pay outstanding balances."}</p></div>
      {loaded && <div className="metrics">
          <Metric label={hi ? "बकाया राशि" : "Outstanding balance"} value={formatMoney(dueMinor)} note={`${invoices.filter((item) => item.status === "unpaid").length} ${hi ? "बकाया इनवॉइस" : "unpaid invoices"}`} />
          <Metric label={hi ? "भुगतान किए गए इनवॉइस" : "Paid invoices"} value={formatMoney(paidMinor)} note={`${invoices.filter((item) => item.status === "paid").length} ${hi ? "भुगतान दर्ज" : "payments recorded"}`} />
      </div>}
      {isStaff && <form className="card form-card invoice-form" onSubmit={createInvoice}>
          <h3>{hi ? "इनवॉइस जारी करें" : "Issue an invoice"}</h3>
          <p className="muted">{hi ? "केवल क्लिनिक स्टाफ। रोगी से उनके CareVoice सेटिंग पृष्ठ पर दिखने वाली खाता ID माँगें।" : "Clinic staff only. Ask the patient for the account ID shown in their CareVoice Settings page."}</p>
        <label>{hi ? "अपॉइंटमेंट (वैकल्पिक)" : "Appointment (optional)"}<select value={invoiceForm.appointment_id} onChange={(event) => selectAppointment(event.target.value)}><option value="">Manual service invoice</option>{billableAppointments.map((appointment) => <option key={appointment.appointment_id} value={appointment.appointment_id}>#{appointment.appointment_id} · {appointment.doctor_name} · patient #{appointment.patient_user_id} · {new Date(appointment.scheduled_for).toLocaleString()}</option>)}</select></label>
        <div className="form-row">
            <label>{hi ? "रोगी खाता ID" : "Patient account ID"}<input required type="number" min="1" value={invoiceForm.patient_user_id} onChange={(event) => setInvoiceForm({ ...invoiceForm, patient_user_id: event.target.value })} /></label>
            <label>{hi ? "राशि (₹)" : "Amount (₹)"}<input required type="number" min="0.01" step="0.01" readOnly={Boolean(invoiceForm.appointment_id)} value={invoiceForm.amount} onChange={(event) => setInvoiceForm({ ...invoiceForm, amount: event.target.value })} /></label>
        </div>
          <label>{hi ? "विवरण" : "Description"}<input required maxLength="240" value={invoiceForm.description} onChange={(event) => setInvoiceForm({ ...invoiceForm, description: event.target.value })} /></label>
          <button className="primary" type="submit" disabled={creatingInvoice}>{creatingInvoice ? (hi ? "बन रहा है…" : "Creating…") : (hi ? "इनवॉइस बनाएँ" : "Create invoice")}</button>
      </form>}
      <section className="card">
          <div className="card-head"><div><span className="eyebrow">{hi ? "भुगतान इतिहास" : "PAYMENT HISTORY"}</span><h3>{hi ? "इनवॉइस" : "Invoices"}</h3></div><button type="button" className="primary" onClick={() => load().catch(() => toast(hi ? "बिलिंग जानकारी लोड नहीं हो सकी। फिर से प्रयास करें।" : "Billing information could not be loaded. Please try again.", "error"))} disabled={loading}>{hi ? "रीफ़्रेश करें" : "Refresh"}</button>{loaded && (paymentMode === "demo" ? <span className="pill muted-pill">{hi ? "केवल डेमो चेकआउट" : "Demo checkout only"}</span> : providerCheckoutEnabled ? <span className="pill">{providerTestMode ? (hi ? "Razorpay टेस्ट मोड तैयार" : "Razorpay Test Mode ready") : (hi ? "गेटवे चेकआउट तैयार" : "Gateway checkout ready")}</span> : <span className="pill muted-pill">{hi ? "भुगतान गेटवे सेटअप आवश्यक" : "Gateway setup required"}</span>)}</div>
          {loaded && paymentMode === "demo" && <div className="gateway-note" role="note">{hi ? "डेमो मोड कार्ड भुगतान नहीं खोलता। Razorpay का टेस्ट कार्ड चेकआउट उपयोग करने के लिए सर्वर पर PAYMENT_MODE=live और Razorpay Test Mode की कुंजियाँ सेट करें।" : "Demo mode does not open card checkout. To use Razorpay's test card checkout, set PAYMENT_MODE=live and configure Razorpay Test Mode keys on the server."}</div>}
          {loaded && paymentMode === "live" && providerCheckoutEnabled && <p className="muted">{providerTestMode ? (hi ? "यह Razorpay Test Mode है। कार्ड और UPI सहित उपलब्ध भुगतान विकल्प टेस्ट खाते की Checkout सेटिंग पर निर्भर करते हैं। कोई वास्तविक राशि नहीं ली जाती।" : "Razorpay Test Mode is active. Available methods, including UPI and Cards, depend on the Test Mode account's Checkout configuration. No real payment is charged.") : (hi ? "भुगतान Razorpay के सुरक्षित होस्टेड चेकआउट में होंगे। उपलब्ध तरीके Razorpay खाते की चेकआउट सेटिंग पर निर्भर करते हैं; कार्ड या बैंक विवरण CareVoice में सेव नहीं होते।" : "Payment opens Razorpay's secure hosted checkout. Available methods follow the Razorpay account's Checkout configuration; CareVoice does not store card or bank details.")}</p>}
          {loaded && paymentMode === "live" && !providerCheckoutEnabled && <p className="muted">{hi ? "Razorpay चेकआउट कॉन्फ़िगर नहीं है। सर्वर की .env फ़ाइल में Test Mode की RAZORPAY_KEY_ID और RAZORPAY_KEY_SECRET सेट करें।" : "Razorpay checkout is not configured. Set Test Mode RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in the server .env file."}</p>}
          {loading ? <p role="status">{hi ? "इनवॉइस लोड हो रहे हैं…" : "Loading invoices…"}</p> : !loaded ? null : !invoices.length ? <div className="empty-row"><span className="empty-symbol">₹</span><div><b>{hi ? "अभी कोई इनवॉइस नहीं" : "No invoices yet"}</b><p>{hi ? "क्लिनिक द्वारा जारी इनवॉइस यहाँ दिखेंगे।" : "Invoices issued by your clinic will show here."}</p></div></div> :
          <div className="invoice-list">{invoices.map((invoice) => {
            const payment = payments.find((item) => item.invoice_id === invoice.id && item.status === "paid") || payments.find((item) => item.invoice_id === invoice.id);
            const simulatedPayment = payment?.is_demo === true;
            return <article className="invoice-row" id={`invoice-${invoice.id}`} tabIndex={-1} key={invoice.id}>
              <div><b>{invoice.invoice_number}</b><p>{invoice.description} · {new Date(invoice.created_at).toLocaleDateString(hi ? "hi-IN" : "en-IN")}</p></div>
              <strong>{formatMoney(invoice.amount_minor, invoice.currency)}</strong>
              <span className={`invoice-status ${invoice.status}`}>{invoice.status === "paid" ? simulatedPayment ? (hi ? "डेमो · वास्तविक भुगतान नहीं" : "DEMO · not a real payment") : (hi ? "भुगतान हुआ" : "Paid") : invoice.status === "unpaid" ? (hi ? "बकाया" : "Unpaid") : invoice.status}</span>
              <div className="cv-card-actions">
                {invoice.status === "paid" && (
                  <button
                    className="cv-button cv-button-quiet"
                    type="button"
                    onClick={() => setSelectedReceipt({ invoice, payment })}
                  >
                    {hi ? "रसीद देखें" : "View receipt"}
                  </button>
                )}
                {invoice.status === "unpaid" && (
                  <button
                    className="cv-button cv-button-primary"
                    type="button"
                    onClick={() => payInvoice(invoice)}
                    disabled={busyId !== null || !checkoutEnabled}
                  >
                    {busyId === invoice.id ? (hi ? "खुल रहा है…" : "Opening…") : paymentMode === "demo" ? (hi ? "डेमो भुगतान" : "Demo payment") : (hi ? "अभी भुगतान करें" : "Pay now")}
                  </button>
                )}
              </div>
            </article>;
          })}</div>}
          {loaded && paymentMode === "live" && !providerCheckoutEnabled && invoices.some((invoice) => invoice.status === "unpaid") && <p className="muted gateway-note">{hi ? "ऑनलाइन भुगतान अभी उपलब्ध नहीं है। व्यवस्थापक को Razorpay Test Mode कुंजियाँ कॉन्फ़िगर करनी होंगी।" : "Online payment is temporarily unavailable. An administrator must configure Razorpay Test Mode keys."}</p>}
      </section>
      <section className="card">
        <div className="card-head"><div><span className="eyebrow">{hi ? "लेनदेन" : "TRANSACTIONS"}</span><h3>{hi ? "भुगतान इतिहास" : "Payment history"}</h3></div></div>
        {payments.length ? <div className="invoice-list">{payments.map((payment) => <article className="invoice-row" key={payment.id}>
          <div><b>{payment.invoice_number}</b><p>{payment.appointment_id ? `${hi ? "अपॉइंटमेंट" : "Appointment"} #${payment.appointment_id} · ` : ""}{payment.transaction_id} · {payment.paid_at ? (hi ? "भुगतान" : "Paid") : (hi ? "प्रयास" : "Attempt")}: {new Date(payment.paid_at || payment.created_at).toLocaleString(hi ? "hi-IN" : "en-IN")}</p>{payment.doctor_name && <small>{payment.doctor_name}{payment.hospital_name ? ` · ${payment.hospital_name}` : ""}{payment.scheduled_for ? ` · ${new Date(payment.scheduled_for).toLocaleString(hi ? "hi-IN" : "en-IN")}` : ""}</small>}</div>
          <strong>{formatMoney(payment.amount_minor, payment.currency)}</strong>
          <span className={`invoice-status ${payment.status}`}>{payment.is_demo ? "DEMO · " : ""}{payment.status}</span>
          <div className="cv-card-actions">
            {payment.status === "paid" && (
              <button
                className="cv-button cv-button-quiet"
                type="button"
                onClick={() => {
                  const inv = invoices.find((item) => item.id === payment.invoice_id) || {
                    invoice_number: payment.invoice_number,
                    amount_minor: payment.amount_minor,
                    currency: payment.currency,
                    status: payment.status,
                    paid_at: payment.paid_at,
                    created_at: payment.created_at,
                  };
                  setSelectedReceipt({ invoice: inv, payment });
                }}
              >
                {hi ? "रसीद देखें" : "View receipt"}
              </button>
            )}
            {!["hospital_staff", "doctor", "patient"].includes(user?.role) && payment.status === "paid" && (!payment.appointment_id || payment.appointment_status === "cancelled") && (
              <button
                className="cv-button cv-button-primary"
                type="button"
                disabled={busyId !== null}
                onClick={() => requestRefund(payment)}
              >
                {busyId === `refund-${payment.id}` ? "Submitting…" : "Request approved refund"}
              </button>
            )}
          </div>
        </article>)}</div> : <p className="muted">{loading ? "Loading payment history…" : "No payment attempts recorded yet."}</p>}
        {refunds.map((refund) => <p className="muted" key={refund.id}>Refund {refund.provider_refund_id || `#${refund.id}`} · {formatMoney(refund.amount_minor, refund.currency)} · {refund.status}</p>)}
      </section>

      <InvoiceReceiptModal
        isOpen={Boolean(selectedReceipt)}
        onClose={() => setSelectedReceipt(null)}
        invoice={selectedReceipt?.invoice}
        payment={selectedReceipt?.payment}
        language={language}
      />

      <Modal
        isOpen={Boolean(demoCheckout)}
        onClose={() => completeDemoPayment("cancelled")}
        title={hi ? "डेमो भुगतान" : "Demo Payment"}
        size="medium"
        language={language}
      >
        {demoCheckout && (
          <div className="cv-modal-receipt-content">
            <div className="cv-demo-badge" role="status">
              DEMO / NOT A REAL PAYMENT
            </div>
            <p>
              {hi
                ? "डेमो मोड — कोई वास्तविक राशि नहीं ली जाएगी। यह सिमुलेशन भुगतान प्रदाता से संपर्क नहीं करता है और कार्ड या बैंकिंग विवरण नहीं मांगता है।"
                : "Demo mode — no real money will be charged. This simulation does not contact a payment provider and does not ask for card or banking details."}
            </p>
            <p>
              <strong>{demoCheckout.invoice_number}</strong> · {formatMoney(demoCheckout.amount_minor, demoCheckout.currency)}
            </p>
            <div className="cv-card-actions">
              <button
                className="cv-button cv-button-primary"
                type="button"
                disabled={busyId === demoCheckout.order_id}
                onClick={() => completeDemoPayment("success")}
              >
                {hi ? "सफल सिमुलेशन" : "Simulate success"}
              </button>
              <button
                className="cv-button cv-button-secondary"
                type="button"
                disabled={busyId === demoCheckout.order_id}
                onClick={() => completeDemoPayment("failed")}
              >
                {hi ? "विफल सिमुलेशन" : "Simulate failure"}
              </button>
              <button
                className="cv-button cv-button-quiet"
                type="button"
                disabled={busyId === demoCheckout.order_id}
                onClick={() => completeDemoPayment("cancelled")}
              >
                {hi ? "रद्द करें" : "Cancel demo checkout"}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}

function Metric({ label, value, note }) {
  return <div className="metric"><span className="metric-label">{label}</span><b>{value}</b><small>{note}</small></div>;
}
