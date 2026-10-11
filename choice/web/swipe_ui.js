/* Card tap vs action bar (browser + node tests). */
(function (root) {
  const TAP_MOVE_PX = 14;
  const SWIPE_DIRS = ["left", "right", "up", "down"];

  function movedBeyondTap(dx, dy, threshold) {
    const t = threshold == null ? TAP_MOVE_PX : threshold;
    return Math.abs(dx) > t || Math.abs(dy) > t;
  }

  /** Tap or sub-threshold drag on the card never opens a menu or decides. */
  function cardReleaseOutcome(moved, armedDirection) {
    if (armedDirection && SWIPE_DIRS.includes(armedDirection)) {
      return { openMenu: false, decide: true, direction: armedDirection };
    }
    return { openMenu: false, decide: false, direction: null };
  }

  function actionBarDecideDirection(button) {
    if (!button || !button.dataset) return null;
    const dir = String(button.dataset.dir || "");
    return SWIPE_DIRS.includes(dir) ? dir : null;
  }

  root.ChoiceSwipeUi = {
    TAP_MOVE_PX,
    movedBeyondTap,
    cardReleaseOutcome,
    actionBarDecideDirection,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
