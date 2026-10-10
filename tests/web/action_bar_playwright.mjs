// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node action_bar_playwright.mjs <baseUrl> */

import { chromium } from "playwright";

const baseUrl = process.argv[2] || process.env.CHOICE_TEST_BASE_URL;
if (!baseUrl) {
  console.error("Usage: node action_bar_playwright.mjs <baseUrl>");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "360", width: 360, height: 640 },
  { name: "390", width: 390, height: 844 },
  { name: "768", width: 768, height: 900 },
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

async function openDeck(page, deckId) {
  const root = baseUrl.split("?")[0];
  await page.goto(
    `${root}?testhooks=1&deck=${encodeURIComponent(deckId)}`,
    { waitUntil: "networkidle", timeout: 30_000 },
  );
  await page.waitForFunction(() => window.ChoiceTestHooks && window.ChoiceTestHooks.actionBarMetrics);
  await page.waitForSelector("#actions .action-btn[data-dir='left']", { timeout: 20_000 });
  await page.waitForTimeout(200);
}

async function assertBar(page, vpName) {
  const metrics = await page.evaluate(() => window.ChoiceTestHooks.actionBarMetrics());
  if (!metrics || !metrics.ok) {
    throw new Error(`${vpName}: ${JSON.stringify(metrics)}`);
  }
  if (vpName !== "768" && !metrics.narrow) {
    throw new Error(`${vpName}: expected narrow layout`);
  }
  if (vpName === "768" && metrics.narrow) {
    throw new Error(`${vpName}: expected wide layout`);
  }
}

async function main() {
  const failures = [];
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
      await openDeck(page, "yes-no");
      await assertBar(page, vp.name);
    } catch (err) {
      failures.push(String(err.message || err));
    } finally {
      await browser.close();
    }
  }
  if (failures.length) {
    console.error(failures.join("\n"));
    process.exit(1);
  }
  console.log("action bar ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
