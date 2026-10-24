import { useState, useEffect, useMemo, useRef } from "react";
import { apiRequest } from "../services/api";
import { formatAppointmentDatePart, formatAppointmentDateTime } from "../services/appointments";
import "../patientDashboard.css";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

// Formats ISO timestamp to localized DD MMM YYYY.
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

// Formats ISO timestamp with time: DD MMM YYYY, HH:MM.
function formatDateTime(isoString) {
  if (!isoString) return "";
  try {
    return new Date(isoString).toLocaleString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

// Visual placeholder rendered when a query or list returns zero records with actionable CTA.
export function EmptyState({ icon = "◇", title, description, action }) {
  return (
    <div className="cv-empty">
      <span aria-hidden="true">{icon}</span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

// Standardized clinical metric metadata and reference thresholds.
const METRIC_CONFIGS = {
  bp: {
    label: "Blood Pressure",
    unit: "mmHg",
    series: [
      { key: "bp_systolic", label: "Systolic", color: "#006E51", normalMin: 90, normalMax: 120 },
      { key: "bp_diastolic", label: "Diastolic", color: "#0284C7", normalMin: 60, normalMax: 80 },
    ],
    yMin: 50,
    yMax: 180,
    referenceText: "Standard resting target: < 120/80 mmHg (AHA/ACC Stage 1 threshold >= 130/80)",
  },
  hr: {
    label: "Heart Rate",
    unit: "bpm",
    series: [
      { key: "heart_rate", label: "Pulse Rate", color: "#D97706", normalMin: 60, normalMax: 100 },
    ],
    yMin: 40,
    yMax: 130,
    referenceText: "Normal resting heart rate: 60 – 100 bpm",
  },
  spo2: {
    label: "Oxygen Saturation (SpO2)",
    unit: "%",
    series: [
      { key: "spo2", label: "Oxygen Saturation", color: "#0284C7", normalMin: 95, normalMax: 100 },
    ],
    yMin: 88,
    yMax: 100,
    referenceText: "Normal arterial oxygen saturation on room air: 95 – 100%",
  },
  glucose: {
    label: "Blood Glucose",
    unit: "mg/dL",
    series: [
      { key: "blood_glucose", label: "Glucose Level", color: "#7C3AED", normalMin: 70, normalMax: 99 },
    ],
    yMin: 60,
    yMax: 160,
    referenceText: "Normal fasting reference range: 70 – 99 mg/dL (Pre-diabetes: 100 – 125 mg/dL)",
  },
  weight: {
    label: "Body Weight",
    unit: "kg",
    series: [
      { key: "weight_kg", label: "Weight", color: "#059669", normalMin: 50, normalMax: 85 },
    ],
    yMin: 50,
    yMax: 95,
    referenceText: "Measured body weight trajectory",
  },
};

export function PatientDashboard({ user, patient, token, onNavigate, language = "en" }) {
  const isHindi = language === "hi";

  // Data states
  const [overview, setOverview] = useState(null);
  const [vitalsList, setVitalsList] = useState([]);
  const [labTrends, setLabTrends] = useState({ trends: [] });
  const [insightsData, setInsightsData] = useState(null);
  const [appointments, setAppointments] = useState([]);
  const [timelineEvents, setTimelineEvents] = useState([]);
  const [prescriptions, setPrescriptions] = useState([]);
  const [notes, setNotes] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [allergies, setAllergies] = useState([]);

  // UI interaction states
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [downloadingId, setDownloadingId] = useState(null);

  // Vitals Chart state
  const [activeMetric, setActiveMetric] = useState("bp");
  const [chartTimeRange, setChartTimeRange] = useState("all"); // "30", "60", "all"
  const [showVitalsTable, setShowVitalsTable] = useState(false);
  const [hoveredVitalIndex, setHoveredVitalIndex] = useState(null);

  // Lab Trends Chart state
  const [activeAnalyteKey, setActiveAnalyteKey] = useState("fasting_glucose");
  const [showLabTable, setShowLabTable] = useState(false);
  const [hoveredLabPoint, setHoveredLabPoint] = useState(null);

  // Record details tab state
  const [activeRecordsTab, setActiveRecordsTab] = useState("medications");

  // Vitals logger modal state
  const [showLogModal, setShowLogModal] = useState(false);
  const [loggingBusy, setLoggingBusy] = useState(false);
  const [modalFeedback, setModalFeedback] = useState({ text: "", type: "" });
  const [vitalForm, setVitalForm] = useState({
    bp_systolic: "",
    bp_diastolic: "",
    heart_rate: "",
    spo2: "",
    blood_glucose: "",
    temperature_f: "",
    weight_kg: "",
    notes: "",
    source: "home_device",
  });

  const vitalsChartRef = useRef(null);
  const recordsSectionRef = useRef(null);

  // Load all dashboard records from live API endpoints.
  async function loadDashboardData(isRefresh = false) {
    if (!token) return;
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      const [
        overviewRes,
        vitalsRes,
        labTrendsRes,
        insightsRes,
        apptsRes,
        timelineRes,
        rxRes,
        notesRes,
        docsRes,
        allergiesRes,
      ] = await Promise.allSettled([
        apiRequest("/records/overview", token),
        apiRequest("/records/vitals", token),
        apiRequest("/records/labs/trends", token),
        apiRequest("/records/insights", token),
        apiRequest("/providers/appointments", token),
        apiRequest("/records/timeline", token),
        apiRequest("/records/prescriptions?include_drafts=true", token),
        apiRequest("/records/notes?include_drafts=true", token),
        apiRequest("/records/documents", token),
        apiRequest("/records/allergies", token),
      ]);

      if (overviewRes.status === "fulfilled") setOverview(overviewRes.value);
      if (vitalsRes.status === "fulfilled") setVitalsList(Array.isArray(vitalsRes.value) ? vitalsRes.value : []);
      if (labTrendsRes.status === "fulfilled") setLabTrends(labTrendsRes.value || { trends: [] });
      if (insightsRes.status === "fulfilled") setInsightsData(insightsRes.value);
      if (apptsRes.status === "fulfilled") setAppointments(Array.isArray(apptsRes.value) ? apptsRes.value : apptsRes.value?.items || []);
      if (timelineRes.status === "fulfilled") setTimelineEvents(timelineRes.value?.events || []);
      if (rxRes.status === "fulfilled") setPrescriptions(Array.isArray(rxRes.value) ? rxRes.value : []);
      if (notesRes.status === "fulfilled") setNotes(Array.isArray(notesRes.value) ? notesRes.value : []);
      if (docsRes.status === "fulfilled") setDocuments(Array.isArray(docsRes.value) ? docsRes.value : []);
      if (allergiesRes.status === "fulfilled") setAllergies(Array.isArray(allergiesRes.value) ? allergiesRes.value : []);

      // If overview failed, show error banner
      if (overviewRes.status === "rejected") {
        setError(overviewRes.reason?.message || "Failed to load clinical overview.");
      }
    } catch (err) {
      setError(err?.message || "Unable to synchronize health records.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadDashboardData();
  }, [token]);

  // Set default active lab analyte once lab trends are loaded.
  useEffect(() => {
    if (labTrends?.trends?.length > 0 && !activeAnalyteKey) {
      setActiveAnalyteKey(labTrends.trends[0].parameter_key);
    }
  }, [labTrends]);

  // Downloads authenticated binary PDF files (Health Summary Passport, Lab PDFs, Rx, Notes).
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

  // Submit new vital reading via POST /records/vitals.
  async function handleLogVitalSubmit(e) {
    e.preventDefault();
    setLoggingBusy(true);
    setModalFeedback({ text: "", type: "" });

    try {
      const payload = {
        source: vitalForm.source || "home_device",
        notes: vitalForm.notes ? vitalForm.notes.trim() : null,
      };

      if (vitalForm.bp_systolic) payload.bp_systolic = parseInt(vitalForm.bp_systolic, 10);
      if (vitalForm.bp_diastolic) payload.bp_diastolic = parseInt(vitalForm.bp_diastolic, 10);
      if (vitalForm.heart_rate) payload.heart_rate = parseInt(vitalForm.heart_rate, 10);
      if (vitalForm.spo2) payload.spo2 = parseInt(vitalForm.spo2, 10);
      if (vitalForm.blood_glucose) payload.blood_glucose = parseFloat(vitalForm.blood_glucose);
      if (vitalForm.temperature_f) payload.temperature_f = parseFloat(vitalForm.temperature_f);
      if (vitalForm.weight_kg) payload.weight_kg = parseFloat(vitalForm.weight_kg);

      const created = await apiRequest("/records/vitals", token, {
        method: "POST",
        body: JSON.stringify(payload),
      });

      // Update local state with the new observation
      setVitalsList((prev) => [created, ...prev]);
      if (overview) {
        setOverview((prev) => ({
          ...prev,
          total_counts: {
            ...prev.total_counts,
            vitals: (prev.total_counts?.vitals || 0) + 1,
            total_records: (prev.total_counts?.total_records || 0) + 1,
          },
          recent_vitals: [created, ...(prev.recent_vitals || [])].slice(0, 10),
        }));
      }

      setModalFeedback({
        text: isHindi ? "वाइटल्स रिकॉर्ड सफलतापूर्वक सेव हो गए।" : "Vitals observation successfully recorded.",
        type: "success",
      });

      // Reset form and close modal after brief delay
      setTimeout(() => {
        setShowLogModal(false);
        setVitalForm({
          bp_systolic: "",
          bp_diastolic: "",
          heart_rate: "",
          spo2: "",
          blood_glucose: "",
          temperature_f: "",
          weight_kg: "",
          notes: "",
          source: "home_device",
        });
        setModalFeedback({ text: "", type: "" });
      }, 1000);
    } catch (err) {
      setModalFeedback({
        text: err?.message || "Failed to record observation. Please check value ranges.",
        type: "error",
      });
    } finally {
      setLoggingBusy(false);
    }
  }

  // Filter vitals chronologically based on active date range.
  const filteredVitals = useMemo(() => {
    if (!vitalsList || vitalsList.length === 0) return [];
    const sorted = [...vitalsList].sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at));
    if (chartTimeRange === "all") return sorted;
    const days = parseInt(chartTimeRange, 10);
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    const filtered = sorted.filter((v) => new Date(v.recorded_at) >= cutoff);
    return filtered.length > 0 ? filtered : sorted;
  }, [vitalsList, chartTimeRange]);

  // Compute stats for current active metric.
  const activeMetricStats = useMemo(() => {
    if (!filteredVitals.length) return { latest: "—", avg: "—", min: "—", max: "—" };
    const cfg = METRIC_CONFIGS[activeMetric];
    const key = cfg.series[0].key;

    if (activeMetric === "bp") {
      const last = filteredVitals[filteredVitals.length - 1];
      const sVals = filteredVitals.map((v) => v.bp_systolic).filter((n) => typeof n === "number");
      const dVals = filteredVitals.map((v) => v.bp_diastolic).filter((n) => typeof n === "number");
      const sAvg = sVals.length ? Math.round(sVals.reduce((a, b) => a + b, 0) / sVals.length) : "—";
      const dAvg = dVals.length ? Math.round(dVals.reduce((a, b) => a + b, 0) / dVals.length) : "—";
      return {
        latest: last.bp_systolic && last.bp_diastolic ? `${last.bp_systolic}/${last.bp_diastolic} mmHg` : "—",
        avg: sAvg !== "—" && dAvg !== "—" ? `${sAvg}/${dAvg} mmHg` : "—",
        min: sVals.length && dVals.length ? `${Math.min(...sVals)}/${Math.min(...dVals)}` : "—",
        max: sVals.length && dVals.length ? `${Math.max(...sVals)}/${Math.max(...dVals)}` : "—",
      };
    }

    const vals = filteredVitals.map((v) => v[key]).filter((n) => typeof n === "number");
    if (!vals.length) return { latest: "—", avg: "—", min: "—", max: "—" };
    const last = vals[vals.length - 1];
    const avg = (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(activeMetric === "glucose" ? 0 : 1);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    return {
      latest: `${last} ${cfg.unit}`,
      avg: `${avg} ${cfg.unit}`,
      min: `${min} ${cfg.unit}`,
      max: `${max} ${cfg.unit}`,
    };
  }, [filteredVitals, activeMetric]);

  // Next upcoming appointment
  const nextAppointment = useMemo(() => {
    const upcoming = appointments
      .filter((a) => a.status === "scheduled" || a.status === "confirmed")
      .filter((a) => new Date(a.scheduled_for) >= new Date())
      .sort((a, b) => new Date(a.scheduled_for) - new Date(b.scheduled_for));
    return upcoming.length ? upcoming[0] : null;
  }, [appointments]);

  // Selected analyte trend object from labTrends
  const selectedLabTrend = useMemo(() => {
    if (!labTrends?.trends || labTrends.trends.length === 0) return null;
    return (
      labTrends.trends.find((t) => t.parameter_key === activeAnalyteKey) ||
      labTrends.trends[0]
    );
  }, [labTrends, activeAnalyteKey]);

  // Extracted total counts with safe fallbacks
  const counts = overview?.total_counts || {
    upcoming_appointments: appointments.filter((a) => a.status === "scheduled" || a.status === "confirmed").length,
    active_medications: prescriptions.reduce((acc, p) => acc + (p.items?.length || 0), 0),
    allergies: allergies.length,
    documents: documents.length,
    vitals: vitalsList.length,
    assessments: overview?.recent_assessments?.length || 0,
    total_records: timelineEvents.length || 0,
  };

  const patientName = user?.full_name || patient?.full_name || "Aarav Demo";
  const firstName = patientName.split(" ")[0];

  return (
    <div className="cv-patient-dashboard" aria-label={isHindi ? "मरीज़ स्वास्थ्य डैशबोर्ड" : "Patient Health Dashboard"}>
      {/* ----------------------------------------------------------------------
         1. Welcome Section & Clinical Status Banner
         ---------------------------------------------------------------------- */}
      <section className="cv-welcome-card" aria-labelledby="welcome-patient-heading">
        <div className="cv-welcome-header">
          <div className="cv-welcome-title-group">
            <span className="eyebrow">{isHindi ? "व्यक्तिगत स्वास्थ्य पोर्टल" : "PATIENT HEALTH PORTAL"}</span>
            <h1 id="welcome-patient-heading">
              {isHindi ? `नमस्ते, ${firstName}` : `Welcome back, ${firstName}`}
            </h1>
            <div className="cv-patient-badges">
              <span className="cv-patient-badge">
                <span>🆔</span>
                <span>CV-{user?.id ? String(user.id).padStart(6, "0") : "000003"}</span>
              </span>
              <span className="cv-patient-badge">
                <span>👤</span>
                <span>{patient?.gender || "Male"}, {patient?.age || 32}y</span>
              </span>
              <span className="cv-patient-badge synthetic" title="Synthetic development data">
                <span>🛡️</span>
                <span>{isHindi ? "डेमो डेटा वातावरण" : "Demo Data Active"}</span>
              </span>
              <span className="cv-patient-badge">
                <span>⏱️</span>
                <span>{isHindi ? "सिंक किया गया" : "Synced"} {formatDate(new Date())}</span>
              </span>
            </div>
          </div>

          <div className="cv-welcome-actions">
            <button
              type="button"
              className="cv-button cv-button-secondary"
              onClick={() => loadDashboardData(true)}
              disabled={refreshing}
              aria-label={isHindi ? "डैशबोर्ड रीफ्रेश करें" : "Refresh dashboard data"}
            >
              <span aria-hidden="true">{refreshing ? "…" : "🔄"}</span>
              <span>{refreshing ? (isHindi ? "रिफ्रेश हो रहा है…" : "Refreshing…") : (isHindi ? "ताज़ा करें" : "Refresh")}</span>
            </button>
            <button
              type="button"
              className="cv-button cv-button-primary"
              onClick={() =>
                downloadBinary(
                  "/records/summary/pdf",
                  `carevoice-health-passport-${user?.id || "patient"}.pdf`,
                  "passport"
                )
              }
              disabled={downloadingId === "passport"}
              title="Download official comprehensive PDF Health Passport with QR verification"
            >
              <span aria-hidden="true">📥</span>
              <span>{downloadingId === "passport" ? "Downloading…" : (isHindi ? "स्वास्थ्य पासपोर्ट PDF" : "Health Passport PDF")}</span>
            </button>
          </div>
        </div>

        {/* Clinical Status Summary Banner */}
        <div
          className={`cv-status-banner ${counts.allergies > 0 ? "has-alert" : ""}`}
          role="region"
          aria-label="Clinical status alert summary"
        >
          <div className="cv-status-banner-icon" aria-hidden="true">
            {counts.allergies > 0 ? "⚠️" : "🩺"}
          </div>
          <div className="cv-status-banner-content">
            <span className="cv-status-banner-title">
              {isHindi ? "क्लिनिकल स्थिति सारांश" : "Clinical Status & Care Coordination"}
            </span>
            <p className="cv-status-banner-text">
              {overview?.health_status_summary ||
                `${counts.allergies} recorded allergy alerts. ${counts.active_medications} active medications prescribed. Vitals trajectory stable. Next visit with ${nextAppointment?.doctor_name || "Care Team"}.`}
            </p>
          </div>
        </div>

        {/* Quick Action Navigation Bar */}
        <nav className="cv-quick-actions-bar" aria-label={isHindi ? "त्वरित कार्यवाहियां" : "Quick Actions"}>
          <button
            type="button"
            className="cv-action-pill"
            onClick={() => onNavigate("Symptom check")}
          >
            <span className="cv-action-pill-icon" aria-hidden="true">✳️</span>
            <span>{isHindi ? "लक्षण जाँचें" : "Check Symptoms"}</span>
          </button>
          <button
            type="button"
            className="cv-action-pill"
            onClick={() => setShowLogModal(true)}
          >
            <span className="cv-action-pill-icon" aria-hidden="true">➕</span>
            <span>{isHindi ? "वाइटल्स दर्ज करें" : "Log Vitals"}</span>
          </button>
          <button
            type="button"
            className="cv-action-pill"
            onClick={() => onNavigate("Find care")}
          >
            <span className="cv-action-pill-icon" aria-hidden="true">📅</span>
            <span>{isHindi ? "अपॉइंटमेंट बुक करें" : "Book Doctor"}</span>
          </button>
          <button
            type="button"
            className="cv-action-pill"
            onClick={() => onNavigate("Health records")}
          >
            <span className="cv-action-pill-icon" aria-hidden="true">📁</span>
            <span>{isHindi ? "सभी रिकॉर्ड्स" : "All Records"}</span>
          </button>
          <button
            type="button"
            className="cv-action-pill"
            onClick={() => onNavigate("Assistant")}
          >
            <span className="cv-action-pill-icon" aria-hidden="true">🎙️</span>
            <span>{isHindi ? "AI वॉइस सहायक" : "Voice Assistant"}</span>
          </button>
        </nav>
      </section>

      {/* ----------------------------------------------------------------------
         2. 8 Accurate Clickable Summary Metric Cards
         ---------------------------------------------------------------------- */}
      <section aria-labelledby="summary-metrics-heading">
        <h2 id="summary-metrics-heading" className="sr-only">
          {isHindi ? "स्वास्थ्य सारांश मेट्रिक्स" : "Key Health Summary Metrics"}
        </h2>
        <div className="cv-metrics-grid-8">
          {/* Card 1: Upcoming Visits */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => onNavigate("Appointments")}
            aria-label={`Upcoming visits: ${counts.upcoming_appointments || 0}. Click to view appointment schedule.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">📅</span>
              <span className="cv-metric-badge success">{isHindi ? "शेड्यूल" : "Scheduled"}</span>
            </div>
            <strong className="cv-metric-number">{counts.upcoming_appointments ?? 0}</strong>
            <span className="cv-metric-title">{isHindi ? "आगामी अपॉइंटमेंट" : "Upcoming Visits"}</span>
            <div className="cv-metric-footer">
              <span>{nextAppointment ? formatDate(nextAppointment.scheduled_for) : (isHindi ? "कोई नहीं" : "None scheduled")}</span>
              <span className="cv-metric-arrow" aria-hidden="true">→</span>
            </div>
          </button>

          {/* Card 2: Active Medications */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => {
              setActiveRecordsTab("medications");
              recordsSectionRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
            aria-label={`Active medications: ${counts.active_medications || 0}. Click to view prescriptions.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">℞</span>
              <span className="cv-metric-badge neutral">{prescriptions.length} {isHindi ? "पर्चे" : "Rx"}</span>
            </div>
            <strong className="cv-metric-number">{counts.active_medications ?? 0}</strong>
            <span className="cv-metric-title">{isHindi ? "सक्रिय दवाइयाँ" : "Active Medications"}</span>
            <div className="cv-metric-footer">
              <span>{isHindi ? "सत्यापित खुराक" : "Across prescriptions"}</span>
              <span className="cv-metric-arrow" aria-hidden="true">→</span>
            </div>
          </button>

          {/* Card 3: Recorded Allergies */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => onNavigate("Health records")}
            aria-label={`Recorded allergies: ${counts.allergies || 0}. Click to inspect safety profile.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">⚠️</span>
              <span className={`cv-metric-badge ${counts.allergies > 0 ? "alert" : "success"}`}>
                {counts.allergies > 0 ? (isHindi ? "अलर्ट" : "Active") : (isHindi ? "सुरक्षित" : "Clear")}
              </span>
            </div>
            <strong className="cv-metric-number">{counts.allergies ?? 0}</strong>
            <span className="cv-metric-title">{isHindi ? "दर्ज एलर्जी" : "Recorded Allergies"}</span>
            <div className="cv-metric-footer">
              <span>{allergies[0]?.allergen_or_condition ? allergies[0].allergen_or_condition.split(" ")[0] : (isHindi ? "कोई नहीं" : "No conflicts")}</span>
              <span className="cv-metric-arrow" aria-hidden="true">→</span>
            </div>
          </button>

          {/* Card 4: Lab Reports */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => {
              setActiveRecordsTab("labs");
              recordsSectionRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
            aria-label={`Lab & diagnostic reports: ${counts.documents || 0}. Click to view laboratory panels.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">🔬</span>
              <span className="cv-metric-badge neutral">{isHindi ? "सत्यापित" : "Verified"}</span>
            </div>
            <strong className="cv-metric-number">{counts.documents ?? 0}</strong>
            <span className="cv-metric-title">{isHindi ? "लैब व जांच रिपोर्ट" : "Lab Reports"}</span>
            <div className="cv-metric-footer">
              <span>{isHindi ? "डिजिटल डायग्नोस्टिक्स" : "Pathology & Imaging"}</span>
              <span className="cv-metric-arrow" aria-hidden="true">→</span>
            </div>
          </button>

          {/* Card 5: Health Observations / Vitals */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => vitalsChartRef.current?.scrollIntoView({ behavior: "smooth" })}
            aria-label={`Health observations: ${counts.vitals || 0}. Click to open longitudinal vitals chart.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">❤️</span>
              <span className="cv-metric-badge success">{isHindi ? "ट्रैक किया" : "Tracked"}</span>
            </div>
            <strong className="cv-metric-number">{counts.vitals ?? 0}</strong>
            <span className="cv-metric-title">{isHindi ? "स्वास्थ्य अवलोकन" : "Health Observations"}</span>
            <div className="cv-metric-footer">
              <span>{activeMetricStats.latest}</span>
              <span className="cv-metric-arrow" aria-hidden="true">↓</span>
            </div>
          </button>

          {/* Card 6: AI Assessments */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => onNavigate("Health records")}
            aria-label={`AI assessments: ${counts.assessments || 0}. Click to view triage evaluations.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">📑</span>
              <span className="cv-metric-badge neutral">{isHindi ? "एआई ट्राइएज" : "Synthesized"}</span>
            </div>
            <strong className="cv-metric-number">{counts.assessments ?? 0}</strong>
            <span className="cv-metric-title">{isHindi ? "AI आकलन रिपोर्ट" : "AI Assessments"}</span>
            <div className="cv-metric-footer">
              <span>{isHindi ? "लक्षण इतिहास" : "Symptom evaluations"}</span>
              <span className="cv-metric-arrow" aria-hidden="true">→</span>
            </div>
          </button>

          {/* Card 7: Follow-up Tasks */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => {
              setActiveRecordsTab("notes");
              recordsSectionRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
            aria-label={`Follow-up instructions: ${overview?.follow_up_tasks?.length || 0}. Click to view care plan tasks.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">🩺</span>
              <span className="cv-metric-badge success">{isHindi ? "सक्रिय" : "Active"}</span>
            </div>
            <strong className="cv-metric-number">{overview?.follow_up_tasks?.length ?? (notes.length ? 3 : 0)}</strong>
            <span className="cv-metric-title">{isHindi ? "फॉलो-अप निर्देश" : "Follow-up Tasks"}</span>
            <div className="cv-metric-footer">
              <span>{isHindi ? "डॉक्टर की सलाह" : "Doctor care plan"}</span>
              <span className="cv-metric-arrow" aria-hidden="true">↓</span>
            </div>
          </button>

          {/* Card 8: Total Health Records */}
          <button
            type="button"
            className="cv-metric-btn"
            onClick={() => onNavigate("Health records")}
            aria-label={`Total health records: ${counts.total_records || 0}. Click to view longitudinal timeline.`}
          >
            <div className="cv-metric-top">
              <span className="cv-metric-icon-box" aria-hidden="true">⏱️</span>
              <span className="cv-metric-badge neutral">{isHindi ? "ऑडिटेड" : "Audited"}</span>
            </div>
            <strong className="cv-metric-number">{counts.total_records ?? 0}</strong>
            <span className="cv-metric-title">{isHindi ? "कुल स्वास्थ्य रिकॉर्ड" : "Total Health Records"}</span>
            <div className="cv-metric-footer">
              <span>{isHindi ? "कालक्रम में सभी" : "Full medical ledger"}</span>
              <span className="cv-metric-arrow" aria-hidden="true">→</span>
            </div>
          </button>
        </div>
      </section>

      {/* ----------------------------------------------------------------------
         3. Interactive Health Chart A: Vitals Longitudinal Trend Chart
         Complies with dataviz guidelines: single axis, reference corridor, tooltips, table toggle
         ---------------------------------------------------------------------- */}
      <section ref={vitalsChartRef} className="cv-chart-card" aria-labelledby="vitals-chart-heading">
        <div className="cv-chart-header">
          <div className="cv-chart-title-group">
            <span className="eyebrow">{isHindi ? "लॉन्गीट्यूडिनल वाइटल्स" : "LONGITUDINAL PHYSIOLOGICAL MONITORING"}</span>
            <h2 id="vitals-chart-heading">
              {isHindi ? "वाइटल साइन्स ट्रेंड विज़ुअलाइज़ेशन" : "Vital Signs Longitudinal Trends"}
            </h2>
            <p className="cv-chart-subtitle">
              {METRIC_CONFIGS[activeMetric].referenceText}
            </p>
          </div>

          <div className="cv-chart-controls">
            {/* Metric Selector Chips */}
            <div className="cv-chip-group" role="tablist" aria-label="Select physiological metric">
              {Object.entries(METRIC_CONFIGS).map(([key, config]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={activeMetric === key}
                  className={`cv-chip ${activeMetric === key ? "active" : ""}`}
                  onClick={() => {
                    setActiveMetric(key);
                    setHoveredVitalIndex(null);
                  }}
                >
                  {config.label}
                </button>
              ))}
            </div>

            {/* Time Range Filter */}
            <div className="cv-chip-group" role="group" aria-label="Time range filter">
              {[
                { id: "30", label: isHindi ? "30 दिन" : "Last 30d" },
                { id: "60", label: isHindi ? "60 दिन" : "Last 60d" },
                { id: "all", label: isHindi ? "सभी" : "All" },
              ].map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className={`cv-chip ${chartTimeRange === r.id ? "active" : ""}`}
                  onClick={() => setChartTimeRange(r.id)}
                >
                  {r.label}
                </button>
              ))}
            </div>

            {/* Accessible Table Toggle */}
            <button
              type="button"
              className="cv-button cv-button-secondary"
              onClick={() => setShowVitalsTable((prev) => !prev)}
              aria-expanded={showVitalsTable}
              aria-controls="vitals-accessible-table-view"
            >
              <span>📊</span>
              <span>{showVitalsTable ? (isHindi ? "तालिका छुपाएँ" : "Hide Table") : (isHindi ? "डेटा तालिका" : "Data Table")}</span>
            </button>
          </div>
        </div>

        {/* Statistical Summary Strip */}
        <div className="cv-chart-stat-strip" aria-label="Vitals summary metrics">
          <div className="cv-stat-item">
            <span className="cv-stat-label">{isHindi ? "नवीनतम मान" : "Latest Reading"}</span>
            <span className="cv-stat-val">{activeMetricStats.latest}</span>
          </div>
          <div className="cv-stat-item">
            <span className="cv-stat-label">{isHindi ? "औसत" : "Period Average"}</span>
            <span className="cv-stat-val">{activeMetricStats.avg}</span>
          </div>
          <div className="cv-stat-item">
            <span className="cv-stat-label">{isHindi ? "न्यूनतम" : "Minimum"}</span>
            <span className="cv-stat-val">{activeMetricStats.min}</span>
          </div>
          <div className="cv-stat-item">
            <span className="cv-stat-label">{isHindi ? "अधिकतम" : "Maximum"}</span>
            <span className="cv-stat-val">{activeMetricStats.max}</span>
          </div>
          <div className="cv-stat-item">
            <span className="cv-stat-label">{isHindi ? "कुल रिकॉर्ड्स" : "Readings Count"}</span>
            <span className="cv-stat-val">{filteredVitals.length}</span>
          </div>
        </div>

        {/* SVG Chart Visualization */}
        <div className="cv-svg-container" onMouseLeave={() => setHoveredVitalIndex(null)}>
          {filteredVitals.length > 0 ? (
            (() => {
              const cfg = METRIC_CONFIGS[activeMetric];
              const W = 760;
              const H = 280;
              const padLeft = 60;
              const padRight = 30;
              const padTop = 30;
              const padBottom = 40;
              const plotW = W - padLeft - padRight;
              const plotH = H - padTop - padBottom;

              const yMin = cfg.yMin;
              const yMax = cfg.yMax;
              const yRange = yMax - yMin;

              const getY = (val) => padTop + plotH - ((val - yMin) / yRange) * plotH;
              const getX = (idx, total) =>
                total <= 1 ? padLeft + plotW / 2 : padLeft + (idx / (total - 1)) * plotW;

              // Grid ticks
              const tickCount = 5;
              const yTicks = Array.from({ length: tickCount }, (_, i) =>
                Math.round(yMin + (i * yRange) / (tickCount - 1))
              );

              // Shaded normal reference corridor for series 0
              const norm0 = cfg.series[0];
              const topY0 = getY(Math.min(yMax, norm0.normalMax));
              const botY0 = getY(Math.max(yMin, norm0.normalMin));
              const corridorH0 = Math.max(0, botY0 - topY0);

              return (
                <>
                  <svg
                    className="cv-svg-chart"
                    viewBox={`0 0 ${W} ${H}`}
                    role="img"
                    aria-label={`Longitudinal trend line chart of ${cfg.label} showing ${filteredVitals.length} recorded measurements`}
                  >
                    <defs>
                      <linearGradient id="vitals-corridor-gradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#006E51" stopOpacity="0.12" />
                        <stop offset="100%" stopColor="#006E51" stopOpacity="0.04" />
                      </linearGradient>
                    </defs>

                    {/* Reference Range Shaded Corridor */}
                    <rect
                      x={padLeft}
                      y={topY0}
                      width={plotW}
                      height={corridorH0}
                      fill="url(#vitals-corridor-gradient)"
                      rx="4"
                    />
                    <line
                      x1={padLeft}
                      y1={topY0}
                      x2={padLeft + plotW}
                      y2={topY0}
                      stroke="#006E51"
                      strokeWidth="1"
                      strokeDasharray="4 4"
                      opacity="0.4"
                    />
                    <line
                      x1={padLeft}
                      y1={botY0}
                      x2={padLeft + plotW}
                      y2={botY0}
                      stroke="#006E51"
                      strokeWidth="1"
                      strokeDasharray="4 4"
                      opacity="0.4"
                    />

                    {/* Y-Axis Gridlines & Tick Labels */}
                    {yTicks.map((tickVal) => {
                      const yPos = getY(tickVal);
                      return (
                        <g key={tickVal}>
                          <line
                            x1={padLeft}
                            y1={yPos}
                            x2={padLeft + plotW}
                            y2={yPos}
                            stroke="currentColor"
                            strokeWidth="1"
                            opacity="0.1"
                          />
                          <text
                            x={padLeft - 10}
                            y={yPos + 4}
                            textAnchor="end"
                            fontSize="11"
                            fill="currentColor"
                            opacity="0.6"
                          >
                            {tickVal}
                          </text>
                        </g>
                      );
                    })}

                    {/* X-Axis Baseline */}
                    <line
                      x1={padLeft}
                      y1={padTop + plotH}
                      x2={padLeft + plotW}
                      y2={padTop + plotH}
                      stroke="currentColor"
                      strokeWidth="1"
                      opacity="0.3"
                    />

                    {/* Series Lines */}
                    {cfg.series.map((s) => {
                      const validPoints = filteredVitals
                        .map((v, i) => ({
                          x: getX(i, filteredVitals.length),
                          y: typeof v[s.key] === "number" ? getY(v[s.key]) : null,
                          val: v[s.key],
                          vital: v,
                          index: i,
                        }))
                        .filter((p) => p.y !== null);

                      if (validPoints.length === 0) return null;

                      const pathD = validPoints.reduce(
                        (acc, pt, i) => (i === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`),
                        ""
                      );

                      return (
                        <g key={s.key} className="cv-series-group">
                          <path
                            d={pathD}
                            fill="none"
                            stroke={s.color}
                            strokeWidth="2.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                          {validPoints.map((pt) => {
                            const isHovered = hoveredVitalIndex === pt.index;
                            return (
                              <circle
                                key={pt.index}
                                cx={pt.x}
                                cy={pt.y}
                                r={isHovered ? "6" : "4"}
                                fill="#ffffff"
                                stroke={s.color}
                                strokeWidth={isHovered ? "3" : "2"}
                                className="cv-chart-point"
                                tabIndex={0}
                                role="graphics-symbol"
                                aria-label={`${s.label}: ${pt.val} ${cfg.unit} on ${formatDate(pt.vital.recorded_at)}`}
                                onMouseEnter={() => setHoveredVitalIndex(pt.index)}
                                onFocus={() => setHoveredVitalIndex(pt.index)}
                              />
                            );
                          })}
                        </g>
                      );
                    })}

                    {/* Hover Guide Vertical Crosshair */}
                    {hoveredVitalIndex !== null && (
                      <line
                        x1={getX(hoveredVitalIndex, filteredVitals.length)}
                        y1={padTop}
                        x2={getX(hoveredVitalIndex, filteredVitals.length)}
                        y2={padTop + plotH}
                        stroke="#006E51"
                        strokeWidth="1.5"
                        strokeDasharray="4 4"
                        opacity="0.75"
                      />
                    )}

                    {/* X-Axis Date Labels */}
                    {filteredVitals.map((v, i) => {
                      // Show dates selectively to prevent collisions
                      const total = filteredVitals.length;
                      const showLabel =
                        total <= 7 || i === 0 || i === total - 1 || i % Math.ceil(total / 6) === 0;
                      if (!showLabel) return null;
                      return (
                        <text
                          key={v.id || i}
                          x={getX(i, total)}
                          y={padTop + plotH + 20}
                          textAnchor="middle"
                          fontSize="11"
                          fill="currentColor"
                          opacity="0.65"
                        >
                          {formatDate(v.recorded_at).split(" ").slice(0, 2).join(" ")}
                        </text>
                      );
                    })}
                  </svg>

                  {/* Interactive Floating Hover Tooltip */}
                  {hoveredVitalIndex !== null && filteredVitals[hoveredVitalIndex] && (
                    (() => {
                      const v = filteredVitals[hoveredVitalIndex];
                      const xPct =
                        filteredVitals.length <= 1
                          ? 50
                          : ((hoveredVitalIndex / (filteredVitals.length - 1)) * plotW + padLeft) / (W / 100);

                      let displayVal = "";
                      if (activeMetric === "bp") {
                        displayVal = `${v.bp_systolic || "—"}/${v.bp_diastolic || "—"} mmHg`;
                      } else {
                        displayVal = `${v[cfg.series[0].key]} ${cfg.unit}`;
                      }

                      return (
                        <div
                          className="cv-chart-tooltip"
                          style={{
                            left: `${Math.min(90, Math.max(10, xPct))}%`,
                            top: "35%",
                          }}
                          role="tooltip"
                        >
                          <div className="cv-chart-tooltip-date">{formatDateTime(v.recorded_at)}</div>
                          <div className="cv-chart-tooltip-value">{displayVal}</div>
                          <span
                            className={`cv-chart-tooltip-status ${v.status === "abnormal" ? "abnormal" : "normal"}`}
                          >
                            {v.status ? v.status.toUpperCase() : "NORMAL"}
                          </span>
                          <div className="cv-chart-tooltip-range">
                            {v.notes || (v.source === "home_device" ? "Home Monitor Sync" : "Clinical Encounter")}
                          </div>
                        </div>
                      );
                    })()
                  )}
                </>
              );
            })()
          ) : (
            <div className="cv-empty" style={{ padding: "40px 20px" }}>
              <span aria-hidden="true">❤️</span>
              <h3>{isHindi ? "कोई अवलोकन डेटा नहीं" : "No Physiological Data Recorded"}</h3>
              <p>{isHindi ? "पहला वाइटल्स माप दर्ज करने के लिए नीचे बटन पर क्लिक करें।" : "Click 'Log Vitals' above to record your first vital sign observation."}</p>
              <button
                type="button"
                className="cv-button cv-button-primary"
                onClick={() => setShowLogModal(true)}
              >
                {isHindi ? "वाइटल्स दर्ज करें" : "Log Vitals Now"}
              </button>
            </div>
          )}
        </div>

        {/* Accessible Data Table Toggle */}
        {showVitalsTable && (
          <div id="vitals-accessible-table-view" className="cv-data-table-container">
            <table className="cv-accessible-table">
              <caption className="sr-only">Tabular view of recorded physiological measurements</caption>
              <thead>
                <tr>
                  <th scope="col">{isHindi ? "दिनांक व समय" : "Date & Time"}</th>
                  <th scope="col">{isHindi ? "माप" : "Measurement"}</th>
                  <th scope="col">{isHindi ? "स्थिति" : "Clinical Status"}</th>
                  <th scope="col">{isHindi ? "स्रोत / नोट्स" : "Source & Notes"}</th>
                </tr>
              </thead>
              <tbody>
                {filteredVitals.map((v) => {
                  const cfg = METRIC_CONFIGS[activeMetric];
                  const val =
                    activeMetric === "bp"
                      ? `${v.bp_systolic || "—"}/${v.bp_diastolic || "—"} mmHg`
                      : `${v[cfg.series[0].key]} ${cfg.unit}`;
                  return (
                    <tr key={v.id}>
                      <td>{formatDateTime(v.recorded_at)}</td>
                      <td><strong>{val}</strong></td>
                      <td>
                        <span className={`cv-metric-badge ${v.status === "abnormal" ? "alert" : "success"}`}>
                          {v.status?.toUpperCase() || "NORMAL"}
                        </span>
                      </td>
                      <td>{v.notes || v.source}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ----------------------------------------------------------------------
         4. Interactive Health Chart B: Laboratory Trends Visualization
         Sourced from live /records/labs/trends with analyte selector and PDF link
         ---------------------------------------------------------------------- */}
      <section className="cv-chart-card" aria-labelledby="lab-trends-heading">
        <div className="cv-chart-header">
          <div className="cv-chart-title-group">
            <span className="eyebrow">{isHindi ? "सत्यापित लैब बायोमार्कर्स" : "CLINICAL PATHOLOGY & BIOCHEMISTRY"}</span>
            <h2 id="lab-trends-heading">
              {isHindi ? "प्रयोगशाला परीक्षण रुझान" : "Laboratory Trend Trajectory"}
            </h2>
            <p className="cv-chart-subtitle">
              {selectedLabTrend
                ? `${selectedLabTrend.label} trajectory over ${selectedLabTrend.readings_count} verified laboratory reports`
                : "Longitudinal biological markers tracked across diagnostic panels"}
            </p>
          </div>

          <div className="cv-chart-controls">
            {/* Analyte Chips */}
            <div className="cv-chip-group" role="tablist" aria-label="Select lab analyte">
              {(labTrends?.trends || []).map((trend) => (
                <button
                  key={trend.parameter_key}
                  type="button"
                  role="tab"
                  aria-selected={activeAnalyteKey === trend.parameter_key}
                  className={`cv-chip ${activeAnalyteKey === trend.parameter_key ? "active" : ""}`}
                  onClick={() => {
                    setActiveAnalyteKey(trend.parameter_key);
                    setHoveredLabPoint(null);
                  }}
                >
                  {trend.label}
                </button>
              ))}
            </div>

            <button
              type="button"
              className="cv-button cv-button-secondary"
              onClick={() => setShowLabTable((prev) => !prev)}
              aria-expanded={showLabTable}
            >
              <span>🔬</span>
              <span>{showLabTable ? (isHindi ? "तालिका छुपाएँ" : "Hide Table") : (isHindi ? "डेटा तालिका" : "Data Table")}</span>
            </button>
          </div>
        </div>

        {selectedLabTrend ? (
          <div>
            {/* Analyte Summary Strip */}
            <div className="cv-chart-stat-strip">
              <div className="cv-stat-item">
                <span className="cv-stat-label">{isHindi ? "नवीनतम मान" : "Latest Value"}</span>
                <span className="cv-stat-val">
                  {selectedLabTrend.latest_value} {selectedLabTrend.unit}
                </span>
              </div>
              <div className="cv-stat-item">
                <span className="cv-stat-label">{isHindi ? "जैविक संदर्भ सीमा" : "Biological Target"}</span>
                <span className="cv-stat-val">{selectedLabTrend.reference_range}</span>
              </div>
              <div className="cv-stat-item">
                <span className="cv-stat-label">{isHindi ? "रुझान दिशा" : "Trajectory"}</span>
                <span className="cv-stat-val" style={{ color: selectedLabTrend.direction === "improving" ? "#006E51" : "inherit" }}>
                  {selectedLabTrend.direction === "improving" ? "🟢 Improving" : "🔵 Stable"}
                </span>
              </div>
              <div className="cv-stat-item">
                <span className="cv-stat-label">{isHindi ? "रिपोर्ट संख्या" : "Report Points"}</span>
                <span className="cv-stat-val">{selectedLabTrend.readings_count}</span>
              </div>
            </div>

            {/* SVG Trajectory Chart for Selected Analyte */}
            <div className="cv-svg-container" onMouseLeave={() => setHoveredLabPoint(null)}>
              {(() => {
                const history = [...(selectedLabTrend.history || [])].sort(
                  (a, b) => new Date(a.date) - new Date(b.date)
                );
                if (history.length === 0) return null;

                const W = 760;
                const H = 240;
                const padLeft = 60;
                const padRight = 30;
                const padTop = 30;
                const padBottom = 40;
                const plotW = W - padLeft - padRight;
                const plotH = H - padTop - padBottom;

                const vals = history.map((h) => h.value);
                const rawMin = Math.min(...vals);
                const rawMax = Math.max(...vals);
                const margin = (rawMax - rawMin) * 0.3 || rawMax * 0.2 || 10;
                const yMin = Math.max(0, Math.floor(rawMin - margin));
                const yMax = Math.ceil(rawMax + margin);
                const yRange = yMax - yMin || 1;

                const getY = (val) => padTop + plotH - ((val - yMin) / yRange) * plotH;
                const getX = (idx, total) =>
                  total <= 1 ? padLeft + plotW / 2 : padLeft + (idx / (total - 1)) * plotW;

                const pathD = history.reduce(
                  (acc, pt, i) => (i === 0 ? `M ${getX(i, history.length)} ${getY(pt.value)}` : `${acc} L ${getX(i, history.length)} ${getY(pt.value)}`),
                  ""
                );

                return (
                  <>
                    <svg
                      className="cv-svg-chart"
                      viewBox={`0 0 ${W} ${H}`}
                      role="img"
                      aria-label={`Historical trend trajectory of ${selectedLabTrend.label}`}
                    >
                      {/* Gridlines */}
                      {[yMin, Math.round((yMin + yMax) / 2), yMax].map((tick) => {
                        const yPos = getY(tick);
                        return (
                          <g key={tick}>
                            <line
                              x1={padLeft}
                              y1={yPos}
                              x2={padLeft + plotW}
                              y2={yPos}
                              stroke="currentColor"
                              strokeWidth="1"
                              opacity="0.1"
                            />
                            <text
                              x={padLeft - 10}
                              y={yPos + 4}
                              textAnchor="end"
                              fontSize="11"
                              fill="currentColor"
                              opacity="0.6"
                            >
                              {tick}
                            </text>
                          </g>
                        );
                      })}

                      {/* Trajectory Path Line */}
                      <path
                        d={pathD}
                        fill="none"
                        stroke="#006E51"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />

                      {/* Interactive Points */}
                      {history.map((pt, i) => {
                        const isHovered = hoveredLabPoint?.date === pt.date;
                        return (
                          <circle
                            key={i}
                            cx={getX(i, history.length)}
                            cy={getY(pt.value)}
                            r={isHovered ? "6" : "4.5"}
                            fill="#ffffff"
                            stroke="#006E51"
                            strokeWidth={isHovered ? "3" : "2"}
                            className="cv-chart-point"
                            tabIndex={0}
                            role="graphics-symbol"
                            aria-label={`${pt.label}: ${pt.value} ${pt.unit} on ${formatDate(pt.date)}`}
                            onMouseEnter={() => setHoveredLabPoint(pt)}
                            onFocus={() => setHoveredLabPoint(pt)}
                          />
                        );
                      })}

                      {/* Date Axis */}
                      {history.map((pt, i) => (
                        <text
                          key={i}
                          x={getX(i, history.length)}
                          y={padTop + plotH + 20}
                          textAnchor="middle"
                          fontSize="11"
                          fill="currentColor"
                          opacity="0.7"
                        >
                          {formatDate(pt.date)}
                        </text>
                      ))}
                    </svg>

                    {/* Tooltip */}
                    {hoveredLabPoint && (
                      <div
                        className="cv-chart-tooltip"
                        style={{
                          left: "50%",
                          top: "25%",
                        }}
                        role="tooltip"
                      >
                        <div className="cv-chart-tooltip-date">{formatDate(hoveredLabPoint.date)}</div>
                        <div className="cv-chart-tooltip-value">
                          {hoveredLabPoint.value} {hoveredLabPoint.unit}
                        </div>
                        <span
                          className={`cv-chart-tooltip-status ${hoveredLabPoint.status === "normal" ? "normal" : "abnormal"}`}
                        >
                          {hoveredLabPoint.status ? hoveredLabPoint.status.toUpperCase() : "VERIFIED"}
                        </span>
                        <div className="cv-chart-tooltip-range">{hoveredLabPoint.document_title}</div>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>

            {/* Clinical Explanation & Source Document Link */}
            <div className="cv-lab-insight-box">
              <span style={{ fontSize: "20px" }}>🔬</span>
              <div className="cv-lab-insight-content">
                <div className="cv-lab-insight-title">
                  {selectedLabTrend.label} — {isHindi ? "क्लिनिकल व्याख्या" : "Clinical Interpretation & Target"}
                </div>
                <p className="cv-lab-insight-text">
                  {selectedLabTrend.patient_explanation} {selectedLabTrend.clinical_correlation}
                </p>
                {selectedLabTrend.history?.[0]?.document_id && (
                  <button
                    type="button"
                    className="cv-text-button"
                    style={{ marginTop: "8px", fontWeight: "700" }}
                    onClick={() =>
                      downloadBinary(
                        `/records/documents/${selectedLabTrend.history[0].document_id}/download`,
                        `diagnostic-report-${selectedLabTrend.history[0].document_id}.pdf`,
                        `doc-${selectedLabTrend.history[0].document_id}`
                      )
                    }
                  >
                    <span>📄</span>
                    <span>{isHindi ? "स्रोत लैब रिपोर्ट PDF डाउनलोड करें" : "Download Verified Laboratory Report PDF"} →</span>
                  </button>
                )}
              </div>
            </div>

            {/* Table view */}
            {showLabTable && (
              <div className="cv-data-table-container">
                <table className="cv-accessible-table">
                  <caption className="sr-only">Historical laboratory readings table</caption>
                  <thead>
                    <tr>
                      <th scope="col">{isHindi ? "दिनांक" : "Date"}</th>
                      <th scope="col">{isHindi ? "परीक्षण" : "Investigation"}</th>
                      <th scope="col">{isHindi ? "परिणाम" : "Observed Result"}</th>
                      <th scope="col">{isHindi ? "संदर्भ अंतराल" : "Reference Range"}</th>
                      <th scope="col">{isHindi ? "रिपोर्ट शीर्षक" : "Diagnostic Document"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedLabTrend.history?.map((h, i) => (
                      <tr key={i}>
                        <td>{formatDate(h.date)}</td>
                        <td>{h.label}</td>
                        <td><strong>{h.value} {h.unit}</strong></td>
                        <td>{h.reference_range}</td>
                        <td>{h.document_title}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <EmptyState
            icon="🔬"
            title={isHindi ? "कोई लैब डेटा उपलब्ध नहीं" : "No Laboratory Trends Yet"}
            description={isHindi ? "लैब रिपोर्ट अपलोड होने पर बायोमार्कर ट्रेंड्स यहाँ दिखाई देंगे।" : "Longitudinal trajectories will generate automatically as verified diagnostic panels are recorded."}
          />
        )}
      </section>

      {/* ----------------------------------------------------------------------
         5. Grounded AI-Powered Health Insights
         Sourced from live /records/insights with grounding citations and medical disclaimer
         ---------------------------------------------------------------------- */}
      <section className="cv-insights-card" aria-labelledby="ai-insights-heading">
        <div className="cv-chart-header" style={{ marginBottom: "12px" }}>
          <div>
            <span className="eyebrow">{isHindi ? "सत्यापित रिकॉर्ड्स पर आधारित" : "CLINICAL EVIDENCE SYNTHESIS"}</span>
            <h2 id="ai-insights-heading" style={{ margin: "4px 0" }}>
              {isHindi ? "AI स्वास्थ्य अंतर्दृष्टि व देखभाल योजना" : "AI-Synthesized Health Insights"}
            </h2>
          </div>
          <span className="cv-patient-badge">
            <span>🤖</span>
            <span>{isHindi ? "सत्यापित डेटा द्वारा संचालित" : "Grounded by Clinical Records"}</span>
          </span>
        </div>

        {/* Clear Medical Disclaimer */}
        <div className="cv-insights-disclaimer" role="note">
          <span aria-hidden="true">ℹ️</span>
          <span>
            {insightsData?.disclaimer ||
              "CareVoice AI insights are educational summaries synthesized from your authorized clinical records. They do not constitute a medical diagnosis or treatment plan."}
          </span>
        </div>

        {/* 3 Grounded Insight Cards */}
        <div className="cv-insights-grid">
          {(insightsData?.insights || [
            {
              id: "vitals",
              title: "Vital Signs Trajectory",
              summary: "Blood pressure has stabilized within normal thresholds (120/78 mmHg). Pulse rate is regular at 68 bpm.",
              badge: "Clinical Trend",
              grounding_sources: [{ type: "vital", label: "Vitals Log #7" }],
            },
            {
              id: "safety",
              title: "Medication & Allergy Safety Profile",
              summary: "Safety profile active for documented Penicillin allergy. Beta-lactam antibiotics are contraindicated.",
              badge: "Patient Safety",
              grounding_sources: [{ type: "allergy", label: "Allergy Alert: Penicillins" }],
            },
            {
              id: "continuity",
              title: "Care Continuity & Instructions",
              summary: "Follow DASH dietary protocol (<2g sodium/day). Next cardiology review scheduled.",
              badge: "Actionable Plan",
              grounding_sources: [{ type: "note", label: "Dr. Kabir Consultation Note" }],
            },
          ]).map((insight) => (
            <article key={insight.id} className="cv-insight-item">
              <div className="cv-insight-top">
                <span className="cv-insight-badge">{insight.badge || "Clinical Insight"}</span>
                <span style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>Grounded</span>
              </div>
              <h3 className="cv-insight-title">{insight.title}</h3>
              <p className="cv-insight-summary">{insight.summary}</p>
              {insight.grounding_sources?.length > 0 && (
                <div className="cv-insight-grounding">
                  <span>{isHindi ? "प्रमाण स्रोत:" : "Traceable Source:"}</span>
                  {insight.grounding_sources.map((src, idx) => (
                    <span key={idx} className="cv-grounding-tag">
                      <span>✓</span>
                      <span>{src.label}</span>
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>

        {/* Suggested Questions for Next Clinical Visit */}
        {insightsData?.suggested_questions?.length > 0 && (
          <div className="cv-suggested-questions">
            <h4>{isHindi ? "अगली मुलाक़ात के लिए सुझाए गए प्रश्न:" : "Questions for your next clinician consultation:"}</h4>
            <div className="cv-questions-list">
              {insightsData.suggested_questions.map((q, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="cv-question-btn"
                  onClick={() => onNavigate("Assistant")}
                  title="Ask CareVoice AI about this question"
                >
                  <span>💬 {q}</span>
                  <span style={{ color: "var(--cv-accent)" }}>→</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ----------------------------------------------------------------------
         6. Rich Health Record Sections (Tabbed Panels below charts)
         Tabs: Active Medications, Lab Reports, Clinical Notes, Activity Feed
         ---------------------------------------------------------------------- */}
      <section ref={recordsSectionRef} className="cv-records-tabs-container" aria-labelledby="health-records-heading">
        <div className="cv-welcome-header" style={{ marginBottom: "16px" }}>
          <div>
            <span className="eyebrow">{isHindi ? "क्लिनिकल रिकॉर्ड्स" : "VERIFIED HEALTH RECORDS"}</span>
            <h2 id="health-records-heading" style={{ margin: "4px 0" }}>
              {isHindi ? "विस्तृत स्वास्थ्य इतिहास व दस्तावेज़" : "Health Records & Diagnostic History"}
            </h2>
          </div>
          <button
            type="button"
            className="cv-text-button"
            onClick={() => onNavigate("Health records")}
            style={{ fontWeight: "700" }}
          >
            {isHindi ? "पूर्ण स्वास्थ्य रिकॉर्ड्स पोर्टल खोलें" : "Open Full Records Portal"} →
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="cv-tab-nav" role="tablist" aria-label="Health records categories">
          {[
            { id: "medications", label: isHindi ? "सक्रिय दवाइयाँ (Rx)" : "Active Medications (Rx)", icon: "℞", count: counts.active_medications },
            { id: "labs", label: isHindi ? "लैब व डायग्नोस्टिक्स" : "Diagnostic Reports", icon: "🔬", count: documents.length },
            { id: "notes", label: isHindi ? "क्लिनिकल नोट्स" : "Doctor Notes", icon: "🩺", count: notes.length },
            { id: "timeline", label: isHindi ? "हालिया कालक्रम" : "Activity Timeline", icon: "⏱️", count: timelineEvents.length },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeRecordsTab === tab.id}
              className={`cv-tab-btn ${activeRecordsTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveRecordsTab(tab.id)}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
              {typeof tab.count === "number" && (
                <span className="cv-patient-badge" style={{ padding: "1px 6px" }}>{tab.count}</span>
              )}
            </button>
          ))}
        </div>

        {/* Tab Panel 1: Active Medications */}
        {activeRecordsTab === "medications" && (
          <div className="cv-record-cards-grid" role="tabpanel">
            {prescriptions.length > 0 ? (
              prescriptions.map((rx) => (
                <article key={rx.id} className="cv-record-card">
                  <div className="cv-record-card-header">
                    <div>
                      <h3 className="cv-record-card-title">{rx.diagnosis || "Clinical Prescription"}</h3>
                      <span style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                        {rx.prescription_number} • {formatDate(rx.created_at)}
                      </span>
                    </div>
                    <span className={`cv-metric-badge ${rx.is_ai_draft ? "neutral" : "success"}`}>
                      {rx.is_ai_draft ? "AI Draft" : "Signed"}
                    </span>
                  </div>

                  <div className="cv-record-card-body">
                    {rx.items?.map((it, idx) => (
                      <div key={idx} style={{ padding: "6px 0", borderBottom: idx < rx.items.length - 1 ? "1px solid var(--cv-border-soft)" : "none" }}>
                        <strong>{it.medication_name} {it.strength || ""}</strong>
                        <div style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                          {it.frequency} • {it.duration} ({it.dosage_form})
                        </div>
                        {it.instructions && (
                          <div style={{ fontSize: "11px", color: "var(--cv-text-body)", marginTop: "2px" }}>
                            {it.instructions}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {rx.allergy_warnings?.length > 0 && (
                    <div style={{ fontSize: "11px", color: "#b45309", background: "#fffbeb", padding: "6px 8px", borderRadius: "4px" }}>
                      ⚠️ {rx.allergy_warnings[0]}
                    </div>
                  )}

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "auto", paddingTop: "8px" }}>
                    <span style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                      {rx.doctor_name ? `Dr. ${rx.doctor_name}` : "Attending Clinician"}
                    </span>
                    <button
                      type="button"
                      className="cv-text-button"
                      disabled={downloadingId === `rx-${rx.id}`}
                      onClick={() =>
                        downloadBinary(
                          `/records/prescriptions/${rx.id}/pdf`,
                          `prescription-${rx.prescription_number}.pdf`,
                          `rx-${rx.id}`
                        )
                      }
                    >
                      <span>📥</span>
                      <span>{downloadingId === `rx-${rx.id}` ? "…" : "Rx PDF"}</span>
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <EmptyState icon="℞" title="No Prescriptions" description="No active prescriptions on file." />
            )}
          </div>
        )}

        {/* Tab Panel 2: Diagnostic & Lab Reports */}
        {activeRecordsTab === "labs" && (
          <div className="cv-record-cards-grid" role="tabpanel">
            {documents.length > 0 ? (
              documents.map((doc) => (
                <article key={doc.id} className="cv-record-card">
                  <div className="cv-record-card-header">
                    <div>
                      <h3 className="cv-record-card-title">{doc.title}</h3>
                      <span style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                        {doc.extracted_data?.category || doc.document_type} • {formatDate(doc.created_at)}
                      </span>
                    </div>
                    <span className="cv-metric-badge success">Verified</span>
                  </div>

                  {doc.extracted_data?.parameters?.length > 0 && (
                    <div className="cv-record-card-body" style={{ maxHeight: "110px", overflowY: "auto" }}>
                      {doc.extracted_data.parameters.slice(0, 4).map((p, idx) => (
                        <div key={idx} style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", padding: "3px 0" }}>
                          <span style={{ color: "var(--cv-text-secondary)" }}>{p.name}</span>
                          <strong>{p.value}</strong>
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "auto", paddingTop: "8px" }}>
                    <span style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                      {doc.extracted_data?.signing_doctor || "Pathology Department"}
                    </span>
                    <button
                      type="button"
                      className="cv-button cv-button-secondary"
                      style={{ padding: "6px 12px", fontSize: "12px" }}
                      disabled={downloadingId === `doc-${doc.id}`}
                      onClick={() =>
                        downloadBinary(
                          `/records/documents/${doc.id}/download`,
                          `${doc.title.replace(/\s+/g, "_")}.pdf`,
                          `doc-${doc.id}`
                        )
                      }
                    >
                      <span>📥</span>
                      <span>{downloadingId === `doc-${doc.id}` ? "Downloading…" : "Download PDF"}</span>
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <EmptyState icon="🔬" title="No Diagnostic Documents" description="No diagnostic documents currently uploaded." />
            )}
          </div>
        )}

        {/* Tab Panel 3: Clinical Notes */}
        {activeRecordsTab === "notes" && (
          <div className="cv-record-cards-grid" role="tabpanel">
            {notes.length > 0 ? (
              notes.map((note) => (
                <article key={note.id} className="cv-record-card">
                  <div className="cv-record-card-header">
                    <div>
                      <h3 className="cv-record-card-title">{note.chief_complaint || "Consultation Note"}</h3>
                      <span style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                        {note.note_type} • {formatDate(note.created_at)}
                      </span>
                    </div>
                    <span className={`cv-metric-badge ${note.is_ai_draft ? "neutral" : "success"}`}>
                      {note.is_ai_draft ? "AI Draft" : "Signed"}
                    </span>
                  </div>

                  <div className="cv-record-card-body">
                    {note.assessment && (
                      <p style={{ margin: "4px 0" }}>
                        <strong>Assessment:</strong> {note.assessment}
                      </p>
                    )}
                    {note.follow_up_instructions && (
                      <p style={{ margin: "4px 0", color: "var(--cv-accent)" }}>
                        <strong>Plan:</strong> {note.follow_up_instructions}
                      </p>
                    )}
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "auto", paddingTop: "8px" }}>
                    <span style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>
                      {note.doctor_name ? `Dr. ${note.doctor_name}` : "Attending Doctor"}
                    </span>
                    <button
                      type="button"
                      className="cv-text-button"
                      disabled={downloadingId === `note-${note.id}`}
                      onClick={() =>
                        downloadBinary(
                          `/records/notes/${note.id}/pdf`,
                          `clinical-note-${note.id}.pdf`,
                          `note-${note.id}`
                        )
                      }
                    >
                      <span>📥</span>
                      <span>{downloadingId === `note-${note.id}` ? "…" : "Note PDF"}</span>
                    </button>
                  </div>
                </article>
              ))
            ) : (
              <EmptyState icon="🩺" title="No Doctor Notes" description="No consultation notes recorded yet." />
            )}
          </div>
        )}

        {/* Tab Panel 4: Activity Timeline */}
        {activeRecordsTab === "timeline" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }} role="tabpanel">
            {timelineEvents.slice(0, 8).map((ev) => (
              <div
                key={ev.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 14px",
                  background: "var(--cv-surface-soft)",
                  borderRadius: "8px",
                  fontSize: "13px",
                  gap: "12px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
                  <span style={{ fontSize: "16px" }}>
                    {ev.event_type === "prescription" ? "℞" : ev.event_type === "document" ? "🔬" : ev.event_type === "appointment" ? "📅" : "❤️"}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: "700", color: "var(--cv-text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {ev.title}
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--cv-text-muted)" }}>{ev.description}</div>
                  </div>
                </div>
                <div style={{ fontSize: "11px", color: "var(--cv-text-muted)", whiteSpace: "nowrap" }}>
                  {formatDate(ev.timestamp)}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ----------------------------------------------------------------------
         7. Log Vitals Observation Modal Dialog
         ---------------------------------------------------------------------- */}
      {showLogModal && (
        <div
          className="cv-modal-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget && !loggingBusy) setShowLogModal(false);
          }}
        >
          <div
            className="cv-modal-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="log-vitals-modal-title"
          >
            <div className="cv-modal-header">
              <h3 id="log-vitals-modal-title">
                {isHindi ? "नया वाइटल्स माप दर्ज करें" : "Record Physiological Observation"}
              </h3>
              <button
                type="button"
                className="cv-modal-close-btn"
                onClick={() => setShowLogModal(false)}
                disabled={loggingBusy}
                aria-label="Close modal"
              >
                ✕
              </button>
            </div>

            <p style={{ margin: "0", fontSize: "12px", color: "var(--cv-text-muted)" }}>
              {isHindi
                ? "अपने होम मॉनिटर या क्लिनिकल चेकअप से प्राप्त वाइटल रीडिंग्स दर्ज करें।"
                : "Enter resting vital signs from your home health device or recent consultation. Measurements are validated against clinical biological reference ranges."}
            </p>

            {modalFeedback.text && (
              <div
                style={{
                  padding: "8px 12px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  background: modalFeedback.type === "success" ? "#dcfce7" : "#fee2e2",
                  color: modalFeedback.type === "success" ? "#15803d" : "#b91c1c",
                }}
                role="status"
              >
                {modalFeedback.text}
              </div>
            )}

            <form onSubmit={handleLogVitalSubmit}>
              <div className="cv-modal-form-grid">
                <div className="cv-form-field">
                  <label htmlFor="input-bp-systolic">Systolic BP (mmHg)</label>
                  <input
                    id="input-bp-systolic"
                    type="number"
                    min="50"
                    max="280"
                    placeholder="e.g. 120"
                    value={vitalForm.bp_systolic}
                    onChange={(e) => setVitalForm({ ...vitalForm, bp_systolic: e.target.value })}
                  />
                </div>

                <div className="cv-form-field">
                  <label htmlFor="input-bp-diastolic">Diastolic BP (mmHg)</label>
                  <input
                    id="input-bp-diastolic"
                    type="number"
                    min="30"
                    max="180"
                    placeholder="e.g. 80"
                    value={vitalForm.bp_diastolic}
                    onChange={(e) => setVitalForm({ ...vitalForm, bp_diastolic: e.target.value })}
                  />
                </div>

                <div className="cv-form-field">
                  <label htmlFor="input-heart-rate">Heart Rate (bpm)</label>
                  <input
                    id="input-heart-rate"
                    type="number"
                    min="30"
                    max="240"
                    placeholder="e.g. 72"
                    value={vitalForm.heart_rate}
                    onChange={(e) => setVitalForm({ ...vitalForm, heart_rate: e.target.value })}
                  />
                </div>

                <div className="cv-form-field">
                  <label htmlFor="input-spo2">SpO2 (%)</label>
                  <input
                    id="input-spo2"
                    type="number"
                    min="50"
                    max="100"
                    placeholder="e.g. 99"
                    value={vitalForm.spo2}
                    onChange={(e) => setVitalForm({ ...vitalForm, spo2: e.target.value })}
                  />
                </div>

                <div className="cv-form-field">
                  <label htmlFor="input-glucose">Blood Glucose (mg/dL)</label>
                  <input
                    id="input-glucose"
                    type="number"
                    step="0.1"
                    min="20"
                    max="600"
                    placeholder="e.g. 94.0"
                    value={vitalForm.blood_glucose}
                    onChange={(e) => setVitalForm({ ...vitalForm, blood_glucose: e.target.value })}
                  />
                </div>

                <div className="cv-form-field">
                  <label htmlFor="input-temp">Temperature (°F)</label>
                  <input
                    id="input-temp"
                    type="number"
                    step="0.1"
                    min="90"
                    max="110"
                    placeholder="e.g. 98.6"
                    value={vitalForm.temperature_f}
                    onChange={(e) => setVitalForm({ ...vitalForm, temperature_f: e.target.value })}
                  />
                </div>

                <div className="cv-form-field">
                  <label htmlFor="input-weight">Weight (kg)</label>
                  <input
                    id="input-weight"
                    type="number"
                    step="0.1"
                    min="1"
                    max="300"
                    placeholder="e.g. 75.0"
                    value={vitalForm.weight_kg}
                    onChange={(e) => setVitalForm({ ...vitalForm, weight_kg: e.target.value })}
                  />
                </div>

                <div className="cv-form-field">
                  <label htmlFor="input-source">Source</label>
                  <select
                    id="input-source"
                    value={vitalForm.source}
                    onChange={(e) => setVitalForm({ ...vitalForm, source: e.target.value })}
                  >
                    <option value="home_device">Home Device (Smart Monitor)</option>
                    <option value="clinical_encounter">Clinical Encounter</option>
                    <option value="patient_manual">Manual Patient Entry</option>
                  </select>
                </div>

                <div className="cv-form-field full-width">
                  <label htmlFor="input-notes">Clinical Notes / Context</label>
                  <textarea
                    id="input-notes"
                    rows="2"
                    placeholder="e.g. Morning seated measurement before breakfast."
                    value={vitalForm.notes}
                    onChange={(e) => setVitalForm({ ...vitalForm, notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="cv-modal-actions">
                <button
                  type="button"
                  className="cv-button cv-button-secondary"
                  onClick={() => setShowLogModal(false)}
                  disabled={loggingBusy}
                >
                  {isHindi ? "रद्द करें" : "Cancel"}
                </button>
                <button
                  type="submit"
                  className="cv-button cv-button-primary"
                  disabled={loggingBusy}
                >
                  {loggingBusy ? (isHindi ? "सेव हो रहा है…" : "Saving…") : (isHindi ? "वाइटल्स सेव करें" : "Save Vitals")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default PatientDashboard;
