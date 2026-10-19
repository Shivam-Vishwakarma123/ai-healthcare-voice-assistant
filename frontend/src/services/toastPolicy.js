const unsafeDetails = /traceback|stack trace|sqlalchemy|psycopg|select\s+.+\s+from\s|insert\s+into|update\s+\w+\s+set|razorpay_key_secret|webhook_secret|authorization:\s*bearer|\b(?:otp|cvv|card number)\s*[:=]/i;

export function sanitizeToastMessage(value) {
  const message = String(value || "").trim();
  if (!message) return "";
  if (unsafeDetails.test(message)) return "Something went wrong. Please try again. If the problem continues, contact support.";
  return message.length > 320 ? `${message.slice(0, 317)}…` : message;
}

export function isDuplicateToast(key, now, recent, windowMs = 1500) {
  const previous = recent.get(key) || 0;
  if (now - previous < windowMs) return true;
  if (recent.size >= 100) recent.clear();
  recent.set(key, now);
  return false;
}
