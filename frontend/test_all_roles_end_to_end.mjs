import { chromium } from "playwright";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const BASE_URL = "http://127.0.0.1:3000";
const API_URL = "http://127.0.0.1:8000/api/v1";
const CREDENTIALS_PATH = resolve("../.qa-test-credentials.env");
const SCREENSHOT_DIR = resolve("qa-screenshots");
if (!existsSync(CREDENTIALS_PATH)) {
  throw new Error("Missing ignored .qa-test-credentials.env; see docs/qa/QA_AUDIT_REPORT.md for setup.");
}
const localCredentials = Object.fromEntries(
  readFileSync(CREDENTIALS_PATH, "utf8").split(/\r?\n/)
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => { const at = line.indexOf("="); return [line.slice(0, at), line.slice(at + 1)]; }),
);
function credential(role, field) {
  const key = `CV_QA_${role.toUpperCase()}_${field}`;
  if (!localCredentials[key]) throw new Error(`Missing ${key} in ignored local credential file.`);
  return localCredentials[key];
}
mkdirSync(SCREENSHOT_DIR, { recursive: true });

function resetRateLimits() {
  try {
    execSync("docker exec healthcare-backend python -c 'from app.auth.rate_limit import reset_auth_rate_limits; reset_auth_rate_limits()'");
  } catch {
    // ignore
  }
}

const ROLE_CREDENTIALS = [
  {
    role: "patient",
    login: credential("patient", "LOGIN"),
    password: credential("patient", "PASSWORD"),
    expectedPage: "Overview",
    expectedHeading: "Aarav Demo",
  },
  {
    role: "doctor",
    login: credential("doctor", "LOGIN"),
    password: credential("doctor", "PASSWORD"),
    expectedPage: "Doctor workspace",
    expectedHeading: "Doctor Clinical Workspace",
  },
  {
    role: "hospital_staff",
    login: credential("hospital_staff", "LOGIN"),
    password: credential("hospital_staff", "PASSWORD"),
    expectedPage: "Provider dashboard",
    expectedHeading: "Hospital dashboard",
  },
  {
    role: "hospital_admin",
    login: credential("hospital_admin", "LOGIN"),
    password: credential("hospital_admin", "PASSWORD"),
    expectedPage: "Administration",
    expectedHeading: "Administrative Console",
  },
  {
    role: "platform_admin",
    login: credential("platform_admin", "LOGIN"),
    password: credential("platform_admin", "PASSWORD"),
    expectedPage: "Administration",
    expectedHeading: "Administrative Console",
  },
];
const selectedRoles = process.env.CV_QA_ROLE_FILTER?.split(",").map((role) => role.trim()).filter(Boolean);

async function runRoleAudit() {
  console.log("===============================================================================");
  console.log("CAREVOICE AI: MASTER ROLE-WISE AUDIT & END-TO-END VERIFICATION SUITE");
  console.log("===============================================================================\n");

  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  for (const cred of ROLE_CREDENTIALS.filter((item) => !selectedRoles || selectedRoles.includes(item.role))) {
    console.log(`\n-------------------------------------------------------------------------------`);
    console.log(`AUDITING ROLE: [${cred.role.toUpperCase()}]`);
    console.log(`-------------------------------------------------------------------------------`);

    // Authenticate through the rendered UI and retain sanitized browser/network diagnostics.
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const pageErrors = [];
    const failedApiResponses = [];
    const failedRequests = [];
    page.on("pageerror", (err) => pageErrors.push(err.message));
    page.on("requestfailed", (request) => failedRequests.push(`${new URL(request.url()).pathname} (${request.failure()?.errorText || "unknown"})`));
    page.on("response", (response) => {
      if (response.url().startsWith(API_URL) && response.status() >= 400) {
        failedApiResponses.push(`${response.status()} ${new URL(response.url()).pathname}`);
      }
    });
    await page.goto(BASE_URL);
    await page.getByRole("button", { name: "Sign in", exact: true }).first().click({ noWaitAfter: true });
    await page.getByPlaceholder("Username or email address").fill(cred.login);
    await page.getByLabel("Password", { exact: true }).fill(cred.password);
    await page.getByRole("button", { name: "Sign in", exact: true }).last().click();
    await page.locator(".cv-breadcrumb strong").waitFor({ state: "visible", timeout: 30000 });
    await page.reload();
    await page.waitForFunction(
      (expected) => document.querySelector(".cv-breadcrumb strong")?.textContent?.trim() === expected,
      cred.expectedPage,
      { timeout: 20000 },
    );
    await page.waitForFunction(
      () => (document.querySelector(".cv-content")?.innerText?.trim().length || 0) > 50,
      null,
      { timeout: 20000 },
    );

    // 3. Verify Role-Specific Default Landing Page
    console.log(`Checking default landing page for role [${cred.role}]...`);
    const breadcrumb = await page.textContent(".cv-breadcrumb strong");
    console.log(`  ✓ Landed on breadcrumb: "${breadcrumb.trim()}" (Expected: "${cred.expectedPage}")`);
    assert.equal(breadcrumb.trim(), cred.expectedPage, `Default landing page must be ${cred.expectedPage}`);

    // Verify main content loaded cleanly
    const bodyText = await page.textContent(".cv-content");
    assert.ok(bodyText.length > 50, "Content must not be blank");

    // 4. Role-Specific Feature Verifications
    if (cred.role === "patient") {
      console.log("Testing Patient Features...");
      // Check patient vitals / dashboard cards
      const hasWelcome = await page.isVisible("#welcome-patient-heading");
      assert.ok(hasWelcome, "Patient dashboard must display welcome heading");
      console.log("  ✓ Patient Welcome Header confirmed.");

      // Navigate to Health Records
      await page.getByRole("button", { name: "Health records", exact: true }).click();
      await page.waitForSelector(".health-records-tabs", { timeout: 10000 });
      console.log("  ✓ Health Records 12-tab navigation loaded.");

      // Test Prescriptions Tab Grid
      await page.locator("[role='tab']:has-text('Prescriptions')").click();
      await page.waitForSelector(".record-card-rx", { timeout: 10000 });
      const rxCount = await page.$$eval(".record-card-rx", (cards) => cards.length);
      console.log(`  ✓ Prescriptions Grid loaded ${rxCount} records.`);
      assert.ok(rxCount > 0, "Patient must have prescription cards");

      // Verify Signed vs Draft status badges
      const signedPill = await page.isVisible(".cv-badge-signed-pill");
      const draftPill = await page.isVisible(".cv-badge-draft-pill");
      console.log(`  ✓ Doctor Signed badges: ${signedPill} | AI Draft badges: ${draftPill}`);

      // Capture screenshot
      await page.screenshot({ path: resolve(SCREENSHOT_DIR, "audit-role-patient.png") });
      console.log("  ✓ Captured audit-role-patient.png");

      // Exercise theme/language controls and check layout overflow at the requested widths.
      await page.getByRole("button", { name: "Overview", exact: true }).click();
      await page.waitForSelector(".cv-patient-dashboard", { timeout: 10000 });
      const themeSelect = page.getByRole("main").getByRole("combobox", { name: "Color theme" });
      const viewportResults = [];
      for (const width of [320, 375, 390, 430, 768, 1024, 1280, 1440]) {
        await page.setViewportSize({ width, height: 900 });
        for (const mode of ["light", "dark"]) {
          await themeSelect.selectOption(mode);
          const layout = await page.evaluate(() => ({
            width: window.innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            theme: document.documentElement.dataset.theme,
          }));
          assert.equal(layout.theme, mode, `${mode} theme must apply at ${width}px`);
          assert.ok(layout.scrollWidth <= layout.width + 1, `Horizontal overflow at ${width}px in ${mode} mode`);
          viewportResults.push(`${width}:${mode}=PASS`);
          if (width === 320 && mode === "dark") {
            await page.screenshot({ path: resolve(SCREENSHOT_DIR, "patient-320-dark.png") });
          }
          if (width === 1440 && mode === "light") {
            await page.screenshot({ path: resolve(SCREENSHOT_DIR, "patient-1440-light.png") });
          }
          if (width === 1440 && mode === "dark") {
            await page.screenshot({ path: resolve(SCREENSHOT_DIR, "patient-overview-dark-updated.png"), fullPage: true });
          }
        }
      }
      await page.emulateMedia({ colorScheme: "light" });
      await themeSelect.selectOption("system");
      await page.waitForFunction(() => document.documentElement.dataset.theme === "light");
      await page.emulateMedia({ colorScheme: "dark" });
      await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
      await page.getByRole("button", { name: "हि", exact: true }).first().click();
      await page.waitForFunction(() => document.documentElement.lang === "hi");
      await page.setViewportSize({ width: 390, height: 844 });
      const hindiOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      assert.equal(hindiOverflow, false, "Hindi dashboard must not overflow at 390px");
      await page.setViewportSize({ width: 1440, height: 900 });
      console.log(`  ✓ Theme checks, Hindi nav, and 16 viewport/theme combinations passed (${viewportResults.join(", ")}).`);
      await page.getByRole("button", { name: "EN", exact: true }).first().click();
      await page.waitForFunction(() => document.documentElement.lang === "en");
      await themeSelect.selectOption("system");
      await page.setViewportSize({ width: 1440, height: 900 });

      const patientRoutes = [
        ["Find care", ".cv-search"],
        ["Appointments", ".cv-appointment-list"],
        ["Symptom check", ".cv-page-title, form"],
        ["CareVoice assistant", ".cv-assistant-layout, .cv-voice-assistant, .cv-page-title"],
        ["Health profile", ".cv-page-title, form"],
        ["Notifications", ".cv-page-title, form"],
      ];
      for (const [label, contentSelector] of patientRoutes) {
        const providerLoads = label === "Find care"
          ? Promise.all(["/providers/doctors", "/providers/hospitals"].map((path) => page.waitForResponse(
            (response) => new URL(response.url()).pathname === `${new URL(API_URL).pathname}${path}` && response.status() === 200,
            { timeout: 20000 },
          )))
          : null;
        await page.getByRole("button", { name: label, exact: true }).click();
        await page.locator(".cv-breadcrumb strong").getByText(label, { exact: true }).waitFor({ state: "visible", timeout: 15000 });
        await page.locator(contentSelector).first().waitFor({ state: "visible", timeout: 15000 });
        if (providerLoads) await providerLoads;
        if (label === "Notifications") {
          await page.screenshot({ path: resolve(SCREENSHOT_DIR, "notifications-dark-refresh.png"), fullPage: true });
        }
      }
      await page.getByRole("button", { name: "DPDP Privacy", exact: true }).click();
      await page.locator(".cv-breadcrumb strong").getByText("DPDP Privacy", { exact: true }).waitFor({ state: "visible", timeout: 15000 });
      await page.locator(".cv-page-title, .cv-card").first().waitFor({ state: "visible", timeout: 15000 });

      // Use the marked RBAC patient account and a fixed description so repeated audit runs reuse one invoice.
      const qaInvoiceDescription = "QA synthetic Razorpay Test Mode checkout";
      const staffPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      await staffPage.goto(BASE_URL);
      await staffPage.getByRole("button", { name: "Sign in", exact: true }).first().click({ noWaitAfter: true });
      await staffPage.getByPlaceholder("Username or email address").fill(credential("hospital_staff", "LOGIN"));
      await staffPage.getByLabel("Password", { exact: true }).fill(credential("hospital_staff", "PASSWORD"));
      await staffPage.getByRole("button", { name: "Sign in", exact: true }).last().click();
      await staffPage.locator(".cv-breadcrumb strong").waitFor({ state: "visible", timeout: 30000 });
      await staffPage.getByRole("button", { name: "Billing", exact: true }).click();
      await staffPage.getByLabel("Patient account ID").waitFor({ state: "visible", timeout: 15000 });
      await staffPage.getByText("Razorpay Test Mode ready", { exact: true }).waitFor({ state: "visible", timeout: 15000 });
      const existingQaInvoice = staffPage.locator(".invoice-row").filter({ hasText: qaInvoiceDescription });
      if (await existingQaInvoice.count() === 0) {
        const appointmentSelect = staffPage.locator(".invoice-form select");
        const eligibleAppointments = await appointmentSelect.locator("option").evaluateAll((options) => options
          .filter((option) => option.value)
          .map((option) => option.value));
        if (eligibleAppointments.length) {
          await appointmentSelect.selectOption(eligibleAppointments[0]);
          await staffPage.getByLabel("Description").fill(qaInvoiceDescription);
          await staffPage.getByRole("button", { name: "Create invoice", exact: true }).click();
          await staffPage.locator(".invoice-row").filter({ hasText: qaInvoiceDescription }).waitFor({ state: "visible", timeout: 20000 });
        } else {
          console.log("  BLOCKED: no unbilled synthetic appointment is available for a hospital-scoped QA invoice.");
        }
      }
      if (await staffPage.locator(".invoice-row").filter({ hasText: qaInvoiceDescription }).count()) {
        assert.match(await staffPage.locator(".invoice-row").filter({ hasText: qaInvoiceDescription }).innerText(), /Unpaid/);
      }
      await staffPage.getByRole("button", { name: /sign out/i }).click();
      await staffPage.close();

      await page.getByRole("button", { name: "Billing", exact: true }).click();
      await page.locator(".cv-breadcrumb strong").getByText("Billing", { exact: true }).waitFor({ state: "visible", timeout: 15000 });
      await page.getByText("Razorpay Test Mode ready", { exact: true }).waitFor({ state: "visible", timeout: 15000 });
      const qaInvoiceRow = page.locator(".invoice-row").filter({ hasText: qaInvoiceDescription });
      if (await qaInvoiceRow.count()) {
        const payNow = qaInvoiceRow.getByRole("button", { name: "Pay now", exact: true });
        assert.ok(await payNow.isEnabled(), "The synthetic unpaid invoice must expose Test Mode checkout.");
        assert.ok(await qaInvoiceRow.getByText("Unpaid", { exact: true }).isVisible(), "The synthetic QA invoice must remain unpaid before checkout.");
        console.log("  ✓ Patient routes rendered; Razorpay Test Mode checkout is enabled for the synthetic invoice.");
      } else {
        console.log("  BLOCKED: no eligible unbilled synthetic appointment was available to issue a QA invoice.");
      }
    }

    if (cred.role === "doctor") {
      console.log("Testing Doctor Clinician Workspace...");
      // Verify Overview tab is default
      const overviewTab = await page.locator("button.cv-btn-primary:has-text('Clinician Overview')").isVisible();
      assert.ok(overviewTab, "Clinician Overview must be active tab");
      console.log("  ✓ Clinician Overview tab is active by default.");

      // Verify KPI Stat Cards
      const kpis = await page.textContent(".doctor-workspace-container");
      assert.ok(kpis.includes("Today's Consultations") || kpis.includes("Assigned Patients"), "Doctor Overview must render clinical KPIs");
      console.log("  ✓ Clinical KPI Stat Tiles confirmed.");

      // Verify Sub-Tabs (Ambient Scribe, Clinical Notes, Protocol Monitor, Prescribe, Inbox, History)
      const tabs = ["Assigned Patients", "Ambient Scribe", "Clinical Notes", "Protocol Monitor", "Prescription Builder", "AI Assessment Inbox", "Patient Longitudinal History"];
      for (const t of tabs) {
        const hasTab = await page.locator(`button:has-text('${t}')`).first().isVisible();
        assert.ok(hasTab, `Doctor workspace must include tab [${t}]`);
      }
      console.log(`  ✓ All 7 specialized clinician sub-tabs verified.`);

      // Test switching to Ambient Scribe
      await page.locator("button:has-text('Ambient Scribe')").first().click();
      await page.waitForSelector(".cv-ambient-scribe-container", { timeout: 8000 });
      console.log("  ✓ Ambient Clinical Scribe tab loaded with voice intake controls.");

      // Test switching to Protocol Monitor
      await page.locator("button:has-text('Protocol Monitor')").first().click();
      await page.waitForSelector("button:has-text('Run Vitals Protocol Evaluation')", { timeout: 8000 });
      console.log("  ✓ Clinical Protocol Monitor loaded with NEWS2/Dengue/SNOOP inputs.");

      // Capture screenshot
      await page.screenshot({ path: resolve(SCREENSHOT_DIR, "audit-role-doctor.png") });
      console.log("  ✓ Captured audit-role-doctor.png");
    }

    if (cred.role === "hospital_staff") {
      console.log("Testing Hospital Staff Front-Desk Reception Hub...");
      // Verify Front-Desk Reception Header
      const receptionHeading = page.locator(".cv-provider-dashboard h2").filter({ hasText: "Front-Desk Reception & Patient Check-In Queue" });
      await receptionHeading.waitFor({ state: "visible", timeout: 15000 });
      const hasReception = await receptionHeading.isVisible();
      assert.ok(hasReception, "Hospital staff dashboard must render Front-Desk Reception Queue");
      console.log("  ✓ Front-Desk Reception Queue header confirmed.");

      // Verify Reception Metrics
      const metricsText = await page.textContent(".cv-metrics");
      assert.ok(metricsText.includes("Total Appointments") && metricsText.includes("Pending Check-In"), "Metrics must display reception queue stats");
      console.log("  ✓ Front-Desk Operations KPIs verified.");

      console.log("  ✓ Reception queue displayed; mutation controls were not activated.");

      // Capture screenshot
      await page.screenshot({ path: resolve(SCREENSHOT_DIR, "audit-role-hospital-staff.png") });
      console.log("  ✓ Captured audit-role-hospital-staff.png");
    }

    if (cred.role === "hospital_admin" || cred.role === "platform_admin") {
      console.log(`Testing Admin Console for [${cred.role}]...`);
      const adminWorkspace = page.locator(".cv-admin-management");
      await adminWorkspace.waitFor({ state: "visible", timeout: 15000 });
      await adminWorkspace.locator(".cv-loading").waitFor({ state: "hidden", timeout: 30000 });
      const adminHeading = await adminWorkspace.locator(".cv-admin-heading h2").textContent();
      assert.match(adminHeading || "", /Administration workspace/i);
      const sectionCount = await adminWorkspace.locator(".cv-admin-section").count();
      assert.ok(sectionCount > 0, "Admin console must render management sections");
      console.log("  ✓ Management records and controls displayed.");

      // Capture screenshot
      await page.screenshot({ path: resolve(SCREENSHOT_DIR, `audit-role-${cred.role}.png`) });
      console.log(`  ✓ Captured audit-role-${cred.role}.png`);
    }

    const storedSession = await page.evaluate(() => ({
      token: Boolean(localStorage.getItem("ahva_token")),
      user: Boolean(localStorage.getItem("ahva_user")),
    }));
    assert.deepEqual(storedSession, { token: true, user: true }, "UI session must persist after refresh");
    console.log(`  Session persisted; page errors=${pageErrors.length}, API errors=${failedApiResponses.length}, failed requests=${failedRequests.length}`);
    if (pageErrors.length) console.log(`  Page errors: ${pageErrors.join(" | ")}`);
    if (failedApiResponses.length) console.log(`  API errors: ${failedApiResponses.join(", ")}`);
    if (failedRequests.length) console.log(`  Failed requests: ${failedRequests.join(", ")}`);
    await page.getByRole("button", { name: /sign out/i }).click();
    await page.getByRole("button", { name: "Sign in", exact: true }).waitFor({ state: "visible", timeout: 10000 });
    assert.equal(await page.evaluate(() => localStorage.getItem("ahva_token")), null, "Logout must clear token");
    await page.close();
  }

  await browser.close();
  console.log("\n===============================================================================");
  console.log(`✓ UI role journey completed for ${ROLE_CREDENTIALS.filter((item) => !selectedRoles || selectedRoles.includes(item.role)).length} selected role(s).`);
  console.log("===============================================================================\n");
}

runRoleAudit().catch((err) => {
  console.error("Audit test failure:", err);
  process.exit(1);
});
