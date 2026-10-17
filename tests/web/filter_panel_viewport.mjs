// SPDX-License-Identifier: AGPL-3.0-only

/** Acceptance helpers for filter sheet with on-screen keyboard (shrunk visual viewport). */

export function filterPanelKeyboardAccepts(metrics, minOptions = 4) {
  if (!metrics) return false;
  if (!metrics.narrow) return false;
  if (!metrics.cssVarsSet) return false;
  if (!metrics.topAnchored) return false;
  if (!metrics.heightFitsViewport) return false;
  if (!metrics.searchVisible) return false;
  if (!metrics.applyReachable) return false;
  if (metrics.visibleOptionCount < minOptions) return false;
  if (metrics.nestedListScroll) return false;
  return true;
}

export function narrowViewportBox(vvHeight, vvTop = 0) {
  return {
    vvTop,
    vvHeight,
    vvBottom: vvTop + vvHeight,
  };
}
