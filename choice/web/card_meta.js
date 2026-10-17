/* Card metadata blocks: mark, sections, reveal, chips (shared by paint*). */
const ChoiceCardMeta = (function () {
  const dom = typeof ChoiceDom !== "undefined" ? ChoiceDom : null;

  function el(tag, cls, text) {
    if (dom) return dom.el(tag, cls, text);
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function itemDecided(item) {
    if (!item) return false;
    if (item.choice != null && String(item.choice) !== "") return true;
    return !!(item.choice_label && String(item.choice_label).trim());
  }

  function appendMark(parent, item) {
    if (!item.mark) return;
    const word = item.mark === "right" ? "Correct" : "Missed";
    const note = item.mark_note ? " (" + item.mark_note + ")" : "";
    parent.append(el("p", "fine", word + note));
  }

  function appendSections(parent, item, blind) {
    if (blind || !item.sections || !item.sections.length) return;
    const wrap = el("div", "card-sections");
    item.sections.forEach((sec) => {
      const block = el("details", "section-block" + (sec.main ? " section-main" : ""));
      block.open = !sec.collapsed;
      block.append(el("summary", "section-title", sec.title || "Details"));
      if (sec.text) block.append(el("p", "section-text body", sec.text));
      wrap.append(block);
    });
    parent.append(wrap);
  }

  function appendReveal(parent, item, blind) {
    if (blind || !item || !item.reveal || !item.reveal.length) return;
    if (!itemDecided(item)) return;
    const row = el("div", "chips reveal-row");
    item.reveal.forEach((chip) =>
      row.append(el("span", "chip reveal-chip", chip.label + ": " + chip.text)),
    );
    parent.append(row);
  }

  function appendChips(parent, item, blind) {
    if (blind || !item.chips || !item.chips.length) return;
    const row = el("div", "chips");
    item.chips.forEach((chip) => row.append(el("span", "chip", chip.label + ": " + chip.text)));
    parent.append(row);
  }

  return {
    itemDecided,
    appendMark,
    appendSections,
    appendReveal,
    appendChips,
  };
})();

if (typeof globalThis !== "undefined") {
  globalThis.ChoiceCardMeta = ChoiceCardMeta;
}
