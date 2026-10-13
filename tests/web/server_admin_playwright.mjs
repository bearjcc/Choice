// SPDX-License-Identifier: AGPL-3.0-only
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const baseUrl = process.argv[2];
const shotDir = process.argv[3] || "";
if (!baseUrl) process.exit(2);

const browser = await chromium.launch({ headless: true, channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await context.addInitScript(() => localStorage.setItem("choice.user", "alice"));
const page = await context.newPage();
await page.goto(baseUrl, { waitUntil: "networkidle" });
await page.waitForFunction(() => window.ChoiceTestHooks);
await page.evaluate(() => window.ChoiceTestHooks.openServerAdminPanel());
await page.waitForSelector("#dialog-body .server-admin-form");
if (shotDir) {
  fs.mkdirSync(shotDir, { recursive: true });
  await page.screenshot({ path: path.join(shotDir, "server-admin-1440x900.png"), fullPage: true });
}
await browser.close();
