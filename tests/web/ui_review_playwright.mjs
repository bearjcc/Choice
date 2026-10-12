// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node ui_review_playwright.mjs <baseUrl> [screenshotDir] */

import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.argv[2] || process.env.CHOICE_TEST_BASE_URL;
const shotDir = process.argv[3] || process.env.CHOICE_UI_SCREENSHOT_DIR || "";
if (!baseUrl) {
  console.error("Usage: node ui_review_playwright.mjs <baseUrl> [screenshotDir]");
  process.exit(2);
}

const ALL_VIEWPORTS = [
  { name: "360x640", width: 360, height: 640, mobile: true },
  { name: "390x844", width: 390, height: 844, mobile: true },
  { name: "412x915", width: 412, height: 915, mobile: true },
  { name: "768x1024", width: 768, height: 1024, mobile: false },
  { name: "1366x768", width: 1366, height: 768, mobile: false },
  { name: "1920x1080", width: 1920, height: 1080, mobile: false },
  { name: "1440x900", width: 1440, height: 900, mobile: false },
  { name: "2560x1080", width: 2560, height: 1080, mobile: false },
];

const VIEWPORTS = process.env.CHOICE_UI_VIEWPORTS
  ? ALL_VIEWPORTS.filter((vp) => process.env.CHOICE_UI_VIEWPORTS.split(",").includes(vp.name))
  : ALL_VIEWPORTS;

const SHOT_WIDTHS = new Set(["390x844", "1366x768", "1440x900", "1920x1080", "2560x1080"]);

const STRESS_DECKS = [
  {
    id: "content",
    title: "Content",
    endless: true,
    count_label: "∞ · 7,138 unlabelled photos",
    source_type: "swipe",
  },
  {
    id: "dupes",
    title: "Duplicates",
    left: 3810,
    total: 3810,
    count_label: "3,810 borderline left",
    meter: true,
  },
  {
    id: "longrun",
    title: "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijkl",
    left: 2,
    total: 10,
  },
  {
    id: "long",
    title: "Very Long Deck Title That Should Stay Readable",
    left: 12,
    total: 40,
  },
  { id: "private", title: "Private queue", left: 3, total: 3, private: true },
  { id: "broken", title: "Broken plugin", error: "deck.py raised on import" },
];

function launchBrowser() {
  const chrome = process.env.CHOICE_TEST_CHROME || "/usr/local/bin/google-chrome";
  return chromium.launch({ headless: true, executablePath: chrome });
}

async function assertLayout(page, label) {
  const m = await page.evaluate(() => window.ChoiceTestHooks.layoutMetrics());
  const problems = [];
  if (m.overflowX) problems.push("horizontal overflow");
  if (m.badDecks && m.badDecks.length) {
    problems.push(`single-char title wraps: ${JSON.stringify(m.badDecks)}`);
  }
  const badControls = (m.controls || []).filter((c) => !c.skipped && !c.ok);
  if (badControls.length) problems.push(`controls off-screen: ${JSON.stringify(badControls)}`);
  const tiny = (m.smallTaps || []).filter(
    (t) => (t.w < 40 || t.h < 40) && !String(t.cls).includes("deck-more"),
  );
  if (tiny.length) problems.push(`small tap targets: ${JSON.stringify(tiny)}`);
  if (problems.length) throw new Error(`${label}: ${problems.join("; ")}`);
}

async function maybeShot(page, vp, screen) {
  if (!shotDir || !SHOT_WIDTHS.has(vp.name)) return;
  fs.mkdirSync(shotDir, { recursive: true });
  const file = path.join(shotDir, `${screen}-${vp.name}.png`);
  await page.screenshot({ path: file, fullPage: true });
}

async function ensureLibrary(page) {
  const people = page.locator(".people");
  if (await people.count()) {
    await page.locator("button.deck-link").filter({ hasText: "Bear" }).click();
  }
  await page.waitForSelector("ul.library button.deck-link, .empty", { timeout: 15_000 });
}

async function openDeck(page, title) {
  await ensureLibrary(page);
  await page.locator("ul.library button.deck-link").filter({ hasText: title }).first().click();
  await page.waitForSelector("#back-library:not([hidden])", { timeout: 15_000 });
}

async function installStressIndexStub(page) {
  const body = JSON.stringify({
    ok: true,
    library: STRESS_DECKS,
    decks: STRESS_DECKS,
    app_title: "Choice UI",
    warnings: [],
  });
  await page.route("**/api/index**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body });
  });
}

async function runScenario(page, vp, scenario) {
  await page.setViewportSize({ width: vp.width, height: vp.height });
  if (scenario.indexStub) {
    await installStressIndexStub(page);
  } else {
    await page.unroute("**/api/index**").catch(() => {});
  }
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 25_000 });
  await page.waitForFunction(() => window.ChoiceTestHooks);
  await scenario.setup(page);
  await page.waitForTimeout(80);
  await assertLayout(page, `${vp.name}/${scenario.name}`);
  await maybeShot(page, vp, scenario.name);
  if (scenario.after) await scenario.after(page);
}

const SCENARIOS = [
  {
    name: "home-stress",
    indexStub: true,
    setup: async (page) => {
      await page.evaluate((decks) => window.ChoiceTestHooks.seedHomeLibrary(decks), STRESS_DECKS);
      const dup = await page.evaluate(() =>
        window.ChoiceTestHooks.formatCountMeta({
          left: 3810,
          count_label: "3,810 borderline left",
        }),
      );
      if (dup.includes("3810 left")) {
        throw new Error(`duplicate left in count meta: ${dup}`);
      }
      const vw = page.viewportSize().width;
      const more = await page.locator(".library .deck-more").first().boundingBox();
      if (!more || more.x + more.width > vw + 2) {
        throw new Error("deck-more menu pushed off screen");
      }
    },
  },
  {
    name: "home-empty",
    setup: async (page) => {
      await page.evaluate(() => window.ChoiceTestHooks.seedHomeLibrary([]));
    },
  },
  {
    name: "home-live",
    setup: async (page) => {
      await page.waitForSelector("ul.library, .empty", { timeout: 20_000 });
    },
  },
  {
    name: "deck-header",
    setup: async (page) => {
      await page.waitForSelector("ul.library button.deck-link", { timeout: 20_000 });
      await openDeck(page, "Yes or no");
      await page.evaluate(() =>
        window.ChoiceTestHooks.mockDeckCounts({
          count_label: "3,810 borderline left",
          left: 3810,
          total: 5000,
          meter: true,
        }),
      );
    },
  },
  {
    name: "deck-card",
    setup: async (page) => {
      await openDeck(page, "Yes or no");
      await page.waitForSelector("article.card", { timeout: 15_000 });
    },
  },
  {
    name: "action-bar",
    setup: async (page) => {
      await openDeck(page, "Yes or no");
      await page.waitForSelector("#actions:not([hidden])", { timeout: 15_000 });
      const metrics = await page.evaluate(() => window.ChoiceTestHooks.actionBarMetrics());
      if (!metrics.ok) throw new Error(`action bar: ${JSON.stringify(metrics)}`);
    },
  },
  {
    name: "empty-scanning",
    setup: async (page) => {
      await openDeck(page, "Yes or no");
      await page.evaluate(() => window.ChoiceTestHooks.showScanningEmpty());
    },
  },
  {
    name: "modal-menu",
    setup: async (page) => {
      await page.waitForSelector("ul.library button.deck-link", { timeout: 20_000 });
      await openDeck(page, "Yes or no");
      await page.click("#menu");
      await page.waitForFunction(() => window.ChoiceDialog.isOpen());
    },
    after: async (page) => {
      await page.evaluate(() => window.ChoiceDialog.close());
    },
  },
  {
    name: "back-to-decks",
    setup: async (page) => {
      await openDeck(page, "Yes or no");
      await page.click("#back-library");
      await page.waitForSelector("ul.library, .empty", { timeout: 15_000 });
    },
  },
  {
    name: "modal-client-settings",
    setup: async (page) => {
      await ensureLibrary(page);
      await page.click("#client-settings");
      await page.waitForFunction(() => window.ChoiceDialog.isOpen());
    },
    after: async (page) => {
      await page.evaluate(() => window.ChoiceDialog.close());
    },
  },
  {
    name: "modal-server-admin",
    setup: async (page) => {
      await ensureLibrary(page);
      await page.evaluate(() => window.ChoiceTestHooks.openAdminPanel());
      await page.waitForFunction(() => window.ChoiceDialog.isOpen());
    },
    after: async (page) => {
      await page.evaluate(() => window.ChoiceDialog.close());
    },
  },
  {
    name: "modal-counts",
    setup: async (page) => {
      await openDeck(page, "Yes or no");
      await page.click("#menu");
      await page.locator("dialog .menu-item", { hasText: "Counts" }).click();
      await page.waitForFunction(() => window.ChoiceDialog.isOpen());
    },
    after: async (page) => {
      await page.evaluate(() => window.ChoiceDialog.close());
    },
  },
  {
    name: "queue-badge",
    setup: async (page) => {
      await page.waitForSelector("ul.library button.deck-link", { timeout: 20_000 });
      await openDeck(page, "Yes or no");
      await page.evaluate(() => {
        window.ChoiceTestHooks.seedQueueFailures();
        document.getElementById("queue-badge").hidden = false;
      });
    },
  },
];

async function main() {
  const browser = await launchBrowser();
  const failures = [];
  try {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: vp.mobile ? 2.5 : 1,
        isMobile: vp.mobile,
        hasTouch: vp.mobile,
      });
      await context.addInitScript(() => {
        localStorage.setItem("choice.user", "bear");
      });
      const page = await context.newPage();
      page.setDefaultTimeout(20_000);
      for (const scenario of SCENARIOS) {
        try {
          await runScenario(page, vp, scenario);
        } catch (err) {
          failures.push(`${vp.name}/${scenario.name}: ${err.message || err}`);
        }
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  if (failures.length) {
    console.error(failures.join("\n"));
    process.exit(1);
  }
  console.log(`ui_review ok (${VIEWPORTS.length} viewports × ${SCENARIOS.length} screens)`);
}

main();
