// SPDX-License-Identifier: AGPL-3.0-only

import assert from "node:assert/strict";
import { test } from "node:test";
import { dialogFitsViewport } from "./dialog_layout.mjs";

test("dialogFitsViewport accepts fully visible shell", () => {
  assert.equal(
    dialogFitsViewport({
      top: 100,
      left: 10,
      right: 350,
      bottom: 500,
      vvTop: 0,
      vvLeft: 0,
      vvRight: 360,
      vvBottom: 640,
      scrollHeight: 400,
      clientHeight: 400,
    }),
    true,
  );
});

test("dialogFitsViewport accepts internal scroll when clipped", () => {
  assert.equal(
    dialogFitsViewport({
      top: 50,
      left: 10,
      right: 350,
      bottom: 650,
      vvTop: 0,
      vvLeft: 0,
      vvRight: 360,
      vvBottom: 640,
      scrollHeight: 900,
      clientHeight: 500,
    }),
    true,
  );
});

test("dialogFitsViewport rejects off-screen without scroll room", () => {
  assert.equal(
    dialogFitsViewport({
      top: 700,
      left: 10,
      right: 350,
      bottom: 900,
      vvTop: 0,
      vvLeft: 0,
      vvRight: 360,
      vvBottom: 640,
      scrollHeight: 200,
      clientHeight: 200,
    }),
    false,
  );
});
