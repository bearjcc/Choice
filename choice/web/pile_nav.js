/* Pile cursor helpers (browser + node tests). */
(function (root) {
  function syncPosToAnchor(items, pos, anchorId) {
    if (!items || !items.length) return 0;
    if (!anchorId) return pos >= items.length ? 0 : pos;
    const idx = items.findIndex((row) => row.id === anchorId);
    return idx >= 0 ? idx : 0;
  }

  function removePendingSwipe(items, pos, itemId) {
    const list = items.slice();
    const idx = list.findIndex((row) => row.id === itemId);
    if (idx === -1) return { items: list, pos };
    list.splice(idx, 1);
    let nextPos = pos;
    if (idx < pos) nextPos -= 1;
    else if (idx === pos && nextPos >= list.length) {
      nextPos = list.length ? Math.min(nextPos, list.length - 1) : 0;
    }
    return { items: list, pos: nextPos };
  }

  function advanceShowAllPos(items, pos, itemId) {
    if (!items.length) return 0;
    const idx = items.findIndex((row) => row.id === itemId);
    if (idx === -1) return pos >= items.length ? 0 : pos;
    return (idx + 1) % items.length;
  }

  function restorePendingUndo(items, pos, restoredItem) {
    const list = items.slice();
    const id = restoredItem && restoredItem.id;
    if (!id) return { items: list, pos };
    const existing = list.findIndex((row) => row.id === id);
    if (existing >= 0) return { items: list, pos: existing };
    const insertAt = Math.max(0, Math.min(pos, list.length));
    list.splice(insertAt, 0, restoredItem);
    return { items: list, pos: insertAt };
  }

  function currentItem(items, pos) {
    return items && items.length && pos >= 0 && pos < items.length ? items[pos] : null;
  }

  root.ChoicePileNav = {
    syncPosToAnchor,
    removePendingSwipe,
    advanceShowAllPos,
    restorePendingUndo,
    currentItem,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
