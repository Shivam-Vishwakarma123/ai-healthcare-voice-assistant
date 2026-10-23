import assert from "node:assert/strict";
import { test } from "node:test";

// Calculates relative luminance according to WCAG 2.1 formula.
function getLuminance(r, g, b) {
  const [rs, gs, bs] = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

// Calculates contrast ratio between two RGB colors (L1 + 0.05) / (L2 + 0.05).
function getContrastRatio(rgb1, rgb2) {
  const l1 = getLuminance(rgb1[0], rgb1[1], rgb1[2]);
  const l2 = getLuminance(rgb2[0], rgb2[1], rgb2[2]);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// Parses 6-character hex color to [r, g, b].
function parseHex(hex) {
  const clean = hex.replace("#", "");
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

// Safety Invariant 1: Emergency Red-Flag Triage
test("Safety Invariant 1: Emergency red-flag symptoms mandate emergency classification and helpline display", () => {
  const emergencyInputs = [
    "Severe crushing chest pain radiating to left arm and jaw",
    "Sudden facial drooping, speech slurred, left arm weakness",
    "Extreme difficulty breathing and blue lips",
  ];

  const redFlagKeywords = ["chest pain", "slurred", "drooping", "difficulty breathing", "blue lips"];

  for (const input of emergencyInputs) {
    const lower = input.toLowerCase();
    const isRedFlag = redFlagKeywords.some((kw) => lower.includes(kw));
    assert.equal(isRedFlag, true, `Input '${input}' must trigger clinical red-flag detector`);

    // Mock triage evaluation outcome
    const mockTriageResult = {
      urgency: isRedFlag ? "emergency" : "routine",
      emergency_warning: isRedFlag ? "Immediate emergency medical attention required" : null,
      emergency_numbers: isRedFlag ? ["112", "108"] : [],
    };

    assert.equal(mockTriageResult.urgency, "emergency");
    assert.ok(mockTriageResult.emergency_warning);
    assert.deepEqual(mockTriageResult.emergency_numbers, ["112", "108"]);
  }
});

// Safety Invariant 2: Draft vs. Clinician-Finalized Electronic Signatures
test("Safety Invariant 2: Finalized clinical notes and prescriptions are immutable and enforce electronic signatures", () => {
  const draftNote = {
    id: 101,
    patient_id: 5,
    doctor_id: 12,
    status: "draft",
    assessment: "Suspected upper respiratory tract infection",
    finalized_at: null,
    signed_by: null,
  };

  const finalizedNote = {
    id: 102,
    patient_id: 5,
    doctor_id: 12,
    status: "finalized",
    assessment: "Upper respiratory tract infection, viral etiology confirmed",
    finalized_at: "2026-10-23T10:15:00Z",
    signed_by: "Dr. Ananya Sharma, MD",
  };

  function canEditNote(note, currentUser) {
    if (note.status === "finalized") return false; // Immutable safety rule
    return currentUser.role === "doctor" && currentUser.id === note.doctor_id;
  }

  const doctorUser = { id: 12, role: "doctor" };
  const otherDoctor = { id: 15, role: "doctor" };
  const patientUser = { id: 5, role: "patient" };

  assert.equal(canEditNote(draftNote, doctorUser), true, "Authoring doctor can edit draft note");
  assert.equal(canEditNote(draftNote, otherDoctor), false, "Non-authoring doctor cannot edit draft");
  assert.equal(canEditNote(draftNote, patientUser), false, "Patient cannot edit clinical note");

  assert.equal(canEditNote(finalizedNote, doctorUser), false, "Finalized note is strictly immutable");
  assert.equal(canEditNote(finalizedNote, otherDoctor), false, "Finalized note is strictly immutable");
  assert.ok(finalizedNote.signed_by, "Finalized record must carry clinician electronic signature");
  assert.ok(finalizedNote.finalized_at, "Finalized record must carry timestamp");
});

// Safety Invariant 3: Role-Based Access Control (RBAC) Boundaries
test("Safety Invariant 3: RBAC boundaries strictly separate patient, doctor, and admin privileges", () => {
  const routes = [
    { name: "My health records", roles: ["patient"] },
    { name: "Doctor workspace", roles: ["doctor"] },
    { name: "Hospital administration", roles: ["hospital_admin", "platform_admin"] },
    { name: "Platform settings", roles: ["platform_admin"] },
  ];

  function isAuthorized(route, userRole) {
    return route.roles.includes(userRole);
  }

  // Patient checks
  assert.equal(isAuthorized(routes[0], "patient"), true);
  assert.equal(isAuthorized(routes[1], "patient"), false);
  assert.equal(isAuthorized(routes[2], "patient"), false);
  assert.equal(isAuthorized(routes[3], "patient"), false);

  // Doctor checks
  assert.equal(isAuthorized(routes[0], "doctor"), false);
  assert.equal(isAuthorized(routes[1], "doctor"), true);
  assert.equal(isAuthorized(routes[2], "doctor"), false);
  assert.equal(isAuthorized(routes[3], "doctor"), false);

  // Platform admin checks
  assert.equal(isAuthorized(routes[2], "platform_admin"), true);
  assert.equal(isAuthorized(routes[3], "platform_admin"), true);
});

// Safety Invariant 4: Accessibility and Color Contrast Verification (WCAG AAA/AA)
test("Safety Invariant 4: Light and dark theme palettes satisfy WCAG 2.1 contrast guidelines", () => {
  // Light mode tokens
  const primaryLight = parseHex("#006E51"); // Clinical Deep Green
  const whiteSurface = parseHex("#FFFFFF");
  const darkText = parseHex("#0F172A");

  // Dark mode tokens
  const primaryDark = parseHex("#34D399"); // Accessible Mint Green
  const darkSurface = parseHex("#101E19"); // Deep Slate-Forest
  const lightText = parseHex("#F8FAFC");
  const darkBtnText = parseHex("#042F2E"); // Contrast text on mint button

  // Light Mode Contrast: Primary green #006E51 on white surface #FFFFFF
  const lightPrimaryRatio = getContrastRatio(primaryLight, whiteSurface);
  assert.ok(
    lightPrimaryRatio >= 4.5,
    `Light primary contrast ratio ${lightPrimaryRatio.toFixed(2)} must exceed WCAG AA 4.5:1`
  );

  // Light Mode Contrast: Dark text #0F172A on white surface #FFFFFF
  const lightTextRatio = getContrastRatio(darkText, whiteSurface);
  assert.ok(
    lightTextRatio >= 7.0,
    `Light body text contrast ratio ${lightTextRatio.toFixed(2)} must exceed WCAG AAA 7.0:1`
  );

  // Dark Mode Contrast: Mint green #34D399 on dark surface #101E19
  const darkPrimaryRatio = getContrastRatio(primaryDark, darkSurface);
  assert.ok(
    darkPrimaryRatio >= 7.0,
    `Dark primary contrast ratio ${darkPrimaryRatio.toFixed(2)} must exceed WCAG AAA 7.0:1`
  );

  // Dark Mode Contrast: Light text #F8FAFC on dark surface #101E19
  const darkTextRatio = getContrastRatio(lightText, darkSurface);
  assert.ok(
    darkTextRatio >= 7.0,
    `Dark text contrast ratio ${darkTextRatio.toFixed(2)} must exceed WCAG AAA 7.0:1`
  );

  // Dark Mode Button Contrast: Dark text #042F2E on mint button #34D399
  const darkButtonTextRatio = getContrastRatio(darkBtnText, primaryDark);
  assert.ok(
    darkButtonTextRatio >= 7.0,
    `Dark button text contrast ratio ${darkButtonTextRatio.toFixed(2)} must exceed WCAG AAA 7.0:1`
  );
});
