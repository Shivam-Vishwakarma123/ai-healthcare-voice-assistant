const IST = "Asia/Kolkata";

// Formats appointment date-time timestamps into localized Indian Standard Time calendar representations.
export function formatAppointmentDateTime(value, locale = "en-IN") {
  return new Intl.DateTimeFormat(locale, {
    timeZone: IST,
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

// Extracts isolated day or month substrings formatted according to IST timezone conventions.
export function formatAppointmentDatePart(value, part, locale = "en-IN") {
  return new Intl.DateTimeFormat(locale, {
    timeZone: IST,
    day: part === "day" ? "2-digit" : undefined,
    month: part === "month" ? "short" : undefined,
  }).format(new Date(value));
}

// Computes ISO calendar date strings (YYYY-MM-DD) anchored to Indian Standard Time with offset day shifts.
export function getISTDate(offsetDays = 0) {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  const date = new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day) + offsetDays));
  return date.toISOString().slice(0, 10);
}

// Generates unique cryptographic UUIDs or secure fallback strings for API request idempotency keys.
export function createIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `appointment-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
