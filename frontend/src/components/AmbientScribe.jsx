import { useState, useRef, useEffect } from "react";
import { apiRequest } from "../services/api";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

// Ambient clinical scribe generating structured SOAP notes from doctor-patient dialogue with safety guardrails.
export function AmbientScribe({
  token,
  user,
  language = "en",
  assignedPatients = [],
  onNoteFinalized,
  onClose,
}) {
  const isHindi = language === "hi";

  // Patient and Encounter State
  const [selectedPatientId, setSelectedPatientId] = useState(
    assignedPatients.length > 0 ? assignedPatients[0].patient_user_id : ""
  );
  const [appointmentId, setAppointmentId] = useState("");
  const [consultLanguage, setConsultLanguage] = useState(language);

  // Input Mode: "audio" or "text"
  const [inputMode, setInputMode] = useState("text");
  const [transcriptText, setTranscriptText] = useState("");

  // Audio Recording State
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);

  // Status & Progress State
  const [processing, setProcessing] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  // Guardrail Alerts
  const [emergencyAlert, setEmergencyAlert] = useState(null);
  const [boundaryViolation, setBoundaryViolation] = useState(null);

  // Generated AI Draft & Doctor Edited Note
  const [aiDraft, setAiDraft] = useState(null);
  const [editedNote, setEditedNote] = useState({
    chief_complaint: "",
    subjective: "",
    objective: "",
    assessment: "",
    plan: "",
    follow_up_instructions: "",
  });

  // Doctor Signature & Finalization
  const [doctorSignature, setDoctorSignature] = useState(
    user?.full_name ? `Dr. ${user.full_name} (RMP / Registered Medical Practitioner)` : ""
  );
  const [isFinalized, setIsFinalized] = useState(false);
  const [finalizedData, setFinalizedData] = useState(null);
  const [showDiff, setShowDiff] = useState(true);

  // Patient Care Guide State
  const [patientGuide, setPatientGuide] = useState(null);
  const [loadingGuide, setLoadingGuide] = useState(false);
  const [guideLang, setGuideLang] = useState("en");

  // MediaRecorder Refs
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerIntervalRef = useRef(null);

  // Clean up timer on unmount
  useEffect(() => {
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, []);

  // Update selected patient when assignedPatients change
  useEffect(() => {
    if (assignedPatients.length > 0 && !selectedPatientId) {
      setSelectedPatientId(assignedPatients[0].patient_user_id);
    }
  }, [assignedPatients, selectedPatientId]);

  // Initializes browser media stream and MediaRecorder to capture live ambient consultation dialogue.
  async function startRecording() {
    setErrorMessage("");
    setEmergencyAlert(null);
    setBoundaryViolation(null);
    audioChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: mimeType });
        setAudioBlob(blob);
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start(500); // 500ms chunk slices
      setIsRecording(true);
      setRecordingSeconds(0);

      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      setErrorMessage(
        isHindi
          ? "माइक्रोफ़ोन का उपयोग नहीं किया जा सका। कृपया ब्राउज़र अनुमतियाँ जांचें।"
          : `Microphone access denied or unavailable: ${err.message}`
      );
    }
  }

  // Stops audio recording hardware capture and synthesizes collected audio chunks into binary blob.
  function stopRecording() {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
    }
  }

  // Converts elapsed recording seconds into formatted mm:ss timer string.
  function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }

  // Submits clinical transcript or audio to backend LLM parser to extract structured SOAP draft note.
  async function handleGenerateSOAP() {
    if (!selectedPatientId) {
      setErrorMessage(isHindi ? "कृपया मरीज चुनें।" : "Please select an assigned patient first.");
      return;
    }

    setProcessing(true);
    setStatusMessage(isHindi ? "क्लिनिकल वार्तालाप का विश्लेषण किया जा रहा है…" : "Analyzing clinical dialogue and running safety triage…");
    setErrorMessage("");
    setEmergencyAlert(null);
    setBoundaryViolation(null);

    try {
      const formData = new FormData();
      formData.append("patient_user_id", String(selectedPatientId));
      if (appointmentId) {
        formData.append("appointment_id", String(appointmentId));
      }
      formData.append("language", consultLanguage);

      if (inputMode === "audio") {
        if (selectedFile) {
          formData.append("audio_file", selectedFile);
        } else if (audioBlob) {
          formData.append("audio_file", audioBlob, "ambient_consultation.webm");
        } else {
          setErrorMessage(isHindi ? "कृपया पहले ऑडियो रिकॉर्ड करें या फ़ाइल अपलोड करें।" : "Please record audio or upload an audio file first.");
          setProcessing(false);
          return;
        }
      } else {
        if (!transcriptText.trim()) {
          setErrorMessage(isHindi ? "कृपया परामर्श बातचीत दर्ज करें।" : "Please enter consultation dialogue transcript.");
          setProcessing(false);
          return;
        }
        formData.append("transcript", transcriptText.trim());
      }

      const response = await fetch(`${API_BASE}/records/ambient-scribe/draft`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        // Red-Flag Emergency Detected (HTTP 422 with emergency halt)
        if (response.status === 422 && data.detail?.emergency_detected) {
          setEmergencyAlert(data.detail);
          setProcessing(false);
          return;
        }

        // Boundary / Personal Treatment Violation
        if (response.status === 422 && (data.detail?.includes?.("personal treatment") || data.detail?.includes?.("authorized clinician"))) {
          setBoundaryViolation(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
          setProcessing(false);
          return;
        }

        throw new Error(data.detail || `Server returned error HTTP ${response.status}`);
      }

      // Populate AI Draft and Doctor Editing Space
      setAiDraft(data);
      setEditedNote({
        chief_complaint: data.chief_complaint || "",
        subjective: data.subjective || "",
        objective: data.objective || "",
        assessment: data.assessment || "",
        plan: data.plan || "",
        follow_up_instructions: data.follow_up_instructions || "",
      });
      setIsFinalized(false);
      setStatusMessage(isHindi ? "✨ संरचित SOAP ड्राफ्ट सफलतापूर्वक तैयार हुआ।" : "✨ Structured SOAP clinical draft generated. Review and verify below.");
    } catch (err) {
      setErrorMessage(err.message || "Failed to process clinical dialogue.");
    } finally {
      setProcessing(false);
    }
  }

  // Signs, seals, and finalizes draft SOAP note with registered medical practitioner electronic signature.
  async function handleFinalizeNote() {
    if (!aiDraft?.note_id) {
      setErrorMessage(isHindi ? "कोई ड्राफ्ट नोट उपलब्ध नहीं है।" : "No active draft note to finalize.");
      return;
    }
    if (!doctorSignature.trim()) {
      setErrorMessage(isHindi ? "हस्ताक्षर अनिवार्य है।" : "Doctor electronic signature is required.");
      return;
    }

    setProcessing(true);
    try {
      // 1. Update note with doctor edits
      await apiRequest(`/records/notes/${aiDraft.note_id}`, token, {
        method: "PUT",
        body: JSON.stringify({
          chief_complaint: editedNote.chief_complaint,
          history_of_present_illness: editedNote.subjective,
          examination_findings: editedNote.objective,
          assessment: editedNote.assessment,
          plan: editedNote.plan,
          follow_up_instructions: editedNote.follow_up_instructions,
        }),
      });

      // 2. Finalize note with signature
      const fin = await apiRequest(`/records/notes/${aiDraft.note_id}/finalize`, token, {
        method: "POST",
      });

      setIsFinalized(true);
      setFinalizedData(fin);
      setStatusMessage("✅ Clinical Note signed, sealed, and finalized in medical record.");

      if (onNoteFinalized) {
        onNoteFinalized(fin);
      }
    } catch (err) {
      setErrorMessage(`Finalization failed: ${err.message}`);
    } finally {
      setProcessing(false);
    }
  }

  // Fetches bilingual patient-friendly aftercare instructions synthesized from encounter notes.
  async function fetchPatientGuide(lang) {
    const apptId = appointmentId || (aiDraft?.appointment_id);
    if (!apptId) {
      setErrorMessage(isHindi ? "मरीज गाइड के लिए अपॉइंटमेंट आईडी आवश्यक है।" : "Encounter / Appointment ID is required to synthesize Patient Care Guide.");
      return;
    }

    setLoadingGuide(true);
    setGuideLang(lang);
    try {
      const guide = await apiRequest(`/records/encounters/${apptId}/patient-guide?lang=${lang}`, token);
      setPatientGuide(guide);
    } catch (err) {
      setErrorMessage(`Patient guide error: ${err.message}`);
    } finally {
      setLoadingGuide(false);
    }
  }

  // Pre-populates dialogue input with a sample clinical encounter including vital signs and penicillin allergy.
  function loadSampleConsultation() {
    setInputMode("text");
    setTranscriptText(
      `Doctor: Good morning Ramesh-ji, how have you been feeling since last week?\n` +
      `Patient: Namaste Doctor. Since two days I have severe fever reaching 102 degrees F, persistent body aches, and dry cough. My throat hurts when swallowing.\n` +
      `Doctor: I see. Let me check your vitals. Pulse is 88 beats per minute, blood pressure is 122/78 mmHg, and your SpO2 is 97% on room air. Chest is clear on auscultation, but posterior pharynx shows mild erythematous injection without tonsillar exudates.\n` +
      `Patient: Doctor, I also had mild nausea yesterday. Any chance of an antibiotic? By the way, I am allergic to Penicillin. I got hives and swelling last year when prescribed Amoxicillin.\n` +
      `Doctor: Good that you reminded me. We must avoid all Penicillin-class drugs. Given the viral upper respiratory prodrome, an antibiotic is not indicated right now. Let us start Paracetamol 650mg TDS after meals for fever, warm saline gargles four times a day, and plenty of oral fluids. If fever exceeds 103 or SpO2 drops below 94%, come to urgent care immediately.`
    );
  }

  return (
    <div className="cv-ambient-scribe-container">
      {/* Top Banner / Header */}
      <div className="cv-scribe-header">
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "24px" }}>🎙️</span>
          <div>
            <h2 style={{ margin: 0, fontSize: "1.3rem", fontWeight: "700" }}>
              {isHindi ? "एम्बिएंट क्लिनिकल स्क्राइब (AI ड्राफ्टिंग)" : "Ambient Clinical Scribe (AI Documentation)"}
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
              {isHindi
                ? "लाइव डॉक्टर-मरीज बातचीत से स्वचालित संरचित SOAP क्लिनिकल ड्राफ्ट तैयार करें। आपातकालीन सुरक्षा जांच अंतर्निहित है।"
                : "Continuous clinical dialogue documentation. Generates structured SOAP notes with automated red-flag safety guardrails."}
            </p>
          </div>
        </div>
        {onClose && (
          <button className="cv-btn cv-btn-ghost" onClick={onClose} style={{ padding: "4px 8px" }}>
            ✕ {isHindi ? "बंद करें" : "Close"}
          </button>
        )}
      </div>

      {/* Emergency Red-Flag Alert Banner (Critical Stop) */}
      {emergencyAlert && (
        <div className="cv-emergency-banner" role="alert">
          <div className="cv-emergency-icon">🚨</div>
          <div className="cv-emergency-content">
            <h3 className="cv-emergency-title">
              {isHindi ? "गंभीर आपातकालीन संकेत मिले - तत्काल चिकित्सा सहायता आवश्यक" : "CRITICAL EMERGENCY RED-FLAG DETECTED — IMMEDIATE CLINICAL TRIAGE REQUIRED"}
            </h3>
            <p className="cv-emergency-desc">
              {emergencyAlert.message || "Acute emergency presentation identified in consultation dialogue. Ambient scribe halted with zero database retention."}
            </p>
            {emergencyAlert.red_flags?.length > 0 && (
              <div style={{ margin: "8px 0" }}>
                <strong>{isHindi ? "पहचाने गए गंभीर लक्षण:" : "Identified Red Flags:"}</strong>
                <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
                  {emergencyAlert.red_flags.map((flag, idx) => (
                    <li key={idx} style={{ fontWeight: "600" }}>{flag}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="cv-emergency-hotlines">
              <span>📞 {isHindi ? "आपातकालीन नंबर:" : "Emergency Helplines:"}</span>
              <a href="tel:112" className="cv-hotline-btn">🚑 112 (National Emergency)</a>
              <a href="tel:108" className="cv-hotline-btn">🏥 108 (Ambulance)</a>
              <a href="tel:14416" className="cv-hotline-btn">🧠 14416 (Tele-MANAS Mental Health)</a>
            </div>
          </div>
        </div>
      )}

      {/* Boundary / Self-Prescribing Warning */}
      {boundaryViolation && (
        <div className="cv-alert cv-alert-warning" role="alert" style={{ marginBottom: "16px" }}>
          <span style={{ fontSize: "18px" }}>🛑</span>
          <div>
            <strong>{isHindi ? "क्लिनिकल सीमा उल्लंघन:" : "Clinical Encounter Boundary Alert:"}</strong>
            <p style={{ margin: "4px 0 0" }}>{boundaryViolation}</p>
          </div>
        </div>
      )}

      {/* Error & Status Banners */}
      {errorMessage && <div className="cv-alert cv-alert-danger" style={{ marginBottom: "16px" }}>{errorMessage}</div>}
      {statusMessage && <div className="cv-alert cv-alert-success" style={{ marginBottom: "16px" }}>{statusMessage}</div>}

      {/* Encounter Configuration Section */}
      <div className="cv-scribe-config-card">
        <div className="cv-form-row" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "12px" }}>
          <div>
            <label className="cv-label">{isHindi ? "सौंपा गया मरीज *" : "Assigned Patient *"}</label>
            <select
              className="cv-input"
              value={selectedPatientId}
              onChange={(e) => setSelectedPatientId(e.target.value)}
            >
              <option value="">{isHindi ? "-- मरीज चुनें --" : "-- Select Patient --"}</option>
              {assignedPatients.map((p) => (
                <option key={p.patient_user_id} value={p.patient_user_id}>
                  {p.patient_name} ({p.email})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="cv-label">{isHindi ? "अपॉइंटमेंट आईडी (वैकल्पिक)" : "Appointment ID (Optional)"}</label>
            <input
              type="number"
              className="cv-input"
              placeholder="e.g. 100"
              value={appointmentId}
              onChange={(e) => setAppointmentId(e.target.value)}
            />
          </div>

          <div>
            <label className="cv-label">{isHindi ? "परामर्श भाषा" : "Encounter Language"}</label>
            <select
              className="cv-input"
              value={consultLanguage}
              onChange={(e) => setConsultLanguage(e.target.value)}
            >
              <option value="en">English (Medical)</option>
              <option value="hi">हिन्दी (Hindi Consultation)</option>
            </select>
          </div>
        </div>

        {/* Input Mode Selector */}
        <div style={{ display: "flex", gap: "10px", marginTop: "16px", borderBottom: "1px solid var(--cv-border)", paddingBottom: "10px" }}>
          <button
            type="button"
            className={`cv-btn ${inputMode === "text" ? "cv-btn-primary" : "cv-btn-ghost"}`}
            onClick={() => setInputMode("text")}
            style={{ fontSize: "0.85rem" }}
          >
            ✍️ {isHindi ? "वार्तालाप टेक्स्ट" : "Dialogue Transcript"}
          </button>
          <button
            type="button"
            className={`cv-btn ${inputMode === "audio" ? "cv-btn-primary" : "cv-btn-ghost"}`}
            onClick={() => setInputMode("audio")}
            style={{ fontSize: "0.85rem" }}
          >
            🎙️ {isHindi ? "लाइव माइक्रोफ़ोन / ऑडियो फ़ाइल" : "Live Mic / Audio File"}
          </button>
          <button
            type="button"
            className="cv-btn cv-btn-secondary"
            onClick={loadSampleConsultation}
            style={{ fontSize: "0.85rem", marginLeft: "auto" }}
          >
            📋 {isHindi ? "नमूना बातचीत भरें" : "Load Sample Dialogue"}
          </button>
        </div>

        {/* Text Transcript Input */}
        {inputMode === "text" && (
          <div style={{ marginTop: "12px" }}>
            <textarea
              className="cv-input"
              rows={6}
              placeholder={
                isHindi
                  ? "डॉक्टर और मरीज के बीच हुई बातचीत यहाँ लिखें या पेस्ट करें…"
                  : "Paste or type doctor-patient dialogue transcript here...\nDoctor: Good morning, what brings you in today?\nPatient: I have had a high fever for two days..."
              }
              value={transcriptText}
              onChange={(e) => setTranscriptText(e.target.value)}
            />
          </div>
        )}

        {/* Live Audio / File Upload Input */}
        {inputMode === "audio" && (
          <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
              {!isRecording ? (
                <button
                  type="button"
                  className="cv-btn cv-btn-danger"
                  onClick={startRecording}
                  style={{ display: "flex", alignItems: "center", gap: "8px" }}
                >
                  <span className="cv-record-dot" />
                  <span>{isHindi ? "रिकॉर्डिंग शुरू करें" : "Start Live Consultation Recording"}</span>
                </button>
              ) : (
                <button
                  type="button"
                  className="cv-btn cv-btn-secondary"
                  onClick={stopRecording}
                  style={{ display: "flex", alignItems: "center", gap: "8px", borderColor: "var(--cv-danger)" }}
                >
                  <span className="cv-pulse-dot" />
                  <span>{isHindi ? "रोकें" : "Stop Recording"} ({formatDuration(recordingSeconds)})</span>
                </button>
              )}

              {audioBlob && !isRecording && (
                <span className="cv-badge cv-badge-routine" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span>✓</span>
                  <span>Audio Captured: {formatDuration(recordingSeconds)}</span>
                </span>
              )}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
              <span>— {isHindi ? "या ऑडियो फ़ाइल अपलोड करें:" : "Or upload consultation audio recording:"} —</span>
              <input
                type="file"
                accept="audio/*,.wav,.mp3,.m4a,.webm,.ogg"
                onChange={(e) => {
                  if (e.target.files?.[0]) setSelectedFile(e.target.files[0]);
                }}
              />
              {selectedFile && <span>({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)</span>}
            </div>
          </div>
        )}

        {/* Process Button */}
        <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
          <button
            type="button"
            className="cv-btn cv-btn-primary"
            onClick={handleGenerateSOAP}
            disabled={processing || isRecording}
            style={{ minWidth: "220px", display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}
          >
            {processing ? (
              <>
                <span className="cv-spinner-sm" />
                <span>{isHindi ? "प्रोसेस हो रहा है…" : "Analyzing Dialogue…"}</span>
              </>
            ) : (
              <>
                <span>⚡</span>
                <span>{isHindi ? "SOAP ड्राफ्ट तैयार करें" : "Generate Structured SOAP Draft"}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Two-Column SOAP Editor & Visual Diff Workspace */}
      {aiDraft && (
        <div className="cv-soap-workspace" style={{ marginTop: "24px" }}>
          {/* Workspace Status Bar */}
          <div className="cv-soap-toolbar">
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span className={`cv-badge ${isFinalized ? "cv-badge-routine" : "cv-badge-urgent"}`}>
                {isFinalized ? "✓ Finalized & Signed" : "⏳ AI Draft Note (Requires Clinician Signature)"}
              </span>
              <span style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)" }}>
                Note #{aiDraft.note_id}
              </span>
            </div>

            <div style={{ display: "flex", gap: "8px" }}>
              <button
                type="button"
                className={`cv-btn ${showDiff ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                onClick={() => setShowDiff(!showDiff)}
                style={{ fontSize: "0.8rem", padding: "4px 8px" }}
              >
                {showDiff ? "Hide AI Draft Diff" : "Show Side-by-Side Diff"}
              </button>
            </div>
          </div>

          {/* Clinical Insights Strip: Extracted Vitals, Allergies, Rx */}
          {(Object.keys(aiDraft.vitals_extracted || {}).length > 0 || (aiDraft.allergies_noted || []).length > 0) && (
            <div className="cv-extracted-insights-strip">
              {Object.keys(aiDraft.vitals_extracted || {}).length > 0 && (
                <div className="cv-insight-group">
                  <span className="cv-insight-title">📊 Extracted Vitals:</span>
                  {Object.entries(aiDraft.vitals_extracted).map(([key, val]) => (
                    <span key={key} className="cv-vitals-pill">
                      <strong>{key.toUpperCase()}:</strong> {val}
                    </span>
                  ))}
                </div>
              )}

              {aiDraft.allergies_noted?.length > 0 && (
                <div className="cv-insight-group">
                  <span className="cv-insight-title">⚠️ Allergies Identified:</span>
                  {aiDraft.allergies_noted.map((all, i) => (
                    <span key={i} className="cv-badge cv-badge-urgent">
                      {all}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Two-Column Editor Layout */}
          <div className={`cv-diff-editor ${showDiff ? "split" : "single"}`}>
            {/* Left Column: AI Draft (Read-Only Reference) */}
            {showDiff && (
              <div className="cv-diff-column ai-reference">
                <div className="cv-column-header">
                  <span>🤖 AI Ambient Draft (Read-Only)</span>
                  <span className="cv-col-tag">Unverified</span>
                </div>

                <div className="cv-diff-section">
                  <label className="cv-diff-label">Chief Complaint</label>
                  <div className="cv-diff-box">{aiDraft.chief_complaint || "—"}</div>
                </div>

                <div className="cv-diff-section">
                  <label className="cv-diff-label">Subjective (HPI)</label>
                  <div className="cv-diff-box">{aiDraft.subjective || "—"}</div>
                </div>

                <div className="cv-diff-section">
                  <label className="cv-diff-label">Objective (Exam & Vitals)</label>
                  <div className="cv-diff-box">{aiDraft.objective || "—"}</div>
                </div>

                <div className="cv-diff-section">
                  <label className="cv-diff-label">Assessment</label>
                  <div className="cv-diff-box">{aiDraft.assessment || "—"}</div>
                </div>

                <div className="cv-diff-section">
                  <label className="cv-diff-label">Plan & Prescriptions</label>
                  <div className="cv-diff-box">{aiDraft.plan || "—"}</div>
                </div>

                <div className="cv-diff-section">
                  <label className="cv-diff-label">Follow-up Instructions</label>
                  <div className="cv-diff-box">{aiDraft.follow_up_instructions || "—"}</div>
                </div>
              </div>
            )}

            {/* Right Column: Doctor Verified Note (Editable) */}
            <div className="cv-diff-column doctor-edit">
              <div className="cv-column-header">
                <span>🩺 Doctor Final Clinical Note (Editable)</span>
                <span className="cv-col-tag clinician">Clinical Primacy</span>
              </div>

              <div className="cv-diff-section">
                <label className="cv-diff-label">Chief Complaint *</label>
                <input
                  type="text"
                  className="cv-input"
                  disabled={isFinalized}
                  value={editedNote.chief_complaint}
                  onChange={(e) => setEditedNote({ ...editedNote, chief_complaint: e.target.value })}
                />
              </div>

              <div className="cv-diff-section">
                <label className="cv-diff-label">Subjective (History of Present Illness) *</label>
                <textarea
                  className="cv-input"
                  rows={4}
                  disabled={isFinalized}
                  value={editedNote.subjective}
                  onChange={(e) => setEditedNote({ ...editedNote, subjective: e.target.value })}
                />
              </div>

              <div className="cv-diff-section">
                <label className="cv-diff-label">Objective (Examination & Vitals) *</label>
                <textarea
                  className="cv-input"
                  rows={4}
                  disabled={isFinalized}
                  value={editedNote.objective}
                  onChange={(e) => setEditedNote({ ...editedNote, objective: e.target.value })}
                />
              </div>

              <div className="cv-diff-section">
                <label className="cv-diff-label">Assessment (Diagnostic Reasoning) *</label>
                <textarea
                  className="cv-input"
                  rows={3}
                  disabled={isFinalized}
                  value={editedNote.assessment}
                  onChange={(e) => setEditedNote({ ...editedNote, assessment: e.target.value })}
                />
              </div>

              <div className="cv-diff-section">
                <label className="cv-diff-label">Plan & Treatment *</label>
                <textarea
                  className="cv-input"
                  rows={4}
                  disabled={isFinalized}
                  value={editedNote.plan}
                  onChange={(e) => setEditedNote({ ...editedNote, plan: e.target.value })}
                />
              </div>

              <div className="cv-diff-section">
                <label className="cv-diff-label">Follow-up Instructions</label>
                <textarea
                  className="cv-input"
                  rows={2}
                  disabled={isFinalized}
                  value={editedNote.follow_up_instructions}
                  onChange={(e) => setEditedNote({ ...editedNote, follow_up_instructions: e.target.value })}
                />
              </div>

              {/* Electronic Signature Box */}
              <div className="cv-signature-box">
                <label className="cv-label" style={{ fontWeight: "700" }}>
                  ✍️ {isHindi ? "चिकित्सक का इलेक्ट्रॉनिक हस्ताक्षर *" : "Registered Medical Practitioner Electronic Signature *"}
                </label>
                <input
                  type="text"
                  className="cv-input"
                  disabled={isFinalized}
                  placeholder="e.g. Dr. Shivam Vishwakarma (MCI Reg: 84920/2020)"
                  value={doctorSignature}
                  onChange={(e) => setDoctorSignature(e.target.value)}
                />
                <small style={{ color: "var(--cv-text-muted)", display: "block", marginTop: "4px" }}>
                  By signing, you confirm personal clinical verification and assume full legal diagnostic responsibility under NMC guidelines.
                </small>
              </div>

              {/* Finalization Action Row */}
              <div style={{ marginTop: "16px", display: "flex", gap: "10px", justifyContent: "flex-end" }}>
                {!isFinalized ? (
                  <button
                    type="button"
                    className="cv-btn cv-btn-primary"
                    onClick={handleFinalizeNote}
                    disabled={processing}
                    style={{ minWidth: "220px", display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}
                  >
                    <span>🛡️</span>
                    <span>{isHindi ? "हस्ताक्षर करें व अंतिम रूप दें" : "Sign & Finalize Clinical Note"}</span>
                  </button>
                ) : (
                  <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
                    <span className="cv-badge cv-badge-routine">
                      ✓ Electronically Signed: {finalizedData?.finalized_at || new Date().toLocaleString()}
                    </span>
                    <button
                      type="button"
                      className="cv-btn cv-btn-secondary"
                      onClick={() => fetchPatientGuide("en")}
                      disabled={loadingGuide}
                    >
                      {loadingGuide && guideLang === "en" ? "Generating..." : "📄 Patient Guide (English)"}
                    </button>
                    <button
                      type="button"
                      className="cv-btn cv-btn-secondary"
                      onClick={() => fetchPatientGuide("hi")}
                      disabled={loadingGuide}
                    >
                      {loadingGuide && guideLang === "hi" ? "तैयार हो रहा है…" : "📄 मरीज गाइड (हिन्दी)"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Multilingual Patient Care Guide Modal / Display */}
      {patientGuide && (
        <div className="cv-patient-guide-modal" style={{ marginTop: "24px" }}>
          <div className="cv-guide-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--cv-border)", paddingBottom: "10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "20px" }}>📖</span>
                <h3 style={{ margin: 0 }}>{patientGuide.title}</h3>
                <span className="cv-badge cv-badge-routine">{patientGuide.language === "hi" ? "हिन्दी" : "English"}</span>
              </div>
              <button className="cv-btn cv-btn-ghost" onClick={() => setPatientGuide(null)}>✕</button>
            </div>

            <div style={{ margin: "14px 0" }}>
              <p><strong>Clinician:</strong> {patientGuide.doctor_name} ({patientGuide.specialty})</p>
              <p><strong>Patient:</strong> {patientGuide.patient_name}</p>
              <p style={{ marginTop: "8px", lineHeight: "1.5" }}>{patientGuide.overview}</p>
            </div>

            {patientGuide.medications?.length > 0 && (
              <div style={{ margin: "14px 0" }}>
                <h4 style={{ margin: "0 0 8px" }}>💊 {guideLang === "hi" ? "निर्धारित दवाइयां:" : "Prescribed Medications:"}</h4>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {patientGuide.medications.map((m, idx) => (
                    <div key={idx} style={{ padding: "8px 12px", background: "var(--cv-surface-soft)", borderRadius: "8px" }}>
                      <strong>{m.medication}</strong> {m.strength && `(${m.strength})`} — {m.frequency} ({m.duration})
                      <div style={{ fontSize: "0.85rem", color: "var(--cv-text-muted)", marginTop: "2px" }}>
                        <em>{m.instructions}</em>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {patientGuide.follow_up_instructions && (
              <div style={{ margin: "14px 0" }}>
                <h4 style={{ margin: "0 0 4px" }}>📋 {guideLang === "hi" ? "फॉलो-अप निर्देश:" : "Follow-Up Instructions:"}</h4>
                <p style={{ margin: 0 }}>{patientGuide.follow_up_instructions}</p>
              </div>
            )}

            {patientGuide.red_flag_warnings?.length > 0 && (
              <div className="cv-alert cv-alert-warning" style={{ margin: "14px 0" }}>
                <h4 style={{ margin: "0 0 4px" }}>⚠️ {guideLang === "hi" ? "सावधानी व खतरे के संकेत:" : "Red-Flag Warning Signs:"}</h4>
                <ul style={{ margin: "4px 0", paddingLeft: "20px" }}>
                  {patientGuide.red_flag_warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="cv-emergency-hotlines" style={{ marginTop: "14px" }}>
              <span>📞 {guideLang === "hi" ? "आपातकालीन संपर्क:" : "Emergency Contacts:"}</span>
              {(patientGuide.emergency_contacts || ["112 (National Emergency)", "108 (Ambulance)", "14416 (Tele-MANAS)"]).map((c, i) => (
                <span key={i} className="cv-hotline-btn">{c}</span>
              ))}
            </div>

            <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button
                type="button"
                className="cv-btn cv-btn-secondary"
                onClick={() => window.print()}
              >
                🖨️ {guideLang === "hi" ? "प्रिंट करें" : "Print Guide"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
