/* Choice page. One deck at a time. The server is the source of truth. */

const state = {
  index: null,
  deckId: null,
  pending: true,
  blind: false,
  payload: null,
  pos: 0,
  note: "",
  noteFor: null,
  busy: false,
  user: localStorage.getItem("choice.user") || "",
  picking: false,
};

const $ = (id) => document.getElementById(id);

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
  const res = await fetch(withUser(path), opts);
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
  if (!$("dialog").open || !body) return;
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

async function boot() {
  $("home").addEventListener("click", () => {
    if (state.picking) return backFromPeople();
    showLibrary();
  });
  $("who").addEventListener("click", showPeople);
  $("pending").addEventListener("click", togglePending);
  $("blind").addEventListener("click", toggleBlind);
  $("counts").addEventListener("click", openCounts);
  $("dialog").addEventListener("close", () => $("dialog-body").replaceChildren());
  document.addEventListener("keydown", onKey);
  window.addEventListener("popstate", route);
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
  $("title").textContent = "Choice";
  $("tools").hidden = true;
  $("track").hidden = true;
  $("actions").hidden = true;
  $("home").hidden = true;
  $("home").textContent = "Decks";
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
  state.deckId = null;
  state.payload = null;
  if (location.search) history.pushState(null, "", location.pathname);
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
  $("home").hidden = true;
  $("home").textContent = "Decks";
  paintWho();
  $("status").textContent = "";
  $("status").hidden = true;
  const list = el("ul", "library");
  (state.index.decks || []).forEach((deck) => {
    const item = el("li");
    if (deck.error) {
      item.append(el("strong", null, deck.title));
      item.append(el("p", "problem", deck.error));
      list.append(item);
      return;
    }
    const button = el("button", "deck-link");
    const copy = el("span", "deck-copy");
    copy.append(el("span", "deck-name", deck.title));
    copy.append(el("span", "deck-meta", deck.count_label || (deck.left + " left of " + deck.total)));
    button.append(copy);
    if (deck.meter !== false) {
      const bar = el("span", "bar");
      bar.setAttribute("aria-hidden", "true");
      const fill = el("span");
      fill.style.width = (deck.total ? (100 * deck.decided) / deck.total : 0) + "%";
      bar.append(fill);
      button.append(bar);
    }
    button.addEventListener("click", () => openDeck(deck.id, true));
    item.append(button);
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
  wrap.append(btn);
  parts.push(wrap);
}

function showSetup(cfg) {
  state.deckId = null;
  $("title").textContent = "Add deck";
  $("tools").hidden = true;
  $("track").hidden = true;
  $("actions").hidden = true;
  $("home").hidden = false;
  const form = el("form", "setup-form");
  form.addEventListener("submit", (event) => event.preventDefault());

  form.append(fieldLabel("Deck id"));
  const deckId = el("input");
  deckId.name = "deck_id";
  deckId.required = true;
  form.append(deckId);

  form.append(fieldLabel("Title"));
  const deckTitle = el("input");
  deckTitle.name = "title";
  form.append(deckTitle);

  form.append(fieldLabel("Source"));
  const sourcePick = el("select");
  (cfg.sources || []).forEach((src) => {
    const opt = el("option", null, src.id + " (" + src.type + ")");
    opt.value = src.id;
    sourcePick.append(opt);
  });
  form.append(sourcePick);

  form.append(fieldLabel("Mount path (folder within source)"));
  const mount = el("input");
  mount.name = "mount";
  mount.placeholder = ".";
  form.append(mount);

  form.append(fieldLabel("Output mode"));
  const output = el("select");
  [["results", "Results (log only)"], ["sort", "Sort (move to folders)"]].forEach(([value, label]) => {
    const opt = el("option", null, label);
    opt.value = value;
    output.append(opt);
  });
  form.append(output);

  form.append(fieldLabel("Recursive scan"));
  const recursive = el("input");
  recursive.type = "checkbox";
  recursive.name = "recursive";
  form.append(recursive);

  form.append(fieldLabel("Include globs (comma-separated)"));
  const include = el("input");
  include.name = "include";
  include.placeholder = "*.jpg, *.png";
  form.append(include);

  form.append(fieldLabel("Exclude globs"));
  const exclude = el("input");
  exclude.name = "exclude";
  exclude.placeholder = "keep/**";
  form.append(exclude);

  form.append(fieldLabel("Sort folder: right swipe"));
  const sortRight = el("input");
  sortRight.name = "sort_right";
  sortRight.placeholder = "keep";
  form.append(sortRight);

  form.append(fieldLabel("Sort folder: left swipe"));
  const sortLeft = el("input");
  sortLeft.name = "sort_left";
  sortLeft.placeholder = "delete";
  form.append(sortLeft);

  form.append(fieldLabel("Secret env name (e.g. IMMICH_API_KEY)"));
  const secretName = el("input");
  secretName.name = "secret_name";
  secretName.placeholder = "IMMICH_API_KEY";
  form.append(secretName);

  form.append(fieldLabel("Secret value (stored in secrets file, not config)"));
  const secretValue = el("input");
  secretValue.type = "password";
  secretValue.name = "secret_value";
  secretValue.autocomplete = "off";
  form.append(secretValue);

  const testBtn = el("button", null, "Test connection");
  testBtn.type = "button";
  const saveBtn = el("button", null, "Save");
  saveBtn.type = "submit";
  form.append(testBtn, saveBtn);

  testBtn.addEventListener("click", async () => {
    const src = (cfg.sources || []).find((s) => s.id === sourcePick.value);
    if (!src) return setStatus("Pick a source.");
    const body = {
      mount: mount.value || ".",
      source: Object.assign({}, src, {
        output: output.value,
        recursive: recursive.checked,
        include: splitGlobs(include.value),
        exclude: splitGlobs(exclude.value),
        sort_right: sortRight.value,
        sort_left: sortLeft.value,
      }),
    };
    const res = await api("/api/sources/test", body);
    if (!res.ok) return setStatus(res.message || "Test failed.");
    const names = (res.preview || []).map((p) => p.title).join(", ");
    setStatus(res.message + (names ? " Preview: " + names : ""));
  });

  form.addEventListener("submit", async () => {
    const id = deckId.value.trim();
    if (!id) return setStatus("Deck id is required.");
    const decks = (cfg.decks || []).filter((d) => d.id !== id);
    const entry = {
      id,
      title: deckTitle.value.trim() || id,
      source: sourcePick.value,
      mount: mount.value.trim() || ".",
      output: output.value,
      recursive: recursive.checked,
    };
    const inc = splitGlobs(include.value);
    const exc = splitGlobs(exclude.value);
    if (inc.length) entry.include = inc;
    if (exc.length) entry.exclude = exc;
    if (sortRight.value.trim()) entry.sort_right = sortRight.value.trim();
    if (sortLeft.value.trim()) entry.sort_left = sortLeft.value.trim();
    decks.push(entry);
    const sname = secretName.value.trim();
    const sval = secretValue.value;
    if (sname && sval) {
      const sec = await api("/api/secrets", { name: sname, value: sval });
      if (!sec.ok) return setStatus(sec.message || "Could not store secret.");
      secretValue.value = "";
    }
    const res = await api("/api/config", { sources: cfg.sources, decks });
    if (!res.ok) return setStatus(res.message || "Could not save.");
    setStatus("Saved. Restart Choice if decks do not refresh.");
    showLibrary();
  });

  $("main").replaceChildren(form);
  setStatus("");
}

function fieldLabel(text) {
  const label = el("label", "setup-label", text);
  return label;
}

function splitGlobs(text) {
  return String(text || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function openDeck(id, push) {
  state.deckId = id;
  state.pos = 0;
  state.note = "";
  state.noteFor = null;
  $("status").textContent = "";
  const stored = localStorage.getItem(blindKey(id));
  const deck = (state.index.decks || []).find((row) => row.id === id);
  if (deck && deck.error) return showProblem(deck.error);
  if (push) history.pushState(null, "", "?deck=" + encodeURIComponent(id));
  const ok = await loadItems(stored);
  if (ok) renderDeck();
}

async function loadItems(storedBlind) {
  let data;
  try {
    data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/items?pending=" + (state.pending ? "1" : "0"));
  } catch (_err) {
    return showProblem("Could not reach Choice.");
  }
  if (!data.ok) {
    showProblem(data.message || "Could not read this deck.");
    return false;
  }
  state.payload = data;
  if (storedBlind !== undefined) {
    state.blind = storedBlind === null ? !!data.blind : storedBlind === "1";
  }
  if (state.pos >= data.items.length) state.pos = 0;
  return true;
}

function renderDeck() {
  state.picking = false;
  const data = state.payload;
  const several = state.index && state.index.decks && state.index.decks.length > 1;
  $("home").hidden = !several;
  $("home").textContent = "Decks";
  paintWho();
  $("title").textContent = data.title;
  $("tools").hidden = false;
  $("count").textContent = data.count_label || (data.left + " left");
  $("pending").textContent = state.pending ? "Show all" : "Still to do";
  $("blind").setAttribute("aria-pressed", state.blind ? "true" : "false");
  $("track").hidden = data.meter === false;
  const pct = data.total ? (100 * data.decided) / data.total : 0;
  $("fill").style.width = pct + "%";
  $("track").setAttribute("aria-valuenow", String(data.decided));
  $("track").setAttribute("aria-valuemax", String(data.total));
  $("track").setAttribute("aria-label", data.count_label || (data.decided + " of " + data.total + " decided"));
  renderActions();
  const item = current();
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
  bindDrag(card);
  preloadMedia();
}

function preloadMedia() {
  const items = (state.payload && state.payload.items) || [];
  const urls = [];
  for (let i = 0; i < 3 && i < items.length; i++) {
    const row = items[(state.pos + i) % items.length];
    if (!row) continue;
    if (row.kind === "image" && row.media) urls.push(mediaSrc(row, null));
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
  });
}

function paintCard(card, item) {
  if (item.kind === "pair" && item.sides && item.sides.length) {
    paintPair(card, item);
    return;
  }
  const showTitle = item.kind === "file" || (item.kind !== "image" && (!state.blind || !item.body)) || (item.kind === "image" && !state.blind);
  if (item.kind === "image" && item.media) {
    const frame = el("div", "frame");
    appendPhoto(frame, mediaSrc(item, null), state.blind ? "Card" : item.title);
    const cap = el("div", "cap");
    if (showTitle) cap.append(el("h2", null, item.title));
    if (item.body) cap.append(el("p", "body", item.body));
    const call = callText(item);
    if (call) cap.append(el("p", "fine", "Your call: " + call));
    appendMark(cap, item);
    appendChips(cap, item);
    if (cap.childNodes.length) frame.append(cap);
    card.append(frame);
    return;
  }
  if (showTitle || item.body || item.kind === "file" || callText(item) || item.mark) {
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

function paintPair(card, item) {
  const media = item.sides.some((side) => side.media);
  card.classList.add("pair");
  if (media) card.classList.add("has-media");
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
  item.sides.forEach((side) => {
    const pane = el("section", side.media ? "side has-media" : "side");
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

function mediaSrc(item, side) {
  let url = "/api/decks/" + encodeURIComponent(state.deckId) + "/media?item=" + encodeURIComponent(item.id);
  if (side) url += "&side=" + encodeURIComponent(side.key);
  const token = side ? side.media_token : item.media_token;
  return withUser(url + "&v=" + encodeURIComponent(token || ""));
}

function appendPhoto(frame, src, alt) {
  const img = el("img");
  img.alt = alt;
  img.src = src;
  img.draggable = false;
  const bleed = el("img", "bleed");
  bleed.alt = "";
  bleed.draggable = false;
  bleed.setAttribute("aria-hidden", "true");
  bleed.src = src;
  frame.append(bleed, img);
}

function appendChips(parent, item) {
  if (state.blind || !item.chips || !item.chips.length) return;
  const row = el("div", "chips");
  item.chips.forEach((chip) => row.append(el("span", "chip", chip.label + ": " + chip.text)));
  parent.append(row);
}

function renderEmpty() {
  const data = state.payload;
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
  $("actions").hidden = false;
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

function renderActions() {
  const row = $("actions");
  const item = current();
  row.hidden = false;
  row.replaceChildren();
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
  const undo = el("button", null, "Undo");
  undo.disabled = !state.payload.can_undo || state.busy;
  undo.addEventListener("click", () => undoLast());
  row.append(undo);
  if (item) {
    const details = el("button", null, "Details");
    details.addEventListener("click", openDetails);
    row.append(details);
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

function bindDrag(card) {
  let drag = null;
  const hint = el("div", "hint");
  hint.hidden = true;
  card.append(hint);

  card.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || state.busy) return;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, on: false };
  });
  card.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.on) {
      if (Math.abs(dx) < 10) return;
      if (Math.abs(dy) > Math.abs(dx)) {
        drag = null;
        return;
      }
      drag.on = true;
      card.setPointerCapture(event.pointerId);
    }
    if (reduceMotion()) return;
    card.style.transform = "translateX(" + dx + "px) rotate(" + Math.max(-8, Math.min(8, dx / 40)) + "deg)";
    const side = dx > 0 ? "right" : "left";
    const spec = specFor(side);
    const label = spec && buttonLabel(spec, current());
    hint.hidden = !label;
    hint.className = "hint " + side;
    hint.style.color = spec && spec.color ? spec.color : "";
    hint.textContent = label || "";
  });
  const finish = (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dx = event.clientX - drag.x;
    const side = dx > 0 ? "right" : "left";
    const spec = specFor(side);
    const armed = drag.on && Math.abs(dx) > 88 && spec && buttonLabel(spec, current());
    drag = null;
    hint.hidden = true;
    card.style.transform = "";
    if (armed) act(side);
  };
  card.addEventListener("pointerup", finish);
  card.addEventListener("pointercancel", finish);
}

async function act(direction) {
  const spec = specFor(direction);
  const item = current();
  const label = spec && item ? buttonLabel(spec, item) : null;
  if (!spec || !item || !label || state.busy) return;
  if ($("dialog").open) $("dialog").close();
  state.busy = true;
  renderActions();
  const card = document.querySelector(".card");
  if (card && !reduceMotion() && (direction === "left" || direction === "right")) {
    const sign = direction === "right" ? 1 : -1;
    card.style.transition = "transform 180ms ease-out";
    card.style.transform = "translateX(" + (sign * 120) + "%) rotate(" + (sign * 8) + "deg)";
  }
  let data;
  try {
    data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/decide", {
      item: item.id,
      direction: direction,
      note: state.note,
    });
  } catch (_err) {
    data = { ok: false, message: "Could not reach Choice." };
  }
  if (!reduceMotion()) await wait(180);
  if (!data.ok) {
    if (card) card.style.transform = "";
    setStatus(data.message || "Not saved");
    state.busy = false;
    renderActions();
    return;
  }
  state.note = "";
  state.noteFor = null;
  setStatus(data.message || label);
  const id = item.id;
  const later = !!spec.later;
  const ok = await loadItems();
  if (!ok) {
    state.busy = false;
    return;
  }
  const items = (state.payload && state.payload.items) || [];
  if (later || !state.pending) {
    const idx = items.findIndex((row) => row.id === id);
    if (idx !== -1) state.pos = items.length ? (idx + 1) % items.length : 0;
  }
  state.busy = false;
  renderDeck();
}

async function undoLast() {
  if (state.busy || !state.payload || !state.payload.can_undo) return;
  state.busy = true;
  let data;
  try {
    data = await api("/api/decks/" + encodeURIComponent(state.deckId) + "/undo", {});
  } catch (_err) {
    data = { ok: false, message: "Could not reach Choice." };
  }
  setStatus(data.message || "");
  const ok = await loadItems();
  state.busy = false;
  if (ok) renderDeck();
}

function openDetails() {
  const item = current();
  if (!item) return;
  if (state.noteFor !== item.id) {
    state.note = "";
    state.noteFor = item.id;
  }
  const body = $("dialog-body");
  body.replaceChildren();
  body.append(el("h2", null, "Details"));
  if (item.kind === "pair" && item.sides && item.sides.length) {
    if (item.title) body.append(el("p", null, item.title));
    if (item.body) body.append(el("p", "body", item.body));
    item.sides.forEach((side) => {
      body.append(el("h3", "side-label", sideLabel(side)));
      if (side.body) body.append(el("p", "body", side.body));
    });
    if (!state.blind) {
      (item.chips || []).concat(item.reveal || []).forEach((chip) => {
        body.append(el("p", null, chip.label + ": " + chip.text));
      });
    } else {
      body.append(el("p", "fine", "Blind is on. Chips and reveal fields stay hidden."));
    }
  } else if (!state.blind) {
    body.append(el("p", null, item.title));
    if (item.body) body.append(el("p", "body", item.body));
    if (item.file) body.append(el("p", "fine", item.file));
    (item.chips || []).concat(item.reveal || []).forEach((chip) => {
      body.append(el("p", null, chip.label + ": " + chip.text));
    });
  } else {
    if (item.body) body.append(el("p", "body", item.body));
    body.append(el("p", "fine", "Blind is on. Title, chips, and reveal fields stay hidden."));
  }
  const call = callText(item);
  if (call) body.append(el("p", null, "Your call: " + call));
  appendMark(body, item);
  const note = el("input", "note");
  note.type = "text";
  note.maxLength = 500;
  note.placeholder = "Note, sent with the next swipe";
  note.value = state.note;
  note.addEventListener("input", () => { state.note = note.value; });
  body.append(note);
  const row = el("div", "sheet-actions");
  specs().forEach((spec) => {
    const label = buttonLabel(spec, item);
    if (!label) return;
    row.append(actionButton(spec, label));
  });
  body.append(row);
  body.append(el("p", "fine", "Arrow keys decide. U undoes. I opens this."));
  const close = el("button", null, "Close");
  close.addEventListener("click", () => $("dialog").close());
  body.append(close);
  $("dialog").showModal();
}

function openCounts() {
  const data = state.payload;
  if (!data) return;
  const body = $("dialog-body");
  body.replaceChildren();
  if (data.report) {
    appendReport(body, data.report);
  } else {
    body.append(el("h2", null, "Counts"));
    body.append(el("p", null, data.decided + " decided, " + data.left + " left, " + data.total + " in the pile."));
    (data.tally || []).forEach((row) => body.append(el("p", null, row.label + ": " + row.n)));
    if (!data.tally || !data.tally.length) body.append(el("p", null, "No decisions yet."));
  }
  const close = el("button", null, "Close");
  close.addEventListener("click", () => $("dialog").close());
  body.append(close);
  $("dialog").showModal();
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
  if ($("dialog").open && event.key === "Escape") return;
  const map = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" };
  if (map[event.key]) {
    event.preventDefault();
    if ($("dialog").open) $("dialog").close();
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
  if (event.key === "u" || event.key === "U") undoLast();
  if (event.key === "i" || event.key === "I") openDetails();
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
  link.href = "/license";
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
  if ($("dialog").open) $("dialog").close();
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
  if (wanted && !allowed) history.pushState(null, "", location.pathname);
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
  $("count").textContent = "";
  $("title").textContent = "People";
  $("home").textContent = "Back";
  $("home").hidden = peopleOn() && !currentPerson();
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
  if (location.search) history.pushState(null, "", location.pathname);
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
  close.addEventListener("click", () => $("dialog").close());
  row.append(save, remove, close);
  body.append(row);
  $("dialog").showModal();
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
  if ($("dialog").open) $("dialog").close();
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
  if ($("dialog").open) $("dialog").close();
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

boot();
