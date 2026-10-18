import { useState, useEffect } from "react";
import Modal from "./Modal";
import { apiRequest, formatMoney } from "../services/api";

function LoadingState({ label = "Loading…" }) {
  return (
    <div className="cv-loading" role="status">
      <span className="cv-spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

function ProviderDetailContent({ type, detail, language }) {
  const hi = language === "hi";

  if (type === "doctors") {
    const qualifications = detail.qualifications || [];
    const schedules = (detail.schedules || []).filter((item) => item.is_active);

    return (
      <div className="cv-modal-provider-content">
        {detail.bio && <p className="cv-modal-bio">{detail.bio}</p>}

        <div className="cv-modal-section">
          <h3>{hi ? "विशेषताएँ" : "Specialties"}</h3>
          <p>{(detail.specialties || [detail.specialty]).join(", ")}</p>
        </div>

        <div className="cv-modal-grid">
          <div className="cv-modal-section">
            <h3>{hi ? "अनुभव" : "Experience"}</h3>
            <p>{hi ? `${detail.experience_years} वर्ष` : `${detail.experience_years} years`}</p>
          </div>

          <div className="cv-modal-section">
            <h3>{hi ? "परामर्श शुल्क" : "Consultation fee"}</h3>
            <p><strong>{formatMoney(detail.fee_minor)}</strong></p>
          </div>
        </div>

        <div className="cv-modal-section">
          <h3>{hi ? "भाषाएँ" : "Languages"}</h3>
          <p>{(detail.languages || []).join(", ") || "—"}</p>
        </div>

        <div className="cv-modal-section">
          <h3>{hi ? "परामर्श प्रकार" : "Consultation types"}</h3>
          <p>{(detail.consultation_types || []).map((item) => item.replaceAll("_", " ")).join(", ") || "—"}</p>
        </div>

        <div className="cv-modal-section">
          <h3>{hi ? "योग्यताएँ" : "Qualifications"}</h3>
          {qualifications.length ? (
            <ul className="cv-modal-list">
              {qualifications.map((item) => (
                <li key={item.id}>
                  <strong>{item.degree}</strong> · {item.institution}
                  <br />
                  <span className="cv-modal-meta">{item.verification_status}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cv-subtle">{hi ? "कोई प्रकाशित योग्यता नहीं है।" : "No qualifications have been published."}</p>
          )}
        </div>

        <div className="cv-modal-section">
          <h3>{hi ? "उपलब्धता" : "Availability"}</h3>
          {schedules.length ? (
            <ul className="cv-modal-list">
              {schedules.map((item) => (
                <li key={item.id}>
                  {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][item.day_of_week]} · {item.starts_at.slice(0, 5)}–{item.ends_at.slice(0, 5)} ({item.timezone})
                  <br />
                  <span className="cv-modal-meta">{item.consultation_type.replaceAll("_", " ")}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="cv-subtle">{hi ? "कोई समय-सारणी प्रकाशित नहीं है।" : "No availability has been published."}</p>
          )}
        </div>
      </div>
    );
  }

  // Hospital details
  return (
    <div className="cv-modal-provider-content">
      {detail.description && <p className="cv-modal-bio">{detail.description}</p>}

      <div className="cv-modal-section">
        <h3>{hi ? "पता" : "Address"}</h3>
        <p>{detail.address || "—"}</p>
      </div>

      <div className="cv-modal-grid">
        <div className="cv-modal-section">
          <h3>{hi ? "फ़ोन" : "Phone"}</h3>
          <p>{detail.phone ? <a href={`tel:${detail.phone}`}>{detail.phone}</a> : "—"}</p>
        </div>

        <div className="cv-modal-section">
          <h3>{hi ? "वेबसाइट" : "Website"}</h3>
          <p>{detail.website ? <a href={detail.website} target="_blank" rel="noreferrer">{detail.website}</a> : "—"}</p>
        </div>
      </div>

      <div className="cv-modal-section">
        <h3>{hi ? "विभाग" : "Departments"}</h3>
        <p>{detail.departments || "—"}</p>
      </div>
    </div>
  );
}

export default function ProviderDetailModal({ isOpen, onClose, type, profileId, token, language }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const hi = language === "hi";

  useEffect(() => {
    if (!isOpen || !profileId) {
      setDetail(null);
      setError("");
      return;
    }

    let active = true;
    setLoading(true);
    setError("");

    apiRequest(`/providers/${type}/${profileId}`, token)
      .then((fullProfile) => {
        if (active) setDetail(fullProfile);
      })
      .catch((reason) => {
        if (active) {
          setError(reason?.message || (hi ? "विवरण लोड नहीं हो सके।" : "Details could not be loaded."));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen, profileId, type, token, hi]);

  const title = type === "doctors"
    ? (detail?.full_name || (hi ? "डॉक्टर प्रोफ़ाइल" : "Doctor profile"))
    : (detail?.name || (hi ? "अस्पताल विवरण" : "Hospital details"));

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="large" language={language}>
      {loading && <LoadingState label={hi ? "विवरण लोड हो रहे हैं…" : "Loading details…"} />}

      {error && (
        <div className="cv-modal-error" role="alert">
          <p>{error}</p>
          <button
            className="cv-button cv-button-quiet"
            type="button"
            onClick={() => {
              setError("");
              setLoading(true);
              apiRequest(`/providers/${type}/${profileId}`, token)
                .then(setDetail)
                .catch((reason) => setError(reason?.message || (hi ? "विवरण लोड नहीं हो सके।" : "Details could not be loaded.")))
                .finally(() => setLoading(false));
            }}
          >
            {hi ? "फिर कोशिश करें" : "Retry"}
          </button>
        </div>
      )}

      {!loading && !error && detail && (
        <ProviderDetailContent type={type} detail={detail} language={language} />
      )}

      {!loading && !error && !detail && (
        <p className="cv-subtle">{hi ? "विवरण उपलब्ध नहीं हैं।" : "Details are not available."}</p>
      )}
    </Modal>
  );
}
