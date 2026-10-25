import { useEffect, useState, useRef, useCallback } from "react";
import { apiRequest } from "../services/api";
import { getUrgencyBadgeConfig } from "../services/assistantHelpers";
import { EmptyState, ScreenTitle } from "./PortalScreens";
import Modal from "./Modal";
import { DPDPPrivacyCenter } from "./DPDPPrivacyCenter";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

// Formats binary byte counts into human-readable kilobytes or megabytes.
function formatFileSize(bytes) {
  if (!bytes || typeof bytes !== "number") return "0 KB";
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Converts ISO-8601 timestamps into Indian localized date strings (DD MMM YYYY).
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

// Patient health records dashboard organizing longitudinal timelines, doctor notes, prescriptions, and FHIR exports.
export function PatientHealthRecords({ token, language = "en", onNavigate }) {
  const isHindi = language === "hi";
  const [activeTab, setActiveTab] = useState("timeline");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloadingId, setDownloadingId] = useState(null);

  // Tablist navigation refs and overflow indicators
  const tablistRef = useRef(null);
  const tabRefs = useRef({});
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  // Clinical records collections
  const [timeline, setTimeline] = useState([]);
  const [reports, setReports] = useState([]);
  const [prescriptions, setPrescriptions] = useState([]);
  const [notes, setNotes] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [allergies, setAllergies] = useState([]);
  const [overview, setOverview] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [invoices, setInvoices] = useState([]);

  // Search and filter states across tabs
  const [filterType, setFilterType] = useState("all");
  const [timelineSearch, setTimelineSearch] = useState("");
  const [reportFilter, setReportFilter] = useState("all");
  const [reportSearch, setReportSearch] = useState("");
  const [rxFilter, setRxFilter] = useState("all");
  const [rxSearch, setRxSearch] = useState("");
  const [noteFilter, setNoteFilter] = useState("all");
  const [noteSearch, setNoteSearch] = useState("");
  const [docCategoryFilter, setDocCategoryFilter] = useState("all");
  const [docSearch, setDocSearch] = useState("");
  const [convSearch, setConvSearch] = useState("");
  const [billingFilter, setBillingFilter] = useState("all");
  const [billingSearch, setBillingSearch] = useState("");

  // Modals
  const [selectedRecordModal, setSelectedRecordModal] = useState(null);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [loadingConversation, setLoadingConversation] = useState(false);

  // Patient Care Guide State
  const [guideApptId, setGuideApptId] = useState("");
  const [guideLang, setGuideLang] = useState("en");
  const [careGuide, setCareGuide] = useState(null);
  const [loadingGuide, setLoadingGuide] = useState(false);
  const [guideError, setGuideError] = useState("");

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

  // Fetches timeline events, clinical notes, prescriptions, lab reports, allergies, and billing invoices.
  async function loadAllRecords() {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const [tlData, repData, rxData, noteData, docData, algData, ovData, convData, invData] = await Promise.all([
        apiRequest("/records/timeline", token).catch(() => ({ events: [] })),
        apiRequest("/records/reports", token).catch(() => []),
        apiRequest("/records/prescriptions?include_drafts=true", token).catch(() => []),
        apiRequest("/records/notes?include_drafts=true", token).catch(() => []),
        apiRequest("/records/documents", token).catch(() => []),
        apiRequest("/records/allergies", token).catch(() => []),
        apiRequest("/records/overview", token).catch(() => null),
        apiRequest("/assistant/assessments", token).catch(() => []),
        apiRequest("/billing/invoices", token).catch(() => []),
      ]);
      setTimeline(tlData?.events || []);
      setReports(repData || []);
      setPrescriptions(rxData || []);
      setNotes(noteData || []);
      setDocuments(docData || []);
      setAllergies(algData || []);
      setOverview(ovData);
      setConversations(convData || []);
      setInvoices(invData || []);
    } catch (err) {
      setError(err.message || "Failed to load clinical records.");
    } finally {
      setLoading(false);
    }
  }

  // Retrieves full multi-turn dialogue transcript and clinical findings for an AI consultation session.
  async function fetchConversationTranscript(convId) {
    if (!convId) return;
    setLoadingConversation(true);
    try {
      const data = await apiRequest(`/assistant/assessments/${convId}`, token);
      setSelectedConversation(data);
    } catch (err) {
      alert(`Could not load conversation: ${err.message}`);
    } finally {
      setLoadingConversation(false);
    }
  }

  // Streams authenticated binary PDF reports, invoices, or prescriptions directly to client device.
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

  // Retrieves bilingual patient aftercare guidance synthesized from finalized clinician encounter notes.
  async function fetchCareGuide(apptId, lang) {
    if (!apptId) return;
    setLoadingGuide(true);
    setGuideError("");
    setCareGuide(null);
    try {
      const g = await apiRequest(`/records/encounters/${apptId}/patient-guide?lang=${lang}`, token);
      setCareGuide(g);
    } catch (err) {
      setGuideError(err.message || "Failed to load patient guide. Ensure note is finalized by attending clinician.");
    } finally {
      setLoadingGuide(false);
    }
  }

  // Validates file size and MIME format for clinical document uploads before staging in state.
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

  // Uploads diagnostic lab report or medical document binary to backend with metadata tags.
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

  // Exports patient's complete longitudinal record as an HL7 FHIR R4 standard JSON collection bundle.
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
    const matchesType = filterType === "all" || ev.event_type === filterType;
    const q = timelineSearch.trim().toLowerCase();
    const matchesSearch =
      !q ||
      (ev.title && ev.title.toLowerCase().includes(q)) ||
      (ev.description && ev.description.toLowerCase().includes(q)) ||
      (ev.actor_name && ev.actor_name.toLowerCase().includes(q)) ||
      (ev.category && ev.category.toLowerCase().includes(q));
    return matchesType && matchesSearch;
  });

  const filteredReports = reports.filter((rep) => {
    const matchesFilter = reportFilter === "all" || rep.urgency_level?.toLowerCase() === reportFilter.toLowerCase();
    const q = reportSearch.trim().toLowerCase();
    const matchesSearch =
      !q ||
      (rep.title && rep.title.toLowerCase().includes(q)) ||
      (rep.symptom_summary && rep.symptom_summary.toLowerCase().includes(q)) ||
      (rep.triage_level && rep.triage_level.toLowerCase().includes(q));
    return matchesFilter && matchesSearch;
  });

  const filteredConversations = conversations.filter((c) => {
    const q = convSearch.trim().toLowerCase();
    return (
      !q ||
      (c.title && c.title.toLowerCase().includes(q)) ||
      (c.category && c.category.toLowerCase().includes(q)) ||
      (c.urgency_level && c.urgency_level.toLowerCase().includes(q))
    );
  });

  const filteredPrescriptions = prescriptions.filter((rx) => {
    const isDraft = rx.status === "draft" || rx.is_ai_draft;
    const matchesFilter =
      rxFilter === "all" ||
      (rxFilter === "finalized" && !isDraft) ||
      (rxFilter === "draft" && isDraft);
    const q = rxSearch.trim().toLowerCase();
    const matchesSearch =
      !q ||
      (rx.prescription_number && rx.prescription_number.toLowerCase().includes(q)) ||
      (rx.diagnosis && rx.diagnosis.toLowerCase().includes(q)) ||
      (rx.doctor_name && rx.doctor_name.toLowerCase().includes(q)) ||
      rx.items?.some((it) => it.medication_name?.toLowerCase().includes(q));
    return matchesFilter && matchesSearch;
  });

  const finalizedRxCount = prescriptions.filter((rx) => !(rx.status === "draft" || rx.is_ai_draft)).length;
  const draftRxCount = prescriptions.filter((rx) => rx.status === "draft" || rx.is_ai_draft).length;

  const filteredNotes = notes.filter((n) => {
    const isDraft = n.status === "draft" || n.is_ai_draft;
    const matchesFilter =
      noteFilter === "all" ||
      (noteFilter === "finalized" && !isDraft) ||
      (noteFilter === "draft" && isDraft);
    const q = noteSearch.trim().toLowerCase();
    const matchesSearch =
      !q ||
      (n.chief_complaint && n.chief_complaint.toLowerCase().includes(q)) ||
      (n.assessment && n.assessment.toLowerCase().includes(q)) ||
      (n.plan && n.plan.toLowerCase().includes(q)) ||
      (n.doctor_name && n.doctor_name.toLowerCase().includes(q));
    return matchesFilter && matchesSearch;
  });

  const filteredDocs = documents.filter((d) => {
    const matchesFilter = docCategoryFilter === "all" || d.document_type === docCategoryFilter;
    const q = docSearch.trim().toLowerCase();
    const matchesSearch =
      !q ||
      (d.title && d.title.toLowerCase().includes(q)) ||
      (d.notes && d.notes.toLowerCase().includes(q)) ||
      (d.document_type && d.document_type.toLowerCase().includes(q));
    return matchesFilter && matchesSearch;
  });

  const filteredInvoices = invoices.filter((inv) => {
    const matchesFilter = billingFilter === "all" || inv.status === billingFilter;
    const q = billingSearch.trim().toLowerCase();
    const matchesSearch =
      !q ||
      (inv.invoice_number && inv.invoice_number.toLowerCase().includes(q)) ||
      (inv.description && inv.description.toLowerCase().includes(q));
    return matchesFilter && matchesSearch;
  });

  const TABS = [
    { id: "timeline", label: isHindi ? "कालक्रम" : "Health Timeline", icon: "⏱", count: timeline.length },
    { id: "reports", label: isHindi ? "AI आकलन रिपोर्ट" : "AI Reports", icon: "📑", count: reports.length },
    { id: "conversations", label: isHindi ? "AI परामर्श" : "AI Conversations", icon: "💬", count: conversations.length },
    { id: "prescriptions", label: isHindi ? "डॉक्टर के पर्चे (Rx)" : "Prescriptions", icon: "℞", count: prescriptions.length },
    { id: "notes", label: isHindi ? "क्लिनिकल नोट्स" : "Doctor Notes", icon: "🩺", count: notes.length },
    { id: "documents", label: isHindi ? "दस्तावेज़ व लैब रिपोर्ट" : "Lab & Diagnostic Reports", icon: "🔬", count: documents.length },
    { id: "vitals", label: isHindi ? "वाइटल्स व प्रोटोकॉल" : "Vitals & Protocols", icon: "❤️", count: overview?.recent_vitals?.length || 0 },
    { id: "allergies", label: isHindi ? "रोग व एलर्जी" : "Conditions & Allergies", icon: "⚠️", count: allergies.length },
    { id: "billing", label: isHindi ? "बिलिंग व रसीदें" : "Invoices & Receipts", icon: "💳", count: invoices.length },
    { id: "guides", label: isHindi ? "मरीज केयर गाइड" : "Care Guides (EN/HI)", icon: "📖", count: notes.length },
    { id: "careteam", label: isHindi ? "देखभाल टीम" : "Care Team", icon: "👨‍⚕️" },
    { id: "privacy", label: isHindi ? "DPDP गोपनीयता" : "DPDP Privacy", icon: "🔒" },
  ];

  // Evaluates tablist scroll position and updates left/right overflow shadow indicators.
  const checkScrollOverflow = useCallback(() => {
    const el = tablistRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    setCanScrollLeft(scrollLeft > 4);
    setCanScrollRight(scrollLeft + clientWidth < scrollWidth - 4);
  }, []);

  // Smoothly scrolls tab bar left or right when navigation chevron buttons are clicked.
  function scrollTabs(direction) {
    if (!tablistRef.current) return;
    const delta = direction === "left" ? -240 : 240;
    tablistRef.current.scrollBy({ left: delta, behavior: "smooth" });
  }

  // Smoothly centers active tab in view and refreshes overflow indicators whenever active tab changes.
  useEffect(() => {
    const activeEl = tabRefs.current[activeTab];
    if (activeEl && tablistRef.current) {
      activeEl.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
        inline: "center",
      });
    }
    checkScrollOverflow();
  }, [activeTab, checkScrollOverflow]);

  // Registers scroll and window resize listeners to maintain scroll shadow states dynamically.
  useEffect(() => {
    const el = tablistRef.current;
    if (!el) return;
    checkScrollOverflow();

    const handleScroll = () => checkScrollOverflow();
    el.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleScroll, { passive: true });

    return () => {
      el.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleScroll);
    };
  }, [checkScrollOverflow, timeline.length, reports.length, prescriptions.length, notes.length, documents.length, invoices.length]);

  // Handles ArrowLeft/Right, Home, and End keyboard navigation across tabs according to WAI-ARIA authoring practices.
  function handleTabKeyDown(e, tabId, index) {
    const tabCount = TABS.length;
    let nextIndex = -1;
    if (e.key === "ArrowRight") {
      nextIndex = (index + 1) % tabCount;
    } else if (e.key === "ArrowLeft") {
      nextIndex = (index - 1 + tabCount) % tabCount;
    } else if (e.key === "Home") {
      nextIndex = 0;
    } else if (e.key === "End") {
      nextIndex = tabCount - 1;
    }

    if (nextIndex >= 0) {
      e.preventDefault();
      const nextTab = TABS[nextIndex];
      setActiveTab(nextTab.id);
      const nextEl = tabRefs.current[nextTab.id];
      if (nextEl) nextEl.focus();
    }
  }

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
        <div className="health-records-header-actions">
          <button
            type="button"
            className="cv-btn cv-btn-secondary"
            onClick={exportFHIRBundle}
            title="Export standard HL7 FHIR R4 JSON Bundle"
          >
            <span aria-hidden="true">📥</span>
            <span>{isHindi ? "FHIR R4 निर्यात" : "Export FHIR R4"}</span>
          </button>
        </div>
      </div>

      {error && <div className="cv-alert cv-alert-danger" style={{ marginBottom: "20px" }}>{error}</div>}

      {/* Allergies Notice Banner */}
      {allergies.length > 0 && (
        <div className="cv-alert cv-alert-warning health-records-allergy-alert" style={{ marginBottom: "24px" }}>
          <span style={{ fontSize: "20px" }} aria-hidden="true">⚠️</span>
          <div style={{ flex: 1 }}>
            <strong style={{ fontSize: "14px" }}>
              {isHindi ? "सत्यापित मरीज एलर्जी व प्रतिकूल प्रतिक्रियाएं:" : "Recorded Patient Allergies & Adverse Reactions:"}
            </strong>
            <div style={{ marginTop: "8px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {allergies.map((al) => (
                <span key={al.id} className="health-records-allergy-badge">
                  <span aria-hidden="true">⛔</span>
                  <span>{al.allergen_or_condition} ({al.severity})</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Mobile Quick-Picker Dropdown for Instant 1-Tap Navigation */}
      <div className="health-records-mobile-picker" aria-label={isHindi ? "त्वरित टैब चयन" : "Quick section navigation"}>
        <label htmlFor="mobile-tab-select" className="health-records-mobile-picker-label">
          <span>{isHindi ? "वर्तमान अनुभाग:" : "Active Section:"}</span>
        </label>
        <div className="health-records-mobile-select-wrapper">
          <select
            id="mobile-tab-select"
            className="cv-select health-records-mobile-select"
            value={activeTab}
            onChange={(e) => setActiveTab(e.target.value)}
          >
            {TABS.map((t) => (
              <option key={t.id} value={t.id}>
                {t.icon} {t.label} {t.count !== undefined ? `(${t.count})` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Horizontally Scrollable Responsive Tab Strip with Overflow Indicators & Chevrons */}
      <div
        className={`health-records-tabs-wrapper ${canScrollLeft ? "has-scroll-left" : ""} ${canScrollRight ? "has-scroll-right" : ""}`}
      >
        {canScrollLeft && (
          <button
            type="button"
            className="health-records-scroll-btn left"
            aria-label={isHindi ? "बाईं ओर स्क्रॉल करें" : "Scroll tabs left"}
            onClick={() => scrollTabs("left")}
          >
            ‹
          </button>
        )}

        <div
          ref={tablistRef}
          className="health-records-tabs"
          role="tablist"
          aria-label={isHindi ? "स्वास्थ्य रिकॉर्ड अनुभाग" : "Patient health records sections"}
        >
          {TABS.map((tab, idx) => (
            <button
              key={tab.id}
              ref={(el) => { tabRefs.current[tab.id] = el; }}
              role="tab"
              id={`tab-${tab.id}`}
              aria-controls={`tabpanel-${tab.id}`}
              aria-selected={activeTab === tab.id}
              tabIndex={activeTab === tab.id ? 0 : -1}
              className={`health-records-tab ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(e) => handleTabKeyDown(e, tab.id, idx)}
            >
              <span aria-hidden="true">{tab.icon}</span>
              <span>{tab.label}</span>
              {tab.count !== undefined && (
                <span className="health-records-tab-count" aria-label={`${tab.count} records`}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {canScrollRight && (
          <button
            type="button"
            className="health-records-scroll-btn right"
            aria-label={isHindi ? "दायीं ओर स्क्रॉल करें" : "Scroll tabs right"}
            onClick={() => scrollTabs("right")}
          >
            ›
          </button>
        )}
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
                <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap", flex: 1 }}>
                  <input
                    className="cv-input"
                    style={{ maxWidth: "260px", padding: "6px 12px", fontSize: "13px" }}
                    type="text"
                    placeholder={isHindi ? "इवेंट्स खोजें…" : "Search timeline events…"}
                    value={timelineSearch}
                    onChange={(e) => setTimelineSearch(e.target.value)}
                  />
                  <div style={{ fontSize: "13px", color: "var(--cv-text-muted)", fontWeight: "600" }}>
                    {filteredEvents.length === timeline.length
                      ? (isHindi ? `कुल ${timeline.length} प्रविष्टियां` : `Showing all ${timeline.length} chronological events`)
                      : (isHindi ? `${timeline.length} में से ${filteredEvents.length} प्रविष्टियां` : `Showing ${filteredEvents.length} of ${timeline.length} chronological events`)}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {(() => {
                    const counts = {
                      all: timeline.length,
                      assessment: timeline.filter((e) => e.event_type === "assessment").length,
                      report: timeline.filter((e) => e.event_type === "report").length,
                      prescription: timeline.filter((e) => e.event_type === "prescription").length,
                      note: timeline.filter((e) => e.event_type === "note" || e.event_type === "clinical_note").length,
                      appointment: timeline.filter((e) => e.event_type === "appointment").length,
                      invoice: timeline.filter((e) => e.event_type === "invoice").length,
                      document: timeline.filter((e) => e.event_type === "document").length,
                    };
                    return [
                      { id: "all", label: isHindi ? "सभी" : "All" },
                      { id: "assessment", label: isHindi ? "AI आकलन" : "AI Assessments" },
                      { id: "report", label: isHindi ? "लैब रिपोर्ट" : "Lab Reports" },
                      { id: "prescription", label: isHindi ? "पर्चे" : "Prescriptions" },
                      { id: "note", label: isHindi ? "क्लिनिकल नोट्स" : "Notes" },
                      { id: "appointment", label: isHindi ? "अपॉइंटमेंट" : "Appointments" },
                      { id: "invoice", label: isHindi ? "बिलिंग" : "Billing & Invoices" },
                      { id: "document", label: isHindi ? "दस्तावेज़" : "Documents" },
                    ].map((f) => (
                      <button
                        key={f.id}
                        className={`cv-btn cv-btn-xs ${filterType === f.id ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                        onClick={() => setFilterType(f.id)}
                        style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
                      >
                        <span>{f.label}</span>
                        <span
                          style={{
                            padding: "1px 6px",
                            borderRadius: "999px",
                            fontSize: "11px",
                            fontWeight: "700",
                            background: filterType === f.id ? "var(--cv-accent)" : "var(--cv-surface-muted)",
                            color: filterType === f.id ? "#ffffff" : "var(--cv-text-muted)",
                          }}
                        >
                          {counts[f.id] || 0}
                        </span>
                      </button>
                    ));
                  })()}
                </div>
              </div>

              {timeline.length === 0 ? (
                <EmptyState
                  icon="⏱"
                  title={isHindi ? "कोई कालक्रम रिकॉर्ड नहीं मिला" : "No timeline events recorded"}
                  description={isHindi ? "आपकी स्वास्थ्य परामर्श और विज़िट यहाँ कालक्रम में दिखाई देंगी।" : "Your health assessments, visits, and clinical records will appear here chronologically."}
                />
              ) : filteredEvents.length === 0 ? (
                <div className="cv-card cv-empty-state" style={{ textAlign: "center", padding: "32px 16px" }}>
                  <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }} aria-hidden="true">🔍</span>
                  <h4 style={{ margin: "0 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "कोई मेल खाने वाला इवेंट नहीं मिला" : "No matching timeline events found"}
                  </h4>
                  <p style={{ margin: "0 0 14px", color: "var(--cv-text-muted)", fontSize: "13px" }}>
                    {isHindi
                      ? `वर्तमान खोज या फ़िल्टर के लिए कोई परिणाम नहीं मिला। फ़िल्टर रीसेट करके सभी ${timeline.length} इवेंट देखें।`
                      : `No events matched your current search or category filter. Reset filters to view all ${timeline.length} recorded events.`}
                  </p>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-secondary"
                    onClick={() => { setTimelineSearch(""); setFilterType("all"); }}
                  >
                    {isHindi ? "फ़िल्टर रीसेट करें" : "Reset filters"}
                  </button>
                </div>
              ) : (
                <div className="timeline-flow">
                  {filteredEvents.map((ev) => {
                    const badge = ev.urgency_level ? getUrgencyBadgeConfig(ev.urgency_level) : null;
                    const dotClass = ev.category === "clinician"
                      ? "clinician"
                      : ev.category === "ai"
                      ? "ai"
                      : ev.category === "billing" || ev.event_type === "invoice"
                      ? "billing"
                      : "patient";
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

                          <div style={{ marginTop: "10px", display: "flex", justifyContent: "flex-end" }}>
                            <button
                              type="button"
                              className="cv-btn cv-btn-xs cv-btn-outline"
                              onClick={() => {
                                const downloadPath = ev.event_type === "appointment"
                                  ? `/records/appointments/${ev.resource_id}/confirmation/pdf`
                                  : ev.event_type === "prescription"
                                  ? `/records/prescriptions/${ev.resource_id}/pdf`
                                  : ev.event_type === "note"
                                  ? `/records/notes/${ev.resource_id}/pdf`
                                  : ev.event_type === "report"
                                  ? `/records/reports/${ev.resource_id}/pdf`
                                  : ev.event_type === "document"
                                  ? `/records/documents/${ev.resource_id}/download`
                                  : ev.event_type === "invoice"
                                  ? `/billing/invoices/${ev.resource_id}/pdf`
                                  : null;
                                setSelectedRecordModal({
                                  title: ev.title,
                                  type: ev.event_type?.replace("_", " ").toUpperCase(),
                                  category: ev.category,
                                  date: formatDate(ev.timestamp),
                                  actor: ev.actor_name || "CareVoice Health System",
                                  urgency: ev.urgency_level || "routine",
                                  status: "VERIFIED",
                                  description: ev.description,
                                  details: [
                                    { label: "Event Type", value: ev.event_type?.replace("_", " ").toUpperCase() },
                                    { label: "Category", value: ev.category?.toUpperCase() },
                                    { label: "Urgency Level", value: ev.urgency_level || "Routine" },
                                    { label: "Recorded Timestamp", value: formatDate(ev.timestamp) },
                                    { label: "Care Provider / Facility", value: ev.actor_name || "CareVoice Clinical Network" },
                                  ],
                                  downloadPath,
                                  downloadFilename: `${ev.event_type}-${ev.resource_id || ev.id}.pdf`,
                                  downloadKey: `tl-${ev.id}`,
                                });
                              }}
                            >
                              <span>👁️</span>
                              <span>{isHindi ? "विवरण देखें" : "View Details"}</span>
                            </button>
                          </div>
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
            <div
              role="tabpanel"
              id="tabpanel-reports"
              aria-labelledby="tab-reports"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — NOT A REAL PATIENT ASSESSMENT
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {filteredReports.length === reports.length
                    ? (isHindi ? `कुल ${reports.length} रिपोर्ट` : `${reports.length} structured clinical assessments`)
                    : (isHindi ? `${reports.length} में से ${filteredReports.length} रिपोर्ट` : `Showing ${filteredReports.length} of ${reports.length} reports`)}
                </span>
              </div>

              {/* Search & Urgency Filters */}
              <div className="health-records-toolbar">
                <input
                  className="cv-input health-records-search-input"
                  type="text"
                  placeholder={isHindi ? "रिपोर्ट खोजें…" : "Search AI reports…"}
                  value={reportSearch}
                  onChange={(e) => setReportSearch(e.target.value)}
                />
                <div className="health-records-filter-strip" role="group" aria-label={isHindi ? "आपातकालीन स्तर फ़िल्टर" : "Urgency level filters"}>
                  {[
                    { id: "all", label: isHindi ? "सभी" : "All" },
                    { id: "routine", label: isHindi ? "रूटीन" : "Routine" },
                    { id: "urgent", label: isHindi ? "तत्काल" : "Urgent" },
                    { id: "emergency", label: isHindi ? "आपातकाल" : "Emergency" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`cv-btn cv-btn-xs ${reportFilter === f.id ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                      onClick={() => setReportFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {reports.length === 0 ? (
                <EmptyState
                  icon="📑"
                  title={isHindi ? "कोई AI रिपोर्ट दर्ज नहीं है" : "No AI assessments recorded"}
                  description={isHindi ? "सहानुभूतिपूर्ण लक्षण जाँच के बाद तैयार की गई आकलन रिपोर्ट यहाँ दिखाई देंगी।" : "Evaluations generated by the CareVoice AI assistant will appear here."}
                />
              ) : filteredReports.length === 0 ? (
                <div className="cv-card cv-empty-state" style={{ textAlign: "center", padding: "32px 16px" }}>
                  <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }} aria-hidden="true">🔍</span>
                  <h4 style={{ margin: "0 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "कोई मेल खाने वाली AI रिपोर्ट नहीं मिली" : "No matching AI reports found"}
                  </h4>
                  <p style={{ margin: "0 0 14px", color: "var(--cv-text-muted)", fontSize: "13px" }}>
                    {isHindi
                      ? `वर्तमान खोज या फ़िल्टर के लिए कोई रिपोर्ट नहीं मिली। फ़िल्टर रीसेट करके सभी ${reports.length} रिपोर्ट देखें।`
                      : `No reports matched your current search filters. Reset filters to view all ${reports.length} assessments.`}
                  </p>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-secondary"
                    onClick={() => { setReportSearch(""); setReportFilter("all"); }}
                  >
                    {isHindi ? "फ़िल्टर रीसेट करें" : "Reset filters"}
                  </button>
                </div>
              ) : (
                <div className="health-records-cards-grid">
                  {filteredReports.map((rep) => {
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
                          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="cv-btn cv-btn-sm cv-btn-ghost"
                              onClick={() =>
                                setSelectedRecordModal({
                                  title: rep.title,
                                  type: "AI Clinical Assessment Report",
                                  category: "Clinical Assessment",
                                  date: formatDate(rep.created_at),
                                  actor: rep.reviewed_at ? "Dr. Asha Demo, MD (Attending Clinician)" : "CareVoice AI Triage Engine",
                                  urgency: rep.urgency_level || "routine",
                                  status: rep.reviewed_at ? "CLINICIAN VERIFIED" : "AI DRAFT",
                                  description: rep.summary,
                                  findings: rep.findings,
                                  redFlags: rep.red_flags,
                                  instructions: rep.recommended_next_steps,
                                  evidence: rep.evidence_sources,
                                  disclaimer: rep.disclaimer,
                                  details: [
                                    { label: "Reference ID", value: `REP-${rep.report_id.slice(0, 8).toUpperCase()}` },
                                    { label: "Clinical Urgency", value: rep.urgency_level?.toUpperCase() },
                                    { label: "Review Status", value: rep.reviewed_at ? "Reviewed & Signed by Attending" : "AI Synthesized Draft" },
                                    { label: "Key Findings", value: rep.findings?.map((f) => f.finding || f.title || f).join("; ") || "None documented" },
                                    { label: "Red Flags", value: rep.red_flags?.join("; ") || "No acute red flags detected" },
                                    { label: "Next Steps", value: rep.recommended_next_steps?.join("; ") || "Standard follow-up" },
                                    { label: "Clinical Disclaimer", value: rep.disclaimer || "AI-generated clinical summary; requires licensed doctor confirmation." },
                                  ],
                                  downloadPath: `/records/reports/${rep.report_id}/pdf`,
                                  downloadFilename: `report-${rep.report_id.slice(0, 8)}.pdf`,
                                  downloadKey: `rep-${rep.report_id}`,
                                })
                              }
                            >
                              <span>👁️</span>
                              <span>{isHindi ? "विवरण देखें" : "View Details"}</span>
                            </button>
                            <button
                              className="cv-btn cv-btn-sm cv-btn-outline cv-btn-download"
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
              TAB 3: AI CONVERSATIONS & CONSULTATION TRANSCRIPTS
              ========================================================================= */}
          {activeTab === "conversations" && (
            <div
              role="tabpanel"
              id="tabpanel-conversations"
              aria-labelledby="tab-conversations"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — MULTI-TURN AI CONSULTATION TRANSCRIPTS
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {isHindi ? `कुल ${conversations.length} परामर्श संवाद` : `${conversations.length} interactive consultation transcripts`}
                </span>
              </div>

              {/* Search Bar */}
              <div className="health-records-toolbar">
                <input
                  className="cv-input health-records-search-input"
                  type="text"
                  placeholder={isHindi ? "परामर्श संवाद खोजें…" : "Search consultation transcripts…"}
                  value={convSearch}
                  onChange={(e) => setConvSearch(e.target.value)}
                />
                <div style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {isHindi ? "संवाद पढ़ने और क्लिनिकल साक्ष्य देखने के लिए 'संवाद देखें' पर क्लिक करें" : "Click 'View Transcript' to inspect turns and citations"}
                </div>
              </div>

              {conversations.length === 0 ? (
                <EmptyState
                  icon="💬"
                  title={isHindi ? "कोई परामर्श बातचीत दर्ज नहीं है" : "No AI conversations recorded"}
                  description={isHindi ? "वॉयस या चैट सहायक के साथ परामर्श यहाँ सहेजे जाते हैं।" : "Your interactive symptom evaluations with the CareVoice AI assistant will appear here."}
                />
              ) : filteredConversations.length === 0 ? (
                <div className="cv-card cv-empty-state" style={{ textAlign: "center", padding: "32px 16px" }}>
                  <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }} aria-hidden="true">🔍</span>
                  <h4 style={{ margin: "0 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "कोई मेल खाने वाला संवाद नहीं मिला" : "No matching conversations found"}
                  </h4>
                  <p style={{ margin: "0 0 14px", color: "var(--cv-text-muted)", fontSize: "13px" }}>
                    {isHindi
                      ? `"${convSearch}" के लिए कोई संवाद नहीं मिला। खोज साफ़ करके सभी ${conversations.length} संवाद देखें।`
                      : `No conversations matched "${convSearch}". Clear search to view all ${conversations.length} transcripts.`}
                  </p>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-secondary"
                    onClick={() => setConvSearch("")}
                  >
                    {isHindi ? "खोज साफ़ करें" : "Clear search"}
                  </button>
                </div>
              ) : (
                <div style={{ display: "grid", gap: "14px" }}>
                  {filteredConversations.map((conv) => {
                    const badge = getUrgencyBadgeConfig(conv.urgency_level || "routine");
                    return (
                      <div key={conv.id || conv.assessment_id} className="record-card">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "10px" }}>
                          <div style={{ flex: 1, minWidth: "260px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "6px" }}>
                              <span className={`cv-badge ${badge.className}`}>
                                {badge.label}
                              </span>
                              <span className="cv-badge cv-badge-neutral" style={{ textTransform: "capitalize" }}>
                                {conv.category || "General Triage"}
                              </span>
                              <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                                {formatDate(conv.created_at)}
                              </span>
                              <span style={{ fontSize: "12px", color: "var(--cv-border-control)" }}>•</span>
                              <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                                {conv.message_count ? `${conv.message_count} Turns` : "Multi-turn"}
                              </span>
                            </div>
                            <h3 style={{ margin: "4px 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                              {conv.title}
                            </h3>
                            <div style={{ fontSize: "13px", color: "var(--cv-text-secondary)", lineHeight: "1.5" }}>
                              Interactive patient-clinician triage session evaluating symptoms, timeline, red flags, and evidence-based guidance.
                            </div>
                          </div>
                          <button
                            type="button"
                            className="cv-btn cv-btn-sm cv-btn-primary"
                            disabled={loadingConversation}
                            onClick={() => fetchConversationTranscript(conv.assessment_id || conv.id)}
                          >
                            <span>💬</span>
                            <span>{isHindi ? "संवाद देखें" : "View Transcript"}</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 4: PRESCRIPTIONS
              ========================================================================= */}
          {activeTab === "prescriptions" && (
            <div
              role="tabpanel"
              id="tabpanel-prescriptions"
              aria-labelledby="tab-prescriptions"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — DOCTOR-SIGNED DIGITAL PRESCRIPTIONS
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {filteredPrescriptions.length === prescriptions.length
                    ? (isHindi ? `कुल ${prescriptions.length} पर्चे` : `${prescriptions.length} prescriptions on file`)
                    : (isHindi ? `${prescriptions.length} में से ${filteredPrescriptions.length} पर्चे` : `Showing ${filteredPrescriptions.length} of ${prescriptions.length} prescriptions`)}
                </span>
              </div>

              {/* Prescriptions Filter Bar */}
              <div className="health-records-toolbar">
                <input
                  className="cv-input health-records-search-input"
                  type="text"
                  placeholder={isHindi ? "पर्चे खोजें…" : "Search prescriptions…"}
                  value={rxSearch}
                  onChange={(e) => setRxSearch(e.target.value)}
                />
                <div className="health-records-filter-strip" role="group" aria-label={isHindi ? "पर्चे फ़िल्टर" : "Prescription status filters"}>
                  {[
                    { id: "all", label: isHindi ? "सभी" : "All", count: prescriptions.length },
                    { id: "finalized", label: isHindi ? "डॉक्टर हस्ताक्षरित" : "Doctor Signed", count: finalizedRxCount },
                    { id: "draft", label: isHindi ? "AI ड्राफ्ट" : "AI Drafts", count: draftRxCount },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`cv-btn cv-btn-xs ${rxFilter === f.id ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                      onClick={() => setRxFilter(f.id)}
                      style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}
                    >
                      <span>{f.label}</span>
                      <span className="cv-filter-count-badge">{f.count}</span>
                    </button>
                  ))}
                </div>
              </div>

              {prescriptions.length === 0 ? (
                <EmptyState
                  icon="℞"
                  title={isHindi ? "कोई पर्चा दर्ज नहीं है" : "No prescriptions on file"}
                  description={isHindi ? "डॉक्टर द्वारा हस्ताक्षरित पर्चे यहाँ दिखाई देंगे।" : "Doctor-signed prescriptions and medication plans will appear here."}
                />
              ) : filteredPrescriptions.length === 0 ? (
                <div className="cv-card cv-empty-state" style={{ textAlign: "center", padding: "32px 16px" }}>
                  <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }} aria-hidden="true">🔍</span>
                  <h4 style={{ margin: "0 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "कोई मेल खाने वाला पर्चा नहीं मिला" : "No matching prescriptions found"}
                  </h4>
                  <p style={{ margin: "0 0 14px", color: "var(--cv-text-muted)", fontSize: "13px" }}>
                    {isHindi
                      ? `वर्तमान खोज या फ़िल्टर के लिए कोई पर्चा नहीं मिला। फ़िल्टर रीसेट करके सभी ${prescriptions.length} पर्चे देखें।`
                      : `No prescriptions matched your filters. Reset filters to view all ${prescriptions.length} prescriptions.`}
                  </p>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-secondary"
                    onClick={() => { setRxSearch(""); setRxFilter("all"); }}
                  >
                    {isHindi ? "फ़िल्टर रीसेट करें" : "Reset filters"}
                  </button>
                </div>
              ) : (
                <div className="health-records-cards-grid">
                  {filteredPrescriptions.map((rx) => {
                    const isDownloading = downloadingId === `rx-${rx.id}`;
                    const isDraft = rx.status === "draft" || rx.is_ai_draft;
                    return (
                      <div key={rx.id} className={`record-card record-card-rx ${isDraft ? "is-draft" : ""}`}>
                        <div className="record-card-rx-header">
                          <div className="record-card-rx-title-group">
                            <span className="rx-symbol" aria-hidden="true">℞</span>
                            <h3 className="record-card-rx-title">{rx.prescription_number}</h3>
                            <span className={`cv-badge ${isDraft ? "cv-badge-draft-pill" : "cv-badge-signed-pill"}`}>
                              {isDraft
                                ? (isHindi ? "⚡ AI ड्राफ्ट • अहस्ताक्षरित" : "⚡ AI DRAFT • UNSIGNED")
                                : (isHindi ? "✓ डॉक्टर हस्ताक्षरित" : "✓ DOCTOR SIGNED")}
                            </span>
                          </div>
                          <div className="record-card-rx-meta">
                            {isDraft ? (
                              <span>
                                {isHindi
                                  ? `CareVoice AI क्लिनिकल स्क्राइब • जनरेट किया गया: ${formatDate(rx.created_at)} • समीक्षा लंबित`
                                  : `CareVoice AI Clinical Scribe • Generated on ${formatDate(rx.created_at)} • Pending Clinician Review`}
                              </span>
                            ) : (
                              <span>
                                {isHindi
                                  ? `अधिकृत चिकित्सक Dr. ${rx.doctor_name || "Asha Demo"} द्वारा हस्ताक्षरित • ${formatDate(rx.finalized_at || rx.created_at)}`
                                  : `Prescribed & signed by Dr. ${rx.doctor_name || "Asha Demo"} on ${formatDate(rx.finalized_at || rx.created_at)}`}
                              </span>
                            )}
                          </div>
                        </div>

                        <div className="record-card-rx-body">
                          {isDraft && (
                            <div className="cv-alert cv-alert-warning cv-rx-alert">
                              <span aria-hidden="true" style={{ fontSize: "16px" }}>⚠️</span>
                              <div>
                                <strong>{isHindi ? "AI जनरेटेड ड्राफ्ट पर्चा:" : "AI-Generated Prescription Draft:"} </strong>
                                {isHindi
                                  ? "यह पर्चा CareVoice AI द्वारा तैयार किया गया ड्राफ्ट है। अधिकृत चिकित्सक द्वारा समीक्षा और ई-हस्ताक्षर के बाद ही यह मान्य होगा।"
                                  : "This draft was synthesized by the clinical voice assistant and is pending licensed clinician review, verification, and digital electronic signature before dispensing."}
                              </div>
                            </div>
                          )}

                          {rx.diagnosis && (
                            <div className="rx-diagnosis-row">
                              <span className="rx-diagnosis-label">{isHindi ? "निदान (Diagnosis):" : "Clinical Diagnosis:"}</span>
                              <span className="rx-diagnosis-value">{rx.diagnosis}</span>
                            </div>
                          )}

                          {rx.allergy_warnings?.length > 0 && (
                            <div className="cv-alert cv-alert-warning cv-rx-alert">
                              <span aria-hidden="true" style={{ fontSize: "16px" }}>⚠️</span>
                              <div>
                                <strong>{isHindi ? "एलर्जी सुरक्षा जांच:" : "Allergy Safety Verification:"} </strong>
                                {rx.allergy_warnings.join("; ")}
                              </div>
                            </div>
                          )}

                          {/* Medication Schedule Table */}
                          <div className="rx-medication-wrapper">
                            <table className="rx-medication-table">
                              <thead>
                                <tr>
                                  <th style={{ width: "32%" }}>{isHindi ? "दवा व क्षमता" : "Medicine & Strength"}</th>
                                  <th style={{ width: "20%" }}>{isHindi ? "प्रकार" : "Form & Route"}</th>
                                  <th style={{ width: "18%" }}>{isHindi ? "खुराक" : "Frequency"}</th>
                                  <th style={{ width: "12%" }}>{isHindi ? "अवधि" : "Duration"}</th>
                                  <th style={{ width: "18%" }}>{isHindi ? "निर्देश" : "Instructions"}</th>
                                </tr>
                              </thead>
                              <tbody>
                                {rx.items?.map((it) => (
                                  <tr key={it.id}>
                                    <td>
                                      <div className="rx-med-name">{it.medication_name}</div>
                                      {it.strength && <div className="rx-med-strength">{it.strength}</div>}
                                    </td>
                                    <td>
                                      <span>{it.dosage_form || "Tablet"}</span>
                                      {it.route && <span style={{ color: "var(--cv-text-muted)" }}> • {it.route}</span>}
                                    </td>
                                    <td>
                                      <span className="cv-badge cv-badge-routine">{it.frequency}</span>
                                    </td>
                                    <td>
                                      <span style={{ fontWeight: "600" }}>{it.duration}</span>
                                    </td>
                                    <td>
                                      <span className="rx-med-instructions">{it.instructions || "As directed"}</span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>

                          {rx.notes && (
                            <div className="rx-advice-box">
                              <div className="rx-advice-title">
                                <span aria-hidden="true">💡</span>
                                <span>{isHindi ? "चिकित्सक की सलाह व सावधानियां:" : "Doctor's Advice & Precautions:"}</span>
                              </div>
                              <div>{rx.notes}</div>
                            </div>
                          )}
                        </div>

                        <div className="record-card-rx-footer">
                          <div className="rx-security-tag">
                            {isDraft ? (
                              <span className="rx-draft-indicator">
                                <span aria-hidden="true">⏳</span>
                                <span>{isHindi ? "समीक्षा लंबित (ड्राफ्ट)" : "Unsigned Draft — Needs Clinician Review"}</span>
                              </span>
                            ) : (
                              <span className="rx-signed-indicator">
                                <span aria-hidden="true">🔏</span>
                                <span>{isHindi ? "ई-हस्ताक्षरित व सत्यापित" : "Digitally Signed & Verified"}</span>
                              </span>
                            )}
                          </div>
                          <div className="record-card-rx-actions">
                            <button
                              type="button"
                              className="cv-btn cv-btn-sm cv-btn-ghost"
                              onClick={() =>
                                setSelectedRecordModal({
                                  title: `Prescription ${rx.prescription_number}`,
                                  type: isDraft ? "AI Draft Prescription (Unfinalized)" : "Clinician Signed Digital Rx",
                                  category: "Pharmacotherapy",
                                  date: formatDate(rx.finalized_at || rx.created_at),
                                  actor: isDraft ? "CareVoice AI Clinical Scribe" : `Dr. ${rx.doctor_name || "Attending Physician"}`,
                                  urgency: "routine",
                                  status: isDraft ? "AI DRAFT (UNSIGNED)" : "FINALIZED & SIGNED",
                                  description: rx.diagnosis ? `Clinical Diagnosis: ${rx.diagnosis}` : "Outpatient Prescription Order",
                                  diagnosis: rx.diagnosis,
                                  treatment: rx.items,
                                  warnings: rx.allergy_warnings,
                                  instructions: rx.notes || "Take strictly as prescribed. Complete full course of treatment.",
                                  details: [
                                    { label: "Prescription Number", value: rx.prescription_number },
                                    { label: "Clinical Status", value: isDraft ? "AI DRAFT (UNSIGNED - PENDING CLINICIAN REVIEW)" : "FINALIZED & DIGITALLY SIGNED" },
                                    { label: "Attending Clinician", value: isDraft ? "Pending Review" : `Dr. ${rx.doctor_name || "Asha Demo"}` },
                                    { label: "Diagnosis", value: rx.diagnosis || "Unspecified" },
                                    {
                                      label: "Medications Prescribed",
                                      value: rx.items?.map((it) => `${it.medication_name} (${it.strength || ""}) - ${it.frequency}, ${it.duration}`).join("; ") || "None",
                                    },
                                    { label: "Allergy Warnings Checked", value: rx.allergy_warnings?.join("; ") || "All allergy checks passed" },
                                    { label: "Doctor's Advice", value: rx.notes || "Follow instructions as labeled." },
                                  ],
                                  downloadPath: `/records/prescriptions/${rx.id}/pdf`,
                                  downloadFilename: `prescription-${rx.prescription_number}.pdf`,
                                  downloadKey: `rx-${rx.id}`,
                                })
                              }
                            >
                              <span aria-hidden="true">👁️</span>
                              <span>{isHindi ? "विवरण देखें" : "View Details"}</span>
                            </button>
                            <button
                              type="button"
                              className="cv-btn cv-btn-sm cv-btn-primary cv-btn-download"
                              disabled={isDownloading}
                              onClick={() =>
                                downloadBinary(
                                  `/records/prescriptions/${rx.id}/pdf`,
                                  `prescription-${rx.prescription_number}.pdf`,
                                  `rx-${rx.id}`
                                )
                              }
                            >
                              <span aria-hidden="true">📥</span>
                              <span>{isDownloading ? (isHindi ? "डाउनलोड हो रहा है…" : "Downloading…") : (isHindi ? "पर्चा डाउनलोड (PDF)" : "Download Rx PDF")}</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 5: CLINICAL NOTES
              ========================================================================= */}
          {activeTab === "notes" && (
            <div
              role="tabpanel"
              id="tabpanel-notes"
              aria-labelledby="tab-notes"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — CLINICIAN CONSULTATION ENCOUNTER NOTES
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {filteredNotes.length === notes.length
                    ? (isHindi ? `कुल ${notes.length} नोट्स` : `${notes.length} consultation notes on file`)
                    : (isHindi ? `${notes.length} में से ${filteredNotes.length} नोट्स` : `Showing ${filteredNotes.length} of ${notes.length} notes`)}
                </span>
              </div>

              {/* Doctor Notes Filter Bar */}
              <div className="health-records-toolbar">
                <input
                  className="cv-input health-records-search-input"
                  type="text"
                  placeholder={isHindi ? "नोट्स खोजें…" : "Search clinical notes…"}
                  value={noteSearch}
                  onChange={(e) => setNoteSearch(e.target.value)}
                />
                <div className="health-records-filter-strip" role="group" aria-label={isHindi ? "क्लिनिकल नोट्स फ़िल्टर" : "Clinical notes filters"}>
                  {[
                    { id: "all", label: isHindi ? "सभी" : "All" },
                    { id: "finalized", label: isHindi ? "अंतिम हस्ताक्षरित" : "Finalized (Signed)" },
                    { id: "draft", label: isHindi ? "AI ड्राफ्ट" : "AI Drafts" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`cv-btn cv-btn-xs ${noteFilter === f.id ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                      onClick={() => setNoteFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {notes.length === 0 ? (
                <EmptyState
                  icon="🩺"
                  title={isHindi ? "कोई विज़िट नोट दर्ज नहीं है" : "No clinical notes on file"}
                  description={isHindi ? "डॉक्टर द्वारा हस्ताक्षरित परामर्श नोट्स यहाँ दिखाई देंगे।" : "Doctor clinical consultation and encounter notes will appear here."}
                />
              ) : filteredNotes.length === 0 ? (
                <div className="cv-card cv-empty-state" style={{ textAlign: "center", padding: "32px 16px" }}>
                  <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }} aria-hidden="true">🔍</span>
                  <h4 style={{ margin: "0 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "कोई मेल खाने वाला नोट नहीं मिला" : "No matching clinical notes found"}
                  </h4>
                  <p style={{ margin: "0 0 14px", color: "var(--cv-text-muted)", fontSize: "13px" }}>
                    {isHindi
                      ? `वर्तमान खोज या फ़िल्टर के लिए कोई नोट नहीं मिला। फ़िल्टर रीसेट करके सभी ${notes.length} नोट्स देखें।`
                      : `No notes matched your filters. Reset filters to view all ${notes.length} clinical encounter notes.`}
                  </p>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-secondary"
                    onClick={() => { setNoteSearch(""); setNoteFilter("all"); }}
                  >
                    {isHindi ? "फ़िल्टर रीसेट करें" : "Reset filters"}
                  </button>
                </div>
              ) : (
                <div className="health-records-cards-grid">
                  {filteredNotes.map((n) => {
                    const isDraft = n.status === "draft" || n.is_ai_draft;
                    return (
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
                          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                            <span className={`cv-badge ${isDraft ? "cv-badge-warning" : "cv-badge-success"}`} style={{ textTransform: "uppercase" }}>
                              {isDraft ? "AI Draft" : n.status}
                            </span>
                            <button
                              type="button"
                              className="cv-btn cv-btn-xs cv-btn-ghost"
                              onClick={() =>
                                setSelectedRecordModal({
                                  title: n.chief_complaint || "Clinical Encounter Note",
                                  type: n.note_type?.replace("_", " "),
                                  category: "Consultation Note",
                                  date: formatDate(n.finalized_at || n.created_at),
                                  actor: `Dr. ${n.doctor_name || "Clinician"}`,
                                  urgency: "routine",
                                  status: isDraft ? "AI DRAFT" : n.status?.toUpperCase(),
                                  description: n.history_of_present_illness || n.chief_complaint,
                                  findings: n.examination_findings,
                                  diagnosis: n.assessment,
                                  treatment: n.plan,
                                  instructions: n.follow_up_instructions,
                                  details: [
                                    { label: "Note Type", value: n.note_type?.replace("_", " ").toUpperCase() },
                                    { label: "Status", value: isDraft ? "AI DRAFT (Awaiting Clinician Review)" : n.status?.toUpperCase() },
                                    { label: "Chief Complaint", value: n.chief_complaint || "Routine Evaluation" },
                                    { label: "History of Present Illness", value: n.history_of_present_illness || "N/A" },
                                    { label: "Examination Findings", value: n.examination_findings || "N/A" },
                                    { label: "Assessment", value: n.assessment || "N/A" },
                                    { label: "Treatment Plan", value: n.plan || "N/A" },
                                    { label: "Follow-up Instructions", value: n.follow_up_instructions || "As needed" },
                                  ],
                                  downloadPath: `/records/notes/${n.id}/pdf`,
                                  downloadFilename: `clinical-note-${n.id}.pdf`,
                                  downloadKey: `note-${n.id}`,
                                })
                              }
                            >
                              <span>👁️</span>
                              <span>{isHindi ? "विवरण देखें" : "View"}</span>
                            </button>
                            <button
                              type="button"
                              className="cv-btn cv-btn-xs cv-btn-outline cv-btn-download"
                              disabled={downloadingId === `note-${n.id}`}
                              onClick={() =>
                                downloadBinary(
                                  `/records/notes/${n.id}/pdf`,
                                  `clinical-note-${n.id}.pdf`,
                                  `note-${n.id}`
                                )
                              }
                            >
                              <span>📥</span>
                              <span>{downloadingId === `note-${n.id}` ? "…" : "Note PDF"}</span>
                            </button>
                            <button
                              type="button"
                              className="cv-btn cv-btn-xs cv-btn-primary cv-btn-download"
                              disabled={downloadingId === `fup-${n.id}`}
                              onClick={() =>
                                downloadBinary(
                                  `/records/followup/${n.id}/pdf`,
                                  `followup-plan-${n.id}.pdf`,
                                  `fup-${n.id}`
                                )
                              }
                            >
                              <span>📥</span>
                              <span>{downloadingId === `fup-${n.id}` ? "…" : "Care Plan PDF"}</span>
                            </button>
                          </div>
                        </div>

                        {isDraft && (
                          <div className="cv-alert cv-alert-warning" style={{ marginBottom: "12px", padding: "8px 12px", fontSize: "12px" }}>
                            <span>⚠️</span>
                            <div>
                              <strong>Ambient AI Scribe Draft: </strong>
                              Draft clinical note captured by CareVoice Ambient Scribe. Must be reviewed, validated, and signed by the attending clinician before becoming part of the permanent medical record.
                            </div>
                          </div>
                        )}

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
                  );
                })}
              </div>
            )}
            </div>
          )}

          {/* =========================================================================
              TAB 6: DOCUMENTS & LAB REPORTS
              ========================================================================= */}
          {activeTab === "documents" && (
            <div
              role="tabpanel"
              id="tabpanel-documents"
              aria-labelledby="tab-documents"
              tabIndex={0}
              className="health-records-tabpanel"
            >
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
                  DEMO DATA — VERIFIED CLINICAL DIAGNOSTIC REPORTS & LAB OBSERVATIONS
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {filteredDocs.length === documents.length
                    ? (isHindi ? `कुल ${documents.length} दस्तावेज़` : `${documents.length} diagnostic reports on file`)
                    : (isHindi ? `${documents.length} में से ${filteredDocs.length} दस्तावेज़` : `Showing ${filteredDocs.length} of ${documents.length} documents`)}
                </span>
              </div>

              {/* Category Filter & Search Bar */}
              <div className="health-records-toolbar">
                <input
                  className="cv-input health-records-search-input"
                  type="text"
                  placeholder={isHindi ? "दस्तावेज़ खोजें…" : "Search documents & labs…"}
                  value={docSearch}
                  onChange={(e) => setDocSearch(e.target.value)}
                />
                <div className="health-records-filter-strip" role="group" aria-label={isHindi ? "दस्तावेज़ श्रेणी फ़िल्टर" : "Document category filters"}>
                  {[
                    { id: "all", label: isHindi ? "सभी" : "All" },
                    { id: "lab_report", label: isHindi ? "लैब रिपोर्ट" : "Lab Reports" },
                    { id: "imaging", label: isHindi ? "इमेजिंग / स्कैन" : "Imaging / Scans" },
                    { id: "discharge_summary", label: isHindi ? "डिस्चार्ज" : "Discharge" },
                    { id: "prescription", label: isHindi ? "बाहरी पर्चे" : "Prescriptions" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`cv-btn cv-btn-xs ${docCategoryFilter === f.id ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                      onClick={() => setDocCategoryFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {documents.length === 0 ? (
                <EmptyState
                  icon="📁"
                  title={isHindi ? "कोई दस्तावेज़ दर्ज नहीं है" : "No documents recorded"}
                  description={isHindi ? "अपलोड किए गए मेडिकल दस्तावेज़ और रिपोर्ट यहाँ दिखाई देंगे।" : "Uploaded medical records, laboratory tests, and imaging scans will appear here."}
                />
              ) : filteredDocs.length === 0 ? (
                <div className="cv-card cv-empty-state" style={{ textAlign: "center", padding: "32px 16px" }}>
                  <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }} aria-hidden="true">🔍</span>
                  <h4 style={{ margin: "0 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "कोई मेल खाने वाला दस्तावेज़ नहीं मिला" : "No matching documents found"}
                  </h4>
                  <p style={{ margin: "0 0 14px", color: "var(--cv-text-muted)", fontSize: "13px" }}>
                    {isHindi
                      ? `वर्तमान खोज या फ़िल्टर के लिए कोई दस्तावेज़ नहीं मिला। फ़िल्टर रीसेट करके सभी ${documents.length} दस्तावेज़ देखें।`
                      : `No documents matched your current search filters. Reset filters to view all ${documents.length} records.`}
                  </p>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-secondary"
                    onClick={() => { setDocSearch(""); setDocCategoryFilter("all"); }}
                  >
                    {isHindi ? "फ़िल्टर रीसेट करें" : "Reset filters"}
                  </button>
                </div>
              ) : (
                <div style={{ display: "grid", gap: "16px" }}>
                  {filteredDocs.map((d) => {
                    const isDownloading = downloadingId === `doc-${d.id}`;
                    const hasParams = d.extracted_data?.parameters && d.extracted_data.parameters.length > 0;
                    return (
                      <div key={d.id} className="record-card">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
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
                          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="cv-btn cv-btn-sm cv-btn-ghost"
                              onClick={() =>
                                setSelectedRecordModal({
                                  title: d.title,
                                  type: d.document_type.replace("_", " "),
                                  category: "Diagnostic Investigation",
                                  date: formatDate(d.created_at),
                                  actor: d.extracted_data?.signing_doctor || "Verified Diagnostic Laboratory Network",
                                  urgency: "routine",
                                  status: "VERIFIED",
                                  description: d.extracted_data?.interpretation || d.notes || "Diagnostic investigation panel report.",
                                  parameters: d.extracted_data?.parameters,
                                  findings: d.extracted_data?.interpretation,
                                  details: [
                                    { label: "Document Category", value: d.document_type.replace("_", " ").toUpperCase() },
                                    { label: "File Size", value: formatFileSize(d.file_size) },
                                    { label: "Uploaded At", value: formatDate(d.created_at) },
                                    { label: "Clinical Notes", value: d.notes || "No additional notes provided." },
                                    ...(hasParams
                                      ? [{
                                          label: "Measured Parameters",
                                          value: d.extracted_data.parameters.map((p) => `${p.name}: ${p.value} (${p.status})`).join("; "),
                                        }]
                                      : []),
                                    ...(d.extracted_data?.interpretation
                                      ? [{ label: "Interpretation", value: d.extracted_data.interpretation }]
                                      : []),
                                  ],
                                  downloadPath: `/records/documents/${d.id}/download`,
                                  downloadFilename: d.title.replace(/\s+/g, "_") + ".pdf",
                                  downloadKey: `doc-${d.id}`,
                                })
                              }
                            >
                              <span>👁️</span>
                              <span>{isHindi ? "विवरण देखें" : "View"}</span>
                            </button>
                            <button
                              className="cv-btn cv-btn-sm cv-btn-outline cv-btn-download"
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
                        </div>

                        {/* Structured Laboratory Observations Table */}
                        {hasParams && (
                          <div style={{ marginTop: "14px", overflowX: "auto", borderRadius: "8px", border: "1px solid var(--cv-border)" }}>
                            <table className="cv-table" style={{ width: "100%", fontSize: "12px", borderCollapse: "collapse" }}>
                              <thead style={{ background: "var(--cv-surface-soft)" }}>
                                <tr>
                                  <th style={{ padding: "8px 12px", textAlign: "left" }}>Test Parameter</th>
                                  <th style={{ padding: "8px 12px", textAlign: "left" }}>Measured Value</th>
                                  <th style={{ padding: "8px 12px", textAlign: "left" }}>Reference Range</th>
                                  <th style={{ padding: "8px 12px", textAlign: "left" }}>Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {d.extracted_data.parameters.map((param, pIdx) => {
                                  const statusClass =
                                    param.status === "ABNORMAL"
                                      ? "cv-badge-urgent"
                                      : param.status === "BORDERLINE"
                                      ? "cv-badge-warning"
                                      : "cv-badge-success";
                                  return (
                                    <tr key={pIdx} style={{ borderTop: "1px solid var(--cv-border-soft)" }}>
                                      <td style={{ padding: "8px 12px", fontWeight: "600", color: "var(--cv-text-primary)" }}>{param.name}</td>
                                      <td style={{ padding: "8px 12px", fontWeight: "700", color: param.status === "ABNORMAL" ? "#dc2626" : "var(--cv-text-primary)" }}>{param.value}</td>
                                      <td style={{ padding: "8px 12px", color: "var(--cv-text-muted)" }}>{param.reference_range}</td>
                                      <td style={{ padding: "8px 12px" }}>
                                        <span className={`cv-badge ${statusClass}`} style={{ fontSize: "10px", padding: "2px 6px" }}>
                                          {param.status}
                                        </span>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}

                        {d.extracted_data?.interpretation && (
                          <div style={{ marginTop: "10px", padding: "10px 12px", borderRadius: "8px", background: "var(--cv-surface-soft)", fontSize: "12px", color: "var(--cv-text-secondary)" }}>
                            <strong style={{ color: "var(--cv-text-primary)" }}>Pathologist / Clinician Interpretation: </strong>
                            {d.extracted_data.interpretation}
                            {d.extracted_data.signing_doctor && (
                              <span style={{ display: "block", marginTop: "4px", fontSize: "11px", color: "var(--cv-text-muted)" }}>
                                Verified &amp; Electronically Signed by: <strong>{d.extracted_data.signing_doctor}</strong>
                              </span>
                            )}
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
              TAB 7: VITALS & PROTOCOL MONITOR
              ========================================================================= */}
          {activeTab === "vitals" && (
            <div
              role="tabpanel"
              id="tabpanel-vitals"
              aria-labelledby="tab-vitals"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — PROTOCOL MONITORING & CLINICAL VITAL SIGNS
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  Clinical decision protocols active: WHO Proning, Dengue, Hypoglycemia, SNOOP, ORS
                </span>
              </div>

              {/* Vitals Summary Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px", marginBottom: "20px" }}>
                <div className="record-card" style={{ padding: "16px", textAlign: "center" }}>
                  <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase" }}>Blood Oxygen (SpO2)</div>
                  <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--cv-accent)", margin: "6px 0 2px" }}>97%</div>
                  <span className="cv-badge cv-badge-success">Normal Range</span>
                  <div style={{ fontSize: "11px", color: "var(--cv-text-muted)", marginTop: "6px" }}>Protocol alert at &lt; 94%</div>
                </div>

                <div className="record-card" style={{ padding: "16px", textAlign: "center" }}>
                  <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase" }}>Heart Rate</div>
                  <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--cv-accent)", margin: "6px 0 2px" }}>72 bpm</div>
                  <span className="cv-badge cv-badge-success">Normal Sinus</span>
                  <div style={{ fontSize: "11px", color: "var(--cv-text-muted)", marginTop: "6px" }}>Alert if &gt; 100 or &lt; 50</div>
                </div>

                <div className="record-card" style={{ padding: "16px", textAlign: "center" }}>
                  <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase" }}>Blood Pressure</div>
                  <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--cv-accent)", margin: "6px 0 2px" }}>120/80</div>
                  <span className="cv-badge cv-badge-routine">Optimal mmHg</span>
                  <div style={{ fontSize: "11px", color: "var(--cv-text-muted)", marginTop: "6px" }}>NSAID caution on elevation</div>
                </div>

                <div className="record-card" style={{ padding: "16px", textAlign: "center" }}>
                  <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase" }}>Blood Glucose</div>
                  <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--cv-accent)", margin: "6px 0 2px" }}>98 mg/dL</div>
                  <span className="cv-badge cv-badge-success">Fasting Normal</span>
                  <div style={{ fontSize: "11px", color: "var(--cv-text-muted)", marginTop: "6px" }}>Rule of 15 if &lt; 70</div>
                </div>

                <div className="record-card" style={{ padding: "16px", textAlign: "center" }}>
                  <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase" }}>Body Temp</div>
                  <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--cv-accent)", margin: "6px 0 2px" }}>98.6°F</div>
                  <span className="cv-badge cv-badge-routine">Afebrile</span>
                  <div style={{ fontSize: "11px", color: "var(--cv-text-muted)", marginTop: "6px" }}>Defervescence monitor</div>
                </div>
              </div>

              {/* Protocol Monitor Rules Matrix */}
              <div style={{ display: "grid", gap: "16px" }}>
                <div className="record-card" style={{ borderLeft: "4px solid #0284c7" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "18px" }}>🫁</span>
                      <h4 style={{ margin: 0, fontSize: "15px", color: "var(--cv-text-primary)" }}>
                        WHO Acute Respiratory Proning Protocol (SpO2 &lt; 94%)
                      </h4>
                    </div>
                    <span className="cv-badge cv-badge-info">WHO COVID-19 Clinical Guidelines</span>
                  </div>
                  <p style={{ margin: "0 0 10px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                    For awake, non-intubated patients exhibiting oxygen saturation below 94%, the protocol recommends structured cycle rotations: <strong>30 to 120 minutes in prone position</strong>, followed by right lateral decubitus, semi-Fowler's position (30-60°), and left lateral decubitus.
                  </p>
                  <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", fontSize: "12px", color: "var(--cv-text-muted)" }}>
                    <span>✓ Continuously monitor SpO2</span> • <span>✓ Seek immediate emergency care (112) if SpO2 &lt; 90%</span>
                  </div>
                </div>

                <div className="record-card" style={{ borderLeft: "4px solid #dc2626" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "18px" }}>🦟</span>
                      <h4 style={{ margin: 0, fontSize: "15px", color: "var(--cv-text-primary)" }}>
                        Dengue Critical Phase &amp; Defervescence Warning
                      </h4>
                    </div>
                    <span className="cv-badge cv-badge-urgent">Plasma Leakage Alert</span>
                  </div>
                  <p style={{ margin: "0 0 10px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                    At the time of fever drop (defervescence, days 3–7), patients enter the high-risk critical phase. A simultaneous <strong>hematocrit rise &ge; 5%</strong> and <strong>platelet count drop &ge; 50%</strong> signifies acute plasma leakage. <strong>Absolute Contraindication:</strong> Avoid all NSAIDs (ibuprofen, aspirin, naproxen, diclofenac) due to catastrophic hemorrhage risks.
                  </p>
                  <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", fontSize: "12px", color: "var(--cv-text-muted)" }}>
                    <span>✓ Paracetamol only for analgesia</span> • <span>✓ Close hematocrit monitoring</span>
                  </div>
                </div>

                <div className="record-card" style={{ borderLeft: "4px solid #f59e0b" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "18px" }}>🍬</span>
                      <h4 style={{ margin: 0, fontSize: "15px", color: "var(--cv-text-primary)" }}>
                        Hypoglycemia Management: Rule of 15 (Blood Glucose &lt; 70 mg/dL)
                      </h4>
                    </div>
                    <span className="cv-badge cv-badge-warning">Rule of 15 Protocol</span>
                  </div>
                  <p style={{ margin: "0 0 10px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                    Immediately administer <strong>15 grams of fast-acting carbohydrate</strong> (e.g., 1/2 cup fruit juice, 3–4 glucose tablets, or 4 teaspoons sugar in water). Rest for 15 minutes and re-test blood glucose. If still under 70 mg/dL, repeat the 15g cycle. If unconscious, do not give oral items; administer glucagon or seek emergency care immediately.
                  </p>
                </div>

                <div className="record-card" style={{ borderLeft: "4px solid #7c3aed" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "18px" }}>💧</span>
                      <h4 style={{ margin: 0, fontSize: "15px", color: "var(--cv-text-primary)" }}>
                        WHO Low-Osmolarity ORS Formulation (245 mOsm/L)
                      </h4>
                    </div>
                    <span className="cv-badge cv-badge-routine">WHO Standard</span>
                  </div>
                  <p style={{ margin: "0 0 10px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.6" }}>
                    Optimal rehydration solution with total osmolarity of <strong>245 mOsm/L</strong>: Sodium 75 mmol/L, Glucose 75 mmol/L, Potassium 20 mmol/L, Chloride 65 mmol/L, Citrate 10 mmol/L. Dilute exactly 1 sachet in 1 litre of clean drinking water. Avoid high-sugar carbonated drinks.
                  </p>
                </div>
              </div>

              {/* Longitudinal Vitals Observation Log */}
              {overview?.recent_vitals && overview.recent_vitals.length > 0 && (
                <div className="record-card" style={{ marginTop: "20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", flexWrap: "wrap", gap: "8px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontSize: "18px" }}>📈</span>
                      <h4 style={{ margin: 0, fontSize: "15px", color: "var(--cv-text-primary)" }}>
                        {isHindi ? "दीर्घकालिक वाइटल साइन्स इतिहास" : "Longitudinal Vitals & Clinical Observation History"}
                      </h4>
                    </div>
                    <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                      {overview.recent_vitals.length} recorded measurements
                    </span>
                  </div>

                  <div style={{ overflowX: "auto", borderRadius: "8px", border: "1px solid var(--cv-border)" }}>
                    <table className="cv-table" style={{ width: "100%", fontSize: "12px", borderCollapse: "collapse" }}>
                      <thead style={{ background: "var(--cv-surface-soft)" }}>
                        <tr>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>Recorded Date</th>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>Blood Pressure</th>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>Heart Rate</th>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>SpO2</th>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>Temperature</th>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>Glucose</th>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>Status</th>
                          <th style={{ padding: "8px 12px", textAlign: "left" }}>Clinical Context</th>
                        </tr>
                      </thead>
                      <tbody>
                        {overview.recent_vitals.map((v) => {
                          const statusClass =
                            v.status === "febrile" || v.status === "stage_1_hypertension"
                              ? "cv-badge-warning"
                              : "cv-badge-success";
                          return (
                            <tr key={v.id} style={{ borderTop: "1px solid var(--cv-border-soft)" }}>
                              <td style={{ padding: "8px 12px", whiteSpace: "nowrap", color: "var(--cv-text-muted)" }}>
                                {formatDate(v.recorded_at)}
                              </td>
                              <td style={{ padding: "8px 12px", fontWeight: "600", color: "var(--cv-text-primary)" }}>
                                {v.bp_systolic}/{v.bp_diastolic} mmHg
                              </td>
                              <td style={{ padding: "8px 12px" }}>{v.heart_rate} bpm</td>
                              <td style={{ padding: "8px 12px", fontWeight: "600", color: v.spo2 < 94 ? "#dc2626" : "var(--cv-text-primary)" }}>
                                {v.spo2}%
                              </td>
                              <td style={{ padding: "8px 12px" }}>{v.temperature_f}°F</td>
                              <td style={{ padding: "8px 12px" }}>{v.blood_glucose} mg/dL</td>
                              <td style={{ padding: "8px 12px" }}>
                                <span className={`cv-badge ${statusClass}`} style={{ fontSize: "10px", padding: "2px 6px", textTransform: "capitalize" }}>
                                  {v.status?.replace("_", " ")}
                                </span>
                              </td>
                              <td style={{ padding: "8px 12px", color: "var(--cv-text-secondary)", fontSize: "11px" }}>
                                {v.notes}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 8: CONDITIONS & ALLERGIES
              ========================================================================= */}
          {activeTab === "allergies" && (
            <div
              role="tabpanel"
              id="tabpanel-allergies"
              aria-labelledby="tab-allergies"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — VERIFIED PATIENT ALLERGIES &amp; CONTRAINDICATION RULES
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {isHindi ? `कुल ${allergies.length} दर्ज एलर्जी` : `${allergies.length} documented adverse reactions`}
                </span>
              </div>

              {/* Active Chronic Conditions */}
              <div style={{ marginBottom: "20px" }}>
                <h4 style={{ margin: "0 0 10px", fontSize: "15px", color: "var(--cv-text-primary)" }}>
                  {isHindi ? "सक्रिय दीर्घकालिक स्थितियां (Chronic Conditions)" : "Active Chronic Conditions & Clinical Diagnoses"}
                </h4>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "12px" }}>
                  <div className="record-card" style={{ padding: "12px 16px", borderLeft: "4px solid #0284c7" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                      <strong style={{ color: "var(--cv-text-primary)", fontSize: "14px" }}>Essential (Primary) Hypertension</strong>
                      <span className="cv-badge cv-badge-routine">ICD-10 I10</span>
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                      Onset: 2 years ago • Managed with Telmisartan 40mg daily • BP well-controlled
                    </div>
                  </div>
                  <div className="record-card" style={{ padding: "12px 16px", borderLeft: "4px solid #10b981" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                      <strong style={{ color: "var(--cv-text-primary)", fontSize: "14px" }}>Type 2 Diabetes Mellitus</strong>
                      <span className="cv-badge cv-badge-routine">ICD-10 E11</span>
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                      Onset: 3 years ago • Monitored with HbA1c (6.8%, target &lt; 7.0%)
                    </div>
                  </div>
                </div>
              </div>

              {/* Recorded Allergies List */}
              {allergies.length === 0 ? (
                <EmptyState
                  icon="⚠️"
                  title={isHindi ? "कोई एलर्जी दर्ज नहीं है" : "No allergies recorded"}
                  description={isHindi ? "मरीज के लिए कोई दवा एलर्जी या प्रतिकूल प्रतिक्रियाएं दर्ज नहीं हैं।" : "No known drug allergies or adverse reactions are on record for this patient."}
                />
              ) : (
                <div style={{ display: "grid", gap: "14px", marginBottom: "24px" }}>
                  {allergies.map((al) => (
                    <div key={al.id} className="record-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                          <span style={{ fontSize: "18px" }}>⚠️</span>
                          <h4 style={{ margin: 0, fontSize: "16px", color: "var(--cv-text-primary)" }}>
                            {al.allergen_or_condition}
                          </h4>
                          <span className={`cv-badge ${al.severity?.toLowerCase() === "severe" ? "cv-badge-urgent" : "cv-badge-warning"}`}>
                            {al.severity} Severity
                          </span>
                        </div>
                        <div style={{ fontSize: "13px", color: "var(--cv-text-secondary)" }}>
                          <strong>Recorded Reaction: </strong>
                          {al.reaction_details || al.notes || "Hypersensitivity / severe allergic reaction"}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="cv-btn cv-btn-sm cv-btn-outline"
                        onClick={() =>
                          setSelectedRecordModal({
                            title: `Allergy: ${al.allergen_or_condition}`,
                            type: "Documented Drug Allergy",
                            category: "Immunology & Patient Safety",
                            date: formatDate(al.created_at),
                            actor: "Verified Clinical Allergy Registry",
                            urgency: al.severity === "severe" ? "emergency" : al.severity === "moderate" ? "urgent" : "routine",
                            status: "ACTIVE CONTRAINDICATION",
                            description: `Documented clinical hypersensitivity reaction: ${al.reaction_details || al.notes || "Adverse allergic reaction"}`,
                            warnings: [
                              `Severity Rating: ${al.severity?.toUpperCase()}`,
                              "Hard clinical contraindication on related compounds and classes.",
                              "Mandatory pre-flight medication cross-check active on all prescription orders.",
                            ],
                            instructions: [
                              "Avoid all medications containing this substance or related derivatives.",
                              "Ensure attending clinicians and triage nurses are informed prior to any administration.",
                              "Carry medical emergency identification detailing this hypersensitivity.",
                            ],
                            details: [
                              { label: "Allergen / Substance", value: al.allergen_or_condition },
                              { label: "Severity Rating", value: al.severity?.toUpperCase() },
                              { label: "Clinical Reaction", value: al.reaction_details || "Hypersensitivity" },
                              { label: "Contraindication Status", value: "Hard block on related compounds, mandatory pre-flight validation" },
                              { label: "Recorded Date", value: formatDate(al.created_at) },
                            ],
                          })
                        }
                      >
                        <span>👁️</span>
                        <span>{isHindi ? "विवरण देखें" : "View Details"}</span>
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Clinical Contraindication Guidance Rules */}
              <div style={{ marginTop: "20px" }}>
                <h4 style={{ margin: "0 0 12px", fontSize: "15px", color: "var(--cv-text-primary)" }}>
                  Clinical Safety &amp; Cross-Reactivity Guardrails (Module 5)
                </h4>
                <div style={{ display: "grid", gap: "12px" }}>
                  <div className="record-card" style={{ padding: "12px 16px" }}>
                    <strong style={{ color: "var(--cv-accent)" }}>Penicillin &amp; Cephalosporin Cross-Reactivity:</strong>
                    <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--cv-text-body)" }}>
                      Patients with severe penicillin anaphylaxis carry a <strong>2%–5% (and up to 10%)</strong> cross-reactivity risk with 1st and 2nd generation cephalosporins due to shared beta-lactam ring structures. System enforces hard blocking for penicillins and safety warnings for cephalosporins.
                    </p>
                  </div>
                  <div className="record-card" style={{ padding: "12px 16px" }}>
                    <strong style={{ color: "var(--cv-accent)" }}>Dengue / Thrombocytopenia &amp; NSAIDs:</strong>
                    <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--cv-text-body)" }}>
                      Ibuprofen, Naproxen, and Aspirin irreversibly inhibit platelet aggregation and cause gastric mucosal erosions. Strictly contraindicated during acute dengue infection or platelet counts &lt; 100,000 /µL.
                    </p>
                  </div>
                  <div className="record-card" style={{ padding: "12px 16px" }}>
                    <strong style={{ color: "var(--cv-accent)" }}>Hypertension &amp; Fluid-Retaining Analgesics:</strong>
                    <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--cv-text-body)" }}>
                      NSAIDs cause renal prostaglandin inhibition resulting in sodium retention and systemic vasoconstriction, blunting antihypertensive therapies.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================================
              TAB 9: INVOICES & PAYMENT RECEIPTS
              ========================================================================= */}
          {activeTab === "billing" && (
            <div
              role="tabpanel"
              id="tabpanel-billing"
              aria-labelledby="tab-billing"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — VERIFIED MEDICAL INVOICES &amp; PAYMENT RECEIPTS
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  {filteredInvoices.length === invoices.length
                    ? (isHindi ? `कुल ${invoices.length} बिलिंग रिकॉर्ड` : `${invoices.length} billing statements on file`)
                    : (isHindi ? `${invoices.length} में से ${filteredInvoices.length} रिकॉर्ड` : `Showing ${filteredInvoices.length} of ${invoices.length} invoices`)}
                </span>
              </div>

              {/* Billing Search & Status Filters */}
              <div className="health-records-toolbar">
                <input
                  className="cv-input health-records-search-input"
                  type="text"
                  placeholder={isHindi ? "बिल खोजें…" : "Search invoices…"}
                  value={billingSearch}
                  onChange={(e) => setBillingSearch(e.target.value)}
                />
                <div className="health-records-filter-strip" role="group" aria-label={isHindi ? "बिलिंग फ़िल्टर" : "Billing status filters"}>
                  {[
                    { id: "all", label: isHindi ? "सभी" : "All" },
                    { id: "paid", label: isHindi ? "भुगतान पूर्ण" : "Paid" },
                    { id: "pending", label: isHindi ? "लंबित" : "Pending" },
                    { id: "failed", label: isHindi ? "विफल" : "Failed" },
                  ].map((f) => (
                    <button
                      key={f.id}
                      type="button"
                      className={`cv-btn cv-btn-xs ${billingFilter === f.id ? "cv-btn-secondary" : "cv-btn-ghost"}`}
                      onClick={() => setBillingFilter(f.id)}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {invoices.length === 0 ? (
                <EmptyState
                  icon="💳"
                  title={isHindi ? "कोई बिलिंग रिकॉर्ड दर्ज नहीं है" : "No billing records found"}
                  description={isHindi ? "परामर्श के बाद जारी किए गए बिल और रसीदें यहाँ दिखाई देंगे।" : "Medical invoices and payment receipts from consultations will appear here."}
                />
              ) : filteredInvoices.length === 0 ? (
                <div className="cv-card cv-empty-state" style={{ textAlign: "center", padding: "32px 16px" }}>
                  <span style={{ fontSize: "32px", display: "block", marginBottom: "8px" }} aria-hidden="true">🔍</span>
                  <h4 style={{ margin: "0 0 6px", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                    {isHindi ? "कोई मेल खाने वाला बिल नहीं मिला" : "No matching invoices found"}
                  </h4>
                  <p style={{ margin: "0 0 14px", color: "var(--cv-text-muted)", fontSize: "13px" }}>
                    {isHindi
                      ? `वर्तमान खोज या स्थिति फ़िल्टर के लिए कोई इनवॉइस नहीं मिला। फ़िल्टर रीसेट करके सभी ${invoices.length} इनवॉइस देखें।`
                      : `No invoices matched your current filters. Reset filters to view all ${invoices.length} billing statements.`}
                  </p>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-secondary"
                    onClick={() => { setBillingSearch(""); setBillingFilter("all"); }}
                  >
                    {isHindi ? "फ़िल्टर रीसेट करें" : "Reset filters"}
                  </button>
                </div>
              ) : (
                <div style={{ display: "grid", gap: "14px" }}>
                  {filteredInvoices.map((inv) => {
                    const isPaid = inv.status === "paid";
                    const isPending = inv.status === "pending";
                    const amountFormatted = `₹${(inv.amount_minor / 100).toLocaleString("en-IN")}`;
                    const isDownloadingInv = downloadingId === `inv-${inv.id}`;
                    const isDownloadingRec = downloadingId === `rec-${inv.id}`;
                    return (
                      <div key={inv.id} className="record-card">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
                              <span style={{ fontSize: "11px", fontWeight: "700", color: "var(--cv-text-muted)", letterSpacing: "0.05em" }}>
                                {inv.invoice_number}
                              </span>
                              <span className={`cv-badge ${isPaid ? "cv-badge-success" : isPending ? "cv-badge-warning" : "cv-badge-urgent"}`} style={{ textTransform: "uppercase" }}>
                                {inv.status}
                              </span>
                              <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                                {formatDate(inv.created_at)}
                              </span>
                            </div>
                            <h3 style={{ margin: "4px 0", fontSize: "16px", color: "var(--cv-text-primary)" }}>
                              {inv.description || "Medical Consultation Fee"}
                            </h3>
                            <div style={{ fontSize: "20px", fontWeight: "800", color: "var(--cv-accent)", marginTop: "4px" }}>
                              {amountFormatted}
                            </div>
                            {inv.paid_at && (
                              <div style={{ fontSize: "12px", color: "var(--cv-text-muted)", marginTop: "2px" }}>
                                Paid on {formatDate(inv.paid_at)}
                              </div>
                            )}
                          </div>

                          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="cv-btn cv-btn-sm cv-btn-ghost"
                              onClick={() =>
                                setSelectedRecordModal({
                                  title: `Invoice ${inv.invoice_number}`,
                                  type: "Medical Billing Statement",
                                  category: "Hospital Administration",
                                  date: formatDate(inv.created_at),
                                  actor: inv.hospital_name || "CareVoice Health Center",
                                  urgency: "routine",
                                  status: inv.status?.toUpperCase(),
                                  description: `${inv.description || "Outpatient Clinical Consultation and Assessment Fee"} — Total Amount: ${amountFormatted}`,
                                  details: [
                                    { label: "Invoice Number", value: inv.invoice_number },
                                    { label: "Total Amount", value: amountFormatted },
                                    { label: "Payment Status", value: inv.status?.toUpperCase() },
                                    { label: "Currency", value: inv.currency?.toUpperCase() || "INR" },
                                    { label: "Billing Method", value: inv.payment_gateway || "Online UPI / Card Settlement" },
                                    { label: "Issue Date", value: formatDate(inv.created_at) },
                                    { label: "Settlement Timestamp", value: inv.paid_at ? formatDate(inv.paid_at) : "Pending Payment" },
                                  ],
                                  downloadPath: `/billing/invoices/${inv.id}/pdf`,
                                  downloadFilename: `invoice-${inv.invoice_number}.pdf`,
                                  downloadKey: `inv-${inv.id}`,
                                })
                              }
                            >
                              <span>👁️</span>
                              <span>{isHindi ? "विवरण देखें" : "View"}</span>
                            </button>
                            <button
                              type="button"
                              className="cv-btn cv-btn-sm cv-btn-outline cv-btn-download"
                              disabled={isDownloadingInv}
                              onClick={() =>
                                downloadBinary(
                                  `/billing/invoices/${inv.id}/pdf`,
                                  `invoice-${inv.invoice_number}.pdf`,
                                  `inv-${inv.id}`
                                )
                              }
                            >
                              <span>📥</span>
                              <span>{isDownloadingInv ? "…" : (isHindi ? "चालान PDF" : "Invoice PDF")}</span>
                            </button>
                            {isPaid && (
                              <button
                                type="button"
                                className="cv-btn cv-btn-sm cv-btn-primary cv-btn-download"
                                disabled={isDownloadingRec}
                                onClick={() =>
                                  downloadBinary(
                                    `/billing/receipts/${inv.id}/pdf`,
                                    `receipt-${inv.invoice_number}.pdf`,
                                    `rec-${inv.id}`
                                  )
                                }
                              >
                                <span>🧾</span>
                                <span>{isDownloadingRec ? "…" : (isHindi ? "रसीद PDF" : "Receipt PDF")}</span>
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 10: MULTILINGUAL PATIENT CARE GUIDES (EN / HI)
              ========================================================================= */}
          {activeTab === "guides" && (
            <div
              role="tabpanel"
              id="tabpanel-guides"
              aria-labelledby="tab-guides"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — POST-CONSULTATION PATIENT CARE GUIDES (EN / HI)
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  Clinical Primacy Enforced: Only finalized clinician encounter notes
                </span>
              </div>

              {/* Guide Selector Controls */}
              <div className="record-card" style={{ marginBottom: "20px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "14px", alignItems: "flex-end" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "var(--cv-text-secondary)", marginBottom: "6px" }}>
                      {isHindi ? "परामर्श नोट चुनें" : "Select Clinical Encounter"}
                    </label>
                    <select
                      className="cv-select"
                      value={guideApptId}
                      onChange={(e) => setGuideApptId(e.target.value)}
                    >
                      <option value="">
                        {notes.length === 0 ? "No finalized notes available" : "-- Choose Finalized Consultation --"}
                      </option>
                      {notes.map((n) => (
                        <option key={n.id} value={n.appointment_id || n.id}>
                          {n.chief_complaint || "Encounter"} - Dr. {n.doctor_name || "Clinician"} ({formatDate(n.finalized_at || n.created_at)})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "12px", fontWeight: "700", color: "var(--cv-text-secondary)", marginBottom: "6px" }}>
                      {isHindi ? "गाइड भाषा चुनें" : "Guide Language"}
                    </label>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        type="button"
                        className={`cv-btn cv-btn-sm ${guideLang === "en" ? "cv-btn-primary" : "cv-btn-outline"}`}
                        onClick={() => setGuideLang("en")}
                      >
                        English (EN)
                      </button>
                      <button
                        type="button"
                        className={`cv-btn cv-btn-sm ${guideLang === "hi" ? "cv-btn-primary" : "cv-btn-outline"}`}
                        onClick={() => setGuideLang("hi")}
                      >
                        हिंदी (HI)
                      </button>
                    </div>
                  </div>

                  <div>
                    <button
                      type="button"
                      className="cv-btn cv-btn-primary"
                      disabled={loadingGuide || (!guideApptId && notes.length === 0)}
                      onClick={() => {
                        const targetId = guideApptId || (notes[0]?.appointment_id || notes[0]?.id);
                        if (targetId) fetchCareGuide(targetId, guideLang);
                      }}
                      style={{ width: "100%" }}
                    >
                      <span>📖</span>
                      <span>
                        {loadingGuide
                          ? (isHindi ? "गाइड तैयार हो रही है…" : "Loading Care Guide…")
                          : (isHindi ? "केयर गाइड देखें" : "Generate / View Care Guide")}
                      </span>
                    </button>
                  </div>
                </div>
              </div>

              {guideError && (
                <div className="cv-alert cv-alert-warning" style={{ marginBottom: "16px" }}>
                  <span>⚠️</span>
                  <div>{guideError}</div>
                </div>
              )}

              {/* Care Guide Display */}
              {careGuide ? (
                <div className="record-card" style={{ borderTop: "4px solid var(--cv-accent)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "10px", borderBottom: "1px solid var(--cv-border-soft)", paddingBottom: "14px", marginBottom: "16px" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                        <span style={{ fontSize: "20px" }}>📖</span>
                        <h3 style={{ margin: 0, fontSize: "18px", color: "var(--cv-text-primary)" }}>
                          {careGuide.title || (isHindi ? "रोगी देखभाल गाइड" : "Personalized Patient Care Guide")}
                        </h3>
                        <span className="cv-badge cv-badge-routine">{careGuide.language?.toUpperCase()}</span>
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--cv-text-muted)", marginTop: "4px" }}>
                        Attending: <strong>Dr. {careGuide.attending_doctor || "Clinician"}</strong> • Generated {formatDate(careGuide.generated_at)}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        type="button"
                        className="cv-btn cv-btn-sm cv-btn-outline"
                        onClick={() => window.print()}
                      >
                        <span>🖨️</span>
                        <span>{isHindi ? "प्रिंट करें" : "Print Guide"}</span>
                      </button>
                      <button
                        type="button"
                        className="cv-btn cv-btn-sm cv-btn-primary"
                        onClick={() => {
                          const blob = new Blob([JSON.stringify(careGuide, null, 2)], { type: "application/json" });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement("a");
                          a.href = url;
                          a.download = `patient-care-guide-${careGuide.language}.json`;
                          a.click();
                          URL.revokeObjectURL(url);
                        }}
                      >
                        <span>📥</span>
                        <span>{isHindi ? "गाइड सेव करें" : "Download Guide"}</span>
                      </button>
                    </div>
                  </div>

                  {/* Plain Language Summary */}
                  <div style={{ marginBottom: "16px", padding: "14px", borderRadius: "8px", background: "var(--cv-surface-soft)" }}>
                    <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>
                      {isHindi ? "सरल भाषा में स्वास्थ्य सारांश" : "Plain Language Health Summary"}
                    </div>
                    <p style={{ margin: 0, fontSize: "14px", color: "var(--cv-text-body)", lineHeight: "1.7" }}>
                      {careGuide.plain_language_summary}
                    </p>
                  </div>

                  {/* Medication Timing Schedule */}
                  {careGuide.medication_schedule?.length > 0 && (
                    <div style={{ marginBottom: "16px" }}>
                      <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase", marginBottom: "8px" }}>
                        {isHindi ? "दवा लेने का समय सारणी" : "Medication & Administration Schedule"}
                      </div>
                      <div style={{ display: "grid", gap: "8px" }}>
                        {careGuide.medication_schedule.map((m, idx) => (
                          <div key={idx} style={{ padding: "10px 14px", borderRadius: "8px", border: "1px solid var(--cv-border)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                            <div>
                              <strong style={{ color: "var(--cv-text-primary)", fontSize: "14px" }}>{m.medication}</strong>
                              <div style={{ fontSize: "12px", color: "var(--cv-text-muted)", marginTop: "2px" }}>
                                {m.timing_with_meals} • Duration: {m.duration}
                              </div>
                            </div>
                            <span className="cv-badge cv-badge-routine">{m.dosage}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Red Flags / Emergency Warnings */}
                  {careGuide.red_flag_symptoms?.length > 0 && (
                    <div className="cv-alert cv-alert-danger" style={{ marginBottom: "16px", padding: "12px 16px" }}>
                      <span style={{ fontSize: "20px" }}>🚨</span>
                      <div style={{ flex: 1 }}>
                        <strong style={{ fontSize: "14px" }}>
                          {isHindi ? "आपातकालीन चेतावनी लक्षण (तुरंत डॉक्टर या 112 से संपर्क करें):" : "Emergency Warning Symptoms (Seek immediate care or call 112):"}
                        </strong>
                        <ul style={{ margin: "6px 0 0", paddingLeft: "18px", fontSize: "13px" }}>
                          {careGuide.red_flag_symptoms.map((rf, idx) => (
                            <li key={idx}>{rf}</li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  )}

                  {/* Lifestyle & Dietary Guidance */}
                  {careGuide.lifestyle_and_diet?.length > 0 && (
                    <div style={{ marginBottom: "16px" }}>
                      <div style={{ fontSize: "11px", fontWeight: "800", color: "var(--cv-text-muted)", textTransform: "uppercase", marginBottom: "6px" }}>
                        {isHindi ? "दैनिक जीवनशैली व आहार निर्देश" : "Daily Lifestyle & Dietary Recommendations"}
                      </div>
                      <ul style={{ margin: 0, paddingLeft: "18px", fontSize: "13px", color: "var(--cv-text-body)", lineHeight: "1.7" }}>
                        {careGuide.lifestyle_and_diet.map((ls, idx) => (
                          <li key={idx}>{ls}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Audio Prompt Simulation */}
                  {careGuide.multilingual_audio_prompt && (
                    <div style={{ padding: "12px 14px", borderRadius: "8px", background: "var(--cv-accent-soft)", border: "1px solid var(--cv-accent)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontSize: "20px" }}>🔊</span>
                        <div style={{ fontSize: "13px", color: "var(--cv-text-primary)", fontWeight: "600" }}>
                          {isHindi ? "ऑडियो विवरण उपलब्ध है" : "Audio Guide Voice Narration Available"}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="cv-btn cv-btn-xs cv-btn-primary"
                        onClick={() => {
                          if ("speechSynthesis" in window) {
                            const utt = new SpeechSynthesisUtterance(careGuide.plain_language_summary);
                            utt.lang = careGuide.language === "hi" ? "hi-IN" : "en-US";
                            window.speechSynthesis.speak(utt);
                          } else {
                            alert("Text-to-speech is not supported by your browser.");
                          }
                        }}
                      >
                        ▶ {isHindi ? "सुनें" : "Play Narration"}
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <EmptyState
                  icon="📖"
                  title={isHindi ? "कोई केयर गाइड चयनित नहीं है" : "Select an encounter to view Care Guide"}
                  description={isHindi ? "ऊपर दी गई सूची से परामर्श चुनें और 'केयर गाइड देखें' पर क्लिक करें।" : "Choose an encounter from the dropdown above and generate your multilingual patient care guide."}
                />
              )}
            </div>
          )}

          {/* =========================================================================
              TAB 11: CARE TEAM & FACILITIES
              ========================================================================= */}
          {activeTab === "careteam" && (
            <div
              role="tabpanel"
              id="tabpanel-careteam"
              aria-labelledby="tab-careteam"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — ASSIGNED MULTIDISCIPLINARY CARE TEAM &amp; NETWORK
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  CareVoice Integrated Health Network
                </span>
              </div>

              <div style={{ display: "grid", gap: "16px", marginBottom: "24px" }}>
                <div className="record-card" style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
                  <div style={{ width: "52px", height: "52px", borderRadius: "50%", background: "var(--cv-accent-soft)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "24px" }}>
                    👨‍⚕️
                  </div>
                  <div style={{ flex: 1, minWidth: "220px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <h4 style={{ margin: 0, fontSize: "16px", color: "var(--cv-text-primary)" }}>Dr. Ayesha Khan, MD</h4>
                      <span className="cv-badge cv-badge-routine">Primary Attending Physician</span>
                    </div>
                    <div style={{ fontSize: "13px", color: "var(--cv-text-muted)", marginTop: "4px" }}>
                      Internal Medicine &amp; Chronic Care Management • Reg #MCI-2018-98421
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--cv-text-secondary)", marginTop: "2px" }}>
                      Available for Teleconsultation &amp; In-Person Follow-up
                    </div>
                  </div>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-primary"
                    onClick={() => alert("Follow-up appointment booking initiated. Our scheduling team will confirm your slot.")}
                  >
                    <span>📅</span>
                    <span>Book Appointment</span>
                  </button>
                </div>

                <div className="record-card" style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
                  <div style={{ width: "52px", height: "52px", borderRadius: "50%", background: "var(--cv-surface-soft)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "24px" }}>
                    🩺
                  </div>
                  <div style={{ flex: 1, minWidth: "220px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <h4 style={{ margin: 0, fontSize: "16px", color: "var(--cv-text-primary)" }}>Dr. Rajesh Sharma, MD, DM</h4>
                      <span className="cv-badge cv-badge-info">Consulting Cardiologist</span>
                    </div>
                    <div style={{ fontSize: "13px", color: "var(--cv-text-muted)", marginTop: "4px" }}>
                      Cardiovascular Sciences &amp; Preventive Cardiology • Reg #DMC-14298
                    </div>
                  </div>
                  <button
                    type="button"
                    className="cv-btn cv-btn-sm cv-btn-outline"
                    onClick={() => alert("Consultation request logged.")}
                  >
                    Request Referral
                  </button>
                </div>

                <div className="record-card" style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
                  <div style={{ width: "52px", height: "52px", borderRadius: "50%", background: "var(--cv-surface-soft)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "24px" }}>
                    🏥
                  </div>
                  <div style={{ flex: 1, minWidth: "220px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <h4 style={{ margin: 0, fontSize: "16px", color: "var(--cv-text-primary)" }}>CareVoice Health Center of Excellence</h4>
                      <span className="cv-badge cv-badge-success">NABH Accredited</span>
                    </div>
                    <div style={{ fontSize: "13px", color: "var(--cv-text-muted)", marginTop: "4px" }}>
                      Institutional Hub, South Extension, New Delhi 110049
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--cv-text-secondary)", marginTop: "2px" }}>
                      Emergency Department: Open 24x7 • Diagnostic Labs Onsite
                    </div>
                  </div>
                </div>
              </div>

              {/* Emergency Hotlines Row */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "14px" }}>
                <div className="record-card" style={{ borderLeft: "4px solid #dc2626" }}>
                  <div style={{ fontSize: "11px", fontWeight: "800", color: "#dc2626", textTransform: "uppercase" }}>National Emergency Hotline</div>
                  <div style={{ fontSize: "24px", fontWeight: "900", color: "var(--cv-text-primary)", margin: "4px 0" }}>112</div>
                  <div style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>Ambulance, Police, and Fire Services nationwide</div>
                </div>
                <div className="record-card" style={{ borderLeft: "4px solid #0284c7" }}>
                  <div style={{ fontSize: "11px", fontWeight: "800", color: "#0284c7", textTransform: "uppercase" }}>Tele-MANAS Mental Health</div>
                  <div style={{ fontSize: "24px", fontWeight: "900", color: "var(--cv-text-primary)", margin: "4px 0" }}>14416</div>
                  <div style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>24/7 Toll-free mental health psychological support</div>
                </div>
              </div>
            </div>
          )}

          {/* =========================================================================
              TAB 12: DPDP PRIVACY & PORTABILITY
              ========================================================================= */}
          {activeTab === "privacy" && (
            <div
              role="tabpanel"
              id="tabpanel-privacy"
              aria-labelledby="tab-privacy"
              tabIndex={0}
              className="health-records-tabpanel"
            >
              <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
                <span className="demo-data-tag">
                  DEMO DATA — DPDP ACT 2023 PATIENT PRIVACY &amp; CONSENT
                </span>
                <span style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                  Revocable Consent, 48h Cooling-off, FHIR R4 Bundle &amp; PIN-Protected Links
                </span>
              </div>

              <DPDPPrivacyCenter
                token={token}
                isHindi={isHindi}
                patientId={overview?.patient_user_id || 1}
              />
            </div>
          )}
        </>
      )}

      {/* =========================================================================
          VIEW RECORD DETAILS MODAL (Action: View Details, Print, Download)
          ========================================================================= */}
      {selectedRecordModal && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedRecordModal(null)}
          size="large"
          title={selectedRecordModal.title || (isHindi ? "क्लिनिकल रिकॉर्ड विवरण" : "Clinical Record Details")}
          language={language}
          className="cv-modal-clinical-record"
          bodyClassName="cv-modal-record-body"
        >
          <div id="cv-printable-area" className="cv-record-detail-container">
            {/* Official Clinic / Hospital Letterhead Header */}
            <div className="cv-print-header">
              <div className="cv-print-header-top">
                <div className="cv-print-logo-group">
                  <span className="cv-print-cross-icon" aria-hidden="true">✚</span>
                  <div>
                    <div className="cv-print-hospital-name">CAREVOICE HEALTH NETWORK</div>
                    <div className="cv-print-hospital-sub">Center of Clinical Excellence &amp; Patient Care • Reg #NABH-2024-ND-0842</div>
                  </div>
                </div>
                <div className="cv-print-meta-right">
                  <div><strong>Record Ref:</strong> {selectedRecordModal.downloadKey || "CV-REC-2026"}</div>
                  <div><strong>Date:</strong> {selectedRecordModal.date}</div>
                </div>
              </div>

              {/* Patient Demographic Bar */}
              <div className="cv-patient-demographics-bar">
                <div><strong>Patient:</strong> {overview?.full_name || "Patient Record"}</div>
                <div><strong>Patient ID:</strong> P-{String(overview?.patient_user_id || 1).padStart(5, "0")}</div>
                <div><strong>Age / Gender:</strong> {overview?.age ? `${overview.age}Y` : "Adult"} / {overview?.gender ? overview.gender.toUpperCase() : "N/A"}</div>
                <div><strong>Attending:</strong> {selectedRecordModal.actor || "Staff Clinician"}</div>
              </div>
            </div>

            {/* Scrollable Clinical Body */}
            <div className="cv-record-detail-body">
              {/* Record Title & Badges Strip */}
              <div className="cv-record-title-strip">
                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
                  <span className="cv-badge cv-badge-routine" style={{ textTransform: "uppercase" }}>
                    {selectedRecordModal.type || "Clinical Record"}
                  </span>
                  {selectedRecordModal.urgency && (
                    <span className={`cv-badge ${getUrgencyBadgeConfig(selectedRecordModal.urgency).className}`}>
                      {getUrgencyBadgeConfig(selectedRecordModal.urgency).label}
                    </span>
                  )}
                  {selectedRecordModal.status && (
                    <span className={`cv-badge ${selectedRecordModal.status.toLowerCase().includes("draft") ? "cv-badge-warning" : "cv-badge-success"}`}>
                      {selectedRecordModal.status.toUpperCase()}
                    </span>
                  )}
                  {selectedRecordModal.category && (
                    <span className="cv-badge cv-badge-neutral" style={{ textTransform: "uppercase" }}>
                      {selectedRecordModal.category}
                    </span>
                  )}
                </div>
                <h3 className="cv-record-main-title">{selectedRecordModal.title}</h3>
              </div>

              {/* Section 1: Chief Complaint / Reason for Visit */}
              {selectedRecordModal.description && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">📋</span>
                    <span>{isHindi ? "मुख्य शिकायत और विज़िट सारांश" : "Chief Complaint & Encounter Summary"}</span>
                  </h4>
                  <div className="cv-detail-text-box">
                    {selectedRecordModal.description}
                  </div>
                </div>
              )}

              {/* Section 2: Vital Signs Encounter Snapshot */}
              {(selectedRecordModal.vitals || (overview?.recent_vitals && overview.recent_vitals.length > 0)) && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">💓</span>
                    <span>{isHindi ? "वाइटल साइन्स अवलोकन" : "Recorded Vital Signs"}</span>
                  </h4>
                  <div className="cv-patient-demographics-bar" style={{ background: "var(--cv-surface-tint)" }}>
                    {(() => {
                      const v = selectedRecordModal.vitals || overview?.recent_vitals?.[0];
                      return (
                        <>
                          <div><strong>Blood Pressure:</strong> {v.bp_systolic && v.bp_diastolic ? `${v.bp_systolic}/${v.bp_diastolic} mmHg` : "120/80 mmHg"}</div>
                          <div><strong>Heart Rate:</strong> {v.heart_rate_bpm ? `${v.heart_rate_bpm} bpm` : "72 bpm"}</div>
                          <div><strong>Oxygen (SpO2):</strong> {v.spo2_percent ? `${v.spo2_percent}%` : "98%"}</div>
                          <div><strong>Temperature:</strong> {v.body_temp_c ? `${(v.body_temp_c * 9/5 + 32).toFixed(1)}°F (${v.body_temp_c}°C)` : "98.6°F"}</div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              )}

              {/* Section 3: Diagnostic Parameters Table (Lab/Imaging) */}
              {selectedRecordModal.parameters?.length > 0 && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">🧪</span>
                    <span>{isHindi ? "परीक्षण परिणाम और जैविक संदर्भ अंतराल" : "Test Parameters & Biological Reference Intervals"}</span>
                  </h4>
                  <div className="cv-table-responsive">
                    <table className="cv-clinical-table">
                      <thead>
                        <tr>
                          <th>Test Parameter</th>
                          <th>Observed Result</th>
                          <th>Reference Range</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedRecordModal.parameters.map((p, idx) => (
                          <tr key={idx} className={p.status !== "NORMAL" ? "cv-row-abnormal" : ""}>
                            <td style={{ fontWeight: "600" }}>{p.name}</td>
                            <td><strong>{p.value}</strong></td>
                            <td style={{ color: "var(--cv-text-muted)" }}>{p.reference_range}</td>
                            <td>
                              <span className={`cv-badge ${p.status === "NORMAL" ? "cv-badge-success" : p.status?.includes("CRITICAL") ? "cv-badge-danger" : "cv-badge-warning"}`}>
                                {p.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Section 4: Physical Examination & Clinical Findings */}
              {selectedRecordModal.findings && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">🔍</span>
                    <span>{isHindi ? "शारीरिक परीक्षण और अवलोकन" : "Clinical Findings & Observations"}</span>
                  </h4>
                  {Array.isArray(selectedRecordModal.findings) ? (
                    <ul className="cv-detail-list">
                      {selectedRecordModal.findings.map((f, idx) => (
                        <li key={idx}>
                          <strong>{f.finding || f.title || f}</strong>
                          {f.significance && <span style={{ color: "var(--cv-text-muted)", marginLeft: "6px" }}>— {f.significance}</span>}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="cv-detail-text-box">{selectedRecordModal.findings}</div>
                  )}
                </div>
              )}

              {/* Section 5: Clinical Diagnosis & Assessment */}
              {selectedRecordModal.diagnosis && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">🩺</span>
                    <span>{isHindi ? "नैदानिक मूल्यांकन / निदान" : "Clinical Diagnosis & Assessment"}</span>
                  </h4>
                  <div className="cv-detail-text-box cv-diagnosis-box">
                    {selectedRecordModal.diagnosis}
                  </div>
                </div>
              )}

              {/* Section 6: Treatment Plan & Prescribed Medications */}
              {selectedRecordModal.treatment && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">℞</span>
                    <span>{isHindi ? "उपचार योजना और निर्धारित दवाएं" : "Treatment Plan & Prescribed Medications"}</span>
                  </h4>
                  {Array.isArray(selectedRecordModal.treatment) ? (
                    <div className="cv-table-responsive">
                      <table className="cv-clinical-table">
                        <thead>
                          <tr>
                            <th>Medication</th>
                            <th>Strength &amp; Form</th>
                            <th>Frequency &amp; Route</th>
                            <th>Duration</th>
                            <th>Instructions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedRecordModal.treatment.map((it, idx) => (
                            <tr key={idx}>
                              <td style={{ fontWeight: "700", color: "var(--cv-accent)" }}>{it.medication_name}</td>
                              <td>{it.strength} {it.dosage_form}</td>
                              <td>{it.frequency} ({it.route})</td>
                              <td>{it.duration}</td>
                              <td style={{ fontSize: "12px" }}>{it.instructions}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="cv-detail-text-box">{selectedRecordModal.treatment}</div>
                  )}
                </div>
              )}

              {/* Section 7: Allergy & Safety Alerts */}
              {(selectedRecordModal.warnings?.length > 0 || selectedRecordModal.redFlags?.length > 0) && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title" style={{ color: "#dc2626" }}>
                    <span className="cv-section-icon" aria-hidden="true">⚠️</span>
                    <span>{isHindi ? "एलर्जी और क्लिनिकल सुरक्षा चेतावनी" : "Allergy Screen & Clinical Safety Alerts"}</span>
                  </h4>
                  <div className="cv-warning-box">
                    {selectedRecordModal.warnings?.map((w, idx) => (
                      <div key={idx} style={{ marginBottom: "4px" }}>• {w}</div>
                    ))}
                    {selectedRecordModal.redFlags?.map((rf, idx) => (
                      <div key={idx} style={{ color: "#b91c1c", fontWeight: "600", marginBottom: "4px" }}>🚨 RED FLAG: {rf}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* Section 8: Follow-up Instructions & Next Steps */}
              {selectedRecordModal.instructions && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">📅</span>
                    <span>{isHindi ? "अनुवर्ती निर्देश और आपातकालीन चेतावनी" : "Follow-Up Instructions & Warning Signs"}</span>
                  </h4>
                  {Array.isArray(selectedRecordModal.instructions) ? (
                    <ul className="cv-detail-list">
                      {selectedRecordModal.instructions.map((step, idx) => (
                        <li key={idx}>{step}</li>
                      ))}
                    </ul>
                  ) : (
                    <div className="cv-detail-text-box">{selectedRecordModal.instructions}</div>
                  )}
                </div>
              )}

              {/* Section 9: Clinical Evidence & Citations */}
              {selectedRecordModal.evidence?.length > 0 && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">📚</span>
                    <span>{isHindi ? "क्लिनिकल साक्ष्य और दिशानिर्देश संदर्भ" : "Clinical Evidence & Medical Citations"}</span>
                  </h4>
                  <div style={{ display: "grid", gap: "6px" }}>
                    {selectedRecordModal.evidence.map((src, idx) => (
                      <div key={idx} className="cv-citation-badge">
                        <span style={{ fontWeight: "600" }}>{src.title || src.source_title || src}</span>
                        {src.provenance && <span style={{ color: "var(--cv-text-muted)", marginLeft: "6px" }}>({src.provenance})</span>}
                        {src.url && (
                          <a href={src.url} target="_blank" rel="noopener noreferrer" style={{ marginLeft: "8px", color: "var(--cv-accent)" }}>
                            ↗ Read Guideline
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Section 10: Administrative & Encounter Details */}
              {selectedRecordModal.details?.length > 0 && (
                <div className="cv-detail-section cv-print-section">
                  <h4 className="cv-detail-section-title">
                    <span className="cv-section-icon" aria-hidden="true">ℹ️</span>
                    <span>{isHindi ? "अतिरिक्त प्रशासनिक और क्लिनिकल विवरण" : "Administrative & Encounter Details"}</span>
                  </h4>
                  <div className="cv-detail-grid">
                    {selectedRecordModal.details.map((d, idx) => (
                      <div key={idx} className="cv-detail-grid-item">
                        <span className="cv-detail-grid-label">{d.label}</span>
                        <span className="cv-detail-grid-val">{d.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Section 11: Attending Clinician Digital Signature Block */}
              <div className="cv-detail-signature-block cv-print-section">
                <div className="cv-signature-left">
                  <div className="cv-signature-stamp">CAREVOICE VERIFIED</div>
                  <div style={{ fontSize: "11px", color: "var(--cv-text-muted)", marginTop: "4px" }}>
                    Electronically authenticated via secure SHA-256 digital signature in compliance with IT Act &amp; MCI Telemedicine Guidelines.
                  </div>
                </div>
                <div className="cv-signature-right">
                  <div className="cv-signature-line" />
                  <div style={{ fontWeight: "700", color: "var(--cv-text-primary)", fontSize: "14px" }}>
                    {selectedRecordModal.actor || "Attending Consultant"}
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                    CareVoice Medical Staff • Registered Practitioner
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--cv-accent-text)", marginTop: "2px" }}>
                    Authenticated: {selectedRecordModal.date}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Modal Action Controls (Hidden during print) */}
          <div className="cv-modal-actions no-print">
            <button
              type="button"
              className="cv-btn cv-btn-outline cv-btn-print"
              onClick={() => window.print()}
            >
              <span>🖨️</span>
              <span>{isHindi ? "प्रिंट रिकॉर्ड" : "Print Record"}</span>
            </button>

            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              {selectedRecordModal.downloadPath && (
                <button
                  type="button"
                  className="cv-btn cv-btn-primary cv-btn-download"
                  disabled={downloadingId === (selectedRecordModal.downloadKey || "modal-download")}
                  onClick={() =>
                    downloadBinary(
                      selectedRecordModal.downloadPath,
                      selectedRecordModal.downloadFilename || "clinical-record.pdf",
                      selectedRecordModal.downloadKey || "modal-download"
                    )
                  }
                >
                  <span>📥</span>
                  <span>
                    {downloadingId === (selectedRecordModal.downloadKey || "modal-download")
                      ? (isHindi ? "डाउनलोड हो रहा है…" : "Downloading PDF…")
                      : (isHindi ? "PDF डाउनलोड" : "Download PDF")}
                  </span>
                </button>
              )}
              <button
                type="button"
                className="cv-btn cv-btn-secondary"
                style={{ minHeight: "44px", minWidth: "80px", fontWeight: "700" }}
                onClick={() => setSelectedRecordModal(null)}
              >
                {isHindi ? "बंद करें" : "Close"}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* =========================================================================
          VIEW AI CONVERSATION TRANSCRIPT MODAL
          ========================================================================= */}
      {selectedConversation && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedConversation(null)}
          title={selectedConversation.symptom_summary?.slice(0, 60) || (isHindi ? "परामर्श संवाद" : "AI Consultation Transcript")}
        >
          <div style={{ padding: "4px 0", maxHeight: "70vh", overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px", borderBottom: "1px solid var(--cv-border-soft)", paddingBottom: "10px", marginBottom: "14px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span className={`cv-badge ${getUrgencyBadgeConfig(selectedConversation.triage_level || selectedConversation.care_urgency || "routine").className}`}>
                  {getUrgencyBadgeConfig(selectedConversation.triage_level || selectedConversation.care_urgency || "routine").label}
                </span>
                <span className="cv-badge cv-badge-neutral" style={{ textTransform: "uppercase" }}>
                  Language: {selectedConversation.language?.toUpperCase() || "EN"}
                </span>
              </div>
              <div style={{ fontSize: "12px", color: "var(--cv-text-muted)" }}>
                ID: {selectedConversation.assessment_id?.slice(0, 8)}
              </div>
            </div>

            {/* Clinical Symptom Summary */}
            {selectedConversation.symptom_summary && (
              <div style={{ marginBottom: "14px", padding: "10px 12px", borderRadius: "8px", background: "var(--cv-surface-soft)", fontSize: "13px", lineHeight: "1.5" }}>
                <strong style={{ color: "var(--cv-text-primary)" }}>Clinical Symptom Summary: </strong>
                <span style={{ color: "var(--cv-text-body)" }}>{selectedConversation.symptom_summary}</span>
              </div>
            )}

            {/* Multi-turn Chat Dialogue */}
            <div style={{ display: "grid", gap: "12px", marginBottom: "16px" }}>
              {(selectedConversation.messages || []).map((msg, mIdx) => {
                const isAssistant = msg.role === "assistant";
                return (
                  <div
                    key={mIdx}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: isAssistant ? "flex-start" : "flex-end",
                    }}
                  >
                    <div style={{ fontSize: "11px", fontWeight: "700", color: "var(--cv-text-muted)", marginBottom: "3px", textTransform: "uppercase" }}>
                      {isAssistant ? "CareVoice AI Assistant" : "Patient"}
                    </div>
                    <div
                      style={{
                        maxWidth: "85%",
                        padding: "10px 14px",
                        borderRadius: "12px",
                        background: isAssistant ? "var(--cv-surface-soft)" : "var(--cv-accent)",
                        color: isAssistant ? "var(--cv-text-primary)" : "#ffffff",
                        fontSize: "13px",
                        lineHeight: "1.5",
                        whiteSpace: "pre-wrap",
                        boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                      }}
                    >
                      {msg.content}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Red Flags if present */}
            {selectedConversation.red_flags?.length > 0 && (
              <div className="cv-alert cv-alert-danger" style={{ marginBottom: "12px", padding: "10px 12px", fontSize: "12px" }}>
                <span>🚨</span>
                <div>
                  <strong>Red Flag Symptoms Identified: </strong>
                  <ul style={{ margin: "4px 0 0", paddingLeft: "16px" }}>
                    {selectedConversation.red_flags.map((rf, idx) => (
                      <li key={idx}>{rf}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* Recommended Next Steps */}
            {selectedConversation.recommended_next_steps?.length > 0 && (
              <div style={{ marginBottom: "12px", padding: "10px 12px", borderRadius: "8px", background: "var(--cv-surface-soft)", fontSize: "12px" }}>
                <strong style={{ color: "var(--cv-text-primary)" }}>Recommended Clinical Next Steps: </strong>
                <ol style={{ margin: "4px 0 0", paddingLeft: "16px", color: "var(--cv-text-secondary)" }}>
                  {selectedConversation.recommended_next_steps.map((step, idx) => (
                    <li key={idx}>{step}</li>
                  ))}
                </ol>
              </div>
            )}

            {/* Evidence Sources */}
            {selectedConversation.evidence_sources?.length > 0 && (
              <div style={{ marginBottom: "14px", fontSize: "11px", color: "var(--cv-text-muted)" }}>
                <strong>Evidence Citations: </strong>
                {selectedConversation.evidence_sources.map((s, idx) => (
                  <span key={idx}>
                    {idx > 0 && " • "}
                    {s.title || s.provenance}
                  </span>
                ))}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "14px", borderTop: "1px solid var(--cv-border-soft)", paddingTop: "10px" }}>
              <button
                type="button"
                className="cv-btn cv-btn-sm cv-btn-secondary"
                onClick={() => setSelectedConversation(null)}
              >
                {isHindi ? "संवाद बंद करें" : "Close Transcript"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
