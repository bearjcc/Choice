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
