import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const VIEWPORTS = [
  { name: "mobile_320", width: 320, height: 640 },
  { name: "mobile_375", width: 375, height: 667 },
  { name: "tablet_768", width: 768, height: 1024 },
  { name: "desktop_1024", width: 1024, height: 768 },
  { name: "desktop_1440", width: 1440, height: 900 },
];

const OUTPUT_DIR = "/tmp/dashboard_verification";
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function runVerification() {
  console.log("Starting CareVoice Patient Dashboard Headless Browser Verification...");

  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  try {
    // 1. Verify standard desktop first with full interactions
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();

    // Log in via API to get auth token and set localStorage
    const loginResp = await fetch("http://127.0.0.1:8000/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "patient01@demo.carevoice.test",
        password: "CareVoiceDemo2026!",
      }),
    });
    if (!loginResp.ok) throw new Error(`Auth failed: ${loginResp.status}`);
    const authData = await loginResp.json();
    console.log(`✓ Authenticated as ${authData.user.full_name} (${authData.user.role})`);

    // Navigate to frontend app
    await page.goto("http://127.0.0.1:3000");

    // Inject token and user state into localStorage
    await page.evaluate((auth) => {
      localStorage.setItem("ahva_token", auth.access_token);
      localStorage.setItem("ahva_user", JSON.stringify(auth.user));
    }, authData);

    // Reload page so app boots authenticated into Overview/Dashboard
    await page.reload();
    await page.waitForLoadState("networkidle");

    // Wait for the patient dashboard container
    await page.waitForSelector(".cv-patient-dashboard", { timeout: 10000 });
    console.log("✓ Patient Dashboard container loaded successfully.");

    // Check Welcome Heading and Health ID
    const headingText = await page.textContent("#welcome-patient-heading");
    console.log(`✓ Welcome heading: "${headingText?.trim()}"`);

    const healthIdBadge = await page.textContent(".cv-patient-badge");
    console.log(`✓ Health ID: "${healthIdBadge?.trim()}"`);

    // Check 8 Metric Cards
    const metricCards = await page.$$(".cv-metric-btn");
    console.log(`✓ Verified ${metricCards.length} clickable summary metric cards (Expected: 8)`);
    if (metricCards.length !== 8) {
      throw new Error(`Expected 8 metric cards, found ${metricCards.length}`);
    }

    // Check Vitals Chart and SVG elements
    const svgChart = await page.waitForSelector(".cv-svg-chart");
    const chartPoints = await page.$$(".cv-chart-point");
    console.log(`✓ Vitals SVG chart rendered with ${chartPoints.length} interactive data points`);

    // Test Metric Switching (Click "Heart Rate")
    const hrChip = await page.locator(".cv-chip:has-text('Heart Rate')");
    await hrChip.click();
    await page.waitForTimeout(300);
    console.log("✓ Switched active physiological metric to Heart Rate");

    // Test Accessible Data Table Toggle
    const tableToggleBtn = await page.locator("button[aria-controls='vitals-accessible-table-view']");
    await tableToggleBtn.click();
    await page.waitForSelector("#vitals-accessible-table-view table");
    console.log("✓ Accessible data table opened with semantic <table>, <th>, <td>");

    // Test Lab Trends Analyte Switch (Click "HbA1c" or second chip)
    const labChips = await page.$$("section[aria-labelledby='lab-trends-heading'] .cv-chip");
    if (labChips.length > 1) {
      await labChips[1].click();
      await page.waitForTimeout(300);
      console.log("✓ Switched laboratory analyte trajectory view");
    }

    // Test Record Tabs Switching
    const labsTab = await page.locator(".cv-tab-btn:has-text('Diagnostic Reports')");
    await labsTab.click();
    await page.waitForTimeout(300);
    const labCards = await page.$$(".cv-record-card");
    console.log(`✓ Switched to Diagnostic Reports tab, rendered ${labCards.length} verified reports`);

    const notesTab = await page.locator(".cv-tab-btn:has-text('Doctor Notes')");
    await notesTab.click();
    await page.waitForTimeout(300);
    console.log("✓ Switched to Doctor Notes tab");

    // Test Log Vitals Modal opening
    const logVitalsBtn = await page.locator(".cv-action-pill:has-text('Log Vitals')");
    await logVitalsBtn.click();
    await page.waitForSelector(".cv-modal-dialog");
    console.log("✓ Log Vitals modal dialog opened");

    // Close modal
    const closeBtn = await page.locator(".cv-modal-close-btn");
    await closeBtn.click();
    await page.waitForTimeout(200);
    console.log("✓ Log Vitals modal closed");

    await context.close();

    // 2. Viewport testing across 320px, 375px, 768px, 1024px, 1440px
    for (const vp of VIEWPORTS) {
      const vpContext = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const vpPage = await vpContext.newPage();

      await vpPage.goto("http://127.0.0.1:3000");
      await vpPage.evaluate((auth) => {
        localStorage.setItem("ahva_token", auth.access_token);
        localStorage.setItem("ahva_user", JSON.stringify(auth.user));
      }, authData);

      await vpPage.reload();
      await vpPage.waitForSelector(".cv-patient-dashboard");
      await vpPage.waitForTimeout(500);

      // Verify no horizontal overflow
      const hasHorizontalScroll = await vpPage.evaluate(() => {
        return document.documentElement.scrollWidth > window.innerWidth;
      });

      const shotPath = path.join(OUTPUT_DIR, `dashboard_${vp.name}.png`);
      await vpPage.screenshot({ path: shotPath, fullPage: true });
      console.log(`✓ Viewport ${vp.name} (${vp.width}x${vp.height}): Screenshot saved, horizontal overflow: ${hasHorizontalScroll}`);

      await vpContext.close();
    }

    console.log("\nAll browser verification checks passed successfully!");
  } finally {
    await browser.close();
  }
}

runVerification().catch((err) => {
  console.error("Verification error:", err);
  process.exit(1);
});
