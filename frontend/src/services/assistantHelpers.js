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
  return {
    label: "ℹ️ Routine",
    labelHi: "ℹ️ सामान्य",
    className: "cv-urgency-badge routine",
    role: "status",
  };
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
