import assert from "node:assert/strict";
import { test } from "node:test";
import { getAppointmentPaymentAction, getAppointmentPaymentState } from "../src/services/appointmentPayments.js";

test("unpaid appointments and future legacy visits without invoices can start payment", () => {
  assert.equal(getAppointmentPaymentState({ invoice_id: 3, invoice_status: "unpaid", can_start_payment: true }), "due");
  assert.equal(getAppointmentPaymentState({ status: "confirmed", fee_minor: 55000, invoice_id: null, can_start_payment: true }), "due");
});

test("paid appointments show receipt state and never offer another charge", () => {
  assert.equal(getAppointmentPaymentState({ invoice_id: 4, invoice_status: "paid", payment_status: "paid" }), "paid");
});

test("payment pending, failure and cancellation have distinct retry states", () => {
  assert.equal(getAppointmentPaymentState({ invoice_status: "unpaid", payment_status: "created" }), "pending");
  assert.equal(getAppointmentPaymentState({ invoice_status: "unpaid", payment_status: "failed", can_start_payment: true }), "failed");
  assert.equal(getAppointmentPaymentState({ invoice_status: "unpaid", payment_status: "cancelled", can_start_payment: true }), "cancelled");
});

test("backend eligibility prevents past or cancelled visits from starting or retrying payment", () => {
  assert.equal(getAppointmentPaymentState({ status: "scheduled", fee_minor: 85000, can_start_payment: false, payment_block_reason: "past" }), "not_due");
  assert.equal(getAppointmentPaymentState({ invoice_status: "unpaid", payment_status: "failed", can_start_payment: false }), "not_due");
  assert.equal(getAppointmentPaymentState({ status: "cancelled", fee_minor: 85000, can_start_payment: false }), "not_due");
  assert.equal(getAppointmentPaymentState({ status: "confirmed", fee_minor: 85000 }), "not_due");
});

test("appointment payment actions distinguish pending checks, retries and refund details", () => {
  assert.equal(getAppointmentPaymentAction("due"), "pay");
  assert.equal(getAppointmentPaymentAction("pending"), "check_status");
  assert.equal(getAppointmentPaymentAction("failed"), "retry");
  assert.equal(getAppointmentPaymentAction("cancelled"), "retry");
  assert.equal(getAppointmentPaymentAction("paid"), "receipt");
  assert.equal(getAppointmentPaymentAction("refunded"), "details");
  assert.equal(getAppointmentPaymentAction("partially_refunded"), "details");
  assert.equal(getAppointmentPaymentAction("not_due"), null);
});

test("unbilled past appointments and zero-fee appointments do not prompt charges", () => {
  assert.equal(getAppointmentPaymentState({ status: "completed", fee_minor: 55000 }), "not_due");
  assert.equal(getAppointmentPaymentState({ status: "scheduled", fee_minor: 0, can_start_payment: false }), "not_due");
});
