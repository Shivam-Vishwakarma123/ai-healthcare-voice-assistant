import { chromium } from "playwright";
import assert from "node:assert/strict";

const CREDENTIALS = {
  email: "patient01@demo.carevoice.test",
  password: "CareVoiceDemo2026!",
};

async function login() {
  const resp = await fetch("http://127.0.0.1:8000/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(CREDENTIALS),
  });
  if (!resp.ok) throw new Error(`Auth failed: ${resp.status}`);
  return await resp.json();
}

async function runE2ETests() {
  console.log("=== CareVoice AI Health Records Full Feature & PDF Verification ===");
  const auth = await login();
  console.log(`✓ Authenticated: ${auth.user.full_name} (ID: ${auth.user.id})`);

  // Verify Backend API & Patient Ownership
  console.log("\n--- Validating Backend Prescriptions & Patient Ownership ---");
  const rxResp = await fetch("http://127.0.0.1:8000/api/v1/records/prescriptions?include_drafts=true", {
    headers: { Authorization: `Bearer ${auth.access_token}` },
  });
  assert.equal(rxResp.status, 200, "Prescriptions API must return 200");
  const rxList = await rxResp.json();
  console.log(`✓ Found ${rxList.length} prescriptions for patient.`);
  assert.ok(rxList.length > 0, "Patient must have prescriptions on file");

  for (const rx of rxList) {
    assert.equal(rx.patient_user_id, auth.user.id, `Rx ${rx.prescription_number} does not belong to patient!`);
    console.log(`  - Rx: ${rx.prescription_number} | Status: ${rx.status} | is_ai_draft: ${rx.is_ai_draft} | Doctor: ${rx.doctor_name || "N/A"}`);
  }

  // Verify PDF Generation Endpoint
  console.log("\n--- Validating Prescription PDF Generation ---");
  const firstRx = rxList[0];
  const pdfResp = await fetch(`http://127.0.0.1:8000/api/v1/records/prescriptions/${firstRx.id}/pdf`, {
    headers: { Authorization: `Bearer ${auth.access_token}` },
  });
  assert.equal(pdfResp.status, 200, "PDF endpoint must return 200");
  const contentType = pdfResp.headers.get("content-type");
  assert.ok(contentType?.includes("application/pdf"), `Content type should be application/pdf, got ${contentType}`);
  const pdfBuffer = await pdfResp.arrayBuffer();
  const pdfBytes = new Uint8Array(pdfBuffer);
  const pdfHeader = String.fromCharCode(...pdfBytes.slice(0, 5));
  assert.equal(pdfHeader, "%PDF-", "PDF file header must start with %PDF-");
  console.log(`✓ Prescription PDF for ${firstRx.prescription_number} generated successfully (${pdfBytes.length} bytes, header: ${pdfHeader})`);

  // Verify Doctor Notes PDF Generation
  console.log("\n--- Validating Clinical Note PDF Generation ---");
  const notesResp = await fetch("http://127.0.0.1:8000/api/v1/records/notes", {
    headers: { Authorization: `Bearer ${auth.access_token}` },
  });
  const notesList = await notesResp.json();
  if (notesList.length > 0) {
    const notePdfResp = await fetch(`http://127.0.0.1:8000/api/v1/records/notes/${notesList[0].id}/pdf`, {
      headers: { Authorization: `Bearer ${auth.access_token}` },
    });
    assert.equal(notePdfResp.status, 200, "Note PDF endpoint must return 200");
    const notePdfBuffer = await notePdfResp.arrayBuffer();
    const noteHeader = String.fromCharCode(...new Uint8Array(notePdfBuffer).slice(0, 5));
    assert.equal(noteHeader, "%PDF-", "Note PDF must start with %PDF-");
    console.log(`✓ Clinical Note PDF for Note #${notesList[0].id} generated successfully (${notePdfBuffer.byteLength} bytes)`);
  }

  // Browser UI & Interaction Testing
  console.log("\n--- Testing UI Tabs, Modals, and Card Grid in Browser ---");
  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  page.on("pageerror", (err) => {
    console.error("Page error:", err);
    process.exit(1);
  });

  await page.goto("http://127.0.0.1:3000");
  await page.evaluate((auth) => {
    localStorage.setItem("ahva_token", auth.access_token);
    localStorage.setItem("ahva_user", JSON.stringify(auth.user));
    localStorage.setItem("carevoice_theme", "light");
  }, auth);
  await page.reload();

  await page.waitForSelector("#welcome-patient-heading", { timeout: 15000 });
  await page.locator(".cv-nav-item:has-text('Health records')").click();
  await page.waitForSelector(".health-records-tabs");

  // Test tabs
  const testTabs = [
    { name: "Prescriptions", selector: ".record-card-rx" },
    { name: "Doctor Notes", selector: ".record-card" },
    { name: "Timeline", selector: ".timeline-item, .record-card, .cv-empty" },
    { name: "AI Reports", selector: ".record-card, .cv-empty" },
    { name: "Lab & Diagnostic", selector: ".record-card, .cv-empty, table" },
  ];

  for (const tab of testTabs) {
    console.log(`Testing tab: [${tab.name}]...`);
    const tabBtn = page.locator(`[role='tab']:has-text('${tab.name}')`);
    await tabBtn.click();
    await page.waitForSelector(tab.selector, { timeout: 10000 });
    console.log(`  ✓ Tab [${tab.name}] loaded successfully.`);
  }

  // Return to Prescriptions Tab
  console.log("\n--- Testing Prescriptions Filtering & Detail Modal ---");
  await page.locator("[role='tab']:has-text('Prescriptions')").click();
  await page.waitForSelector(".record-card-rx");

  // Verify Grid Layout
  const gridCount = await page.$$eval(".health-records-cards-grid .record-card-rx", (cards) => cards.length);
  console.log(`✓ Prescriptions grid rendered with ${gridCount} cards.`);
  assert.equal(gridCount, rxList.length, "Grid card count should match API count");

  // Test "Doctor Signed" filter button
  console.log("Testing 'Doctor Signed' filter...");
  await page.locator(".health-records-filter-strip button:has-text('Doctor Signed')").click();
  await page.waitForTimeout(300);
  const signedCards = await page.$$eval(".record-card-rx", (cards) => cards.length);
  console.log(`  ✓ 'Doctor Signed' filter shows ${signedCards} cards.`);

  // Test "AI Drafts" filter button
  console.log("Testing 'AI Drafts' filter...");
  await page.locator(".health-records-filter-strip button:has-text('AI Drafts')").click();
  await page.waitForTimeout(300);
  const draftCards = await page.$$eval(".record-card-rx", (cards) => cards.length);
  console.log(`  ✓ 'AI Drafts' filter shows ${draftCards} cards.`);

  // Reset filter to "All"
  await page.locator(".health-records-filter-strip button:has-text('All')").click();
  await page.waitForTimeout(300);

  // Open "View Details" Modal
  console.log("Testing 'View Details' modal...");
  const viewBtn = page.locator(".record-card-rx button:has-text('View Details')").first();
  await viewBtn.click();

  // Verify Modal Content
  await page.waitForSelector(".cv-modal-content, [role='dialog']");
  const modalText = await page.textContent(".cv-modal-content, [role='dialog']");
  assert.ok(modalText.includes("Prescription"), "Modal should mention Prescription");
  console.log("  ✓ Prescription detail modal opened with structured medical details.");

  // Close modal
  const closeBtn = page.locator(".cv-modal-close, button:has-text('Close')").first();
  await closeBtn.click();
  await page.waitForSelector(".cv-modal-content", { state: "detached" });
  console.log("  ✓ Detail modal closed cleanly.");

  await browser.close();
  console.log("\n🎉 ALL HEALTH RECORDS TESTS AND VERIFICATIONS PASSED!");
}

runE2ETests().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
