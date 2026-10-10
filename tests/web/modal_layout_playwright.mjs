// SPDX-License-Identifier: AGPL-3.0-only
/* Usage: node modal_layout_playwright.mjs <baseUrl> */

import { chromium } from "playwright";
import { dialogFitsViewport, dialogPhoneLayout } from "./dialog_layout.mjs";

const baseUrl = process.argv[2];
if (!baseUrl) {
  console.error("Usage: node modal_layout_playwright.mjs <baseUrl>");
  process.exit(2);
}

const MOBILE_UA =
  "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36";

const PHONE_VIEWPORTS = [
  { name: "360x640", width: 360, height: 640 },
  { name: "390x844", width: 390, height: 844 },
  { name: "412x915", width: 412, height: 915 },
];

const DESKTOP_VIEWPORTS = [{ name: "844x390-landscape", width: 844, height: 390 }];

const HOOK_SCENARIOS = [
  {
    name: "menu",
    needsDeck: true,
    deckId: "sort-pile",
    run: async (page) => {
      await page.click("#menu");
      await page.waitForFunction(() => window.ChoiceDialog.isOpen());
      await page.waitForSelector("#dialog .menu-item");
    },
  },
  {
    name: "counts",
    needsDeck: true,
    deckId: "yes-no",
    run: async (page) => {
      await page.click("#menu");
      await page.locator("dialog .menu-item", { hasText: "Counts" }).click();
    },
    click: "#dialog .dialog-body button",
  },
  {
    name: "count-settings",
    needsDeck: true,
    deckId: "sort-pile",
    run: async (page) => {
      await page.click("#menu");
      await page.locator("dialog .menu-item", { hasText: "Count display" }).click();
    },
    click: "#dialog .sheet-actions button",
  },
  {
    name: "order-settings",
    needsDeck: true,
    deckId: "sort-pile",
    run: async (page) => {
      await page.click("#menu");
      await page.locator("dialog .menu-item", { hasText: "Order and filter" }).click();
    },
    click: "#dialog select.setup-input",
  },
  {
    name: "queue-failures",
    needsDeck: true,
    deckId: "yes-no",
    run: async (page) =>
      page.evaluate(() => {
        window.ChoiceTestHooks.seedQueueFailures();
        document.getElementById("queue-badge").click();
      }),
  },
  {
    name: "browse-picker",
    needsDeck: false,
    run: async (page) =>
      page.evaluate(() => {
        const input = { value: "." };
        window.ChoiceTestHooks.openBrowsePicker(input, { type: "folder" });
      }),
    click: "#dialog button",
  },
  {
    name: "confirm",
    needsDeck: false,
    run: async (page) =>
      page.evaluate(() => {
        window.ChoiceTestHooks.openConfirm("Remove this deck?");
      }),
    click: "#dialog .sheet-actions button",
  },
  {
    name: "assign",
    needsDeck: false,
    run: async (page) => {
      await page.evaluate(() => window.ChoiceTestHooks.showPeople());
      await page.locator("button.assign").first().click();
    },
    click: "#dialog .sheet-actions button",
  },
  {
    name: "add-deck",
    needsDeck: false,
    run: async (page) => page.evaluate(() => window.ChoiceTestHooks.openAddDeck()),
    click: "#dialog .setup-wizard button",
  },
  {
    name: "deck-edit",
    needsDeck: false,
    run: async (page) => page.locator("button.deck-more").first().click(),
    click: "#dialog .setup-wizard button",
  },
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

async function ensureDeckLibrary(page) {
  await page.waitForFunction(() => document.querySelector("button.deck-link, .people"));
  if (await page.locator(".people").isVisible()) {
    await page.locator("button.deck-link").filter({ hasText: "Bear" }).click();
  }
  await page.waitForSelector("ul.library button.deck-link", { timeout: 20_000 });
}

async function openDeck(page, deckId) {
  const title = deckId === "sort-pile" ? "Sort pile" : "Yes or no";
  await ensureDeckLibrary(page);
  await page.locator("ul.library button.deck-link").filter({ hasText: title }).first().click();
  await page.waitForSelector("#menu:not([hidden])", { timeout: 15_000 });
}

async function assertDialog(page, vp, scenarioName, phone, clickSelector) {
  await page.waitForFunction(() => window.ChoiceDialog && window.ChoiceDialog.isOpen());
  await page.waitForSelector("#dialog-body button, #dialog-body select, #dialog-body h2", {
    timeout: 10_000,
  });
  await page.waitForTimeout(200);
  await page.evaluate(() => window.ChoiceDialog.syncViewport());
  const metrics = await page.evaluate(() => window.ChoiceDialog.layoutMetrics());
  const ok = phone ? dialogPhoneLayout(metrics, vp.width) : dialogFitsViewport(metrics);
  if (!ok) {
    throw new Error(`${vp.name} ${scenarioName}: ${JSON.stringify(metrics)}`);
  }
  if (clickSelector) {
    const loc = page.locator(clickSelector).first();
    if ((await loc.count()) < 1) {
      const snippet = await page.locator("#dialog-body").innerText();
      throw new Error(`${scenarioName}: no control ${clickSelector}: ${snippet.slice(0, 120)}`);
    }
    await loc.click({ force: true, timeout: 10_000 });
  }
}

async function collectDomModalIds(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll("[data-choice-modal]")]
      .map((el) => el.getAttribute("data-choice-modal"))
      .filter(Boolean),
  );
}

async function runPhoneSuite(vp) {
  const browser = await launchBrowser();
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    userAgent: MOBILE_UA,
    deviceScaleFactor: 2.6,
    isMobile: true,
    hasTouch: true,
  });
  await context.addInitScript(() => {
    localStorage.setItem("choice.user", "bear");
  });
  const page = await context.newPage();
  const failures = [];
  const exercisedDom = new Set();
  const SCENARIO_DOM = {
    menu: ["menu"],
    counts: ["menu"],
    "count-settings": ["count-settings"],
    "order-settings": ["order-settings"],
    "queue-failures": ["queue-failures"],
    "browse-picker": [],
    confirm: [],
    assign: ["assign"],
    "add-deck": ["add-deck"],
    "deck-edit": ["deck-edit"],
  };
  try {
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
    await page.waitForFunction(() => window.ChoiceTestHooks);
    await ensureDeckLibrary(page);
    const expectedDom = await page.evaluate(() => window.ChoiceTestHooks.expectedModalTriggerIds());
    const seenDom = new Set();
    for (const scenario of HOOK_SCENARIOS) {
      try {
        if (scenario.needsDeck) {
          await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
          await openDeck(page, scenario.deckId || "yes-no");
        } else {
          await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
        }
        for (const id of await collectDomModalIds(page)) seenDom.add(id);
        await scenario.run(page);
        (SCENARIO_DOM[scenario.name] || []).forEach((id) => exercisedDom.add(id));
        for (const id of await collectDomModalIds(page)) seenDom.add(id);
        await assertDialog(page, vp, scenario.name, true, scenario.click);
        await page.evaluate(() => window.ChoiceDialog.close());
        await page.waitForFunction(() => !window.ChoiceDialog.isOpen());
      } catch (err) {
        failures.push(String(err.message || err));
      }
    }
    for (const id of expectedDom) {
      if (!exercisedDom.has(id)) {
        failures.push(`${vp.name}: modal trigger [data-choice-modal=${id}] was not opened by a scenario`);
      }
    }
  } finally {
    await browser.close();
  }
  return failures;
}

async function runDesktopSuite(vp) {
  const browser = await launchBrowser();
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
  });
  await context.addInitScript(() => {
    localStorage.setItem("choice.user", "bear");
  });
  const page = await context.newPage();
  const failures = [];
  try {
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30_000 });
    await openDeck(page, "sort-pile");
    const scenario = HOOK_SCENARIOS.find((s) => s.name === "order-settings");
    await scenario.run(page);
    await page.waitForSelector("#dialog select.setup-input", { timeout: 10_000 });
    await assertDialog(page, vp, scenario.name, false, scenario.click);
    await page.evaluate(() => window.ChoiceDialog.close());
  } catch (err) {
    failures.push(String(err.message || err));
  } finally {
    await browser.close();
  }
  return failures;
}

async function main() {
  const failures = [];
  for (const vp of PHONE_VIEWPORTS) {
    failures.push(...(await runPhoneSuite(vp)));
  }
  for (const vp of DESKTOP_VIEWPORTS) {
    failures.push(...(await runDesktopSuite(vp)));
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
