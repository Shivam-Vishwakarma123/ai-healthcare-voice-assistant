import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { apiRequest } from "../src/services/api.js";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test("apiRequest sends JSON and bearer headers and returns JSON", async () => {
  let requestUrl;
  let requestOptions;
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    requestOptions = options;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await apiRequest("patients/me", "access-token", {
    method: "POST",
    body: JSON.stringify({ name: "Test" }),
  });

  assert.equal(requestUrl, "http://localhost:8000/api/v1/patients/me");
  assert.equal(requestOptions.headers.Authorization.startsWith("Bearer "), true);
  assert.equal(requestOptions.headers["Content-Type"], "application/json");
  assert.deepEqual(result, { ok: true });
});

test("apiRequest forwards idempotency headers unchanged", async () => {
  let requestOptions;
  globalThis.fetch = async (_url, options) => {
    requestOptions = options;
    return new Response(JSON.stringify({ id: 1 }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  };

  await apiRequest("/providers/appointments", "access-token", {
    method: "POST",
    headers: { "Idempotency-Key": "booking-command-123" },
    body: JSON.stringify({ doctor_id: 1 }),
  });

  assert.equal(requestOptions.headers["Idempotency-Key"], "booking-command-123");
});

test("apiRequest accepts Headers instances for request metadata", async () => {
  let requestOptions;
  globalThis.fetch = async (_url, options) => {
    requestOptions = options;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  await apiRequest("/providers/appointments", "access-token", {
    method: "POST",
    headers: new Headers({ "Idempotency-Key": "booking-command-456" }),
    body: JSON.stringify({ doctor_id: 2 }),
  });

  assert.equal(requestOptions.headers["Idempotency-Key"], "booking-command-456");
  assert.equal(requestOptions.headers.Authorization.startsWith("Bearer "), true);
});

test("apiRequest surfaces backend errors and uses a status fallback", async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: "Database unavailable" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  await assert.rejects(
    apiRequest("/health", null),
    (error) => error.message === "Database unavailable" && error.status === 503,
  );

  globalThis.fetch = async () => new Response("unavailable", { status: 502 });
  await assert.rejects(apiRequest("/health", null), /Request failed \(502\)/);
});

test("apiRequest explains a network or CORS connection failure", async () => {
  globalThis.fetch = async () => {
    throw new TypeError("Failed to fetch");
  };
  await assert.rejects(
    apiRequest("/providers/appointments", "access-token"),
    /Could not reach the CareVoice API.*backend.*CORS/i,
  );
});

test("apiRequest preserves aborted requests", async () => {
  const abortError = new DOMException("Request aborted", "AbortError");
  globalThis.fetch = async () => {
    throw abortError;
  };
  await assert.rejects(apiRequest("/providers/doctors", null), (error) => error === abortError);
});

test("apiRequest accepts an empty 204 response", async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 });
  assert.equal(await apiRequest("/resource", null), null);
});

test("apiRequest rejects malformed successful responses", async () => {
  globalThis.fetch = async () => new Response("not-json", { status: 200 });
  await assert.rejects(apiRequest("/resource", null), /invalid response/i);
});

test("apiRequest leaves multipart content type to the browser", async () => {
  let requestOptions;
  globalThis.fetch = async (_url, options) => {
    requestOptions = options;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  const form = new FormData();
  form.append("language", "hi");

  assert.deepEqual(await apiRequest("/assistant/speech-to-text", "access-token", {
    method: "POST",
    body: form,
  }), { ok: true });
  assert.equal(requestOptions.headers["Content-Type"], undefined);
  assert.equal(requestOptions.headers.Authorization.startsWith("Bearer "), true);
});
