import { useState, useEffect } from "react";
import { apiRequest } from "../services/api";
import { ScreenTitle } from "./PortalScreens";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

// Manages DPDP Act 2023 consent directives, 48-hour PIN-protected share links, FHIR exports, and data erasure.
export function DPDPPrivacyCenter({ token, user, language = "en", onNavigate }) {
  const isHindi = language === "hi";

  // Consent Directive State
  const [consentToStore, setConsentToStore] = useState(() => {
    try {
      return localStorage.getItem("carevoice_history_consent") === "true";
    } catch {
      return false;
    }
  });
  const [consentToShare, setConsentToShare] = useState(true);
  const [consentResearch, setConsentResearch] = useState(false);
  const [savingConsent, setSavingConsent] = useState(false);
  const [consentNotice, setConsentNotice] = useState("");

  // DPDP 48-Hour Scheduled Erasure State
  const [erasureScheduled, setErasureScheduled] = useState(false);
  const [erasureNotice, setErasureNotice] = useState("");
  const [processingErasure, setProcessingErasure] = useState(false);

  // 48-Hour PIN-Protected Share Link State
  const [sharePin, setSharePin] = useState("1234");
  const [generatedShare, setGeneratedShare] = useState(null);
  const [generatingShare, setGeneratingShare] = useState(false);
  const [shareError, setShareError] = useState("");
  const [copiedLink, setCopiedLink] = useState(false);

  // Share Receiver Verification Tester State
  const [verifyToken, setVerifyToken] = useState("");
  const [verifyPin, setVerifyPin] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [sharedSummaryResult, setSharedSummaryResult] = useState(null);
  const [verifyError, setVerifyError] = useState("");

  // Patient Care Guide State
  const [guideApptId, setGuideApptId] = useState("");
  const [guideLanguage, setGuideLanguage] = useState("en");
  const [patientGuide, setPatientGuide] = useState(null);
  const [loadingGuide, setLoadingGuide] = useState(false);
  const [guideError, setGuideError] = useState("");

  // FHIR Export State
  const [exportingFHIR, setExportingFHIR] = useState(false);

  // Updates DPDP Act consent directives for data retention, clinical provider sharing, and research.
  async function handleSaveConsent() {
    setSavingConsent(true);
    setConsentNotice("");
    try {
      localStorage.setItem("carevoice_history_consent", String(consentToStore));
      const res = await apiRequest("/records/privacy/consent", token, {
        method: "POST",
        body: JSON.stringify({
          consent_to_store: consentToStore,
          consent_to_share_with_doctors: consentToShare,
          consent_anonymized_research: consentResearch,
        }),
      });
      setConsentNotice(res.message || (isHindi ? "सहमति निर्देश सफलतापूर्वक सहेजे गए।" : "Consent directives updated under DPDP Act 2023."));
    } catch (err) {
      setConsentNotice(isHindi ? "सहमति सहेजने में त्रुटि।" : `Failed to update consent: ${err.message}`);
    } finally {
      setSavingConsent(false);
    }
  }

  // Schedules deletion of conversation transcripts subject to DPDP 48-hour cooling-off safety period.
  async function handleRequestErasure() {
    if (!window.confirm(
      isHindi
        ? "क्या आप निश्चित रूप से अपनी सभी AI परामर्श वार्तालापों को मिटाने का अनुरोध करना चाहते हैं? 48 घंटे की सुरक्षा अवधि के बाद यह स्थायी रूप से हट जाएगा।"
        : "Are you sure you want to schedule erasure of all consultation conversations? Under DPDP Act 2023, a 48-hour cooling-off safety period applies before permanent deletion."
    )) {
      return;
    }

    setProcessingErasure(true);
    setErasureNotice("");
    try {
      const res = await apiRequest("/assistant/conversations", token, {
        method: "DELETE",
      });
      setErasureScheduled(true);
      setErasureNotice(
        res.message ||
        "All consultation conversations scheduled for permanent erasure under DPDP Act 2023 with a 48-hour cooling-off safety period."
      );
    } catch (err) {
      setErasureNotice(`Erasure request failed: ${err.message}`);
    } finally {
      setProcessingErasure(false);
    }
  }

  // Generates a 48-hour time-limited, PIN-authenticated public share link for patient medical records.
  async function handleGenerateShareLink() {
    if (!sharePin || sharePin.length < 4 || sharePin.length > 8) {
      setShareError(isHindi ? "पिन 4 से 8 अंकों का होना चाहिए।" : "PIN must be between 4 and 8 digits.");
      return;
    }

    setGeneratingShare(true);
    setShareError("");
    setCopiedLink(false);
    try {
      const patientId = user?.patient_id || user?.id;
      const res = await apiRequest("/records/share-link", token, {
        method: "POST",
        body: JSON.stringify({
          patient_user_id: Number(patientId),
          pin: sharePin,
          expires_hours: 48,
        }),
      });
      setGeneratedShare(res);
      setVerifyToken(res.share_token);
      setVerifyPin(sharePin);
    } catch (err) {
      setShareError(err.message || "Could not generate share link.");
    } finally {
      setGeneratingShare(false);
    }
  }

  // Copies the generated record sharing URL to client system clipboard.
  function handleCopyShareLink() {
    if (!generatedShare) return;
    const url = `${window.location.origin}/records/shared/${generatedShare.share_token}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 3000);
    });
  }

  // Simulates external clinician record verification using share token and PIN.
  async function handleVerifyShare() {
    if (!verifyToken || !verifyPin) {
      setVerifyError(isHindi ? "टोकन और पिन दोनों आवश्यक हैं।" : "Both share token and numeric PIN are required.");
      return;
    }

    setVerifying(true);
    setVerifyError("");
    setSharedSummaryResult(null);
    try {
      const res = await apiRequest(
        `/records/shared/${encodeURIComponent(verifyToken)}?pin=${encodeURIComponent(verifyPin)}`,
        "" // Public endpoint, no auth bearer required
      );
      setSharedSummaryResult(res);
    } catch (err) {
      setVerifyError(err.message || "Invalid PIN, expired token, or access denied.");
    } finally {
      setVerifying(false);
    }
  }

  // Fetches bilingual (English/Hindi) post-consultation care and follow-up guidance.
  async function handleFetchPatientGuide() {
    if (!guideApptId) {
      setGuideError(isHindi ? "कृपया अपॉइंटमेंट आईडी दर्ज करें।" : "Please enter an appointment ID.");
      return;
    }

    setLoadingGuide(true);
    setGuideError("");
    setPatientGuide(null);
    try {
      const guide = await apiRequest(
        `/records/encounters/${guideApptId}/patient-guide?lang=${guideLanguage}`,
        token
      );
      setPatientGuide(guide);
    } catch (err) {
      setGuideError(err.message || "Failed to load patient guide. Ensure encounter is finalized by doctor.");
    } finally {
      setLoadingGuide(false);
    }
  }

  // Downloads authenticated HL7 FHIR R4 medical record collection bundle in JSON format.
  async function handleExportFHIR() {
    setExportingFHIR(true);
    try {
      const patientId = user?.patient_id || user?.id;
      const resp = await fetch(`${API_BASE}/records/patients/${patientId}/fhir-export`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`Export failed (${resp.status})`);
      const bundle = await resp.json();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = `carevoice-fhir-r4-${patientId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objUrl);
    } catch (err) {
      alert(`FHIR Export error: ${err.message}`);
    } finally {
      setExportingFHIR(false);
    }
  }

  return (
    <div className="cv-privacy-center">
      <ScreenTitle
        eyebrow="DIGITAL PERSONAL DATA PROTECTION (DPDP ACT 2023)"
        title={isHindi ? "DPDP गोपनीयता व सहमति केंद्र" : "DPDP Privacy & Consent Center"}
        description={
          isHindi
            ? "डिजिटल व्यक्तिगत डेटा संरक्षण अधिनियम, 2023 के तहत अपने स्वास्थ्य डेटा की सहमति, 48-घंटे की कूलिंग-ऑफ इरेज़र, पिन-सुरक्षित शेयर लिंक और FHIR डेटा निर्यात प्रबंधित करें।"
            : "Manage granular consent directives, request 48-hour cooling-off erasure, generate PIN-protected record links, and export standard HL7 FHIR R4 records."
        }
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px" }}>
        {/* SECTION 1: Patient Data Consent Management */}
        <div className="cv-card cv-privacy-card">
          <div className="cv-card-header">
            <span style={{ fontSize: "20px" }}>📝</span>
            <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
              {isHindi ? "स्वास्थ्य डेटा सहमति निर्देश" : "Granular Consent Directives"}
            </h3>
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
            {isHindi
              ? "आप अपनी सहमति कभी भी वापस ले सकते हैं या बदल सकते हैं। प्रत्येक परिवर्तन ऑडिट लॉग में दर्ज होता है।"
              : "Control how CareVoice processes your clinical dialogue and records. Revocable at any time under DPDP Act Section 6."}
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px", margin: "16px 0" }}>
            <label className="cv-checkbox-row">
              <input
                type="checkbox"
                checked={consentToStore}
                onChange={(e) => setConsentToStore(e.target.checked)}
              />
              <div>
                <strong>{isHindi ? "परामर्श इतिहास व ऑडियो रिकॉर्ड सहेजें" : "Store consultation transcripts & audio"}</strong>
                <small style={{ display: "block", color: "var(--cv-text-muted)" }}>
                  {isHindi
                    ? "भविष्य के परामर्शों के लिए संदर्भ उपलब्ध कराता है।"
                    : "Maintains longitudinal consultation history for clinician review."}
                </small>
              </div>
            </label>

            <label className="cv-checkbox-row">
              <input
                type="checkbox"
                checked={consentToShare}
                onChange={(e) => setConsentToShare(e.target.checked)}
              />
              <div>
                <strong>{isHindi ? "नेटवर्क के सत्यापित डॉक्टरों के साथ साझा करें" : "Share with verified CareVoice doctors"}</strong>
                <small style={{ display: "block", color: "var(--cv-text-muted)" }}>
                  {isHindi
                    ? "अपॉइंटमेंट के दौरान डॉक्टरों को आपका पूर्व इतिहास देखने की अनुमति।"
                    : "Grants authorized clinicians access during scheduled appointments."}
                </small>
              </div>
            </label>

            <label className="cv-checkbox-row">
              <input
                type="checkbox"
                checked={consentResearch}
                onChange={(e) => setConsentResearch(e.target.checked)}
              />
              <div>
                <strong>{isHindi ? "अनाम अनुसंधान व सार्वजनिक स्वास्थ्य डेटा" : "Anonymized public health research"}</strong>
                <small style={{ display: "block", color: "var(--cv-text-muted)" }}>
                  {isHindi
                    ? "महामारी व स्वास्थ्य अनुसंधान के लिए पूरी तरह अनाम डेटा।"
                    : "Contribute de-identified aggregate metrics to public health studies."}
                </small>
              </div>
            </label>
          </div>

          {consentNotice && (
            <div className="cv-alert cv-alert-success" style={{ margin: "10px 0", fontSize: "0.85rem" }}>
              {consentNotice}
            </div>
          )}

          <button
            type="button"
            className="cv-btn cv-btn-primary"
            onClick={handleSaveConsent}
            disabled={savingConsent}
            style={{ width: "100%", justifyContent: "center" }}
          >
            {savingConsent ? "Saving..." : (isHindi ? "सहमति निर्देश अपडेट करें" : "Update Consent Directives")}
          </button>
        </div>

        {/* SECTION 2: 48-Hour Cooling-Off Scheduled Erasure */}
        <div className="cv-card cv-privacy-card">
          <div className="cv-card-header">
            <span style={{ fontSize: "20px" }}>⏳</span>
            <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
              {isHindi ? "48-घंटे कूलिंग-ऑफ डेटा इरेज़र" : "48-Hour Cooling-Off Erasure"}
            </h3>
          </div>
          <p style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
            {isHindi
              ? "डेटा मिटाने का अनुरोध करने पर 48 घंटे की सुरक्षा अवधि मिलती है ताकि गलती से हुआ अनुरोध रद्द किया जा सके।"
              : "Right to Erasure with clinical safety buffer. A 48-hour cooling-off window allows cancellation before permanent purge."}
          </p>

          {erasureScheduled ? (
            <div className="cv-alert cv-alert-warning" style={{ margin: "16px 0" }}>
              <div style={{ fontWeight: "700" }}>⏳ Erasure Scheduled Under DPDP Act</div>
              <p style={{ margin: "4px 0 0", fontSize: "0.85rem" }}>
                {erasureNotice || "Your consultation data is queued for permanent deletion. Safety cooling-off period active for 48 hours."}
              </p>
            </div>
          ) : (
            <div style={{ margin: "16px 0", padding: "12px", background: "var(--cv-surface-soft)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--cv-text-secondary)" }}>
                Status: <strong>No pending erasure requests</strong>
              </div>
              <small style={{ color: "var(--cv-text-muted)", display: "block", marginTop: "4px" }}>
                Finalized clinical notes and signed prescriptions are retained under medical records compliance regulations.
              </small>
            </div>
          )}

          <button
            type="button"
            className="cv-btn cv-btn-danger"
            onClick={handleRequestErasure}
            disabled={processingErasure}
            style={{ width: "100%", justifyContent: "center" }}
          >
            {processingErasure ? "Scheduling..." : (isHindi ? "परामर्श इतिहास मिटाने का अनुरोध करें" : "Request Consultation History Erasure")}
          </button>
        </div>
      </div>

      {/* SECTION 3: 48-Hour PIN-Protected Secure Share Link */}
      <div className="cv-card cv-privacy-card" style={{ marginTop: "24px" }}>
        <div className="cv-card-header">
          <span style={{ fontSize: "20px" }}>🔗</span>
          <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
            {isHindi ? "48-घंटे पिन-सुरक्षित रिकॉर्ड शेयर लिंक" : "48-Hour PIN-Protected Share Link"}
          </h3>
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
          {isHindi
            ? "दूसरे डॉक्टर या आपातकालीन कर्मी को अपना स्वास्थ्य सारांश दिखाने के लिए एक अस्थायी 48-घंटे का लिंक बनाएं, जो आपके द्वारा तय किए गए 4-8 अंकों के पिन से सुरक्षित रहेगा।"
            : "Generate a cryptographically secured temporary link for external physicians or second opinions. Protected with a numeric PIN and auto-expires in 48 hours."}
        </p>

        <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap", margin: "16px 0" }}>
          <div style={{ minWidth: "160px" }}>
            <label className="cv-label">{isHindi ? "4-8 अंकों का पिन *" : "Numeric PIN (4-8 digits) *"}</label>
            <input
              type="text"
              maxLength={8}
              className="cv-input"
              value={sharePin}
              onChange={(e) => setSharePin(e.target.value.replace(/\D/g, ""))}
              placeholder="e.g. 5839"
            />
          </div>

          <button
            type="button"
            className="cv-btn cv-btn-primary"
            onClick={handleGenerateShareLink}
            disabled={generatingShare}
          >
            {generatingShare ? "Generating..." : (isHindi ? "🔒 सुरक्षित शेयर लिंक बनाएं" : "🔒 Generate Secure Share Link")}
          </button>
        </div>

        {shareError && <div className="cv-alert cv-alert-danger" style={{ marginBottom: "12px" }}>{shareError}</div>}

        {generatedShare && (
          <div className="cv-share-result-box" style={{ padding: "14px", background: "var(--cv-surface-tint)", borderRadius: "8px", border: "1px solid var(--cv-accent-soft)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
              <div>
                <strong>Share Token:</strong> <code style={{ fontSize: "0.9rem" }}>{generatedShare.share_token}</code>
                <span className="cv-badge cv-badge-routine" style={{ marginLeft: "8px" }}>Valid for 48 Hours</span>
              </div>
              <button type="button" className="cv-btn cv-btn-secondary" onClick={handleCopyShareLink}>
                {copiedLink ? "✓ Copied Link!" : "📋 Copy Share Link"}
              </button>
            </div>
            <div style={{ marginTop: "8px", fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
              Share this link and inform the recipient of your PIN (<code>{sharePin}</code>). The recipient cannot view records without entering this PIN.
            </div>
          </div>
        )}

        {/* Receiver Verification Simulator */}
        <div style={{ marginTop: "20px", borderTop: "1px dashed var(--cv-border)", paddingTop: "16px" }}>
          <h4 style={{ margin: "0 0 8px", fontSize: "0.95rem" }}>
            🔍 {isHindi ? "प्राप्तकर्ता पिन सत्यापन सिम्युलेटर:" : "Receiver PIN Verification Tester:"}
          </h4>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <input
              type="text"
              className="cv-input"
              style={{ flex: "2", minWidth: "220px" }}
              placeholder="Paste Share Token"
              value={verifyToken}
              onChange={(e) => setVerifyToken(e.target.value)}
            />
            <input
              type="password"
              className="cv-input"
              style={{ flex: "1", minWidth: "100px" }}
              placeholder="Enter PIN"
              value={verifyPin}
              onChange={(e) => setVerifyPin(e.target.value)}
            />
            <button
              type="button"
              className="cv-btn cv-btn-secondary"
              onClick={handleVerifyShare}
              disabled={verifying}
            >
              {verifying ? "Verifying..." : "Decrypt & View Record"}
            </button>
          </div>

          {verifyError && <div className="cv-alert cv-alert-danger" style={{ marginTop: "10px" }}>{verifyError}</div>}

          {sharedSummaryResult && (
            <div className="cv-shared-record-preview" style={{ marginTop: "14px", padding: "14px", background: "var(--cv-surface-soft)", borderRadius: "8px" }}>
              <h4 style={{ margin: "0 0 6px" }}>✓ Decrypted Patient Clinical Summary: {sharedSummaryResult.patient_name}</h4>
              <p style={{ margin: 0, fontSize: "0.85rem" }}>
                <strong>Overview:</strong> Age {sharedSummaryResult.age || "N/A"}, {sharedSummaryResult.gender || "N/A"} •
                Active Allergies: {sharedSummaryResult.active_allergies?.length || 0} •
                Prescriptions: {sharedSummaryResult.recent_prescriptions?.length || 0}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* SECTION 4: Multilingual Patient Care Guide (English & Hindi) */}
      <div className="cv-card cv-privacy-card" style={{ marginTop: "24px" }}>
        <div className="cv-card-header">
          <span style={{ fontSize: "20px" }}>📖</span>
          <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
            {isHindi ? "बहुभाषी मरीज देखभाल गाइड (क्लिनिकल प्राथमिकता)" : "Multilingual Patient Care Guide (Clinical Primacy)"}
          </h3>
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
          {isHindi
            ? "क्लिनिकल प्राथमिकता सिद्धांत: केवल डॉक्टर द्वारा हस्ताक्षरित व अंतिम रूप दिए गए क्लिनिकल नोट्स और पर्चे ही मरीज गाइड में संकलित होते हैं।"
            : "Enforces Clinical Primacy: Only doctor-verified and signed clinical records are compiled into patient guides. AI drafts are strictly excluded."}
        </p>

        <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap", margin: "16px 0" }}>
          <div>
            <label className="cv-label">{isHindi ? "अपॉइंटमेंट आईडी *" : "Encounter / Appointment ID *"}</label>
            <input
              type="number"
              className="cv-input"
              placeholder="e.g. 100"
              value={guideApptId}
              onChange={(e) => setGuideApptId(e.target.value)}
            />
          </div>

          <div>
            <label className="cv-label">{isHindi ? "भाषा" : "Language"}</label>
            <select
              className="cv-input"
              value={guideLanguage}
              onChange={(e) => setGuideLanguage(e.target.value)}
            >
              <option value="en">English (Medical Guide)</option>
              <option value="hi">हिन्दी (Hindi Patient Guide)</option>
            </select>
          </div>

          <button
            type="button"
            className="cv-btn cv-btn-primary"
            onClick={handleFetchPatientGuide}
            disabled={loadingGuide}
          >
            {loadingGuide ? "Generating..." : (isHindi ? "गाइड तैयार करें" : "Generate Patient Guide")}
          </button>
        </div>

        {guideError && <div className="cv-alert cv-alert-danger" style={{ marginBottom: "12px" }}>{guideError}</div>}

        {patientGuide && (
          <div className="cv-guide-card" style={{ padding: "16px", background: "var(--cv-surface-soft)", borderRadius: "8px", marginTop: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>{patientGuide.title}</h3>
              <span className="cv-badge cv-badge-routine">{patientGuide.language === "hi" ? "हिन्दी" : "English"}</span>
            </div>
            <p style={{ margin: "8px 0" }}>{patientGuide.overview}</p>

            {patientGuide.medications?.length > 0 && (
              <div style={{ margin: "12px 0" }}>
                <h4 style={{ margin: "0 0 6px" }}>💊 {guideLanguage === "hi" ? "दवाइयां:" : "Medications:"}</h4>
                {patientGuide.medications.map((m, idx) => (
                  <div key={idx} style={{ padding: "6px 10px", background: "var(--cv-surface)", borderRadius: "6px", marginBottom: "4px" }}>
                    <strong>{m.medication}</strong> {m.strength && `(${m.strength})`} — {m.frequency} ({m.duration})
                    <div style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>{m.instructions}</div>
                  </div>
                ))}
              </div>
            )}

            {patientGuide.follow_up_instructions && (
              <div style={{ margin: "12px 0" }}>
                <h4 style={{ margin: "0 0 4px" }}>📋 Follow-Up:</h4>
                <p style={{ margin: 0 }}>{patientGuide.follow_up_instructions}</p>
              </div>
            )}

            {patientGuide.red_flag_warnings?.length > 0 && (
              <div className="cv-alert cv-alert-warning" style={{ margin: "12px 0" }}>
                <strong>⚠️ Red-Flags & Emergency Contacts:</strong>
                <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
                  {patientGuide.red_flag_warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}

            <div style={{ marginTop: "12px", display: "flex", justifyContent: "flex-end" }}>
              <button type="button" className="cv-btn cv-btn-secondary" onClick={() => window.print()}>
                🖨️ Print Patient Guide
              </button>
            </div>
          </div>
        )}
      </div>

      {/* SECTION 5: Standardized Data Portability (HL7 FHIR R4) */}
      <div className="cv-card cv-privacy-card" style={{ marginTop: "24px" }}>
        <div className="cv-card-header">
          <span style={{ fontSize: "20px" }}>📦</span>
          <h3 style={{ margin: 0, fontSize: "1.1rem" }}>
            {isHindi ? "मानकीकृत स्वास्थ्य डेटा पोर्टेबिलिटी (HL7 FHIR R4)" : "Standardized Health Data Portability (HL7 FHIR R4)"}
          </h3>
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
          {isHindi
            ? "अपना पूरा स्वास्थ्य रिकॉर्ड अंतर्राष्ट्रीय HL7 FHIR R4 मानक JSON प्रारूप में डाउनलोड करें। किसी भी अन्य स्वास्थ्य प्रणाली या डॉक्टर को प्रदान करने के लिए उपयुक्त।"
            : "Export your complete medical record in HL7 FHIR Release 4 JSON specification, compatible with EHR systems and National Digital Health Mission (ABDM)."}
        </p>

        <div style={{ marginTop: "16px", display: "flex", gap: "10px", flexWrap: "wrap" }}>
          <button
            type="button"
            className="cv-btn cv-btn-secondary"
            onClick={handleExportFHIR}
            disabled={exportingFHIR}
          >
            {exportingFHIR ? "Exporting..." : "📥 Export HL7 FHIR R4 JSON Bundle"}
          </button>
        </div>
      </div>
    </div>
  );
}
