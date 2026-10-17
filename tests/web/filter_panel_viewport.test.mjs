// SPDX-License-Identifier: AGPL-3.0-only

import assert from "node:assert/strict";
import { test } from "node:test";
import { filterPanelKeyboardAccepts } from "./filter_panel_viewport.mjs";

test("filterPanelKeyboardAccepts passes shrunk keyboard layout", () => {
  assert.equal(
    filterPanelKeyboardAccepts(
      {
        narrow: true,
        cssVarsSet: true,
        topAnchored: true,
        heightFitsViewport: true,
        searchVisible: true,
        applyReachable: true,
        visibleOptionCount: 6,
        nestedListScroll: false,
      },
      4,
    ),
    true,
  );
});

test("filterPanelKeyboardAccepts rejects nested option list scroll", () => {
  assert.equal(
    filterPanelKeyboardAccepts({
      narrow: true,
      cssVarsSet: true,
      topAnchored: true,
      heightFitsViewport: true,
      searchVisible: true,
      applyReachable: true,
      visibleOptionCount: 6,
      nestedListScroll: true,
    }),
    false,
  );
});
