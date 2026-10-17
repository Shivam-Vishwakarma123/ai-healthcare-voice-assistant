import { useEffect, useState } from "react";
import { apiRequest, formatMoney } from "../services/api";

function loadRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Could not load Razorpay Checkout. Check your internet connection and try again."));
    document.head.appendChild(script);
  });
}

export default function Billing({ token, user, language = "en" }) {
  const [invoices, setInvoices] = useState([]);
  const [payments, setPayments] = useState([]);
  const [billableAppointments, setBillableAppointments] = useState([]);
  const [enabled, setEnabled] = useState(false);
  const [paymentMode, setPaymentMode] = useState("live");
  const [demoCheckout, setDemoCheckout] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [creatingInvoice, setCreatingInvoice] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [invoiceForm, setInvoiceForm] = useState({ patient_user_id: "", appointment_id: "", description: "", amount: "" });
  const hi = language === "hi";
  const isStaff = ["hospital_staff", "hospital_admin", "platform_admin"].includes(user?.role);

  async function load() {
    setLoading(true);
    setLoaded(false);
    setError("");
    try {
      const [rows, config, paymentRows, appointmentRows] = await Promise.all([
        apiRequest("/billing/invoices", token),
        apiRequest("/billing/config", token),
        apiRequest("/billing/payments", token),
        isStaff ? apiRequest("/billing/billable-appointments", token) : Promise.resolve([]),
      ]);
      setInvoices(rows);
      setPayments(paymentRows);
      setBillableAppointments(appointmentRows);
      setEnabled(config.online_payment_enabled);
      setPaymentMode(config.payment_mode);
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load().catch((reason) => setError(reason.message || "Billing information could not be loaded.")); }, [token]);

  async function createInvoice(event) {
    event.preventDefault();
    if (creatingInvoice) return;
    setCreatingInvoice(true);
    setError("");
    setNotice("");
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
      setNotice(hi ? "इनवॉइस बनाया गया।" : "Invoice created.");
      await load();
    } catch (reason) {
      setError(reason.message || "Invoice could not be created.");
    } finally {
      setCreatingInvoice(false);
    }
  }

  async function payInvoice(invoice) {
    setError("");
    setNotice("");
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
      await loadRazorpay();
      const checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount_minor,
        currency: order.currency,
        name: "CareVoice Health",
        description: order.description,
        order_id: order.order_id,
        prefill: { name: user.full_name, email: user.email },
        theme: { color: "#167b6b" },
        handler: async (response) => {
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
            setNotice(hi ? "भुगतान सत्यापित हुआ। इनवॉइस का भुगतान हो गया है।" : "Payment verified. Your invoice is paid.");
            await load();
          } catch (reason) {
            setError(reason.message);
          } finally {
            setBusyId(null);
          }
        },
        modal: { ondismiss: () => setBusyId(null) },
      });
      checkout.on("payment.failed", (event) => {
        setError(event.error?.description || "Payment was not completed. Your invoice remains unpaid.");
        setBusyId(null);
      });
      checkout.open();
    } catch (reason) {
      setError(reason.message);
      setBusyId(null);
    }
  }

  async function completeDemoPayment(outcome) {
    if (!demoCheckout) return;
    setError("");
    setNotice("");
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
      setNotice(messages[outcome]);
      setDemoCheckout(null);
      await load();
    } catch (reason) {
      setError(reason.message || "Demo payment could not be completed.");
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
      {error && <div className="notice error" role="alert"><span>{error}</span><button type="button" onClick={() => setError("")} aria-label="Dismiss error">Dismiss</button></div>}
      {notice && <div className="notice success" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Dismiss message">×</button></div>}
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
          <div className="card-head"><div><span className="eyebrow">{hi ? "भुगतान इतिहास" : "PAYMENT HISTORY"}</span><h3>{hi ? "इनवॉइस" : "Invoices"}</h3></div><button type="button" className="primary" onClick={() => load().catch((reason) => setError(reason.message || "Billing information could not be loaded."))} disabled={loading}>{hi ? "रीफ़्रेश करें" : "Refresh"}</button>{loaded && (enabled ? <span className="pill">{hi ? "ऑनलाइन भुगतान सक्षम" : "Online payments enabled"}</span> : <span className="pill muted-pill">{hi ? "भुगतान गेटवे सेटअप आवश्यक" : "Gateway setup required"}</span>)}</div>
          {loaded && <p className="muted">{paymentMode === "demo" ? "DEMO MODE — transactions are simulations, not real payments." : enabled ? "Live payment mode. Transactions are verified with the configured provider." : "Online payment is not configured."}</p>}
          {loading ? <p role="status">{hi ? "इनवॉइस लोड हो रहे हैं…" : "Loading invoices…"}</p> : !loaded ? null : !invoices.length ? <div className="empty-row"><span className="empty-symbol">₹</span><div><b>{hi ? "अभी कोई इनवॉइस नहीं" : "No invoices yet"}</b><p>{hi ? "क्लिनिक द्वारा जारी इनवॉइस यहाँ दिखेंगे।" : "Invoices issued by your clinic will show here."}</p></div></div> :
          <div className="invoice-list">{invoices.map((invoice) => <article className="invoice-row" key={invoice.id}>
              <div><b>{invoice.invoice_number}</b><p>{invoice.description} · {new Date(invoice.created_at).toLocaleDateString(hi ? "hi-IN" : "en-IN")}</p></div>
            <strong>{formatMoney(invoice.amount_minor, invoice.currency)}</strong>
              <span className={`invoice-status ${invoice.status}`}>{invoice.status === "paid" ? (hi ? "भुगतान हुआ" : "Paid") : (hi ? "बकाया" : "Unpaid")}</span>
              {invoice.status === "unpaid" && <button className="primary" type="button" onClick={() => payInvoice(invoice)} disabled={busyId !== null || !enabled}>{busyId === invoice.id ? (hi ? "खुल रहा है…" : "Opening…") : paymentMode === "demo" ? (hi ? "डेमो भुगतान" : "Demo payment") : (hi ? "अभी भुगतान करें" : "Pay now")}</button>}
          </article>)}</div>}
          {loaded && !enabled && invoices.some((invoice) => invoice.status === "unpaid") && <p className="muted gateway-note">{hi ? "ऑनलाइन भुगतान अभी उपलब्ध नहीं है। अपने क्लिनिक से संपर्क करें; व्यवस्थापक को Razorpay कुंजियाँ कॉन्फ़िगर करनी होंगी।" : "Online payment is temporarily unavailable. Contact your clinic; an administrator must configure Razorpay test/live keys."}</p>}
          {loaded && paymentMode === "live" && enabled && <p className="muted gateway-note">{hi ? "भुगतान Razorpay द्वारा संसाधित होते हैं। CareVoice कार्ड या बैंक विवरण संग्रहीत नहीं करता।" : "Payments are processed by Razorpay. CareVoice does not store card or bank details."}</p>}
      </section>
      <section className="card">
        <div className="card-head"><div><span className="eyebrow">{hi ? "लेनदेन" : "TRANSACTIONS"}</span><h3>{hi ? "भुगतान इतिहास" : "Payment history"}</h3></div></div>
        {payments.length ? <div className="invoice-list">{payments.map((payment) => <article className="invoice-row" key={payment.id}>
          <div><b>{payment.invoice_number}</b><p>{payment.transaction_id} · {new Date(payment.created_at).toLocaleString()}</p></div>
          <strong>{formatMoney(payment.amount_minor, payment.currency)}</strong>
          <span className={`invoice-status ${payment.status}`}>{payment.is_demo ? "DEMO · " : ""}{payment.status}</span>
        </article>)}</div> : <p className="muted">{loading ? "Loading payment history…" : "No payment attempts recorded yet."}</p>}
      </section>
      {demoCheckout && <div className="cv-dialog-backdrop" role="presentation">
        <section className="cv-dialog cv-demo-checkout" role="dialog" aria-modal="true" aria-labelledby="demo-checkout-title" aria-describedby="demo-checkout-description">
          <span className="eyebrow">DEMO / NOT A REAL PAYMENT</span>
          <h2 id="demo-checkout-title">Demo Payment</h2>
          <p id="demo-checkout-description">Demo mode — no real money will be charged. This simulation does not contact a payment provider and does not ask for card or banking details.</p>
          <p><strong>{demoCheckout.invoice_number}</strong> · {formatMoney(demoCheckout.amount_minor, demoCheckout.currency)}</p>
          <div className="cv-form-row">
            <button className="cv-button cv-button-primary" type="button" disabled={busyId === demoCheckout.order_id} onClick={() => completeDemoPayment("success")}>Simulate success</button>
            <button className="cv-button cv-button-secondary" type="button" disabled={busyId === demoCheckout.order_id} onClick={() => completeDemoPayment("failed")}>Simulate failure</button>
            <button className="cv-button cv-button-quiet" type="button" disabled={busyId === demoCheckout.order_id} onClick={() => completeDemoPayment("cancelled")}>Cancel demo checkout</button>
          </div>
        </section>
      </div>}
    </>
  );
}

function Metric({ label, value, note }) {
  return <div className="metric"><span className="metric-label">{label}</span><b>{value}</b><small>{note}</small></div>;
}
