/* Pile cursor helpers (browser + node tests). */
(function (root) {
  function syncPosToAnchor(items, pos, anchorId) {
    if (!items || !items.length) return 0;
    if (anchorId) {
      const idx = items.findIndex((row) => row.id === anchorId);
      if (idx >= 0) return idx;
    }
    if (pos >= items.length) return Math.max(0, items.length - 1);
    return Math.max(0, Math.min(pos, items.length - 1));
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
    if (idx === -1) return syncPosToAnchor(items, pos, null);
    return (idx + 1) % items.length;
  }

  function restoreUndoAtPos(items, pos, restoredItem) {
    const list = items.slice();
    const id = restoredItem && restoredItem.id;
    if (!id) return { items: list, pos };
    const existing = list.findIndex((row) => row.id === id);
    if (existing >= 0) list.splice(existing, 1);
    const insertAt = Math.max(0, Math.min(pos, list.length));
    list.splice(insertAt, 0, restoredItem);
    return { items: list, pos: insertAt };
  }

  /** @deprecated use restoreUndoAtPos */
  function restorePendingUndo(items, pos, restoredItem) {
    return restoreUndoAtPos(items, pos, restoredItem);
  }

  function mergeReloadItems(prevItems, serverItems, pos, pin) {
    const prev = prevItems || [];
    const incoming = serverItems || [];
    if (!prev.length) return incoming.slice();
    const byId = new Map(incoming.map((row) => [row.id, row]));
    const out = [];
    const seen = new Set();
    for (const row of prev) {
      const fresh = byId.get(row.id);
      if (fresh) {
        out.push(fresh);
        seen.add(row.id);
      } else if (pin && row.id === pin.id) {
        out.push(pin.item || row);
        seen.add(row.id);
      }
    }
    for (const row of incoming) {
      if (seen.has(row.id)) continue;
      out.push(row);
      seen.add(row.id);
    }
    if (pin && pin.id) {
      const row = byId.get(pin.id) || pin.item;
      if (row && !seen.has(pin.id)) {
        const insertAt = Math.max(0, Math.min(typeof pin.pos === "number" ? pin.pos : pos, out.length));
        out.splice(insertAt, 0, row);
        seen.add(pin.id);
      } else if (row) {
        const idx = out.findIndex((r) => r.id === pin.id);
        const want = Math.max(0, Math.min(typeof pin.pos === "number" ? pin.pos : pos, Math.max(0, out.length - 1)));
        if (idx >= 0 && idx !== want) {
          const [moved] = out.splice(idx, 1);
          out.splice(Math.min(want, out.length), 0, moved);
        }
      }
    }
    if (!out.length) return incoming.slice();
    return out;
  }

  function currentItem(items, pos) {
    return items && items.length && pos >= 0 && pos < items.length ? items[pos] : null;
  }

  root.ChoicePileNav = {
    syncPosToAnchor,
    removePendingSwipe,
    advanceShowAllPos,
    restoreUndoAtPos,
    restorePendingUndo,
    mergeReloadItems,
    currentItem,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
