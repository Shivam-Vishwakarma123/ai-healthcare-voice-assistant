import Modal from "./Modal";
import { formatAppointmentDateTime } from "../services/appointments";

export default function AppointmentHistoryModal({ isOpen, onClose, appointment, history = [], loading, language = "en" }) {
  const hi = language === "hi";

  const title = appointment
    ? `${hi ? "अपॉइंटमेंट इतिहास" : "Appointment History"} #${appointment.id}`
    : (hi ? "अपॉइंटमेंट इतिहास" : "Appointment History");

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="medium" language={language}>
      {loading ? (
        <div className="cv-loading" role="status">
          <span className="cv-spinner" aria-hidden="true" />
          {hi ? "इतिहास लोड हो रहा है…" : "Loading history…"}
        </div>
      ) : history.length ? (
        <div className="cv-modal-history-list">
          {history.map((event) => (
            <div className="cv-modal-history-item" key={event.id}>
              <div className="cv-modal-history-header">
                <strong>{event.event_type.replaceAll("_", " ")}</strong>
                <time>{formatAppointmentDateTime(event.created_at, hi ? "hi-IN" : "en-IN")} IST</time>
              </div>
              {event.reason && <p className="cv-modal-history-reason">{event.reason}</p>}
            </div>
          ))}
        </div>
      ) : (
        <p className="cv-subtle">{hi ? "कोई इतिहास उपलब्ध नहीं है।" : "No history is available for this appointment."}</p>
      )}
    </Modal>
  );
}
