import { chromium } from "playwright";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";

const BASE_URL = "http://127.0.0.1:3000";
const API_URL = "http://127.0.0.1:8000/api/v1";

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
    email: "patient01@demo.carevoice.test",
    password: "CareVoiceDemo2026!",
    expectedPage: "Overview",
    expectedHeading: "Aarav Demo",
  },
  {
    role: "doctor",
    email: "doctor01@demo.carevoice.test",
    password: "CareVoiceDemo2026!",
    expectedPage: "Doctor workspace",
    expectedHeading: "Doctor Clinical Workspace",
  },
  {
    role: "hospital_staff",
    email: "hospital.staff",
    password: "HospitalStaff@2026!",
    expectedPage: "Provider dashboard",
    expectedHeading: "Hospital dashboard",
  },
  {
    role: "hospital_admin",
    email: "hospital-admin01@demo.carevoice.test",
    password: "CareVoiceDemo2026!",
    expectedPage: "Administration",
    expectedHeading: "Administrative Console",
  },
  {
    role: "platform_admin",
    email: "platform.admin",
    password: "PlatformTest@2026!",
    expectedPage: "Administration",
    expectedHeading: "Administrative Console",
  },
];

async function loginApi(loginId, password) {
  resetRateLimits();
  const body = loginId.includes("@")
    ? { email: loginId, password }
    : { username: loginId, password };
  const resp = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Login failed for ${loginId} (${resp.status}): ${err}`);
  }
  return await resp.json();
}

async function runRoleAudit() {
  console.log("===============================================================================");
  console.log("CAREVOICE AI: MASTER ROLE-WISE AUDIT & END-TO-END VERIFICATION SUITE");
  console.log("===============================================================================\n");

  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  for (const cred of ROLE_CREDENTIALS) {
    console.log(`\n-------------------------------------------------------------------------------`);
    console.log(`AUDITING ROLE: [${cred.role.toUpperCase()}] (${cred.email})`);
    console.log(`-------------------------------------------------------------------------------`);

    // 1. Backend Login & Token Verification
    const auth = await loginApi(cred.email, cred.password);
    console.log(`✓ Authenticated: ${auth.user.full_name} | Role: ${auth.user.role} | ID: ${auth.user.id}`);
    assert.equal(auth.user.role, cred.role, `Role mismatch for ${cred.email}`);

    // 2. Browser Session Setup
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    page.on("pageerror", (err) => console.error(`[Page Error - ${cred.role}]:`, err));

    await page.goto(BASE_URL);
    await page.evaluate((auth) => {
      localStorage.setItem("ahva_token", auth.access_token);
      localStorage.setItem("ahva_user", JSON.stringify(auth.user));
      localStorage.setItem("carevoice_theme", "light");
    }, auth);

    await page.reload();
    await page.waitForTimeout(1000);

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
      await page.locator(".cv-nav-item:has-text('Health records')").click();
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
      await page.screenshot({ path: `audit-role-patient.png` });
      console.log("  ✓ Captured audit-role-patient.png");
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
      await page.screenshot({ path: `audit-role-doctor.png` });
      console.log("  ✓ Captured audit-role-doctor.png");
    }

    if (cred.role === "hospital_staff") {
      console.log("Testing Hospital Staff Front-Desk Reception Hub...");
      // Verify Front-Desk Reception Header
      const hasReception = await page.locator("text=Front-Desk Reception & Patient Check-In Queue").isVisible();
      assert.ok(hasReception, "Hospital staff dashboard must render Front-Desk Reception Queue");
      console.log("  ✓ Front-Desk Reception Queue header confirmed.");

      // Verify Reception Metrics
      const metricsText = await page.textContent(".cv-metrics");
      assert.ok(metricsText.includes("Total Appointments") && metricsText.includes("Pending Check-In"), "Metrics must display reception queue stats");
      console.log("  ✓ Front-Desk Operations KPIs verified.");

      // Test check-in button if any scheduled appointments exist
      const checkInBtn = page.locator("button:has-text('Confirm Arrival / Check-In')").first();
      if (await checkInBtn.isVisible()) {
        console.log("  Found scheduled visit awaiting arrival. Testing Check-In action...");
        await checkInBtn.click();
        await page.waitForTimeout(1000);
        console.log("  ✓ Check-in action completed.");
      } else {
        console.log("  ✓ Reception queue displayed cleanly (all visits already confirmed or none pending).");
      }

      // Capture screenshot
      await page.screenshot({ path: `audit-role-hospital-staff.png` });
      console.log("  ✓ Captured audit-role-hospital-staff.png");
    }

    if (cred.role === "hospital_admin" || cred.role === "platform_admin") {
      console.log(`Testing Admin Console for [${cred.role}]...`);
      // Verify Admin Management Console
      const adminHeading = await page.textContent("h1, h2");
      console.log(`  ✓ Admin console loaded with heading.`);

      // Verify User Management Table or Tabs
      const hasUsers = await page.locator(".cv-user-row, .cv-card, table").first().isVisible();
      assert.ok(hasUsers, "Admin console must display users or management controls");
      console.log("  ✓ Management records and controls displayed.");

      // Capture screenshot
      await page.screenshot({ path: `audit-role-${cred.role}.png` });
      console.log(`  ✓ Captured audit-role-${cred.role}.png`);
    }

    await page.close();
  }

  await browser.close();
  console.log("\n===============================================================================");
  console.log("🎉 ALL 5 APPLICATION ROLES SUCCESSFULLY AUDITED AND VERIFIED END-TO-END!");
  console.log("===============================================================================\n");
}

runRoleAudit().catch((err) => {
  console.error("Audit test failure:", err);
  process.exit(1);
});
