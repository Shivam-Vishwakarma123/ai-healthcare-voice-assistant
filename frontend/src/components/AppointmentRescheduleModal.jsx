import Modal from "./Modal";

// Modal dialog allowing patients or providers to reschedule an appointment with slot availability picker.
export default function AppointmentRescheduleModal({
  isOpen,
  onClose,
  appointment,
  token,
  rescheduleType,
  setRescheduleType,
  rescheduleTime,
  setRescheduleTime,
  rescheduleReason,
  setRescheduleReason,
  rescheduleBusy,
  onSubmit,
  SlotPickerComponent,
  language = "en",
}) {
  const hi = language === "hi";

  if (!appointment) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={hi ? "अपॉइंटमेंट का समय बदलें" : "Reschedule Appointment"}
      size="medium"
      language={language}
    >
      <form className="cv-form" onSubmit={(event) => onSubmit(event, appointment)}>
        <p className="cv-subtle">
          <strong>{appointment.doctor_name}</strong> · {appointment.specialty}
        </p>

        <label>
          {hi ? "परामर्श का प्रकार" : "Consultation type"}
          <select
            value={rescheduleType}
            onChange={(event) => {
              setRescheduleType(event.target.value);
              setRescheduleTime("");
            }}
          >
            {["in_person", "online", "phone"].map((type) => (
              <option key={type} value={type}>
                {type.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>

        {SlotPickerComponent && (
          <SlotPickerComponent
            key={`${appointment.id}-${rescheduleType}`}
            token={token}
            doctorId={appointment.doctor_id}
            consultationType={rescheduleType}
            value={rescheduleTime}
            onChange={setRescheduleTime}
            language={language}
          />
        )}

        <label>
          {hi ? "कारण (वैकल्पिक)" : "Reason (optional)"}
          <input
            maxLength={500}
            value={rescheduleReason}
            onChange={(event) => setRescheduleReason(event.target.value)}
            placeholder={hi ? "समय बदलने का कारण" : "Reason for rescheduling"}
          />
        </label>

        <div className="cv-card-actions">
          <button
            className="cv-button cv-button-quiet"
            type="button"
            onClick={onClose}
            disabled={rescheduleBusy}
          >
            {hi ? "रद्द करें" : "Cancel"}
          </button>
          <button
            className="cv-button cv-button-primary"
            type="submit"
            disabled={!rescheduleTime || rescheduleBusy}
          >
            {rescheduleBusy
              ? (hi ? "बदल रहे हैं…" : "Rescheduling…")
              : (hi ? "नया समय पुष्टि करें" : "Confirm new time")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
