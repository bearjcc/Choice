// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node top_bar_screenshots.mjs <baseUrl> <outDir> [before|after] */

import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.argv[2];
const outDir = process.argv[3];
const tag = process.argv[4] || "after";
if (!baseUrl || !outDir) {
  console.error("Usage: node top_bar_screenshots.mjs <baseUrl> <outDir> [before|after]");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "320", width: 320, height: 640 },
  { name: "390", width: 390, height: 844 },
  { name: "1440", width: 1440, height: 900 },
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

async function openDeck(page) {
  await page.waitForFunction(() => window.ChoiceTestHooks);
  const people = page.locator(".people");
  if (await people.count()) {
    await page.locator("button.deck-link").filter({ hasText: "Bear" }).click();
  }
  await page.waitForSelector("ul.library button.deck-link", { timeout: 15_000 });
  await page.locator("ul.library button.deck-link").first().click();
  await page.waitForSelector("#menu:not([hidden])", { timeout: 15_000 });
  await page.locator("#title").evaluate((el) => {
    el.textContent = "Tag check with a very long deck title that should ellipsize";
  });
}

async function assertOneRow(page) {
  const box = await page.locator(".top-row").boundingBox();
  const menu = await page.locator("#menu").boundingBox();
  if (!box || !menu) throw new Error("missing top bar boxes");
  if (menu.y > box.y + box.height * 0.6) {
    throw new Error("menu button wrapped below top row");
  }
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  for (const vp of VIEWPORTS) {
    const browser = await launchBrowser();
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      colorScheme: "dark",
    });
    await context.addInitScript(() => {
      localStorage.setItem("choice.user", "bear");
    });
    const page = await context.newPage();
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
    await openDeck(page);
    await assertOneRow(page);
    await page.locator(".top-row").screenshot({
      path: path.join(outDir, `top-bar-${tag}-${vp.name}.png`),
    });
    await browser.close();
  }
  console.log("top bar screenshots ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
