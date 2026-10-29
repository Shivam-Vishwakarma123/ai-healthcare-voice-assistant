import Modal from "./Modal";
import {
  formatDoctorFee,
  formatTriageCategory,
  formatTriageHeading,
  getUrgencyBadgeConfig,
} from "../services/assistantHelpers";

// Professional healthcare guidance modal displaying real deterministic triage results,
// emergency warnings, actionable next steps, clarifying prompts, and clinician recommendations.
export default function SymptomGuidanceModal({
  isOpen,
  onClose,
  result,
  language = "en",
  onNavigate,
  onEditSymptoms,
  triggerRef,
}) {
  const hi = language === "hi";

  if (!isOpen || !result) return null;

  const urgency = (result.urgency || result.urgency_level || "routine").toLowerCase();
  const isEmergency = urgency === "emergency" || result.safety_block || Boolean(result.emergency_warning);
  const isUrgent = urgency === "urgent";
  const isInsufficient = urgency === "insufficient_information" || urgency === "info_needed" || urgency === "more_info_needed";
  const badgeConfig = getUrgencyBadgeConfig(urgency);
  const statusHeading = formatTriageHeading(urgency, language);
  const categoryLabel = formatTriageCategory(result.category, language);

  function handleClarificationClick(questionText) {
    if (onEditSymptoms) {
      onEditSymptoms(questionText);
    } else {
      onClose();
    }
  }

  function handleEditClick() {
    if (onEditSymptoms) {
      onEditSymptoms();
    } else {
      onClose();
    }
  }

  const modalFooter = (
    <div className="cv-guidance-footer-actions">
      <div className="cv-guidance-footer-left">
        {isEmergency && result.emergency_numbers?.length > 0 && (
          <a
            href={`tel:${String(result.emergency_numbers[0]).replace(/\D/g, "")}`}
            className="cv-button cv-button-danger cv-emergency-action-btn"
          >
            🚨 {hi ? `${result.emergency_numbers[0]} पर कॉल करें` : `Call ${result.emergency_numbers[0]} Now`}
          </a>
        )}
        {!isEmergency && onNavigate && result.recommended_doctors?.length > 0 && (
          <button
            type="button"
            className="cv-button cv-button-primary"
            onClick={() => {
              onClose();
              onNavigate("Find care");
            }}
          >
            🩺 {hi ? "केयर डायरेक्टरी देखें →" : "Explore care directory →"}
          </button>
        )}
      </div>
      <div className="cv-guidance-footer-right">
        <button
          type="button"
          className="cv-button cv-button-secondary"
          onClick={handleEditClick}
        >
          ✏️ {hi ? "लक्षण बदलें" : "Edit Symptoms"}
        </button>
        <button
          type="button"
          className="cv-button cv-button-quiet"
          onClick={onClose}
        >
          {hi ? "बंद करें" : "Close"}
        </button>
      </div>
    </div>
  );

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={hi ? "आपकी सुरक्षा मार्गदर्शन" : "Your Safety Guidance"}
      subtitle={
        hi
          ? "बताए गए लक्षणों के आधार पर शैक्षिक सुरक्षा मार्गदर्शन — यह पक्का डॉक्टरी निदान नहीं है।"
          : "Educational safety guidance based on reported symptoms — not a confirmed diagnosis."
      }
      headerBadge={
        <span className={badgeConfig.className} role={badgeConfig.role}>
          {hi ? badgeConfig.labelHi : badgeConfig.label}
        </span>
      }
      footer={modalFooter}
      size="medium"
      language={language}
      className="cv-modal-guidance"
      bodyClassName="cv-modal-guidance-body"
      triggerRef={triggerRef}
    >
      <div
        className={`cv-guidance-content triage-result ${
          isEmergency ? "emergency" : isUrgent ? "urgent" : isInsufficient ? "info-needed" : "routine"
        }`}
        role={isEmergency ? "alert" : "status"}
      >
        {/* Acuity Status Hero Banner */}
        <div
          className={`cv-guidance-status-banner ${
            isEmergency ? "emergency" : isUrgent ? "urgent" : isInsufficient ? "info-needed" : "routine"
          }`}
        >
          <div className="cv-guidance-status-row">
            <span className="cv-guidance-status-icon" aria-hidden="true">
              {isEmergency ? "🚨" : isUrgent ? "⚠️" : isInsufficient ? "❓" : "ℹ️"}
            </span>
            <div className="cv-guidance-status-copy">
              <h3 className="cv-guidance-status-title">{statusHeading}</h3>
              {categoryLabel && (
                <span className="cv-guidance-category-pill">{categoryLabel}</span>
              )}
            </div>
          </div>
        </div>

        {/* Emergency Red-Flag Warning */}
        {result.emergency_warning && (
          <div className="notice error cv-guidance-emergency-alert" role="alert">
            <div className="cv-guidance-emergency-alert-inner">
              <span className="cv-guidance-alert-icon" aria-hidden="true">⚠️</span>
              <strong>{result.emergency_warning}</strong>
            </div>
          </div>
        )}

        {/* Emergency Numbers Callout */}
        {result.emergency_numbers?.length > 0 && (
          <div className="cv-triage-emergency-callout cv-guidance-callout">
            <b>{hi ? "आपातकालीन नंबर पर तुरंत कॉल करें:" : "Call emergency helpline now:"}</b>
            <div className="cv-emergency-pills">
              {result.emergency_numbers.map((number, index) => (
                <a
                  key={`${number}-${index}`}
                  href={`tel:${String(number).replace(/\D/g, "")}`}
                  className="cv-emergency-pill"
                >
                  📞 {number}
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Primary Summary & Guidance */}
        <div className="cv-guidance-narrative">
          {result.summary && (
            <p className="cv-guidance-summary">{result.summary}</p>
          )}
          {result.guidance && (
            <p className="cv-guidance-text">{result.guidance}</p>
          )}
        </div>

        {/* Identified Symptoms Pills */}
        {result.reported_symptoms?.length > 0 && (
          <div className="cv-guidance-section">
            <span className="cv-guidance-section-label">
              {hi ? "पहचाने गए लक्षण:" : "Identified symptoms:"}
            </span>
            <div className="cv-symptom-tag-list">
              {result.reported_symptoms.map((symptom, idx) => (
                <span key={`${symptom}-${idx}`} className="cv-symptom-tag">
                  {symptom}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Recommended Action Steps */}
        {result.recommended_next_steps?.length > 0 && (
          <div className="cv-guidance-section">
            <h4 className="cv-guidance-section-title">
              📋 {hi ? "अनुशंसित अगले कदम:" : "Recommended next steps:"}
            </h4>
            <ol className="cv-guidance-steps-list">
              {result.recommended_next_steps.map((step, idx) => (
                <li key={idx}>{step}</li>
              ))}
            </ol>
          </div>
        )}

        {/* Possible Explanations / Educational Context */}
        {result.possible_explanations?.length > 0 && (
          <div className="cv-guidance-section">
            <h4 className="cv-guidance-section-title">
              💡 {hi ? "संभावित संदर्भ (शैक्षिक केवल):" : "Possible context (educational only):"}
            </h4>
            <ul className="cv-guidance-list">
              {result.possible_explanations.map((exp, idx) => (
                <li key={idx}>{exp}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Clinical Uncertainty Note */}
        {result.uncertainty_note && (
          <div className="cv-guidance-uncertainty-note" role="note">
            <span aria-hidden="true">ℹ️</span>
            <span>{result.uncertainty_note}</span>
          </div>
        )}

        {/* Clarifying Follow-up Questions (Click to add to symptoms) */}
        {result.follow_up_questions?.length > 0 && (
          <div className="cv-guidance-section cv-guidance-followup-section">
            <h4 className="cv-guidance-section-title">
              💬 {hi ? "अधिक जानकारी जोड़ें (लक्षणों में जोड़ने हेतु क्लिक करें):" : "Clarify details (click to add to symptoms):"}
            </h4>
            <div className="cv-followup-chips">
              {result.follow_up_questions.map((question, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="cv-followup-chip"
                  onClick={() => handleClarificationClick(question)}
                  title={hi ? "लक्षणों में जोड़ें और संपादित करें" : "Add to symptoms and edit"}
                >
                  + {question}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Verified Doctor Recommendations (if returned by API) */}
        {result.recommended_doctors?.length > 0 && (
          <div className="cv-guidance-section cv-doctor-recommendations">
            <div className="cv-doctor-recommendations-title">
              <span>🩺</span>
              <span>
                {hi ? "उपलब्ध सत्यापित विशेषज्ञ:" : "Verified Clinicians in Directory:"}
              </span>
            </div>
            <div className="cv-doctor-grid">
              {result.recommended_doctors.map((doc) => (
                <div key={doc.doctor_id} className="cv-doctor-card">
                  <div className="cv-doctor-card-header">
                    <h5 className="cv-doctor-card-name">Dr. {doc.doctor_name}</h5>
                    <div className="cv-doctor-card-specialty">{doc.specialty}</div>
                    {doc.hospital_name && (
                      <div className="cv-doctor-card-hospital">🏥 {doc.hospital_name}</div>
                    )}
                  </div>
                  {doc.match_reasons?.length > 0 && (
                    <ul className="cv-doctor-card-reasons">
                      {doc.match_reasons.slice(0, 2).map((reason, idx) => (
                        <li key={idx}>{reason}</li>
                      ))}
                    </ul>
                  )}
                  <div className="cv-doctor-card-footer">
                    <span className="cv-doctor-card-fee">
                      {formatDoctorFee(doc.fee_minor)}
                    </span>
                    {onNavigate && (
                      <button
                        type="button"
                        className="cv-doctor-book-btn"
                        onClick={() => {
                          onClose();
                          onNavigate("Find care");
                        }}
                      >
                        {hi ? "अपॉइंटमेंट बुक करें →" : "Book appointment →"}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Clinical Disclaimer */}
        <div className="cv-guidance-disclaimer">
          <p>
            {result.disclaimer ||
              (hi
                ? "यह सीमित जाँच आपातकाल को खारिज नहीं कर सकती और निदान नहीं है। खतरा हो तो अभी 112 या 108 पर कॉल करें।"
                : "This limited check cannot rule out an emergency and is not a diagnosis. If you may be in danger, call 112 or 108 now.")}
          </p>
        </div>
      </div>
    </Modal>
  );
}
