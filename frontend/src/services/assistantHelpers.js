/**
 * Assistant and Triage UI helpers.
 */

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

export function formatDoctorFee(feeMinor) {
  if (typeof feeMinor !== "number" || feeMinor <= 0) return "Free";
  return `₹${Math.round(feeMinor / 100)}`;
}

export function isEmergencyHelpline(number) {
  const clean = String(number).trim();
  return clean === "112" || clean === "108" || clean.includes("14416");
}
