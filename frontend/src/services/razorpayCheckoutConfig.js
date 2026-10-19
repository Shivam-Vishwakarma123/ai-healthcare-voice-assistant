/**
 * Request the existing payment methods plus UPI in Razorpay Standard Checkout.
 * This is a display preference only; Razorpay still enforces the methods
 * activated for the merchant account.
 */
export function razorpayPaymentDisplayConfig() {
  return {
    display: {
      blocks: {
        carevoice_payment_options: {
          name: "Payment Options",
          instruments: [
            { method: "upi" },
            { method: "card" },
            { method: "netbanking" },
            { method: "wallet" },
          ],
        },
      },
      sequence: ["block.carevoice_payment_options"],
      preferences: { show_default_blocks: false },
    },
  };
}
