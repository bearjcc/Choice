/* Server Admin panel — forms driven by /api/admin/config-schema. */

async function ensureConfigSchema() {
  if (window.__choiceConfigSchema) return window.__choiceConfigSchema;
  const res = await api("/api/admin/config-schema");
  if (!res.ok) throw new Error(res.message || "schema");
  window.__choiceConfigSchema = res;
  return res;
}

function serverValuesFromApi(data) {
  const s = data.settings || {};
  return {
    title: data.app_title,
    state: {
      dir: data.state_dir || "",
      secrets_file: data.secrets_file || "",
      users_file: data.users_file || "",
    },
    client: { buffer: data.client_buffer || 30 },
    network: s.network || {},
    http: s.http || {},
    images: s.images || {},
  };
}

async function openServerAdminPanel() {
  const body = document.getElementById("dialog-body");
  if (!body) return;
  body.replaceChildren();
  body.append(el("h2", null, "Server admin"));
  let schema;
  let data;
  try {
    schema = await ensureConfigSchema();
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

  const form = el("div", "server-admin-form");
  const serverFields = (schema.fields || []).filter((f) => f.surface === "server");
  const bySection = {};
  serverFields.forEach((f) => {
    const sec = f.section || "general";
    if (!bySection[sec]) bySection[sec] = [];
    bySection[sec].push(f);
  });
  const values = serverValuesFromApi(data);
  const sectionTitles = {
    general: "General",
    state: "State & files",
    client: "Client",
    network: "Network",
    http: "HTTP",
    images: "Image delivery",
  };
  Object.keys(bySection).forEach((sec) => {
    const section = el("section", "admin-section");
    section.append(el("h3", null, sectionTitles[sec] || sec));
    ChoiceConfigUi.renderFields(bySection[sec], values, section, {
      codecs: data.codecs,
      hw_accel: data.hw_accel,
    });
    form.append(section);
  });

  const svc = el("section", "admin-section");
  svc.append(el("h3", null, "Service"));
  svc.append(
    el(
      "p",
      "fine",
      "Version " + (data.version || "?") + " · uptime " + Math.floor(data.uptime_sec || 0) + "s",
    ),
  );
  const restartBtn = el("button", "danger", "Restart Choice");
  restartBtn.type = "button";
  restartBtn.addEventListener("click", async () => {
    const ok = await ChoiceDialog.confirm("Restart Choice now?", {
      title: "Restart",
      confirmLabel: "Restart",
      cancelLabel: "Cancel",
    });
    if (!ok) return;
    try {
      await api("/api/admin/restart", { confirm: true });
    } catch (_e) {
      setStatus("Restart requested.");
    }
  });
  svc.append(restartBtn);
  form.append(svc);

  const sessSec = el("section", "admin-section");
  sessSec.append(el("h3", null, "Sessions"));
  const sessList = el("ul", "admin-session-list");
  sessSec.append(sessList);
  form.append(sessSec);

  const usersSec = el("section", "admin-section");
  usersSec.append(el("h3", null, "Users"));
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
  save.addEventListener("click", () => saveServerAdminForm(form, serverFields));
  actions.append(save);
  const previewBtn = el("button", null, "Test image settings");
  previewBtn.type = "button";
  previewBtn.addEventListener("click", () => testImageSettings(form, serverFields));
  actions.append(previewBtn);
  const close = el("button", null, "Close");
  close.addEventListener("click", () => ChoiceDialog.close());
  actions.append(close);
  body.append(actions);

  refreshSessions(sessList);
  ChoiceDialog.open();
}

async function saveServerAdminForm(form, fields) {
  const patch = ChoiceConfigUi.collectPatch(form, fields);
  let res = await api("/api/admin/server", { settings: patch });
  if (!res.ok && res.restart_required) {
    const ok = await ChoiceDialog.confirm(res.message || "Save and restart later?", {
      title: "Restart required",
      confirmLabel: "Save",
      cancelLabel: "Cancel",
    });
    if (!ok) return;
    res = await api("/api/admin/server", { settings: patch, confirm_restart: true });
  }
  if (!res.ok) {
    setStatus(res.message || "Could not save.");
    return;
  }
  setStatus(res.restart_required ? "Saved. Restart to apply network/state changes." : "Server settings saved.");
  ChoiceDialog.close();
}

async function testImageSettings(form, fields) {
  const patch = ChoiceConfigUi.collectPatch(form, fields);
  const sample = window.prompt("Path to a sample image on the server:");
  if (!sample) return;
  const res = await api("/api/admin/transcode-preview", {
    sample_path: sample,
    settings: patch.images || {},
  });
  setStatus(
    res.ok
      ? "Before " + res.original_bytes + " B → after " + res.output_bytes + " B"
      : res.message || "Preview failed.",
  );
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
    li.append(el("span", null, (row.user || "—") + " · " + (row.user_agent || "").slice(0, 48)));
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
