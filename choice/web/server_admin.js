/* Server Admin panel (owner-only): network, service, users, sessions, HTTP, images. */

async function openServerAdminPanel() {
  const body = document.getElementById("dialog-body");
  if (!body) return;
  body.replaceChildren();
  body.append(el("h2", null, "Server admin"));
  let data;
  try {
    data = await api("/api/admin/server");
  } catch (_err) {
    body.append(el("p", "problem", "Could not reach Choice."));
    ChoiceDialog.open();
    return;
  }
  if (!data.ok) {
    body.append(el("p", "problem", data.message || "Server admin is unavailable."));
    ChoiceDialog.open();
    return;
  }
  const settings = data.settings || {};
  const net = settings.network || {};
  const http = settings.http || {};
  const images = settings.images || {};
  const form = el("div", "server-admin-form");

  const netSec = el("section", "admin-section");
  netSec.append(el("h3", null, "Network"));
  const host = fieldInput("Bind host", net.host || "127.0.0.1");
  const port = fieldInput("Port", String(net.port || 8741));
  const basePath = fieldInput("Base path", net.base_path || "");
  const publicUrl = fieldInput("Public URL", net.public_url || "");
  const tlsCert = fieldInput("TLS certificate path", net.tls_cert || "");
  const tlsKey = fieldInput("TLS key path", net.tls_key || "");
  const trustFwd = fieldCheckbox(
    "Behind reverse proxy (trust X-Forwarded-* headers)",
    !!net.trust_forwarded,
  );
  netSec.append(host.wrap, port.wrap, basePath.wrap, publicUrl.wrap, tlsCert.wrap, tlsKey.wrap, trustFwd.wrap);
  form.append(netSec);

  const svc = el("section", "admin-section");
  svc.append(el("h3", null, "Service"));
  svc.append(
    el(
      "p",
      "fine",
      "Version " +
        (data.version || "?") +
        " · uptime " +
        Math.floor(data.uptime_sec || 0) +
        "s",
    ),
  );
  const restartBtn = el("button", "danger", "Restart Choice");
  restartBtn.type = "button";
  restartBtn.addEventListener("click", async () => {
    const ok = await ChoiceDialog.confirm(
      "Restart Choice now? Active connections will drop briefly.",
      { title: "Restart", confirmLabel: "Restart", cancelLabel: "Cancel" },
    );
    if (!ok) return;
    try {
      await api("/api/admin/restart", { confirm: true });
    } catch (_e) {
      setStatus("Restart requested.");
    }
  });
  svc.append(restartBtn);
  form.append(svc);

  const httpSec = el("section", "admin-section");
  httpSec.append(el("h3", null, "HTTP"));
  const compress = fieldSelect("Compression", http.compress || "gzip", [
    ["off", "Off"],
    ["gzip", "Gzip"],
    ["brotli", "Brotli"],
    ["both", "Prefer Brotli, then Gzip"],
  ]);
  httpSec.append(compress.wrap);
  form.append(httpSec);

  const imgSec = el("section", "admin-section");
  imgSec.append(el("h3", null, "Image delivery"));
  const transcode = fieldCheckbox("Transcode on serve", !!images.transcode);
  const fmt = fieldSelect("Format", images.format || "original", formatOptions(data.codecs));
  const maxEdge = fieldInput("Max long edge (px)", String(images.max_edge || 2048));
  const quality = fieldInput("Quality", String(images.quality || 85));
  const minBytes = fieldInput("Min file size (bytes)", String(images.min_bytes || 0));
  const hw = fieldSelect("Hardware path", images.hw_accel || "auto", hwOptions(data.hw_accel));
  const hwNote = el("p", "fine", (data.hw_accel && data.hw_accel.note) || "");
  const previewBtn = el("button", null, "Test settings");
  previewBtn.type = "button";
  const previewOut = el("pre", "admin-preview", "");
  previewBtn.addEventListener("click", async () => {
    const sample = window.prompt("Path to a sample image on the server:");
    if (!sample) return;
    const patch = collectImageSettings(
      transcode,
      fmt,
      maxEdge,
      quality,
      minBytes,
      hw,
    );
    const res = await api("/api/admin/transcode-preview", {
      sample_path: sample,
      settings: patch,
    });
    previewOut.textContent = res.ok
      ? `Before: ${res.original_bytes} B → After: ${res.output_bytes} B (${res.format})`
      : res.message || "Preview failed.";
  });
  imgSec.append(
    transcode.wrap,
    fmt.wrap,
    maxEdge.wrap,
    quality.wrap,
    minBytes.wrap,
    hw.wrap,
    hwNote,
    previewBtn,
    previewOut,
  );
  form.append(imgSec);

  const sessSec = el("section", "admin-section");
  sessSec.append(el("h3", null, "Sessions"));
  const sessList = el("ul", "admin-session-list");
  sessSec.append(sessList);
  form.append(sessSec);

  const usersSec = el("section", "admin-section");
  usersSec.append(el("h3", null, "Users"));
  usersSec.append(el("p", "fine", "Manage people and owner in users.json."));
  const openPeople = el("button", null, "Open People manager");
  openPeople.type = "button";
  openPeople.addEventListener("click", () => {
    ChoiceDialog.close();
    showPeople();
  });
  usersSec.append(openPeople);
  form.append(usersSec);

  body.append(form);

  const actions = el("div", "sheet-actions");
  const save = el("button", "primary", "Save server settings");
  save.addEventListener("click", () => saveServerSettings(host, port, basePath, publicUrl, tlsCert, tlsKey, trustFwd, compress, transcode, fmt, maxEdge, quality, minBytes, hw));
  actions.append(save);
  const close = el("button", null, "Close");
  close.addEventListener("click", () => ChoiceDialog.close());
  actions.append(close);
  body.append(actions);

  refreshSessions(sessList);
  ChoiceDialog.open();
}

function formatOptions(codecs) {
  const opts = [["original", "Original"]];
  if (!codecs || codecs.webp) opts.push(["webp", "WebP"]);
  if (codecs && codecs.avif) opts.push(["avif", "AVIF"]);
  if (codecs && codecs.jxl) opts.push(["jxl", "JXL"]);
  return opts;
}

function hwOptions(status) {
  const rows = [
    ["auto", "Auto"],
    ["off", "CPU only (Pillow)"],
    ["pillow", "Pillow pool"],
  ];
  if (status && status.ffmpeg) rows.push(["ffmpeg", "ffmpeg CLI"]);
  if (status && status.vips) rows.push(["vips", "libvips"]);
  return rows;
}

function fieldInput(label, value) {
  const wrap = el("label", "setup-field");
  wrap.append(el("span", "setup-label", label));
  const input = el("input", "setup-input");
  input.type = "text";
  input.value = value;
  wrap.append(input);
  return { wrap, input };
}

function fieldCheckbox(label, checked) {
  const wrap = el("label", "setup-field checkbox-field");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = checked;
  wrap.append(input, document.createTextNode(" " + label));
  return { wrap, input };
}

function fieldSelect(label, value, options) {
  const wrap = el("label", "setup-field");
  wrap.append(el("span", "setup-label", label));
  const sel = el("select", "setup-input");
  options.forEach(([v, t]) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = t;
    if (v === value) opt.selected = true;
    sel.append(opt);
  });
  wrap.append(sel);
  return { wrap, sel };
}

function collectImageSettings(transcode, fmt, maxEdge, quality, minBytes, hw) {
  return {
    transcode: transcode.input.checked,
    format: fmt.sel.value,
    max_edge: parseInt(maxEdge.input.value, 10) || 2048,
    quality: parseInt(quality.input.value, 10) || 85,
    min_bytes: parseInt(minBytes.input.value, 10) || 0,
    hw_accel: hw.sel.value,
  };
}

async function saveServerSettings(host, port, basePath, publicUrl, tlsCert, tlsKey, trustFwd, compress, transcode, fmt, maxEdge, quality, minBytes, hw) {
  const settings = {
    network: {
      host: host.input.value.trim(),
      port: parseInt(port.input.value, 10) || 8741,
      base_path: basePath.input.value.trim(),
      public_url: publicUrl.input.value.trim(),
      tls_cert: tlsCert.input.value.trim(),
      tls_key: tlsKey.input.value.trim(),
      trust_forwarded: trustFwd.input.checked,
    },
    http: { compress: compress.sel.value },
    images: collectImageSettings(transcode, fmt, maxEdge, quality, minBytes, hw),
  };
  let res = await api("/api/admin/server", { settings });
  if (!res.ok && res.restart_required) {
    const ok = await ChoiceDialog.confirm(
      res.message || "Save and mark restart required?",
      { title: "Restart required", confirmLabel: "Save", cancelLabel: "Cancel" },
    );
    if (!ok) return;
    res = await api("/api/admin/server", { settings, confirm_restart: true });
  }
  if (!res.ok) {
    setStatus(res.message || "Could not save.");
    return;
  }
  setStatus(res.restart_required ? "Saved. Restart Choice to apply network changes." : "Server settings saved.");
  ChoiceDialog.close();
}

async function refreshSessions(list) {
  list.replaceChildren();
  let data;
  try {
    data = await api("/api/admin/sessions");
  } catch (_e) {
    list.append(el("li", null, "Could not load sessions."));
    return;
  }
  (data.sessions || []).forEach((row) => {
    const li = el("li", "admin-session-row");
    li.append(
      el(
        "span",
        null,
        (row.user || "—") + " · " + (row.user_agent || "").slice(0, 48),
      ),
    );
    const revoke = el("button", "danger", "Revoke");
    revoke.type = "button";
    revoke.addEventListener("click", async () => {
      await api("/api/admin/sessions/revoke", { session_id: row.id });
      refreshSessions(list);
    });
    li.append(revoke);
    list.append(li);
  });
  if (!list.childNodes.length) list.append(el("li", null, "No active sessions yet."));
}
