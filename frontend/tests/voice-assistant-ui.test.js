import assert from "node:assert/strict";
import { test } from "node:test";
import {
  formatDoctorFee,
  getUrgencyBadgeConfig,
  isEmergencyHelpline,
} from "../src/services/assistantHelpers.js";

test("getUrgencyBadgeConfig maps urgency levels accurately", () => {
  const em = getUrgencyBadgeConfig("emergency");
  assert.equal(em.label, "🚨 Emergency");
  assert.equal(em.role, "alert");
  assert.ok(em.className.includes("emergency"));

  const urg = getUrgencyBadgeConfig("urgent");
  assert.equal(urg.label, "⚠️ Urgent");
  assert.ok(urg.className.includes("urgent"));

  const routine = getUrgencyBadgeConfig("routine");
  assert.equal(routine.label, "ℹ️ Routine");
  assert.ok(routine.className.includes("routine"));
});

test("formatDoctorFee converts minor units to INR display", () => {
  assert.equal(formatDoctorFee(50000), "₹500");
  assert.equal(formatDoctorFee(125000), "₹1250");
  assert.equal(formatDoctorFee(0), "Free");
  assert.equal(formatDoctorFee(null), "Free");
});

test("isEmergencyHelpline recognizes Indian emergency numbers", () => {
  assert.equal(isEmergencyHelpline("112"), true);
  assert.equal(isEmergencyHelpline("108"), true);
  assert.equal(isEmergencyHelpline("Tele-MANAS 14416"), true);
  assert.equal(isEmergencyHelpline("14416"), true);
  assert.equal(isEmergencyHelpline("9999999999"), false);
});
