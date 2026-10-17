// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node filter_keyboard_playwright.mjs <baseUrl> [screenshotDir] */

import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { filterPanelKeyboardAccepts } from "./filter_panel_viewport.mjs";

const baseUrl = process.argv[2];
const shotDir = process.argv[3] || "";
if (!baseUrl) {
  console.error("Usage: node filter_keyboard_playwright.mjs <baseUrl> [screenshotDir]");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "390x844", width: 390, height: 844 },
  { name: "390x450", width: 390, height: 450 },
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
  await page.locator("ul.library button.deck-link").filter({ hasText: title }).first().click();
  await page.waitForSelector("#filter-toggle:not([hidden])", { timeout: 15_000 });
}

async function maybeShot(page, vp, deck, phase) {
  if (!shotDir) return;
  fs.mkdirSync(shotDir, { recursive: true });
  await page.screenshot({
    path: path.join(shotDir, `filter-keyboard-${deck}-${phase}-${vp.name}.png`),
    fullPage: true,
  });
}

async function assertKeyboardLayout(page, vpName, minOptions) {
  const metrics = await page.evaluate(() => window.ChoiceTestHooks.filterPanelKeyboardMetrics());
  if (!filterPanelKeyboardAccepts(metrics, minOptions)) {
    throw new Error(`${vpName}: keyboard layout failed: ${JSON.stringify(metrics)}`);
  }
}

async function exerciseMulti(page, vpName) {
  await page.locator("#filter-toggle").click();
  await page.waitForFunction(() => document.getElementById("filter-panel")?.open);
  const search = page.locator(".filter-panel-search").first();
  await search.click();
  await search.fill("");
  await assertKeyboardLayout(page, vpName, 4);
  await maybeShot(page, { name: vpName }, "many", "focused");
  await page.locator("#filter-panel-apply").click();
  await page.waitForFunction(() => !document.getElementById("filter-panel")?.open);
}

async function exerciseCombo(page, vpName) {
  await page.locator("#filter-toggle").click();
  await page.waitForFunction(() => document.getElementById("filter-panel")?.open);
  const combo = page.locator(".filter-combobox-input").first();
  await combo.click();
  await combo.fill("Rating");
  await assertKeyboardLayout(page, vpName, 4);
  await maybeShot(page, { name: vpName }, "combo", "focused");
  await page.locator("#filter-panel-apply").click();
  await page.waitForFunction(() => !document.getElementById("filter-panel")?.open);
}

async function main() {
  for (const vp of VIEWPORTS) {
    const browser = await launchBrowser();
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    await context.addInitScript(() => {
      localStorage.setItem("choice.user", "bear");
    });
    const page = await context.newPage();
    try {
      await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
      await openDeck(page, "Many filters");
      await exerciseMulti(page, vp.name);

      await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
      await openDeck(page, "Combobox filters");
      await exerciseCombo(page, vp.name);
    } finally {
      await browser.close();
    }
  }
  console.log("filter keyboard layout ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
