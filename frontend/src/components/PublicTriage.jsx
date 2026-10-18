import { useState } from "react";
import { apiRequest } from "../services/api";

export default function PublicTriage({ language = "en" }) {
  const [symptoms, setSymptoms] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hi = language === "hi";

  async function checkSymptoms(event) {
    event.preventDefault();
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

  return (
    <section className="public-triage" aria-labelledby="public-triage-title">
      <span className="eyebrow">{hi ? "खाते की आवश्यकता नहीं" : "NO ACCOUNT REQUIRED"}</span>
      <h2 id="public-triage-title">{hi ? "तत्काल लक्षण जाँचें" : "Check urgent symptoms"}</h2>
      <p className="cv-triage-intro">{hi ? "तत्काल, नियम-आधारित सुरक्षा मार्गदर्शन के लिए लक्षण हिंदी या अंग्रेज़ी में बताएँ।" : "Describe symptoms in English, Hindi, or Hinglish for immediate, rule-based safety guidance."}</p>
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
          placeholder={hi ? "उदाहरण: सीने में भारीपन, चक्कर आना या साँस लेने में दिक्कत…" : "For example: chest pressure, sudden dizziness, difficulty breathing…"}
          minLength={2}
          maxLength={4000}
          rows={4}
          required
        />
        <button className="cv-button cv-button-primary cv-full cv-triage-submit" type="submit" disabled={busy || symptoms.trim().length < 2}>
          {busy ? (hi ? "जाँच हो रही है…" : "Evaluating safety…") : (hi ? "सुरक्षा मार्गदर्शन पाएँ →" : "Get safety guidance →")}
        </button>
      </form>
      {error && <div className="notice error cv-triage-error" role="alert">{error}</div>}
      {result && (
        <div className={`triage-result ${result.urgency === "emergency" ? "emergency" : "routine"}`} role={result.urgency === "emergency" ? "alert" : "status"}>
          <div className="cv-triage-result-header">
            <span className="cv-triage-badge" aria-hidden="true">{result.urgency === "emergency" ? "🚨" : "ℹ️"}</span>
            <strong>{result.urgency === "emergency" ? (hi ? "तत्काल आपातकालीन सहायता लें" : "Seek emergency care immediately") : (hi ? "सुरक्षा परिणाम" : `${result.urgency.toUpperCase()} guidance`)}</strong>
          </div>
          <p className="cv-triage-summary">{result.summary}</p>
          <p className="cv-triage-guidance">{result.guidance}</p>
          {result.emergency_numbers.length > 0 && (
            <div className="cv-triage-emergency-callout">
              <b>{hi ? "आपातकालीन नंबर पर तुरंत कॉल करें:" : "Call emergency helpline now:"}</b>
              <div className="cv-emergency-pills">
                {result.emergency_numbers.map((number, index) => (
                  <a key={`${number}-${index}`} href={`tel:${String(number).replace(/\D/g, "")}`} className="cv-emergency-pill">
                    📞 {number}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      <p className="triage-disclaimer">
        {hi ? "यह सीमित जाँच आपातकाल को खारिज नहीं कर सकती और निदान नहीं है। खतरा हो तो अभी 112 या 108 पर कॉल करें।" : "This limited check cannot rule out an emergency and is not a diagnosis. If you may be in danger, call 112 or 108 now."}
      </p>
    </section>
  );
}
