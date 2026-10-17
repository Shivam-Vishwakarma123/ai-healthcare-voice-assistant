const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");

function normalizeHeaders(headers) {
  if (!headers) return {};
  if (headers instanceof Headers) return Object.fromEntries(headers.entries());
  if (Array.isArray(headers)) return Object.fromEntries(headers);
  if (typeof headers === "object") return { ...headers };
  return {};
}

export async function apiRequest(path, token, options = {}) {
  const isMultipart = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers = {
    ...(options.body && !isMultipart ? { "Content-Type": "application/json" } : {}),
    ...normalizeHeaders(options.headers),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  let response;
  try {
    response = await fetch(`${API_BASE}${normalizedPath}`, { ...options, headers });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    if (error instanceof TypeError) {
      throw new Error("Could not reach the CareVoice API. Check that the backend is running and that its CORS settings allow this page.");
    }
    throw error;
  }
  let data = null;
  if (response.status !== 204) {
    try {
      data = await response.json();
    } catch {
      if (response.ok) throw new Error("Server returned an invalid response.");
    }
  }
  if (!response.ok) {
    const message = typeof data?.detail === "string" ? data.detail : `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

export function readCachedUser() {
  try {
    const value = localStorage.getItem("ahva_user");
    return value ? JSON.parse(value) : null;
  } catch {
    try {
      localStorage.removeItem("ahva_user");
    } catch {
      return null;
    }
    return null;
  }
}

export function formatMoney(amountMinor, currency = "INR") {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(amountMinor / 100);
}
