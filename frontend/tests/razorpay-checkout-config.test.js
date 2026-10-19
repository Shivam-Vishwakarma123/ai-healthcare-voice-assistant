import test from "node:test";
import assert from "node:assert/strict";
import { razorpayPaymentDisplayConfig } from "../src/services/razorpayCheckoutConfig.js";

test("requests UPI alongside the existing checkout methods", () => {
  const config = razorpayPaymentDisplayConfig();
  assert.deepEqual(
    config.display.blocks.carevoice_payment_options.instruments,
    [
      { method: "upi" },
      { method: "card" },
      { method: "netbanking" },
      { method: "wallet" },
    ],
  );
  assert.deepEqual(config.display.sequence, ["block.carevoice_payment_options"]);
  assert.equal(config.display.preferences.show_default_blocks, false);
  assert.equal(config.display.hide, undefined);
});
