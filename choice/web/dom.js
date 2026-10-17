/* Minimal DOM helpers shared by app, filter panel, and config UI. */
const ChoiceDom = (function () {
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  return { el };
})();

if (typeof globalThis !== "undefined") {
  globalThis.ChoiceDom = ChoiceDom;
}
