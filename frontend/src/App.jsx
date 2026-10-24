import { useEffect, useState } from "react";
import Billing from "./components/Billing";
import AdminManagement from "./components/AdminManagement";
import VoiceAssistant from "./components/VoiceAssistant";
import { PatientHealthRecords } from "./components/PatientHealthRecords";
import { DoctorWorkspace } from "./components/DoctorWorkspace";
import { DPDPPrivacyCenter } from "./components/DPDPPrivacyCenter";
import {
  AppointmentsPage,
  CareDirectoryPage,
  DashboardPage,
  NotificationsPage,
  ProfilePage,
  ProviderDashboardPage,
  ScreenTitle,
  TriagePage,
  UnavailablePage,
} from "./components/PortalScreens";
import PublicTriage from "./components/PublicTriage";
import { useToast } from "./components/ToastProvider";
import { apiRequest, readCachedUser } from "./services/api";
import { applyTheme, persistThemePreference, readThemePreference } from "./services/theme";
import "./App.css";
import "./portal.css";
import "./healthcare.css";

const emptyProfile = { full_name: "", email: "", age: "", gender: "prefer_not_to_say" };
const navigation = [
  { id: "Overview", icon: "⌂", en: "Overview", hi: "अवलोकन" },
  { id: "Find care", icon: "♙", en: "Find care", hi: "देखभाल खोजें" },
  { id: "Appointments", icon: "▦", en: "Appointments", hi: "अपॉइंटमेंट" },
  { id: "Health records", icon: "📁", en: "Health records", hi: "स्वास्थ्य रिकॉर्ड" },
  { id: "Symptom check", icon: "✳", en: "Symptom check", hi: "लक्षण जाँच" },
  { id: "Assistant", icon: "◉", en: "CareVoice assistant", hi: "CareVoice सहायक" },
  { id: "Profile", icon: "♡", en: "Health profile", hi: "स्वास्थ्य प्रोफ़ाइल" },
  { id: "Privacy", icon: "🛡️", en: "DPDP Privacy", hi: "DPDP गोपनीयता" },
  { id: "Notifications", icon: "♧", en: "Notifications", hi: "सूचनाएँ" },
  { id: "Billing", icon: "₹", en: "Billing", hi: "बिलिंग" },
];
const providerNavigation = [
  { id: "Provider dashboard", icon: "▦", en: "Provider dashboard", hi: "प्रदाता डैशबोर्ड" },
  { id: "Doctor workspace", icon: "🩺", en: "Doctor workspace", hi: "डॉक्टर कार्यक्षेत्र" },
];
const administrationNavigation = [
  { id: "Administration", icon: "⚙", en: "Administration", hi: "प्रशासन" },
];

// Safely retrieves a key from localStorage with exception resilience and default fallback.
function storageGet(key, fallback = "") {
  try {
    return window.localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

// Master application component orchestrating auth state, bilingual localization, routing, and portal views.
export default function App() {
  const toast = useToast();
  const isPasswordResetPath = window.location.pathname === "/reset-password";
  const isAdminSetupPath = window.location.pathname === "/setup/administrator";
  const [token, setToken] = useState(() => isPasswordResetPath ? "" : storageGet("ahva_token"));
  const [user, setUser] = useState(readCachedUser);
  const [language, setLanguage] = useState(() => storageGet("carevoice_language", "en"));
  const [theme, setTheme] = useState(readThemePreference);
  const [page, setPage] = useState("Overview");
  const [patients, setPatients] = useState([]);
  const [recentAppointment, setRecentAppointment] = useState(null);
  const [billingRequest, setBillingRequest] = useState(null);
  const [profile, setProfile] = useState(emptyProfile);
  const [accountLoading, setAccountLoading] = useState(Boolean(!isPasswordResetPath && storageGet("ahva_token")));
  const [busy, setBusy] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [authMode, setAuthMode] = useState(() => (
    isPasswordResetPath ? "reset-password" : isAdminSetupPath ? "bootstrap" : "landing"
  ));
  const [bootstrapStatus, setBootstrapStatus] = useState({ setup_available: false, reason: "checking" });
  const [auth, setAuth] = useState({
    full_name: "",
    email: "",
    password: "",
    password_confirmation: "",
    bootstrap_token: "",
    reset_token: new URLSearchParams(window.location.search).get("token") || "",
  });

  useEffect(() => {
    if (!error) return;
    toast(error, "error");
    setError("");
  }, [error, toast]);

  useEffect(() => {
    if (!notice) return;
    toast(notice, "success");
    setNotice("");
  }, [notice, toast]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => applyTheme(theme, document.documentElement, media);
    apply();
    if (theme !== "system") return undefined;
    media.addEventListener?.("change", apply);
    return () => media.removeEventListener?.("change", apply);
  }, [theme]);

  useEffect(() => {
    document.documentElement.lang = language === "hi" ? "hi" : "en";
  }, [language]);

  // Updates application color theme and saves preference to browser local storage.
  function changeTheme(nextTheme) {
    setTheme(nextTheme);
    if (!persistThemePreference(nextTheme)) setError("The theme preference could not be saved in this browser.");
  }

  useEffect(() => {
    let active = true;
    apiRequest("/auth/bootstrap/status", "")
      .then((result) => {
        if (active) setBootstrapStatus({
          setup_available: result.setup_available === true,
          reason: result.reason || (result.setup_available ? "available" : "unavailable"),
        });
      })
      .catch(() => {
        if (active) setBootstrapStatus({ setup_available: false, reason: "status_unavailable" });
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const handleHistoryChange = () => {
      setAuthMode(window.location.pathname === "/setup/administrator" ? "bootstrap" : "landing");
    };
    window.addEventListener("popstate", handleHistoryChange);
    return () => window.removeEventListener("popstate", handleHistoryChange);
  }, []);

  // Switches between landing, login, register, and initial administrator bootstrap authentication modes.
  function changeAuthMode(mode) {
    const nextPath = mode === "bootstrap" ? "/setup/administrator" : "/";
    if (window.location.pathname !== nextPath) window.history.pushState({}, "", nextPath);
    setAuthMode(mode);
    setError("");
    setNotice("");
  }

  useEffect(() => {
    if (!isPasswordResetPath) return;
    try {
      window.localStorage.removeItem("ahva_token");
      window.localStorage.removeItem("ahva_user");
    } catch {
      setError("Could not clear the expired sign-in session from this browser.");
    }
    setUser(null);
    setPatients([]);
    setRecentAppointment(null);
  }, [isPasswordResetPath]);

  useEffect(() => {
    if (!token) {
      setAccountLoading(false);
      return undefined;
    }
    let active = true;
    setAccountLoading(true);
    // Loads profile and linked patient demographic data for the authenticated session.
    async function loadAccount() {
      try {
        const account = await apiRequest("/auth/me", token);
        const patientRows = account.role === "patient" ? await apiRequest("/patients/", token) : [];
        if (!active) return;
        setUser(account);
        setPage(account.role === "patient" ? "Overview" : "Provider dashboard");
        setPatients(patientRows);
        try {
          window.localStorage.setItem("ahva_user", JSON.stringify(account));
        } catch {
          setError("Your browser could not save session details. The current session is still active.");
        }
        if (patientRows[0]) {
          const patient = patientRows[0];
          setProfile({ full_name: patient.full_name, email: patient.email, age: String(patient.age), gender: patient.gender });
        } else {
          setProfile({ ...emptyProfile, full_name: account.full_name, email: account.email });
        }
      } catch (reason) {
        if (!active) return;
        if (reason.status === 401 || reason.status === 403) {
          clearLocalSession();
        } else {
          setError(reason.message || "Your account could not be loaded. Please try again.");
        }
      } finally {
        if (active) setAccountLoading(false);
      }
    }
    loadAccount();
    return () => { active = false; };
  }, [token]);

  // Toggles interface language between English and Hindi, persisting the choice in localStorage.
  function changeLanguage(nextLanguage) {
    setLanguage(nextLanguage);
    try {
      window.localStorage.setItem("carevoice_language", nextLanguage);
    } catch {
      setError("The language preference could not be saved in this browser.");
    }
  }

  useEffect(() => {
    document.body.classList.toggle("cv-menu-open", mobileMenuOpen);
    return () => document.body.classList.remove("cv-menu-open");
  }, [mobileMenuOpen]);

  useEffect(() => {
    if (!mobileMenuOpen) return undefined;
    const onKeyDown = (event) => { if (event.key === "Escape") setMobileMenuOpen(false); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileMenuOpen]);

  // Toggles the mobile responsive hamburger navigation menu drawer open or closed.
  function toggleMobileMenu() {
    setMobileMenuOpen(prev => !prev);
  }

  // Closes the responsive mobile navigation drawer.
  function closeMobileMenu() {
    setMobileMenuOpen(false);
  }

  // Handles navigation item clicks, switching views and dismissing mobile drawers.
  const handleNavClick = (pageId) => {
    setPage(pageId);
    setMobileMenuOpen(false);
    setError("");
    setNotice("");
  };

  // Syncs updated account attributes into React component state and local storage.
  function updateCurrentUser(account) {
    setUser(account);
    try {
      window.localStorage.setItem("ahva_user", JSON.stringify(account));
    } catch {
      setError("Your account was updated, but the browser could not refresh its saved session details.");
    }
  }

  // Clears session tokens, stored user profiles, and active patient records from local state.
  function clearLocalSession(errorMessage = "") {
    try {
      window.localStorage.removeItem("ahva_token");
      window.localStorage.removeItem("ahva_user");
    } catch {
      // ignore storage access errors
    }
    setToken("");
    setUser(null);
    setPatients([]);
    setPage("Overview");
    setAuthMode("landing");
    if (window.location.pathname !== "/") window.history.replaceState({}, "", "/");
    if (errorMessage) setError(errorMessage);
    setNotice("");
  }

  // Signs out the user, calling the backend revocation endpoint and purging browser credentials.
  async function signOut() {
    const currentToken = token;
    clearLocalSession();
    if (currentToken) {
      try {
        await apiRequest("/auth/logout", currentToken, { method: "POST" });
      } catch {
        // ignore network or 401 errors on logout
      }
    }
  }

  // Submits user credentials for registration, login, or initial platform bootstrap.
  async function submitAuth(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const path = authMode === "bootstrap" ? "/auth/bootstrap/platform-admin" : `/auth/${authMode}`;
      const body = authMode === "register"
        ? { full_name: auth.full_name, email: auth.email, password: auth.password }
        : authMode === "bootstrap"
          ? auth
          : authMode === "login"
            ? (auth.email.includes("@")
              ? { email: auth.email, password: auth.password }
              : { username: auth.email, password: auth.password })
            : { email: auth.email, password: auth.password };
      const result = await apiRequest(path, "", {
        method: "POST",
        body: JSON.stringify(body),
      });
      try {
        window.localStorage.setItem("ahva_token", result.access_token);
        window.localStorage.setItem("ahva_user", JSON.stringify(result.user));
      } catch {
        throw new Error("Your browser could not save the sign-in session. Check browser storage settings and try again.");
      }
      setUser(result.user);
      setPage(result.user.role === "patient" ? "Overview" : "Provider dashboard");
      setToken(result.access_token);
      setNotice(authMode === "register" ? "Your account was created." : "You’re signed in.");
      setBootstrapStatus({ setup_available: false, reason: "complete" });
      if (authMode === "bootstrap") window.history.replaceState({}, "", "/");
    } catch (reason) {
      setError(reason.message || "We couldn’t complete sign-in. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  // Requests a time-limited one-time password reset token via transactional email.
  async function submitPasswordResetRequest(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await apiRequest("/auth/password-reset/request", "", {
        method: "POST",
        body: JSON.stringify({ email: auth.email }),
      });
      setNotice(result.message);
    } catch (reason) {
      setError(reason.message || "Password reset could not be requested.");
    } finally {
      setBusy(false);
    }
  }

  // Submits verified reset token and new strong password to complete account recovery.
  async function submitPasswordReset(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await apiRequest("/auth/password-reset/confirm", "", {
        method: "POST",
        body: JSON.stringify({ token: auth.reset_token, new_password: auth.password }),
      });
      setAuthMode("login");
      setAuth((current) => ({ ...current, password: "" }));
      window.history.replaceState({}, "", "/");
      setNotice(result.message);
    } catch (reason) {
      setError(reason.message || "Password could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  // Persists patient demographic profile information to the backend API.
  async function saveProfile(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const data = { ...profile, age: Number(profile.age) };
    try {
      const saved = patients[0]
        ? await apiRequest(`/patients/${patients[0].id}`, token, { method: "PATCH", body: JSON.stringify(data) })
        : await apiRequest("/patients/", token, { method: "POST", body: JSON.stringify(data) });
      setPatients([saved]);
      setProfile({ full_name: saved.full_name, email: saved.email, age: String(saved.age), gender: saved.gender });
      setNotice("Your health profile was saved.");
    } catch (reason) {
      setError(reason.message || "Your profile could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  // Deletes the active patient demographic profile following explicit user confirmation.
  async function deleteProfile() {
    if (!patients[0] || !window.confirm(language === "hi" ? "क्या आप अपनी स्वास्थ्य प्रोफ़ाइल हटाना चाहते हैं?" : "Delete your patient profile? This cannot be undone.")) return;
    setError("");
    setNotice("");
    try {
      await apiRequest(`/patients/${patients[0].id}`, token, { method: "DELETE" });
      setPatients([]);
      setProfile({ ...emptyProfile, full_name: user.full_name, email: user.email });
      setNotice(language === "hi" ? "आपकी प्रोफ़ाइल हटा दी गई है।" : "Your patient profile was deleted.");
    } catch (reason) {
      setError(reason.message || "Your profile could not be deleted.");
    }
  }

  if (!token || !user) {
    if (token && accountLoading) {
      return (
        <div className="cv-app-shell cv-loading-screen" role="status">
          <div className="cv-account-loading">
            <span className="cv-spinner" aria-hidden="true" />
            <p>{language === "hi" ? "सत्र लोड हो रहा है…" : "Loading session…"}</p>
          </div>
        </div>
      );
    }
    return (
      <AuthScreen
        mode={authMode}
        auth={auth}
        setAuth={setAuth}
        setError={setError}
        setNotice={setNotice}
        busy={busy}
        error={error}
        notice={notice}
        language={language}
        setLanguage={changeLanguage}
        theme={theme}
        setTheme={changeTheme}
        bootstrapStatus={bootstrapStatus}
        setMode={changeAuthMode}
        onSubmit={submitAuth}
        onResetRequest={submitPasswordResetRequest}
        onResetConfirm={submitPasswordReset}
        resetToken={auth.reset_token}
      />
    );
  }

  const isHindi = language === "hi";
  const isAdmin = user?.role === "platform_admin" || user?.role === "hospital_admin";
  const isDoctor = user?.role === "doctor";
  const canAccessBilling = user?.role === "patient" || ["hospital_staff", "hospital_admin", "platform_admin"].includes(user?.role);
  const homePage = user?.role === "patient" ? "Overview" : "Provider dashboard";
  const visibleNavigation = user?.role === "patient"
    ? navigation
    : [
        ...providerNavigation.filter((item) => item.id !== "Doctor workspace" || isDoctor),
        ...(isAdmin ? administrationNavigation : []),
        ...navigation.filter((item) => ["Find care", "Appointments"].includes(item.id)),
        ...(canAccessBilling ? navigation.filter((item) => item.id === "Billing") : []),
      ];
  const currentPage = visibleNavigation.find((item) => item.id === page);
  const pageLabel = currentPage ? (isHindi ? currentPage.hi : currentPage.en) : page;

  return (
    <div className="cv-app-shell">
      {mobileMenuOpen && (
        <div className="cv-menu-backdrop" onClick={closeMobileMenu} role="presentation" aria-hidden="true" />
      )}
      <aside id="cv-sidebar" className={`cv-sidebar ${mobileMenuOpen ? "open" : ""}`} role="navigation" aria-label={isHindi ? "मुख्य नेविगेशन" : "Main navigation"}>
        <div className="cv-sidebar-head">
          <a className="cv-brand" href="#home" onClick={(event) => { event.preventDefault(); handleNavClick(homePage); }}>
            <span className="cv-brand-mark" aria-hidden="true">✚</span>
            <span>CareVoice<small>HEALTH</small></span>
          </a>
          <button
            type="button"
            className="cv-sidebar-close"
            onClick={closeMobileMenu}
            aria-label={isHindi ? "बंद करें" : "Close menu"}
          >×</button>
        </div>
        <div className="cv-sidebar-mobile-controls">
          <LanguageToggle language={language} setLanguage={changeLanguage} />
          <ThemeSelector theme={theme} setTheme={changeTheme} language={language} />
        </div>
        <div className="cv-nav-label">{isHindi ? "आपका कार्यक्षेत्र" : "YOUR WORKSPACE"}</div>
        <nav className="cv-navigation" aria-label={isHindi ? "मुख्य नेविगेशन" : "Main navigation"}>
          {visibleNavigation.map((item) => (
            <button key={item.id} className={`cv-nav-item ${page === item.id ? "active" : ""}`} aria-current={page === item.id ? "page" : undefined} onClick={() => handleNavClick(item.id)}>
              <span aria-hidden="true">{item.icon}</span><span>{isHindi ? item.hi : item.en}</span>
            </button>
          ))}
        </nav>
        <div className="cv-sidebar-emergency"><span aria-hidden="true">!</span><div><strong>{isHindi ? "आपातकाल?" : "Need urgent help?"}<br /><a href="tel:112">112</a> / <a href="tel:108">108</a></strong><p>{isHindi ? "सुरक्षा जाँच में देरी न करें।" : "Do not delay urgent care for an online check."}</p></div></div>
        <div className="cv-sidebar-account">
          <span className="cv-avatar" aria-hidden="true">{user?.full_name?.trim().charAt(0)?.toUpperCase() || "U"}</span>
          <span className="cv-account-name"><strong>{user?.full_name || (isHindi ? "खाता" : "Account")}</strong><small>{roleLabel(user?.role, isHindi)}</small></span>
          <button type="button" onClick={signOut} className="cv-signout" aria-label={isHindi ? "साइन आउट" : "Sign out"} title={isHindi ? "साइन आउट" : "Sign out"}>↪</button>
        </div>
      </aside>

      <main className="cv-main">
        <header className="cv-topbar">
          <div className="cv-topbar-left">
            <button
              type="button"
              className="cv-hamburger"
              onClick={toggleMobileMenu}
              aria-expanded={mobileMenuOpen}
              aria-controls="cv-sidebar"
              aria-label={isHindi ? "मेनू खोलें" : "Open menu"}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <path d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <a className="cv-mobile-brand" href="#home" onClick={(event) => { event.preventDefault(); handleNavClick(homePage); }}>
              <span className="cv-brand-mark" aria-hidden="true">✚</span>
              <span>CareVoice<small>HEALTH</small></span>
            </a>
            <div className="cv-breadcrumb"><span>{isHindi ? "कार्यस्थान" : "Workspace"}</span><b aria-hidden="true">/</b><strong>{pageLabel}</strong></div>
          </div>
          <div className="cv-topbar-actions">
            <LanguageToggle language={language} setLanguage={changeLanguage} />
            <ThemeSelector theme={theme} setTheme={changeTheme} language={language} />
            <span className="cv-session-status"><i aria-hidden="true" />{isHindi ? "सुरक्षित सत्र" : "Signed-in session"}</span>
            <button className="cv-mobile-signout" onClick={signOut}>{isHindi ? "बाहर जाएँ" : "Sign out"}</button>
          </div>
        </header>
        <div className="cv-content">
          {accountLoading ? <div className="cv-account-loading" role="status"><span className="cv-spinner" />{isHindi ? "आपका खाता लोड हो रहा है…" : "Loading your account…"}</div> : (
            <>
              {page === "Overview" && (user?.role === "patient"
                ? <DashboardPage user={user} patient={patients[0]} token={token} onNavigate={setPage} language={language} />
                : <ProviderDashboardPage user={user} token={token} onUserUpdated={updateCurrentUser} language={language} />)}
              {page === "Provider dashboard" && <ProviderDashboardPage user={user} token={token} onUserUpdated={updateCurrentUser} language={language} />}
              {page === "Doctor workspace" && isDoctor && <DoctorWorkspace token={token} user={user} language={language} onNavigate={setPage} />}
              {page === "Administration" && isAdmin && <AdminManagement token={token} user={user} onUserUpdated={updateCurrentUser} onSessionInvalidated={signOut} language={language} />}
              {page === "Find care" && <CareDirectoryPage token={token} onNavigate={setPage} onAppointmentBooked={(appointment) => { setRecentAppointment(appointment); setPage("Appointments"); }} language={language} canBook={user?.role === "patient"} />}
              {page === "Appointments" && <AppointmentsPage token={token} language={language} user={user} patient={patients[0]} recentAppointment={recentAppointment} onNavigate={(nextPage, request) => { if (nextPage === "Billing") setBillingRequest(request || null); setPage(nextPage); }} />}
              {page === "Health records" && <PatientHealthRecords token={token} user={user} language={language} onNavigate={setPage} />}
              {page === "Symptom check" && <TriagePage language={language} token={token} onNavigate={setPage} />}
              {page === "Assistant" && <><ScreenTitle title={isHindi ? "CareVoice सहायक" : "CareVoice assistant"} description={isHindi ? "सामान्य स्वास्थ्य जानकारी के लिए लिखें या बोलें।" : "Type or speak for general health information. This is not a diagnosis or a substitute for care."} /><VoiceAssistant token={token} language={language} onNavigate={setPage} /></>}
              {page === "Profile" && user?.role === "patient" && <ProfilePage profile={profile} setProfile={setProfile} patient={patients[0]} busy={busy} onSave={saveProfile} onDelete={deleteProfile} token={token} user={user} onUserUpdated={updateCurrentUser} language={language} />}
              {page === "Privacy" && <DPDPPrivacyCenter token={token} user={user} language={language} onNavigate={setPage} />}
              {page === "Notifications" && <NotificationsPage token={token} user={user} onUserUpdated={updateCurrentUser} language={language} />}
              {page === "Billing" && canAccessBilling && <Billing token={token} user={user} language={language} target={billingRequest} onTargetHandled={() => setBillingRequest(null)} />}
              {page === "Medical records" && <PatientHealthRecords token={token} user={user} language={language} onNavigate={setPage} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

// Renders public landing and authentication screens (login, signup, recovery, bootstrap).
function AuthScreen({ mode, setMode, auth, setAuth, setError, setNotice, busy, error, notice, language, setLanguage, theme, setTheme, bootstrapStatus, onSubmit, onResetRequest, onResetConfirm, resetToken }) {
  const hi = language === "hi";
  const isLogin = mode === "login";
  const isRegister = mode === "register";
  const isResetRequest = mode === "forgot-password";
  const isResetConfirm = mode === "reset-password";
  const isBootstrap = mode === "bootstrap";
  const formSubmit = isResetRequest ? onResetRequest : isResetConfirm ? onResetConfirm : onSubmit;
  return (
    <main className="cv-public-shell">
      <header className="cv-public-header">
        <a className="cv-brand" href="#home" onClick={(event) => { event.preventDefault(); setMode("landing"); }}>
          <span className="cv-brand-mark" aria-hidden="true">✚</span>
          <span>CareVoice<small>HEALTH</small></span>
        </a>
        <nav className="cv-public-nav" aria-label={hi ? "मुख्य मेनू" : "Main menu"}>
          {mode === "landing" && <><a href="#care">{hi ? "देखभाल सेवाएँ" : "Care services"}</a><a href="#safety">{hi ? "सुरक्षा पहले" : "Safety first"}</a></>}
          <LanguageToggle language={language} setLanguage={setLanguage} />
          <ThemeSelector theme={theme} setTheme={setTheme} language={language} />
          <button className="cv-button cv-button-quiet" onClick={() => setMode("login")}>{hi ? "साइन इन" : "Sign in"}</button>
          <button className="cv-button cv-button-primary" onClick={() => setMode("register")}>{hi ? "खाता बनाएँ" : "Create account"}</button>
          {bootstrapStatus.reason !== "complete" && <button className="cv-button cv-button-quiet" onClick={() => setMode("bootstrap")}>{hi ? "प्रारंभिक व्यवस्थापक सेटअप" : "Initial administrator setup"}</button>}
        </nav>
      </header>
      {mode === "landing" ? (
        <>
          <section className="cv-hero" id="home">
            <div className="cv-hero-copy">
              <span className="cv-hero-kicker"><i aria-hidden="true" /> {hi ? "आपकी देखभाल, एक साथ" : "CARE THAT FEELS MORE CONNECTED"}</span>
              <h1>{hi ? <>स्वास्थ्य सेवा<br />जो <em>आपकी सुने।</em></> : <>Healthcare that<br />listens to <em>you.</em></>}</h1>
              <p>{hi ? "अपॉइंटमेंट प्रबंधित करें, अपने क्लिनिक की डायरेक्टरी खोजें और सामान्य स्वास्थ्य जानकारी पाएँ।" : "Manage appointments, explore your clinic’s care directory, and find general health information in one thoughtful portal."}</p>
              <div className="cv-hero-actions"><button className="cv-button cv-button-primary" onClick={() => setMode("register")}>{hi ? "शुरू करें" : "Get started"} <span aria-hidden="true">→</span></button><button className="cv-button cv-button-secondary" onClick={() => setMode("login")}>{hi ? "पहले से खाता है? साइन इन" : "I already have an account"}</button></div>
              <div className="cv-hero-trust"><span>✓ {hi ? "आपके खाते से जुड़ी प्रोफ़ाइल" : "Account-scoped profile"}</span><span>✓ {hi ? "नियम-आधारित आपातकालीन जाँच" : "Rule-based emergency checks"}</span><span>✓ {hi ? "हिंदी और अंग्रेज़ी इंटरफ़ेस" : "English and Hindi interface"}</span></div>
            </div>
            <aside className="cv-hero-panel" aria-label={hi ? "पोर्टल सुविधाएँ" : "CareVoice features"}>
              <div className="cv-hero-panel-top"><span className="cv-icon-tile">✳</span><span className="cv-feature-tag">{hi ? "आपका केयर पोर्टल" : "YOUR CARE SPACE"}</span></div>
              <h2>{hi ? "बेहतर देखभाल तक आसान पहुँच।" : "A clearer path to the care you need."}</h2>
              <p>{hi ? "क्लिनिक द्वारा उपलब्ध कराए गए वास्तविक रिकॉर्ड से जानकारी पाएँ।" : "See real information returned by your clinic—not fabricated listings or booking confirmations."}</p>
              <div className="cv-feature-lines"><div><span>01</span><b>{hi ? "अपने क्लिनिक से जुड़ें" : "Connect with your clinic"}</b><small>{hi ? "अपॉइंटमेंट, प्रोफ़ाइल और बिलिंग" : "Appointments, profile, and billing"}</small></div><div><span>02</span><b>{hi ? "स्थानीय देखभाल खोजें" : "Find local care"}</b><small>{hi ? "डॉक्टर और अस्पताल की लाइव सूची देखें" : "Explore live doctor and hospital listings"}</small></div><div><span>03</span><b>{hi ? "सुरक्षा से शुरुआत करें" : "Start with safety"}</b><small>{hi ? "नियम-आधारित लक्षण जाँच, AI की ज़रूरत नहीं" : "Deterministic symptom triage, no AI needed"}</small></div></div>
              <div className="cv-panel-decoration" aria-hidden="true">+</div>
            </aside>
          </section>
          <section className="cv-public-lower" id="care">
            <div className="cv-section-intro"><span className="eyebrow">{hi ? "स्पष्ट और सुलभ देखभाल" : "CARE, WITH CLARITY"}</span><h2>{hi ? "आपकी स्वास्थ्य यात्रा के लिए सहायता" : "Support for your health journey"}</h2><p>{hi ? "अपने क्लिनिक खाते से जुड़ी सुविधाओं के लिए साइन इन करें।" : "Sign in to access the features connected to your clinic account."}</p></div>
            <div className="cv-public-feature-grid">
              <article><span className="cv-icon-tile">▦</span><h3>{hi ? "अपॉइंटमेंट" : "Appointments"}</h3><p>{hi ? "अपने क्लिनिक की सेवा से मुलाक़ात बुक करें, देखें या रद्द करें।" : "Book, review, and cancel visits using your clinic’s appointment service."}</p></article>
              <article><span className="cv-icon-tile">♙</span><h3>{hi ? "देखभाल खोजें" : "Find care"}</h3><p>{hi ? "डायरेक्टरी में उपलब्ध डॉक्टर और अस्पताल की प्रोफ़ाइल खोजें।" : "Search doctor and hospital profiles actually available in the directory."}</p></article>
              <article><span className="cv-icon-tile">◉</span><h3>CareVoice</h3><p>{hi ? "सामान्य प्रश्न पूछें; यह सहायक पेशेवर देखभाल का विकल्प नहीं है।" : "Ask general questions; the assistant is not a substitute for professional care."}</p></article>
            </div>
          </section>
          <section className="cv-public-safety" id="safety"><div><span className="eyebrow">{hi ? "सबसे पहले सुरक्षा" : "SAFETY COMES FIRST"}</span><h2>{hi ? "तत्काल मदद चाहिए?" : "Urgent symptoms need urgent care."}</h2><p>{hi ? "यदि आपको तत्काल खतरा हो सकता है, ऑनलाइन जवाब की प्रतीक्षा न करें।" : "If you may be in immediate danger, do not wait for an online response."}</p><div className="cv-emergency-actions"><a href="tel:112">{hi ? "112 पर कॉल करें" : "Call 112"}</a><a href="tel:108">{hi ? "एम्बुलेंस 108" : "Ambulance 108"}</a></div></div><PublicTriage language={language} /></section>
          <footer className="cv-public-footer"><span>© {new Date().getFullYear()} CareVoice Health</span><span>{hi ? "विकास सेवा · वास्तविक रोगी जानकारी न डालें" : "Development service · Do not enter real patient information"}</span></footer>
        </>
      ) : (
        <section className="cv-auth-layout">
          <div className="cv-auth-side">
            <button className="cv-back-link" onClick={() => setMode("landing")}>← {hi ? "मुख्य पृष्ठ" : "Back to home"}</button>
            <span className="cv-hero-kicker"><i aria-hidden="true" /> {hi ? "आपका सुरक्षित पोर्टल" : "YOUR PERSONAL CARE PORTAL"}</span>
            <h1>{isRegister ? (hi ? "अपनी देखभाल यात्रा शुरू करें।" : "Make space for better care.") : (hi ? "वापसी पर स्वागत है।" : "Welcome back to your care space.")}</h1>
            <p>{hi ? "आपकी देखभाल से जुड़ी सुविधाएँ एक ही खाते में।" : "Access your profile, appointments, and care directory through your clinic account."}</p>
            <div className="cv-auth-side-note"><span aria-hidden="true">♡</span><p>For your privacy, use only information you intend to store in this development portal. Never delay emergency care.</p></div>
          </div>
          <form className="cv-auth-card" onSubmit={formSubmit}>
            <span className="eyebrow">{isRegister ? (hi ? "खाता पंजीकरण" : "ACCOUNT REGISTRATION") : isBootstrap ? (hi ? "एक बार का व्यवस्थापक सेटअप" : "ONE-TIME ADMINISTRATOR SETUP") : isResetRequest || isResetConfirm ? (hi ? "पासवर्ड रिकवरी" : "PASSWORD RECOVERY") : (hi ? "सुरक्षित साइन इन" : "SECURE SIGN IN")}</span>
            <h2>{isRegister ? (hi ? "खाता बनाएँ" : "Create your account") : isBootstrap ? (hi ? "प्रारंभिक व्यवस्थापक बनाएँ" : "Create initial administrator") : isResetRequest ? (hi ? "पासवर्ड रीसेट करें" : "Reset your password") : isResetConfirm ? (hi ? "नया पासवर्ड चुनें" : "Choose a new password") : (hi ? "साइन इन करें" : "Sign in")}</h2>
            <p className="cv-subtle">{isBootstrap ? (hi ? "यह केवल पहले व्यवस्थापक के लिए उपलब्ध है। सर्वर ऑपरेटर से सेटअप टोकन प्राप्त करें।" : "Available only for the first administrator. Obtain the setup token from the server operator.") : isResetRequest ? (hi ? "यदि इस ईमेल से खाता जुड़ा है, तो रीसेट निर्देश भेजे जाएँगे।" : "If an account matches this email, reset instructions will be sent.") : isResetConfirm ? (hi ? "रीसेट लिंक से नया पासवर्ड बनाएँ।" : "Set a new password using your reset link.") : isRegister ? (hi ? "शुरू करने के लिए नीचे जानकारी भरें।" : "A few details to get your account started.") : (hi ? "अपने केयर पोर्टल तक पहुँचने के लिए साइन इन करें।" : "Sign in to access your clinic-connected care portal.")}</p>
            {isBootstrap && bootstrapStatus.reason === "token_not_configured" && <div className="cv-error" role="alert">{hi ? "प्रारंभिक सेटअप सक्षम नहीं है। बैकएंड .env में कम से कम 32 अक्षरों वाला ADMIN_BOOTSTRAP_TOKEN सेट करें और बैकएंड रीस्टार्ट करें।" : "Initial setup is not enabled. Set ADMIN_BOOTSTRAP_TOKEN (at least 32 characters) in the backend .env file, then restart the backend."}</div>}
            {isBootstrap && bootstrapStatus.reason === "state_unavailable" && <div className="cv-error" role="alert">{hi ? "सेटअप स्थिति उपलब्ध नहीं है। डेटाबेस माइग्रेशन जाँचें और बैकएंड रीस्टार्ट करें।" : "Setup state is unavailable. Check that database migrations completed, then restart the backend."}</div>}
            {isBootstrap && bootstrapStatus.reason === "status_unavailable" && <div className="cv-error" role="alert">{hi ? "बैकएंड से सेटअप स्थिति नहीं मिल सकी। कनेक्शन जाँचें और पुनः प्रयास करें।" : "Could not check setup availability with the backend. Check the connection and try again."}</div>}
            {isBootstrap && bootstrapStatus.reason === "complete" && <div className="cv-success" role="status">{hi ? "प्रारंभिक व्यवस्थापक सेटअप पहले ही पूरा हो चुका है। साइन इन करें।" : "Initial administrator setup is already complete. Please sign in."}</div>}
            {error && <div className="cv-error" role="alert">{error}</div>}
            {notice && <div className="cv-success" role="status">{notice}</div>}
            {(isRegister || isBootstrap) && <label>{hi ? "पूरा नाम" : "Full name"}<input autoComplete="name" required minLength={2} maxLength={120} value={auth.full_name} onChange={(event) => setAuth({ ...auth, full_name: event.target.value })} placeholder={hi ? "आपका पूरा नाम" : "Your full name"} /></label>}
            {!isResetConfirm && <label>{isLogin ? (hi ? "उपयोगकर्ता नाम या ईमेल" : "Username or email") : (hi ? "ईमेल पता" : "Email address")}<input type={isLogin ? "text" : "email"} autoComplete={isLogin ? "username" : "email"} required maxLength={254} value={auth.email} onChange={(event) => setAuth({ ...auth, email: event.target.value })} placeholder={isLogin ? "Username or email address" : "you@example.com"} /></label>}
            {isBootstrap && <label>{hi ? "सेटअप टोकन" : "Setup token"}<input type="password" autoComplete="off" required minLength={32} maxLength={256} value={auth.bootstrap_token} onChange={(event) => setAuth({ ...auth, bootstrap_token: event.target.value })} /></label>}
            {isResetConfirm && !resetToken && <p className="cv-error" role="alert">{hi ? "रीसेट लिंक में टोकन नहीं है। कृपया नया लिंक माँगें।" : "The reset link has no token. Please request a new link."}</p>}
            {(isLogin || isRegister || isResetConfirm || isBootstrap) && <label>{isResetConfirm ? (hi ? "नया पासवर्ड" : "New password") : (hi ? "पासवर्ड" : "Password")}<input type="password" autoComplete={isLogin ? "current-password" : "new-password"} required minLength={isBootstrap ? 12 : isRegister || isResetConfirm ? 10 : 1} maxLength={128} value={auth.password} onChange={(event) => setAuth({ ...auth, password: event.target.value })} placeholder={isLogin ? "Enter your password" : isBootstrap ? "12+ characters with upper/lowercase, number, and symbol" : (hi ? "कम से कम 10 अक्षर" : "At least 10 characters")} /></label>}
            {isBootstrap && <label>{hi ? "पासवर्ड की पुष्टि करें" : "Confirm password"}<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={auth.password_confirmation} onChange={(event) => setAuth({ ...auth, password_confirmation: event.target.value })} /></label>}
            <button className="cv-button cv-button-primary cv-full" disabled={busy || (isBootstrap && !bootstrapStatus.setup_available) || (isResetConfirm && !resetToken)}>{busy ? (hi ? "कृपया प्रतीक्षा करें…" : "Please wait…") : isRegister ? (hi ? "खाता बनाएँ" : "Create account") : isBootstrap ? (hi ? "व्यवस्थापक सेटअप करें" : "Set up administrator") : isResetRequest ? (hi ? "रीसेट निर्देश भेजें" : "Send reset instructions") : isResetConfirm ? (hi ? "पासवर्ड बदलें" : "Change password") : (hi ? "साइन इन करें" : "Sign in")} <span aria-hidden="true">→</span></button>
            {isLogin && <p className="cv-auth-switch"><button type="button" onClick={() => { setError(""); setNotice(""); setMode("forgot-password"); }}>{hi ? "पासवर्ड भूल गए?" : "Forgot password?"}</button></p>}
            {(isLogin || isRegister) ? <p className="cv-auth-switch">{isRegister ? (hi ? "पहले से खाता है?" : "Already have an account?") : (hi ? "CareVoice में नए हैं?" : "New to CareVoice?")} <button type="button" onClick={() => { setError(""); setMode(isRegister ? "login" : "register"); }}>{isRegister ? (hi ? "साइन इन" : "Sign in") : (hi ? "खाता बनाएँ" : "Create account")}</button></p> : <p className="cv-auth-switch"><button type="button" onClick={() => { setError(""); setNotice(""); setMode("login"); }}>{hi ? "साइन इन पर वापस जाएँ" : "Back to sign in"}</button></p>}
            <div className="cv-auth-emergency"><strong>{hi ? "आपातकाल?" : "Is this an emergency?"}</strong><span>{hi ? "112 या 108 पर कॉल करें।" : "Call 112 or 108 now."}</span></div>
          </form>
        </section>
      )}
    </main>
  );
}

// Renders an accessible toggle button group to switch between English and Hindi interface languages.
function LanguageToggle({ language, setLanguage }) {
  return (
    <div className="cv-language-toggle" role="group" aria-label="Interface language">
      <button type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</button>
      <button type="button" aria-pressed={language === "hi"} onClick={() => setLanguage("hi")}>हि</button>
    </div>
  );
}

// Dropdown selector allowing users to switch between system auto, light, and dark visual themes.
function ThemeSelector({ theme, setTheme, language }) {
  const hi = language === "hi";
  return (
    <label className="cv-theme-selector">
      <span className="cv-sr-only">{hi ? "रंग थीम" : "Color theme"}</span>
      <select
        aria-label={hi ? "रंग थीम" : "Color theme"}
        value={theme}
        onChange={(event) => setTheme(event.target.value)}
      >
        <option value="system">{hi ? "🌓 सिस्टम (स्वतः)" : "🌓 System (auto)"}</option>
        <option value="light">{hi ? "☀️ लाइट मोड" : "☀️ Light mode"}</option>
        <option value="dark">{hi ? "🌙 डार्क मोड" : "🌙 Dark mode"}</option>
      </select>
    </label>
  );
}

// Maps role identifier slugs to localized human-readable display badges in English or Hindi.
function roleLabel(role, hindi) {
  if (role === "platform_admin") return hindi ? "प्लेटफ़ॉर्म एडमिन" : "Platform administrator";
  if (role === "hospital_admin") return hindi ? "अस्पताल एडमिन" : "Hospital administrator";
  if (role === "hospital_staff") return hindi ? "अस्पताल टीम" : "Hospital staff";
  if (role === "doctor") return hindi ? "डॉक्टर" : "Doctor";
  return hindi ? "रोगी खाता" : "Patient account";
}
