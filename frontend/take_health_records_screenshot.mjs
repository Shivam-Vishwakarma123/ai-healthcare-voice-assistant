import { chromium } from "playwright";

async function login() {
  const resp = await fetch("http://127.0.0.1:8000/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "patient01@demo.carevoice.test",
      password: "CareVoiceDemo2026!",
    }),
  });
  return await resp.json();
}

async function capture() {
  const auth = await login();
  console.log("Logged in as patient:", auth.user.email);

  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  const viewports = [
    { name: "desktop-1440", width: 1440, height: 900 },
    { name: "tablet-768", width: 768, height: 1024 },
    { name: "mobile-375", width: 375, height: 812 },
  ];

  for (const vp of viewports) {
    console.log(`Starting viewport: ${vp.name} (${vp.width}x${vp.height})...`);
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const page = await context.newPage();

    page.on("pageerror", (err) => console.error(`[Page Error ${vp.name}]:`, err));

    await page.goto("http://127.0.0.1:3000");
    await page.evaluate((auth) => {
      localStorage.setItem("ahva_token", auth.access_token);
      localStorage.setItem("ahva_user", JSON.stringify(auth.user));
      localStorage.setItem("carevoice_theme", "light");
    }, auth);

    await page.reload();

    // Wait for initial dashboard load to finish so loadAccount doesn't reset page
    await page.waitForSelector("#welcome-patient-heading", { timeout: 15000 });
    await page.waitForTimeout(500);

    // If hamburger is present and visible, click it to expand drawer
    const hamburger = await page.$(".cv-hamburger");
    if (hamburger && (await hamburger.isVisible())) {
      await hamburger.click();
      await page.waitForTimeout(400);
    }

    // Click Health records in nav
    const hrNav = page.locator(".cv-nav-item:has-text('Health records')");
    await hrNav.waitFor({ state: "visible", timeout: 10000 });
    await hrNav.click();
    await page.waitForTimeout(500);

    // Switch to Prescriptions tab (support both desktop tab button and mobile quick-select)
    const mobileSelect = await page.$("#mobile-tab-select");
    if (mobileSelect && (await mobileSelect.isVisible())) {
      await mobileSelect.selectOption("prescriptions");
    } else {
      const rxTab = page.locator("[role='tab']:has-text('Prescriptions')");
      await rxTab.waitFor({ state: "visible", timeout: 10000 });
      await rxTab.click();
    }

    // Wait until cards render
    await page.waitForSelector(".record-card-rx", { timeout: 15000 });
    await page.waitForTimeout(600);

    // Capture Light mode screenshot
    await page.screenshot({ path: `health-records-rx-${vp.name}-light.png`, fullPage: false });
    console.log(`✓ Captured health-records-rx-${vp.name}-light.png`);

    // Switch to Dark mode
    await page.evaluate(() => {
      document.documentElement.dataset.theme = "dark";
    });
    await page.waitForTimeout(400);

    // Capture Dark mode screenshot
    await page.screenshot({ path: `health-records-rx-${vp.name}-dark.png`, fullPage: false });
    console.log(`✓ Captured health-records-rx-${vp.name}-dark.png`);

    await context.close();
  }

  await browser.close();
  console.log("All screenshots captured successfully!");
}

capture().catch((err) => {
  console.error("Capture failure:", err);
  process.exit(1);
});
