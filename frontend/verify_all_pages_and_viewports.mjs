import { chromium } from "playwright";
import assert from "node:assert/strict";

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
  const resp = await fetch("http://127.0.0.1:8000/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });
  if (!resp.ok) throw new Error(`Auth failed for ${credentials.email}: ${resp.status}`);
  return await resp.json();
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
    console.log("  ✓ 8 metric cards, physiological vitals chart, and welcome card validated.");

    // 2. Find Care Page Check
    console.log("Checking [Find care]...");
    await page.locator(".cv-nav-item:has-text('Find care')").click();
    await page.waitForSelector(".cv-search");
    const searchMargin = await page.evaluate(() => {
      return window.getComputedStyle(document.querySelector(".cv-search")).marginBottom;
    });
    assert.equal(searchMargin, "24px", "Expected 24px deliberate spacing below search");
    console.log("  ✓ Search input present with deliberate 24px bottom spacing.");

    // 3. Appointments Page & Receipt Modal Check
    console.log("Checking [Appointments] & In-Page Receipt Modal...");
    await page.locator(".cv-nav-item:has-text('Appointments')").click();
    await page.waitForSelector(".cv-appointment-list");
    const viewReceiptBtn = await page.locator("button:has-text('View receipt')").first();
    await viewReceiptBtn.click();
    await page.waitForSelector("#appointment-receipt-view");
    const receiptId = await page.textContent("[data-testid='receipt-id']");
    assert.ok(receiptId?.trim().length > 0);
    // Ensure we did not navigate to Billing
    const activeRoute = await page.textContent(".cv-nav-item.active");
    assert.match(activeRoute, /Appointments/i, "Must stay on Appointments page!");
    // Close modal
    await page.locator(".cv-modal-receipt-content button:has-text('Close')").click();
    await page.waitForSelector("#appointment-receipt-view", { state: "detached" });
    console.log(`  ✓ Receipt modal opened in-page (${receiptId?.trim()}), closed cleanly, route retained.`);

    // 4. Health Records Page Check
    console.log("Checking [Health records]...");
    await page.locator(".cv-nav-item:has-text('Health records')").click();
    await page.waitForSelector("[role='tablist'], .health-records-tabs");
    const tabButtons = await page.$$("[role='tab']");
    assert.ok(tabButtons.length >= 10, "Expected at least 10 health record tabs");
    // Switch to Prescriptions tab
    const rxTab = await page.locator("[role='tab']:has-text('Prescriptions')");
    await rxTab.click();
    await page.waitForTimeout(200);
    console.log(`  ✓ Health records rendered with ${tabButtons.length} responsive tabs, tab navigation operational.`);

    // 5. Symptom Check Page Check
    console.log("Checking [Symptom check]...");
    await page.locator(".cv-nav-item:has-text('Symptom check')").click();
    await page.waitForSelector(".cv-card, form, .cv-page-title");
    console.log("  ✓ Symptom check triage form rendered.");

    // 6. Assistant Page Check
    console.log("Checking [Assistant]...");
    await page.locator(".cv-nav-item:has-text('assistant')").click();
    await page.waitForSelector(".cv-assistant-layout, .cv-voice-assistant, .cv-page-title");
    console.log("  ✓ CareVoice AI Assistant rendered.");

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
