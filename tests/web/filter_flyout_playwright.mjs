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

async function openDeck(page, title) {
  await page.waitForFunction(() => window.ChoiceTestHooks);
  const people = page.locator(".people");
  if (await people.count()) {
    await page.locator("button.deck-link").filter({ hasText: "Bear" }).click();
  }
  await page.waitForSelector("ul.library button.deck-link, .empty", { timeout: 15_000 });
  const deckBtn = page.locator("ul.library button.deck-link").filter({ hasText: title });
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

async function exerciseManyFilters(page, vpName) {
  await page.locator("#filter-toggle").click();
  await page.waitForFunction(() => document.getElementById("filter-panel")?.open);

  const scroll = await page.evaluate(() => window.ChoiceTestHooks.filterPanelScrollMetrics());
  if (!scroll || !scroll.ok) {
    throw new Error(`${vpName}: filter panel should scroll: ${JSON.stringify(scroll)}`);
  }

  const search = page.locator(".filter-panel-search").first();
  await search.fill("Face 1");
  await page.locator(".filter-option-row").filter({ hasText: "Face 1" }).first().click();
  await search.fill("");
  await page.locator(".filter-option-row").filter({ hasText: "Tag 2" }).first().click();
  await page.locator("#filter-panel-apply").click();
  await page.waitForFunction(() => !document.getElementById("filter-panel")?.open);

  await assertCardVisible(page, vpName);
  await page.locator("#filter-summary:not([hidden])").waitFor({ state: "visible" });
}

async function exerciseComboboxDeck(page, vpName) {
  const comboInput = page.locator(".filter-combobox-input").first();
  await comboInput.click();
  await comboInput.fill("Rating 7");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expectComboboxValue(page, "Rating 7");

  await page.locator(".filter-combobox-clear").first().click();
  await expectComboboxValue(page, "");

  await comboInput.click();
  await comboInput.fill("Rating 3");
  await page.locator(".filter-combobox-option").filter({ hasText: "Rating 3" }).click();
  await expectComboboxValue(page, "Rating 3");

  const tagSearch = page.locator(".filter-panel-section").filter({ hasText: "Tags" }).locator(".filter-panel-search");
  await tagSearch.fill("Tag 5");
  await page
    .locator(".filter-panel-section")
    .filter({ hasText: "Tags" })
    .locator(".filter-option-row")
    .filter({ hasText: "Tag 5" })
    .click();

  await page.locator("#filter-panel-apply").click();
  await page.waitForFunction(() => !document.getElementById("filter-panel")?.open);
  await assertCardVisible(page, vpName);
}

async function expectComboboxValue(page, text) {
  const val = await page.locator(".filter-combobox-input").first().inputValue();
  if (val !== text) {
    throw new Error(`combobox expected "${text}" got "${val}"`);
  }
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
      await openDeck(page, "Many filters");
      await assertCardVisible(page, vp.name);
      await maybeShot(page, vp, "many-card");
      await exerciseManyFilters(page, vp.name);
      await maybeShot(page, vp, "many-after-apply");

      await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
      await openDeck(page, "Combobox filters");
      await page.locator("#filter-toggle").click();
      await page.waitForFunction(() => document.getElementById("filter-panel")?.open);
      await exerciseComboboxDeck(page, vp.name);
      await maybeShot(page, vp, "combo-after-apply");
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
