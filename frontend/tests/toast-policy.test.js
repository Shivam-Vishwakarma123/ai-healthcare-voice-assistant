import test from "node:test";
import assert from "node:assert/strict";
import { isDuplicateToast, sanitizeToastMessage } from "../src/services/toastPolicy.js";

test("keeps useful cancellation copy safe for a toast", () => {
  assert.equal(sanitizeToastMessage("Payment cancelled. You can try again whenever you're ready."), "Payment cancelled. You can try again whenever you're ready.");
});

test("replaces stack traces and database details with safe copy", () => {
  assert.match(sanitizeToastMessage("Traceback (most recent call last): SELECT * FROM payments"), /Something went wrong/);
});

test("bounds long notifications", () => {
  assert.ok(sanitizeToastMessage("a".repeat(400)).length <= 320);
});

test("suppresses duplicate callback notifications within the dedupe window", () => {
  const recent = new Map();
  assert.equal(isDuplicateToast("error:failed", 10_000, recent), false);
  assert.equal(isDuplicateToast("error:failed", 10_500, recent), true);
  assert.equal(isDuplicateToast("error:failed", 12_000, recent), false);
});
