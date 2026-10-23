// Evaluates appointment invoice and transaction attributes to determine unified payment status.
export function getAppointmentPaymentState(appointment) {
  if (appointment.invoice_status === "paid") return "paid";
  if (appointment.invoice_status === "refunded") return "refunded";
  if (appointment.invoice_status === "partially_refunded") return "partially_refunded";
  if (appointment.invoice_status === "cancelled") return "invoice_cancelled";
  if (appointment.invoice_status === "unpaid") {
    if (["created", "processing"].includes(appointment.payment_status)) return "pending";
    if (["failed", "cancelled"].includes(appointment.payment_status)) {
      return appointment.can_start_payment === true ? appointment.payment_status : "not_due";
    }
    return appointment.can_start_payment === true ? "due" : "not_due";
  }
  if (!appointment.invoice_id && appointment.fee_minor > 0 && appointment.can_start_payment === true) {
    return "due";
  }
  return "not_due";
}

// Maps the current payment state to the relevant user action (pay, retry, view receipt, or check status).
export function getAppointmentPaymentAction(paymentState) {
  if (paymentState === "paid") return "receipt";
  if (["refunded", "partially_refunded"].includes(paymentState)) return "details";
  if (paymentState === "pending") return "check_status";
  if (["failed", "cancelled"].includes(paymentState)) return "retry";
  if (paymentState === "due") return "pay";
  return null;
}
