import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const OUTPUT_DIR = "/tmp/dark_mode_audit";
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

async function auditPages() {
  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();

    // Authenticate
    const loginResp = await fetch("http://127.0.0.1:8000/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "patient01@demo.carevoice.test",
        password: "CareVoiceDemo2026!",
      }),
    });
    const authData = await loginResp.json();

    await page.goto("http://127.0.0.1:3000");
    await page.evaluate((auth) => {
      localStorage.setItem("ahva_token", auth.access_token);
      localStorage.setItem("ahva_user", JSON.stringify(auth.user));
      localStorage.setItem("carevoice_theme", "dark");
    }, authData);

    await page.reload();
    await page.waitForSelector(".cv-patient-dashboard");
    await page.waitForTimeout(500);

    // 1. Overview in Dark Mode
    await page.screenshot({ path: path.join(OUTPUT_DIR, "overview_dark.png"), fullPage: true });
    console.log("✓ Saved overview_dark.png");

    // 2. Find Care in Dark Mode
    const findCareNav = await page.locator(".cv-nav-item:has-text('Find care')");
    await findCareNav.click();
    await page.waitForSelector(".cv-search");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUTPUT_DIR, "find_care_dark.png"), fullPage: true });
    console.log("✓ Saved find_care_dark.png");

    // 3. Appointments in Dark Mode
    const apptsNav = await page.locator(".cv-nav-item:has-text('Appointments')");
    await apptsNav.click();
    await page.waitForSelector(".cv-appointment-list");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUTPUT_DIR, "appointments_dark.png"), fullPage: true });
    console.log("✓ Saved appointments_dark.png");

    // 4. Health Records in Dark Mode
    const recordsNav = await page.locator(".cv-nav-item:has-text('Health records')");
    await recordsNav.click();
    await page.waitForSelector(".cv-page-title");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUTPUT_DIR, "health_records_dark.png"), fullPage: true });
    console.log("✓ Saved health_records_dark.png");

    // 5. Billing in Dark Mode
    const billingNav = await page.locator(".cv-nav-item:has-text('Billing')");
    await billingNav.click();
    await page.waitForSelector(".cv-page-title");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUTPUT_DIR, "billing_dark.png"), fullPage: true });
    console.log("✓ Saved billing_dark.png");

    await context.close();
  } finally {
    await browser.close();
  }
}

auditPages().catch((err) => {
  console.error("Audit error:", err);
  process.exit(1);
});
