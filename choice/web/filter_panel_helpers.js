/* Shared filter UI helpers (browser + node unit tests). */
(function (root) {
  function isMultiSelect(filterSpec) {
    if (!filterSpec) return true;
    if (filterSpec.mode === "single") return false;
    return filterSpec.multi !== false;
  }

  function optionMatchesQuery(opt, query) {
    const q = (query || "").trim().toLowerCase();
    if (!q) return true;
    const value = String(opt.value);
    const label = opt.label != null ? String(opt.label) : value;
    return label.toLowerCase().includes(q) || value.toLowerCase().includes(q);
  }

  function filterOptionsByQuery(options, query) {
    return (options || []).filter((opt) => optionMatchesQuery(opt, query));
  }

  function selectionEmpty(sel) {
    if (!sel) return true;
    return !Object.keys(sel).some((key) => {
      if (key === "_sort") return !!sel[key];
      const row = sel[key];
      return row && row.values && row.values.length;
    });
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

  root.ChoiceFilterHelpers = {
    isMultiSelect,
    optionMatchesQuery,
    filterOptionsByQuery,
    selectionEmpty,
    deepCopySelection,
    activeValueCount,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
