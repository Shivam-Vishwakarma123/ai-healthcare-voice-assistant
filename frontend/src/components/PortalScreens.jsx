import { useEffect, useMemo, useRef, useState } from "react";
import PublicTriage from "./PublicTriage";
import VoiceAssistant from "./VoiceAssistant";
import ProviderDetailModal from "./ProviderDetailModal";
import AppointmentHistoryModal from "./AppointmentHistoryModal";
import AppointmentRescheduleModal from "./AppointmentRescheduleModal";
import AppointmentReceiptModal from "./AppointmentReceiptModal";
import { apiRequest, formatMoney } from "../services/api";
import { createIdempotencyKey, formatAppointmentDatePart, formatAppointmentDateTime, getISTDate } from "../services/appointments";
import { getAppointmentPaymentAction, getAppointmentPaymentState } from "../services/appointmentPayments";
import NotificationContactForm from "./NotificationContactForm";
import { PatientDashboard } from "./PatientDashboard";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

// Standardized portal page header rendering eyebrow category, primary heading, description, and action button.
export function ScreenTitle({ eyebrow = "CAREVOICE PORTAL", title, description, action }) {
  return (
    <div className="cv-page-title">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
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

// Accessible loading spinner with localized textual status message.
function LoadingState({ label = "Loading…" }) {
  return <div className="cv-loading" role="status"><span className="cv-spinner" aria-hidden="true" />{label}</div>;
}

// Expandable inline drawer displaying clinician or hospital profile details, verified degrees, and hours.
function ProviderInlineDetails({ type, detail, loading, error, onRetry, language }) {
  const hi = language === "hi";
  if (loading) return <LoadingState label={hi ? "विवरण लोड हो रहे हैं…" : "Loading details…"} />;
  if (error) {
    return (
      <div className="cv-provider-inline-error" role="alert">
        <p>{error}</p>
        <button className="cv-button cv-button-quiet" type="button" onClick={onRetry}>{hi ? "फिर कोशिश करें" : "Retry"}</button>
      </div>
    );
  }
  if (!detail) return <p className="cv-subtle">{hi ? "विवरण उपलब्ध नहीं हैं।" : "Details are not available."}</p>;

  if (type === "doctors") {
    const qualifications = detail.qualifications || [];
    const schedules = (detail.schedules || []).filter((item) => item.is_active);
    return (
      <div className="cv-provider-inline-content">
        <p>{detail.bio || detail.specialty}</p>
        <dl>
          <div><dt>{hi ? "विशेषताएँ" : "Specialties"}</dt><dd>{(detail.specialties || [detail.specialty]).join(", ")}</dd></div>
          <div><dt>{hi ? "अनुभव" : "Experience"}</dt><dd>{hi ? `${detail.experience_years} वर्ष` : `${detail.experience_years} years`}</dd></div>
          <div><dt>{hi ? "परामर्श शुल्क" : "Consultation fee"}</dt><dd>{formatMoney(detail.fee_minor)}</dd></div>
          <div><dt>{hi ? "भाषाएँ" : "Languages"}</dt><dd>{(detail.languages || []).join(", ") || "—"}</dd></div>
          <div><dt>{hi ? "परामर्श प्रकार" : "Consultation types"}</dt><dd>{(detail.consultation_types || []).map((item) => item.replaceAll("_", " ")).join(", ") || "—"}</dd></div>
        </dl>
        <h4>{hi ? "योग्यताएँ" : "Qualifications"}</h4>
        {qualifications.length ? <ul>{qualifications.map((item) => <li key={item.id}>{item.degree} · {item.institution} · {item.verification_status}</li>)}</ul> : <p className="cv-subtle">{hi ? "कोई प्रकाशित योग्यता नहीं है।" : "No qualifications have been published."}</p>}
        <h4>{hi ? "उपलब्धता" : "Availability"}</h4>
        {schedules.length ? <ul>{schedules.map((item) => <li key={item.id}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][item.day_of_week]} · {item.starts_at.slice(0, 5)}–{item.ends_at.slice(0, 5)} ({item.timezone}) · {item.consultation_type.replaceAll("_", " ")}</li>)}</ul> : <p className="cv-subtle">{hi ? "कोई समय-सारणी प्रकाशित नहीं है।" : "No availability has been published."}</p>}
      </div>
    );
  }

  return (
    <div className="cv-provider-inline-content">
      <p>{detail.description || (hi ? "विवरण उपलब्ध नहीं हैं।" : "No additional description has been provided.")}</p>
      <dl>
        <div><dt>{hi ? "पता" : "Address"}</dt><dd>{detail.address || "—"}</dd></div>
        <div><dt>{hi ? "फ़ोन" : "Phone"}</dt><dd>{detail.phone ? <a href={`tel:${detail.phone}`}>{detail.phone}</a> : "—"}</dd></div>
        <div><dt>{hi ? "वेबसाइट" : "Website"}</dt><dd>{detail.website ? <a href={detail.website} target="_blank" rel="noreferrer">{detail.website}</a> : "—"}</dd></div>
        <div><dt>{hi ? "विभाग" : "Departments"}</dt><dd>{detail.departments || "—"}</dd></div>
      </dl>
    </div>
  );
}

// Queries backend availability engine and renders selectable IST appointment time slot buckets.
function AppointmentSlotPicker({ token, doctorId, consultationType, value, onChange, language }) {
  const [day, setDay] = useState(() => getISTDate(1));
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const hi = language === "hi";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    apiRequest(`/providers/doctors/${doctorId}/available-slots?${new URLSearchParams({ day, consultation_type: consultationType })}`, token)
      .then((results) => {
        if (active) setSlots(results);
      })
      .catch((reason) => {
        if (active) {
          setSlots([]);
          setError(reason?.message || (hi ? "समय उपलब्ध नहीं हो सके।" : "Available times could not be loaded."));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [doctorId, day, consultationType, token]);

  return (
    <>
      <label>{hi ? "तारीख (IST)" : "Date (IST)"}<input required type="date" min={getISTDate()} value={day} onChange={(event) => { setDay(event.target.value); onChange(""); }} /></label>
      <label>{hi ? "उपलब्ध समय (IST)" : "Available time (IST)"}
        <select required value={value} onChange={(event) => onChange(event.target.value)} disabled={loading || slots.length === 0}>
          <option value="">{loading ? (hi ? "समय लोड हो रहा है…" : "Loading times…") : (hi ? "समय चुनें" : "Select a time")}</option>
          {slots.map((slot) => <option key={slot.scheduled_for} value={slot.scheduled_for}>{formatAppointmentDateTime(slot.scheduled_for, hi ? "hi-IN" : "en-IN")}</option>)}
        </select>
      </label>
      {loading && <p className="cv-subtle" role="status">{hi ? "प्रकाशित समय-सारणी से उपलब्धता जाँची जा रही है…" : "Checking the clinician’s published availability…"}</p>}
      {!loading && !error && slots.length === 0 && <p className="cv-subtle">{hi ? "इस तारीख को कोई समय उपलब्ध नहीं है। दूसरी तारीख चुनें।" : "No slots are available on this date. Choose another date."}</p>}
      {error && <p className="cv-error" role="alert">{error}</p>}
    </>
  );
}

// In-place alert banner displaying data retrieval failures with optional retry trigger.
function InlineError({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className="cv-error" role="alert">
      <div><strong>We couldn’t load this information.</strong><p>{message}</p></div>
      {onRetry && <button className="cv-button cv-button-quiet" onClick={onRetry}>Try again</button>}
    </div>
  );
}

// Public emergency symptom safety checker and triage portal with hotlines and voice consultation.
export function TriagePage({ language = "en", token, onNavigate }) {
  const hi = language === "hi";
  return (
    <>
      <ScreenTitle eyebrow={hi ? "लक्षण सुरक्षा जाँच" : "SYMPTOM SAFETY CHECK"} title={hi ? "आप कैसा महसूस कर रहे हैं?" : "How are you feeling?"} description={hi ? "तत्काल, नियम-आधारित मार्गदर्शन के लिए बताएँ कि क्या हो रहा है। यह निदान नहीं है।" : "Describe what is happening for immediate, rule-based guidance. This is not a diagnosis."} />
      <div className="cv-triage-layout">
        <PublicTriage language={language} onNavigate={onNavigate} />
        <aside className="cv-card cv-safety-note">
          <span className="cv-icon-tile" aria-hidden="true">!</span>
          <h2>{hi ? "आपातकालीन सहायता चाहिए?" : "Need emergency help?"}</h2>
          <p>{hi ? "यदि तत्काल खतरा हो सकता है तो ऑनलाइन जवाब की प्रतीक्षा न करें।" : "Do not wait for an online response if you may be in immediate danger."}</p>
          <a className="cv-emergency-link" href="tel:112">{hi ? "112 पर कॉल करें" : "Call 112"}</a>
          <a className="cv-emergency-link" href="tel:108">{hi ? "एम्बुलेंस 108" : "Ambulance 108"}</a>
          <small>{hi ? "यह जाँच आपातकाल को खारिज नहीं कर सकती। योग्य चिकित्सक से संपर्क करें।" : "This safety checker cannot rule out an emergency. Contact a qualified clinician for care."}</small>
        </aside>
      </div>
      <section className="cv-section" aria-label={hi ? "सामान्य AI सहायता" : "General AI assistance"}>
        <ScreenTitle
          eyebrow={hi ? "वैकल्पिक सामान्य जानकारी" : "OPTIONAL GENERAL INFORMATION"}
          title={hi ? "लक्षणों के बारे में पूछें" : "Ask about your symptoms"}
          description={hi
            ? "टाइप करें या बोलें। आपातकालीन सुरक्षा जाँच हमेशा AI से पहले होती है।"
            : "Type or speak. Deterministic emergency checks always run before AI or source retrieval."}
        />
        <VoiceAssistant token={token} language={language} onNavigate={onNavigate} />
      </section>
    </>
  );
}

// Real-time activity notifications feed tracking appointments, billing receipts, and contact channels.
export function NotificationsPage({ token, user, onUserUpdated, language = "en" }) {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const hi = language === "hi";

  async function loadNotifications() {
    setLoading(true);
    setError("");
    try {
      const response = await apiRequest("/patients/notifications", token);
      setNotifications(Array.isArray(response?.items) ? response.items : []);
    } catch (err) {
      setError(err?.message || (hi ? "सूचनाएँ लोड नहीं हो सकीं।" : "Could not load notifications."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (token) {
      loadNotifications();
    } else {
      setLoading(false);
    }
  }, [token]);

  return (
    <>
      <ScreenTitle
        title={hi ? "सूचनाएँ" : "Notifications"}
        description={hi ? "आपकी देखभाल, अपॉइंटमेंट और बिलिंग से जुड़े वास्तविक समय के अपडेट।" : "Real-time updates, reminders, and activity receipts for your care."}
        action={
          <button
            type="button"
            className="cv-button cv-button-secondary"
            onClick={loadNotifications}
            disabled={loading}
          >
            {loading ? (hi ? "लोड हो रहा है…" : "Refreshing…") : (hi ? "ताज़ा करें" : "Refresh")}
          </button>
        }
      />

      <section className="cv-card">
        <div className="cv-card-heading">
          <h2>{hi ? "हाल की सूचनाएँ" : "Recent notices"}</h2>
          <span className="cv-count">{notifications.length}</span>
        </div>

        {loading ? (
          <LoadingState label={hi ? "सूचनाएँ लोड हो रही हैं…" : "Loading notifications…"} />
        ) : error ? (
          <div className="cv-provider-inline-error" role="alert">
            <p>{error}</p>
            <button className="cv-button cv-button-quiet" type="button" onClick={loadNotifications}>
              {hi ? "फिर कोशिश करें" : "Retry"}
            </button>
          </div>
        ) : notifications.length === 0 ? (
          <EmptyState
            icon="♧"
            title={hi ? "कोई नई सूचना नहीं है" : "No notifications yet"}
            description={hi ? "जब आप अपॉइंटमेंट बुक करेंगे, समय बदलेंगे या भुगतान करेंगे, तो यहाँ संदेश दिखाई देंगे।" : "Notices will appear here when you book appointments, reschedule, or complete payments."}
          />
        ) : (
          <div className="cv-invoice-list">
            {notifications.map((item) => (
              <div key={item.id} className="cv-invoice-row">
                <div>
                  <b>{hi ? item.title_hi : item.title}</b>
                  <p>{hi ? item.message_hi : item.message}</p>
                  <small style={{ color: "var(--cv-text-muted)", fontSize: "11px" }}>
                    {new Date(item.created_at).toLocaleString(hi ? "hi-IN" : "en-IN", { timeZone: "Asia/Kolkata" })} IST
                  </small>
                </div>
                <span className="cv-status" style={{ textTransform: "uppercase" }}>
                  {item.channel}
                </span>
                <span className={`cv-status ${item.status === "failed" ? "cv-status-cancelled" : ""}`}>
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <NotificationContactForm
        token={token}
        user={user}
        onUpdated={onUserUpdated}
        language={language}
      />
    </>
  );
}

// Patient and clinical staff home dashboard displaying high-level metrics, upcoming visits, and shortcuts.
export function DashboardPage({ user, patient, token, onNavigate, language = "en" }) {
  const staffView = ["staff", "admin"].includes(user?.role);
  if (!staffView) {
    return (
      <PatientDashboard
        user={user}
        patient={patient}
        token={token}
        onNavigate={onNavigate}
        language={language}
      />
    );
  }

  const [data, setData] = useState({ appointments: [], doctors: [], hospitals: [] });
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState({});
  const hi = language === "hi";

  async function loadDashboard() {
    setLoading(true);
    const endpoints = [
      ["appointments", "/providers/appointments"],
      ["doctors", "/providers/doctors"],
      ["hospitals", "/providers/hospitals"],
    ];
    const results = await Promise.allSettled(endpoints.map(([, path]) => apiRequest(path, token)));
    const nextData = {};
    const nextErrors = {};
    results.forEach((result, index) => {
      const [key] = endpoints[index];
      if (result.status === "fulfilled") nextData[key] = Array.isArray(result.value) ? result.value : (result.value?.items || []);
      else {
        nextData[key] = [];
        nextErrors[key] = result.reason?.message || "Please try again.";
      }
    });
    setData((current) => ({ ...current, ...nextData }));
    setErrors(nextErrors);
    setLoading(false);
  }

  useEffect(() => { loadDashboard(); }, [token]);

  const upcoming = useMemo(
    () => data.appointments.filter((appointment) => appointment.status === "scheduled" && new Date(appointment.scheduled_for) >= new Date())
      .sort((a, b) => new Date(a.scheduled_for) - new Date(b.scheduled_for)),
    [data.appointments],
  );
  const firstName = user?.full_name?.trim().split(/\s+/)[0] || (hi ? "दोस्त" : "there");

  return (
    <>
      <ScreenTitle
        eyebrow={staffView ? (hi ? "क्लिनिक कार्यक्षेत्र" : "CARE TEAM WORKSPACE") : (hi ? "आपका स्वास्थ्य" : "YOUR HEALTH")}
        title={staffView ? (hi ? "देखभाल संचालन" : "Care operations") : (hi ? "आपका स्वास्थ्य, एक नज़र में" : "Your health, in focus")}
        description={staffView
          ? (hi ? "अपने क्लिनिक की उपलब्ध सेवाएँ और अपॉइंटमेंट देखें।" : "A live snapshot of appointments and care-directory availability.")
          : (hi ? `${firstName}, आपके केयर पोर्टल में आपका स्वागत है।` : `Welcome back, ${firstName}. Your care, organized in one place.`)}
        action={<button className="cv-button cv-button-primary" onClick={() => onNavigate("Symptom check")}>{hi ? "लक्षण जाँचें" : "Check symptoms"} <span aria-hidden="true">→</span></button>}
      />
      {loading ? <LoadingState label={hi ? "आपका डैशबोर्ड लोड हो रहा है…" : "Loading your dashboard…"} /> : (
        <>
          <div className="cv-metrics" aria-label={staffView ? "Care operations summary" : "Patient overview"}>
            {staffView ? (
              <>
                <MetricCard icon="▦" label={hi ? "कुल अपॉइंटमेंट" : "Appointments"} value={errors.appointments ? "—" : data.appointments.length} note={hi ? "लाइव अपॉइंटमेंट API" : "From the live appointments API"} />
                <MetricCard icon="♙" label={hi ? "डॉक्टर" : "Doctors"} value={errors.doctors ? "—" : data.doctors.length} note={hi ? "उपलब्ध डॉक्टर" : "Available directory profiles"} />
                <MetricCard icon="⌂" label={hi ? "अस्पताल" : "Hospitals"} value={errors.hospitals ? "—" : data.hospitals.length} note={hi ? "केयर डायरेक्टरी" : "In the care directory"} />
                <MetricCard icon="✓" label={hi ? "आगामी अपॉइंटमेंट" : "Upcoming visits"} value={errors.appointments ? "—" : upcoming.length} note={hi ? "शेड्यूल किए गए" : "Currently scheduled"} />
              </>
            ) : (
              <>
                <MetricCard icon="♡" label={hi ? "स्वास्थ्य प्रोफ़ाइल" : "Health profile"} value={patient ? (hi ? "पूरी" : "Ready") : (hi ? "सेटअप करें" : "Set up")} note={patient ? (hi ? "आपकी प्रोफ़ाइल सेव है" : "Your profile is saved") : (hi ? "व्यक्तिगत जानकारी जोड़ें" : "Add your patient details")} />
                <MetricCard icon="▦" label={hi ? "आगामी अपॉइंटमेंट" : "Upcoming visits"} value={errors.appointments ? "—" : upcoming.length} note={errors.appointments ? (hi ? "अभी उपलब्ध नहीं" : "Temporarily unavailable") : (hi ? "शेड्यूल किए गए" : "From your appointment list")} />
                <MetricCard icon="♙" label={hi ? "डॉक्टर" : "Care directory"} value={errors.doctors ? "—" : data.doctors.length} note={hi ? "डायरेक्टरी प्रोफ़ाइल" : "Doctor profiles"} />
                <MetricCard icon="⌂" label={hi ? "अस्पताल" : "Hospitals"} value={errors.hospitals ? "—" : data.hospitals.length} note={hi ? "उपलब्ध स्थान" : "Care locations"} />
              </>
            )}
          </div>
          <div className="cv-columns">
            <section className="cv-card">
              <div className="cv-card-heading">
                <div><span className="eyebrow">{hi ? "आपकी देखभाल" : "YOUR CARE"}</span><h2>{hi ? "अगली मुलाक़ात" : "Upcoming appointments"}</h2></div>
                <button className="cv-text-button" onClick={() => onNavigate("Appointments")}>{hi ? "सभी देखें" : "View all"} →</button>
              </div>
              {errors.appointments ? <InlineError message={errors.appointments} onRetry={loadDashboard} /> :
                upcoming.length ? <div className="cv-appointment-list">{upcoming.slice(0, 3).map((appointment) => <AppointmentSummary key={appointment.id} appointment={appointment} />)}</div> :
                  <EmptyState icon="▦" title={hi ? "अभी कोई आगामी अपॉइंटमेंट नहीं" : "No upcoming appointments"} description={hi ? "डॉक्टर खोजें और अपॉइंटमेंट बुक करें।" : "Explore the care directory to find a doctor and book a visit."} action={<button className="cv-button cv-button-secondary" onClick={() => onNavigate("Find care")}>{hi ? "देखभाल खोजें" : "Explore care"}</button>} />}
            </section>
            <section className="cv-card cv-shortcuts">
              <span className="eyebrow">{hi ? "त्वरित पहुँच" : "QUICK ACCESS"}</span>
              <h2>{hi ? "आज आपको किस मदद की ज़रूरत है?" : "How can we help today?"}</h2>
              <QuickLink icon="✳" title={hi ? "लक्षण जाँचें" : "Symptom check"} detail={hi ? "नियम-आधारित सुरक्षा मार्गदर्शन" : "Rule-based safety guidance"} onClick={() => onNavigate("Symptom check")} />
              <QuickLink icon="📁" title={hi ? "स्वास्थ्य रिकॉर्ड" : "Health records"} detail={hi ? "इतिहास, पर्चे, रिपोर्ट व FHIR" : "History, prescriptions, reports & FHIR"} onClick={() => onNavigate("Health records")} />
              <QuickLink icon="◉" title={hi ? "CareVoice से बात करें" : "Talk to CareVoice"} detail={hi ? "सामान्य स्वास्थ्य जानकारी" : "General health information"} onClick={() => onNavigate("Assistant")} />
              <QuickLink icon="♙" title={hi ? "डॉक्टर खोजें" : "Find a doctor"} detail={hi ? "डॉक्टर और अस्पताल ब्राउज़ करें" : "Browse doctors and hospitals"} onClick={() => onNavigate("Find care")} />
            </section>
          </div>
          {Object.keys(errors).length > 0 && <p className="cv-subtle">{hi ? "कुछ डैशबोर्ड जानकारी अभी उपलब्ध नहीं है।" : "Some dashboard information is temporarily unavailable."}</p>}
        </>
      )}
    </>
  );
}

// Healthcare provider management console for editing biography, publishing schedules, and managing qualifications.
export function ProviderDashboardPage({ user, token, onUserUpdated, language = "en" }) {
  const hi = language === "hi";
  const [dashboard, setDashboard] = useState(null);
  const [reviewQueue, setReviewQueue] = useState({ hospitals: [], doctors: [], qualifications: [] });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [doctorForm, setDoctorForm] = useState({ bio: "", specialties: "", languages: "", consultation_types: "" });
  const [scheduleForm, setScheduleForm] = useState({ day_of_week: "1", starts_at: "09:00", ends_at: "12:00", timezone: "Asia/Kolkata", consultation_type: "in_person" });
  const [qualificationForm, setQualificationForm] = useState({ degree: "", institution: "", completion_year: "" });
  const [hospitalForm, setHospitalForm] = useState({ name: "", city: "", state: "", address: "", phone: "", description: "" });
  const [newDoctor, setNewDoctor] = useState({ full_name: "", specialty: "", fee: "0", experience_years: "0", bio: "" });
  const [newHospital, setNewHospital] = useState({ name: "", city: "", state: "", address: "", phone: "", website: "", departments: "General Medicine", description: "" });

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const result = await apiRequest("/providers/dashboard", token);
      setDashboard(result);
      if (result.doctor) {
        setDoctorForm({
          bio: result.doctor.bio || "",
          specialties: (result.doctor.specialties || []).join(", "),
          languages: (result.doctor.languages || []).join(", "),
          consultation_types: (result.doctor.consultation_types || []).join(", "),
        });
      }
      if (result.hospital) {
        setHospitalForm({
          name: result.hospital.name,
          city: result.hospital.city,
          state: result.hospital.state,
          address: result.hospital.address || "",
          phone: result.hospital.phone || "",
          description: result.hospital.description || "",
        });
      }
      if (user?.role === "platform_admin") setReviewQueue(await apiRequest("/providers/review-queue", token));
    } catch (reason) {
      setError(reason?.message || "The provider workspace could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadDashboard(); }, [token, user?.role]);

  async function perform(action, successMessage) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const result = await action();
      setNotice(typeof successMessage === "function" ? successMessage(result) : successMessage);
      await loadDashboard();
    } catch (reason) {
      setError(reason?.message || "The change could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function saveDoctor(event) {
    event.preventDefault();
    if (!dashboard?.doctor) return;
    await perform(
      () => apiRequest(`/providers/doctors/${dashboard.doctor.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({
          bio: doctorForm.bio,
          specialties: doctorForm.specialties.split(",").map((item) => item.trim()).filter(Boolean),
          languages: doctorForm.languages.split(",").map((item) => item.trim()).filter(Boolean),
          consultation_types: doctorForm.consultation_types.split(",").map((item) => item.trim()).filter(Boolean),
        }),
      }),
      hi ? "प्रोफ़ाइल सेव हो गई।" : "Clinician profile saved.",
    );
  }

  async function saveSchedule(event) {
    event.preventDefault();
    if (!dashboard?.doctor) return;
    const current = dashboard.doctor.schedules.map(({ day_of_week, starts_at, ends_at, timezone, consultation_type, is_active }) => ({
      day_of_week, starts_at, ends_at, timezone, consultation_type, is_active,
    }));
    current.push({ ...scheduleForm, day_of_week: Number(scheduleForm.day_of_week), is_active: true });
    await perform(
      () => apiRequest(`/providers/doctors/${dashboard.doctor.id}/schedules`, token, { method: "PUT", body: JSON.stringify(current) }),
      hi ? "समय-सारणी सेव हो गई।" : "Recurring schedule saved.",
    );
  }

  async function removeSchedule(scheduleId) {
    if (!dashboard?.doctor) return;
    const current = dashboard.doctor.schedules
      .filter((item) => item.id !== scheduleId)
      .map(({ day_of_week, starts_at, ends_at, timezone, consultation_type, is_active }) => ({
        day_of_week, starts_at, ends_at, timezone, consultation_type, is_active,
      }));
    await perform(
      () => apiRequest(`/providers/doctors/${dashboard.doctor.id}/schedules`, token, { method: "PUT", body: JSON.stringify(current) }),
      hi ? "समय-सारणी अपडेट हुई।" : "Recurring schedule updated.",
    );
  }

  async function addQualification(event) {
    event.preventDefault();
    if (!dashboard?.doctor) return;
    const current = dashboard.doctor.qualifications.map(({ degree, institution, completion_year }) => ({
      degree, institution, completion_year,
    }));
    current.push({
      degree: qualificationForm.degree,
      institution: qualificationForm.institution,
      completion_year: qualificationForm.completion_year ? Number(qualificationForm.completion_year) : null,
    });
    await perform(
      () => apiRequest(`/providers/doctors/${dashboard.doctor.id}`, token, {
        method: "PATCH",
        body: JSON.stringify({ qualifications: current }),
      }),
      hi ? "योग्यता समीक्षा के लिए सेव हुई।" : "Qualification saved and sent for verification.",
    );
    setQualificationForm({ degree: "", institution: "", completion_year: "" });
  }

  async function saveHospital(event) {
    event.preventDefault();
    if (!dashboard?.hospital) return;
    await perform(
      () => apiRequest(`/providers/hospitals/${dashboard.hospital.id}`, token, { method: "PATCH", body: JSON.stringify(hospitalForm) }),
      hi ? "अस्पताल प्रोफ़ाइल सेव हो गई।" : "Hospital profile saved.",
    );
  }

  async function addDoctor(event) {
    event.preventDefault();
    if (!dashboard?.hospital) return;
    await perform(
      () => apiRequest(`/providers/hospitals/${dashboard.hospital.id}/doctors`, token, {
        method: "POST",
        body: JSON.stringify({
          ...newDoctor,
          fee_minor: Math.round(Number(newDoctor.fee) * 100),
          experience_years: Number(newDoctor.experience_years),
        }),
      }),
      (doctor) => hi
        ? `डॉक्टर प्रोफ़ाइल #${doctor.id} समीक्षा के लिए भेजी गई।`
        : `Clinician profile #${doctor.id} created and awaits verification.`,
    );
    setNewDoctor({ full_name: "", specialty: "", fee: "0", experience_years: "0", bio: "" });
  }

  async function review(type, id) {
    await perform(
      () => apiRequest(`/providers/${type}/${id}/verification`, token, { method: "PATCH", body: JSON.stringify({ verification_status: "verified" }) }),
      hi ? "प्रोफ़ाइल सत्यापित की गई।" : "Profile marked as verified.",
    );
  }

  async function addHospital(event) {
    event.preventDefault();
    await perform(
      () => apiRequest("/providers/hospitals", token, {
        method: "POST",
        body: JSON.stringify(newHospital),
      }),
      (hospital) => hi
        ? `अस्पताल प्रोफ़ाइल #${hospital.id} समीक्षा के लिए भेजी गई।`
        : `Hospital profile #${hospital.id} created with ${hospital.verification_status} status.`,
    );
    setNewHospital({ name: "", city: "", state: "", address: "", phone: "", website: "", departments: "General Medicine", description: "" });
  }

  return (
    <>
      <ScreenTitle
        eyebrow={hi ? "प्रदाता कार्यक्षेत्र" : "PROVIDER WORKSPACE"}
        title={user?.role === "doctor" ? (hi ? "डॉक्टर डैशबोर्ड" : "Clinician dashboard") : user?.role?.startsWith("hospital_") ? (hi ? "अस्पताल डैशबोर्ड" : "Hospital dashboard") : (hi ? "प्लेटफ़ॉर्म प्रशासन" : "Platform administration")}
        description={hi ? "प्रोफ़ाइल, समय-सारणी और सत्यापन की स्थिति सुरक्षित रूप से प्रबंधित करें।" : "Manage persistent provider profiles, published schedules, and verification using role-scoped APIs."}
      />
      {error && <InlineError message={error} onRetry={loadDashboard} />}
      {notice && <div className="cv-success" role="status">{notice}</div>}
      {["doctor", "hospital_staff"].includes(user?.role) && <NotificationContactForm token={token} user={user} onUpdated={onUserUpdated} language={language} />}
      {loading ? <LoadingState /> : !dashboard ? <EmptyState title="Workspace unavailable" description="No dashboard data was returned." /> : (
        <div className="cv-provider-dashboard">
          {dashboard.role === "doctor" && dashboard.doctor && (
            <>
              <div className="cv-metrics"><MetricCard icon="✓" label={hi ? "सत्यापन" : "Verification"} value={dashboard.doctor.verification_status} note={hi ? "मंच प्रशासक सत्यापन करते हैं।" : "Only platform administrators can verify a profile."} /></div>
              <form className="cv-card cv-form" onSubmit={saveDoctor}>
                <h2>{hi ? "चिकित्सक प्रोफ़ाइल" : "Clinician profile"}</h2>
                <label>{hi ? "परिचय" : "Biography"}<textarea rows={4} maxLength={2000} value={doctorForm.bio} onChange={(event) => setDoctorForm({ ...doctorForm, bio: event.target.value })} /></label>
                <label>{hi ? "विशेषज्ञताएँ (कॉमा से अलग)" : "Specialties (comma separated)"}<input value={doctorForm.specialties} onChange={(event) => setDoctorForm({ ...doctorForm, specialties: event.target.value })} /></label>
                <label>{hi ? "भाषाएँ (कॉमा से अलग)" : "Languages (comma separated)"}<input value={doctorForm.languages} onChange={(event) => setDoctorForm({ ...doctorForm, languages: event.target.value })} /></label>
                <label>{hi ? "परामर्श प्रकार: in_person, online, phone" : "Consultation types: in_person, online, phone"}<input value={doctorForm.consultation_types} onChange={(event) => setDoctorForm({ ...doctorForm, consultation_types: event.target.value })} /></label>
                <button className="cv-button cv-button-primary" disabled={saving}>{hi ? "प्रोफ़ाइल सेव करें" : "Save profile"}</button>
              </form>
              <form className="cv-card cv-form" onSubmit={saveSchedule}>
                <h2>{hi ? "साप्ताहिक समय-सारणी जोड़ें" : "Add a recurring weekly schedule"}</h2>
                <label>{hi ? "सप्ताह का दिन" : "Weekday"}<select value={scheduleForm.day_of_week} onChange={(event) => setScheduleForm({ ...scheduleForm, day_of_week: event.target.value })}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
                <div className="cv-form-row">
                  <label>{hi ? "शुरू" : "Start"}<input type="time" value={scheduleForm.starts_at} onChange={(event) => setScheduleForm({ ...scheduleForm, starts_at: event.target.value })} /></label>
                  <label>{hi ? "समाप्त" : "End"}<input type="time" value={scheduleForm.ends_at} onChange={(event) => setScheduleForm({ ...scheduleForm, ends_at: event.target.value })} /></label>
                </div>
                <label>{hi ? "परामर्श प्रकार" : "Consultation type"}<select value={scheduleForm.consultation_type} onChange={(event) => setScheduleForm({ ...scheduleForm, consultation_type: event.target.value })}><option value="in_person">In person</option><option value="online">Online</option><option value="phone">Phone</option></select></label>
                <button className="cv-button cv-button-primary" disabled={saving}>{hi ? "समय-सारणी सेव करें" : "Save schedule"}</button>
                <p className="cv-subtle">{hi ? "यह साप्ताहिक समय है, तत्काल उपलब्ध स्लॉट नहीं।" : "This publishes recurring hours; it does not claim real-time slot availability."}</p>
              </form>
              <section className="cv-card">
                <h2>{hi ? "प्रकाशित समय-सारणी" : "Published weekly schedule"}</h2>
                {dashboard.doctor.schedules.length ? dashboard.doctor.schedules.map((schedule) => <div className="cv-review-row" key={schedule.id}><span>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][schedule.day_of_week]} · {schedule.starts_at.slice(0, 5)}–{schedule.ends_at.slice(0, 5)} ({schedule.timezone}) · {schedule.consultation_type.replaceAll("_", " ")}</span><button className="cv-button cv-button-quiet" type="button" disabled={saving} onClick={() => removeSchedule(schedule.id)}>{hi ? "हटाएँ" : "Remove"}</button></div>) : <p className="cv-subtle">{hi ? "अभी कोई समय-सारणी प्रकाशित नहीं है।" : "No recurring hours are published yet."}</p>}
              </section>
              <section className="cv-card">
                <h2>{hi ? "योग्यताएँ" : "Qualifications"}</h2>
                {dashboard.doctor.qualifications.length ? dashboard.doctor.qualifications.map((qualification) => <p key={qualification.id}>{qualification.degree} · {qualification.institution} · {qualification.verification_status}</p>) : <p className="cv-subtle">{hi ? "योग्यताएँ अभी दर्ज नहीं हैं।" : "No qualifications are recorded on this profile."}</p>}
                <form className="cv-form" onSubmit={addQualification}>
                  <label>{hi ? "डिग्री" : "Degree"}<input required value={qualificationForm.degree} onChange={(event) => setQualificationForm({ ...qualificationForm, degree: event.target.value })} /></label>
                  <label>{hi ? "संस्थान" : "Institution"}<input required value={qualificationForm.institution} onChange={(event) => setQualificationForm({ ...qualificationForm, institution: event.target.value })} /></label>
                  <label>{hi ? "समाप्ति वर्ष" : "Completion year"}<input type="number" min="1950" max="2100" value={qualificationForm.completion_year} onChange={(event) => setQualificationForm({ ...qualificationForm, completion_year: event.target.value })} /></label>
                  <button className="cv-button cv-button-secondary" disabled={saving}>{hi ? "योग्यता जोड़ें" : "Add qualification"}</button>
                </form>
              </section>
            </>
          )}
          {dashboard.hospital && (
            <>
              <div className="cv-metrics"><MetricCard icon="♙" label={hi ? "डॉक्टर" : "Doctors"} value={dashboard.doctor_count} note={hi ? "इस अस्पताल में" : "Assigned to this hospital"} /><MetricCard icon="▦" label={hi ? "अपॉइंटमेंट" : "Appointments"} value={dashboard.appointment_count} note={hi ? "इस अस्पताल में" : "Scoped to this hospital"} /></div>
              {user?.role === "hospital_admin" && (
                <>
                  <form className="cv-card cv-form" onSubmit={saveHospital}>
                    <h2>{hi ? "अस्पताल प्रोफ़ाइल" : "Hospital profile"}</h2>
                    {Object.entries(hospitalForm).map(([field, value]) => <label key={field}>{field.replaceAll("_", " ")}<input value={value} onChange={(event) => setHospitalForm({ ...hospitalForm, [field]: event.target.value })} /></label>)}
                    <button className="cv-button cv-button-primary" disabled={saving}>{hi ? "बदलाव सेव करें" : "Save hospital details"}</button>
                  </form>
                  <form className="cv-card cv-form" onSubmit={addDoctor}>
                    <h2>{hi ? "डॉक्टर प्रोफ़ाइल जोड़ें" : "Add a clinician profile"}</h2>
                    <label>{hi ? "पूरा नाम" : "Full name"}<input required minLength={2} value={newDoctor.full_name} onChange={(event) => setNewDoctor({ ...newDoctor, full_name: event.target.value })} /></label>
                    <label>{hi ? "विशेषज्ञता" : "Specialty"}<input required value={newDoctor.specialty} onChange={(event) => setNewDoctor({ ...newDoctor, specialty: event.target.value })} /></label>
                    <div className="cv-form-row">
                      <label>{hi ? "अनुभव (वर्ष)" : "Experience (years)"}<input type="number" min="0" max="80" value={newDoctor.experience_years} onChange={(event) => setNewDoctor({ ...newDoctor, experience_years: event.target.value })} /></label>
                      <label>{hi ? "परामर्श शुल्क (₹)" : "Consultation fee (₹)"}<input type="number" min="0" max="100000" step="0.01" value={newDoctor.fee} onChange={(event) => setNewDoctor({ ...newDoctor, fee: event.target.value })} /></label>
                    </div>
                    <label>{hi ? "परिचय" : "Biography"}<textarea rows={3} maxLength={2000} value={newDoctor.bio} onChange={(event) => setNewDoctor({ ...newDoctor, bio: event.target.value })} /></label>
                    <button className="cv-button cv-button-secondary" disabled={saving}>{hi ? "समीक्षा हेतु भेजें" : "Create pending profile"}</button>
                  </form>
                </>
              )}
              <section className="cv-card">
                <h2>{hi ? "इस अस्पताल के डॉक्टर" : "Clinicians at this hospital"}</h2>
                {dashboard.doctors?.length ? dashboard.doctors.map((doctor) => <div className="cv-review-row" key={doctor.id}>
                  <span><strong>{doctor.full_name}</strong><br />{doctor.specialties.join(", ")} · {doctor.verification_status} · {doctor.schedules.length} {hi ? "समय-सारणी" : "schedule entries"}</span>
                </div>) : <p className="cv-subtle">{hi ? "अभी डॉक्टर प्रोफ़ाइल नहीं हैं।" : "No clinician profiles are assigned to this hospital."}</p>}
              </section>
            </>
          )}
          {dashboard.role === "platform_admin" && (
            <>
              <div className="cv-metrics"><MetricCard icon="⌂" label="Hospitals" value={dashboard.hospital_count} note="Persistent provider records" /><MetricCard icon="♙" label="Doctors" value={dashboard.doctor_count} note="Persistent provider records" /><MetricCard icon="!" label="Pending review" value={dashboard.pending_hospitals + dashboard.pending_doctors} note="Not shown in public directory" /></div>
              <form className="cv-card cv-form" onSubmit={addHospital}>
                <h2>{hi ? "अस्पताल प्रोफ़ाइल जोड़ें" : "Add a hospital profile"}</h2>
                <label>{hi ? "अस्पताल का नाम" : "Hospital name"}<input required minLength={2} maxLength={180} value={newHospital.name} onChange={(event) => setNewHospital({ ...newHospital, name: event.target.value })} /></label>
                <div className="cv-form-row">
                  <label>{hi ? "शहर" : "City"}<input required maxLength={80} value={newHospital.city} onChange={(event) => setNewHospital({ ...newHospital, city: event.target.value })} /></label>
                  <label>{hi ? "राज्य" : "State"}<input required maxLength={80} value={newHospital.state} onChange={(event) => setNewHospital({ ...newHospital, state: event.target.value })} /></label>
                </div>
                <label>{hi ? "पता (वैकल्पिक)" : "Address (optional)"}<input maxLength={255} value={newHospital.address} onChange={(event) => setNewHospital({ ...newHospital, address: event.target.value })} /></label>
                <div className="cv-form-row">
                  <label>{hi ? "फोन (वैकल्पिक)" : "Phone (optional)"}<input type="tel" maxLength={32} value={newHospital.phone} onChange={(event) => setNewHospital({ ...newHospital, phone: event.target.value })} /></label>
                  <label>{hi ? "वेबसाइट (वैकल्पिक)" : "Website (optional)"}<input type="url" maxLength={255} value={newHospital.website} onChange={(event) => setNewHospital({ ...newHospital, website: event.target.value })} /></label>
                </div>
                <label>{hi ? "सेवाएँ / विभाग" : "Services / departments"}<input maxLength={1000} value={newHospital.departments} onChange={(event) => setNewHospital({ ...newHospital, departments: event.target.value })} /></label>
                <label>{hi ? "विवरण" : "Description"}<textarea rows={3} maxLength={2000} value={newHospital.description} onChange={(event) => setNewHospital({ ...newHospital, description: event.target.value })} /></label>
                <button className="cv-button cv-button-primary" disabled={saving}>{hi ? "समीक्षा हेतु भेजें" : "Create pending hospital"}</button>
              </form>
              <section className="cv-card">
                <h2>{hi ? "सत्यापन समीक्षा कतार" : "Verification review queue"}</h2>
                {[...reviewQueue.hospitals.map((item) => ({ ...item, kind: "hospitals" })), ...reviewQueue.doctors.map((item) => ({ ...item, kind: "doctors" })), ...reviewQueue.qualifications.map((item) => ({ ...item, kind: "qualifications" }))].map((item) => (
                  <div className="cv-review-row" key={`${item.kind}-${item.id}`}><span>{item.kind === "hospitals" ? `Hospital · ${item.name}` : item.kind === "doctors" ? `Doctor · ${item.full_name} · ${item.specialty}` : `Qualification · ${item.degree} · ${item.institution} (doctor ${item.doctor_id})`}</span><button className="cv-button cv-button-secondary" disabled={saving} onClick={() => review(item.kind, item.id)}>{hi ? "सत्यापित करें" : "Verify"}</button></div>
                ))}
                {!reviewQueue.hospitals.length && !reviewQueue.doctors.length && !reviewQueue.qualifications.length && <p className="cv-subtle">{hi ? "कोई प्रोफ़ाइल समीक्षा की प्रतीक्षा में नहीं है।" : "No provider profiles are awaiting review."}</p>}
              </section>
            </>
          )}
          {dashboard.role === "hospital_staff" && <section className="cv-card"><ScreenTitle title={dashboard.hospital.name} description={`${dashboard.hospital.city}, ${dashboard.hospital.state}`} /><p>{hi ? "यह केवल-पठन कार्यक्षेत्र है।" : "This hospital staff workspace is read-only."}</p></section>}
        </div>
      )}
    </>
  );
}

// Searchable directory of verified doctors and hospitals with AI matching and slot booking workflows.
export function CareDirectoryPage({ token, onNavigate, onAppointmentBooked, language = "en", canBook = true }) {
  const [doctors, setDoctors] = useState([]);
  const [hospitals, setHospitals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [directoryError, setDirectoryError] = useState("");
  const [bookingError, setBookingError] = useState("");
  const [activeModalProfile, setActiveModalProfile] = useState(null); // { type: "doctors" | "hospitals", id: string | number }
  const [query, setQuery] = useState("");
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [scheduledFor, setScheduledFor] = useState("");
  const bookingCommandRef = useRef(null);
  const [consultationType, setConsultationType] = useState("in_person");
  const [notes, setNotes] = useState("");
  const [doctorOffset, setDoctorOffset] = useState(0);
  const [hospitalOffset, setHospitalOffset] = useState(0);
  const [directoryTotals, setDirectoryTotals] = useState({ doctors: 0, hospitals: 0 });
  const [recommendationInput, setRecommendationInput] = useState({ symptoms: "", specialty: "", city: "", language: "", consultation_type: "" });
  const [recommendations, setRecommendations] = useState([]);
  const [recommendationBusy, setRecommendationBusy] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const [recommendationsLoaded, setRecommendationsLoaded] = useState(false);
  const pageSize = 12;
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const bookDialogRef = useRef(null);
  const bookingTriggerRef = useRef(null);
  const savingRef = useRef(saving);
  const profileDetailsRef = useRef({});
  const profileRequestsRef = useRef(new Map());
  const hi = language === "hi";

  useEffect(() => { savingRef.current = saving; }, [saving]);

  async function loadDirectory(signal) {
    setLoading(true);
    setDirectoryError("");
    try {
      const createParams = (offset) => {
        const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
        if (query.trim()) params.set("search", query.trim());
        return params;
      };
      const [doctorPage, hospitalPage] = await Promise.all([
        apiRequest(`/providers/doctors?${createParams(doctorOffset)}`, token, { signal }),
        apiRequest(`/providers/hospitals?${createParams(hospitalOffset)}`, token, { signal }),
      ]);
      if (signal?.aborted) return;
      setDoctors(doctorPage.items);
      setHospitals(hospitalPage.items);
      setDirectoryTotals({ doctors: doctorPage.total, hospitals: hospitalPage.total });
    } catch (reason) {
      if (signal?.aborted) return;
      setDirectoryError(reason?.message || "Please try again.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    loadDirectory(controller.signal);
    return () => controller.abort();
  }, [token, query, doctorOffset, hospitalOffset]);
  useEffect(() => {
    if (!selectedDoctor) return undefined;
    bookDialogRef.current?.querySelector("input, select, button")?.focus();
    function closeOnEscape(event) {
      if (event.key === "Escape" && !savingRef.current) setSelectedDoctor(null);
      if (event.key === "Tab" && bookDialogRef.current) {
        const focusable = [...bookDialogRef.current.querySelectorAll("button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex='-1'])")];
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      bookingTriggerRef.current?.focus();
    };
  }, [selectedDoctor]);

  async function loadProviderProfile(type, profileId) {
    const key = `${type}:${profileId}`;
    if (profileDetailsRef.current[key]) return profileDetailsRef.current[key];
    if (profileRequestsRef.current.has(key)) return profileRequestsRef.current.get(key);
    setProfileLoadingKey(key);
    setProfileErrors((current) => ({ ...current, [key]: "" }));
    const request = apiRequest(`/providers/${type}/${profileId}`, token)
      .then((fullProfile) => {
        profileDetailsRef.current[key] = fullProfile;
        setProfileDetails((current) => ({ ...current, [key]: fullProfile }));
        return fullProfile;
      })
      .catch((reason) => {
        const message = reason?.message || (hi ? "विवरण लोड नहीं हो सके।" : "Details could not be loaded.");
        setProfileErrors((current) => ({ ...current, [key]: message }));
        return null;
      })
      .finally(() => {
        profileRequestsRef.current.delete(key);
        setProfileLoadingKey((current) => current === key ? null : current);
      });
    profileRequestsRef.current.set(key, request);
    return await request;
  }

  async function showProfile(type, profile) {
    const key = `${type}:${profile.id}`;
    if (expandedProfileKey === key) {
      setExpandedProfileKey(null);
      return;
    }
    setExpandedProfileKey(key);
    await loadProviderProfile(type, profile.id);
  }

  function renderProfileDetails(type, profileId) {
    const key = `${type}:${profileId}`;
    const expanded = expandedProfileKey === key;
    return (
      <div className="cv-provider-inline-details" id={`provider-details-${type}-${profileId}`} aria-live="polite" hidden={!expanded}>
        {expanded && <ProviderInlineDetails
            type={type}
            detail={profileDetails[key]}
            loading={profileLoadingKey === key}
            error={profileErrors[key]}
            onRetry={() => loadProviderProfile(type, profileId)}
            language={language}
          />}
      </div>
    );
  }

  async function getRecommendations(event) {
    event?.preventDefault?.();
    setRecommendationBusy(true);
    setRecommendationError("");
    setRecommendations([]);
    setRecommendationsLoaded(false);
    try {
      const payload = Object.fromEntries(
        Object.entries(recommendationInput).map(([key, value]) => [
          key,
          value.trim() || (key === "symptoms" ? "" : null),
        ]),
      );
      setRecommendations(await apiRequest("/providers/recommendations", token, {
        method: "POST",
        body: JSON.stringify(payload),
      }));
      setRecommendationsLoaded(true);
    } catch (reason) {
      setRecommendationError(reason?.message || "Recommendations could not be loaded.");
    } finally {
      setRecommendationBusy(false);
    }
  }

  async function bookVisit(event) {
    event.preventDefault();
    if (!selectedDoctor || !scheduledFor || saving) return;
    setSaving(true);
    setBookingError("");
    setNotice("");
    try {
      const booking = {
        doctor_id: selectedDoctor.id,
        scheduled_for: scheduledFor,
        consultation_type: consultationType,
        notes: notes.trim() || null,
      };
      const fingerprint = JSON.stringify(booking);
      if (bookingCommandRef.current?.fingerprint !== fingerprint) {
        bookingCommandRef.current = { fingerprint, key: createIdempotencyKey() };
      }
      const createdAppointment = await apiRequest("/providers/appointments", token, {
        method: "POST",
        headers: { "Idempotency-Key": bookingCommandRef.current.key },
        body: JSON.stringify(booking),
      });
      if (!createdAppointment?.id || createdAppointment.status !== "scheduled") {
        throw new Error(hi ? "सर्वर ने बुकिंग की पुष्टि नहीं की।" : "The server did not confirm the appointment booking.");
      }
      setNotice(hi ? "अपॉइंटमेंट बुक हो गया है।" : "Your appointment was booked successfully.");
      setSelectedDoctor(null);
      setScheduledFor("");
      setNotes("");
      bookingCommandRef.current = null;
      if (onAppointmentBooked) onAppointmentBooked(createdAppointment);
      else onNavigate("Appointments");
    } catch (reason) {
      setBookingError(reason?.message || (hi ? "अपॉइंटमेंट बुक नहीं हो पाया।" : "The appointment could not be booked."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <ScreenTitle title={hi ? "देखभाल खोजें" : "Find care"} description={hi ? "डॉक्टर और अस्पतालों की लाइव डायरेक्टरी ब्राउज़ करें।" : "Browse the live doctor and hospital directory. Bookings are sent to the clinic API."} />
      {directoryError && <InlineError message={directoryError} onRetry={() => loadDirectory()} />}
      {bookingError && !selectedDoctor && <InlineError message={bookingError} />}
      {notice && <div className="cv-success" role="status">{notice}</div>}
      <label className="cv-search">
        <span aria-hidden="true">⌕</span>
        <span className="cv-sr-only">{hi ? "नाम, विशेषज्ञता या शहर से खोजें" : "Search by name, specialty, or location"}</span>
        <input value={query} onChange={(event) => { setQuery(event.target.value); setDoctorOffset(0); setHospitalOffset(0); }} placeholder={hi ? "डॉक्टर, विशेषज्ञता या शहर खोजें…" : "Search doctors, specialties, hospitals, or cities…"} />
        {query && <button type="button" onClick={() => setQuery("")} aria-label={hi ? "खोज साफ़ करें" : "Clear search"}>×</button>}
      </label>
      <form className="cv-card cv-form cv-recommendation-form" onSubmit={getRecommendations}>
        <div><span className="eyebrow">{hi ? "पारदर्शी मिलान" : "EXPLAINABLE MATCHING"}</span><h2>{hi ? "देखभाल विकल्प खोजें" : "Explore matching care options"}</h2></div>
        <label>{hi ? "लक्षण या विशेषज्ञता" : "Symptoms or specialty"}<textarea rows={2} maxLength={1000} value={recommendationInput.symptoms} onChange={(event) => setRecommendationInput({ ...recommendationInput, symptoms: event.target.value })} placeholder={hi ? "उदाहरण: सीने में दर्द" : "For example: chest pain"} /></label>
        <div className="cv-form-row">
          <label>{hi ? "शहर" : "City"}<input value={recommendationInput.city} onChange={(event) => setRecommendationInput({ ...recommendationInput, city: event.target.value })} /></label>
          <label>{hi ? "भाषा" : "Language"}<input value={recommendationInput.language} onChange={(event) => setRecommendationInput({ ...recommendationInput, language: event.target.value })} placeholder="Hindi, English…" /></label>
        </div>
        <div className="cv-form-row">
          <label>{hi ? "विशेषज्ञता" : "Specialty"}<input value={recommendationInput.specialty} onChange={(event) => setRecommendationInput({ ...recommendationInput, specialty: event.target.value })} /></label>
          <label>{hi ? "परामर्श प्रकार" : "Consultation type"}<select value={recommendationInput.consultation_type} onChange={(event) => setRecommendationInput({ ...recommendationInput, consultation_type: event.target.value })}><option value="">{hi ? "कोई भी" : "Any"}</option><option value="in_person">In person</option><option value="online">Online</option><option value="phone">Phone</option></select></label>
        </div>
        <button className="cv-button cv-button-secondary" disabled={recommendationBusy}>{recommendationBusy ? (hi ? "खोज रहे हैं…" : "Finding matches…") : (hi ? "मिलान देखें" : "Show matches")}</button>
        <p className="cv-subtle">{hi ? "मिलान केवल सत्यापित प्रोफ़ाइल के प्रकाशित मानदंडों पर आधारित हैं। यह निदान या डॉक्टर की गुणवत्ता रेटिंग नहीं है।" : "Matches use only verified profiles and the criteria you provide. They are not a diagnosis or provider-quality ratings."}</p>
      </form>
      {recommendationError && <InlineError message={recommendationError} onRetry={() => getRecommendations()} />}
      {recommendationsLoaded && recommendations.length === 0 && <EmptyState title={hi ? "कोई मेल नहीं मिला" : "No matching providers"} description={hi ? "प्रकाशित सत्यापित प्रोफ़ाइल आपके दिए मानदंडों से मेल नहीं खातीं। मानदंड बदलकर फिर प्रयास करें।" : "No verified published profiles match those criteria. Adjust the filters and try again."} />}
      {recommendations.length > 0 && <section className="cv-section" aria-label={hi ? "मेल खाते प्रदाता" : "Matching providers"}>
        <div className="cv-section-heading"><h2>{hi ? "मेल खाते विकल्प" : "Matching options"}</h2><span className="cv-count">{recommendations.length}</span></div>
        <div className="cv-doctor-grid">{recommendations.map((item) => <article className="cv-doctor-card" key={item.doctor_id}>
          <h3>{item.doctor_name}</h3><p className="cv-specialty">{item.specialty}</p><p className="cv-location">{item.hospital_name || (hi ? "स्वतंत्र प्रदाता" : "Independent provider")}</p>
          <p><strong>{hi ? "मानदंड मिलान" : "Criteria match"}: {Math.round(item.score * 100)}%</strong></p>
          <ul>{item.match_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          <p className="cv-subtle">{item.availability_note}</p>
          <button
            className="cv-button cv-button-quiet"
            type="button"
            onClick={() => setActiveModalProfile({ type: "doctors", id: item.doctor_id })}
          >{hi ? "प्रोफ़ाइल देखें" : "View profile"}</button>
        </article>)}</div>
      </section>}
      {loading ? <LoadingState label={hi ? "केयर डायरेक्टरी लोड हो रही है…" : "Loading the care directory…"} /> : (
        <>
          {directoryError ? null : <section className="cv-section">
            <div className="cv-section-heading"><div><span className="eyebrow">{hi ? "चिकित्सक" : "CLINICIANS"}</span><h2>{hi ? "डॉक्टर" : "Doctors"}</h2></div><span className="cv-count">{directoryTotals.doctors}</span></div>
            {doctors.length ? <div className="cv-doctor-grid">{doctors.map((doctor) => (
              <article className="cv-doctor-card" key={doctor.id}>
                <div className="cv-doctor-avatar" aria-hidden="true">{doctor.full_name?.trim().charAt(0)?.toUpperCase() || "D"}</div>
                <div className="cv-doctor-name"><h3>{doctor.full_name}</h3><span className={`cv-verification ${doctor.verified ? "" : "unverified"}`}>{doctor.verified ? (hi ? "सत्यापित" : "Verified") : (hi ? "असत्यापित" : "Not verified")}</span></div>
                <p className="cv-specialty">{(doctor.specialties || [doctor.specialty]).join(" · ")}</p>
                <p className="cv-location">{doctor.hospital_name || (hi ? "स्वतंत्र प्रदाता" : "Independent provider")}</p>
                <div className="cv-doctor-meta"><span>{doctor.languages?.join(", ") || (hi ? "भाषाएँ सूचीबद्ध नहीं" : "Languages not listed")}</span><strong>{formatMoney(doctor.fee_minor)}</strong></div>
                <p className="cv-subtle">{doctor.consultation_types?.map((item) => item.replaceAll("_", " ")).join(" · ")}</p>
                <div className="cv-card-actions">
                  <button
                    className="cv-button cv-button-quiet"
                    type="button"
                    onClick={() => setActiveModalProfile({ type: "doctors", id: doctor.id })}
                  >{hi ? "प्रोफ़ाइल देखें" : "View profile"}</button>
                  {canBook && <button ref={bookingTriggerRef} className="cv-button cv-button-primary" disabled={!doctor.is_active || !doctor.schedules?.some((item) => item.is_active)} onClick={() => { bookingTriggerRef.current = document.activeElement; setSelectedDoctor(doctor); setScheduledFor(""); setConsultationType(doctor.consultation_types?.[0] || "in_person"); setBookingError(""); setNotice(""); }}>
                    {!doctor.is_active ? (hi ? "अनुपलब्ध" : "Unavailable") : !doctor.schedules?.some((item) => item.is_active) ? (hi ? "समय-सारणी नहीं" : "No schedule") : (hi ? "बुक करें" : "Book visit")}
                  </button>}
                </div>
              </article>
            ))}</div> : <EmptyState title={hi ? "कोई डॉक्टर नहीं मिला" : "No doctors found"} description={hi ? "दूसरा नाम या विशेषज्ञता खोजें।" : "No verified providers match this search."} />}
          </section>}
          {directoryError ? null : <section className="cv-section">
            <div className="cv-section-heading"><div><span className="eyebrow">{hi ? "देखभाल केंद्र" : "CARE LOCATIONS"}</span><h2>{hi ? "अस्पताल" : "Hospitals"}</h2></div><span className="cv-count">{directoryTotals.hospitals}</span></div>
            {hospitals.length ? <div className="cv-hospital-grid">{hospitals.map((hospital) => (
              <article className="cv-hospital-card" key={hospital.id}>
                <span className="cv-hospital-icon" aria-hidden="true">⌂</span>
                <div><div className="cv-doctor-name"><h3>{hospital.name}</h3><span className={`cv-verification ${hospital.verified ? "" : "unverified"}`}>{hospital.verified ? (hi ? "सत्यापित" : "Verified") : (hi ? "असत्यापित" : "Not verified")}</span></div>
                  <p className="cv-location">{hospital.city}, {hospital.state}</p><p className="cv-specialty">{hospital.departments}</p>
                  {hospital.description && <p className="cv-subtle">{hospital.description}</p>}
                  <div className="cv-card-actions">
                    <button
                      className="cv-button cv-button-quiet"
                      type="button"
                      onClick={() => setActiveModalProfile({ type: "hospitals", id: hospital.id })}
                    >{hi ? "अस्पताल विवरण" : "View hospital"}</button>
                  </div>
                </div>
              </article>
            ))}</div> : <EmptyState title={hi ? "अभी कोई अस्पताल सूचीबद्ध नहीं" : "No hospitals listed"} description={hi ? "क्लिनिक ने अभी कोई अस्पताल रिकॉर्ड उपलब्ध नहीं कराया है।" : "The clinic has not provided any hospital records yet."} />}
          </section>}
          {!directoryError && directoryTotals.doctors > pageSize && <nav className="cv-directory-pagination" aria-label={hi ? "डॉक्टर डायरेक्टरी पृष्ठ" : "Doctor directory pages"}>
            <button className="cv-button cv-button-quiet" disabled={doctorOffset === 0} onClick={() => setDoctorOffset(Math.max(0, doctorOffset - pageSize))}>{hi ? "पिछला डॉक्टर" : "Previous doctors"}</button>
            <span>{hi ? "डॉक्टर पृष्ठ" : "Doctor page"} {Math.floor(doctorOffset / pageSize) + 1}</span>
            <button className="cv-button cv-button-quiet" disabled={doctorOffset + pageSize >= directoryTotals.doctors} onClick={() => setDoctorOffset(doctorOffset + pageSize)}>{hi ? "अगले डॉक्टर" : "Next doctors"}</button>
          </nav>}
          {!directoryError && directoryTotals.hospitals > pageSize && <nav className="cv-directory-pagination" aria-label={hi ? "अस्पताल डायरेक्टरी पृष्ठ" : "Hospital directory pages"}>
            <button className="cv-button cv-button-quiet" disabled={hospitalOffset === 0} onClick={() => setHospitalOffset(Math.max(0, hospitalOffset - pageSize))}>{hi ? "पिछले अस्पताल" : "Previous hospitals"}</button>
            <span>{hi ? "अस्पताल पृष्ठ" : "Hospital page"} {Math.floor(hospitalOffset / pageSize) + 1}</span>
            <button className="cv-button cv-button-quiet" disabled={hospitalOffset + pageSize >= directoryTotals.hospitals} onClick={() => setHospitalOffset(hospitalOffset + pageSize)}>{hi ? "अगले अस्पताल" : "Next hospitals"}</button>
          </nav>}
        </>
      )}
      {selectedDoctor && (
        <div className="cv-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setSelectedDoctor(null); }}>
          <section ref={bookDialogRef} className="cv-dialog" role="dialog" aria-modal="true" aria-labelledby="cv-book-title" aria-describedby="cv-book-description">
            <button className="cv-dialog-close" type="button" aria-label={hi ? "बंद करें" : "Close"} disabled={saving} onClick={() => setSelectedDoctor(null)}>×</button>
            <span className="eyebrow">{hi ? "अपॉइंटमेंट" : "APPOINTMENT"}</span>
            <h2 id="cv-book-title">{hi ? "अपॉइंटमेंट बुक करें" : "Book a visit"}</h2>
            <p id="cv-book-description" className="cv-subtle">{selectedDoctor.full_name} · {selectedDoctor.specialty}</p>
            <p className="cv-subtle">{selectedDoctor.hospital_name || (hi ? "स्वतंत्र प्रदाता" : "Independent provider")} · {hi ? "परामर्श शुल्क" : "Consultation fee"}: <strong>{formatMoney(selectedDoctor.fee_minor)}</strong>. {hi ? "अभी अग्रिम भुगतान आवश्यक नहीं है; क्लिनिक बाद में इनवॉइस जारी कर सकता है।" : "No advance payment is required for booking; the clinic may issue an invoice afterward."}</p>
            {selectedDoctor.schedules?.length ? <div className="cv-subtle">{selectedDoctor.schedules.filter((item) => item.is_active).map((item) => <p key={item.id}>{["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][item.day_of_week]} · {item.starts_at.slice(0, 5)}–{item.ends_at.slice(0, 5)} ({item.timezone})</p>)}</div> : <p className="cv-subtle">{hi ? "डॉक्टर की समय-सारणी उपलब्ध नहीं है।" : "No published schedule is available."}</p>}
            {bookingError && <InlineError message={bookingError} />}
            <form className="cv-form" onSubmit={bookVisit}>
              <label>{hi ? "परामर्श का प्रकार" : "Consultation type"}<select value={consultationType} onChange={(event) => { setConsultationType(event.target.value); setScheduledFor(""); }}>{(selectedDoctor.consultation_types || ["in_person"]).map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></label>
              <AppointmentSlotPicker token={token} doctorId={selectedDoctor.id} consultationType={consultationType} value={scheduledFor} onChange={setScheduledFor} language={language} />
              <label>{hi ? "नोट (वैकल्पिक)" : "Note (optional)"}<textarea rows={3} maxLength={500} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={hi ? "क्लिनिक के लिए संदेश" : "A short note for the clinic"} /></label>
              <p className="cv-subtle">{hi ? "समय भारतीय मानक समय (IST) में दिखाए गए हैं।" : "Times are shown in Indian Standard Time (IST). Your booking is confirmed only after the clinic API succeeds."}</p>
              <button className="cv-button cv-button-primary cv-full" disabled={saving || !scheduledFor}>{saving ? (hi ? "भेजा जा रहा है…" : "Submitting…") : (hi ? "अपॉइंटमेंट की पुष्टि करें" : "Confirm appointment")}</button>
            </form>
          </section>
        </div>
      )}
      <ProviderDetailModal
        isOpen={Boolean(activeModalProfile)}
        onClose={() => setActiveModalProfile(null)}
        type={activeModalProfile?.type}
        profileId={activeModalProfile?.id}
        token={token}
        language={language}
      />
    </>
  );
}

// Appointment lifecycle view managing visit scheduling, rescheduling, cancellations, slips, and payment flows.
export function AppointmentsPage({ token, language = "en", user, patient, recentAppointment, onNavigate }) {
  const [appointments, setAppointments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cancellingId, setCancellingId] = useState(null);
  const [confirmingId, setConfirmingId] = useState(null);
  const [selectedRescheduleAppointment, setSelectedRescheduleAppointment] = useState(null);
  const [rescheduleTime, setRescheduleTime] = useState("");
  const [rescheduleType, setRescheduleType] = useState("in_person");
  const [rescheduleReason, setRescheduleReason] = useState("");
  const [rescheduleBusy, setRescheduleBusy] = useState(false);
  const [selectedHistoryAppointment, setSelectedHistoryAppointment] = useState(null);
  const [historyById, setHistoryById] = useState({});
  const [historyLoadingId, setHistoryLoadingId] = useState(null);
  const [paymentStartId, setPaymentStartId] = useState(null);
  const [selectedReceiptAppointment, setSelectedReceiptAppointment] = useState(null);
  const rescheduleCommandRef = useRef(null);
  const hi = language === "hi";

  async function loadAppointments() {
    setLoading(true);
    setError("");
    try {
      setAppointments(await apiRequest("/providers/appointments", token));
    } catch (reason) {
      setError(reason?.message || "Please try again.");
    } finally {
      setLoading(false);
    }
  }
  async function startAppointmentPayment(appointment) {
    if (paymentStartId !== null) return;
    setPaymentStartId(appointment.id);
    setError("");
    try {
      let invoiceId = appointment.invoice_id;
      if (!invoiceId) {
        const invoice = await apiRequest(`/billing/appointments/${appointment.id}/invoice`, token, { method: "POST" });
        invoiceId = invoice.id;
      }
      onNavigate?.("Billing", { invoiceId, action: appointment.invoice_status === "paid" ? "receipt" : "pay" });
    } catch (reason) {
      setError(reason?.message || (hi ? "भुगतान इनवॉइस नहीं बनाया जा सका।" : "The consultation invoice could not be prepared."));
    } finally {
      setPaymentStartId(null);
    }
  }
  useEffect(() => { loadAppointments(); }, [token]);
  useEffect(() => {
    if (!recentAppointment) return;
    setAppointments((current) => [
      recentAppointment,
      ...current.filter((item) => item.id !== recentAppointment.id),
    ]);
  }, [recentAppointment]);

  async function cancelAppointment(appointment) {
    if (!window.confirm(hi ? "क्या आप यह अपॉइंटमेंट रद्द करना चाहते हैं? भुगतान अपने आप वापस नहीं होगा; भुगतान किए गए अपॉइंटमेंट के रिफंड की समीक्षा क्लिनिक एडमिन करेगा।" : "Cancel this appointment? Cancellation does not automatically refund a payment. A clinic administrator must review any refund for a paid appointment.")) return;
    setCancellingId(appointment.id);
    setError("");
    try {
      const updated = await apiRequest(`/providers/appointments/${appointment.id}/cancel`, token, { method: "PATCH" });
      setAppointments((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason?.message || (hi ? "अपॉइंटमेंट रद्द नहीं हो पाया।" : "The appointment could not be cancelled."));
    } finally {
      setCancellingId(null);
    }
  }

  async function confirmAppointment(appointment) {
    setConfirmingId(appointment.id);
    setError("");
    try {
      const updated = await apiRequest(`/providers/appointments/${appointment.id}/confirm`, token, { method: "POST" });
      setAppointments((current) => current.map((item) => item.id === updated.id ? updated : item));
      await loadAppointmentHistory(updated.id);
    } catch (reason) {
      setError(reason?.message || (hi ? "अपॉइंटमेंट की पुष्टि नहीं हो सकी।" : "The appointment could not be confirmed."));
    } finally {
      setConfirmingId(null);
    }
  }

  async function downloadAppointmentSlip(appointmentId) {
    try {
      const resp = await fetch(`${API_BASE}/records/appointments/${appointmentId}/confirmation/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
      const blob = await resp.blob();
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = `appointment-confirmation-${appointmentId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objUrl);
    } catch (err) {
      alert(`Could not download appointment slip: ${err.message}`);
    }
  }

  async function loadAppointmentHistory(appointment) {
    setSelectedHistoryAppointment(appointment);
    setHistoryLoadingId(appointment.id);
    setError("");
    try {
      const events = await apiRequest(`/providers/appointments/${appointment.id}/history`, token);
      setHistoryById((current) => ({ ...current, [appointment.id]: events }));
    } catch (reason) {
      setError(reason?.message || (hi ? "इतिहास लोड नहीं हो सका।" : "Appointment history could not be loaded."));
    } finally {
      setHistoryLoadingId(null);
    }
  }

  async function rescheduleAppointment(event, appointment) {
    event.preventDefault();
    if (!rescheduleTime || rescheduleBusy) return;
    setRescheduleBusy(true);
    setError("");
    try {
      const command = {
        scheduled_for: rescheduleTime,
        consultation_type: rescheduleType,
        reason: rescheduleReason.trim() || null,
      };
      const fingerprint = JSON.stringify({ appointment_id: appointment.id, ...command });
      if (rescheduleCommandRef.current?.fingerprint !== fingerprint) {
        rescheduleCommandRef.current = { fingerprint, key: createIdempotencyKey() };
      }
      const updated = await apiRequest(`/providers/appointments/${appointment.id}/reschedule`, token, {
        method: "PATCH",
        headers: { "Idempotency-Key": rescheduleCommandRef.current.key },
        body: JSON.stringify(command),
      });
      setAppointments((current) => current.map((item) => item.id === updated.id ? updated : item));
      rescheduleCommandRef.current = null;
      setSelectedRescheduleAppointment(null);
      setRescheduleTime("");
      setRescheduleReason("");
    } catch (reason) {
      setError(reason?.message || (hi ? "अपॉइंटमेंट का समय नहीं बदल सका।" : "The appointment could not be rescheduled."));
    } finally {
      setRescheduleBusy(false);
    }
  }

  const sorted = [...appointments].sort((a, b) => new Date(a.scheduled_for) - new Date(b.scheduled_for));
  const upcoming = sorted.filter((item) => item.status !== "cancelled" && new Date(item.scheduled_for) >= new Date());
  const history = sorted.filter((item) => item.status === "cancelled" || new Date(item.scheduled_for) < new Date());
  const canConfirm = ["doctor", "hospital_staff", "hospital_admin", "platform_admin"].includes(user?.role);

  function listItems(rows, emptyTitle, emptyDescription) {
    return rows.length ? <div className="cv-appointment-list">{rows.map((appointment) => {
      const paymentState = getAppointmentPaymentState(appointment);
      const paymentAction = getAppointmentPaymentAction(paymentState);
      return (
      <article className="cv-appointment-row" key={appointment.id}>
        <span className="cv-date-chip"><b>{formatAppointmentDatePart(appointment.scheduled_for, "day", hi ? "hi-IN" : "en-IN")}</b><small>{formatAppointmentDatePart(appointment.scheduled_for, "month", hi ? "hi-IN" : "en-IN")}</small></span>
        <div className="cv-appointment-details"><h3>{appointment.doctor_name || (hi ? "चिकित्सक" : "Clinician")}</h3><p>{appointment.specialty || (hi ? "विशेषज्ञता सूचीबद्ध नहीं" : "Specialty not listed")} · {appointment.hospital_name || (hi ? "अस्पताल सूचीबद्ध नहीं" : "Location not listed")}</p><time dateTime={appointment.scheduled_for}>{formatAppointmentDateTime(appointment.scheduled_for, hi ? "hi-IN" : "en-IN")} IST</time></div>
        <span className={`cv-status cv-status-${appointment.status}`}>{appointment.status}</span>
        {user?.role === "patient" && <div className="cv-appointment-payment" aria-label={hi ? "भुगतान स्थिति" : "Payment status"}>
          <span>{hi ? "परामर्श शुल्क" : "Consultation fee"}: {formatMoney(appointment.fee_minor)}</span>
          {paymentState === "paid" ? <><span className="cv-status cv-status-paid">{appointment.payment_is_demo ? (hi ? "डेमो भुगतान · वास्तविक भुगतान नहीं" : "DEMO paid · not a real payment") : (hi ? "भुगतान हुआ" : "Paid")}</span><button className="cv-button cv-button-quiet" type="button" onClick={() => setSelectedReceiptAppointment(appointment)}>{hi ? "रसीद देखें" : "View receipt"}</button></> : ["refunded", "partially_refunded"].includes(paymentState) ? <><span className="cv-status">{paymentState === "refunded" ? (hi ? "रिफंड हुआ" : "Refunded") : (hi ? "आंशिक रिफंड" : "Partially refunded")}</span><button className="cv-button cv-button-quiet" type="button" onClick={() => setSelectedReceiptAppointment(appointment)}>{hi ? "विवरण देखें" : "View details"}</button></> : paymentState === "invoice_cancelled" ? <span className="cv-subtle">{hi ? "इनवॉइस रद्द" : "Invoice cancelled"}</span> : paymentAction ? <><span className="cv-subtle">{paymentState === "pending" ? (hi ? "भुगतान लंबित" : "Payment pending") : paymentState === "failed" ? (hi ? "भुगतान विफल" : "Payment failed") : paymentState === "cancelled" ? (hi ? "भुगतान रद्द" : "Payment cancelled") : (hi ? "भुगतान बाकी" : "Payment due")}</span><button className={`cv-button ${paymentAction === "pay" ? "cv-button-primary" : "cv-button-quiet"}`} type="button" disabled={paymentAction === "check_status" ? loading : paymentStartId !== null} onClick={() => paymentAction === "check_status" ? loadAppointments() : startAppointmentPayment(appointment)}>{paymentAction === "check_status" ? (loading ? (hi ? "जाँच रहे हैं…" : "Checking…") : (hi ? "भुगतान स्थिति जाँचें" : "Check payment status")) : paymentStartId === appointment.id ? (hi ? "तैयार हो रहा है…" : "Preparing…") : paymentAction === "retry" ? (hi ? "फिर भुगतान करें" : "Retry payment") : (hi ? "अभी भुगतान करें" : "Pay now")}</button></> : <span className="cv-subtle">{paymentState === "not_due" ? (appointment.payment_block_reason === "past" ? (hi ? "बीते हुए अपॉइंटमेंट के लिए भुगतान उपलब्ध नहीं है" : "Payment unavailable for a past appointment") : appointment.payment_block_reason === "cancelled" ? (hi ? "रद्द अपॉइंटमेंट के लिए भुगतान उपलब्ध नहीं है" : "Payment unavailable for a cancelled appointment") : (hi ? "इस अपॉइंटमेंट के लिए नया भुगतान उपलब्ध नहीं है" : "New payment is unavailable for this appointment")) : (hi ? "क्लिनिक का इनवॉइस अभी जारी नहीं हुआ" : "Clinic invoice not issued yet")}</span>}
        </div>}
        <div className="cv-appointment-actions">
          <button className="cv-button cv-button-quiet cv-button-download" type="button" onClick={() => downloadAppointmentSlip(appointment.id)} title="Download appointment confirmation slip PDF">
            📄 {hi ? "स्लिप (PDF)" : "Slip (PDF)"}
          </button>
          {appointment.status === "scheduled" && canConfirm && <button className="cv-button cv-button-quiet" disabled={confirmingId === appointment.id} onClick={() => confirmAppointment(appointment)}>{confirmingId === appointment.id ? (hi ? "पुष्टि हो रही है…" : "Confirming…") : (hi ? "पुष्टि करें" : "Confirm")}</button>}
          {["scheduled", "confirmed"].includes(appointment.status) && new Date(appointment.scheduled_for) >= new Date() && <button className="cv-button cv-button-quiet" disabled={rescheduleBusy} onClick={() => { setSelectedRescheduleAppointment(appointment); setRescheduleTime(""); setRescheduleType(appointment.consultation_type); setError(""); }}>{hi ? "समय बदलें" : "Reschedule"}</button>}
          {["scheduled", "confirmed"].includes(appointment.status) && new Date(appointment.scheduled_for) >= new Date() && <button className="cv-button cv-button-quiet" disabled={cancellingId === appointment.id} onClick={() => cancelAppointment(appointment)}>{cancellingId === appointment.id ? (hi ? "रद्द हो रहा है…" : "Cancelling…") : (hi ? "रद्द करें" : "Cancel")}</button>}
          <button className="cv-button cv-button-quiet" disabled={historyLoadingId === appointment.id} onClick={() => loadAppointmentHistory(appointment)}>{historyLoadingId === appointment.id ? (hi ? "इतिहास…" : "Loading history…") : (hi ? "इतिहास" : "History")}</button>
        </div>
      </article>
    );
    })}</div> : <EmptyState icon="▦" title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <>
      <ScreenTitle title={hi ? "अपॉइंटमेंट" : "Appointments"} description={hi ? "IST में मुलाक़ातें देखें, बदलें और उनका इतिहास जाँचें।" : "View, manage, and review appointments. All appointment times are shown in IST."} action={<button className="cv-button cv-button-quiet" type="button" onClick={loadAppointments} disabled={loading}>{hi ? "स्थिति रीफ़्रेश करें" : "Refresh status"}</button>} />
      {error && <InlineError message={error} onRetry={loadAppointments} />}
      {loading ? <LoadingState label={hi ? "अपॉइंटमेंट लोड हो रहे हैं…" : "Loading appointments…"} /> : error && appointments.length === 0 ? null : (
        <>
          <section className="cv-card"><div className="cv-card-heading"><div><span className="eyebrow">{hi ? "आगे की योजना" : "PLAN AHEAD"}</span><h2>{hi ? "आगामी मुलाक़ातें" : "Upcoming visits"}</h2></div><span className="cv-count">{upcoming.length}</span></div>{listItems(upcoming, hi ? "कोई आगामी अपॉइंटमेंट नहीं" : "No upcoming appointments", hi ? "केयर डायरेक्टरी से डॉक्टर खोजें और बुक करें।" : "Find a clinician in the care directory and book a visit.")}</section>
          <section className="cv-card"><div className="cv-card-heading"><div><span className="eyebrow">{hi ? "पिछली मुलाक़ातें" : "PAST CARE"}</span><h2>{hi ? "अपॉइंटमेंट इतिहास" : "Appointment history"}</h2></div><span className="cv-count">{history.length}</span></div>{listItems(history, hi ? "अभी कोई इतिहास नहीं" : "No appointment history", hi ? "आपके पुराने या रद्द अपॉइंटमेंट यहाँ दिखेंगे।" : "Past and cancelled appointments will appear here.")}</section>
        </>
      )}
      <AppointmentHistoryModal
        isOpen={Boolean(selectedHistoryAppointment)}
        onClose={() => setSelectedHistoryAppointment(null)}
        appointment={selectedHistoryAppointment}
        history={selectedHistoryAppointment ? (historyById[selectedHistoryAppointment.id] || []) : []}
        loading={Boolean(selectedHistoryAppointment && historyLoadingId === selectedHistoryAppointment.id)}
        language={language}
      />
      <AppointmentRescheduleModal
        isOpen={Boolean(selectedRescheduleAppointment)}
        onClose={() => {
          setSelectedRescheduleAppointment(null);
          setRescheduleTime("");
          setRescheduleReason("");
        }}
        appointment={selectedRescheduleAppointment}
        token={token}
        rescheduleType={rescheduleType}
        setRescheduleType={setRescheduleType}
        rescheduleTime={rescheduleTime}
        setRescheduleTime={setRescheduleTime}
        rescheduleReason={rescheduleReason}
        setRescheduleReason={setRescheduleReason}
        rescheduleBusy={rescheduleBusy}
        onSubmit={rescheduleAppointment}
        SlotPickerComponent={AppointmentSlotPicker}
        language={language}
      />
      <AppointmentReceiptModal
        isOpen={Boolean(selectedReceiptAppointment)}
        onClose={() => setSelectedReceiptAppointment(null)}
        appointment={selectedReceiptAppointment}
        token={token}
        language={language}
        user={user}
        patient={patient}
      />
    </>
  );
}

// Patient demographic profile editor for managing personal identity, contact details, and account deletion.
export function ProfilePage({ profile, setProfile, patient, busy, onSave, onDelete, language = "en", token, user, onUserUpdated }) {
  const hi = language === "hi";
  const update = (key, value) => setProfile({ ...profile, [key]: value });
  return (
    <>
      <ScreenTitle title={hi ? "स्वास्थ्य प्रोफ़ाइल" : "Health profile"} description={hi ? "अपने रोगी खाते में सेव की गई जानकारी की समीक्षा करें।" : "Review the patient information saved to your account."} />
      <div className="cv-profile-layout">
        <form className="cv-card cv-form" onSubmit={onSave}>
          <h2>{hi ? "व्यक्तिगत जानकारी" : "Personal details"}</h2>
          <p className="cv-subtle">{hi ? "यह जानकारी आपके साइन-इन खाते से जुड़ी है।" : "This information is linked to your signed-in account."}</p>
          <label>{hi ? "पूरा नाम" : "Full name"}<input required minLength={2} maxLength={120} autoComplete="name" value={profile.full_name} onChange={(event) => update("full_name", event.target.value)} /></label>
          <label>{hi ? "ईमेल पता" : "Email address"}<input type="email" required autoComplete="email" value={profile.email} onChange={(event) => update("email", event.target.value)} /></label>
          <div className="cv-form-row">
            <label>{hi ? "आयु" : "Age"}<input type="number" required min="0" max="120" value={profile.age} onChange={(event) => update("age", event.target.value)} /></label>
            <label>{hi ? "लिंग" : "Gender"}<select value={profile.gender} onChange={(event) => update("gender", event.target.value)}><option value="prefer_not_to_say">{hi ? "बताना नहीं चाहते" : "Prefer not to say"}</option><option value="female">{hi ? "महिला" : "Female"}</option><option value="male">{hi ? "पुरुष" : "Male"}</option><option value="other">{hi ? "अन्य" : "Other"}</option></select></label>
          </div>
          <button className="cv-button cv-button-primary cv-full" disabled={busy}>{busy ? (hi ? "सेव हो रहा है…" : "Saving…") : patient ? (hi ? "बदलाव सेव करें" : "Save changes") : (hi ? "प्रोफ़ाइल बनाएँ" : "Create patient profile")}</button>
          {patient && <button className="cv-button cv-button-danger cv-full" type="button" onClick={onDelete}>{hi ? "प्रोफ़ाइल हटाएँ" : "Delete profile"}</button>}
        </form>
        <div className="cv-form">
          <NotificationContactForm token={token} user={user} onUpdated={onUserUpdated} language={language} />
          <aside className="cv-card cv-privacy">
            <span className="cv-icon-tile" aria-hidden="true">♡</span><h2>{hi ? "आपकी जानकारी, आपकी पसंद" : "Your information, your choice"}</h2>
            <p>{hi ? "केवल वही जानकारी सेव करें जिसे आप अपने पोर्टल खाते में रखना चाहते हैं।" : "Only save information you intend to keep in this portal account."}</p>
            <div className="cv-privacy-banner"><strong>{hi ? "विकास परिवेश" : "Development environment"}</strong><span>{hi ? "वास्तविक रोगी जानकारी न डालें।" : "Do not enter real patient information."}</span></div>
          </aside>
        </div>
      </div>
    </>
  );
}

// Fallback placeholder screen for features or routes currently under development or unconfigured.
export function UnavailablePage({ title, description }) {
  return <><ScreenTitle title={title} description={description} /><section className="cv-card"><EmptyState icon="⧖" title="Not available in this version" description="This area is not connected to a backend service yet. No records or notifications are being simulated." /></section></>;
}

// Compact dashboard KPI widget displaying an icon, label, primary numerical value, and note.
function MetricCard({ icon, label, value, note }) {
  return <article className="cv-metric"><span className="cv-icon-tile" aria-hidden="true">{icon}</span><span className="cv-metric-label">{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

// Card snippet summarizing an upcoming appointment's date, doctor, specialty, and status.
function AppointmentSummary({ appointment }) {
  return <article className="cv-upcoming-item">
    <span className="cv-date-chip"><b>{formatAppointmentDatePart(appointment.scheduled_for, "day")}</b><small>{formatAppointmentDatePart(appointment.scheduled_for, "month")}</small></span>
    <div><h3>{appointment.doctor_name || "Clinician"}</h3><p>{appointment.specialty || "Specialty not listed"}</p><time dateTime={appointment.scheduled_for}>{formatAppointmentDateTime(appointment.scheduled_for)} IST</time></div>
    <span className={`cv-status cv-status-${appointment.status}`}>{appointment.status}</span>
  </article>;
}

// Actionable navigation tile linking directly to key portal workflows and clinical tools.
function QuickLink({ icon, title, detail, onClick }) {
  return <button className="cv-quick-link" onClick={onClick}><span aria-hidden="true">{icon}</span><span><strong>{title}</strong><small>{detail}</small></span><b aria-hidden="true">→</b></button>;
}
