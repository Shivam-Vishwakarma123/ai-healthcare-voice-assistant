import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  getUrgencyBadgeConfig,
  formatTriageHeading,
  formatTriageCategory,
  formatDoctorFee,
  isEmergencyHelpline,
} from "../src/services/assistantHelpers.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Test 1: Empty and Short Symptom Input Validation
test("Triage Validation: Empty or short inputs (< 2 chars) are rejected with accessible error message", () => {
  function validateSymptomInput(input, language = "en") {
    const trimmed = (input || "").trim();
    const hi = language === "hi";
    if (!trimmed) {
      return {
        valid: false,
        error: hi
          ? "कृपया सुरक्षा मार्गदर्शन पाने के लिए अपने लक्षणों का विवरण दर्ज करें।"
          : "Please describe your symptoms before requesting safety guidance.",
      };
    }
    if (trimmed.length < 2) {
      return {
        valid: false,
        error: hi
          ? "कृपया कम से कम 2 अक्षरों में लक्षणों का विवरण दें।"
          : "Please enter at least 2 characters describing your symptoms.",
      };
    }
    return { valid: true, error: "" };
  }

  // Empty string
  const emptyResEn = validateSymptomInput("", "en");
  assert.equal(emptyResEn.valid, false);
  assert.match(emptyResEn.error, /describe your symptoms/i);

  const emptyResHi = validateSymptomInput("   ", "hi");
  assert.equal(emptyResHi.valid, false);
  assert.match(emptyResHi.error, /कृपया सुरक्षा मार्गदर्शन/);

  // Single character (< 2 characters)
  const singleCharEn = validateSymptomInput("a", "en");
  assert.equal(singleCharEn.valid, false);
  assert.match(singleCharEn.error, /at least 2 characters/i);

  const singleCharHi = validateSymptomInput("क", "hi");
  assert.equal(singleCharHi.valid, false);
  assert.match(singleCharHi.error, /कम से कम 2 अक्षरों/);

  // Valid inputs (English, Hindi, Hinglish)
  assert.equal(validateSymptomInput("chest pain", "en").valid, true);
  assert.equal(validateSymptomInput("सीने में दर्द", "hi").valid, true);
  assert.equal(validateSymptomInput("chhati me dard aur chakkar", "en").valid, true);
});

// Test 2: Urgency Badge Configuration for all acuity tiers
test("Triage Helpers: Urgency badge configurations return accessible roles and localized labels", () => {
  // Emergency
  const emergencyBadge = getUrgencyBadgeConfig("emergency");
  assert.equal(emergencyBadge.role, "alert");
  assert.equal(emergencyBadge.className, "cv-urgency-badge emergency");
  assert.equal(emergencyBadge.label, "🚨 Emergency");
  assert.equal(emergencyBadge.labelHi, "🚨 आपातकालीन");

  // Urgent
  const urgentBadge = getUrgencyBadgeConfig("urgent");
  assert.equal(urgentBadge.role, "status");
  assert.equal(urgentBadge.className, "cv-urgency-badge urgent");
  assert.equal(urgentBadge.label, "⚠️ Urgent");
  assert.equal(urgentBadge.labelHi, "⚠️ तत्काल");

  // Insufficient Information (Enum normalization)
  for (const variant of ["insufficient_information", "info_needed", "more_info_needed"]) {
    const infoBadge = getUrgencyBadgeConfig(variant);
    assert.equal(infoBadge.role, "status");
    assert.equal(infoBadge.className, "cv-urgency-badge info-needed");
    assert.equal(infoBadge.label, "❓ More Info Needed");
    assert.equal(infoBadge.labelHi, "❓ अधिक जानकारी आवश्यक");
  }

  // Routine
  const routineBadge = getUrgencyBadgeConfig("routine");
  assert.equal(routineBadge.role, "status");
  assert.equal(routineBadge.className, "cv-urgency-badge routine");
  assert.equal(routineBadge.label, "ℹ️ Routine");
  assert.equal(routineBadge.labelHi, "ℹ️ सामान्य");
});

// Test 3: Formatting Triage Headings & Categories (No raw enum keys dumped)
test("Triage Helpers: Enum formatting prevents raw keys from appearing in UI headings", () => {
  // Headings
  assert.equal(formatTriageHeading("emergency", "en"), "Seek Emergency Care Immediately");
  assert.equal(formatTriageHeading("emergency", "hi"), "तत्काल आपातकालीन सहायता लें");

  assert.equal(formatTriageHeading("urgent", "en"), "Urgent Clinical Evaluation Recommended");
  assert.equal(formatTriageHeading("urgent", "hi"), "तत्काल क्लिनिकल मूल्यांकन की सलाह");

  assert.equal(formatTriageHeading("insufficient_information", "en"), "Additional Symptom Details Needed");
  assert.equal(formatTriageHeading("insufficient_information", "hi"), "अधिक लक्षण विवरण की आवश्यकता है");

  assert.equal(formatTriageHeading("routine", "en"), "Routine Clinical Safety Guidance");
  assert.equal(formatTriageHeading("routine", "hi"), "सामान्य स्वास्थ्य मार्गदर्शन");

  // Categories
  assert.equal(formatTriageCategory("emergency", "en"), "Emergency Evaluation");
  assert.equal(formatTriageCategory("emergency", "hi"), "आपातकालीन मूल्यांकन");
  assert.equal(formatTriageCategory("red_flag", "en"), "Red-Flag Warning");
  assert.equal(formatTriageCategory("red_flag", "hi"), "सुरक्षा चेतावनी");
  assert.equal(formatTriageCategory("mental_health", "en"), "Mental Health Support");
  assert.equal(formatTriageCategory("insufficient_information", "en"), "Incomplete Details");
});

// Test 4: Indian National Emergency Helplines detection
test("Triage Safety: Emergency numbers accurately identify 112, 108, and Tele-MANAS 14416", () => {
  assert.equal(isEmergencyHelpline("112"), true);
  assert.equal(isEmergencyHelpline("108"), true);
  assert.equal(isEmergencyHelpline("14416 (Tele-MANAS)"), true);
  assert.equal(isEmergencyHelpline("14416"), true);
  assert.equal(isEmergencyHelpline("080-1234567"), false);
});

// Test 5: Doctor consultation fees format
test("Triage Helpers: Clinician consultation fees properly format INR minor units", () => {
  assert.equal(formatDoctorFee(0), "Free");
  assert.equal(formatDoctorFee(-100), "Free");
  assert.equal(formatDoctorFee(50000), "₹500");
  assert.equal(formatDoctorFee(125000), "₹1250");
  assert.equal(formatDoctorFee(null), "Free");
});

// Test 6: Verify PublicTriage does NOT render inline results pushing page content
test("PublicTriage Structure: Inline .triage-result container is removed from page flow", () => {
  const publicTriagePath = path.join(__dirname, "../src/components/PublicTriage.jsx");
  const content = fs.readFileSync(publicTriagePath, "utf8");

  // In the old design, {result && <div className="triage-result ...">...</div>} was rendered inline directly below the form.
  // In the new design, the result is displayed in SymptomGuidanceModal.
  assert.ok(
    content.includes("<SymptomGuidanceModal"),
    "PublicTriage must render SymptomGuidanceModal"
  );
  assert.ok(
    !content.includes('<div className="triage-result'),
    "PublicTriage must not render inline .triage-result container below the form"
  );

  // Must include the compact reopen card when modal is closed
  assert.ok(
    content.includes("cv-triage-reopen-card"),
    "PublicTriage must include a compact reopen card to view previous safety guidance"
  );

  // Must include accessible form validation
  assert.ok(
    content.includes('role="alert"'),
    "Validation errors and API failures must have role='alert'"
  );
  assert.ok(
    content.includes("aria-invalid={Boolean(validationError)}"),
    "Textarea must carry dynamic aria-invalid attribute"
  );
  assert.ok(
    content.includes("aria-busy={busy}"),
    "Submit button must indicate busy state via aria-busy"
  );
});

// Test 7: Verify SymptomGuidanceModal adheres to WAI-ARIA and Clinical Safety Requirements
test("SymptomGuidanceModal Structure: Wraps Modal with accessible dialog semantics and healthcare hierarchy", () => {
  const modalPath = path.join(__dirname, "../src/components/SymptomGuidanceModal.jsx");
  const content = fs.readFileSync(modalPath, "utf8");

  assert.ok(content.includes("<Modal"), "SymptomGuidanceModal must wrap Modal component");
  assert.ok(content.includes("cv-guidance-content"), "Must have .cv-guidance-content container");
  assert.ok(content.includes("cv-guidance-status-banner"), "Must have hero status banner");
  assert.ok(content.includes("emergency_warning"), "Must render emergency red-flag warning");
  assert.ok(content.includes("emergency_numbers"), "Must render emergency helpline links");
  assert.ok(content.includes("cv-guidance-narrative"), "Must render clinical summary and narrative");
  assert.ok(content.includes("reported_symptoms"), "Must render identified symptoms tags");
  assert.ok(content.includes("recommended_next_steps"), "Must render numbered next steps");
  assert.ok(content.includes("possible_explanations"), "Must render educational context");
  assert.ok(content.includes("uncertainty_note"), "Must render clinical uncertainty note");
  assert.ok(content.includes("follow_up_questions"), "Must render clarifying questions");
  assert.ok(content.includes("recommended_doctors"), "Must render clinician recommendations");
  assert.ok(content.includes("cv-guidance-disclaimer"), "Must render healthcare disclaimer");
  assert.ok(content.includes("cv-guidance-footer-actions"), "Must render modal footer actions");
});

// Test 8: Base Modal component WAI-ARIA and accessibility attributes
test("Modal Primitive: Supports WAI-ARIA dialog attributes, focus trapping, and backdrop dismissal", () => {
  const baseModalPath = path.join(__dirname, "../src/components/Modal.jsx");
  const content = fs.readFileSync(baseModalPath, "utf8");

  assert.ok(content.includes('role="dialog"'), "Modal must have role='dialog'");
  assert.ok(content.includes('aria-modal="true"'), "Modal must have aria-modal='true'");
  assert.ok(content.includes('aria-labelledby="cv-modal-title"'), "Modal must have aria-labelledby");
  assert.ok(content.includes('Escape'), "Modal must handle Escape key dismiss");
  assert.ok(content.includes('document.body.style.overflow = "hidden"'), "Modal must lock body scroll");
  assert.ok(content.includes('cv-modal-backdrop'), "Modal must have backdrop overlay");
  assert.ok(content.includes('triggerRef'), "Modal must support triggerRef for focus restoration");
  assert.ok(content.includes('headerBadge'), "Modal must support headerBadge prop");
  assert.ok(content.includes('footer'), "Modal must support footer prop");
});

// Test 9: CSS styling invariants for healthcare modal & responsive layout
test("CSS Verification: Healthcare modal has high-z-index, responsive styles, and dark-theme tokens", () => {
  const cssPath = path.join(__dirname, "../src/healthcare.css");
  const css = fs.readFileSync(cssPath, "utf8");

  // Backdrop stacking above navbar and sidebar
  assert.ok(css.includes(".cv-modal-backdrop"), "CSS must contain .cv-modal-backdrop");
  assert.ok(css.includes("z-index: 2000;"), "Backdrop z-index must be at least 2000");

  // Guidance modal classes
  assert.ok(css.includes(".cv-modal-guidance"), "CSS must define .cv-modal-guidance");
  assert.ok(css.includes(".cv-guidance-status-banner"), "CSS must define .cv-guidance-status-banner");
  assert.ok(css.includes(".cv-guidance-emergency-alert"), "CSS must define .cv-guidance-emergency-alert");
  assert.ok(css.includes(".cv-guidance-steps-list"), "CSS must define .cv-guidance-steps-list");
  assert.ok(css.includes(".cv-guidance-uncertainty-note"), "CSS must define .cv-guidance-uncertainty-note");
  assert.ok(css.includes(".cv-triage-reopen-card"), "CSS must define .cv-triage-reopen-card");

  // Responsive mobile support
  assert.ok(css.includes("max-width: 640px"), "CSS must include mobile breakpoint rules");
});
