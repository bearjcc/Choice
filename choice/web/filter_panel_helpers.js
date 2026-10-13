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

  root.ChoiceFilterHelpers = {
    isMultiSelect,
    optionMatchesQuery,
    filterOptionsByQuery,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
