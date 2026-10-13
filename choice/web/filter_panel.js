/* Plugin filter flyout: draft selection, Apply/Clear, mobile sheet / desktop drawer. */

const ChoiceFilterPanel = (function () {
  const NARROW_MQ = "(max-width: 699px)";
  const SEARCH_MIN_OPTIONS = 10;

  let schema = null;
  let draft = null;
  let applyHandler = null;
  let previouslyFocused = null;
  let trapHandler = null;

  function $(id) {
    return document.getElementById(id);
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function deepCopySelection(sel) {
    if (!sel) return null;
    const out = {};
    Object.keys(sel).forEach((key) => {
      const row = sel[key];
      if (key === "_sort") {
        if (row) out._sort = row;
        return;
      }
      if (!row || !row.values || !row.values.length) return;
      out[key] = { values: row.values.slice(), match: row.match };
    });
    return Object.keys(out).length ? out : null;
  }

  function selectionEmpty(sel) {
    if (!sel) return true;
    return !Object.keys(sel).some((key) => {
      if (key === "_sort") return !!sel[key];
      const row = sel[key];
      return row && row.values && row.values.length;
    });
  }

  function activeValueCount(sel) {
    if (!sel) return 0;
    let n = 0;
    Object.keys(sel).forEach((key) => {
      if (key === "_sort") return;
      const row = sel[key];
      if (row && row.values) n += row.values.length;
    });
    return n;
  }

  function defaultMatchMode(filterSpec) {
    const modes = filterSpec && filterSpec.match;
    if (Array.isArray(modes) && modes.length) return modes[0];
    return "any";
  }

  function optionLabel(filterSpec, value) {
    const opts = (filterSpec && filterSpec.options) || [];
    const hit = opts.find((o) => String(o.value) === String(value));
    return hit ? hit.label || String(value) : String(value);
  }

  function buildSummary(sel) {
    if (!sel || !schema || !schema.filters) return "";
    const labels = [];
    schema.filters.forEach((spec) => {
      if (!spec || !spec.id) return;
      const row = sel[spec.id];
      if (!row || !row.values || !row.values.length) return;
      row.values.forEach((v) => labels.push(optionLabel(spec, v)));
    });
    if (!labels.length) return "";
    if (labels.length === 1) return labels[0];
    if (labels.length === 2) return labels[0] + " · " + labels[1];
    return labels[0] + " · " + labels[1] + " +" + (labels.length - 2);
  }

  function focusableIn(root) {
    if (!root) return [];
    return [...root.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )].filter((node) => node.offsetParent !== null || node === document.activeElement);
  }

  function attachFocusTrap(panel) {
    const inner = panel.querySelector(".filter-panel-inner");
    detachFocusTrap();
    trapHandler = (event) => {
      if (event.key !== "Tab" || !panel.open) return;
      const nodes = focusableIn(inner);
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", trapHandler);
  }

  function detachFocusTrap() {
    if (trapHandler) {
      document.removeEventListener("keydown", trapHandler);
      trapHandler = null;
    }
  }

  function renderBody() {
    const body = $("filter-panel-body");
    if (!body || !schema) return;
    body.replaceChildren();
    const sel = draft || {};

    (schema.filters || []).forEach((filterSpec) => {
      if (!filterSpec || filterSpec.type !== "tags" || !filterSpec.id) return;
      const section = el("section", "filter-panel-section");
      section.append(el("h3", "filter-panel-section-title", filterSpec.label || filterSpec.id));

      const options = filterSpec.options || [];
      let searchInput = null;
      if (options.length > SEARCH_MIN_OPTIONS) {
        searchInput = el("input", "filter-panel-search");
        searchInput.type = "search";
        searchInput.placeholder = "Search…";
        searchInput.setAttribute("aria-label", "Search " + (filterSpec.label || filterSpec.id));
        searchInput.autocomplete = "off";
        section.append(searchInput);
      }

      const chips = el("div", "filter-chips filter-panel-chips");
      const renderChips = (query) => {
        const q = (query || "").trim().toLowerCase();
        chips.replaceChildren();
        options.forEach((opt) => {
          const value = String(opt.value);
          const label = opt.label || value;
          if (q && !label.toLowerCase().includes(q) && !value.toLowerCase().includes(q)) return;
          const active =
            sel[filterSpec.id] &&
            sel[filterSpec.id].values &&
            sel[filterSpec.id].values.indexOf(value) !== -1;
          const chip = el("button", "filter-chip" + (active ? " on" : ""), label);
          chip.type = "button";
          if (opt.count != null) chip.title = String(opt.count);
          chip.addEventListener("click", () => toggleDraftValue(filterSpec, value));
          chips.append(chip);
        });
      };
      renderChips("");
      if (searchInput) {
        searchInput.addEventListener("input", () => renderChips(searchInput.value));
      }
      section.append(chips);

      const modes = filterSpec.match;
      const hasValues =
        sel[filterSpec.id] && sel[filterSpec.id].values && sel[filterSpec.id].values.length;
      if (Array.isArray(modes) && modes.length > 1 && hasValues) {
        const toggle = el("div", "filter-match");
        toggle.setAttribute("role", "group");
        toggle.setAttribute("aria-label", (filterSpec.label || filterSpec.id) + " match");
        modes.forEach((mode) => {
          const btn = el(
            "button",
            "filter-match-btn" + (sel[filterSpec.id].match === mode ? " on" : ""),
            mode
          );
          btn.type = "button";
          btn.addEventListener("click", () => setDraftMatch(filterSpec.id, mode));
          toggle.append(btn);
        });
        section.append(toggle);
      }
      body.append(section);
    });

    if (schema.sort && schema.sort.length) {
      const sortSection = el("section", "filter-panel-section filter-panel-sort");
      sortSection.append(el("h3", "filter-panel-section-title", "Sort"));
      const pick = el("select", "filter-sort");
      pick.id = "filter-panel-sort";
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Default";
      pick.append(blank);
      schema.sort.forEach((row) => {
        const opt = document.createElement("option");
        opt.value = row.value;
        opt.textContent = row.label || row.value;
        if (sel._sort === row.value) opt.selected = true;
        pick.append(opt);
      });
      pick.addEventListener("change", () => {
        draft = Object.assign({}, draft || {});
        if (!pick.value) delete draft._sort;
        else draft._sort = pick.value;
        if (selectionEmpty(draft)) draft = null;
      });
      sortSection.append(pick);
      body.append(sortSection);
    }
  }

  function toggleDraftValue(filterSpec, value) {
    const filterId = filterSpec.id;
    draft = Object.assign({}, draft || {});
    const row = Object.assign({ values: [] }, draft[filterId] || {});
    const multi = filterSpec.multi !== false;
    const idx = row.values.indexOf(value);
    if (idx === -1) {
      row.values = multi ? row.values.concat(value) : [value];
      if (filterSpec.match && !row.match) row.match = defaultMatchMode(filterSpec);
    } else {
      row.values = row.values.filter((v) => v !== value);
    }
    if (!row.values.length) delete draft[filterId];
    else draft[filterId] = row;
    if (selectionEmpty(draft)) draft = null;
    renderBody();
  }

  function setDraftMatch(filterId, mode) {
    if (!draft || !draft[filterId] || !draft[filterId].values.length) return;
    draft = Object.assign({}, draft);
    draft[filterId] = Object.assign({}, draft[filterId], { match: mode });
    renderBody();
  }

  function clearDraft() {
    draft = null;
    renderBody();
  }

  function updateChrome(appliedSelection) {
    const toggle = $("filter-toggle");
    const badge = $("filter-badge");
    const summary = $("filter-summary");
    const hasSchema = schema && schema.filters && schema.filters.length;
    if (toggle) {
      toggle.hidden = !hasSchema;
      toggle.setAttribute("aria-expanded", isOpen() ? "true" : "false");
    }
    const count = activeValueCount(appliedSelection);
    if (badge) {
      if (count > 0) {
        badge.hidden = false;
        badge.textContent = count > 99 ? "99+" : String(count);
      } else {
        badge.hidden = true;
        badge.textContent = "";
      }
    }
    const text = buildSummary(appliedSelection);
    if (summary) {
      if (text) {
        summary.hidden = false;
        summary.textContent = text;
        summary.setAttribute("aria-label", "Active filters: " + text);
      } else {
        summary.hidden = true;
        summary.textContent = "";
        summary.removeAttribute("aria-label");
      }
    }
  }

  function open(appliedSelection, onApply) {
    const panel = $("filter-panel");
    if (!panel || !schema) return;
    applyHandler = onApply;
    draft = deepCopySelection(appliedSelection);
    previouslyFocused = document.activeElement;
    renderBody();
    if (!panel.open) panel.showModal();
    attachFocusTrap(panel);
    const toggle = $("filter-toggle");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    const first = focusableIn(panel.querySelector(".filter-panel-inner"))[0];
    if (first) first.focus();
  }

  function close(discard) {
    const panel = $("filter-panel");
    if (!panel || !panel.open) return;
    panel.close();
    detachFocusTrap();
    draft = null;
    applyHandler = null;
    const toggle = $("filter-toggle");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    if (previouslyFocused && typeof previouslyFocused.focus === "function") {
      try {
        previouslyFocused.focus();
      } catch (_e) {
        /* ignore */
      }
    }
    previouslyFocused = null;
  }

  function isOpen() {
    const panel = $("filter-panel");
    return !!(panel && panel.open);
  }

  function setSchema(next) {
    schema = next && next.filters && next.filters.length ? next : null;
  }

  function init(handlers) {
    const panel = $("filter-panel");
    const toggle = $("filter-toggle");
    const summary = $("filter-summary");
    if (!panel || panel.dataset.filterPanelInit === "1") return;
    panel.dataset.filterPanelInit = "1";

    panel.addEventListener("click", (event) => {
      if (event.target === panel) close(true);
    });
    panel.addEventListener("cancel", (event) => {
      event.preventDefault();
      close(true);
    });

    const closeBtn = $("filter-panel-close");
    if (closeBtn) closeBtn.addEventListener("click", () => close(true));

    const applyBtn = $("filter-panel-apply");
    const clearBtn = $("filter-panel-clear");
    if (applyBtn) {
      applyBtn.addEventListener("click", () => {
        const next = deepCopySelection(draft);
        const fn = applyHandler || (handlers && handlers.onApply);
        close(true);
        if (fn) fn(next);
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", () => clearDraft());
    }
    if (toggle) {
      toggle.addEventListener("click", () => {
        if (isOpen()) close(true);
        else if (handlers && handlers.onOpen) handlers.onOpen();
      });
    }
    if (summary) {
      summary.addEventListener("click", () => {
        if (handlers && handlers.onOpen) handlers.onOpen();
      });
      summary.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (handlers && handlers.onOpen) handlers.onOpen();
        }
      });
    }

    panel.addEventListener("close", () => {
      detachFocusTrap();
      draft = null;
      applyHandler = null;
      const t = $("filter-toggle");
      if (t) t.setAttribute("aria-expanded", "false");
    });
  }

  /** Headless: panel body scrolls when many options. */
  function panelScrollMetrics() {
    const body = $("filter-panel-body");
    if (!body) return { ok: false, reason: "no-body" };
    return {
      ok: body.scrollHeight > body.clientHeight + 4,
      scrollHeight: body.scrollHeight,
      clientHeight: body.clientHeight,
    };
  }

  return {
    init,
    setSchema,
    updateChrome,
    open,
    close,
    isOpen,
    buildSummary,
    activeValueCount,
    panelScrollMetrics,
  };
})();
