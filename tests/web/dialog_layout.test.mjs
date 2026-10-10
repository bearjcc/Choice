// SPDX-License-Identifier: AGPL-3.0-only

import assert from "node:assert/strict";
import { test } from "node:test";
import { dialogFitsViewport, dialogPhoneLayout } from "./dialog_layout.mjs";

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

test("dialogPhoneLayout accepts wide bottom sheet", () => {
  assert.equal(
    dialogPhoneLayout(
      {
        top: 400,
        left: 20,
        right: 340,
        bottom: 630,
        width: 320,
        vvTop: 0,
        vvLeft: 0,
        vvWidth: 360,
        vvHeight: 640,
        vvRight: 360,
        vvBottom: 640,
        scrollHeight: 400,
        clientHeight: 400,
        narrow: true,
      },
      360,
    ),
    true,
  );
});

test("dialogPhoneLayout rejects tiny top-left shell", () => {
  assert.equal(
    dialogPhoneLayout(
      {
        top: 0,
        left: 0,
        right: 40,
        bottom: 30,
        width: 40,
        vvTop: 0,
        vvLeft: 0,
        vvWidth: 360,
        vvHeight: 640,
        vvRight: 360,
        vvBottom: 640,
        scrollHeight: 200,
        clientHeight: 200,
        narrow: true,
      },
      360,
    ),
    false,
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
