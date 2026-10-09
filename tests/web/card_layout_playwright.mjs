// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node card_layout_playwright.mjs <baseUrl> */

import { chromium } from "playwright";

const baseUrl = process.argv[2];
if (!baseUrl) {
  console.error("Usage: node card_layout_playwright.mjs <baseUrl>");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "466x900", width: 466, height: 900 },
  { name: "390x844", width: 390, height: 844 },
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

async function openImageDeck(page) {
  await page.waitForFunction(() => window.ChoiceTestHooks);
  const deckBtn = page.locator("button.deck-link").first();
  await deckBtn.waitFor({ state: "visible", timeout: 15_000 });
  await deckBtn.click();
  await page.waitForSelector("article.card.image", { timeout: 15_000 });
  await page.waitForFunction(() => {
    const frame = document.querySelector("article.card.image .frame img");
    return frame && frame.complete && frame.naturalWidth > 0;
  });
}

async function assertCardLayout(page, vpName) {
  const metrics = await page.evaluate(() => window.ChoiceTestHooks.cardLayoutMetrics());
  if (!metrics || !metrics.ok) {
    throw new Error(`${vpName}: ${JSON.stringify(metrics)}`);
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
      await openImageDeck(page);
      await assertCardLayout(page, vp.name);
    } finally {
      await browser.close();
    }
  }
  console.log("card layout ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
