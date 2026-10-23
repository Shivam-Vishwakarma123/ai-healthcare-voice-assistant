import { useState } from "react";
import Modal from "./Modal";
import { formatMoney } from "../services/api";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

// Renders an accessible modal dialog displaying invoice transaction details and authenticated PDF downloads.
export default function InvoiceReceiptModal({ isOpen, onClose, invoice, payment, token, language = "en" }) {
  const hi = language === "hi";
  const [downloading, setDownloading] = useState(false);

  if (!invoice) return null;

  const simulatedPayment = payment?.is_demo === true || invoice.payment_is_demo === true;

  // Streams binary PDF from authenticated API endpoint and triggers client browser file download.
  async function handleDownload(urlPath, filename) {
    if (!token) return;
    setDownloading(true);
    try {
      const resp = await fetch(`${API_BASE}${urlPath}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`Download failed with status ${resp.status}`);
      const blob = await resp.blob();
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objUrl);
    } catch (err) {
      alert(`Download failed: ${err.message}`);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={hi ? "भुगतान रसीद" : "Payment Receipt"}
      size="medium"
      language={language}
    >
      <div className="cv-modal-receipt-content">
        {simulatedPayment && (
          <div className="cv-demo-badge" role="status">
            {hi ? "डेमो भुगतान · कोई वास्तविक शुल्क नहीं लिया गया" : "DEMO PAYMENT · Not a real financial transaction"}
          </div>
        )}

        <div className="cv-receipt-header">
          <div>
            <span className="eyebrow">{hi ? "इनवॉइस संख्या" : "INVOICE NUMBER"}</span>
            <h3>{invoice.invoice_number}</h3>
          </div>
          <div className="cv-receipt-amount">
            <span className="eyebrow">{hi ? "कुल राशि" : "TOTAL AMOUNT"}</span>
            <strong>{formatMoney(invoice.amount_minor, invoice.currency)}</strong>
          </div>
        </div>

        <div className="cv-modal-grid">
          <div className="cv-modal-section">
            <h3>{hi ? "स्थिति" : "Status"}</h3>
            <span className={`cv-status cv-status-${invoice.status}`}>
              {invoice.status === "paid" ? (hi ? "भुगतान हुआ" : "Paid") : invoice.status}
            </span>
          </div>

          <div className="cv-modal-section">
            <h3>{hi ? "दिनांक" : "Date"}</h3>
            <p>{new Date(invoice.paid_at || invoice.created_at).toLocaleString(hi ? "hi-IN" : "en-IN")} IST</p>
          </div>
        </div>

        <div className="cv-modal-section">
          <h3>{hi ? "विवरण" : "Description"}</h3>
          <p>{invoice.description || (hi ? "परामर्श सेवा" : "Consultation service")}</p>
        </div>

        <div className="cv-modal-section">
          <h3>{hi ? "भुगतान संदर्भ (लेनदेन ID)" : "Transaction Reference"}</h3>
          <p><code>{payment?.transaction_id || invoice.payment_intent_id || invoice.invoice_number}</code></p>
        </div>

        <div style={{ display: "flex", gap: "10px", marginTop: "16px", flexWrap: "wrap" }}>
          {invoice.status === "paid" && (
            <button
              className="cv-btn cv-btn-sm cv-btn-primary"
              style={{ flex: 1 }}
              type="button"
              disabled={downloading}
              onClick={() => handleDownload(`/billing/receipts/${invoice.id}/pdf`, `receipt-${invoice.invoice_number}.pdf`)}
            >
              📥 {downloading ? (hi ? "डाउनलोड हो रहा है…" : "Downloading…") : (hi ? "सत्यापित रसीद (PDF)" : "Download Receipt (PDF)")}
            </button>
          )}
          <button
            className="cv-btn cv-btn-sm cv-btn-secondary"
            style={{ flex: 1 }}
            type="button"
            disabled={downloading}
            onClick={() => handleDownload(`/billing/invoices/${invoice.id}/pdf`, `invoice-${invoice.invoice_number}.pdf`)}
          >
            📄 {downloading ? (hi ? "डाउनलोड हो रहा है…" : "Downloading…") : (hi ? "टैक्स इनवॉइस (PDF)" : "Download Invoice (PDF)")}
          </button>
        </div>

        <div className="cv-card-actions" style={{ marginTop: "12px" }}>
          <button className="cv-button cv-button-quiet cv-full" type="button" onClick={onClose}>
            {hi ? "बंद करें" : "Close"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
