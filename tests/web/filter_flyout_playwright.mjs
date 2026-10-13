// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node filter_flyout_playwright.mjs <baseUrl> [screenshotDir] */

import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.argv[2];
const shotDir = process.argv[3] || "";
if (!baseUrl) {
  console.error("Usage: node filter_flyout_playwright.mjs <baseUrl> [screenshotDir]");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "390x844", width: 390, height: 844 },
  { name: "1440x900", width: 1440, height: 900 },
];

function launchBrowser() {
  const chrome = process.env.CHOICE_TEST_CHROME || "/usr/local/bin/google-chrome";
  const opts = { headless: true };
  if (process.env.CHOICE_TEST_CHROME) {
    opts.executablePath = process.env.CHOICE_TEST_CHROME;
  } else {
    opts.channel = "chrome";
  }
  return chromium.launch(opts).catch(() => chromium.launch({ headless: true, executablePath: chrome }));
}

async function openManyFiltersDeck(page) {
  await page.waitForFunction(() => window.ChoiceTestHooks);
  const people = page.locator(".people");
  if (await people.count()) {
    await page.locator("button.deck-link").filter({ hasText: "Bear" }).click();
  }
  await page.waitForSelector("ul.library button.deck-link, .empty", { timeout: 15_000 });
  const deckBtn = page.locator("ul.library button.deck-link").filter({ hasText: "Many filters" });
  await deckBtn.first().click();
  await page.waitForSelector("#filter-toggle:not([hidden])", { timeout: 15_000 });
  await page.waitForSelector("article.card", { timeout: 15_000 });
}

async function assertCardVisible(page, vpName) {
  const m = await page.evaluate(() => window.ChoiceTestHooks.cardVisibleMetrics());
  if (!m || !m.ok) {
    throw new Error(`${vpName}: card not visible: ${JSON.stringify(m)}`);
  }
}

async function maybeShot(page, vp, name) {
  if (!shotDir) return;
  fs.mkdirSync(shotDir, { recursive: true });
  await page.screenshot({
    path: path.join(shotDir, `filter-flyout-${name}-${vp.name}.png`),
    fullPage: true,
  });
}

async function exercisePanel(page, vpName) {
  await page.locator("#filter-toggle").click();
  await page.waitForFunction(() => document.getElementById("filter-panel")?.open);

  const scroll = await page.evaluate(() => window.ChoiceTestHooks.filterPanelScrollMetrics());
  if (!scroll || !scroll.ok) {
    throw new Error(`${vpName}: filter panel should scroll: ${JSON.stringify(scroll)}`);
  }

  await page.locator(".filter-panel-chips .filter-chip").first().click();
  await page.locator(".filter-panel-chips .filter-chip").nth(1).click();
  await page.locator("#filter-panel-apply").click();
  await page.waitForFunction(() => !document.getElementById("filter-panel")?.open);

  await assertCardVisible(page, vpName);
  const summary = page.locator("#filter-summary:not([hidden])");
  await summary.waitFor({ state: "visible" });
}

async function main() {
  for (const vp of VIEWPORTS) {
    const browser = await launchBrowser();
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
    });
    await context.addInitScript(() => {
      localStorage.setItem("choice.user", "bear");
    });
    const page = await context.newPage();
    try {
      await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
      await openManyFiltersDeck(page);
      await assertCardVisible(page, vp.name);
      await maybeShot(page, vp, "card-visible");
      await exercisePanel(page, vp.name);
      await maybeShot(page, vp, "after-apply");
    } finally {
      await browser.close();
    }
  }
  console.log("filter flyout ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
