/**
 * Assistant and Triage UI helpers.
 */

// Resolves localized labels, styling classes, and ARIA roles corresponding to clinical urgency levels.
export function getUrgencyBadgeConfig(urgency) {
  const norm = (urgency || "routine").toLowerCase();
  if (norm === "emergency") {
    return {
      label: "🚨 Emergency",
      labelHi: "🚨 आपातकालीन",
      className: "cv-urgency-badge emergency",
      role: "alert",
    };
  }
  if (norm === "urgent") {
    return {
      label: "⚠️ Urgent",
      labelHi: "⚠️ तत्काल",
      className: "cv-urgency-badge urgent",
      role: "status",
    };
  }
  if (norm === "insufficient_information" || norm === "info_needed" || norm === "more_info_needed") {
    return {
      label: "❓ More Info Needed",
      labelHi: "❓ अधिक जानकारी आवश्यक",
      className: "cv-urgency-badge info-needed",
      role: "status",
    };
  }
  return {
    label: "ℹ️ Routine",
    labelHi: "ℹ️ सामान्य",
    className: "cv-urgency-badge routine",
    role: "status",
  };
}

// Converts clinical urgency level into human-friendly prominent heading.
export function formatTriageHeading(urgency, language = "en") {
  const hi = language === "hi";
  const norm = (urgency || "routine").toLowerCase();
  if (norm === "emergency") {
    return hi ? "तत्काल आपातकालीन सहायता लें" : "Seek Emergency Care Immediately";
  }
  if (norm === "urgent") {
    return hi ? "तत्काल क्लिनिकल मूल्यांकन की सलाह" : "Urgent Clinical Evaluation Recommended";
  }
  if (norm === "insufficient_information" || norm === "info_needed" || norm === "more_info_needed") {
    return hi ? "अधिक लक्षण विवरण की आवश्यकता है" : "Additional Symptom Details Needed";
  }
  return hi ? "सामान्य स्वास्थ्य मार्गदर्शन" : "Routine Clinical Safety Guidance";
}

// Converts internal API triage category enums into clear, human-readable labels.
export function formatTriageCategory(category, language = "en") {
  if (!category) return "";
  const hi = language === "hi";
  const norm = category.toLowerCase().trim();
  const map = {
    emergency: { en: "Emergency Evaluation", hi: "आपातकालीन मूल्यांकन" },
    urgent: { en: "Urgent Review", hi: "तत्काल समीक्षा" },
    urgent_evaluation: { en: "Urgent Evaluation", hi: "तत्काल मूल्यांकन" },
    red_flag: { en: "Red-Flag Warning", hi: "सुरक्षा चेतावनी" },
    insufficient_information: { en: "Incomplete Details", hi: "अपूर्ण विवरण" },
    mental_health: { en: "Mental Health Support", hi: "मानसिक स्वास्थ्य सहायता" },
    safety: { en: "Safety Alert", hi: "सुरक्षा चेतावनी" },
    special_population: { en: "Special Population Guidance", hi: "विशेष जनसंख्या मार्गदर्शन" },
    advice: { en: "General Health Guidance", hi: "सामान्य स्वास्थ्य मार्गदर्शन" },
    routine_guidance: { en: "Routine Guidance", hi: "सामान्य मार्गदर्शन" },
  };
  if (map[norm]) {
    return hi ? map[norm].hi : map[norm].en;
  }
  return norm.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

// Formats consultation fee minor units into rupee currency representations or free status.
export function formatDoctorFee(feeMinor) {
  if (typeof feeMinor !== "number" || feeMinor <= 0) return "Free";
  return `₹${Math.round(feeMinor / 100)}`;
}

// Identifies national emergency and mental health crisis helplines (112, 108, Tele-MANAS 14416).
export function isEmergencyHelpline(number) {
  const clean = String(number).trim();
  return clean === "112" || clean === "108" || clean.includes("14416");
}
