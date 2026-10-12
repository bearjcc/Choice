/* Deck action button icons (Material Design Icons via ChoiceMdi). */

const ChoiceActionIcons = (function () {
  const mdi = typeof ChoiceMdi !== "undefined" ? ChoiceMdi : null;

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

  function hasPath(name) {
    if (!mdi) return false;
    return !!mdi.paths[mdi.resolve(name)];
  }

  function svg(name) {
    if (mdi) return mdi.svg(name, "action-icon-svg");
    return "";
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
    const lead = text.match(/^([ab])\b/);
    if (lead) {
      return lead[1] === "a" ? "letter-a" : "letter-b";
    }
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
    if (configured && hasPath(configured)) return configured;

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
    if (configured && hasPath(configured)) return configured;
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
      if (configured && hasPath(configured)) {
        resolved[id] = configured;
      } else {
        resolved[id] = inferOne(e.spec, e.label);
      }
    });
    dedupePeers(resolved, entries);
    return resolved;
  }

  function arrowVector(name) {
    if (mdi) return mdi.arrowVector(name);
    return null;
  }

  const PATHS = {};
  if (mdi) {
    Object.keys(mdi.aliases).forEach((key) => {
      PATHS[key] = mdi.paths[mdi.resolve(key)] || "";
    });
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
