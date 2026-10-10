/* Built-in inline SVG icons for deck action buttons. */

const ChoiceActionIcons = (function () {
  const PATHS = {
    star:
      "M12 3.2l2.35 4.76 5.25.77-3.8 3.68.9 5.23L12 15.9l-4.7 2.74.9-5.23-3.8-3.68 5.25-.77L12 3.2z",
    trash:
      "M9 4h6m-8 3h10m-1 0-.7 11.2c-.1 1-.9 1.8-1.9 1.8H9.6c-1 0-1.8-.8-1.9-1.8L7 7m3 3v5m4-5v5",
    heart: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.2A4 4 0 0 1 19 10c0 5.6-7 10-7 10z",
    check: "M5 12.5 9.5 17 19 7",
    skip: "M12 5v9m0 0 4-4m-4 4-4-4",
    undo: "M8 9H4V5M4 9a7 7 0 1 1 2.2 5.1",
    up: "M12 18V6m0 0-4.5 4.5M12 6l4.5 4.5",
    down: "M12 6v12m0 0-4.5-4.5M12 18l4.5-4.5",
    left: "M17 12H7m0 0 4-4m-4 4 4 4",
    right: "M7 12h10m0 0-4-4m4 4-4 4",
    x: "M7 7l10 10M17 7 7 17",
    equals: "M6 10h12M6 14h12",
    question: "M9.5 9a3 3 0 1 1 5.5 2c0 2-3 2.2-3 4.2V16M12 19.2h.01",
    "letter-a": "M12 18V6l-4 12h2.2l.8-2.6h3.8l.8 2.6H18L14 6h-2z",
    "letter-b":
      "M9 18V6h4.2a3.2 3.2 0 0 1 0 6.4H11v5.6H9zm2-8.2h2a1.4 1.4 0 0 0 0-2.8H11v2.8z",
  };

  const NEUTRAL_WORDS = new Set([
    "unsure",
    "equal",
    "partial",
    "needs",
    "edit",
    "cant",
    "cannot",
    "tell",
    "maybe",
    "unknown",
  ]);

  const OPPOSITE = { left: "right", right: "left", up: "down", down: "up" };

  function svg(name) {
    const d = PATHS[name] || PATHS.check;
    return (
      '<svg class="action-icon-svg" viewBox="0 0 24 24" focusable="false" aria-hidden="true">' +
      '<path fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round" d="' +
      d +
      '"></path></svg>'
    );
  }

  function tokenize(text) {
    return String(text || "")
      .toLowerCase()
      .replace(/'/g, "")
      .replace(/[^\w\s]/g, " ")
      .split(/\s+/)
      .filter(Boolean);
  }

  function hasWord(words, word) {
    return words.includes(word);
  }

  function hasNegative(words, raw) {
    const text = String(raw || "").toLowerCase();
    if (/\bdon'?t\b/.test(text) || /\bno\b/.test(text) || /\bnot\b/.test(text)) {
      if (
        hasWord(words, "like") ||
        hasWord(words, "safe") ||
        hasWord(words, "yes") ||
        hasWord(words, "keep")
      ) {
        return true;
      }
    }
    if (hasWord(words, "dislike")) return true;
    if (hasWord(words, "unsafe") || text.includes("unsafe")) return true;
    if (hasWord(words, "bad") || hasWord(words, "reject")) return true;
    return false;
  }

  function isNeutral(words) {
    if (hasWord(words, "unsure")) return true;
    if (words.includes("cant") || words.includes("cannot")) return true;
    if (hasWord(words, "tell") && (hasWord(words, "cant") || hasWord(words, "cannot"))) return true;
    if (hasWord(words, "equal")) return true;
    if (hasWord(words, "partial")) return true;
    if (hasWord(words, "needs") && hasWord(words, "edit")) return true;
    return false;
  }

  function neutralIcon(words) {
    if (hasWord(words, "equal")) return "equals";
    return "question";
  }

  function abLetter(words, raw) {
    const text = String(raw || "").toLowerCase().trim();
    if (text === "a") return "letter-a";
    if (text === "b") return "letter-b";
    const m = text.match(/\b([ab])\b/);
    if (!m) return null;
    if (
      text.includes("sound") ||
      text.includes("like me") ||
      text.includes("pick") ||
      words.length <= 2
    ) {
      return m[1] === "a" ? "letter-a" : "letter-b";
    }
    return null;
  }

  function trashOrReject(spec, words, raw) {
    const text = String(raw || "").toLowerCase();
    const into = String((spec && spec.into) || "").toLowerCase();
    const value = String((spec && spec.value) || "").toLowerCase();
    const id = (spec && spec.id) || "";
    if (hasWord(words, "delete") || into.includes("_trash") || into.includes("trash")) {
      return "trash";
    }
    if (hasWord(words, "trash") && id === "down") return "trash";
    if (hasWord(words, "trash") || hasWord(words, "delete")) return "x";
    return null;
  }

  function inferOne(spec, label) {
    const id = (spec && spec.id) || "";
    const raw = label || (spec && spec.label) || "";
    const words = tokenize(raw);
    const value = String((spec && spec.value) || "").toLowerCase();

    if (id === "undo") return "undo";

    const configured = spec && spec.icon;
    if (configured && PATHS[configured]) return configured;

    if (hasNegative(words, raw)) return "x";

    const ab = abLetter(words, raw);
    if (ab) return ab;

    if (isNeutral(words)) return neutralIcon(words);

    const trashIcon = trashOrReject(spec, words, raw);
    if (trashIcon) return trashIcon;

    if (
      hasWord(words, "favour") ||
      hasWord(words, "favorite") ||
      hasWord(words, "favourite") ||
      value.includes("favour")
    ) {
      return "star";
    }
    if (hasWord(words, "super") && hasWord(words, "like")) return "star";
    if (hasWord(words, "star")) return "star";
    if (hasWord(words, "love")) return "heart";
    if (hasWord(words, "heart")) return "heart";

    if (hasWord(words, "merge")) return "right";
    if (hasWord(words, "separate") || (hasWord(words, "keep") && hasWord(words, "separate"))) {
      return "left";
    }

    if (hasWord(words, "skip") || (spec && spec.later)) return "skip";

    if (hasWord(words, "yes") || (hasWord(words, "like") && !hasWord(words, "dislike"))) {
      return "check";
    }
    if (hasWord(words, "keep") && !hasWord(words, "separate")) return "check";

    if (id === "left") return "x";
    if (id === "right") return "check";
    if (id === "up") {
      if (hasWord(words, "super") || hasWord(words, "favour") || hasWord(words, "favorite")) {
        return "star";
      }
      return "up";
    }
    if (id === "down") return "skip";

    return "check";
  }

  function directionDefault(id) {
    if (id === "left") return "x";
    if (id === "right") return "check";
    if (id === "up") return "up";
    if (id === "down") return "skip";
    return "check";
  }

  function dedupePeers(resolved, entries) {
    const byId = {};
    entries.forEach((e) => {
      byId[e.spec.id] = e;
    });
    for (const id of ["left", "right", "up", "down"]) {
      const opp = OPPOSITE[id];
      if (!opp || !byId[id] || !byId[opp]) continue;
      const a = resolved[id];
      const b = resolved[opp];
      if (!a || !b || a !== b) continue;
      if (byId[id].spec.icon || byId[opp].spec.icon) continue;
      resolved[id] = directionDefault(id);
      resolved[opp] = directionDefault(opp);
      if (resolved[id] === resolved[opp]) {
        resolved[id] = id === "left" ? "x" : resolved[id];
        resolved[opp] = id === "left" ? "check" : resolved[opp];
      }
    }
    const lr = entries.filter((e) => e.spec.id === "left" || e.spec.id === "right");
    if (lr.length === 2 && resolved.left === resolved.right) {
      const leftLabel = lr.find((e) => e.spec.id === "left").label || "";
      const rightLabel = lr.find((e) => e.spec.id === "right").label || "";
      const lAb = abLetter(tokenize(leftLabel), leftLabel);
      const rAb = abLetter(tokenize(rightLabel), rightLabel);
      if (lAb && rAb && lAb !== rAb) {
        resolved.left = lAb;
        resolved.right = rAb;
      } else if (hasWord(tokenize(leftLabel), "separate") && hasWord(tokenize(rightLabel), "merge")) {
        resolved.left = "left";
        resolved.right = "right";
      } else if (
        hasWord(tokenize(rightLabel), "super") &&
        hasWord(tokenize(rightLabel), "like") &&
        hasWord(tokenize(leftLabel), "like")
      ) {
        resolved.right = "star";
        resolved.left = "check";
      }
    }
  }

  function resolve(spec, label, options) {
    const configured = spec && spec.icon;
    if (configured && PATHS[configured]) return configured;
    const peers = options && options.peers;
    if (peers && peers.length) {
      const entries = peers.map((p) => ({
        spec: p.spec,
        label: p.label,
      }));
      const map = resolveAll(entries);
      return map[spec.id] || inferOne(spec, label);
    }
    return inferOne(spec, label);
  }

  function resolveAll(entries) {
    const resolved = {};
    entries.forEach((e) => {
      const id = e.spec.id;
      const configured = e.spec.icon;
      if (configured && PATHS[configured]) {
        resolved[id] = configured;
      } else {
        resolved[id] = inferOne(e.spec, e.label);
      }
    });
    dedupePeers(resolved, entries);
    return resolved;
  }

  /** Unit-test helper: dominant direction of arrow icon stems (−1..1 on each axis). */
  function arrowVector(name) {
    const d = PATHS[name];
    if (!d) return null;
    const absV = d.match(/M[\d.]+ ([\d.]+)V([\d.]+)/);
    if (absV) {
      const dy = parseFloat(absV[2]) - parseFloat(absV[1]);
      return { dx: 0, dy: dy < 0 ? -1 : 1 };
    }
    const relV = d.match(/M[\d.]+ ([\d.]+)v([\d.]+)/);
    if (relV) {
      return { dx: 0, dy: 1 };
    }
    const absH = d.match(/M([\d.]+) [\d.]+H([\d.]+)/);
    if (absH) {
      const dx = parseFloat(absH[2]) - parseFloat(absH[1]);
      return { dx: dx < 0 ? -1 : 1, dy: 0 };
    }
    const relH = d.match(/M([\d.]+) [\d.]+h([\d.]+)/);
    if (relH) {
      const dx = parseFloat(relH[2]);
      return { dx: dx < 0 ? -1 : 1, dy: 0 };
    }
    return null;
  }

  return {
    svg,
    resolve,
    resolveAll,
    infer: inferOne,
    tokenize,
    arrowVector,
    names: Object.keys(PATHS),
    paths: PATHS,
  };
})();

if (typeof globalThis !== "undefined") {
  globalThis.ChoiceActionIcons = ChoiceActionIcons;
}
