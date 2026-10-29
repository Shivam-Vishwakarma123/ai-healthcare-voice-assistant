import { useRef, useState } from "react";
import { apiRequest } from "../services/api";
import SymptomGuidanceModal from "./SymptomGuidanceModal";

// Public triage widget evaluating patient symptoms against deterministic red-flag
// clinical safety heuristics and presenting results in a professional healthcare modal.
export default function PublicTriage({ language = "en", onNavigate }) {
  const [symptoms, setSymptoms] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [validationError, setValidationError] = useState("");
  const [isModalOpen, setIsModalOpen] = useState(false);

  const textareaRef = useRef(null);
  const submitButtonRef = useRef(null);
  const hi = language === "hi";

  // Validates symptom input and requests clinical safety evaluation from the API.
  async function checkSymptoms(event) {
    event?.preventDefault();
    if (busy) return;

    const trimmed = symptoms.trim();
    if (!trimmed) {
      setValidationError(
        hi
          ? "कृपया सुरक्षा मार्गदर्शन पाने के लिए अपने लक्षणों का विवरण दर्ज करें।"
          : "Please describe your symptoms before requesting safety guidance."
      );
      textareaRef.current?.focus();
      return;
    }

    if (trimmed.length < 2) {
      setValidationError(
        hi
          ? "कृपया कम से कम 2 अक्षरों में लक्षणों का विवरण दें।"
          : "Please enter at least 2 characters describing your symptoms."
      );
      textareaRef.current?.focus();
      return;
    }

    setValidationError("");
    setError("");
    setBusy(true);
    setIsModalOpen(false);
    setResult(null);

    try {
      const triage = await apiRequest("/assistant/triage", "", {
        method: "POST",
        body: JSON.stringify({ text: trimmed }),
      });
      setResult(triage);
      setIsModalOpen(true);
    } catch (requestError) {
      setError(requestError?.message || (hi ? "सुरक्षा मूल्यांकन में त्रुटि हुई।" : "Safety evaluation request failed."));
      setResult(null);
      setIsModalOpen(false);
    } finally {
      setBusy(false);
    }
  }

  // Appends clinical follow-up question text or focuses the input for symptom editing.
  function handleEditSymptoms(questionText) {
    if (questionText) {
      setSymptoms((prev) => (prev ? `${prev} ${questionText}` : questionText));
    }
    setIsModalOpen(false);
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 50);
  }

  return (
    <section className="public-triage" aria-labelledby="public-triage-title">
      <span className="eyebrow">{hi ? "खाते की आवश्यकता नहीं" : "NO ACCOUNT REQUIRED"}</span>
      <h2 id="public-triage-title">{hi ? "तत्काल लक्षण जाँचें" : "Check urgent symptoms"}</h2>
      <p className="cv-triage-intro">
        {hi
          ? "तत्काल, नियम-आधारित सुरक्षा मार्गदर्शन के लिए लक्षण हिंदी या अंग्रेज़ी में बताएँ।"
          : "Describe symptoms in English, Hindi, or Hinglish for immediate, rule-based safety guidance."}
      </p>

      <form onSubmit={checkSymptoms} className="cv-triage-form" noValidate>
        <label htmlFor="public-triage-symptoms" className="cv-triage-label">
          {hi ? "क्या हो रहा है?" : "What symptoms are you experiencing?"}
          <span className="cv-triage-hint">{hi ? "अपनी भाषा में सहजता से लिखें" : "Describe in your own words"}</span>
        </label>
        <textarea
          ref={textareaRef}
          id="public-triage-symptoms"
          className="cv-triage-input"
          value={symptoms}
          onChange={(event) => {
            setSymptoms(event.target.value);
            if (validationError) setValidationError("");
          }}
          placeholder={
            hi
              ? "उदाहरण: सीने में भारीपन, चक्कर आना या साँस लेने में दिक्कत…"
              : "For example: chest pressure, sudden dizziness, difficulty breathing…"
          }
          maxLength={4000}
          rows={4}
          aria-invalid={Boolean(validationError)}
          aria-describedby={validationError ? "public-triage-validation" : undefined}
          disabled={busy}
        />

        {validationError && (
          <div
            id="public-triage-validation"
            className="notice error cv-triage-validation"
            role="alert"
          >
            {validationError}
          </div>
        )}

        <button
          ref={submitButtonRef}
          className="cv-button cv-button-primary cv-full cv-triage-submit"
          type="submit"
          disabled={busy}
          aria-busy={busy}
        >
          {busy
            ? hi
              ? "जाँच हो रही है…"
              : "Evaluating safety…"
            : hi
            ? "सुरक्षा मार्गदर्शन पाएँ →"
            : "Get safety guidance →"}
        </button>
      </form>

      {error && (
        <div className="notice error cv-triage-error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="cv-button cv-button-quiet cv-triage-retry-btn"
            onClick={checkSymptoms}
          >
            🔄 {hi ? "फिर कोशिश करें" : "Retry"}
          </button>
        </div>
      )}

      {result && !isModalOpen && (
        <div className="cv-triage-reopen-card" role="status">
          <div className="cv-triage-reopen-info">
            <span
              className={`cv-urgency-badge ${
                result.urgency === "emergency"
                  ? "emergency"
                  : result.urgency === "urgent"
                  ? "urgent"
                  : result.urgency === "insufficient_information"
                  ? "info-needed"
                  : "routine"
              }`}
            >
              {result.urgency === "emergency"
                ? hi ? "🚨 आपातकालीन" : "🚨 Emergency"
                : result.urgency === "urgent"
                ? hi ? "⚠️ तत्काल" : "⚠️ Urgent"
                : result.urgency === "insufficient_information"
                ? hi ? "❓ अधिक जानकारी" : "❓ More Info Needed"
                : hi ? "ℹ️ सामान्य" : "ℹ️ Routine"}
            </span>
            <span className="cv-triage-reopen-label">
              {hi ? "सुरक्षा मार्गदर्शन परिणाम उपलब्ध है" : "Safety guidance result is ready"}
            </span>
          </div>
          <button
            type="button"
            className="cv-button cv-button-secondary cv-triage-reopen-btn"
            onClick={() => setIsModalOpen(true)}
          >
            📋 {hi ? "सुरक्षा मार्गदर्शन देखें" : "View safety guidance"}
          </button>
        </div>
      )}

      <p className="triage-disclaimer">
        {result?.disclaimer ||
          (hi
            ? "यह सीमित जाँच आपातकाल को खारिज नहीं कर सकती और निदान नहीं है। खतरा हो तो अभी 112 या 108 पर कॉल करें।"
            : "This limited check cannot rule out an emergency and is not a diagnosis. If you may be in danger, call 112 or 108 now.")}
      </p>

      {/* Professional Healthcare Safety Guidance Modal */}
      <SymptomGuidanceModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        result={result}
        language={language}
        onNavigate={onNavigate}
        onEditSymptoms={handleEditSymptoms}
        triggerRef={submitButtonRef}
      />
    </section>
  );
}
