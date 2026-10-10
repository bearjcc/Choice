// SPDX-License-Identifier: AGPL-3.0-only
/** Returns true when the dialog shell fits the visual viewport (or scrolls inside). */

export function dialogFitsViewport(metrics, slack = 1) {
  if (!metrics) return false;
  const {
    top,
    left,
    right,
    bottom,
    vvTop,
    vvLeft,
    vvRight,
    vvBottom,
    scrollHeight,
    clientHeight,
  } = metrics;
  const inView =
    top >= vvTop - slack &&
    left >= vvLeft - slack &&
    right <= vvRight + slack &&
    bottom <= vvBottom + slack;
  if (inView) return true;
  const overflows = scrollHeight > clientHeight + 1;
  const clipped =
    bottom > vvBottom + slack || top < vvTop - slack || right > vvRight + slack || left < vvLeft - slack;
  return overflows && clipped;
}

/** Phone layout: wide enough, centred or bottom sheet, on-screen. */
export function dialogPhoneLayout(metrics, viewportWidth, slack = 2) {
  if (!metrics || !viewportWidth) return false;
  if (!dialogFitsViewport(metrics, slack)) return false;
  const minW = viewportWidth * 0.8;
  if (metrics.width < minW - slack) return false;
  const vvMidX = metrics.vvLeft + metrics.vvWidth / 2;
  const shellMidX = (metrics.left + metrics.right) / 2;
  const centered = Math.abs(shellMidX - vvMidX) <= 28;
  const bottomAnchored = metrics.bottom >= metrics.vvBottom - 48;
  if (metrics.narrow) return centered || bottomAnchored;
  return centered;
}
