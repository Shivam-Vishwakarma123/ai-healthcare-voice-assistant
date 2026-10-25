import { chromium } from "playwright";
import { existsSync, readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const BASE_URL = "http://127.0.0.1:3000";
const CREDENTIALS_PATH = resolve("../.qa-test-credentials.env");
const OUTPUT_DIR = resolve("qa-screenshots");
const VIEWPORTS = [320, 375, 390, 430, 768, 1024, 1280, 1440];

if (!existsSync(CREDENTIALS_PATH)) {
  throw new Error("Missing ignored .qa-test-credentials.env; no account credentials are printed or stored by this audit.");
}

const localCredentials = Object.fromEntries(
  readFileSync(CREDENTIALS_PATH, "utf8").split(/\r?\n/)
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => {
      const splitAt = line.indexOf("=");
      return [line.slice(0, splitAt), line.slice(splitAt + 1)];
    }),
);

function credential(role, field) {
  const value = localCredentials[`CV_QA_${role.toUpperCase()}_${field}`];
  if (!value) throw new Error(`A marked QA account field is missing for role ${role}.`);
  return value;
}

const ALL_ROLES = ["patient", "doctor", "hospital_staff", "hospital_admin", "platform_admin"];
const ROLE_FILTER = process.env.CV_QA_ROLE_FILTER?.split(",").map((role) => role.trim()).filter(Boolean);
const VIEW_FILTER = process.env.CV_QA_VIEW_FILTER?.toLowerCase();
const ROLES = ROLE_FILTER?.length ? ROLE_FILTER : ALL_ROLES;
const findings = [];
const errors = [];
let checks = 0;
const COMPACT_VIEWPORTS = [320, 430, 768, 1440];

async function setLanguage(page, language) {
  await page.locator(`.cv-topbar-actions .cv-language-toggle button`).nth(language === "en" ? 0 : 1).click();
  await page.waitForFunction((expected) => document.documentElement.lang === expected, language);
}

async function setTheme(page, theme) {
  await page.locator(".cv-topbar-actions select").selectOption(theme);
  if (theme === "system") {
    for (const preference of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme: preference });
      await page.waitForFunction((expected) => document.documentElement.dataset.theme === expected, preference, { timeout: 5000 });
      await checkLayout(page, `system-${preference}`);
    }
  } else {
    await page.waitForFunction((expected) => document.documentElement.dataset.theme === expected, theme, { timeout: 5000 });
    await checkLayout(page, theme);
  }
}

async function checkLayout(page, label) {
  const result = await page.evaluate(() => {
    const width = window.innerWidth;
    const main = document.querySelector(".cv-main");
    const root = document.querySelector(".cv-content");
    const selectors = [
      ".cv-content", ".cv-page-title", ".cv-card", ".card", ".cv-form",
      ".cv-insight-item", ".cv-record-card", ".cv-notification-row",
      ".cv-provider-dashboard", ".doctor-workspace-container", ".cv-admin-management",
    ];
    const outside = [];
    for (const selector of selectors) {
      for (const node of document.querySelectorAll(selector)) {
        if (!node.getClientRects().length) continue;
        const style = getComputedStyle(node);
        if (["auto", "scroll"].includes(style.overflowX)) continue;
        const box = node.getBoundingClientRect();
        if (box.width > 0 && (box.left < -1 || box.right > width + 1)) {
          outside.push(`${selector}:${Math.round(box.left)}..${Math.round(box.right)}`);
          if (outside.length >= 4) break;
        }
      }
      if (outside.length >= 4) break;
    }
    return {
      width,
      scrollWidth: document.documentElement.scrollWidth,
      lang: document.documentElement.lang,
      theme: document.documentElement.dataset.theme,
      contentLength: (root?.innerText || "").trim().length,
      mainWidth: Math.round(main?.getBoundingClientRect().width || 0),
      outside,
    };
  });
  checks += 1;
  if (result.scrollWidth > result.width + 1 || result.outside.length || result.contentLength < 20) {
    findings.push({ label, ...result });
  }
}

async function run() {
  mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  });

  try {
    for (const role of ROLES) {
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      page.on("pageerror", (error) => errors.push({ role, kind: "pageerror", message: error.message }));
      page.on("response", (response) => {
        if (response.url().includes("/api/v1/") && response.status() >= 400) {
          errors.push({ role, kind: "api", status: response.status(), path: new URL(response.url()).pathname });
        }
      });

      await page.goto(BASE_URL);
      await page.getByRole("button", { name: "Sign in", exact: true }).first().click({ noWaitAfter: true });
      await page.getByPlaceholder("Username or email address").fill(credential(role, "LOGIN"));
      await page.getByLabel("Password", { exact: true }).fill(credential(role, "PASSWORD"));
      await page.getByRole("button", { name: "Sign in", exact: true }).last().click();
      await page.locator(".cv-breadcrumb strong").waitFor({ state: "visible", timeout: 30000 });
      await page.locator(".cv-content").waitFor({ state: "visible" });
      await page.waitForFunction(() => (document.querySelector(".cv-content")?.innerText?.trim().length || 0) > 20, null, { timeout: 30000 });

      const navItems = page.locator(".cv-nav-item");
      const routeNames = await navItems.allTextContents();
      console.log(`${role}: ${routeNames.map((name) => name.trim()).join(" | ")}`);

      for (let routeIndex = 0; routeIndex < routeNames.length; routeIndex += 1) {
        await page.setViewportSize({ width: 1440, height: 900 });
        await setLanguage(page, "en");
        const button = page.locator(".cv-nav-item").nth(routeIndex);
        await button.click();
        await page.waitForTimeout(250);
        const routeLabel = routeNames[routeIndex].trim().replace(/\s+/g, " ");
        if (VIEW_FILTER && !routeLabel.toLowerCase().includes(VIEW_FILTER)) continue;
        console.log(`  ${role}: ${routeLabel}`);
        const selected = await button.evaluate((node) => node.classList.contains("active"));
        if (!selected) {
          findings.push({ role, route: routeLabel, kind: "navigation", expected: "clicked item active", actual: "clicked item inactive" });
        }
        const routeErrors = page.locator(".cv-content [role='alert']");
        const routeError = await routeErrors.count() ? await routeErrors.first().textContent() : null;
        if (routeError && /failed|unable|could not|error/i.test(routeError)) {
          findings.push({ role, route: routeLabel, kind: "visible-error", text: routeError.trim().slice(0, 180) });
        }

        // Sweep every requested width in both translated and theme-distinct combinations.
        for (const [language, theme, widths] of [
          ["en", "light", routeLabel === "⌂Overview" ? VIEWPORTS : COMPACT_VIEWPORTS],
          ["hi", "dark", COMPACT_VIEWPORTS],
        ]) {
          await setLanguage(page, language);
          await page.locator(".cv-topbar-actions select").selectOption(theme);
          await page.waitForFunction((expected) => document.documentElement.dataset.theme === expected, theme);
          for (const width of widths) {
            await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
            await page.evaluate(() => new Promise((resolveFrame) => requestAnimationFrame(() => requestAnimationFrame(resolveFrame))));
            await checkLayout(page, `${role}/${routeLabel}/${language}/${theme}/${width}`);
            if (role === "patient" && language === "hi" && theme === "dark" && width === 320 && ["⌂Overview", "🛡️DPDP Privacy"].includes(routeLabel)) {
              const screenshotName = routeLabel === "⌂Overview" ? "patient-overview-320-dark-hi.png" : "patient-privacy-320-dark-hi.png";
              await page.screenshot({ path: resolve(OUTPUT_DIR, screenshotName), fullPage: true });
            }
          }
        }

        // Verify explicit Light, Dark, and System behavior in both interface languages.
        await page.setViewportSize({ width: 1440, height: 900 });
        for (const language of ["en", "hi"]) {
          await setLanguage(page, language);
          for (const theme of ["light", "dark", "system"]) {
            await setTheme(page, theme);
          }
        }
      }

      // browser.newPage() creates an isolated context for the next role, so no logout transition is needed here.
      await page.close();
    }
  } finally {
    await browser.close();
  }

  const report = { roles: ROLES, viewportWidths: VIEWPORTS, checks, findings, errors };
  writeFileSync(resolve(OUTPUT_DIR, "all-roles-ui-matrix.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(`Layout checks: ${checks}; visual findings: ${findings.length}; page/API errors: ${errors.length}`);
  if (findings.length) console.log(JSON.stringify(findings.slice(0, 100), null, 2));
  if (errors.length) console.log(JSON.stringify(errors.slice(0, 100), null, 2));
  if (findings.length || errors.length) process.exitCode = 1;
}

run().catch((error) => {
  console.error("Full UI matrix failed:", error.message);
  process.exitCode = 1;
});
