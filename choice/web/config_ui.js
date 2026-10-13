/* Schema-driven admin fields (data-config-key must match choice/config_schema.py). */

const ChoiceConfigUi = (function () {
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function getByPath(obj, path) {
    const parts = path.split(".");
    let cur = obj;
    for (const p of parts) {
      if (cur == null) return undefined;
      cur = cur[p];
    }
    return cur;
  }

  function fieldWrap(field, control) {
    const wrap = el("label", "setup-field");
    wrap.dataset.configKey = field.key;
    wrap.append(el("span", "setup-label", field.label));
    let hint;
    if (field.help) {
      hint = el("span", "field-help", field.help);
      hint.id = "help-" + field.key.replace(/\./g, "-");
      wrap.append(hint);
    }
    control.setAttribute("data-config-key", field.key);
    if (hint) control.setAttribute("aria-describedby", hint.id);
    wrap.append(control);
    return wrap;
  }

  function buildControl(field, value, dynamicOptions) {
    const v = value !== undefined && value !== null ? value : field.default;
    if (field.type === "bool") {
      const row = el("label", "switch-row");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.className = "switch-input";
      input.checked = !!v;
      const track = el("span", "switch-track");
      track.append(el("span", "switch-thumb"));
      row.append(input, track, el("span", "switch-label", field.label));
      input.setAttribute("data-config-key", field.key);
      return row;
    }
    if (field.type === "select") {
      const sel = el("select", "setup-input");
      const opts = dynamicOptions || field.options || [];
      opts.forEach((row) => {
        const opt = document.createElement("option");
        opt.value = row.value;
        opt.textContent = row.label;
        if (String(row.value) === String(v)) opt.selected = true;
        sel.append(opt);
      });
      return sel;
    }
    if (field.type === "number") {
      const input = el("input", "setup-input");
      input.type = "number";
      input.value = v != null ? String(v) : "";
      return input;
    }
    if (field.type === "json") {
      const ta = el("textarea", "setup-input");
      ta.rows = 3;
      ta.value = v ? (typeof v === "string" ? v : JSON.stringify(v, null, 2)) : "";
      return ta;
    }
    const input = el("input", "setup-input");
    input.type = field.type === "secret" ? "password" : "text";
    if (field.type === "string_list") {
      input.value = Array.isArray(v) ? v.join(", ") : v || "";
      input.placeholder = "a, b, c";
    } else {
      input.value = v != null ? String(v) : "";
    }
    return input;
  }

  function renderFields(fields, values, parent, opts) {
    const basic = fields.filter((f) => !f.advanced);
    const advanced = fields.filter((f) => f.advanced);
    const renderList = (list, container) => {
      list.forEach((field) => {
        let dynamic;
        if (field.key === "images.format" && opts && opts.codecs) {
          dynamic = [
            { value: "original", label: "Original" },
            { value: "webp", label: "WebP" },
          ];
          if (opts.codecs.avif) dynamic.push({ value: "avif", label: "AVIF" });
          if (opts.codecs.jxl) dynamic.push({ value: "jxl", label: "JXL" });
        }
        if (field.key === "images.hw_accel" && opts && opts.hw_accel) {
          dynamic = (field.options || []).filter((row) => {
            if (row.value === "ffmpeg") return opts.hw_accel.ffmpeg;
            if (row.value === "vips") return opts.hw_accel.vips;
            return true;
          });
        }
        const val = valueForField(values, field);
        const control = buildControl(field, val, dynamic);
        if (field.type === "bool") container.append(control);
        else container.append(fieldWrap(field, control));
      });
    };
    renderList(basic, parent);
    if (advanced.length) {
      const details = el("details", "setup-more admin-advanced");
      details.append(el("summary", null, "Advanced"));
      renderList(advanced, details);
      parent.append(details);
    }
  }

  function valueForField(values, field) {
    if (field.key.startsWith("decks.")) {
      const short = field.key.slice(6);
      if (values.decks && short in values.decks) return values.decks[short];
    }
    return getByPath(values, field.key);
  }

  function readFieldValue(control, field) {
    if (field.type === "bool") return control.querySelector("input").checked;
    const input = control.matches("[data-config-key]") ? control : control.querySelector("[data-config-key]");
    if (!input) return null;
    if (field.type === "number") {
      const n = parseInt(input.value, 10);
      return Number.isFinite(n) ? n : field.default;
    }
    if (field.type === "string_list") {
      return String(input.value || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    }
    if (field.type === "json") {
      const raw = input.value.trim();
      if (!raw) return null;
      try {
        return JSON.parse(raw);
      } catch (_e) {
        return raw;
      }
    }
    return input.value;
  }

  function collectPatch(container, fields) {
    const patch = { title: undefined, state: {}, client: {}, network: {}, http: {}, images: {} };
    fields.forEach((field) => {
      const node = container.querySelector('[data-config-key="' + field.key + '"]');
      if (!node) return;
      const wrap = node.closest(".setup-field") || node;
      const val = readFieldValue(wrap.classList.contains("switch-row") ? wrap : wrap, field);
      if (field.key === "title") patch.title = val;
      else if (field.key.startsWith("state.")) patch.state[field.key.split(".")[1]] = val;
      else if (field.key.startsWith("client.")) patch.client[field.key.split(".")[1]] = val;
      else if (field.key.startsWith("network.")) patch.network[field.key.split(".")[1]] = val;
      else if (field.key.startsWith("http.")) patch.http[field.key.split(".")[1]] = val;
      else if (field.key.startsWith("images.")) patch.images[field.key.split(".")[1]] = val;
    });
    return patch;
  }

  function deckFieldsForType(schema, sourceType) {
    return (schema.fields || []).filter((f) => {
      if (f.surface !== "deck") return false;
      if (!f.source_types || !f.source_types.length) return true;
      return f.source_types.indexOf(sourceType) !== -1;
    });
  }

  function appendDeckFields(form, schema, existing, sourceType) {
    const fields = deckFieldsForType(schema, sourceType);
    if (!fields.length) return;
    const section = el("div", "deck-schema-fields");
    const values = { decks: {} };
    fields.forEach((f) => {
      const short = f.key.replace("decks.", "");
      values.decks[short] = existing ? existing[short] : undefined;
      values[f.key] = values.decks[short];
    });
    renderFields(fields, values, section, {});
    form.append(section);
  }

  function sourceFieldsForType(schema, sourceType) {
    return (schema.fields || []).filter((f) => {
      if (f.surface !== "source") return false;
      if (!f.source_types || !f.source_types.length) return true;
      return f.source_types.indexOf(sourceType) !== -1;
    });
  }

  function readDeckOptions(form, schema, sourceType) {
    const fields = deckFieldsForType(schema, sourceType);
    const out = {};
    fields.forEach((field) => {
      const node = form.querySelector('[data-config-key="' + field.key + '"]');
      if (!node) return;
      const wrap = node.closest(".setup-field") || node;
      const val = readFieldValue(wrap, field);
      const short = field.key.replace("decks.", "");
      if (val === "" || val === null || (Array.isArray(val) && !val.length)) return;
      out[short] = val;
    });
    return out;
  }

  function readSourceOptions(form, schema, sourceType) {
    const fields = sourceFieldsForType(schema, sourceType);
    const out = {};
    fields.forEach((field) => {
      if (field.type === "secret") return;
      const node = form.querySelector('[data-config-key="' + field.key + '"]');
      if (!node) return;
      const wrap = node.closest(".setup-field") || node.closest(".switch-row") || node;
      const val = readFieldValue(wrap, field);
      const short = field.key.replace("sources.", "");
      if (field.type === "bool") {
        out[short] = !!val;
        return;
      }
      if (val === "" || val === null || (Array.isArray(val) && !val.length)) return;
      out[short] = val;
    });
    return out;
  }

  return {
    renderFields,
    collectPatch,
    deckFieldsForType,
    sourceFieldsForType,
    appendDeckFields,
    readDeckOptions,
    readSourceOptions,
  };
})();
