// SPDX-License-Identifier: AGPL-3.0-only

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const code = readFileSync(join(root, "choice/web/swipe_ui.js"), "utf8");
const sandbox = { globalThis: {} };
sandbox.globalThis = sandbox;
vm.runInContext(code, vm.createContext(sandbox));
const ui = sandbox.ChoiceSwipeUi;

test("tap on card does not open menu or decide", () => {
  const out = ui.cardReleaseOutcome(false, null);
  assert.equal(out.openMenu, false);
  assert.equal(out.decide, false);
  assert.equal(out.direction, null);
});

test("short drag below swipe threshold does not open menu or decide", () => {
  assert.equal(ui.movedBeyondTap(5, 5), false);
  const out = ui.cardReleaseOutcome(false, null);
  assert.equal(out.decide, false);
});

test("action bar button triggers decide direction", () => {
  assert.equal(ui.actionBarDecideDirection({ dataset: { dir: "right" } }), "right");
  assert.equal(ui.actionBarDecideDirection({ dataset: { dir: "left" } }), "left");
  assert.equal(ui.actionBarDecideDirection({ dataset: {} }), null);
  assert.equal(ui.actionBarDecideDirection(null), null);
});

test("armed swipe on card decides but does not open menu", () => {
  const out = ui.cardReleaseOutcome(true, "right");
  assert.equal(out.openMenu, false);
  assert.equal(out.decide, true);
  assert.equal(out.direction, "right");
});
