import { chromium } from "playwright";
import assert from "node:assert/strict";

const BASE_URL = "http://127.0.0.1:3000";

const VIEWPORTS = [
  { name: "320px (iPhone SE)", width: 320, height: 568 },
  { name: "375px (iPhone standard)", width: 375, height: 667 },
  { name: "390px (iPhone 13/14)", width: 390, height: 844 },
  { name: "430px (iPhone Plus/Max)", width: 430, height: 932 },
  { name: "768px (iPad portrait)", width: 768, height: 1024 },
  { name: "1280px (Standard desktop)", width: 1280, height: 800 },
];

async function runBrowserVerification() {
  console.log("🚀 Starting Playwright verification for Symptom Guidance Modal...");

  const browser = await chromium.launch({
    headless: true,
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });

  const page = await context.newPage();

  try {
    // 1. Navigate to the landing page with public triage
    console.log("📄 Navigating to", BASE_URL);
    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Ensure Public Triage section is present
    const triageSection = page.locator(".public-triage");
    await triageSection.waitFor({ state: "visible", timeout: 10000 });
    console.log("✅ Public Triage section found on landing page");

    const textarea = page.locator("#public-triage-symptoms");
    const submitBtn = page.locator(".cv-triage-submit");

    // 2. Test Empty Validation
    console.log("🧪 Testing empty symptom validation...");
    await textarea.fill("");
    await submitBtn.click();
    const valError = page.locator(".cv-triage-validation");
    await valError.waitFor({ state: "visible" });
    const valText = await valError.textContent();
    assert.match(valText, /describe your symptoms/i, "Empty error text must guide user");

    // Verify modal is NOT opened
    const modalBefore = page.locator(".cv-modal-guidance");
    assert.equal(await modalBefore.count(), 0, "Modal must not open on invalid submission");

    // 3. Test Short Input (< 2 chars)
    console.log("🧪 Testing short input validation (< 2 characters)...");
    await textarea.fill("a");
    await submitBtn.click();
    await page.waitForTimeout(100);
    const shortValText = await valError.textContent();
    assert.match(shortValText, /at least 2 characters/i, "Short error text must guide user");
    assert.equal(await modalBefore.count(), 0, "Modal must not open on short submission");

    // 4. Test Emergency Triage Flow
    console.log("🧪 Testing emergency symptom triage and modal presentation...");
    const emergencyInput = "Severe crushing chest pain radiating to left arm and jaw with cold sweat";
    await textarea.fill(emergencyInput);
    await submitBtn.click();

    // Verify modal opens with correct emergency hierarchy
    const modal = page.locator(".cv-modal-guidance");
    await modal.waitFor({ state: "visible", timeout: 10000 });
    console.log("✅ SymptomGuidanceModal opened successfully");

    // Verify ARIA semantics
    const dialogRole = await modal.getAttribute("role");
    const ariaModal = await modal.getAttribute("aria-modal");
    assert.equal(dialogRole, "dialog", "Modal must have role='dialog'");
    assert.equal(ariaModal, "true", "Modal must have aria-modal='true'");

    // Verify title and header badge
    const modalTitle = page.locator("#cv-modal-title");
    assert.equal(await modalTitle.textContent(), "Your Safety Guidance");

    const headerBadge = page.locator(".cv-modal .cv-urgency-badge");
    const badgeText = await headerBadge.textContent();
    assert.match(badgeText, /Emergency/i, "Urgency badge must show Emergency");

    // Verify status banner and emergency alert
    const statusBanner = page.locator(".cv-guidance-status-banner");
    await statusBanner.waitFor({ state: "visible" });
    const statusTitle = page.locator(".cv-guidance-status-title");
    assert.match(await statusTitle.textContent(), /Seek Emergency Care Immediately/i);

    // Verify emergency red flag warning
    const emergencyAlert = page.locator(".cv-guidance-emergency-alert");
    await emergencyAlert.waitFor({ state: "visible" });

    // Verify emergency phone links (112, 108)
    const phone112 = page.locator('a[href="tel:112"]');
    assert.ok(await phone112.count() > 0, "Link to 112 must be present");

    // Verify inline result is NOT rendered in the form flow below the form
    const inlineResult = page.locator(".cv-triage-form + .triage-result");
    assert.equal(await inlineResult.count(), 0, "No inline result rendered below the form");

    // 5. Test Escape Key Dismissal & Symptom Text Retention
    console.log("🧪 Testing Escape key dismissal and state retention...");
    await page.keyboard.press("Escape");
    await modal.waitFor({ state: "hidden" });
    console.log("✅ Modal closed via Escape key");

    // Verify symptom textarea retained text
    const retainedText = await textarea.inputValue();
    assert.equal(retainedText, emergencyInput, "Symptom textarea must retain entered symptoms");

    // Verify reopen card is visible
    const reopenCard = page.locator(".cv-triage-reopen-card");
    await reopenCard.waitFor({ state: "visible" });
    console.log("✅ Compact reopen card visible after closing modal");

    // Click "View safety guidance" to reopen modal without refetching
    const reopenBtn = page.locator(".cv-triage-reopen-btn");
    await reopenBtn.click();
    await modal.waitFor({ state: "visible" });
    console.log("✅ Reopened modal via 'View safety guidance' button");

    // Close modal via close button
    const closeBtn = page.locator(".cv-modal-close");
    await closeBtn.click();
    await modal.waitFor({ state: "hidden" });
    console.log("✅ Modal closed via close button");

    // 6. Test Insufficient Information / Clarifying Questions Flow
    console.log("🧪 Testing insufficient information triage and clarifying question chips...");
    await textarea.fill("cough");
    await submitBtn.click();
    await modal.waitFor({ state: "visible" });

    // Verify heading format (no raw enum dump)
    const infoStatusTitle = page.locator(".cv-guidance-status-title");
    const titleText = await infoStatusTitle.textContent();
    assert.ok(
      !titleText.includes("INSUFFICIENT_INFORMATION"),
      "Must not dump raw INSUFFICIENT_INFORMATION enum"
    );
    console.log("✅ Formatted status title:", titleText);

    // If follow-up question chips exist, test clicking one
    const followupChips = page.locator(".cv-followup-chip");
    const chipCount = await followupChips.count();
    if (chipCount > 0) {
      const chipText = await followupChips.first().textContent();
      const questionClean = chipText.replace(/^\+\s*/, "").trim();
      await followupChips.first().click();
      await modal.waitFor({ state: "hidden" });
      const updatedSymptoms = await textarea.inputValue();
      assert.ok(
        updatedSymptoms.includes(questionClean),
        "Clicking clarification chip must append question text to symptoms"
      );
      console.log("✅ Clarification chip clicked and appended to symptoms textarea");
    }

    // 7. Test Responsive Layout across all 6 target viewports
    console.log("🧪 Testing responsiveness across 6 viewports in Light & Dark modes...");
    // Reopen modal with chest pain for comprehensive layout check
    await textarea.fill("Chest tightness and shortness of breath when climbing stairs");
    await submitBtn.click();
    await modal.waitFor({ state: "visible" });

    for (const theme of ["light", "dark"]) {
      console.log(`\n  🎨 Testing theme: ${theme}`);
      await page.evaluate((th) => {
        document.documentElement.dataset.theme = th;
        document.documentElement.style.colorScheme = th;
      }, theme);
      await page.waitForTimeout(100);

      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await page.waitForTimeout(150);

        // Verify no horizontal document overflow
        const overflow = await page.evaluate(() => {
          return {
            docScrollWidth: document.documentElement.scrollWidth,
            winInnerWidth: window.innerWidth,
            bodyScrollWidth: document.body.scrollWidth,
          };
        });

        assert.ok(
          overflow.docScrollWidth <= overflow.winInnerWidth + 1,
          `No horizontal scroll allowed at ${vp.name}. scrollWidth: ${overflow.docScrollWidth}, innerWidth: ${overflow.winInnerWidth}`
        );

        // Verify modal dialog bounding box fits inside viewport
        const modalBox = await modal.boundingBox();
        assert.ok(modalBox, `Modal bounding box must exist at ${vp.name}`);
        assert.ok(
          modalBox.width <= vp.width,
          `Modal width (${modalBox.width}px) must not exceed viewport width (${vp.width}px) at ${vp.name}`
        );
        assert.ok(
          modalBox.height <= vp.height,
          `Modal height (${modalBox.height}px) must not exceed viewport height (${vp.height}px) at ${vp.name}`
        );

        console.log(`    ✓ Viewport ${vp.name} [${vp.width}x${vp.height}] fits perfectly: modal is ${Math.round(modalBox.width)}x${Math.round(modalBox.height)}px`);
      }
    }

    console.log("\n🎉 ALL PLAYWRIGHT E2E ASSERTIONS PASSED SUCCESSFULLY!");
  } finally {
    await browser.close();
  }
}

runBrowserVerification().catch((err) => {
  console.error("❌ Verification failed:", err);
  process.exit(1);
});
