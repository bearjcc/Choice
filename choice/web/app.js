/* Choice page. One deck at a time. The server is the source of truth. */

const state = {
  index: null,
  deckId: null,
  mediaWidth: 1280,
  prefetchDeckId: null,
  pending: true,
  blind: false,
  payload: null,
  pos: 0,
  pageSize: 200,
  paged: null,
  queue: null,
  queuePoll: null,
  scanRetry: null,
  busy: false,
  user: localStorage.getItem("choice.user") || "",
  picking: false,
  galleryAt: {},
  anchorAfterLoad: null,
  lastSwipe: null,
};

const $ = (id) => document.getElementById(id);

function choiceBase() {
  const meta = document.querySelector('meta[name="choice-base"]');
  if (!meta) return "";
  const raw = meta.getAttribute("content") || "/";
  if (raw === "/") return "";
  return raw.replace(/\/$/, "");
}

function apiPath(path) {
  const lead = path.startsWith("/") ? path : "/" + path;
  const base = choiceBase();
  return (base || "") + lead;
}

function appRoot() {
  const base = choiceBase();
  return base ? base + "/" : "/";
}

function setAppSearch(query) {
  const qs = String(query || "").replace(/^\?/, "");
  const url = qs ? appRoot() + "?" + qs : appRoot();
  history.pushState(null, "", url);
}

function clearAppSearch() {
  if (!location.search) return;
  history.pushState(null, "", appRoot());
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function withUser(path) {
  if (!state.user) return path;
  const join = path.includes("?") ? "&" : "?";
  return path + join + "user=" + encodeURIComponent(state.user);
}

async function api(path, body) {
  const opts = {};
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers = { "Content-Type": "application/json" };
    const payload = state.user ? Object.assign({ user: state.user }, body) : body;
    opts.body = JSON.stringify(payload);
  }
  const res = await fetch(withUser(apiPath(path)), opts);
  let data = {};
  try {
    data = await res.json();
  } catch (_err) {
    data = {};
  }
  if (!res.ok && !data.message) data.message = "Choice returned " + res.status;
  if (!res.ok) data.ok = false;
  return data;
}

function setStatus(text) {
  $("status").hidden = false;
  $("status").textContent = text || "";
  const body = $("dialog-body");
  if (!ChoiceDialog.isOpen() || !body) return;
  let note = body.querySelector(".dialog-status");
  if (!text) {
    if (note) note.remove();
    return;
  }
  if (!note) {
    note = el("p", "warn dialog-status", text);
    body.prepend(note);
    return;
  }
  note.textContent = text;
}

function specs() {
  const payload = state.payload;
  if (!payload) return [];
  return (payload.directions || []).concat(payload.buttons || []);
}

function specFor(id) {
  return specs().find((spec) => spec.id === id) || null;
}

function buttonLabel(spec, item) {
  const offers = item && item.offers;
  if (offers && Object.prototype.hasOwnProperty.call(offers, spec.id)) {
    return offers[spec.id] || null;
  }
  return spec.label;
}

function callText(item) {
  if (!item) return "";
  return item.choice_label || item.choice || "";
}

function current() {
  const items = (state.payload && state.payload.items) || [];
  return items[state.pos] || null;
}

function inkOn(hex) {
  const raw = String(hex).replace("#", "");
  const full = raw.length === 3 ? raw.replace(/./g, (ch) => ch + ch) : raw;
  const n = Number.parseInt(full, 16);
  if (!Number.isFinite(n)) return "#fff";
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const y = (r * 299 + g * 587 + b * 114) / 1000;
  return y > 150 ? "#161616" : "#fff";
}

function reduceMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function isWide() {
  return window.matchMedia("(min-width: 700px)").matches;
}

function resolveSwipe(dx, dy, arm, threshold) {
  const a = arm == null ? 10 : arm;
  const t = threshold == null ? 88 : threshold;
  if (Math.abs(dx) < a && Math.abs(dy) < a) return null;
  if (Math.abs(dx) >= Math.abs(dy)) {
    if (Math.abs(dx) < t) return null;
    return dx > 0 ? "right" : "left";
  }
  if (Math.abs(dy) < t) return null;
  return dy < 0 ? "up" : "down";
}

function slugTitle(title) {
  const text = String(title || "").trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return text || "deck";
}

function sourceIcon(type) {
  const map = {
    folder: "folder",
    swipe: "layers",
    swipe_plugin: "layers",
    immich: "cloud",
    rss: "feed",
    atom: "feed",
    webdav: "remote",
  };
  return map[type] || "deck";
}

function iconPath(kind) {
  const paths = {
    folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z",
    layers: "M12 3 3 8l9 5 9-5-9-5zm0 7 3-1.7v3.4L12 16l-9-5v3.4l9 5 9-5v-3.4L12 10z",
    cloud: "M7 18a4 4 0 1 1 .9-7.9A5 5 0 0 1 19 10a3 3 0 0 1 0 6H7z",
    feed: "M4 11a8 8 0 0 1 8 8M4 4a16 16 0 0 1 16 16M5 19a1 1 0 1 1-2 0 1 1 0 0 1 2 0z",
    remote: "M4 6h16v12H4zM8 10h8M8 14h5",
    deck: "M5 5h14v14H5z",
  };
  return paths[kind] || paths.deck;
}

function appendSourceIcon(parent, type) {
  const kind = sourceIcon(type);
  const wrap = el("span", "deck-icon");
  wrap.setAttribute("aria-hidden", "true");
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "deck-icon-svg");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.75");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("d", iconPath(kind));
  svg.append(path);
  wrap.append(svg);
  parent.append(wrap);
  return wrap;
}

async function boot() {
  $("home").addEventListener("click", () => {
    if (state.picking) return backFromPeople();
    showLibrary();
  });
  $("who").addEventListener("click", showPeople);
  $("pending").addEventListener("click", togglePending);
  $("blind").addEventListener("click", toggleBlind);
  $("counts").addEventListener("click", openCounts);
  $("menu").addEventListener("click", openMenu);
  $("queue-badge").addEventListener("click", openQueueFailures);
  ChoiceDialog.init();
  document.addEventListener("keydown", onKey);
  window.addEventListener("popstate", route);
  updateMediaWidth();
  window.addEventListener("resize", updateMediaWidth);
  try {
    state.index = await api("/api/index");
  } catch (_err) {
    return showProblem("Could not reach Choice.");
  }
  if (peopleOn() && state.user && !currentPerson()) {
    state.user = "";
    localStorage.removeItem("choice.user");
    try {
      state.index = await api("/api/index");
    } catch (_err) {
      return showProblem("Could not reach Choice.");
    }
  }
  route();
}

function route() {
  state.picking = false;
  const wanted = new URLSearchParams(location.search).get("deck");
  if (!state.index || !state.index.ok) {
    showProblem((state.index && state.index.message) || "Nothing to swipe.");
    return;
  }
  if (peopleOn() && !currentPerson()) return showPeople();
  if (new URLSearchParams(location.search).get("setup") === "1") {
    return api("/api/config").then((cfg) => {
      if (cfg.ok && cfg.editable) showSetup(cfg);
      else showLibrary();
    });
  }
  if (wanted) return openDeck(wanted, false);
  const decks = state.index.decks || [];
  if (state.index.direct && decks.length === 1 && !decks[0].error) return openDeck(decks[0].id, false);
  showLibrary();
}

function showProblem(message) {
  state.picking = false;
  stopQueuePoll();
  $("title").textContent = "Choice";
  $("tools").hidden = true;
  $("track").hidden = true;
  $("actions").hidden = true;
  $("menu").hidden = false;
  $("count").textContent = "";
  paintWho();
  setStatus("");
  $("status").hidden = true;
  const box = el("div", "empty");
  box.append(el("h2", null, "Cannot open this pile"));
  box.append(el("p", null, message));
  $("main").replaceChildren(box);
}

async function showLibrary() {
  stopQueuePoll();
  state.deckId = null;
  state.payload = null;
  state.paged = null;
  if (location.search) clearAppSearch();
  state.picking = false;
  try {
    const index = await api("/api/index");
    if (!index.ok) return showProblem(index.message || "Nothing to swipe.");
    state.index = index;
  } catch (_err) {
    return showProblem("Could not reach Choice.");
  }
  $("title").textContent = "Choice";
  $("count").textContent = "";
  $("tools").hidden = true;
  $("track").hidden = true;
  $("actions").hidden = true;
  $("menu").hidden = false;
  paintWho();
  $("status").textContent = "";
  $("status").hidden = true;
  const list = el("ul", "library");
  const deckRows =
    state.index.decks && state.index.decks.length
      ? state.index.decks
      : state.index.library || [];
  deckRows.forEach((deck) => {
    const item = el("li");
    if (deck.error) {
      item.append(el("strong", null, deck.title));
      item.append(el("p", "problem", deck.error));
      list.append(item);
      return;
    }
    const card = el("button", "deck-card deck-link");
    card.type = "button";
    const copy = el("span", "deck-copy");
    copy.append(el("span", "deck-name", deck.title));
    let meta = deck.count_label;
    if (!meta && deck.meter === false) meta = deck.count_label || "";
    else if (!meta && deck.stale && deck.left == null) meta = "Scanning…";
    else if (!meta && deck.stale && deck.left != null) meta = deck.left + " left · scanning";
    else if (!meta && deck.left != null) meta = deck.left + " left";
    copy.append(el("span", "deck-meta deck-meta" + (deck.stale ? " stale" : ""), meta || ""));
    const row = el("span", "deck-row");
    appendSourceIcon(row, deck.source_type || "deck");
    row.append(copy);
    card.append(row);
    let pressTimer = null;
    let longPressed = false;
    card.addEventListener("pointerdown", () => {
      prefetchDeckItems(deck.id);
      longPressed = false;
      pressTimer = window.setTimeout(() => {
        pressTimer = null;
        longPressed = true;
        openDeckEdit(deck.id);
      }, 520);
    });
    const clearPress = () => {
      if (pressTimer) {
        clearTimeout(pressTimer);
        pressTimer = null;
      }
    };
    card.addEventListener("pointerup", clearPress);
    card.addEventListener("pointercancel", clearPress);
    card.addEventListener("pointerleave", clearPress);
    card.addEventListener("click", () => {
      if (longPressed) {
        longPressed = false;
        return;
      }
      openDeck(deck.id, true);
    });
    const more = el("button", "deck-more", "...");
    more.type = "button";
    more.setAttribute("aria-label", "Edit deck");
    more.dataset.choiceModal = "deck-edit";
    more.addEventListener("click", (event) => {
      event.stopPropagation();
      openDeckEdit(deck.id);
    });
    item.append(card, more);
    list.append(item);
  });
  const parts = [];
  (state.index.warnings || []).forEach((warning) => parts.push(el("p", "warn", warning)));
  if (!list.childNodes.length) {
    const box = el("div", "empty");
    const person = currentPerson();
    box.append(el("h2", null, "No decks"));
    box.append(el("p", null, person
      ? person.name + " has no decks yet. Open People and tick the ones they should see."
      : "Add a folder with deck.json, or point Choice at a photo folder."));
    parts.push(box);
  } else {
    parts.push(list);
  }
  parts.push(licenceLine());
  setupLink(parts);
  $("main").replaceChildren(...parts);
}

async function setupLink(parts) {
  let cfg = null;
  try {
    cfg = await api("/api/config");
  } catch (_err) {
    return;
  }
  if (!cfg.ok || !cfg.editable) return;
  const wrap = el("div", "setup-link");
  const btn = el("button", null, "Sources and decks");
  btn.type = "button";
  btn.addEventListener("click", () => showSetup(cfg));
  btn.dataset.choiceModal = "add-deck";
  wrap.append(btn);
  parts.push(wrap);
}

function showSetup(cfg, editDeckId) {
  state.deckId = null;
  $("title").textContent = editDeckId ? "Edit deck" : "Add deck";
  $("tools").hidden = true;
  $("track").hidden = true;
  $("actions").hidden = true;
  $("menu").hidden = false;
  const wizard = { step: 1, type: "folder", cfg, editDeckId: editDeckId || null, preview: [] };
  const existing = editDeckId ? (cfg.decks || []).find((d) => d.id === editDeckId) : null;
  if (existing) {
    const src = (cfg.sources || []).find((s) => s.id === existing.source);
    wizard.type = src ? src.type : "folder";
    wizard.step = 2;
  }
  if (!ChoiceDialog.isOpen() && state.index && state.index.ok) {
    const onDeck = $("main").querySelector("article.card");
    if (!onDeck) showLibrary();
  }
  openSetupDialog(wizard);
  setStatus("");
}

function openSetupDialog(wizard) {
  wizard._dialog = true;
  paintSetupStep(wizard);
  ChoiceDialog.open();
}

function openDeckEdit(deckId) {
  api("/api/config").then((cfg) => {
    if (cfg.ok && cfg.editable) showSetup(cfg, deckId);
  });
}

const SETUP_TYPES = [
  { type: "folder", label: "Folder", hint: "Local photos or deck.json" },
  { type: "immich", label: "Immich", hint: "Album or search" },
  { type: "rss", label: "RSS", hint: "Feed items" },
  { type: "webdav", label: "WebDAV", hint: "Remote folder" },
  { type: "swipe", label: "Swipe deck", hint: "deck.py plugin" },
];

function paintSetupStep(wizard) {
  const root = el("div", "setup-wizard");
  root.append(el("p", "setup-step", "Step " + wizard.step + " of 3"));
  if (wizard.step === 1) root.append(setupStepType(wizard));
  else if (wizard.step === 2) root.append(setupStepFields(wizard));
  else root.append(setupStepSave(wizard));
  if (wizard._dialog) {
    const body = $("dialog-body");
    body.replaceChildren(root);
    ChoiceDialog.syncViewport();
    return;
  }
  $("main").replaceChildren(root);
}

function setupStepType(wizard) {
  const wrap = el("div", "setup-tiles");
  wrap.append(el("h2", null, "Source type"));
  const grid = el("div", "tile-grid");
  SETUP_TYPES.forEach((row) => {
    const btn = el("button", "type-tile" + (wizard.type === row.type ? " picked" : ""));
    btn.type = "button";
    btn.append(el("span", "tile-label", row.label));
    btn.append(el("span", "tile-hint", row.hint));
    btn.addEventListener("click", () => {
      wizard.type = row.type;
      wizard.step = 2;
      paintSetupStep(wizard);
    });
    grid.append(btn);
  });
  wrap.append(grid);
  return wrap;
}

function toggleSwitch(name, label, on) {
  const row = el("label", "switch-row");
  const input = el("input");
  input.type = "checkbox";
  input.name = name;
  input.checked = !!on;
  input.className = "switch-input";
  const track = el("span", "switch-track");
  track.append(el("span", "switch-thumb"));
  row.append(input, track, el("span", "switch-label", label));
  return row;
}

function setupStepFields(wizard) {
  const form = el("form", "setup-form");
  form.addEventListener("submit", (event) => event.preventDefault());
  const existing = wizard.editDeckId
    ? (wizard.cfg.decks || []).find((d) => d.id === wizard.editDeckId)
    : null;
  const srcExisting = existing
    ? (wizard.cfg.sources || []).find((s) => s.id === existing.source)
    : null;

  form.append(fieldLabel("Deck title"));
  const titleInput = el("input");
  titleInput.name = "title";
  titleInput.required = true;
  titleInput.value = existing ? existing.title : "";
  form.append(titleInput);

  const fields = el("div", "setup-type-fields");
  if (wizard.type === "folder") {
    form.append(fieldLabel("Folder path"));
    const pathRow = el("div", "path-row");
    const mount = el("input");
    mount.name = "mount";
    mount.placeholder = ".";
    mount.value = existing ? (existing.mount || ".") : ".";
    mount.setAttribute("list", "browse-list");
    pathRow.append(mount);
    const browse = el("button", "path-browse", "Browse");
    browse.type = "button";
    browse.addEventListener("click", () => openBrowsePicker(mount, wizard));
    pathRow.append(browse);
    form.append(pathRow);
    const datalist = el("datalist");
    datalist.id = "browse-list";
    form.append(datalist);
    loadBrowseHints(datalist, wizard, mount.value);

    const output = el("select");
    output.name = "output";
    [["results", "Results (log only)"], ["sort", "Sort into folders"]].forEach(([value, label]) => {
      const opt = el("option", null, label);
      opt.value = value;
      if (existing && existing.output === value) opt.selected = true;
      output.append(opt);
    });
    form.append(fieldLabel("Output"));
    form.append(output);
    form.append(toggleSwitch("recursive", "Recursive scan", existing && existing.recursive));

    const more = el("details", "setup-more");
    more.append(el("summary", null, "More options"));
    const include = el("input");
    include.name = "include";
    include.placeholder = "*.jpg, *.png";
    if (existing && existing.include) include.value = existing.include.join(", ");
    more.append(fieldLabel("Include globs"), include);
    const exclude = el("input");
    exclude.name = "exclude";
    if (existing && existing.exclude) exclude.value = existing.exclude.join(", ");
    more.append(fieldLabel("Exclude globs"), exclude);
    const sortRight = el("input");
    sortRight.name = "sort_right";
    if (existing && existing.sort_right) sortRight.value = existing.sort_right;
    more.append(fieldLabel("Sort folder: right"), sortRight);
    const sortLeft = el("input");
    sortLeft.name = "sort_left";
    if (existing && existing.sort_left) sortLeft.value = existing.sort_left;
    more.append(fieldLabel("Sort folder: left"), sortLeft);
    form.append(more);
  } else if (wizard.type === "immich") {
    form.append(fieldLabel("Immich URL"));
    const url = el("input");
    url.name = "url";
    url.placeholder = "https://photos.example.com";
    if (srcExisting && srcExisting.url) url.value = srcExisting.url;
    form.append(url);
    form.append(fieldLabel("API key (stored as secret)"));
    const key = el("input");
    key.type = "password";
    key.name = "api_key";
    key.autocomplete = "off";
    form.append(key);
    form.append(fieldLabel("Album id or search mount"));
    const mount = el("input");
    mount.name = "mount";
    mount.value = existing ? (existing.mount || "") : "";
    form.append(mount);
  } else if (wizard.type === "rss") {
    form.append(fieldLabel("Feed URL"));
    const feed = el("input");
    feed.name = "url";
    if (srcExisting && srcExisting.url) feed.value = srcExisting.url;
    form.append(feed);
  } else if (wizard.type === "webdav") {
    form.append(fieldLabel("WebDAV URL"));
    const url = el("input");
    url.name = "url";
    if (srcExisting && srcExisting.url) url.value = srcExisting.url;
    form.append(url);
    form.append(fieldLabel("Username"));
    const user = el("input");
    user.name = "username";
    if (srcExisting && srcExisting.username) user.value = srcExisting.username;
    form.append(user);
    form.append(fieldLabel("Password"));
    const pass = el("input");
    pass.type = "password";
    pass.name = "password";
    pass.autocomplete = "off";
    form.append(pass);
    form.append(fieldLabel("Remote folder"));
    const mount = el("input");
    mount.name = "mount";
    mount.value = existing ? (existing.mount || "/") : "/";
    form.append(mount);
  } else if (wizard.type === "swipe") {
    form.append(fieldLabel("Plugin folder path"));
    const plug = el("input");
    plug.name = "path";
    if (srcExisting && srcExisting.path) plug.value = srcExisting.path;
    form.append(plug);
    form.append(fieldLabel("Deck mount within plugin"));
    const mount = el("input");
    mount.name = "mount";
    mount.value = existing ? (existing.mount || ".") : ".";
    form.append(mount);
  }
  form.append(fields);

  const nav = el("div", "setup-nav");
  const back = el("button", null, "Back");
  back.type = "button";
  back.addEventListener("click", () => {
    if (wizard.editDeckId) {
      ChoiceDialog.close();
      return showLibrary();
    }
    wizard.step = 1;
    paintSetupStep(wizard);
  });
  const next = el("button", null, "Continue");
  next.type = "button";
  next.addEventListener("click", () => {
    if (!titleInput.value.trim()) return setStatus("Title is required.");
    wizard.step = 3;
    wizard.draft = readSetupDraft(form, wizard);
    paintSetupStep(wizard);
    runSetupTest(wizard);
  });
  nav.append(back, next);
  form.append(nav);
  return form;
}

function readSetupDraft(form, wizard) {
  const title = form.querySelector("[name=title]").value.trim();
  const id = wizard.editDeckId || slugTitle(title);
  const sourceId = wizard.editDeckId
    ? ((wizard.cfg.decks || []).find((d) => d.id === wizard.editDeckId) || {}).source
    : slugTitle(title + "-src");
  const draft = { id, title, sourceId, type: wizard.type, mount: ".", source: { type: wizard.type, id: sourceId } };
  const mountEl = form.querySelector("[name=mount]");
  if (mountEl) draft.mount = mountEl.value.trim() || ".";
  if (wizard.type === "folder") {
    const output = form.querySelector("[name=output]");
    draft.output = output ? output.value : "results";
    const rec = form.querySelector("[name=recursive]");
    draft.recursive = rec ? rec.checked : false;
    draft.include = splitGlobs((form.querySelector("[name=include]") || {}).value);
    draft.exclude = splitGlobs((form.querySelector("[name=exclude]") || {}).value);
    draft.sort_right = (form.querySelector("[name=sort_right]") || {}).value.trim();
    draft.sort_left = (form.querySelector("[name=sort_left]") || {}).value.trim();
    draft.source.path = ".";
    draft.source.output = draft.output;
    draft.source.recursive = draft.recursive;
  }
  if (wizard.type === "immich") {
    draft.source.url = form.querySelector("[name=url]").value.trim();
    draft.api_key = form.querySelector("[name=api_key]").value;
    draft.secret_name = "IMMICH_API_KEY";
  }
  if (wizard.type === "rss") draft.source.url = form.querySelector("[name=url]").value.trim();
  if (wizard.type === "webdav") {
    draft.source.url = form.querySelector("[name=url]").value.trim();
    draft.source.username = form.querySelector("[name=username]").value.trim();
    draft.password = form.querySelector("[name=password]").value;
  }
  if (wizard.type === "swipe") {
    draft.source.path = form.querySelector("[name=path]").value.trim();
  }
  return draft;
}

async function loadBrowseHints(datalist, wizard, path) {
  try {
    const res = await api("/api/browse");
    if (!res.ok || !res.roots || !res.roots.length) return;
    const source = res.roots[0].source;
    const sub = await api("/api/browse?source=" + encodeURIComponent(source) + "&path=" + encodeURIComponent(path || ""));
    if (!sub.ok || !sub.entries) return;
    datalist.replaceChildren();
    sub.entries.forEach((entry) => {
      const opt = el("option");
      opt.value = entry.path;
      datalist.append(opt);
    });
  } catch (_err) {
    return;
  }
}

function openBrowsePicker(mountInput, wizard) {
  const body = $("dialog-body");
  body.replaceChildren();
  body.append(el("h2", null, "Choose folder"));
  const list = el("ul", "browse-list");
  body.append(list);
  const close = el("button", null, "Close");
  close.addEventListener("click", () => ChoiceDialog.close());
  body.append(close);
  ChoiceDialog.open();
  api("/api/browse").then((res) => {
    if (!res.ok || !res.roots || !res.roots.length) {
      list.append(el("li", null, "No folder sources in config yet."));
      return;
    }
    const source = res.roots[0].source;
    const loadPath = (sub) => {
      list.replaceChildren();
      api("/api/browse?source=" + encodeURIComponent(source) + "&path=" + encodeURIComponent(sub || "")).then((data) => {
        if (!data.ok) {
          list.append(el("li", null, data.message || "Could not list."));
          return;
        }
        if (sub) {
          const up = el("li");
          const upBtn = el("button", null, "..");
          upBtn.type = "button";
          upBtn.addEventListener("click", () => {
            const parts = sub.split("/").filter(Boolean);
            parts.pop();
            loadPath(parts.join("/"));
          });
          up.append(upBtn);
          list.append(up);
        }
        const pick = el("li");
        const pickBtn = el("button", null, "Use " + (sub || "."));
        pickBtn.type = "button";
        pickBtn.addEventListener("click", () => {
          mountInput.value = sub || ".";
          ChoiceDialog.close();
        });
        pick.append(pickBtn);
        list.append(pick);
        (data.entries || []).forEach((entry) => {
          const li = el("li");
          const btn = el("button", null, entry.name + "/");
          btn.type = "button";
          btn.addEventListener("click", () => loadPath(entry.path));
          li.append(btn);
          list.append(li);
        });
      });
    };
    loadPath(mountInput.value === "." ? "" : mountInput.value);
  });
}

function setupStepSave(wizard) {
  const wrap = el("div", "setup-review");
  wrap.append(el("h2", null, wizard.draft.title));
  wrap.append(el("p", "fine", "Id: " + wizard.draft.id));
  const preview = el("ul", "preview-list");
  preview.id = "setup-preview";
  wrap.append(preview);
  const testBtn = el("button", null, "Test again");
  testBtn.type = "button";
  testBtn.addEventListener("click", () => runSetupTest(wizard));
  const saveBtn = el("button", "primary", "Save");
  saveBtn.type = "button";
  saveBtn.addEventListener("click", () => saveSetupDeck(wizard));
  if (wizard.editDeckId) {
    const removeBtn = el("button", null, "Remove from Choice");
    removeBtn.type = "button";
    removeBtn.addEventListener("click", () => removeSetupDeck(wizard));
    wrap.append(removeBtn);
  }
  const back = el("button", null, "Back");
  back.type = "button";
  back.addEventListener("click", () => {
    wizard.step = 2;
    paintSetupStep(wizard);
  });
  const nav = el("div", "setup-nav");
  nav.append(back, testBtn, saveBtn);
  wrap.append(nav);
  return wrap;
}

async function runSetupTest(wizard) {
  const draft = wizard.draft;
  if (!draft) return;
  const sourcePayload = Object.assign({ type: draft.type }, draft.source);
  if (draft.type === "folder") {
    sourcePayload.recursive = draft.recursive;
    sourcePayload.include = draft.include;
    sourcePayload.exclude = draft.exclude;
    sourcePayload.output = draft.output;
  }
  const res = await api("/api/sources/test", { mount: draft.mount, source: sourcePayload });
  const list = document.getElementById("setup-preview");
  if (!list) return;
  list.replaceChildren();
  if (!res.ok) {
    list.append(el("li", "problem", res.message || "Test failed."));
    setStatus(res.message || "Test failed.");
    return;
  }
  setStatus(res.message || "OK");
  (res.preview || []).slice(0, 3).forEach((row) => {
    const li = el("li");
    li.append(el("strong", null, row.title));
    if (row.body) li.append(el("span", "fine", " " + row.body.slice(0, 80)));
    list.append(li);
  });
  wizard.preview = res.preview || [];
}

async function removeSetupDeck(wizard) {
  const cfg = wizard.cfg;
  const deckId = wizard.editDeckId;
  if (!deckId) return;
  const okRemove = await ChoiceDialog.confirm(
    "Remove this deck from Choice? Files and state stay on disk.",
    { title: "Remove deck", confirmLabel: "Remove", cancelLabel: "Cancel" },
  );
  if (!okRemove) return;
  const removed = (cfg.decks || []).find((d) => d.id === deckId);
  const decks = (cfg.decks || []).filter((d) => d.id !== deckId);
  const sources = (cfg.sources || []).filter((s) => {
    if (!removed || s.id !== removed.source) return true;
    return decks.some((d) => d.source === s.id);
  });
  const res = await api("/api/config", { sources, decks });
  if (!res.ok) return setStatus(res.message || "Could not save.");
  setStatus("Deck removed.");
  await refreshIndex();
  if (ChoiceDialog.isOpen()) ChoiceDialog.close();
  showLibrary();
}

async function saveSetupDeck(wizard) {
  const draft = wizard.draft;
  if (!draft) return;
  const cfg = wizard.cfg;
  const sources = (cfg.sources || []).filter((s) => s.id !== draft.sourceId);
  const srcRow = Object.assign({ id: draft.sourceId, type: draft.type }, draft.source);
  if (draft.type === "folder") {
    srcRow.path = srcRow.path || ".";
  }
  sources.push(srcRow);
  const decks = (cfg.decks || []).filter((d) => d.id !== draft.id);
  const entry = {
    id: draft.id,
    title: draft.title,
    source: draft.sourceId,
    mount: draft.mount,
  };
  if (draft.type === "folder") {
    entry.output = draft.output;
    entry.recursive = draft.recursive;
    if (draft.include.length) entry.include = draft.include;
    if (draft.exclude.length) entry.exclude = draft.exclude;
    if (draft.sort_right) entry.sort_right = draft.sort_right;
    if (draft.sort_left) entry.sort_left = draft.sort_left;
  }
  decks.push(entry);
  if (draft.api_key && draft.secret_name) {
    const sec = await api("/api/secrets", { name: draft.secret_name, value: draft.api_key });
    if (!sec.ok) return setStatus(sec.message || "Could not store secret.");
  }
  if (draft.password) {
    const sec = await api("/api/secrets", { name: "WEBDAV_PASSWORD", value: draft.password });
    if (!sec.ok) return setStatus(sec.message || "Could not store secret.");
  }
  const res = await api("/api/config", { sources, decks });
  if (!res.ok) return setStatus(res.message || "Could not save.");
  setStatus("Saved.");
  await refreshIndex();
  if (ChoiceDialog.isOpen()) ChoiceDialog.close();
  showLibrary();
}

function fieldLabel(text) {
  const label = el("label", "setup-label", text);
  return label;
}

function appendSetupField(parent, labelText, controlEl) {
  const wrap = el("div", "setup-field");
  wrap.append(el("label", "setup-label", labelText), controlEl);
  parent.append(wrap);
  return wrap;
}

function displayRandomSeed(prefs, view, deckId) {
  const defaults = (view && view.defaults) || {};
  const autoSeed = defaults.random_seed || deckId || "";
  const stored = (prefs && prefs.random_seed) || "";
  if (!stored || stored === autoSeed) return "";
  return stored;
}

function newRandomSeed() {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function splitGlobs(text) {
  return String(text || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function openDeck(id, push) {
  updateMediaWidth();
  state.deckId = id;
  state.pos = 0;
  $("status").textContent = "";
  const stored = localStorage.getItem(blindKey(id));
  const deck = (state.index.decks || []).find((row) => row.id === id);
  if (deck && deck.error) return showProblem(deck.error);
  if (push) setAppSearch("deck=" + encodeURIComponent(id));
  const ok = await loadItems(stored);
  if (ok) {
    startQueuePoll();
    renderDeck();
  }
}

function itemsApiPath(cursor, limit) {
  const w = state.mediaWidth || 1280;
  let path =
    "/api/decks/" +
    encodeURIComponent(state.deckId) +
    "/items?pending=" +
    (state.pending ? "1" : "0") +
    "&limit=" +
    limit +
    "&w=" +
    w;
  if (cursor) path += "&after=" + encodeURIComponent(cursor);
  return path;
}

function applyPagedMeta(data) {
  const n = (data.items || []).length;
  state.paged = {
    nextAfter: data.next_after || null,
    hasMore: !!data.next_after,
    loading: false,
  };
}

async function ensureCardsAhead() {
  const minAhead = 3;
  const items = (state.payload && state.payload.items) || [];
  if (!state.paged || !state.paged.hasMore || state.paged.loading) return false;
  if (items.length - state.pos >= minAhead) return false;
  const anchorId = anchorItemId();
  state.paged.loading = true;
  let added = false;
  try {
    const data = await api(itemsApiPath(state.paged.nextAfter, state.pageSize));
    if (!data.ok || !data.items || !data.items.length) {
      state.paged.hasMore = false;
      return false;
    }
    const seen = new Set(items.map((row) => row.id));
    data.items.forEach((row) => {
      if (!seen.has(row.id)) {
        items.push(row);
        seen.add(row.id);
        added = true;
      }
    });
    state.paged.nextAfter = data.next_after || null;
    state.paged.hasMore = !!data.next_after;
    state.payload.left = data.left;
    state.payload.total = data.total;
    state.payload.decided = data.decided;
    if (anchorId) state.anchorAfterLoad = anchorId;
    applyPosAnchor(items);
    return added;
  } catch (_err) {
    return false;
  } finally {
    state.paged.loading = false;
  }
}

function stopQueuePoll() {
  if (state.queuePoll) clearInterval(state.queuePoll);
  state.queuePoll = null;
  state.queue = null;
  const badge = $("queue-badge");
  if (badge) badge.hidden = true;
}

function startQueuePoll() {
  stopQueuePoll();
  refreshQueueBadge();
  state.queuePoll = setInterval(refreshQueueBadge, 3000);
}

async function refreshQueueBadge() {
  if (!state.deckId) return;
  try {
    const data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/stats");
    if (!data.ok || !data.stats) return;
    state.queue = data.stats.queue || null;
    paintQueueBadge();
  } catch (_err) {
    /* offline */
  }
}

function paintQueueBadge() {
  const btn = $("queue-badge");
  if (!btn) return;
  const q = state.queue;
  const pending = (q && q.pending) || 0;
  const failed = (q && q.failed) || 0;
  if (!pending && !failed) {
    btn.hidden = true;
    return;
  }
  btn.hidden = false;
  btn.classList.toggle("has-failed", failed > 0);
  const running = (q && q.running) || 0;
  const active = pending + running;
  const parts = [];
  if (active) {
    const label = active === 1 ? "1 move pending or retrying" : active + " moves pending or retrying";
    parts.push(label);
  }
  if (failed) parts.push(failed + " failed");
  btn.textContent = parts.join(" · ");
}

function openQueueFailures() {
  const q = state.queue;
  const failures = (q && q.failures) || [];
  if (!failures.length) {
    if (q && q.failed) setStatus(q.failed + " move(s) failed.");
    return;
  }
  const body = $("dialog-body");
  body.replaceChildren();
  body.append(el("h2", null, "Queue failures"));
  failures.forEach((row) => {
    const label = row.from || row.item || row.id;
    body.append(el("p", "warn", label + ": " + (row.error || "Failed")));
  });
  const close = el("button", null, "Close");
  close.addEventListener("click", () => ChoiceDialog.close());
  body.append(close);
  ChoiceDialog.open();
}

function pileNav() {
  return typeof ChoicePileNav !== "undefined" ? ChoicePileNav : null;
}

function anchorItemId() {
  if (state.anchorAfterLoad) return state.anchorAfterLoad;
  const item = current();
  return item ? item.id : null;
}

function applyPosAnchor(items) {
  const nav = pileNav();
  if (!nav) {
    if (state.pos >= items.length) state.pos = 0;
    return;
  }
  state.pos = nav.syncPosToAnchor(items, state.pos, anchorItemId());
  state.anchorAfterLoad = null;
}

async function loadItems(storedBlind) {
  const anchorId = anchorItemId();
  let data;
  try {
    updateMediaWidth();
    data = await api(itemsApiPath(null, state.pageSize));
  } catch (_err) {
    return showProblem("Could not reach Choice.");
  }
  if (!data.ok) {
    showProblem(data.message || "Could not read this deck.");
    return false;
  }
  state.payload = data;
  applyPagedMeta(data);
  if (storedBlind !== undefined) {
    state.blind = storedBlind === null ? !!data.blind : storedBlind === "1";
  }
  if (anchorId) state.anchorAfterLoad = anchorId;
  applyPosAnchor(data.items || []);
  return true;
}

function renderDeck() {
  state.picking = false;
  clearScanRetry();
  const data = state.payload;
  paintWho();
  $("title").textContent = data.title;
  $("tools").hidden = true;
  $("menu").hidden = false;
  $("count").textContent = data.count_label || (data.left != null ? data.left + " left" : "");
  $("pending").textContent = state.pending ? "Show all" : "Still to do";
  $("blind").setAttribute("aria-pressed", state.blind ? "true" : "false");
  $("track").hidden = data.meter === false;
  const pct = data.total ? (100 * data.decided) / data.total : 0;
  $("fill").style.width = data.meter === false ? "0%" : pct + "%";
  $("track").setAttribute("aria-valuenow", String(data.decided));
  $("track").setAttribute("aria-valuemax", String(data.total));
  const aria = data.count_label
    || (data.total != null ? data.decided + " of " + data.total + " decided" : "");
  $("track").setAttribute("aria-label", aria);
  renderActions();
  let item = current();
  if (!item && state.paged && state.paged.hasMore) {
    ensureCardsAhead().then((added) => {
      if (added && current()) renderDeck();
      else if (!current()) renderEmpty();
    });
    return;
  }
  if (!item) return renderEmpty();
  $("status").hidden = false;
  const card = el("article", "card" + (item.kind === "image" ? " image" : ""));
  card.tabIndex = 0;
  if (data.warnings && data.warnings.length) {
    const wrap = el("div", "stack");
    if (item.kind === "pair") {
      wrap.classList.add("wide");
      if ((item.sides || []).some((side) => side.media)) wrap.classList.add("has-media");
    }
    data.warnings.forEach((warning) => wrap.append(el("p", "warn", warning)));
    wrap.append(card);
    $("main").replaceChildren(wrap);
  } else {
    $("main").replaceChildren(card);
  }
  paintCard(card, item);
  bindDrag(card, item);
  preloadMedia();
  renderActions();
  applyDemoDrag(card);
  ensureCardsAhead().then((added) => {
    if (added && current()) renderDeck();
  });
}

function applyDemoDrag(card) {
  const demo = new URLSearchParams(location.search).get("demo");
  if (!demo || !card) return;
  const side = demo === "drag" ? "right" : demo;
  if (!["left", "right", "up", "down"].includes(side)) return;
  const spec = specFor(side);
  const label = spec && buttonLabel(spec, current());
  const hint = card.querySelector(".drag-hint");
  const hintLabel = hint && hint.querySelector(".drag-hint-label");
  if (hint && hintLabel && label) {
    hint.hidden = false;
    hintLabel.textContent = label;
  }
  card.style.setProperty("--drag-tint", hintTint(side));
  const dx = side === "right" ? 72 : side === "left" ? -72 : 0;
  const dy = side === "up" ? -72 : side === "down" ? 72 : 0;
  card.style.transform = "translate(" + dx + "px," + dy + "px) rotate(" + (dx / 12) + "deg)";
}

function preloadMedia() {
  const items = (state.payload && state.payload.items) || [];
  const urls = [];
  for (let i = 0; i < 3 && i < items.length; i++) {
    const row = items[(state.pos + i) % items.length];
    if (!row) continue;
    if (row.kind === "gallery" && row.images) {
      const gi = galleryIndex(row);
      const slide = row.images[gi] || row.images[0];
      if (slide) urls.push(mediaSrc(row, null, slide.index));
    } else if (row.kind === "image" && row.media) urls.push(mediaSrc(row, null));
    if (row.kind === "pair" && row.sides) {
      row.sides.forEach((side) => {
        if (side.media) urls.push(mediaSrc(row, side));
      });
    }
  }
  urls.forEach((url) => {
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    if (img.decode) {
      img.decode().catch(() => {});
    }
  });
}

function prefetchDeckItems(deckId) {
  if (!deckId || state.prefetchDeckId === deckId) return;
  state.prefetchDeckId = deckId;
  const w = state.mediaWidth || 1280;
  api("/api/decks/" + encodeURIComponent(deckId) + "/items?pending=1&limit=3&w=" + w).catch(() => {});
}

function cardLabel(item, fallback) {
  if (state.blind) return fallback || "Card";
  const text = (item.title || "").trim();
  return text || fallback || "Card";
}

function hasCardTitle(item) {
  return !!(item.title && String(item.title).trim());
}

function paintCard(card, item) {
  if (item.kind === "pair" && item.sides && item.sides.length) {
    paintPair(card, item);
    return;
  }
  if (item.kind === "gallery" && item.images && item.images.length) {
    paintGallery(card, item);
    return;
  }
  const showTitle =
    hasCardTitle(item) &&
    (item.kind !== "image" || !state.blind) &&
    (item.kind !== "file" || hasCardTitle(item));
  if (item.kind === "image" && item.media) {
    const frame = el("div", "frame");
    appendPhoto(frame, mediaSrc(item, null), cardLabel(item, "Photo"));
    const cap = el("div", "cap");
    if (item.body) cap.append(el("p", "body", item.body));
    const call = callText(item);
    if (call) cap.append(el("p", "fine", "Your call: " + call));
    appendMark(cap, item);
    appendChips(cap, item);
    card.append(frame);
    if (cap.childNodes.length) card.append(cap);
    return;
  }
  if (showTitle || item.body || callText(item) || item.mark) {
    const pad = el("div", "pad");
    if (showTitle) pad.append(el("h2", null, item.title));
    if (item.body) pad.append(el("p", "body", item.body));
    const call = callText(item);
    if (call) pad.append(el("p", "fine", "Your call: " + call));
    appendMark(pad, item);
    card.append(pad);
  }
  appendChips(card, item);
}

function galleryIndex(item) {
  const at = state.galleryAt[item.id];
  if (at == null || at < 0) return 0;
  if (!item.images || at >= item.images.length) return 0;
  return at;
}

function setGalleryIndex(item, idx) {
  if (!item.images || !item.images.length) return;
  const n = ((idx % item.images.length) + item.images.length) % item.images.length;
  state.galleryAt[item.id] = n;
  renderDeck();
}

function paintGallery(card, item) {
  card.classList.add("gallery-card");
  const idx = galleryIndex(item);
  const frame = el("div", "frame gallery");
  const imgWrap = el("div", "gallery-view");
  imgWrap.addEventListener("pointerdown", (event) => event.stopPropagation());
  const slide = item.images[idx];
  appendPhoto(imgWrap, mediaSrc(item, null, slide.index), slide.caption || cardLabel(item, "Photo"));
  if (item.images.length > 1) {
    const dots = el("div", "gallery-dots");
    dots.setAttribute("role", "tablist");
    item.images.forEach((row, i) => {
      const dot = el("button", "gallery-dot" + (i === idx ? " on" : ""), String(i + 1));
      dot.type = "button";
      dot.setAttribute("aria-label", "Photo " + (i + 1));
      dot.addEventListener("click", (event) => {
        event.stopPropagation();
        setGalleryIndex(item, i);
      });
      dots.append(dot);
    });
    imgWrap.append(dots);
  }
  frame.append(imgWrap);
  const cap = el("div", "cap");
  const showTitle = hasCardTitle(item) && (!state.blind || !item.body);
  if (showTitle) cap.append(el("h2", null, item.title));
  if (item.body) cap.append(el("p", "body", item.body));
  if (slide.caption) cap.append(el("p", "fine", slide.caption));
  const call = callText(item);
  if (call) cap.append(el("p", "fine", "Your call: " + call));
  appendMark(cap, item);
  appendChips(cap, item);
  if (cap.childNodes.length) frame.append(cap);
  card.append(frame);
  appendChips(card, item);
}

function pairLayoutMode() {
  const layout = (state.payload && state.payload.pair_layout) || "auto";
  if (layout === "stack") return "stack";
  if (layout === "side_by_side") return "side";
  return isWide() ? "side" : "stack";
}

function paintPair(card, item) {
  const media = item.sides.some((side) => side.media);
  const layout = pairLayoutMode();
  card.classList.add("pair");
  if (media) card.classList.add("has-media");
  if (layout === "stack") card.classList.add("pair-stack");
  if (layout === "side") card.classList.add("pair-side-by-side");
  if (item.title || item.body || callText(item) || item.mark) {
    const pad = el("div", "pad");
    if (item.title) pad.append(el("h2", null, item.title));
    if (item.body) pad.append(el("p", "body", item.body));
    const call = callText(item);
    if (call) pad.append(el("p", "fine", "Your call: " + call));
    appendMark(pad, item);
    card.append(pad);
  }
  const sides = el("div", media ? "sides media" : "sides");
  if (layout === "stack") sides.classList.add("stacked");
  item.sides.forEach((side, index) => {
    const pane = el("section", side.media ? "side has-media" : "side");
    if (layout === "stack") pane.classList.add(index === 0 ? "stack-top" : "stack-under");
    pane.setAttribute("role", "button");
    pane.tabIndex = 0;
    const pick = side.key === "b" ? "right" : "left";
    pane.addEventListener("click", () => act(pick));
    pane.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        act(pick);
      }
    });
    if (side.media) {
      const frame = el("div", "frame");
      appendPhoto(frame, mediaSrc(item, side), sideLabel(side));
      frame.append(el("h3", "side-label", sideLabel(side)));
      pane.append(frame);
      if (side.body) pane.append(el("p", "body side-note", side.body));
    } else {
      pane.append(el("h3", "side-label", sideLabel(side)));
      if (side.body) pane.append(el("p", "body", side.body));
    }
    sides.append(pane);
  });
  card.append(sides);
  appendChips(card, item);
}

function appendMark(parent, item) {
  if (!item.mark) return;
  const word = item.mark === "right" ? "Correct" : "Missed";
  const note = item.mark_note ? " (" + item.mark_note + ")" : "";
  parent.append(el("p", "fine", word + note));
}

function sideLabel(side) {
  if (side.label) return side.label;
  return side.key === "b" ? "B" : "A";
}

function updateMediaWidth() {
  const css = Math.min(window.innerWidth || 400, 520);
  const dpr = window.devicePixelRatio || 1;
  const raw = Math.round(css * dpr);
  const buckets = [640, 960, 1280, 1600];
  let pick = buckets[0];
  buckets.forEach((b) => {
    if (raw >= b) pick = b;
  });
  state.mediaWidth = pick;
}

function mediaSrc(item, side, imageIndex) {
  let url = apiPath("/api/decks/" + encodeURIComponent(state.deckId) + "/media?item=" + encodeURIComponent(item.id));
  if (side) url += "&side=" + encodeURIComponent(side.key);
  let token = side ? side.media_token : item.media_token;
  if (imageIndex != null && item.images) {
    const row = item.images.find((r) => r.index === imageIndex) || item.images[imageIndex];
    if (row) {
      token = row.media_token || token;
      url += "&n=" + encodeURIComponent(String(row.index != null ? row.index : imageIndex));
    }
  }
  url += "&w=" + encodeURIComponent(String(state.mediaWidth || 1280));
  return withUser(url + "&v=" + encodeURIComponent(token || ""));
}

function appendPhoto(frame, src, alt) {
  const img = el("img");
  img.alt = alt;
  img.src = src;
  img.draggable = false;
  frame.append(img);
}

function appendChips(parent, item) {
  if (state.blind || !item.chips || !item.chips.length) return;
  const row = el("div", "chips");
  item.chips.forEach((chip) => row.append(el("span", "chip", chip.label + ": " + chip.text)));
  parent.append(row);
}

function clearScanRetry() {
  if (state.scanRetry) {
    clearTimeout(state.scanRetry);
    state.scanRetry = null;
  }
}

function scheduleScanRetry() {
  clearScanRetry();
  state.scanRetry = setTimeout(() => {
    state.scanRetry = null;
    loadItems().then((ok) => {
      if (ok) renderDeck();
    });
  }, 800);
}

function renderEmpty() {
  const data = state.payload;
  clearScanRetry();
  if (data.scanning) {
    const box = el("div", "empty");
    box.append(el("h2", null, "Scanning…"));
    box.append(el("p", null, "The folder changed. Updating the pile."));
    $("main").replaceChildren(box);
    $("actions").hidden = true;
    scheduleScanRetry();
    return;
  }
  const box = el("div", "empty");
  if (data.report) {
    box.classList.add("report");
    appendReport(box, data.report);
  } else if (!data.total) {
    box.append(el("h2", null, "No cards"));
    box.append(el("p", null, "This pile is empty. Add files or rows, then reload."));
  } else {
    box.append(el("h2", null, "Nothing left"));
    box.append(el("p", null, data.decided + " decided."));
  }
  if (data.decided && data.replay !== false) {
    const button = el("button", null, "Review them");
    button.addEventListener("click", async () => {
      state.pending = false;
      if (await loadItems()) renderDeck();
    });
    box.append(button);
  }
  $("main").replaceChildren(box);
  $("actions").hidden = true;
}

function appendReport(box, report) {
  box.append(el("h2", null, report.heading || ""));
  if (report.detail) {
    box.append(el("p", report.kind === "story" ? "ending" : null, report.detail));
  }
  if (report.places && report.places.length) {
    const list = el("ol", "places");
    report.places.forEach((row) => {
      const li = el("li");
      li.append(el("span", "place", row.place));
      li.append(el("span", "who", row.name));
      if (row.note) li.append(el("span", "result-note", row.note));
      list.append(li);
    });
    box.append(list);
  }
  if (report.kind === "story" && report.lines && report.lines.length) {
    box.append(el("p", "fine way", "The way here"));
  }
  if (report.lines && report.lines.length) {
    const list = el("ul", "results");
    report.lines.forEach((row) => {
      const li = el("li", row.mark || "");
      if (row.mark === "right") li.append(el("span", "mark", "Correct"));
      else if (row.mark === "wrong") li.append(el("span", "mark", "Missed"));
      li.append(el("span", "who", row.text || ""));
      if (row.note) li.append(el("span", "result-note", row.note));
      list.append(li);
    });
    box.append(list);
  }
}

function undoEnabled() {
  return !!(state.payload && state.payload.allow_undo !== false);
}

function renderActions() {
  const row = $("actions");
  const item = current();
  const onDeck = !!(state.deckId && state.payload);
  row.hidden = !onDeck;
  row.replaceChildren();
  if (!onDeck) return;
  if (item) {
    ["left", "down", "up", "right"].forEach((id) => {
      const spec = specFor(id);
      if (!spec) return;
      const label = buttonLabel(spec, item);
      if (!label) return;
      row.append(actionButton(spec, label));
    });
    (state.payload.buttons || []).forEach((spec) => row.append(actionButton(spec, spec.label)));
  }
  if (undoEnabled()) {
    const undo = el("button", "action-undo", "Undo");
    undo.type = "button";
    undo.disabled = !state.payload.can_undo || state.busy;
    undo.addEventListener("click", () => undoLast());
    row.append(undo);
  }
}

function actionButton(spec, label) {
  const button = el("button", null, label || spec.label);
  button.dataset.dir = spec.id;
  if (spec.color) {
    button.style.background = spec.color;
    button.style.borderColor = spec.color;
    button.style.color = inkOn(spec.color);
  }
  button.disabled = state.busy;
  button.addEventListener("click", () => act(spec.id));
  return button;
}

function bindDrag(card, item) {
  let drag = null;
  const pairMobile = item && item.kind === "pair" && pairLayoutMode() === "stack";
  const hint = el("div", "drag-hint");
  const hintLabel = el("span", "drag-hint-label");
  hint.append(hintLabel);
  hint.hidden = true;
  card.append(hint);
  card.style.touchAction = "none";

  card.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || state.busy) return;
    if (event.target.closest(".side")) return;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, on: false };
  });
  card.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.on) {
      if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return;
      drag.on = true;
      card.setPointerCapture(event.pointerId);
    }
    const side = resolveSwipe(dx, dy, 10, 40);
    if (reduceMotion()) return;
    const rot = pairMobile ? 0 : Math.max(-8, Math.min(8, dx / 40));
    card.style.transform = "translate(" + dx + "px," + dy + "px) rotate(" + rot + "deg)";
    const armed = resolveSwipe(dx, dy);
    const pick = pairMobile ? (armed === "up" ? "up" : null) : armed;
    const spec = pick ? specFor(pick) : null;
    const label = spec && buttonLabel(spec, current());
    hint.hidden = !label;
    if (label) {
      hint.dataset.dir = pick;
      hintLabel.textContent = label;
      card.style.setProperty("--drag-tint", hintTint(pick));
    } else {
      card.style.removeProperty("--drag-tint");
    }
  });
  const finish = (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    let side = resolveSwipe(dx, dy);
    if (pairMobile) side = side === "up" ? "up" : null;
    const spec = side ? specFor(side) : null;
    const armed = drag.on && side && spec && buttonLabel(spec, current());
    drag = null;
    hint.hidden = true;
    card.style.removeProperty("--drag-tint");
    if (armed) {
      flingCard(card, side);
      act(side);
      return;
    }
    card.style.transition = reduceMotion() ? "" : "transform 180ms ease-out";
    card.style.transform = "";
  };
  card.addEventListener("pointerup", finish);
  card.addEventListener("pointercancel", finish);
}

function hintTint(dir) {
  const map = { right: "var(--drag-yes)", left: "var(--drag-no)", up: "var(--drag-fav)", down: "var(--drag-skip)" };
  return map[dir] || "transparent";
}

function flingCard(card, direction) {
  if (!card || reduceMotion()) {
    if (card) card.style.transform = "";
    return;
  }
  const dx = direction === "right" ? "120%" : direction === "left" ? "-120%" : "0";
  const dy = direction === "up" ? "-120%" : direction === "down" ? "120%" : "0";
  const rot = direction === "right" ? 8 : direction === "left" ? -8 : 0;
  card.style.transition = "transform 180ms ease-out";
  card.style.transform = "translate(" + dx + "," + dy + ") rotate(" + rot + "deg)";
}

function unflingCard(card, direction) {
  if (!card || reduceMotion()) {
    if (card) card.style.transform = "";
    return;
  }
  const dx = direction === "right" ? "120%" : direction === "left" ? "-120%" : "0";
  const dy = direction === "up" ? "-120%" : direction === "down" ? "120%" : "0";
  const rot = direction === "right" ? 8 : direction === "left" ? -8 : 0;
  card.style.transition = "none";
  card.style.transform = "translate(" + dx + "," + dy + ") rotate(" + rot + "deg)";
  requestAnimationFrame(() => {
    card.style.transition = "transform 180ms ease-out";
    card.style.transform = "";
  });
}

function itemFromUndoHint(hint) {
  if (hint && hint.card) return hint.card;
  if (hint && hint._item) return hint._item;
  if (!hint || !hint.item) return null;
  return {
    id: hint.item,
    title: hint.file || hint.label || hint.item,
    kind: "file",
  };
}

function buildUndoHint() {
  const hint = state.payload && state.payload.undo_hint;
  if (hint && hint.item) return hint;
  if (state.lastSwipe && state.lastSwipe.item) {
    return {
      item: state.lastSwipe.item.id,
      direction: state.lastSwipe.direction,
      later: !!state.lastSwipe.later,
      _item: state.lastSwipe.item,
    };
  }
  return null;
}

function applyOptimisticUndo(hint) {
  const restored = itemFromUndoHint(hint);
  if (!restored || !state.payload) return;
  const items = state.payload.items || [];
  const nav = pileNav();
  state.anchorAfterLoad = restored.id;
  const later = !!hint.later;
  if (state.pending && !later) {
    if (nav) {
      const next = nav.restorePendingUndo(items, state.pos, restored);
      state.payload.items = next.items;
      state.pos = next.pos;
    } else {
      const idx = items.findIndex((row) => row.id === restored.id);
      if (idx === -1) items.splice(state.pos, 0, restored);
      state.pos = items.findIndex((row) => row.id === restored.id);
    }
  } else if (nav) {
    state.pos = nav.syncPosToAnchor(items, state.pos, restored.id);
  } else {
    const idx = items.findIndex((row) => row.id === restored.id);
    state.pos = idx >= 0 ? idx : state.pos;
  }
  if (typeof state.payload.decided === "number") {
    state.payload.decided = Math.max(0, state.payload.decided - 1);
  }
  if (typeof state.payload.left === "number") state.payload.left += 1;
  state.payload.can_undo = false;
}

function advanceAfterSwipe(itemId, later) {
  const items = (state.payload && state.payload.items) || [];
  if (!items.length) return;
  const nav = pileNav();
  if (later || !state.pending) {
    state.pos = nav
      ? nav.advanceShowAllPos(items, state.pos, itemId)
      : (() => {
          const idx = items.findIndex((row) => row.id === itemId);
          return idx === -1 ? 0 : (idx + 1) % items.length;
        })();
    return;
  }
  if (nav) {
    const next = nav.removePendingSwipe(items, state.pos, itemId);
    state.payload.items = next.items;
    state.pos = next.pos;
  } else {
    const idx = items.findIndex((row) => row.id === itemId);
    if (idx !== -1) items.splice(idx, 1);
    if (state.pos >= items.length) state.pos = Math.max(0, items.length - 1);
  }
  ensureCardsAhead();
}

async function act(direction) {
  const spec = specFor(direction);
  const item = current();
  const label = spec && item ? buttonLabel(spec, item) : null;
  if (!spec || !item || !label || state.busy) return;
  if (ChoiceDialog.isOpen()) ChoiceDialog.close();
  state.busy = true;
  renderActions();
  const card = document.querySelector(".card");
  if (card && !card.style.transition) flingCard(card, direction);
  const snapshot = state.payload;
  const itemId = item.id;
  const later = !!spec.later;
  state.lastSwipe = { item: { ...item }, direction, later };
  advanceAfterSwipe(itemId, later);
  if (!reduceMotion()) await wait(40);
  state.busy = false;
  renderDeck();
  let data;
  try {
    data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/decide", {
      item: item.id,
      direction: direction,
      deck_id: state.deckId,
    });
  } catch (_err) {
    data = { ok: false, message: "Could not reach Choice." };
  }
  if (!data.ok) {
    state.payload = snapshot;
    state.pos = (snapshot.items || []).findIndex((row) => row.id === itemId);
    if (state.pos < 0) state.pos = 0;
    renderDeck();
    setStatus(data.message || "Not saved");
    return;
  }
  setStatus(data.message || label);
  loadItems().then((ok) => {
    if (ok) {
      refreshQueueBadge();
      renderDeck();
    }
  });
}

async function runPluginAction(spec) {
  if (!spec || !spec.id || state.busy) return;
  if (spec.confirm) {
    const ok = await ChoiceDialog.confirm(spec.label + "?", {
      title: spec.label,
      confirmLabel: "Continue",
      cancelLabel: "Cancel",
    });
    if (!ok) return;
  }
  state.busy = true;
  let data;
  try {
    data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/action", {
      action: spec.id,
    });
  } catch (_err) {
    data = { ok: false, message: "Could not reach Choice." };
  }
  state.busy = false;
  if (!data.ok) {
    setStatus(data.message || "Action failed");
    return;
  }
  setStatus(data.message || "Done");
  if (await loadItems()) renderDeck();
}

async function undoLast() {
  if (state.busy || !undoEnabled() || !state.payload || !state.payload.can_undo) return;
  const hint = buildUndoHint();
  if (!hint || !hint.item) return;
  const direction = hint.direction || "right";
  const snapshot = {
    payload: {
      ...state.payload,
      items: (state.payload.items || []).slice(),
    },
    pos: state.pos,
    lastSwipe: state.lastSwipe,
  };
  applyOptimisticUndo(hint);
  state.busy = true;
  renderActions();
  renderDeck();
  const card = document.querySelector(".card");
  unflingCard(card, direction);
  if (!reduceMotion()) await wait(40);
  state.busy = false;
  renderActions();
  let data;
  try {
    data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/undo", {});
  } catch (_err) {
    data = { ok: false, message: "Could not reach Choice." };
  }
  if (!data.ok) {
    state.payload = snapshot.payload;
    state.pos = snapshot.pos;
    state.lastSwipe = snapshot.lastSwipe;
    renderDeck();
    setStatus(data.message || "Undo failed");
    renderActions();
    return;
  }
  if (data.item) state.anchorAfterLoad = data.item;
  setStatus(data.message || "");
  const ok = await loadItems();
  if (ok) renderDeck();
  else renderActions();
}

async function openMenu() {
  const body = $("dialog-body");
  body.replaceChildren();
  body.append(el("h2", null, "Menu"));
  const list = el("div", "menu-list");
  const add = (label, fn, modalId, opts = {}) => {
    const btn = el("button", "menu-item", label);
    btn.type = "button";
    if (modalId) btn.dataset.choiceModal = modalId;
    btn.addEventListener("click", async () => {
      if (!opts.keepDialog) ChoiceDialog.close();
      await fn();
    });
    list.append(btn);
  };
  if (state.deckId && state.payload) {
    add(state.pending ? "Show all" : "Still to do", togglePending, null);
    add(state.blind ? "Blind off" : "Blind on", toggleBlind, null);
    if (state.payload.view && !state.payload.view.locked) {
      add("Order and filter", openOrderSettings, "order-settings", { keepDialog: true });
    }
    add("Count display", openCountSettings, "count-settings", { keepDialog: true });
    add("Counts", openCounts, "counts", { keepDialog: true });
  }
  if (peopleOn()) add("People", showPeople, "people");
  const decks = (state.index && state.index.decks) || [];
  if (!state.deckId || decks.length > 1) add("Decks", () => showLibrary(), null);
  try {
    const cfg = await api("/api/config");
    if (cfg.ok && cfg.editable) add("Add deck", () => showSetup(cfg), "add-deck", { keepDialog: true });
  } catch (_err) {
    /* no config mode */
  }
  (state.payload && state.payload.actions || []).forEach((spec) => {
    add(spec.label, () => runPluginAction(spec));
  });
  body.append(list);
  const close = el("button", null, "Close");
  close.addEventListener("click", () => ChoiceDialog.close());
  body.append(close);
  ChoiceDialog.open();
}

function splitCsv(text) {
  return String(text || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function openCountSettings() {
  const countsInfo = (state.payload && state.payload.counts) || {};
  const body = $("dialog-body");
  body.replaceChildren();
  body.append(el("h2", null, "Count display"));
  const countsSel = el("select", "setup-input");
  [
    ["auto", "Auto (hide for large or special decks)"],
    ["on", "Always show counts"],
    ["off", "Hide counts"],
  ].forEach(([value, label]) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    if ((countsInfo.mode || "auto") === value) opt.selected = true;
    countsSel.append(opt);
  });
  body.append(el("label", "setup-label", "Show counts"));
  body.append(countsSel);
  const row = el("div", "sheet-actions");
  const save = el("button", null, "Save");
  save.addEventListener("click", async () => {
    let data;
    try {
      data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/counts", {
        mode: countsSel.value,
      });
    } catch (_err) {
      data = { ok: false };
    }
    ChoiceDialog.close();
    if (!data.ok) {
      setStatus(data.message || "Could not save.");
      return;
    }
    if (data.counts) state.payload.counts = data.counts;
    if (await loadItems()) renderDeck();
  });
  row.append(save);
  const close = el("button", null, "Cancel");
  close.addEventListener("click", () => ChoiceDialog.close());
  row.append(close);
  body.append(row);
  ChoiceDialog.open();
}

async function openOrderSettings() {
  const view = (state.payload && state.payload.view) || {};
  if (view.locked) {
    setStatus("This deck keeps a fixed order.");
    return;
  }
  const prefs = view.prefs || {};
  const body = $("dialog-body");
  body.replaceChildren();
  body.append(el("h2", null, "Order and filter"));
  const form = el("form", "order-filter-form setup-form");
  form.addEventListener("submit", (event) => event.preventDefault());
  const sort = el("select", "setup-input");
  [
    ["scan", "Folder scan order"],
    ["filename", "Filename (natural)"],
    ["folder", "Folder, then filename"],
    ["mtime_desc", "Newest first"],
    ["mtime_asc", "Oldest first"],
    ["random", "Random (stable)"],
  ].forEach(([value, label]) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    if ((prefs.sort_mode || "scan") === value) opt.selected = true;
    sort.append(opt);
  });
  appendSetupField(form, "Sort", sort);
  const seed = el("input", "setup-input");
  seed.type = "text";
  seed.placeholder = "auto";
  seed.autocomplete = "off";
  seed.value = displayRandomSeed(prefs, view, state.deckId);
  const seedRow = el("div", "setup-seed-row");
  seedRow.append(seed);
  const reshuffle = el("button", "seed-reshuffle", "Reshuffle");
  reshuffle.type = "button";
  reshuffle.addEventListener("click", () => {
    seed.value = newRandomSeed();
    seed.focus();
  });
  seedRow.append(reshuffle);
  appendSetupField(form, "Random seed", seedRow);
  const types = el("input", "setup-input");
  types.placeholder = "image, video, gif, or extensions";
  types.value = (prefs.file_types || []).join(", ");
  appendSetupField(form, "File types", types);
  const inc = el("input", "setup-input");
  inc.placeholder = "Comma-separated folder names";
  inc.value = (prefs.include_folders || []).join(", ");
  appendSetupField(form, "Include folders", inc);
  const exc = el("input", "setup-input");
  exc.placeholder = "Comma-separated folder names";
  exc.value = (prefs.exclude_folders || []).join(", ");
  appendSetupField(form, "Exclude folders", exc);
  body.append(form);
  const row = el("div", "sheet-actions");
  const save = el("button", null, "Save");
  save.addEventListener("click", async () => {
    state.anchorAfterLoad = current() ? current().id : null;
    const payload = {
      sort_mode: sort.value,
      random_seed: seed.value,
      file_types: splitCsv(types.value),
      include_folders: splitCsv(inc.value),
      exclude_folders: splitCsv(exc.value),
    };
    let data;
    try {
      data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/view", payload);
    } catch (_err) {
      data = { ok: false };
    }
    ChoiceDialog.close();
    if (!data.ok) {
      setStatus(data.message || "Could not save.");
      return;
    }
    if (data.view) state.payload.view = data.view;
    if (await loadItems()) renderDeck();
  });
  row.append(save);
  const close = el("button", null, "Cancel");
  close.addEventListener("click", () => ChoiceDialog.close());
  row.append(close);
  body.append(row);
  ChoiceDialog.open();
}

function openCounts() {
  const data = state.payload;
  if (!data) return;
  const body = $("dialog-body");
  body.replaceChildren();
  if (data.report) {
    appendReport(body, data.report);
  } else if (data.counts_hidden || data.meter === false) {
    body.append(el("h2", null, "Counts"));
    if (data.count_label) body.append(el("p", null, data.count_label));
    else body.append(el("p", null, "Pile totals are hidden for this deck."));
  } else {
    body.append(el("h2", null, "Counts"));
    body.append(el("p", null, data.decided + " decided, " + data.left + " left, " + data.total + " in the pile."));
    (data.tally || []).forEach((row) => body.append(el("p", null, row.label + ": " + row.n)));
    if (!data.tally || !data.tally.length) body.append(el("p", null, "No decisions yet."));
  }
  const close = el("button", null, "Close");
  close.addEventListener("click", () => ChoiceDialog.close());
  body.append(close);
  ChoiceDialog.open();
}

function togglePending() {
  state.pending = !state.pending;
  state.pos = 0;
  loadItems().then((ok) => { if (ok) renderDeck(); });
}

function toggleBlind() {
  state.blind = !state.blind;
  localStorage.setItem(blindKey(state.deckId), state.blind ? "1" : "0");
  renderDeck();
}

function onKey(event) {
  if (event.target.closest("input, textarea")) return;
  if (!state.deckId || state.picking) return;
  if (ChoiceDialog.isOpen() && event.key === "Escape") return;
  const map = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
  if (map[event.key]) {
    event.preventDefault();
    if (ChoiceDialog.isOpen()) ChoiceDialog.close();
    act(map[event.key]);
    return;
  }
  const item = current();
  if (item && item.kind === "pair") {
    if (event.key === "a" || event.key === "A") {
      event.preventDefault();
      act("left");
      return;
    }
    if (event.key === "b" || event.key === "B") {
      event.preventDefault();
      act("right");
      return;
    }
  }
  if ((event.key === "u" || event.key === "U") && undoEnabled()) undoLast();
}

function peopleOn() {
  return !!(state.index && Array.isArray(state.index.users));
}

function currentPerson() {
  if (!peopleOn() || !state.user) return null;
  return state.index.users.find((user) => user.id === state.user) || null;
}

function paintWho() {
  const button = $("who");
  if (state.picking) {
    button.hidden = true;
    return;
  }
  const person = currentPerson();
  button.hidden = false;
  button.textContent = person ? person.name : "People";
  button.title = person ? person.name : "People";
}

function allDecks() {
  if (state.index && state.index.library) return state.index.library;
  return (state.index && state.index.decks) || [];
}

function blindKey(deckId) {
  return "choice.blind." + (state.user ? state.user + "." : "") + deckId;
}

function licenceLine() {
  const note = el("p", "fine");
  note.append(document.createTextNode("Choice is free software. "));
  const link = el("a", null, "AGPL-3.0 licence");
  link.href = apiPath("/license");
  note.append(link);
  return note;
}

function copyUser(user) {
  return { id: user.id, name: user.name, decks: user.decks };
}

function deckSummary(user) {
  if (user.decks === "*") return "Every deck";
  const ids = user.decks || [];
  if (!ids.length) return "No decks";
  return ids.map((id) => {
    const deck = allDecks().find((row) => row.id === id);
    return deck ? deck.title : id;
  }).join(", ");
}

async function refreshIndex() {
  let index;
  try {
    index = await api("/api/index");
  } catch (_err) {
    showProblem("Could not reach Choice.");
    return false;
  }
  if (!index.ok) {
    showProblem(index.message || "Nothing to swipe.");
    return false;
  }
  state.index = index;
  if (peopleOn() && state.user && !currentPerson()) {
    state.user = "";
    localStorage.removeItem("choice.user");
  }
  return true;
}

async function showPeople() {
  state.picking = true;
  setStatus("");
  $("status").hidden = true;
  if (ChoiceDialog.isOpen()) ChoiceDialog.close();
  try {
    if (!(await refreshIndex())) return;
  } catch (_err) {
    return showProblem("Could not reach Choice.");
  }
  renderPeople();
}

function backFromPeople() {
  if (peopleOn() && !currentPerson()) return;
  state.picking = false;
  const wanted = new URLSearchParams(location.search).get("deck");
  const decks = (state.index && state.index.decks) || [];
  const allowed = decks.some((deck) => deck.id === wanted && !deck.error);
  if (wanted && !allowed) clearAppSearch();
  route();
}

function renderPeople() {
  state.picking = true;
  state.deckId = null;
  state.payload = null;
  $("who").hidden = true;
  $("tools").hidden = true;
  $("track").hidden = true;
  $("actions").hidden = true;
  $("menu").hidden = false;
  $("count").textContent = "";
  $("title").textContent = "People";
  const wrap = el("div", "people");
  (state.index.warnings || []).forEach((warning) => wrap.append(el("p", "warn", warning)));
  const users = (state.index && state.index.users) || [];
  if (!users.length) {
    wrap.append(el("p", null, "Add a person to keep their swipes separate, and to choose which decks they see."));
  } else {
    const list = el("ul", "library");
    users.forEach((user) => {
      const item = el("li", "person");
      const button = el("button", "deck-link");
      button.type = "button";
      const copy = el("span", "deck-copy");
      copy.append(el("span", "deck-name", user.name));
      copy.append(el("span", "deck-meta", deckSummary(user)));
      button.append(copy);
      button.addEventListener("click", () => chooseUser(user.id));
      const assign = el("button", "assign", "Assign");
      assign.type = "button";
      assign.dataset.choiceModal = "assign";
      assign.addEventListener("click", () => openAssign(user));
      item.append(button, assign);
      list.append(item);
    });
    wrap.append(list);
  }
  const form = el("form", "add-person");
  const input = el("input");
  input.type = "text";
  input.maxLength = 48;
  input.placeholder = "Name";
  input.setAttribute("aria-label", "Name");
  const add = el("button", null, "Add");
  add.type = "submit";
  form.append(input, add);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    addPerson(input.value);
  });
  wrap.append(form);
  wrap.append(el("p", "fine", "Each person has their own swipes. A name is not a password."));
  wrap.append(licenceLine());
  $("main").replaceChildren(wrap);
}

async function chooseUser(id) {
  if (state.busy) return;
  state.user = id;
  localStorage.setItem("choice.user", id);
  state.picking = false;
  state.deckId = null;
  state.payload = null;
  if (location.search) clearAppSearch();
  if (!(await refreshIndex())) return;
  route();
}

async function addPerson(name) {
  if (state.busy) return;
  const cleaned = name.trim().replace(/\s+/g, " ");
  if (!cleaned) return;
  state.busy = true;
  const users = ((state.index && state.index.users) || []).map(copyUser);
  users.push({ name: cleaned, decks: "*" });
  const ok = await saveUsers(users);
  state.busy = false;
  if (!ok) return;
  setStatus("Added " + cleaned + ".");
  renderPeople();
}

function openAssign(user) {
  const body = $("dialog-body");
  body.replaceChildren();
  body.append(el("h2", null, "Assign"));
  body.append(el("p", null, user.name));
  const decks = allDecks();
  const selected = new Set(user.decks === "*" ? decks.map((deck) => deck.id) : (user.decks || []));
  const list = el("ul", "assign-list");
  decks.forEach((deck) => {
    const item = el("li");
    const label = el("label", "assign-row");
    const box = el("input");
    box.type = "checkbox";
    box.value = deck.id;
    box.checked = selected.has(deck.id);
    label.append(box, document.createTextNode(deck.title));
    item.append(label);
    list.append(item);
  });
  if (decks.length) body.append(list);
  else body.append(el("p", null, "No decks to assign."));
  body.append(el("p", "fine", "Tick every deck to include decks you add later."));
  const row = el("div", "sheet-actions");
  const save = el("button", null, "Save");
  save.type = "button";
  save.addEventListener("click", () => saveAssign(user, list));
  const remove = el("button", null, "Remove " + user.name);
  remove.type = "button";
  remove.addEventListener("click", () => removePerson(user));
  const close = el("button", null, "Close");
  close.type = "button";
  close.addEventListener("click", () => ChoiceDialog.close());
  row.append(save, remove, close);
  body.append(row);
  ChoiceDialog.open();
}

async function saveAssign(user, list) {
  if (state.busy) return;
  const ids = allDecks().map((deck) => deck.id);
  const checked = [];
  list.querySelectorAll("input").forEach((box) => {
    if (box.checked) checked.push(box.value);
  });
  const decks = ids.length && checked.length === ids.length ? "*" : checked;
  const users = ((state.index && state.index.users) || []).map(copyUser);
  const row = users.find((item) => item.id === user.id);
  if (!row) return;
  row.decks = decks;
  state.busy = true;
  const ok = await saveUsers(users);
  state.busy = false;
  if (!ok) return;
  if (ChoiceDialog.isOpen()) ChoiceDialog.close();
  setStatus(user.name + " now has " + assignedPhrase(decks) + ".");
  renderPeople();
}

function assignedPhrase(decks) {
  if (decks === "*") return "every deck";
  if (!decks.length) return "no decks";
  if (decks.length === 1) return "1 deck";
  return decks.length + " decks";
}

async function removePerson(user) {
  if (state.busy) return;
  const users = ((state.index && state.index.users) || []).filter((item) => item.id !== user.id).map(copyUser);
  state.busy = true;
  const ok = await saveUsers(users);
  state.busy = false;
  if (!ok) return;
  if (state.user === user.id) {
    state.user = "";
    localStorage.removeItem("choice.user");
  }
  if (ChoiceDialog.isOpen()) ChoiceDialog.close();
  if (!users.length) setStatus("People are off. Swipes use the shared log again.");
  else setStatus("Removed " + user.name + ". Their swipes stay on disk.");
  renderPeople();
}

async function saveUsers(users) {
  let data;
  try {
    data = await api("/api/users", { users: users });
  } catch (_err) {
    setStatus("Could not reach Choice.");
    return false;
  }
  if (!data.ok) {
    setStatus(data.message || "Not saved.");
    return false;
  }
  return refreshIndex();
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function installTestHooks() {
  if (!new URLSearchParams(location.search).has("testhooks")) return;
  window.ChoiceTestHooks = {
    openMenu,
    openCounts,
    openCountSettings,
    openOrderSettings,
    openAssign,
    openBrowsePicker,
    openQueueFailures,
    showPeople,
    seedQueueFailures() {
      state.queue = {
        failures: [{ from: "sample.jpg", error: "Layout test failure" }],
        failed: 1,
        pending: 0,
        running: 0,
      };
      paintQueueBadge();
    },
    openConfirm(message) {
      return ChoiceDialog.confirm(message, {
        title: "Confirm",
        confirmLabel: "OK",
        cancelLabel: "Cancel",
      });
    },
    async openAddDeck() {
      const cfg = await api("/api/config");
      if (cfg.ok && cfg.editable) showSetup(cfg);
    },
    expectedModalTriggerIds() {
      return [
        "menu",
        "order-settings",
        "count-settings",
        "queue-failures",
        "add-deck",
        "deck-edit",
        "assign",
      ];
    },
    cardLayoutMetrics() {
      const card = document.querySelector("article.card.image");
      if (!card) return { ok: false, reason: "no-image-card" };
      const frame = card.querySelector(".frame");
      const img = frame && frame.querySelector("img");
      const cap = card.querySelector(":scope > .cap");
      if (!frame || !img) return { ok: false, reason: "no-frame-or-img" };
      const fr = frame.getBoundingClientRect();
      const ir = img.getBoundingClientRect();
      const cr = cap ? cap.getBoundingClientRect() : null;
      const gap = cr ? cr.top - ir.bottom : 0;
      const overlap = cr ? ir.bottom - cr.top > 1 : false;
      const topBand = ir.top - fr.top;
      return {
        ok: !overlap && topBand <= 2,
        overlap,
        topBand,
        gap,
        frameHeight: fr.height,
        imgHeight: ir.height,
      };
    },
  };
}

installTestHooks();
boot();
