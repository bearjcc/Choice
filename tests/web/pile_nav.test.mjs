// SPDX-License-Identifier: AGPL-3.0-only

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const code = readFileSync(join(root, "choice/web/pile_nav.js"), "utf8");
const sandbox = { globalThis: {} };
sandbox.globalThis = sandbox;
vm.runInContext(code, vm.createContext(sandbox));
const nav = sandbox.ChoicePileNav;

function item(id) {
  return { id, title: id };
}

function simulatePendingSwipe(items, pos, itemId) {
  const next = nav.removePendingSwipe(items, pos, itemId);
  return { items: next.items, pos: next.pos, current: () => next.items[next.pos] || null };
}

function reloadPending(items, pos, anchorId, apiItems) {
  const newPos = nav.syncPosToAnchor(apiItems, pos, anchorId);
  return { items: apiItems, pos: newPos, current: () => apiItems[newPos] || null };
}

test("pending: swipe a then reload [b,c,d] shows b", () => {
  let items = [item("a"), item("b"), item("c"), item("d")];
  let pos = 0;
  let cur = simulatePendingSwipe(items, pos, "a");
  assert.equal(cur.current().id, "b");
  const after = reloadPending(cur.items, cur.pos, "b", [item("b"), item("c"), item("d")]);
  assert.equal(after.current().id, "b");
});

test("pending: two swipes before first reload shows c", () => {
  let items = [item("a"), item("b"), item("c"), item("d")];
  let pos = 0;
  let cur = simulatePendingSwipe(items, pos, "a");
  assert.equal(cur.current().id, "b");
  cur = simulatePendingSwipe(cur.items, cur.pos, "b");
  assert.equal(cur.current().id, "c");
  const after = reloadPending(cur.items, cur.pos, "c", [item("c"), item("d")]);
  assert.equal(after.current().id, "c");
});

test("show all: swipe advances then reload keeps anchor", () => {
  const items = [item("a"), item("b"), item("c"), item("d")];
  let pos = nav.advanceShowAllPos(items, 0, "a");
  assert.equal(pos, 1);
  assert.equal(items[pos].id, "b");
  const newPos = nav.syncPosToAnchor(items, pos, "b");
  assert.equal(newPos, 1);
});

test("undo: anchor restores undone card index", () => {
  const items = [item("a"), item("b"), item("c")];
  const pos = nav.syncPosToAnchor(items, 0, "a");
  assert.equal(pos, 0);
  const restored = [item("a"), item("b"), item("c"), item("d")];
  const afterUndo = nav.syncPosToAnchor(restored, 1, "a");
  assert.equal(afterUndo, 0);
  assert.equal(restored[afterUndo].id, "a");
});
