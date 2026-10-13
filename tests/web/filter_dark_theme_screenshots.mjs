// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node filter_dark_theme_screenshots.mjs <baseUrl> <outDir> */

import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.argv[2];
const outDir = process.argv[3];
if (!baseUrl || !outDir) {
  console.error("Usage: node filter_dark_theme_screenshots.mjs <baseUrl> <outDir>");
  process.exit(2);
}

fs.mkdirSync(outDir, { recursive: true });

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
  const back = page.locator("#back-library:not([hidden])");
  if (await back.count()) {
    await back.click();
  }
  const people = page.locator(".people");
  if (await people.count()) {
    await page.locator("button.deck-link").filter({ hasText: "Bear" }).click();
  }
  await page.waitForSelector("ul.library button.deck-link, .empty", { timeout: 15_000 });
  await page.locator("ul.library button.deck-link").filter({ hasText: title }).first().click();
  await page.waitForSelector("#filter-toggle:not([hidden])", { timeout: 15_000 });
}

async function main() {
  const browser = await launchBrowser();
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    colorScheme: "dark",
  });
  await context.addInitScript(() => {
    localStorage.setItem("choice.user", "bear");
  });
  const page = await context.newPage();
  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });

  await openDeck(page, "Combobox filters");
  await page.locator("#filter-toggle").click();
  await page.waitForFunction(() => document.getElementById("filter-panel")?.open);
  const combo = page.locator(".filter-combobox-input").first();
  await combo.click();
  await combo.fill("Rating");
  await page.waitForSelector(".filter-combobox-option", { state: "visible" });
  await page.screenshot({
    path: path.join(outDir, "filter-dark-after-combo.png"),
    fullPage: true,
  });

  await page.locator("#filter-panel-close").click();
  await page.waitForFunction(() => !document.getElementById("filter-panel")?.open);

  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
  await openDeck(page, "Many filters");
  await page.locator("#filter-toggle").click();
  await page.waitForFunction(() => document.getElementById("filter-panel")?.open);
  await page.locator(".filter-panel-search").first().fill("Tag");
  await page.waitForSelector(".filter-option-row", { state: "visible" });
  await page.screenshot({
    path: path.join(outDir, "filter-dark-after-multi.png"),
    fullPage: true,
  });

  await browser.close();
  console.log("filter dark theme screenshots ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
