import { useEffect, useState } from "react";
import { apiRequest } from "../services/api";
import { getUrgencyBadgeConfig } from "../services/assistantHelpers";
import { EmptyState, ScreenTitle } from "./PortalScreens";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

function formatFileSize(bytes) {
  if (!bytes || typeof bytes !== "number") return "0 KB";
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(isoString) {
  if (!isoString) return "";
  try {
    return new Date(isoString).toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return isoString;
  }
}

export function PatientHealthRecords({ token, language = "en", onNavigate }) {
  const isHindi = language === "hi";
  const [activeTab, setActiveTab] = useState("timeline");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloadingId, setDownloadingId] = useState(null);

  // Clinical records collections
  const [timeline, setTimeline] = useState([]);
  const [reports, setReports] = useState([]);
  const [prescriptions, setPrescriptions] = useState([]);
  const [notes, setNotes] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [allergies, setAllergies] = useState([]);
  const [filterType, setFilterType] = useState("all");

  // Document upload state
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadType, setUploadType] = useState("lab_report");
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadNotice, setUploadNotice] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);

  useEffect(() => {
    loadAllRecords();
  }, [token]);

  async function loadAllRecords() {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const [tlData, repData, rxData, noteData, docData, algData] = await Promise.all([
        apiRequest("/records/timeline", token).catch(() => ({ events: [] })),
        apiRequest("/records/reports", token).catch(() => []),
        apiRequest("/records/prescriptions", token).catch(() => []),
        apiRequest("/records/notes", token).catch(() => []),
        apiRequest("/records/documents", token).catch(() => []),
        apiRequest("/records/allergies", token).catch(() => []),
      ]);
      setTimeline(tlData?.events || []);
      setReports(repData || []);
      setPrescriptions(rxData || []);
      setNotes(noteData || []);
      setDocuments(docData || []);
      setAllergies(algData || []);
    } catch (err) {
      setError(err.message || "Failed to load clinical records.");
    } finally {
      setLoading(false);
    }
  }

  async function downloadBinary(urlPath, filename, downloadKey) {
    setDownloadingId(downloadKey);
    try {
      const resp = await fetch(`${API_BASE}${urlPath}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        throw new Error(`Download failed with status ${resp.status}`);
      }
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
      alert(`Could not download file: ${err.message}`);
    } finally {
      setDownloadingId(null);
    }
  }

  function handleFileSelection(file) {
    setUploadError("");
    setUploadNotice("");
    if (!file) return;

    if (file.size > 10 * 1024 * 1024) {
      setUploadError(isHindi ? "फ़ाइल का आकार 10 MB से अधिक नहीं हो सकता।" : "File size exceeds the 10 MB limit.");
      return;
    }

    const validExtensions = [".pdf", ".jpg", ".jpeg", ".png", ".webp"];
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!validExtensions.includes(ext)) {
      setUploadError(isHindi ? "केवल PDF, JPG, PNG, WEBP प्रारूप समर्थित हैं।" : "Only PDF, JPG, PNG, and WEBP formats are supported.");
      return;
    }

    setUploadFile(file);
    if (!uploadTitle.trim()) {
      const suggestedTitle = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
      setUploadTitle(suggestedTitle.charAt(0).toUpperCase() + suggestedTitle.slice(1));
    }
  }

  async function handleUploadDocument(event) {
    event.preventDefault();
    if (!uploadFile || !uploadTitle.trim()) {
      setUploadError(isHindi ? "कृपया शीर्षक दर्ज करें और एक वैध फ़ाइल चुनें।" : "Please enter a document title and select a valid file.");
      return;
    }

    setUploading(true);
    setUploadError("");
    setUploadNotice("");
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("title", uploadTitle.trim());
      formData.append("document_type", uploadType);

      await apiRequest("/records/documents/upload", token, {
        method: "POST",
        body: formData,
      });

      setUploadTitle("");
      setUploadFile(null);
      setUploadNotice(isHindi ? "दस्तावेज़ सफलतापूर्वक अपलोड किया गया।" : "Medical document uploaded successfully.");
      const updatedDocs = await apiRequest("/records/documents", token);
      setDocuments(updatedDocs || []);
    } catch (err) {
      setUploadError(err.message || "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  async function exportFHIRBundle() {
    try {
      const bundle = await apiRequest("/records/fhir/export", token);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = `carevoice-fhir-record-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objUrl);
    } catch (err) {
      alert(`FHIR Export failed: ${err.message}`);
    }
  }

  const filteredEvents = timeline.filter((ev) => {
    if (filterType === "all") return true;
    return ev.event_type === filterType;
  });

  return (
    <div className="health-records-container">
      {/* Header with Responsive FHIR Action */}
      <div className="health-records-header-bar">
        <ScreenTitle
          eyebrow={isHindi ? "लॉन्गिट्यूडिनल स्वास्थ्य रिकॉर्ड" : "LONGITUDINAL PATIENT RECORD"}
          title={isHindi ? "मेरे स्वास्थ्य रिकॉर्ड" : "My Health Records"}
          description={
            isHindi
              ? "अपने सभी AI आकलन, डॉक्टर के पर्चे, क्लिनिकल नोट्स, और प्रयोगशाला रिपोर्ट एक ही सुरक्षित स्थान पर देखें।"
              : "Access your consolidated health history, AI triage assessments, doctor-signed prescriptions, clinical notes, and diagnostic records."
          }
        />
        <div style={{ alignSelf: "flex-start", marginTop: "10px" }}>
          <button
            className="cv-btn cv-btn-secondary"
            onClick={exportFHIRBundle}
            title="Export standard HL7 FHIR R4 JSON Bundle"
          >
            <span>📥</span>
            <span>{isHindi ? "FHIR R4 निर्यात" : "Export FHIR R4"}</span>
          </button>
        </div>
      </div>

      {error && <div className="cv-alert cv-alert-danger" style={{ marginBottom: "20px" }}>{error}</div>}

      {/* Allergies Notice Banner */}
      {allergies.length > 0 && (
        <div className="cv-alert cv-alert-warning" style={{ marginBottom: "24px" }}>
          <span style={{ fontSize: "18px" }}>⚠️</span>
          <div style={{ flex: 1 }}>
            <strong>{isHindi ? "सत्यापित मरीज एलर्जी व प्रतिकूल प्रतिक्रियाएं:" : "Recorded Patient Allergies & Adverse Reactions:"}</strong>
            <div style={{ marginTop: "6px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {allergies.map((al) => (
                <span key={al.id} className="cv-badge cv-badge-urgent">
                  {al.allergen_or_condition} ({al.severity})
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Record Navigation Tabs */}
      <div className="health-records-tabs" role="tablist">
        {[
          { id: "timeline", label: isHindi ? "कालक्रम" : "Timeline", icon: "⏱", count: timeline.length },
          { id: "reports", label: isHindi ? "AI आकलन रिपोर्ट" : "AI Reports", icon: "📑", count: reports.length },
          { id: "prescriptions", label: isHindi ? "डॉक्टर के पर्चे (Rx)" : "Prescriptions", icon: "℞", count: prescriptions.length },
          { id: "notes", label: isHindi ? "क्लिनिकल नोट्स" : "Doctor Notes", icon: "🩺", count: notes.length },
          { id: "documents", label: isHindi ? "दस्तावेज़ व लैब रिपोर्ट" : "Documents", icon: "📁", count: documents.length },
        ].map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`health-records-tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span className="health-records-tab-count">{tab.count}</span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ padding: "48px 16px", textAlign: "center", color: "var(--cv-text-muted)" }}>
          <div className="cv-spinner" style={{ margin: "0 auto 16px" }} />
          <div>{isHindi ? "स्वास्थ्य रिकॉर्ड लोड हो रहे हैं…" : "Loading clinical records…"}</div>
        </div>
      ) : (
        <>
          {/* =========================================================================
              TAB 1: TIMELINE
              ========================================================================= */}
          {activeTab === "timeline" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px", flexWrap: "wrap", gap: "10px" }}>
                <div style={{ fontSize: "13px", color: "var(--cv-text-muted)", fontWeight: "600" }}>
                  {isHindi ? `कुल ${filteredEvents.length} प्रविष्टियां` : `Showing ${filteredEvents.length} chronological events`}
                </div>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {[
                    { id: "all", label: isHindi ? "सभी" : "All" },
                    { id: "assessment", label: isHindi ? "AI आकलन" : "AI Assessments" },
                    { id: "prescription", label: isHindi ? "पर्चे" : "Prescriptions" },
                    { id: "note", label: isHindi ? "क्लिनिकल नोट्स" : "Notes" },
                    { id: "appointment", label: isHindi ? "अपॉइंटमेंट" : "Appointments" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      className={`cv-btn cv-btn-xs ${filterType === f.id ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                      onClick={() => setFilterType(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {filteredEvents.length === 0 ? (
                <EmptyState
                  icon="⏱"
                  title={isHindi ? "कोई रिकॉर्ड नहीं मिला" : "No timeline events recorded"}
                  description={isHindi ? "आपकी स्वास्थ्य परामर्श और विज़िट यहाँ कालक्रम में दिखाई देंगी।" : "Your health assessments, visits, and clinical records will appear here chronologically."}
                />
              ) : (
                <div className="timeline-flow">
                  {filteredEvents.map((ev) => {
                    const badge = ev.urgency_level ? getUrgencyBadgeConfig(ev.urgency_level) : null;
                    const dotClass = ev.category === "clinician" ? "clinician" : (ev.category === "ai" ? "ai" : "patient");
                    return (
                      <div key={ev.id} className="timeline-item">
                        <div className={`timeline-dot ${dotClass}`} />
                        <div className="record-card">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                                <span className="cv-badge cv-badge-neutral" style={{ textTransform: "uppercase" }}>
                                  {ev.category} • {ev.event_type.replace("_", " ")}
                                </span>
                                {badge && (
                                  <span className={`cv-badge ${badge.className}`}>
                                    {badge.label}
                                  </span>
                                )}
                              </div>
                              <h3 style={{ margin: "6px 0 2px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                                {ev.title}
                              </h3>
                            </div>
                            <time style={{ fontSize: "12px", color: "var(--cv-text-muted)", fontWeight: "600" }}>
                              {formatDate(ev.timestamp)}
                            </time>
                          </div>

                          <p style={{ margin: "8px 0 10px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                            {ev.description}
                          </p>

                          {ev.actor_name && (
                            <div style={{ fontSize: "12px", color: "var(--cv-text-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
                              <span>👤</span>
                              <span>{ev.actor_role === "doctor" ? "Clinician:" : "Actor:"}</span>
                              <strong style={{ color: "var(--cv-text-primary)" }}>{ev.actor_name}</strong>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 2: AI REPORTS
              ========================================================================= */}
          {activeTab === "reports" && (
            <div>
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — NOT A REAL PATIENT ASSESSMENT
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {isHindi ? `कुल ${reports.length} रिपोर्ट` : `${reports.length} structured clinical assessments`}
                </span>
              </div>

              {reports.length === 0 ? (
                <EmptyState
                  icon="📑"
                  title={isHindi ? "कोई AI रिपोर्ट नहीं है" : "No AI reports generated"}
                  description={isHindi ? "CareVoice सहायक के साथ परामर्श के बाद आप रिपोर्ट तैयार कर सकते हैं।" : "You can generate structured AI reports after completing a symptom assessment with CareVoice."}
                />
              ) : (
                <div style={{ display: "grid", gap: "16px" }}>
                  {reports.map((rep) => {
                    const badge = getUrgencyBadgeConfig(rep.urgency_level);
                    const isDownloading = downloadingId === `rep-${rep.report_id}`;
                    return (
                      <div key={rep.id} className="record-card">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "10px", borderBottom: "1px solid var(--cv-border-soft)", paddingBottom: "12px", marginBottom: "12px" }}>
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
                              <span style={{ fontSize: "11px", fontWeight: "700", color: "var(--cv-text-muted)", letterSpacing: "0.05em" }}>
                                REF: REP-{rep.report_id.slice(0, 8).toUpperCase()}
                              </span>
                              <span style={{ fontSize: "12px", color: "var(--cv-border-control)" }}>•</span>
                              <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                                {formatDate(rep.created_at)}
                              </span>
                              <span className={`cv-badge ${badge.className}`}>
                                {badge.label}
                              </span>
                            </div>
                            <h3 style={{ margin: "4px 0 0", fontSize: "17px", color: "var(--cv-text-primary)" }}>
                              {rep.title}
                            </h3>
                          </div>
                          <button
                            className="cv-btn cv-btn-sm cv-btn-outline"
                            disabled={isDownloading}
                            onClick={() =>
                              downloadBinary(
                                `/records/reports/${rep.report_id}/pdf`,
                                `report-${rep.report_id.slice(0, 8)}.pdf`,
                                `rep-${rep.report_id}`
                              )
                            }
                          >
                            <span>📄</span>
                            <span>{isDownloading ? (isHindi ? "डाउनलोड हो रहा है…" : "Downloading…") : (isHindi ? "PDF डाउनलोड" : "Download PDF")}</span>
                          </button>
                        </div>

                        {/* Summary */}
                        <div style={{ marginBottom: "12px" }}>
                          <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>
                            Clinical Summary
                          </div>
                          <p style={{ margin: 0, fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                            {rep.summary}
                          </p>
                        </div>

                        {/* Findings */}
                        {rep.findings?.length > 0 && (
                          <div style={{ marginBottom: "12px" }}>
                            <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "6px" }}>
                              Key Findings & Observations
                            </div>
                            <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                              {rep.findings.map((f, idx) => (
                                <li key={idx}>
                                  <strong>{f.finding || f.title || f}:</strong> {f.significance || f.notes || ""}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Red Flags Alert if present */}
                        {rep.red_flags?.length > 0 && (
                          <div className="cv-alert cv-alert-danger" style={{ marginBottom: "12px", padding: "10px 12px" }}>
                            <span>🚨</span>
                            <div>
                              <strong>Clinical Warning Flags:</strong>
                              <div style={{ marginTop: "2px" }}>{rep.red_flags.join("; ")}</div>
                            </div>
                          </div>
                        )}

                        {/* Recommended Next Steps */}
                        {rep.recommended_next_steps?.length > 0 && (
                          <div style={{ marginBottom: "12px" }}>
                            <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "6px" }}>
                              Recommended Clinical Next Steps
                            </div>
                            <ol style={{ margin: 0, paddingLeft: "18px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                              {rep.recommended_next_steps.map((st, idx) => (
                                <li key={idx}>{st}</li>
                              ))}
                            </ol>
                          </div>
                        )}

                        {/* Evidence Sources */}
                        {rep.evidence_sources?.length > 0 && (
                          <div style={{ marginBottom: "10px", fontSize: "12px", color: "var(--cv-text-muted)" }}>
                            <strong style={{ color: "var(--cv-text-secondary)" }}>Evidence Citations: </strong>
                            {rep.evidence_sources.map((s, idx) => (
                              <span key={idx}>
                                {idx > 0 && " • "}
                                <a
                                  href={s.url || "#"}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{ color: "var(--cv-accent-text)", textDecoration: "none" }}
                                >
                                  {s.title || s.provenance}
                                </a>
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Clinician Review & Disclaimer */}
                        <div style={{ marginTop: "12px", paddingTop: "10px", borderTop: "1px dashed var(--cv-border)", fontSize: "11px", color: "var(--cv-text-muted)", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
                          <span>
                            {rep.reviewed_at ? (
                              <strong style={{ color: "var(--cv-accent-text)" }}>
                                ✓ Electronically verified by attending clinician on {formatDate(rep.reviewed_at)}
                              </strong>
                            ) : (
                              "Status: Generated AI Assessment"
                            )}
                          </span>
                          <span style={{ fontStyle: "italic", maxWidth: "600px" }}>
                            {rep.disclaimer}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 3: PRESCRIPTIONS
              ========================================================================= */}
          {activeTab === "prescriptions" && (
            <div>
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — DOCTOR-SIGNED DIGITAL PRESCRIPTIONS
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {isHindi ? `कुल ${prescriptions.length} पर्चे` : `${prescriptions.length} finalized prescriptions`}
                </span>
              </div>

              {prescriptions.length === 0 ? (
                <EmptyState
                  icon="℞"
                  title={isHindi ? "कोई पर्चा नहीं मिला" : "No finalized prescriptions"}
                  description={isHindi ? "आपके परामर्श चिकित्सक द्वारा जारी किए गए पर्चे यहाँ दिखाई देंगे।" : "Prescriptions authored and finalized by your licensed clinician will appear here."}
                />
              ) : (
                <div style={{ display: "grid", gap: "20px" }}>
                  {prescriptions.map((rx) => {
                    const isDownloading = downloadingId === `rx-${rx.id}`;
                    return (
                      <div key={rx.id} className="record-card record-card-rx">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "10px", borderBottom: "1px solid var(--cv-border-soft)", paddingBottom: "14px", marginBottom: "14px" }}>
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                              <span style={{ fontSize: "20px", fontWeight: "900", color: "var(--cv-accent)" }}>℞</span>
                              <h3 style={{ margin: 0, fontSize: "17px", color: "var(--cv-text-primary)" }}>
                                {rx.prescription_number}
                              </h3>
                              <span className="cv-badge cv-badge-success" style={{ textTransform: "uppercase" }}>
                                {rx.status}
                              </span>
                            </div>
                            <div style={{ fontSize: "12px", color: "var(--cv-text-muted)", marginTop: "4px" }}>
                              Prescribed by <strong style={{ color: "var(--cv-text-primary)" }}>Dr. {rx.doctor_name || "Clinician"}</strong> on {formatDate(rx.finalized_at || rx.created_at)}
                            </div>
                          </div>
                          <button
                            className="cv-btn cv-btn-sm cv-btn-primary"
                            disabled={isDownloading}
                            onClick={() =>
                              downloadBinary(
                                `/records/prescriptions/${rx.id}/pdf`,
                                `prescription-${rx.prescription_number}.pdf`,
                                `rx-${rx.id}`
                              )
                            }
                          >
                            <span>📥</span>
                            <span>{isDownloading ? (isHindi ? "डाउनलोड हो रहा है…" : "Downloading…") : (isHindi ? "पर्चा डाउनलोड (PDF)" : "Download Rx PDF")}</span>
                          </button>
                        </div>

                        {rx.diagnosis && (
                          <div style={{ marginBottom: "12px", fontSize: "13px" }}>
                            <strong style={{ color: "var(--cv-text-secondary)" }}>Diagnosis: </strong>
                            <span style={{ color: "var(--cv-text-primary)", fontWeight: "600" }}>{rx.diagnosis}</span>
                          </div>
                        )}

                        {rx.allergy_warnings?.length > 0 && (
                          <div className="cv-alert cv-alert-warning" style={{ marginBottom: "14px", padding: "8px 12px", fontSize: "12px" }}>
                            <span>⚠️</span>
                            <div>
                              <strong>Allergy Safety Verification: </strong>
                              {rx.allergy_warnings.join("; ")}
                            </div>
                          </div>
                        )}

                        {/* Medication Table */}
                        <div style={{ overflowX: "auto", marginBottom: "12px", borderRadius: "8px", border: "1px solid var(--cv-border)" }}>
                          <table className="cv-table">
                            <thead>
                              <tr>
                                <th>Medicine & Strength</th>
                                <th>Form / Route</th>
                                <th>Frequency</th>
                                <th>Duration</th>
                                <th>Instructions</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rx.items?.map((it) => (
                                <tr key={it.id}>
                                  <td>
                                    <strong>{it.medication_name}</strong> {it.strength ? `(${it.strength})` : ""}
                                  </td>
                                  <td>{it.dosage_form} • {it.route}</td>
                                  <td>
                                    <span className="cv-badge cv-badge-routine">{it.frequency}</span>
                                  </td>
                                  <td>{it.duration}</td>
                                  <td>{it.instructions || "As directed"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        {rx.notes && (
                          <div style={{ marginTop: "10px", padding: "10px 12px", borderRadius: "8px", background: "var(--cv-surface-soft)", fontSize: "12px", color: "var(--cv-text-secondary)" }}>
                            <strong style={{ color: "var(--cv-text-primary)" }}>Doctor's Advice & Precautions: </strong>
                            {rx.notes}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 4: CLINICAL NOTES
              ========================================================================= */}
          {activeTab === "notes" && (
            <div>
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — CLINICIAN CONSULTATION ENCOUNTER NOTES
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {isHindi ? `कुल ${notes.length} नोट्स` : `${notes.length} finalized consultation notes`}
                </span>
              </div>

              {notes.length === 0 ? (
                <EmptyState
                  icon="🩺"
                  title={isHindi ? "कोई विज़िट नोट नहीं है" : "No clinical notes"}
                  description={isHindi ? "डॉक्टर द्वारा हस्ताक्षरित परामर्श नोट्स यहाँ दिखाई देंगे।" : "Finalized clinical consultation notes from your appointments will appear here."}
                />
              ) : (
                <div style={{ display: "grid", gap: "16px" }}>
                  {notes.map((n) => (
                    <div key={n.id} className="record-card">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", borderBottom: "1px solid var(--cv-border-soft)", paddingBottom: "12px", marginBottom: "12px" }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
                            <span className="cv-badge cv-badge-info" style={{ textTransform: "uppercase" }}>
                              {n.note_type?.replace("_", " ")}
                            </span>
                            <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                              {formatDate(n.finalized_at || n.created_at)}
                            </span>
                            <span style={{ fontSize: "12px", color: "var(--cv-border-control)" }}>•</span>
                            <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                              Attending: <strong style={{ color: "var(--cv-text-primary)" }}>Dr. {n.doctor_name || "Clinician"}</strong>
                            </span>
                          </div>
                          <h3 style={{ margin: "4px 0 0", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                            {n.chief_complaint || "Clinical Consultation Note"}
                          </h3>
                        </div>
                        <span className="cv-badge cv-badge-success" style={{ textTransform: "uppercase" }}>
                          {n.status}
                        </span>
                      </div>

                      {n.history_of_present_illness && (
                        <div style={{ marginBottom: "10px", fontSize: "13px", lineHeight: "1.6" }}>
                          <strong style={{ color: "var(--cv-text-secondary)" }}>History of Present Illness: </strong>
                          <span style={{ color: "var(--cv-text-body)" }}>{n.history_of_present_illness}</span>
                        </div>
                      )}

                      {n.examination_findings && (
                        <div style={{ marginBottom: "10px", fontSize: "13px", lineHeight: "1.6" }}>
                          <strong style={{ color: "var(--cv-text-secondary)" }}>Physical Examination Findings: </strong>
                          <span style={{ color: "var(--cv-text-body)" }}>{n.examination_findings}</span>
                        </div>
                      )}

                      {n.assessment && (
                        <div style={{ marginBottom: "10px", fontSize: "13px", lineHeight: "1.6" }}>
                          <strong style={{ color: "var(--cv-text-secondary)" }}>Assessment & Clinical Impression: </strong>
                          <span style={{ color: "var(--cv-text-body)" }}>{n.assessment}</span>
                        </div>
                      )}

                      {n.plan && (
                        <div style={{ marginBottom: "10px", fontSize: "13px", lineHeight: "1.6" }}>
                          <strong style={{ color: "var(--cv-text-secondary)" }}>Treatment & Management Plan: </strong>
                          <span style={{ color: "var(--cv-text-body)" }}>{n.plan}</span>
                        </div>
                      )}

                      {n.follow_up_instructions && (
                        <div style={{ marginTop: "10px", padding: "8px 12px", borderRadius: "8px", background: "var(--cv-surface-soft)", fontSize: "12px", color: "var(--cv-text-muted)" }}>
                          <strong style={{ color: "var(--cv-text-primary)" }}>Follow-up Instructions: </strong>
                          {n.follow_up_instructions}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 5: DOCUMENTS & LAB REPORTS
              ========================================================================= */}
          {activeTab === "documents" && (
            <div>
              {/* Redesigned Upload Card */}
              <div className="health-records-upload-card">
                <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
                  <span style={{ fontSize: "20px" }}>📤</span>
                  <h3 style={{ margin: 0, fontSize: "17px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "नया मेडिकल दस्तावेज़ या लैब रिपोर्ट अपलोड करें" : "Upload Medical Document or Diagnostic Report"}
                  </h3>
                </div>
                <p style={{ margin: "0 0 16px", fontSize: "13px", color: "var(--cv-text-muted)", lineHeight: "1.5" }}>
                  {isHindi
                    ? "अपने पिछले परीक्षण परिणाम, एक्स-रे, एमआरआई, या बाहरी पर्चे अपलोड करें ताकि आपका मेडिकल चार्ट हमेशा अद्यतन रहे।"
                    : "Add outside diagnostic panels, radiology imaging scans, discharge summaries, or previous prescriptions to keep your longitudinal record comprehensive."}
                </p>

                {uploadNotice && (
                  <div className="cv-alert cv-alert-success" style={{ marginBottom: "16px" }}>
                    <span>✓</span>
                    <div>{uploadNotice}</div>
                  </div>
                )}
                {uploadError && (
                  <div className="cv-alert cv-alert-danger" style={{ marginBottom: "16px" }}>
                    <span>⚠️</span>
                    <div>{uploadError}</div>
                  </div>
                )}

                <form onSubmit={handleUploadDocument}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "14px", marginBottom: "14px" }}>
                    <div>
                      <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "var(--cv-text-secondary)", marginBottom: "6px" }}>
                        {isHindi ? "दस्तावेज़ का शीर्षक *" : "Document Title *"}
                      </label>
                      <input
                        className="cv-input"
                        type="text"
                        required
                        placeholder={isHindi ? "उदा. सीबीसी रक्त परीक्षण, चेस्ट एक्स-रे" : "e.g., Complete Blood Count, Chest X-Ray"}
                        value={uploadTitle}
                        onChange={(e) => setUploadTitle(e.target.value)}
                      />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "var(--cv-text-secondary)", marginBottom: "6px" }}>
                        {isHindi ? "दस्तावेज़ का प्रकार *" : "Document Category *"}
                      </label>
                      <select
                        className="cv-select"
                        value={uploadType}
                        onChange={(e) => setUploadType(e.target.value)}
                      >
                        <option value="lab_report">Lab Report (Pathology / Biochemistry)</option>
                        <option value="imaging">Imaging (X-Ray, CT Scan, MRI, ECG)</option>
                        <option value="discharge_summary">Hospital Discharge Summary</option>
                        <option value="prescription">Prior / External Prescription</option>
                        <option value="other">Other Clinical Document</option>
                      </select>
                    </div>
                  </div>

                  {/* Drag and Drop Zone */}
                  <div
                    className={`health-records-dropzone ${isDragOver ? "active" : ""}`}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setIsDragOver(true);
                    }}
                    onDragLeave={(e) => {
                      e.preventDefault();
                      setIsDragOver(false);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setIsDragOver(false);
                      if (e.dataTransfer.files?.[0]) {
                        handleFileSelection(e.dataTransfer.files[0]);
                      }
                    }}
                    onClick={() => {
                      document.getElementById("cv-file-picker-input")?.click();
                    }}
                  >
                    <input
                      id="cv-file-picker-input"
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,.webp"
                      style={{ display: "none" }}
                      onChange={(e) => {
                        if (e.target.files?.[0]) {
                          handleFileSelection(e.target.files[0]);
                        }
                      }}
                    />
                    <div style={{ fontSize: "28px", marginBottom: "6px" }}>📁</div>
                    <div style={{ fontSize: "14px", fontWeight: "700", color: "var(--cv-text-primary)", marginBottom: "4px" }}>
                      {isHindi ? "फ़ाइल चुनने के लिए क्लिक करें या यहाँ खींचकर छोड़ें" : "Click to browse or drag and drop your file here"}
                    </div>
                    <div style={{ display: "flex", justifyContent: "center", gap: "8px", flexWrap: "wrap", marginTop: "8px" }}>
                      <span className="cv-badge cv-badge-routine">PDF, JPG, PNG, WEBP</span>
                      <span className="cv-badge cv-badge-neutral">Max 10 MB</span>
                    </div>
                  </div>

                  {/* Selected File Preview */}
                  {uploadFile && (
                    <div className="health-records-file-preview">
                      <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
                        <span style={{ fontSize: "20px" }}>📄</span>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: "13px", fontWeight: "700", color: "var(--cv-text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {uploadFile.name}
                          </div>
                          <div style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                            {formatFileSize(uploadFile.size)} • {uploadFile.type || "Document"}
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="cv-btn cv-btn-xs cv-btn-ghost"
                        onClick={(e) => {
                          e.stopPropagation();
                          setUploadFile(null);
                        }}
                        title="Remove file"
                      >
                        ✕ Remove
                      </button>
                    </div>
                  )}

                  <div style={{ marginTop: "16px", display: "flex", justifyContent: "flex-end" }}>
                    <button
                      type="submit"
                      className="cv-btn cv-btn-primary"
                      disabled={uploading || !uploadFile || !uploadTitle.trim()}
                    >
                      <span>📤</span>
                      <span>
                        {uploading
                          ? (isHindi ? "अपलोड हो रहा है…" : "Uploading document…")
                          : (isHindi ? "दस्तावेज़ अपलोड करें" : "Upload Document")}
                      </span>
                    </button>
                  </div>
                </form>
              </div>

              {/* Documents List */}
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — VERIFIED CLINICAL DIAGNOSTIC REPORTS
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {isHindi ? `कुल ${documents.length} दस्तावेज़` : `${documents.length} diagnostic reports`}
                </span>
              </div>

              {documents.length === 0 ? (
                <EmptyState
                  icon="📁"
                  title={isHindi ? "कोई दस्तावेज़ नहीं है" : "No uploaded documents"}
                  description={isHindi ? "अपनी पिछली रिपोर्ट, रक्त परीक्षण, या डिस्चार्ज सारांश यहाँ अपलोड करें।" : "Upload previous medical reports, blood tests, or diagnostic summaries here."}
                />
              ) : (
                <div style={{ display: "grid", gap: "12px" }}>
                  {documents.map((d) => {
                    const isDownloading = downloadingId === `doc-${d.id}`;
                    return (
                      <div key={d.id} className="record-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
                        <div style={{ minWidth: 0, flex: "1 1 280px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
                            <span className="cv-badge cv-badge-routine" style={{ textTransform: "uppercase" }}>
                              {d.document_type.replace("_", " ")}
                            </span>
                            <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                              {formatFileSize(d.file_size)}
                            </span>
                            <span style={{ fontSize: "12px", color: "var(--cv-border-control)" }}>•</span>
                            <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                              {formatDate(d.created_at)}
                            </span>
                          </div>
                          <h4 style={{ margin: "2px 0 0", fontSize: "15px", color: "var(--cv-text-primary)" }}>
                            {d.title}
                          </h4>
                          {d.notes && (
                            <div style={{ fontSize: "12px", color: "var(--cv-text-muted)", marginTop: "2px" }}>
                              {d.notes}
                            </div>
                          )}
                        </div>
                        <button
                          className="cv-btn cv-btn-sm cv-btn-outline"
                          disabled={isDownloading}
                          onClick={() =>
                            downloadBinary(
                              `/records/documents/${d.id}/download`,
                              d.title.replace(/\s+/g, "_") + ".pdf",
                              `doc-${d.id}`
                            )
                          }
                        >
                          <span>📥</span>
                          <span>{isDownloading ? (isHindi ? "डाउनलोड हो रहा है…" : "Downloading…") : (isHindi ? "डाउनलोड PDF" : "Download PDF")}</span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
