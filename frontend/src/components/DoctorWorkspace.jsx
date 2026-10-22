import { useEffect, useState } from "react";
import { apiRequest } from "../services/api";
import { getUrgencyBadgeConfig } from "../services/assistantHelpers";
import { EmptyState, ScreenTitle } from "./PortalScreens";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

export function DoctorWorkspace({ token, user, language = "en", onNavigate }) {
  const isHindi = language === "hi";
  const [activeTab, setActiveTab] = useState("patients");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [workspace, setWorkspace] = useState(null);

  // Selected patient for clinical workflow
  const [selectedPatientId, setSelectedPatientId] = useState(null);
  const [patientOverview, setPatientOverview] = useState(null);
  const [overviewLoading, setOverviewLoading] = useState(false);

  // Clinical Note Form State
  const [noteForm, setNoteForm] = useState({
    patient_user_id: "",
    appointment_id: "",
    chief_complaint: "",
    history_of_present_illness: "",
    examination_findings: "",
    assessment: "",
    plan: "",
    follow_up_instructions: "",
    is_ai_draft: false,
  });
  const [savingNote, setSavingNote] = useState(false);

  // Prescription Form State
  const [rxForm, setRxForm] = useState({
    patient_user_id: "",
    appointment_id: "",
    diagnosis: "",
    notes: "",
    allergy_warnings: [],
    items: [
      {
        medication_name: "",
        strength: "",
        dosage_form: "tablet",
        route: "oral",
        frequency: "1-0-1",
        duration: "5 days",
        quantity: "10 tablets",
        instructions: "Take after meals",
      },
    ],
  });
  const [savingRx, setSavingRx] = useState(false);
  const [activeAllergies, setActiveAllergies] = useState([]);

  useEffect(() => {
    loadWorkspace();
  }, [token]);

  async function loadWorkspace() {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const data = await apiRequest("/records/doctor/workspace", token);
      setWorkspace(data);
      if (data?.assigned_patients?.length > 0 && !selectedPatientId) {
        setSelectedPatientId(data.assigned_patients[0].patient_user_id);
        setNoteForm((prev) => ({ ...prev, patient_user_id: data.assigned_patients[0].patient_user_id }));
        setRxForm((prev) => ({ ...prev, patient_user_id: data.assigned_patients[0].patient_user_id }));
      }
    } catch (err) {
      setError(err.message || "Failed to load doctor workspace.");
    } finally {
      setLoading(false);
    }
  }

  async function loadPatientDetails(patientId) {
    setSelectedPatientId(patientId);
    setOverviewLoading(true);
    try {
      const [overviewData, allergyData] = await Promise.all([
        apiRequest(`/records/overview?patient_user_id=${patientId}`, token),
        apiRequest(`/records/allergies?patient_user_id=${patientId}`, token).catch(() => []),
      ]);
      setPatientOverview(overviewData);
      setActiveAllergies(allergyData || []);
      setNoteForm((prev) => ({ ...prev, patient_user_id: patientId }));
      setRxForm((prev) => ({ ...prev, patient_user_id: patientId }));
    } catch (err) {
      alert(`Could not load patient details: ${err.message}`);
    } finally {
      setOverviewLoading(false);
    }
  }

  async function handleAIDraftNote() {
    if (!selectedPatientId) {
      alert("Please select a patient first.");
      return;
    }
    setSavingNote(true);
    try {
      const draft = await apiRequest("/records/notes/ai-draft", token, {
        method: "POST",
        body: JSON.stringify({
          patient_user_id: Number(selectedPatientId),
          appointment_id: noteForm.appointment_id ? Number(noteForm.appointment_id) : null,
          symptoms_context: noteForm.chief_complaint || "Patient clinical evaluation",
        }),
      });
      setNoteForm({
        patient_user_id: selectedPatientId,
        appointment_id: noteForm.appointment_id,
        chief_complaint: draft.chief_complaint || "",
        history_of_present_illness: draft.history_of_present_illness || "",
        examination_findings: draft.examination_findings || "",
        assessment: draft.assessment || "",
        plan: draft.plan || "",
        follow_up_instructions: draft.follow_up_instructions || "",
        is_ai_draft: true,
      });
      setNotice("✨ AI draft note generated from encounter context. Please review and verify all details before saving.");
    } catch (err) {
      alert(`AI Draft failed: ${err.message}`);
    } finally {
      setSavingNote(false);
    }
  }

  async function handleSaveNote(finalize = false) {
    if (!selectedPatientId) return;
    setSavingNote(true);
    setNotice("");
    try {
      const created = await apiRequest("/records/notes", token, {
        method: "POST",
        body: JSON.stringify({
          patient_user_id: Number(selectedPatientId),
          appointment_id: noteForm.appointment_id ? Number(noteForm.appointment_id) : null,
          note_type: "consultation_note",
          chief_complaint: noteForm.chief_complaint,
          history_of_present_illness: noteForm.history_of_present_illness,
          examination_findings: noteForm.examination_findings,
          assessment: noteForm.assessment,
          plan: noteForm.plan,
          follow_up_instructions: noteForm.follow_up_instructions,
          is_ai_draft: noteForm.is_ai_draft,
        }),
      });

      if (finalize) {
        await apiRequest(`/records/notes/${created.id}/finalize`, token, { method: "POST" });
        setNotice("✅ Clinical note finalized and electronically signed.");
      } else {
        setNotice("💾 Clinical note saved as draft.");
      }
      loadPatientDetails(selectedPatientId);
    } catch (err) {
      alert(`Failed to save note: ${err.message}`);
    } finally {
      setSavingNote(false);
    }
  }

  async function handleAIDraftPrescription() {
    if (!selectedPatientId) {
      alert("Please select a patient first.");
      return;
    }
    setSavingRx(true);
    try {
      const draft = await apiRequest("/records/prescriptions/ai-draft", token, {
        method: "POST",
        body: JSON.stringify({
          patient_user_id: Number(selectedPatientId),
          diagnosis_hint: rxForm.diagnosis || "Symptomatic relief",
        }),
      });
      setRxForm((prev) => ({
        ...prev,
        diagnosis: draft.diagnosis || prev.diagnosis,
        notes: draft.notes || prev.notes,
        allergy_warnings: draft.allergy_warnings || [],
        items: draft.items || prev.items,
      }));
      if (draft.allergy_warnings?.length > 0) {
        alert(`⚠️ ALLERGY WARNING: ${draft.allergy_warnings.join("\n")}`);
      }
      setNotice("✨ AI prescription draft generated. Review medicine doses and allergy warnings.");
    } catch (err) {
      alert(`AI Draft failed: ${err.message}`);
    } finally {
      setSavingRx(false);
    }
  }

  function handleAddMedicineItem() {
    setRxForm((prev) => ({
      ...prev,
      items: [
        ...prev.items,
        {
          medication_name: "",
          strength: "",
          dosage_form: "tablet",
          route: "oral",
          frequency: "1-0-1",
          duration: "5 days",
          quantity: "10 tablets",
          instructions: "Take after meals",
        },
      ],
    }));
  }

  function handleRemoveMedicineItem(index) {
    setRxForm((prev) => ({
      ...prev,
      items: prev.items.filter((_, i) => i !== index),
    }));
  }

  function handleMedicineChange(index, field, value) {
    setRxForm((prev) => {
      const newItems = [...prev.items];
      newItems[index] = { ...newItems[index], [field]: value };
      return { ...prev, items: newItems };
    });
  }

  async function handleSavePrescription(finalize = false) {
    if (!selectedPatientId) return;
    setSavingRx(true);
    setNotice("");
    try {
      const validItems = rxForm.items.filter((it) => it.medication_name.trim());
      if (validItems.length === 0) {
        alert("Please add at least one medication.");
        setSavingRx(false);
        return;
      }
      const created = await apiRequest("/records/prescriptions", token, {
        method: "POST",
        body: JSON.stringify({
          patient_user_id: Number(selectedPatientId),
          appointment_id: rxForm.appointment_id ? Number(rxForm.appointment_id) : null,
          diagnosis: rxForm.diagnosis,
          notes: rxForm.notes,
          items: validItems,
        }),
      });

      if (finalize) {
        await apiRequest(`/records/prescriptions/${created.id}/finalize`, token, { method: "POST" });
        setNotice(`✅ Prescription ${created.prescription_number} finalized and signed.`);
      } else {
        setNotice(`💾 Prescription draft ${created.prescription_number} saved.`);
      }
      loadPatientDetails(selectedPatientId);
    } catch (err) {
      alert(`Failed to save prescription: ${err.message}`);
    } finally {
      setSavingRx(false);
    }
  }

  async function handleReviewReport(reportId) {
    try {
      await apiRequest(`/records/reports/${reportId}/review`, token, { method: "POST" });
      setNotice("✅ AI Assessment marked as reviewed by attending doctor.");
      loadWorkspace();
    } catch (err) {
      alert(`Review failed: ${err.message}`);
    }
  }

  async function downloadBinary(urlPath, filename) {
    try {
      const resp = await fetch(`${API_BASE}${urlPath}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
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
    }
  }

  return (
    <div className="doctor-workspace-container">
      <ScreenTitle
        eyebrow="AUTHORIZED CLINICAL WORKSPACE"
        title={isHindi ? "डॉक्टर कार्यक्षेत्र" : "Doctor Clinical Workspace"}
        description={
          workspace
            ? `${workspace.doctor_name} • ${workspace.specialty} • ${workspace.hospital_name || "CareVoice Network"}`
            : "Authorized encounter documentation, AI triage assessment review, and clinical prescribing."
        }
      />

      {error && <div className="cv-alert cv-alert-danger">{error}</div>}
      {notice && <div className="cv-alert cv-alert-success">{notice}</div>}

      {/* Navigation Sub-Tabs */}
      <div style={{ display: "flex", gap: "0.5rem", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.5rem", marginBottom: "1.5rem", overflowX: "auto" }}>
        {[
          { id: "patients", label: isHindi ? "सौंपे गए मरीज" : "Assigned Patients", icon: "👥", count: workspace?.assigned_patients?.length },
          { id: "notes", label: isHindi ? "क्लिनिकल नोट्स" : "Clinical Notes", icon: "✍️" },
          { id: "prescribe", label: isHindi ? "पर्चा लेखक (Rx)" : "Prescription Builder", icon: "℞" },
          { id: "inbox", label: isHindi ? "AI आकलन इनबॉक्स" : "AI Assessment Inbox", icon: "📥", count: workspace?.recent_ai_assessments?.length },
          { id: "history", label: isHindi ? "मरीज इतिहास" : "Patient Longitudinal History", icon: "📋" },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`cv-btn ${activeTab === tab.id ? "cv-btn-primary" : "cv-btn-ghost"}`}
            style={{ borderRadius: "20px", fontSize: "0.9rem", padding: "0.4rem 0.9rem", whiteSpace: "nowrap" }}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon} {tab.label} {tab.count !== undefined ? `(${tab.count})` : ""}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ padding: "2rem", textAlign: "center" }}>Loading clinician workspace…</div>
      ) : (
        <>
          {/* TAB 1: ASSIGNED PATIENTS */}
          {activeTab === "patients" && (
            <div>
              {workspace?.assigned_patients?.length === 0 ? (
                <EmptyState
                  icon="👥"
                  title="No Assigned Patients"
                  description="Patients with scheduled or past appointments with you will appear in your authorized workspace."
                />
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: "1rem" }}>
                  {workspace?.assigned_patients?.map((p) => (
                    <div key={p.patient_user_id} className="cv-card" style={{ padding: "1.2rem", borderTop: "4px solid var(--color-primary)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <h4 style={{ margin: "0 0 0.2rem 0", fontSize: "1.1rem" }}>{p.patient_name}</h4>
                          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>{p.email}</span>
                        </div>
                        {p.active_allergies_count > 0 && (
                          <span className="cv-badge cv-badge-urgent" title="Patient has recorded allergies">
                            ⚠️ {p.active_allergies_count} Allergies
                          </span>
                        )}
                      </div>

                      <div style={{ margin: "0.8rem 0", fontSize: "0.85rem", display: "grid", gap: "0.3rem" }}>
                        <div>
                          <b>Next Appointment:</b>{" "}
                          {p.next_appointment ? new Date(p.next_appointment).toLocaleDateString() : "None scheduled"}
                        </div>
                        <div>
                          <b>AI Triage Assessments:</b> {p.pending_ai_assessments_count}
                        </div>
                        <div>
                          <b>Total Prescriptions:</b> {p.total_prescriptions_count}
                        </div>
                      </div>

                      <div style={{ display: "flex", gap: "0.4rem", marginTop: "1rem" }}>
                        <button
                          className="cv-btn cv-btn-xs cv-btn-primary"
                          onClick={() => {
                            loadPatientDetails(p.patient_user_id);
                            setActiveTab("notes");
                          }}
                        >
                          ✍️ Write Note
                        </button>
                        <button
                          className="cv-btn cv-btn-xs cv-btn-secondary"
                          onClick={() => {
                            loadPatientDetails(p.patient_user_id);
                            setActiveTab("prescribe");
                          }}
                        >
                          ℞ Prescribe
                        </button>
                        <button
                          className="cv-btn cv-btn-xs cv-btn-outline"
                          onClick={() => {
                            loadPatientDetails(p.patient_user_id);
                            setActiveTab("history");
                          }}
                        >
                          📋 History
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: CLINICAL NOTES */}
          {activeTab === "notes" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1.6fr", gap: "1.5rem" }}>
              {/* Left Column: Patient selector and recent notes */}
              <div>
                <h4 style={{ margin: "0 0 0.8rem 0" }}>1. Select Patient</h4>
                <select
                  className="cv-select"
                  style={{ width: "100%", marginBottom: "1rem" }}
                  value={selectedPatientId || ""}
                  onChange={(e) => loadPatientDetails(Number(e.target.value))}
                >
                  <option value="">-- Choose Assigned Patient --</option>
                  {workspace?.assigned_patients?.map((p) => (
                    <option key={p.patient_user_id} value={p.patient_user_id}>
                      {p.patient_name} ({p.email})
                    </option>
                  ))}
                </select>

                {overviewLoading && <div>Loading patient records…</div>}

                {patientOverview && (
                  <div className="cv-card" style={{ padding: "1rem", fontSize: "0.88rem" }}>
                    <b>Patient:</b> {patientOverview.full_name} ({patientOverview.gender || "N/A"}, Age: {patientOverview.age || "N/A"})
                    {patientOverview.allergies?.length > 0 && (
                      <div style={{ marginTop: "0.4rem", color: "#dc2626" }}>
                        <b>⚠️ Allergies:</b> {patientOverview.allergies.map((a) => a.allergen_or_condition).join(", ")}
                      </div>
                    )}
                    <h5 style={{ margin: "0.8rem 0 0.4rem 0" }}>Recent Clinical Notes ({patientOverview.recent_notes?.length || 0}):</h5>
                    {patientOverview.recent_notes?.map((n) => (
                      <div key={n.id} style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--border-color)" }}>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{new Date(n.created_at).toLocaleDateString()}</span>
                        <div><b>{n.chief_complaint}</b> ({n.status})</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Right Column: Note Editor Form */}
              <div className="cv-card" style={{ padding: "1.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <h3 style={{ margin: 0, fontSize: "1.15rem" }}>Author Encounter Note</h3>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-outline"
                    onClick={handleAIDraftNote}
                    disabled={savingNote || !selectedPatientId}
                  >
                    ✨ AI Draft Note from Context
                  </button>
                </div>

                {noteForm.is_ai_draft && (
                  <div className="cv-alert cv-alert-warning" style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
                    <b>AI-Generated Draft:</b> Clinician oversight required. Review and verify all observations before signing.
                  </div>
                )}

                <div style={{ display: "grid", gap: "0.8rem" }}>
                  <div>
                    <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>Chief Complaint *</label>
                    <input
                      className="cv-input"
                      type="text"
                      placeholder="e.g., Persistent productive cough, 3 days"
                      value={noteForm.chief_complaint}
                      onChange={(e) => setNoteForm({ ...noteForm, chief_complaint: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>History of Present Illness (HPI)</label>
                    <textarea
                      className="cv-input"
                      rows={3}
                      placeholder="Onset, duration, severity, fever, relieving/aggravating factors..."
                      value={noteForm.history_of_present_illness}
                      onChange={(e) => setNoteForm({ ...noteForm, history_of_present_illness: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>Physical Examination Findings</label>
                    <textarea
                      className="cv-input"
                      rows={2}
                      placeholder="Vitals: BP, Pulse, Temp, Chest auscultation, throat examination..."
                      value={noteForm.examination_findings}
                      onChange={(e) => setNoteForm({ ...noteForm, examination_findings: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>Clinical Assessment / Impression *</label>
                    <input
                      className="cv-input"
                      type="text"
                      placeholder="e.g., Acute Upper Respiratory Tract Infection (URTI)"
                      value={noteForm.assessment}
                      onChange={(e) => setNoteForm({ ...noteForm, assessment: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>Management Plan</label>
                    <textarea
                      className="cv-input"
                      rows={2}
                      placeholder="Therapeutic plan, investigations ordered, lifestyle advice..."
                      value={noteForm.plan}
                      onChange={(e) => setNoteForm({ ...noteForm, plan: e.target.value })}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>Follow-up Instructions & Red Flags</label>
                    <input
                      className="cv-input"
                      type="text"
                      placeholder="e.g., Return in 3 days; seek immediate care if breathing difficulty occurs."
                      value={noteForm.follow_up_instructions}
                      onChange={(e) => setNoteForm({ ...noteForm, follow_up_instructions: e.target.value })}
                    />
                  </div>
                </div>

                <div style={{ display: "flex", gap: "0.8rem", marginTop: "1.2rem" }}>
                  <button
                    className="cv-btn cv-btn-secondary"
                    onClick={() => handleSaveNote(false)}
                    disabled={savingNote || !noteForm.chief_complaint}
                  >
                    💾 Save as Draft
                  </button>
                  <button
                    className="cv-btn cv-btn-primary"
                    onClick={() => handleSaveNote(true)}
                    disabled={savingNote || !noteForm.chief_complaint}
                  >
                    ✍️ Finalize & Electronically Sign Note
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: PRESCRIPTION BUILDER */}
          {activeTab === "prescribe" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: "1.5rem" }}>
              {/* Left Column: Patient selector & Allergy Warning */}
              <div>
                <h4 style={{ margin: "0 0 0.8rem 0" }}>1. Select Patient</h4>
                <select
                  className="cv-select"
                  style={{ width: "100%", marginBottom: "1rem" }}
                  value={selectedPatientId || ""}
                  onChange={(e) => loadPatientDetails(Number(e.target.value))}
                >
                  <option value="">-- Choose Assigned Patient --</option>
                  {workspace?.assigned_patients?.map((p) => (
                    <option key={p.patient_user_id} value={p.patient_user_id}>
                      {p.patient_name} ({p.email})
                    </option>
                  ))}
                </select>

                {activeAllergies.length > 0 && (
                  <div className="cv-alert cv-alert-danger" style={{ marginBottom: "1rem" }}>
                    <b>⚠️ ACTIVE PATIENT ALLERGIES:</b>
                    <ul style={{ margin: "0.4rem 0 0 1.2rem", padding: 0 }}>
                      {activeAllergies.map((a) => (
                        <li key={a.id}>
                          <b>{a.allergen_or_condition}</b> ({a.severity}) {a.reaction ? `- ${a.reaction}` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {patientOverview?.recent_prescriptions?.length > 0 && (
                  <div className="cv-card" style={{ padding: "1rem" }}>
                    <h5 style={{ margin: "0 0 0.6rem 0" }}>Prior Prescriptions:</h5>
                    {patientOverview.recent_prescriptions.map((p) => (
                      <div key={p.id} style={{ fontSize: "0.85rem", marginBottom: "0.6rem", borderBottom: "1px solid var(--border-color)", paddingBottom: "0.4rem" }}>
                        <div><b>{p.prescription_number}</b> ({p.status})</div>
                        <div style={{ color: "var(--text-muted)" }}>{p.diagnosis || "No diagnosis"}</div>
                        <button
                          className="cv-btn cv-btn-xs cv-btn-outline"
                          style={{ marginTop: "0.3rem" }}
                          onClick={() => downloadBinary(`/records/prescriptions/${p.id}/pdf`, `rx-${p.prescription_number}.pdf`)}
                        >
                          📄 Download PDF
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Right Column: Rx Builder */}
              <div className="cv-card" style={{ padding: "1.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <h3 style={{ margin: 0, fontSize: "1.15rem" }}>Prescription Authoring (Rx)</h3>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-outline"
                    onClick={handleAIDraftPrescription}
                    disabled={savingRx || !selectedPatientId}
                  >
                    ✨ AI Draft with Allergy Check
                  </button>
                </div>

                <div style={{ display: "grid", gap: "0.8rem", marginBottom: "1rem" }}>
                  <div>
                    <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>Clinical Diagnosis / Indication *</label>
                    <input
                      className="cv-input"
                      type="text"
                      placeholder="e.g., Acute Bronchitis, Hypertension"
                      value={rxForm.diagnosis}
                      onChange={(e) => setRxForm({ ...rxForm, diagnosis: e.target.value })}
                    />
                  </div>
                </div>

                {rxForm.allergy_warnings?.length > 0 && (
                  <div className="cv-alert cv-alert-danger" style={{ marginBottom: "1rem" }}>
                    <b>🚨 ALLERGY CONFLICT WARNING:</b>
                    <ul style={{ margin: "0.4rem 0 0 1.2rem", padding: 0 }}>
                      {rxForm.allergy_warnings.map((w, idx) => (
                        <li key={idx}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Medicine Items */}
                <h4 style={{ margin: "1rem 0 0.5rem 0" }}>Medication Items:</h4>
                <div style={{ display: "grid", gap: "0.8rem" }}>
                  {rxForm.items.map((item, idx) => (
                    <div key={idx} style={{ padding: "0.8rem", background: "var(--bg-card)", border: "1px solid var(--border-color)", borderRadius: "8px" }}>
                      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: "0.5rem", marginBottom: "0.5rem" }}>
                        <div>
                          <label style={{ fontSize: "0.75rem" }}>Medicine Name *</label>
                          <input
                            className="cv-input"
                            placeholder="e.g., Paracetamol, Amoxicillin"
                            value={item.medication_name}
                            onChange={(e) => handleMedicineChange(idx, "medication_name", e.target.value)}
                          />
                        </div>
                        <div>
                          <label style={{ fontSize: "0.75rem" }}>Strength</label>
                          <input
                            className="cv-input"
                            placeholder="500 mg"
                            value={item.strength}
                            onChange={(e) => handleMedicineChange(idx, "strength", e.target.value)}
                          />
                        </div>
                        <div>
                          <label style={{ fontSize: "0.75rem" }}>Form</label>
                          <select
                            className="cv-select"
                            value={item.dosage_form}
                            onChange={(e) => handleMedicineChange(idx, "dosage_form", e.target.value)}
                          >
                            <option value="tablet">Tablet</option>
                            <option value="capsule">Capsule</option>
                            <option value="syrup">Syrup</option>
                            <option value="drops">Drops</option>
                            <option value="inhaler">Inhaler</option>
                            <option value="ointment">Ointment</option>
                          </select>
                        </div>
                        <div>
                          <label style={{ fontSize: "0.75rem" }}>Frequency</label>
                          <input
                            className="cv-input"
                            placeholder="1-0-1"
                            value={item.frequency}
                            onChange={(e) => handleMedicineChange(idx, "frequency", e.target.value)}
                          />
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr auto", gap: "0.5rem", alignItems: "flex-end" }}>
                        <div>
                          <label style={{ fontSize: "0.75rem" }}>Duration</label>
                          <input
                            className="cv-input"
                            placeholder="5 days"
                            value={item.duration}
                            onChange={(e) => handleMedicineChange(idx, "duration", e.target.value)}
                          />
                        </div>
                        <div>
                          <label style={{ fontSize: "0.75rem" }}>Quantity</label>
                          <input
                            className="cv-input"
                            placeholder="10 tabs"
                            value={item.quantity}
                            onChange={(e) => handleMedicineChange(idx, "quantity", e.target.value)}
                          />
                        </div>
                        <div>
                          <label style={{ fontSize: "0.75rem" }}>Patient Instructions</label>
                          <input
                            className="cv-input"
                            placeholder="After food with warm water"
                            value={item.instructions}
                            onChange={(e) => handleMedicineChange(idx, "instructions", e.target.value)}
                          />
                        </div>
                        {rxForm.items.length > 1 && (
                          <button
                            type="button"
                            className="cv-btn cv-btn-xs cv-btn-danger"
                            onClick={() => handleRemoveMedicineItem(idx)}
                          >
                            ✕ Remove
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                <button
                  type="button"
                  className="cv-btn cv-btn-xs cv-btn-outline"
                  style={{ marginTop: "0.8rem" }}
                  onClick={handleAddMedicineItem}
                >
                  + Add Medication
                </button>

                <div style={{ marginTop: "1rem" }}>
                  <label style={{ fontSize: "0.85rem", fontWeight: "bold" }}>General Advice & Clinical Notes</label>
                  <textarea
                    className="cv-input"
                    rows={2}
                    placeholder="Adequate hydration, warm fluids, review in 3 days..."
                    value={rxForm.notes}
                    onChange={(e) => setRxForm({ ...rxForm, notes: e.target.value })}
                  />
                </div>

                <div style={{ display: "flex", gap: "0.8rem", marginTop: "1.2rem" }}>
                  <button
                    className="cv-btn cv-btn-secondary"
                    onClick={() => handleSavePrescription(false)}
                    disabled={savingRx || !selectedPatientId}
                  >
                    💾 Save Draft
                  </button>
                  <button
                    className="cv-btn cv-btn-primary"
                    onClick={() => handleSavePrescription(true)}
                    disabled={savingRx || !selectedPatientId}
                  >
                    ✍️ Finalize & Sign Prescription (Rx)
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: AI ASSESSMENT INBOX */}
          {activeTab === "inbox" && (
            <div>
              {workspace?.recent_ai_assessments?.length === 0 ? (
                <EmptyState
                  icon="📥"
                  title="No AI Triage Assessments"
                  description="Pre-consultation AI triage sessions and symptom assessments from your assigned patients will appear here."
                />
              ) : (
                <div style={{ display: "grid", gap: "1rem" }}>
                  {workspace?.recent_ai_assessments?.map((a) => {
                    const badge = getUrgencyBadgeConfig(a.urgency_level);
                    return (
                      <div key={a.id} className="cv-card" style={{ padding: "1.2rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
                          <div>
                            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                              Patient: <b>{a.patient_name}</b> • {new Date(a.created_at).toLocaleDateString()}
                            </span>
                            <h3 style={{ margin: "0.2rem 0", fontSize: "1.1rem" }}>{a.title}</h3>
                          </div>
                          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                            <span className={`cv-badge ${badge.className}`}>{badge.icon} {badge.label}</span>
                            <button
                              className="cv-btn cv-btn-xs cv-btn-primary"
                              onClick={() => {
                                loadPatientDetails(a.patient_user_id);
                                setNoteForm((prev) => ({
                                  ...prev,
                                  patient_user_id: a.patient_user_id,
                                  chief_complaint: a.title,
                                  history_of_present_illness: `Patient pre-triage: ${a.summary}`,
                                }));
                                setActiveTab("notes");
                              }}
                            >
                              ✍️ Create Note from Assessment
                            </button>
                          </div>
                        </div>
                        <p style={{ margin: "0.6rem 0", fontSize: "0.92rem" }}>
                          <b>Patient Summary:</b> {a.summary || "No summary recorded."}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: PATIENT LONGITUDINAL HISTORY */}
          {activeTab === "history" && (
            <div>
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ fontSize: "0.85rem", fontWeight: "bold", display: "block", marginBottom: "0.3rem" }}>
                  Select Assigned Patient:
                </label>
                <select
                  className="cv-select"
                  style={{ maxWidth: "400px" }}
                  value={selectedPatientId || ""}
                  onChange={(e) => loadPatientDetails(Number(e.target.value))}
                >
                  <option value="">-- Choose Assigned Patient --</option>
                  {workspace?.assigned_patients?.map((p) => (
                    <option key={p.patient_user_id} value={p.patient_user_id}>
                      {p.patient_name} ({p.email})
                    </option>
                  ))}
                </select>
              </div>

              {overviewLoading ? (
                <div>Loading patient longitudinal records…</div>
              ) : patientOverview ? (
                <div style={{ display: "grid", gap: "1rem" }}>
                  <div className="cv-card" style={{ padding: "1.2rem" }}>
                    <h3>Patient Profile Overview</h3>
                    <div><b>Name:</b> {patientOverview.full_name}</div>
                    <div><b>Email:</b> {patientOverview.email}</div>
                    <div><b>Gender:</b> {patientOverview.gender || "N/A"} | <b>Age:</b> {patientOverview.age || "N/A"}</div>
                    {patientOverview.allergies?.length > 0 && (
                      <div style={{ marginTop: "0.5rem", color: "#dc2626" }}>
                        <b>⚠️ Allergies:</b> {patientOverview.allergies.map((a) => `${a.allergen_or_condition} (${a.severity})`).join("; ")}
                      </div>
                    )}
                  </div>

                  <div className="cv-card" style={{ padding: "1.2rem" }}>
                    <h3>Prescription History ({patientOverview.recent_prescriptions?.length || 0})</h3>
                    {patientOverview.recent_prescriptions?.map((rx) => (
                      <div key={rx.id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                        <b>{rx.prescription_number}</b> ({rx.status}) — Diagnosis: {rx.diagnosis || "Clinical evaluation"}
                        <button
                          className="cv-btn cv-btn-xs cv-btn-outline"
                          style={{ marginLeft: "1rem" }}
                          onClick={() => downloadBinary(`/records/prescriptions/${rx.id}/pdf`, `rx-${rx.prescription_number}.pdf`)}
                        >
                          Download PDF
                        </button>
                      </div>
                    ))}
                  </div>

                  <div className="cv-card" style={{ padding: "1.2rem" }}>
                    <h3>Clinical Consultation Notes ({patientOverview.recent_notes?.length || 0})</h3>
                    {patientOverview.recent_notes?.map((n) => (
                      <div key={n.id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border-color)" }}>
                        <b>{n.chief_complaint}</b> ({n.status}) • {new Date(n.created_at).toLocaleDateString()}
                        <p style={{ margin: "0.2rem 0", fontSize: "0.88rem" }}>{n.assessment}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyState
                  icon="📋"
                  title="Select a Patient"
                  description="Pick an assigned patient from the dropdown above to inspect their longitudinal medical records."
                />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
