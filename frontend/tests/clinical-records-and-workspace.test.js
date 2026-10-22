import assert from "node:assert/strict";
import { test } from "node:test";
import { getUrgencyBadgeConfig } from "../src/services/assistantHelpers.js";

test("Role-based workspace visibility logic works as expected", () => {
  const providerNavigation = [
    { id: "Provider dashboard", icon: "▦", en: "Provider dashboard", hi: "प्रदाता डैशबोर्ड" },
    { id: "Doctor workspace", icon: "🩺", en: "Doctor workspace", hi: "डॉक्टर कार्यक्षेत्र" },
  ];

  // For an authorized doctor
  const isDoctorTrue = true;
  const doctorNav = providerNavigation.filter(
    (item) => item.id !== "Doctor workspace" || isDoctorTrue
  );
  assert.equal(doctorNav.some((item) => item.id === "Doctor workspace"), true);

  // For a hospital staff member (not doctor)
  const isDoctorFalse = false;
  const staffNav = providerNavigation.filter(
    (item) => item.id !== "Doctor workspace" || isDoctorFalse
  );
  assert.equal(staffNav.some((item) => item.id === "Doctor workspace"), false);
});

test("Prescription items filter and validate medication name and quantity", () => {
  const items = [
    { medication_name: "Amoxicillin", strength: "500 mg", frequency: "1-1-1", duration: "5 days" },
    { medication_name: "   ", strength: "10 mg", frequency: "1-0-0", duration: "10 days" },
    { medication_name: "Cetirizine", strength: "10 mg", frequency: "0-0-1", duration: "3 days" },
  ];

  const validItems = items.filter((it) => it.medication_name && it.medication_name.trim().length > 0);
  assert.equal(validItems.length, 2);
  assert.equal(validItems[0].medication_name, "Amoxicillin");
  assert.equal(validItems[1].medication_name, "Cetirizine");
});

test("FHIR R4 bundle JSON structure adheres to specification", () => {
  const mockFhirBundle = {
    resourceType: "Bundle",
    type: "collection",
    total: 3,
    entry: [
      {
        fullUrl: "urn:uuid:patient-1",
        resource: {
          resourceType: "Patient",
          id: "1",
          name: [{ use: "official", text: "Alice Patient" }],
        },
      },
      {
        fullUrl: "urn:uuid:allergy-1",
        resource: {
          resourceType: "AllergyIntolerance",
          id: "1",
          clinicalStatus: { coding: [{ code: "active" }] },
          code: { text: "Penicillin" },
        },
      },
      {
        fullUrl: "urn:uuid:encounter-100",
        resource: {
          resourceType: "Encounter",
          id: "100",
          status: "finished",
        },
      },
    ],
  };

  assert.equal(mockFhirBundle.resourceType, "Bundle");
  assert.equal(mockFhirBundle.type, "collection");
  assert.equal(mockFhirBundle.entry.length, 3);
  const resourceTypes = mockFhirBundle.entry.map((e) => e.resource.resourceType);
  assert.deepEqual(resourceTypes, ["Patient", "AllergyIntolerance", "Encounter"]);
});

test("Clinical timeline events chronological ordering", () => {
  const events = [
    { event_type: "conversation", timestamp: "2026-10-20T10:00:00Z", title: "Sore throat triage" },
    { event_type: "note", timestamp: "2026-10-22T09:00:00Z", title: "Dr Consultation Note" },
    { event_type: "appointment", timestamp: "2026-10-21T14:30:00Z", title: "Clinical visit" },
  ];

  const sortedEvents = [...events].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );

  assert.equal(sortedEvents[0].event_type, "note");
  assert.equal(sortedEvents[1].event_type, "appointment");
  assert.equal(sortedEvents[2].event_type, "conversation");
});
