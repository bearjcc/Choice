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
    undo: "M8 7H5v3m0 0a6 6 0 1 0 1.5 4.5",
    up: "M12 6v12m0 0-4.5-4.5M12 18l4.5-4.5",
    down: "M12 18V6m0 0 4.5 4.5M12 6 7.5 10.5",
    left: "M7 12h10m0 0-4-4m4 4-4 4",
    right: "M17 12H7m0 0 4-4m-4 4 4 4",
    x: "M7 7l10 10M17 7 7 17",
  };

  function svg(name) {
    const d = PATHS[name] || PATHS.check;
    return (
      '<svg class="action-icon-svg" viewBox="0 0 24 24" focusable="false" aria-hidden="true">' +
      '<path fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round" d="' +
      d +
      '"></path></svg>'
    );
  }

  function infer(spec, label) {
    const id = (spec && spec.id) || "";
    const text = String(label || (spec && spec.label) || "").toLowerCase();
    const value = String((spec && spec.value) || "").toLowerCase();
    if (id === "undo") return "undo";
    if (text.includes("favour") || text.includes("favorite") || value.includes("favour")) return "star";
    if (text.includes("star")) return "star";
    if (text.includes("trash") || text.includes("delete") || text.includes("reject")) return "trash";
    if (text.includes("no") && id === "left") return "x";
    if (text.includes("yes") || text.includes("like") || text.includes("keep")) return "check";
    if (text.includes("heart") || text.includes("love")) return "heart";
    if (text.includes("skip") || spec && spec.later) return "skip";
    if (id === "left") return "x";
    if (id === "right") return "check";
    if (id === "up") return "star";
    if (id === "down") return "skip";
    return "check";
  }

  function resolve(spec, label) {
    const configured = spec && spec.icon;
    if (configured && PATHS[configured]) return configured;
    return infer(spec, label);
  }

  return { svg, resolve, infer, names: Object.keys(PATHS) };
})();

if (typeof globalThis !== "undefined") {
  globalThis.ChoiceActionIcons = ChoiceActionIcons;
}
