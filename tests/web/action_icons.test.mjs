// SPDX-License-Identifier: AGPL-3.0-only

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const require = createRequire(import.meta.url);

const script = readFileSync(join(root, "choice/web/action_icons.js"), "utf8");
eval(script);
const icons = globalThis.ChoiceActionIcons;

const cases = [
  { label: "Dislike", id: "left", want: "x" },
  { label: "Like", id: "right", want: "check" },
  { label: "Super-like", id: "right", want: "star" },
  { label: "A sounds like me", id: "left", want: "letter-a" },
  { label: "B sounds like me", id: "right", want: "letter-b" },
  { label: "Keep separate", id: "left", want: "left" },
  { label: "Merge", id: "right", want: "right" },
  { label: "⚠ Unsafe", id: "right", want: "x" },
  { label: "Unsure", id: "up", want: "question" },
  { label: "Can't tell", id: "up", want: "question" },
  { label: "Equal", id: "up", want: "equals" },
  { label: "Partial", id: "up", want: "question" },
  { label: "Needs edit", id: "up", want: "question" },
  { label: "Trash", id: "left", want: "x" },
  { label: "Delete", id: "down", into: "_trash", want: "trash" },
  { label: "Favourite", id: "up", want: "star" },
  { label: "Skip", id: "down", want: "skip" },
];

test("label icon table", () => {
  for (const row of cases) {
    const spec = { id: row.id, into: row.into };
    const got = icons.infer(spec, row.label);
    assert.equal(got, row.want, `${row.label} (${row.id})`);
  }
});

test("dislike is not treated as like", () => {
  assert.equal(icons.infer({ id: "right" }, "Dislike"), "x");
});

test("A is me / B is me use letter icons", () => {
  assert.equal(icons.infer({ id: "left" }, "A is me"), "letter-a");
  assert.equal(icons.infer({ id: "right" }, "B is me"), "letter-b");
});

test("plain A and B labels on left and right", () => {
  const map = icons.resolveAll([
    { spec: { id: "left" }, label: "A" },
    { spec: { id: "right" }, label: "B" },
  ]);
  assert.equal(map.left, "letter-a");
  assert.equal(map.right, "letter-b");
});

test("like vs super-like on same deck", () => {
  const map = icons.resolveAll([
    { spec: { id: "left" }, label: "Like" },
    { spec: { id: "right" }, label: "Super-like" },
  ]);
  assert.equal(map.left, "check");
  assert.equal(map.right, "star");
});

test("opposite directions do not share inferred icons", () => {
  const map = icons.resolveAll([
    { spec: { id: "left" }, label: "Option" },
    { spec: { id: "right" }, label: "Option" },
  ]);
  assert.notEqual(map.left, map.right);
});

test("arrow vectors point the right way", () => {
  const up = icons.arrowVector("up");
  const down = icons.arrowVector("down");
  const left = icons.arrowVector("left");
  const right = icons.arrowVector("right");
  assert.ok(up.dy < -0.5, "up should aim upward");
  assert.ok(down.dy > 0.5, "down should aim downward");
  assert.ok(left.dx < -0.5, "left should aim leftward");
  assert.ok(right.dx > 0.5, "right should aim rightward");
});

test("undo path is present", () => {
  assert.ok(icons.paths.undo.includes("M"));
  const html = icons.svg("undo");
  assert.match(html, /action-icon-svg/);
});
