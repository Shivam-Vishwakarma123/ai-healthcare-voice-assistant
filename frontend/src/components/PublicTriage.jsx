import { useState } from "react";
import { apiRequest } from "../services/api";

export default function PublicTriage({ language = "en", onNavigate }) {
  const [symptoms, setSymptoms] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hi = language === "hi";

  async function checkSymptoms(event) {
    event?.preventDefault();
    if (busy || symptoms.trim().length < 2) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const triage = await apiRequest("/assistant/triage", "", {
        method: "POST",
        body: JSON.stringify({ text: symptoms.trim() }),
      });
      setResult(triage);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  function handleQuestionClick(questionText) {
    setSymptoms((prev) => (prev ? `${prev} ${questionText}` : questionText));
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
      <form onSubmit={checkSymptoms} className="cv-triage-form">
        <label htmlFor="public-triage-symptoms" className="cv-triage-label">
          {hi ? "क्या हो रहा है?" : "What symptoms are you experiencing?"}
          <span className="cv-triage-hint">{hi ? "अपनी भाषा में सहजता से लिखें" : "Describe in your own words"}</span>
        </label>
        <textarea
          id="public-triage-symptoms"
          className="cv-triage-input"
          value={symptoms}
          onChange={(event) => setSymptoms(event.target.value)}
          placeholder={
            hi
              ? "उदाहरण: सीने में भारीपन, चक्कर आना या साँस लेने में दिक्कत…"
              : "For example: chest pressure, sudden dizziness, difficulty breathing…"
          }
          minLength={2}
          maxLength={4000}
          rows={4}
          required
        />
        <button
          className="cv-button cv-button-primary cv-full cv-triage-submit"
          type="submit"
          disabled={busy || symptoms.trim().length < 2}
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
          {error}
        </div>
      )}
      {result && (
        <div
          className={`triage-result ${
            result.urgency === "emergency"
              ? "emergency"
              : result.urgency === "urgent"
              ? "urgent"
              : "routine"
          }`}
          role={result.urgency === "emergency" ? "alert" : "status"}
        >
          <div className="cv-triage-result-header">
            <span
              className={`cv-urgency-badge ${
                result.urgency === "emergency"
                  ? "emergency"
                  : result.urgency === "urgent"
                  ? "urgent"
                  : "routine"
              }`}
            >
              {result.urgency === "emergency" ? "🚨 Emergency" : result.urgency === "urgent" ? "⚠️ Urgent" : "ℹ️ Routine"}
            </span>
            <strong>
              {result.urgency === "emergency"
                ? hi
                  ? "तत्काल आपातकालीन सहायता लें"
                  : "Seek emergency care immediately"
                : hi
                ? "सुरक्षा मूल्यांकन परिणाम"
                : `${result.urgency.toUpperCase()} Clinical Guidance`}
            </strong>
          </div>

          {result.emergency_warning && (
            <div className="notice error" role="alert">
              <strong>{result.emergency_warning}</strong>
            </div>
          )}

          <p className="cv-triage-summary">{result.summary}</p>
          <p className="cv-triage-guidance">{result.guidance}</p>

          {result.reported_symptoms?.length > 0 && (
            <div>
              <small className="cv-modal-meta">
                {hi ? "पहचाने गए लक्षण:" : "Identified symptoms:"}
              </small>
              <div className="cv-symptom-tag-list">
                {result.reported_symptoms.map((symptom, idx) => (
                  <span key={`${symptom}-${idx}`} className="cv-symptom-tag">
                    {symptom}
                  </span>
                ))}
              </div>
            </div>
          )}

          {result.emergency_numbers?.length > 0 && (
            <div className="cv-triage-emergency-callout">
              <b>{hi ? "आपातकालीन नंबर पर तुरंत कॉल करें:" : "Call emergency helpline now:"}</b>
              <div className="cv-emergency-pills">
                {result.emergency_numbers.map((number, index) => (
                  <a
                    key={`${number}-${index}`}
                    href={`tel:${String(number).replace(/\D/g, "")}`}
                    className="cv-emergency-pill"
                  >
                    📞 {number}
                  </a>
                ))}
              </div>
            </div>
          )}

          {result.possible_explanations?.length > 0 && (
            <div className="cv-followup-container">
              <div className="cv-followup-title">
                {hi ? "संभावित संदर्भ (निदान नहीं):" : "Possible context (educational only):"}
              </div>
              <ul className="cv-doctor-card-reasons">
                {result.possible_explanations.map((exp, idx) => (
                  <li key={idx}>{exp}</li>
                ))}
              </ul>
            </div>
          )}

          {result.recommended_next_steps?.length > 0 && (
            <div className="cv-followup-container">
              <div className="cv-followup-title">
                {hi ? "अनुशंसित अगले कदम:" : "Recommended next steps:"}
              </div>
              <ul className="cv-doctor-card-reasons">
                {result.recommended_next_steps.map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ul>
            </div>
          )}

          {result.follow_up_questions?.length > 0 && (
            <div className="cv-followup-container">
              <div className="cv-followup-title">
                {hi ? "अधिक जानकारी के लिए क्लिक करें:" : "Clarify details (click to add):"}
              </div>
              <div className="cv-followup-chips">
                {result.follow_up_questions.map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="cv-followup-chip"
                    onClick={() => handleQuestionClick(q)}
                  >
                    + {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {result.recommended_doctors?.length > 0 && (
            <div className="cv-doctor-recommendations">
              <div className="cv-doctor-recommendations-title">
                <span>🩺</span>
                <span>
                  {hi ? "उपलब्ध सत्यापित विशेषज्ञ:" : "Verified Clinicians in Directory:"}
                </span>
              </div>
              <div className="cv-doctor-grid">
                {result.recommended_doctors.map((doc) => (
                  <div key={doc.doctor_id} className="cv-doctor-card">
                    <div className="cv-doctor-card-header">
                      <h4 className="cv-doctor-card-name">Dr. {doc.doctor_name}</h4>
                      <div className="cv-doctor-card-specialty">{doc.specialty}</div>
                      {doc.hospital_name && (
                        <div className="cv-doctor-card-hospital">🏥 {doc.hospital_name}</div>
                      )}
                    </div>
                    {doc.match_reasons?.length > 0 && (
                      <ul className="cv-doctor-card-reasons">
                        {doc.match_reasons.slice(0, 2).map((reason, idx) => (
                          <li key={idx}>{reason}</li>
                        ))}
                      </ul>
                    )}
                    <div className="cv-doctor-card-footer">
                      <span className="cv-doctor-card-fee">
                        ₹{Math.round(doc.fee_minor / 100)}
                      </span>
                      {onNavigate && (
                        <button
                          type="button"
                          className="cv-doctor-book-btn"
                          onClick={() => onNavigate("Find care")}
                        >
                          {hi ? "अपॉइंटमेंट बुक करें →" : "Book appointment →"}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <p className="triage-disclaimer">
        {result?.disclaimer ||
          (hi
            ? "यह सीमित जाँच आपातकाल को खारिज नहीं कर सकती और निदान नहीं है। खतरा हो तो अभी 112 या 108 पर कॉल करें।"
            : "This limited check cannot rule out an emergency and is not a diagnosis. If you may be in danger, call 112 or 108 now.")}
      </p>
    </section>
  );
}
