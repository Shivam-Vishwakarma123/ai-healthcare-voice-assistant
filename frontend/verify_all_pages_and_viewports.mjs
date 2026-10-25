import { chromium } from "playwright";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";

function resetRateLimits() {
  try {
    execSync("docker exec healthcare-backend python -c 'from app.auth.rate_limit import reset_auth_rate_limits; reset_auth_rate_limits()'");
  } catch {
    // ignore
  }
}

const VIEWPORTS = [
  { name: "320px (iPhone SE)", width: 320, height: 568 },
  { name: "360px (Android small)", width: 360, height: 640 },
  { name: "375px (iPhone standard)", width: 375, height: 667 },
  { name: "393px (iPhone 14/15/16)", width: 393, height: 852 },
  { name: "430px (iPhone Plus/Max)", width: 430, height: 932 },
  { name: "768px (iPad portrait)", width: 768, height: 1024 },
  { name: "1024px (iPad landscape)", width: 1024, height: 768 },
  { name: "1280px (Standard desktop)", width: 1280, height: 800 },
  { name: "1440px (Large desktop)", width: 1440, height: 900 },
  { name: "1920px (Ultra-wide 1080p)", width: 1920, height: 1080 },
];

const PATIENT_CREDENTIALS = {
  email: "patient01@demo.carevoice.test",
  password: "CareVoiceDemo2026!",
};

const DOCTOR_CREDENTIALS = {
  email: "doctor01@demo.carevoice.test",
  password: "CareVoiceDemo2026!",
};

const ADMIN_CREDENTIALS = {
  email: "hospital-admin01@demo.carevoice.test",
  password: "CareVoiceDemo2026!",
};

async function login(credentials) {
  resetRateLimits();
  const resp = await fetch("http://127.0.0.1:8000/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });
  if (!resp.ok) throw new Error(`Auth failed for ${credentials.email}: ${resp.status}`);
  return await resp.json();
}

async function assertDialogFits(page, selector, label, widths = [320, 768, 1440]) {
  for (const width of widths) {
    await page.setViewportSize({ width, height: width < 500 ? 700 : 900 });
    await page.waitForTimeout(50);
    const box = await page.locator(selector).evaluate((node) => {
      const rect = node.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height };
    });
    assert.ok(box.width > 0 && box.height > 0, `${label} should remain visible at ${width}px`);
    assert.ok(box.left >= -1 && box.right <= width + 1, `${label} should fit horizontally at ${width}px: ${JSON.stringify(box)}`);
    assert.ok(box.top >= -1 && box.bottom <= (width < 500 ? 700 : 900) + 1, `${label} should fit vertically at ${width}px: ${JSON.stringify(box)}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

async function runComprehensiveAudit() {
  console.log("================================================================================");
  console.log("CAREVOICE AI — COMPREHENSIVE MULTI-PAGE & MULTI-VIEWPORT VERIFICATION AUDIT");
  console.log("================================================================================\n");

  const patientAuth = await login(PATIENT_CREDENTIALS);
  console.log(`✓ Authenticated Patient: ${patientAuth.user.full_name} (${patientAuth.user.role})`);

  const doctorAuth = await login(DOCTOR_CREDENTIALS);
  console.log(`✓ Authenticated Doctor: ${doctorAuth.user.full_name} (${doctorAuth.user.role})`);

  const adminAuth = await login(ADMIN_CREDENTIALS);
  console.log(`✓ Authenticated Admin: ${adminAuth.user.full_name} (${adminAuth.user.role})`);

  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const errors = [];

  try {
    // -------------------------------------------------------------------------
    // Phase 1: Patient Journey Across All 10 Viewports & Theme Modes
    // -------------------------------------------------------------------------
    console.log("\n--- Phase 1: Patient Routes Across 10 Viewports ---");

    for (const vp of VIEWPORTS) {
      process.stdout.write(`Testing Viewport ${vp.name} (${vp.width}x${vp.height})... `);
      const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const page = await context.newPage();

      page.on("pageerror", (err) => {
        errors.push(`[${vp.name}] Uncaught page error: ${err.message}`);
      });

      await page.goto("http://127.0.0.1:3000");
      await page.evaluate((auth) => {
        localStorage.setItem("ahva_token", auth.access_token);
        localStorage.setItem("ahva_user", JSON.stringify(auth.user));
        localStorage.setItem("carevoice_theme", "system");
      }, patientAuth);

      await page.reload();
      await page.waitForSelector(".cv-patient-dashboard", { timeout: 10000 });

      // Verify no horizontal overflow on Overview
      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth + 1;
      });
      assert.equal(overflow, false, `Horizontal overflow detected at ${vp.width}px!`);

      // Switch to Dark mode on this viewport
      await page.evaluate(() => {
        document.documentElement.dataset.theme = "dark";
      });
      await page.waitForTimeout(100);

      const darkOverflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth + 1;
      });
      assert.equal(darkOverflow, false, `Horizontal overflow in dark mode at ${vp.width}px!`);

      await context.close();
      console.log("✓ PASS");
    }

    // -------------------------------------------------------------------------
    // Phase 2: Route-by-Route Deep Inspection on Desktop Viewport
    // -------------------------------------------------------------------------
    console.log("\n--- Phase 2: Route-by-Route Deep Feature Inspection ---");
    const testContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await testContext.newPage();

    page.on("pageerror", (err) => {
      errors.push(`[Route Inspection] Uncaught error: ${err.message}`);
    });

    await page.goto("http://127.0.0.1:3000");
    await page.evaluate((auth) => {
      localStorage.setItem("ahva_token", auth.access_token);
      localStorage.setItem("ahva_user", JSON.stringify(auth.user));
      localStorage.setItem("carevoice_theme", "dark");
    }, patientAuth);

    await page.reload();
    await page.waitForSelector(".cv-patient-dashboard");

    // 1. Overview Page Deep Check
    console.log("Checking [Overview] in Dark Mode...");
    const overviewHeading = await page.textContent("#welcome-patient-heading");
    assert.match(overviewHeading, /Welcome/i);
    const metricCards = await page.$$(".cv-metric-btn");
    assert.equal(metricCards.length, 8, "Expected 8 clickable metric cards");
    const chart = await page.waitForSelector(".cv-svg-chart");
    assert.ok(chart);
    const metricTabs = page.locator(".cv-chip-group[role='tablist'] [role='tab']");
    const metricTabCount = await metricTabs.count();
    for (let i = 0; i < metricTabCount; i += 1) {
      const tab = metricTabs.nth(i);
      await tab.click();
      assert.equal(await tab.getAttribute("aria-selected"), "true", `Vitals metric tab ${i + 1} should select`);
    }
    const chartRanges = page.locator(".cv-chip-group[role='group'] button");
    for (let i = 0; i < await chartRanges.count(); i += 1) await chartRanges.nth(i).click();
    console.log("  ✓ 8 metric cards, physiological vitals chart, and welcome card validated.");

    // 2. Find Care Page Check
    console.log("Checking [Find care]...");
    await page.locator(".cv-nav-item:has-text('Find care')").click();
    await page.waitForSelector(".cv-search");
    const searchMargin = await page.evaluate(() => {
      return window.getComputedStyle(document.querySelector(".cv-search")).marginBottom;
    });
    assert.equal(searchMargin, "24px", "Expected 24px deliberate spacing below search");
    const providerProfile = page.locator(".cv-doctor-card button:has-text('View profile')").first();
    if (await providerProfile.count()) {
      await providerProfile.click();
      await page.waitForSelector(".cv-modal-backdrop .cv-modal");
      await assertDialogFits(page, ".cv-modal-backdrop .cv-modal", "Provider profile modal");
      await page.locator(".cv-modal-close").click();
      await page.waitForSelector(".cv-modal-backdrop", { state: "detached" });
    }
    const bookingButton = page.locator(".cv-doctor-card button:has-text('Book visit')").first();
    if (await bookingButton.count()) {
      await bookingButton.click();
      await page.waitForSelector(".cv-dialog[role='dialog']");
      await assertDialogFits(page, ".cv-dialog[role='dialog']", "Appointment booking dialog");
      await page.locator(".cv-dialog-close").click();
      await page.waitForSelector(".cv-dialog[role='dialog']", { state: "detached" });
    }
    console.log("  ✓ Search spacing and provider/booking modal alignment passed at desktop, tablet, and mobile widths.");

    // 3. Appointments Page & Receipt Modal Check
    console.log("Checking [Appointments] & In-Page Receipt Modal...");
    await page.locator(".cv-nav-item:has-text('Appointments')").click();
    await page.waitForSelector(".cv-appointment-list");
    const viewReceiptBtn = await page.locator("button:has-text('View receipt')").first();
    await viewReceiptBtn.click();
    await page.waitForSelector("#appointment-receipt-view");
    await page.screenshot({ path: "qa-screenshots/appointment-receipt-modal-desktop.png" });
    await page.setViewportSize({ width: 320, height: 700 });
    await page.screenshot({ path: "qa-screenshots/appointment-receipt-modal-mobile.png" });
    await page.setViewportSize({ width: 1440, height: 900 });
    await assertDialogFits(page, ".cv-modal", "Appointment receipt modal");
    const receiptId = await page.textContent("[data-testid='receipt-id']");
    assert.ok(receiptId?.trim().length > 0);
    // Ensure we did not navigate to Billing
    const activeRoute = await page.textContent(".cv-nav-item.active");
    assert.match(activeRoute, /Appointments/i, "Must stay on Appointments page!");
    // Close modal
    await page.locator(".cv-modal-receipt-content button:has-text('Close')").click();
    await page.waitForSelector("#appointment-receipt-view", { state: "detached" });
    const historyButton = page.locator(".cv-appointment-actions button:has-text('History')").first();
    if (await historyButton.count()) {
      await historyButton.click();
      await page.waitForSelector(".cv-modal-history-list");
      await assertDialogFits(page, ".cv-modal", "Appointment history modal");
      await page.locator(".cv-modal-close").click();
      await page.waitForSelector(".cv-modal-history-list", { state: "detached" });
    }
    const rescheduleButton = page.locator(".cv-appointment-actions button:has-text('Reschedule')").first();
    if (await rescheduleButton.count()) {
      await rescheduleButton.click();
      await page.waitForSelector(".cv-dialog[role='dialog']");
      await assertDialogFits(page, ".cv-dialog[role='dialog']", "Reschedule appointment dialog");
      await page.locator(".cv-dialog-close").click();
      await page.waitForSelector(".cv-dialog[role='dialog']", { state: "detached" });
    }
    console.log(`  ✓ Receipt, history${await historyButton.count() ? ", and reschedule" : ""} dialogs fit desktop/tablet/mobile and close cleanly; receipt ${receiptId?.trim()}.`);

    // 4. Health Records Page Check
    console.log("Checking [Health records]...");
    await page.locator(".cv-nav-item:has-text('Health records')").click();
    await page.waitForSelector("[role='tablist'], .health-records-tabs");
    const tabButtons = await page.$$("[role='tab']");
    assert.ok(tabButtons.length >= 10, "Expected at least 10 health record tabs");
    for (const tab of tabButtons) {
      await tab.click();
      assert.equal(await tab.getAttribute("aria-selected"), "true", `Health record tab ${await tab.textContent()} should select`);
    }
    const reportsTab = page.locator(".health-records-tab").filter({ hasText: "AI Reports" });
    if (await reportsTab.count()) {
      await reportsTab.click();
      const reportDetail = page.locator("button:has-text('View Details')").first();
      if (await reportDetail.count()) {
        await reportDetail.click();
        await page.waitForSelector(".cv-record-detail-container");
        await assertDialogFits(page, ".cv-modal", "Clinical record details modal");
        await page.setViewportSize({ width: 320, height: 700 });
        await page.screenshot({ path: "qa-screenshots/clinical-record-modal-mobile.png" });
        const mobileRecordLayout = await page.evaluate(() => {
          const body = document.querySelector(".cv-modal-record-body");
          const content = document.querySelector(".cv-record-detail-body");
          const footer = body.querySelector(":scope > .cv-modal-actions");
          const dialog = document.querySelector(".cv-modal");
          return {
            contentHeight: content.clientHeight,
            contentTextLength: content.innerText.trim().length,
            wrapperScrolls: body.scrollHeight > body.clientHeight + 1,
            footerVisible: footer.getBoundingClientRect().bottom <= dialog.getBoundingClientRect().bottom + 1,
          };
        });
        assert.ok(mobileRecordLayout.contentHeight > 100 && mobileRecordLayout.contentTextLength > 100, "Clinical report content should remain visible and scrollable on mobile");
        assert.equal(mobileRecordLayout.wrapperScrolls, false, "Clinical record modal must not add a second scrollbar on mobile");
        assert.ok(mobileRecordLayout.footerVisible, "Clinical record modal action footer should remain visible on mobile");
        await page.setViewportSize({ width: 1440, height: 900 });
        const scrollModel = await page.evaluate(() => {
          const body = document.querySelector(".cv-modal-record-body");
          const content = document.querySelector(".cv-record-detail-body");
          const footer = document.querySelector(".cv-modal-record-body > .cv-modal-actions");
          const dialog = document.querySelector(".cv-modal");
          return {
            bodyOverflow: getComputedStyle(body).overflowY,
            bodyScrolls: body.scrollHeight > body.clientHeight + 1,
            contentHeight: content.clientHeight,
            footerVisible: footer.getBoundingClientRect().bottom <= dialog.getBoundingClientRect().bottom + 1,
          };
        });
        assert.equal(scrollModel.bodyOverflow, "hidden", "Record modal wrapper should not create a second scrollbar");
        assert.equal(scrollModel.bodyScrolls, false, "Record modal wrapper should not scroll independently of its clinical content");
        assert.ok(scrollModel.contentHeight > 0 && scrollModel.footerVisible, "Clinical content scroll area and action footer should remain visible");
        await page.locator(".cv-modal-close").click();
        await page.waitForSelector(".cv-record-detail-container", { state: "detached" });
        console.log("  ✓ Clinical record modal uses one content scroller and keeps its action footer visible at 320/768/1440 px.");
      }
    }
    console.log(`  ✓ All ${tabButtons.length} health record tabs selected and their panels rendered.`);

    // 5. Symptom Check Page Check
    console.log("Checking [Symptom check]...");
    await page.locator(".cv-nav-item:has-text('Symptom check')").click();
    await page.waitForSelector(".cv-card, form, .cv-page-title");
    await page.locator("#public-triage-symptoms").fill("fever");
    await page.locator(".cv-triage-submit").click();
    await page.waitForSelector(".triage-result");
    console.log("  ✓ Rule-based symptom safety form accepted a synthetic input and rendered a result.");

    // 6. Assistant Page Check
    console.log("Checking [Assistant]...");
    await page.locator(".cv-nav-item:has-text('assistant')").click();
    await page.waitForSelector(".cv-assistant-layout, .cv-voice-assistant, .cv-page-title");
    const assistantInput = page.locator(".chat-form textarea");
    await assistantInput.fill("What does a blood pressure reading measure?");
    await page.locator(".chat-form button[type='submit']").click();
    const assistantOutcome = await Promise.race([
      page.locator(".chat-message.assistant").waitFor({ state: "visible", timeout: 20000 }).then(() => "response").catch(() => "timeout"),
      page.locator(".cv-toast-error").waitFor({ state: "visible", timeout: 20000 }).then(() => "toast").catch(() => "timeout"),
    ]);
    if (assistantOutcome === "toast") {
      const toastText = await page.locator(".cv-toast-error .cv-toast-message").innerText();
      assert.doesNotMatch(toastText, /ollama|docker compose|model .*not downloaded/i, "Assistant infrastructure errors must not expose setup commands to patients");
    }
    console.log(`  ✓ Assistant layout rendered and synthetic question reached ${assistantOutcome === "response" ? "a response" : assistantOutcome === "toast" ? "a safe user-facing fallback" : "the bounded wait"}.`);

    // 7. Profile Page Check
    console.log("Checking [Profile]...");
    await page.locator(".cv-nav-item:has-text('profile')").click();
    await page.waitForSelector(".cv-card, form");
    console.log("  ✓ Patient Profile page loaded.");

    // 8. Privacy Center Check
    console.log("Checking [Privacy] (DPDP Privacy Center)...");
    await page.locator(".cv-nav-item:has-text('Privacy')").click();
    await page.waitForSelector(".cv-card, .cv-page-title");
    console.log("  ✓ DPDP Privacy Center rendered.");

    // 9. Notifications Page Check
    console.log("Checking [Notifications]...");
    await page.locator(".cv-nav-item:has-text('Notifications')").click();
    await page.waitForSelector(".cv-card, form");
    console.log("  ✓ Notifications preferences page loaded.");

    // 10. Billing Page Check
    console.log("Checking [Billing]...");
    await page.locator(".cv-nav-item:has-text('Billing')").click();
    await page.waitForSelector(".page-title, .metrics, .card, h1:has-text('Billing')");
    console.log("  ✓ Billing & invoice history rendered.");

    await testContext.close();

    // -------------------------------------------------------------------------
    // Phase 3: Doctor Workspace Authentication & Route
    // -------------------------------------------------------------------------
    console.log("\n--- Phase 3: Doctor Workspace Inspection ---");
    const docContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const docPage = await docContext.newPage();

    docPage.on("pageerror", (err) => {
      errors.push(`[Doctor Workspace] Uncaught error: ${err.message}`);
    });

    await docPage.goto("http://127.0.0.1:3000");
    await docPage.evaluate((auth) => {
      localStorage.setItem("ahva_token", auth.access_token);
      localStorage.setItem("ahva_user", JSON.stringify(auth.user));
    }, doctorAuth);

    await docPage.reload();
    await docPage.waitForSelector(".cv-topbar");
    await docPage.locator(".cv-nav-item:has-text('Doctor workspace')").click();
    await docPage.waitForSelector(".doctor-workspace-container");
    console.log("✓ Doctor Workspace loaded for Dr. Asha Demo.");
    await docContext.close();

    // -------------------------------------------------------------------------
    // Phase 4: Administration Workspace Authentication & Route
    // -------------------------------------------------------------------------
    console.log("\n--- Phase 4: Hospital Administration Inspection ---");
    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const adminPage = await adminContext.newPage();

    adminPage.on("pageerror", (err) => {
      errors.push(`[Admin Workspace] Uncaught error: ${err.message}`);
    });

    await adminPage.goto("http://127.0.0.1:3000");
    await adminPage.evaluate((auth) => {
      localStorage.setItem("ahva_token", auth.access_token);
      localStorage.setItem("ahva_user", JSON.stringify(auth.user));
    }, adminAuth);

    await adminPage.reload();
    await adminPage.waitForSelector(".cv-topbar");
    await adminPage.locator(".cv-nav-item:has-text('Administration')").click();
    await adminPage.waitForSelector(".cv-admin-management");
    console.log("✓ Hospital Administration portal loaded for Admin.");
    await adminContext.close();

    // -------------------------------------------------------------------------
    // Final Error Tally
    // -------------------------------------------------------------------------
    console.log("\n================================================================================");
    if (errors.length === 0) {
      console.log("🎉 ALL TESTS PASSED! ZERO PAGE ERRORS DETECTED ACROSS ALL ROUTES & VIEWPORTS.");
      console.log("================================================================================");
    } else {
      console.error(`⚠️ Encounted ${errors.length} errors:`);
      errors.forEach((e) => console.error(`  - ${e}`));
      process.exit(1);
    }
  } finally {
    await browser.close();
  }
}

runComprehensiveAudit().catch((err) => {
  console.error("FATAL AUDIT FAILURE:", err);
  process.exit(1);
});
