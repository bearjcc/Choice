/* Plugin filter flyout: draft selection, Apply/Clear, mobile sheet / desktop drawer. */

const ChoiceFilterPanel = (function () {
  const H = typeof ChoiceFilterHelpers !== "undefined" ? ChoiceFilterHelpers : null;

  let schema = null;
  let draft = null;
  let applyHandler = null;
  let previouslyFocused = null;
  let trapHandler = null;
  let vvUnsub = null;

  function isMultiSelect(filterSpec) {
    if (H) return H.isMultiSelect(filterSpec);
    if (!filterSpec) return true;
    if (filterSpec.mode === "single") return false;
    return filterSpec.multi !== false;
  }

  function filterOptionsByQuery(options, query) {
    if (H) return H.filterOptionsByQuery(options, query);
    const q = (query || "").trim().toLowerCase();
    if (!q) return options || [];
    return (options || []).filter((opt) => {
      const value = String(opt.value);
      const label = opt.label != null ? String(opt.label) : value;
      return label.toLowerCase().includes(q) || value.toLowerCase().includes(q);
    });
  }

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

  function setDraftValues(filterSpec, values) {
    const filterId = filterSpec.id;
    draft = Object.assign({}, draft || {});
    if (!values || !values.length) {
      delete draft[filterId];
    } else {
      const row = { values: values.slice() };
      if (filterSpec.match) row.match = (draft[filterId] && draft[filterId].match) || defaultMatchMode(filterSpec);
      draft[filterId] = row;
    }
    if (selectionEmpty(draft)) draft = null;
  }

  function appendMatchToggle(section, filterSpec, sel) {
    const modes = filterSpec.match;
    const hasValues =
      sel[filterSpec.id] && sel[filterSpec.id].values && sel[filterSpec.id].values.length;
    if (!Array.isArray(modes) || modes.length <= 1 || !hasValues) return;
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

  function renderMultiFilter(section, filterSpec, sel, options) {
    const searchInput = el("input", "filter-panel-search");
    searchInput.type = "search";
    searchInput.placeholder = "Search…";
    searchInput.setAttribute("aria-label", "Search " + (filterSpec.label || filterSpec.id));
    searchInput.autocomplete = "off";
    section.append(searchInput);

    const list = el("div", "filter-panel-option-list filter-panel-chips filter-panel-scroll");
    list.setAttribute("role", "group");
    list.setAttribute("aria-label", filterSpec.label || filterSpec.id);

    const renderList = (query) => {
      list.replaceChildren();
      const visible = filterOptionsByQuery(options, query);
      visible.forEach((opt) => {
        const value = String(opt.value);
        const label = opt.label || value;
        const active =
          sel[filterSpec.id] &&
          sel[filterSpec.id].values &&
          sel[filterSpec.id].values.indexOf(value) !== -1;
        const row = el("label", "filter-option-row" + (active ? " on" : ""));
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!active;
        cb.setAttribute("aria-label", label);
        const text = el("span", "filter-option-label", label);
        if (opt.count != null) text.title = String(opt.count);
        row.append(cb, text);
        row.addEventListener("click", (event) => {
          if (event.target === cb) return;
          event.preventDefault();
          toggleDraftValue(filterSpec, value);
        });
        cb.addEventListener("change", () => toggleDraftValue(filterSpec, value));
        list.append(row);
      });
      if (!visible.length) {
        list.append(el("p", "filter-panel-empty", "No matches"));
      }
    };
    renderList("");
    searchInput.addEventListener("input", () => renderList(searchInput.value));
    section.append(searchInput, list);
    appendMatchToggle(section, filterSpec, sel);
  }

  function renderSingleCombobox(section, filterSpec, sel, options) {
    const filterId = filterSpec.id;
    const listId = "filter-listbox-" + filterId;
    const selectedVal =
      sel[filterId] && sel[filterId].values && sel[filterId].values.length
        ? String(sel[filterId].values[0])
        : "";

    const wrap = el("div", "filter-combobox");
    const inputRow = el("div", "filter-combobox-input-row");

    const input = el("input", "filter-combobox-input filter-panel-search");
    input.type = "text";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", listId);
    input.placeholder = "Search or choose…";
    input.setAttribute("aria-label", filterSpec.label || filterId);
    input.autocomplete = "off";
    if (selectedVal) input.value = optionLabel(filterSpec, selectedVal);

    const clearBtn = el("button", "filter-combobox-clear");
    clearBtn.type = "button";
    clearBtn.setAttribute("aria-label", "Clear " + (filterSpec.label || filterId));
    clearBtn.textContent = "×";
    clearBtn.hidden = !selectedVal;

    inputRow.append(input, clearBtn);
    wrap.append(inputRow);

    const listbox = el("div", "filter-combobox-listbox");
    listbox.id = listId;
    listbox.setAttribute("role", "listbox");
    listbox.hidden = true;
    wrap.append(listbox);
    section.append(wrap);

    let activeIndex = -1;
    let queryOnFocus = "";

    function currentSelection() {
      const row = draft && draft[filterId];
      return row && row.values && row.values.length ? String(row.values[0]) : "";
    }

    function openList() {
      listbox.hidden = false;
      wrap.classList.add("is-open");
      input.setAttribute("aria-expanded", "true");
      if (typeof ChoiceVisualViewport !== "undefined") {
        ChoiceVisualViewport.apply();
      }
    }

    function closeList() {
      listbox.hidden = true;
      wrap.classList.remove("is-open");
      input.setAttribute("aria-expanded", "false");
      activeIndex = -1;
      input.removeAttribute("aria-activedescendant");
    }

    function renderOptions(query) {
      const visible = filterOptionsByQuery(options, query);
      listbox.replaceChildren();
      activeIndex = visible.length ? Math.min(activeIndex, visible.length - 1) : -1;
      visible.forEach((opt, idx) => {
        const value = String(opt.value);
        const label = opt.label || value;
        const optEl = el("div", "filter-combobox-option");
        optEl.id = listId + "-opt-" + idx;
        optEl.setAttribute("role", "option");
        optEl.setAttribute("aria-selected", value === currentSelection() ? "true" : "false");
        optEl.textContent = label;
        if (opt.count != null) optEl.title = String(opt.count);
        if (idx === activeIndex) {
          optEl.classList.add("active");
          input.setAttribute("aria-activedescendant", optEl.id);
        }
        optEl.addEventListener("mousedown", (event) => {
          event.preventDefault();
        });
        optEl.addEventListener("click", () => {
          pickValue(value);
        });
        listbox.append(optEl);
      });
      if (!visible.length) {
        listbox.append(el("p", "filter-panel-empty", "No matches"));
      }
      return visible;
    }

    function pickValue(value) {
      setDraftValues(filterSpec, value ? [value] : []);
      input.value = value ? optionLabel(filterSpec, value) : "";
      clearBtn.hidden = !value;
      closeList();
      const oldMatch = section.querySelector(".filter-match");
      if (oldMatch) oldMatch.remove();
      appendMatchToggle(section, filterSpec, draft || {});
    }

    function syncFromDraft() {
      const v = currentSelection();
      clearBtn.hidden = !v;
      if (document.activeElement !== input) {
        input.value = v ? optionLabel(filterSpec, v) : "";
      }
    }

    input.addEventListener("focus", () => {
      queryOnFocus = input.value;
      openList();
      renderOptions(input.value);
    });

    input.addEventListener("input", () => {
      openList();
      activeIndex = 0;
      renderOptions(input.value);
    });

    input.addEventListener("keydown", (event) => {
      const visible = filterOptionsByQuery(options, input.value);
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        input.value = currentSelection() ? optionLabel(filterSpec, currentSelection()) : "";
        closeList();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (listbox.hidden) openList();
        activeIndex = visible.length ? Math.min(activeIndex + 1, visible.length - 1) : -1;
        if (activeIndex < 0 && visible.length) activeIndex = 0;
        renderOptions(input.value);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (listbox.hidden) openList();
        activeIndex = visible.length ? Math.max(activeIndex - 1, 0) : -1;
        renderOptions(input.value);
        return;
      }
      if (event.key === "Enter") {
        if (listbox.hidden || activeIndex < 0 || !visible[activeIndex]) return;
        event.preventDefault();
        pickValue(String(visible[activeIndex].value));
        return;
      }
    });

    input.addEventListener("blur", () => {
      window.setTimeout(() => {
        if (!wrap.contains(document.activeElement)) {
          closeList();
          syncFromDraft();
        }
      }, 0);
    });

    clearBtn.addEventListener("click", () => {
      setDraftValues(filterSpec, []);
      input.value = "";
      clearBtn.hidden = true;
      closeList();
      const matchEl = section.querySelector(".filter-match");
      if (matchEl) matchEl.remove();
      input.focus();
    });

    appendMatchToggle(section, filterSpec, sel);
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
      if (isMultiSelect(filterSpec)) {
        renderMultiFilter(section, filterSpec, sel, options);
      } else {
        renderSingleCombobox(section, filterSpec, sel, options);
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
    const multi = isMultiSelect(filterSpec);
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
    if (typeof ChoiceVisualViewport !== "undefined") {
      if (vvUnsub) vvUnsub();
      vvUnsub = ChoiceVisualViewport.attach(() => {});
      requestAnimationFrame(() => ChoiceVisualViewport.apply());
    }
    attachFocusTrap(panel);
    const toggle = $("filter-toggle");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    const first = focusableIn(panel.querySelector(".filter-panel-inner"))[0];
    if (first) first.focus();
  }

  function close(discard) {
    const panel = $("filter-panel");
    if (!panel || !panel.open) return;
    detachFilterViewport();
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
      detachFilterViewport();
      detachFocusTrap();
      draft = null;
      applyHandler = null;
      const t = $("filter-toggle");
      if (t) t.setAttribute("aria-expanded", "false");
    });
  }

  function detachFilterViewport() {
    if (vvUnsub) {
      vvUnsub();
      vvUnsub = null;
    }
  }

  function keyboardLayoutMetrics() {
    const panel = $("filter-panel");
    const inner = panel && panel.querySelector(".filter-panel-inner");
    const vv = window.visualViewport;
    if (!panel || !panel.open || !inner || !vv) return null;

    const root = getComputedStyle(document.documentElement);
    const vvTopVar = parseFloat(root.getPropertyValue("--vv-top")) || vv.offsetTop;
    const vvHVar = parseFloat(root.getPropertyValue("--vv-h")) || vv.height;
    const vvBottom = vvTopVar + vvHVar;

    const innerRect = inner.getBoundingClientRect();
    const search = panel.querySelector(".filter-panel-search");
    const apply = document.getElementById("filter-panel-apply");
    const options = [...panel.querySelectorAll(".filter-option-row, .filter-combobox-option")].filter(
      (node) => node.offsetParent !== null && !node.closest("[hidden]")
    );

    const visibleOptions = options.filter((node) => {
      const r = node.getBoundingClientRect();
      return r.bottom > vvTopVar + 1 && r.top < vvBottom - 1 && r.height > 0;
    });

    const searchRect = search ? search.getBoundingClientRect() : null;
    const applyRect = apply ? apply.getBoundingClientRect() : null;
    const body = $("filter-panel-body");
    const bodyScrolls = body ? body.scrollHeight > body.clientHeight + 4 : false;

    return {
      narrow: window.matchMedia("(max-width: 699px)").matches,
      vvTop: vvTopVar,
      vvHeight: vvHVar,
      vvBottom,
      innerTop: innerRect.top,
      innerBottom: innerRect.bottom,
      innerHeight: innerRect.height,
      cssVarsSet: root.getPropertyValue("--vv-h").trim() !== "",
      searchVisible:
        searchRect &&
        searchRect.top >= vvTopVar - 2 &&
        searchRect.bottom <= vvBottom + 2,
      applyReachable:
        applyRect && applyRect.top < vvBottom - 2 && applyRect.bottom <= vvBottom + 4,
      visibleOptionCount: visibleOptions.length,
      topAnchored: innerRect.top <= vvTopVar + 24,
      heightFitsViewport: innerRect.height <= vvHVar + 4 && innerRect.height >= vvHVar * 0.75,
      bodyScrolls,
      nestedListScroll: [...panel.querySelectorAll(".filter-panel-option-list")].some(
        (el) => el.scrollHeight > el.clientHeight + 4
      ),
    };
  }

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
    keyboardLayoutMetrics,
    _helpers: { isMultiSelect, filterOptionsByQuery },
  };
})();
