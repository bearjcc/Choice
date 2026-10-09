// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node modal_layout_playwright.mjs <baseUrl> */

import { chromium } from "playwright";
import { dialogFitsViewport } from "./dialog_layout.mjs";

const baseUrl = process.argv[2];
if (!baseUrl) {
  console.error("Usage: node modal_layout_playwright.mjs <baseUrl>");
  process.exit(2);
}

const VIEWPORTS = [
  { name: "360x640", width: 360, height: 640 },
  { name: "390x844", width: 390, height: 844 },
  { name: "844x390-landscape", width: 844, height: 390 },
];

const SCENARIOS = [
  { name: "menu", run: async (page) => page.evaluate(() => window.ChoiceTestHooks.openMenu()) },
  { name: "counts", run: async (page) => page.evaluate(() => window.ChoiceTestHooks.openCounts()) },
  {
    name: "count-settings",
    run: async (page) => page.evaluate(() => window.ChoiceTestHooks.openCountSettings()),
  },
  {
    name: "order-settings",
    run: async (page) => page.evaluate(() => window.ChoiceTestHooks.openOrderSettings()),
  },
  {
    name: "queue-failures",
    run: async (page) =>
      page.evaluate(() => {
        window.ChoiceTestHooks.seedQueueFailures();
        window.ChoiceTestHooks.openQueueFailures();
      }),
  },
  {
    name: "browse-picker",
    run: async (page) =>
      page.evaluate(() => {
        const input = { value: "." };
        window.ChoiceTestHooks.openBrowsePicker(input, { type: "folder" });
      }),
  },
  {
    name: "confirm",
    run: async (page) =>
      page.evaluate(() => {
        window.ChoiceTestHooks.openConfirm("Remove this deck?");
      }),
  },
];

async function assertDialog(page, vpName, scenarioName) {
  await page.waitForFunction(() => window.ChoiceDialog && window.ChoiceDialog.isOpen());
  await page.waitForTimeout(300);
  await page.evaluate(() => window.ChoiceDialog.syncViewport());
  const metrics = await page.evaluate(() => window.ChoiceDialog.layoutMetrics());
  const ok = dialogFitsViewport(metrics);
  if (!ok) {
    throw new Error(`${vpName} ${scenarioName}: ${JSON.stringify(metrics)}`);
  }
  await page.evaluate(() => window.ChoiceDialog.close());
  await page.waitForFunction(() => !window.ChoiceDialog.isOpen());
}

async function openDeck(page) {
  await page.waitForFunction(() => window.ChoiceTestHooks);
  const deckBtn = page.locator("button.deck-link").first();
  await deckBtn.waitFor({ state: "visible", timeout: 15_000 });
  await deckBtn.click();
  await page.waitForSelector("#actions:not([hidden])", { timeout: 15_000 });
}

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
      await openDeck(page);
      for (const scenario of SCENARIOS) {
        try {
          await scenario.run(page);
          await assertDialog(page, vp.name, scenario.name);
        } catch (err) {
          failures.push(String(err.message || err));
        }
      }
      await page.evaluate(() => window.ChoiceTestHooks.showPeople());
      await page.locator("button.assign").first().click();
      await assertDialog(page, vp.name, "assign");
    } finally {
      await browser.close();
    }
  }
  if (failures.length) {
    console.error(failures.join("\n"));
    process.exit(1);
  }
  console.log("modal layout ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
