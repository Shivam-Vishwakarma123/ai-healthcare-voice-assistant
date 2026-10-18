import Modal from "./Modal";
import { formatMoney } from "../services/api";

export default function InvoiceReceiptModal({ isOpen, onClose, invoice, payment, language = "en" }) {
  const hi = language === "hi";

  if (!invoice) return null;

  const simulatedPayment = payment?.is_demo === true || invoice.payment_is_demo === true;

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

        <div className="cv-card-actions">
          <button className="cv-button cv-button-primary cv-full" type="button" onClick={onClose}>
            {hi ? "बंद करें" : "Close"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
