# SPDX-License-Identifier: AGPL-3.0-only
"""The local site.

It binds to this computer unless you pass --lan. A name is not a password.
A POST must be JSON, which blocks a plain cross-site form.
Media URLs only serve a file that is currently a card.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from choice.act import decide, progress, undo, view
from choice.config import ConfigProblem, load_config, mask_secrets, save_config, write_secret
from choice.load import DeckProblem
from choice.media import content_type, view_path
from choice.open import open_path
from choice.people import assignment_warnings, load_roster, parse_users, remove_roster, save_roster
from choice.queue import page_items
from choice.sources.registry import build_source, source_types

_WEB = Path(__file__).resolve().parent / "web"
_LICENSE = Path(__file__).resolve().parents[1] / "LICENSE"
_ID = re.compile(r"[a-z0-9_-]+")
_STATIC = {"app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8"}


class ChoiceSite(ThreadingHTTPServer):
    def __init__(self, address, root: Path, config_path: Path | None = None):
        self.choice_root = root
        self.config_path = config_path
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._guard(self._get)

    def do_POST(self):
        self._guard(self._post)

    def log_message(self, fmt, *args):
        return

    def _guard(self, fn):
        try:
            fn()
        except Exception:
            traceback.print_exc()
            self._json(
                500,
                {
                    "ok": False,
                    "message": (
                        "Choice hit an error. The detail is in the terminal that started it."
                    ),
                },
            )

    def _get(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return self._static("index.html", "text/html; charset=utf-8")
        if len(parts) == 1 and parts[0] in _STATIC:
            return self._static(parts[0], _STATIC[parts[0]])
        if parts == ["license"]:
            return self._license()
        if parts == ["api", "health"]:
            return self._json(200, {"ok": True, "service": "choice"})
        if parts == ["api", "index"]:
            return self._index(parse_qs(parsed.query))
        if parts == ["api", "config"]:
            return self._config_get()
        if parts == ["api", "source-types"]:
            return self._json(200, {"ok": True, "types": source_types()})
        if len(parts) == 5 and parts[:3] == ["api", "sources", "test"]:
            return self._source_test(parts[3], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "stats":
            return self._stats(parts[2], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "export":
            return self._export(parts[2], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "items":
            return self._items(parts[2], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "media":
            return self._media(parts[2], parse_qs(parsed.query))
        self._json(404, {"ok": False, "message": "No such page."})

    def _post(self):
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        body = self._json_body()
        if body is None:
            return
        if parts == ["api", "config"]:
            return self._config_save(body)
        if parts == ["api", "secrets"]:
            return self._secret_save(body)
        if parts == ["api", "sources", "test"] and isinstance(body.get("source"), dict):
            return self._source_test_body(body)
        if parts == ["api", "users"]:
            return self._save_users(body)
        kind = parts[3] if len(parts) == 4 and parts[:2] == ["api", "decks"] else ""
        if kind not in {"decide", "undo"}:
            return self._json(404, {"ok": False, "message": "No such page."})
        deck = self._opened(parts[2], self._requested_user(parse_qs(parsed.query), body))
        if isinstance(deck, dict):
            return self._reply(deck)
        if kind == "undo":
            result = undo(deck)
        else:
            result = decide(
                deck,
                str(body.get("item") or ""),
                str(body.get("direction") or ""),
                body.get("note"),
            )
        self._json(200 if result.get("ok") else 400, result)

    def _library_path(self) -> Path:
        if self.server.config_path is not None:
            return self.server.config_path
        return self.server.choice_root

    def _index(self, query):
        try:
            opened = open_path(self._library_path())
            roster = load_roster(self.server.choice_root)
        except DeckProblem as exc:
            return self._json(200, {"ok": False, "message": str(exc), "direct": True, "decks": []})
        if not roster.enabled:
            return self._json(
                200,
                {"ok": True, "direct": opened.direct, "decks": _rows(opened.decks), "users": None},
            )
        library = [
            {"id": deck.id, "title": deck.title, "error": deck.problem} for deck in opened.decks
        ]
        known = {deck.id for deck in opened.decks}
        warnings = list(roster.warnings) + assignment_warnings(roster.people, known)
        user_id = self._requested_user(query, None)
        payload = {
            "ok": True,
            "direct": opened.direct,
            "users": [person.public() for person in roster.people],
            "library": library,
            "warnings": warnings,
        }
        person = None if not user_id else roster.get(user_id)
        if person is None:
            payload["pick"] = True
            payload["user"] = None
            payload["decks"] = []
            if user_id is None or user_id:
                payload["message"] = "No such person."
            return self._json(200, payload)
        chosen = []
        for deck in opened.decks:
            if person.sees(deck.id):
                deck.actor = person.id
                chosen.append(deck)
        payload["pick"] = False
        payload["user"] = {"id": person.id, "name": person.name}
        payload["decks"] = _rows(chosen)
        self._json(200, payload)

    def _items(self, deck_id, query):
        deck = self._opened(deck_id, self._requested_user(query, None))
        if isinstance(deck, dict):
            return self._reply(deck)
        pending = query.get("pending", ["1"])[0] != "0"
        limit = int((query.get("limit") or ["0"])[0] or 0)
        offset = int((query.get("offset") or ["0"])[0] or 0)
        snap = progress(deck, pending=pending)
        if limit > 0 and snap.get("ok") and snap.get("items"):
            items = snap["items"]
            paged, token = page_items(deck.id, items, offset=offset, limit=limit)
            snap["items"] = paged
            snap["page_token"] = token
        if not snap.get("ok"):
            return self._json(200, snap)
        warnings = list(snap.get("warnings") or [])
        snap.update(deck.public_meta())
        snap["warnings"] = warnings
        self._json(200, snap)

    def _media(self, deck_id, query):
        deck = self._opened(deck_id, self._requested_user(query, None))
        if isinstance(deck, dict):
            return self._reply(deck)
        item_id = (query.get("item") or [""])[0]
        side_key = (query.get("side") or [""])[0]
        version = (query.get("v") or [""])[0]
        try:
            flow = view(deck)
        except DeckProblem as exc:
            return self._json(404, {"ok": False, "message": str(exc)})
        item = next((it for it in flow.items if it.id == item_id), None)
        if deck.plugin is not None and hasattr(deck.plugin, "media_bytes"):
            blob = deck.plugin.media_bytes(item_id)
            if blob:
                data, ctype = blob[0], blob[1]
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, max-age=86400")
                if version:
                    self.send_header("ETag", f'"{version}"')
                self.end_headers()
                self.wfile.write(data)
                return
        source = _media_source(item, side_key)
        if source is None or not source.is_file():
            return self._json(404, {"ok": False, "message": "No such image."})
        path = view_path(source, deck.state_dir / "cache").resolve()
        source = source.resolve()
        cache = (deck.state_dir / "cache").resolve()
        if path != source and cache not in path.parents:
            path = source
        try:
            size = path.stat().st_size
            handle = path.open("rb")
        except OSError:
            return self._json(404, {"ok": False, "message": "That image could not be read."})
        self.send_response(200)
        self.send_header("Content-Type", content_type(path))
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()
        with handle:
            shutil.copyfileobj(handle, self.wfile)

    def _save_users(self, body):
        try:
            opened = open_path(self._library_path())
        except DeckProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        known = {deck.id for deck in opened.decks}
        try:
            people = parse_users(body.get("users"), known)
            if people:
                save_roster(self.server.choice_root, people)
            else:
                remove_roster(self.server.choice_root)
        except DeckProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        self._json(200, {"ok": True, "users": [person.public() for person in people]})

    def _opened(self, deck_id, user_id):
        """The deck for this request, with the person's log selected."""
        deck = self._deck(deck_id)
        if isinstance(deck, dict):
            deck["status"] = 404
            return deck
        try:
            roster = load_roster(self.server.choice_root)
        except DeckProblem as exc:
            return {"ok": False, "message": str(exc), "status": 400}
        if not roster.enabled:
            return deck
        if user_id is None:
            return {"ok": False, "message": "No such person.", "status": 400}
        if not user_id:
            return {"ok": False, "message": "Pick a person first.", "status": 400}
        person = roster.get(user_id)
        if person is None:
            return {"ok": False, "message": "No such person.", "status": 404}
        if not person.sees(deck.id):
            return {
                "ok": False,
                "message": f"{person.name} does not have this deck.",
                "status": 403,
            }
        deck.actor = person.id
        return deck

    def _requested_user(self, query, body):
        """'' if omitted, None if the id is not a person id."""
        raw = ""
        if query:
            raw = (query.get("user") or [""])[0]
        if not str(raw).strip() and isinstance(body, dict):
            raw = body.get("user") or ""
        raw = str(raw or "").strip()
        if not raw:
            return ""
        if not _ID.fullmatch(raw):
            return None
        return raw

    def _json_body(self):
        """The posted object, or None after an error response."""
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("application/json"):
            self._json(415, {"ok": False, "message": "Send JSON."})
            return None
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._json(400, {"ok": False, "message": "Send JSON."})
            return None
        if length < 0 or length > 65536:
            self._json(413, {"ok": False, "message": "That request is too large."})
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "message": "That was not valid JSON."})
            return None
        if not isinstance(body, dict):
            self._json(400, {"ok": False, "message": "Send a JSON object."})
            return None
        return body

    def _reply(self, payload):
        status = payload.pop("status", 404)
        self._json(status, payload)

    def _deck(self, deck_id):
        if not _ID.fullmatch(deck_id or ""):
            return {"ok": False, "message": "No such deck."}
        try:
            opened = open_path(self._library_path())
        except DeckProblem as exc:
            return {"ok": False, "message": str(exc)}
        for deck in opened.decks:
            if deck.id == deck_id:
                return deck
        return {"ok": False, "message": "No such deck."}

    def _static(self, name, ctype):
        path = _WEB / name
        if not path.is_file():
            return self._json(500, {"ok": False, "message": "Choice is missing its page files."})
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _license(self):
        if not _LICENSE.is_file():
            text = "Choice is licensed under the GNU Affero General Public License, version 3.\n"
            data = text.encode("utf-8")
        else:
            data = _LICENSE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _config_get(self):
        path = self.server.config_path
        if path is None or not path.is_file():
            return self._json(200, {"ok": True, "config": None, "editable": False})
        try:
            cfg = load_config(path)
        except ConfigProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        sources = [mask_secrets({"id": s.id, "type": s.type, **s.options}) for s in cfg.sources]
        decks = [
            {"id": d.id, "title": d.title, "source": d.source, "mount": d.mount, **d.options}
            for d in cfg.decks
        ]
        return self._json(
            200,
            {
                "ok": True,
                "editable": True,
                "path": str(path),
                "state_dir": str(cfg.state_dir),
                "sources": sources,
                "decks": decks,
            },
        )

    def _config_save(self, body):
        path = self.server.config_path
        if path is None:
            return self._json(
                400, {"ok": False, "message": "Server was not started with --config."}
            )
        try:
            cfg = load_config(path)
        except ConfigProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        sources = body.get("sources")
        decks = body.get("decks")
        if not isinstance(sources, list) or not isinstance(decks, list):
            return self._json(400, {"ok": False, "message": "Send sources and decks arrays."})
        save_config(cfg, sources, decks)
        return self._json(200, {"ok": True})

    def _source_test(self, source_id, query):
        path = self.server.config_path
        if path is None:
            return self._json(400, {"ok": False, "message": "No config."})
        mount = (query.get("mount") or [""])[0]
        try:
            cfg = load_config(path)
            spec = cfg.source(source_id)
            if spec is None:
                return self._json(404, {"ok": False, "message": "No such source."})
            src = build_source(spec, cfg)
            ok, message = src.test()
            preview = [p.__dict__ for p in src.preview(mount)] if ok else []
            return self._json(200, {"ok": ok, "message": message, "preview": preview})
        except ConfigProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})

    def _source_test_body(self, body):
        path = self.server.config_path
        if path is None:
            return self._json(400, {"ok": False, "message": "No config."})
        row = body.get("source")
        mount = str(body.get("mount") or "")
        try:
            cfg = load_config(path)
            from choice.config import SourceSpec

            spec = SourceSpec(
                id="test",
                type=str(row.get("type") or ""),
                options={k: v for k, v in row.items() if k != "type"},
            )
            src = build_source(spec, cfg)
            ok, message = src.test()
            preview = [p.__dict__ for p in src.preview(mount)] if ok else []
            return self._json(200, {"ok": ok, "message": message, "preview": preview})
        except ConfigProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})

    def _stats(self, deck_id, query):
        deck = self._opened(deck_id, self._requested_user(query, None))
        if isinstance(deck, dict):
            return self._reply(deck)
        plugin = deck.plugin
        if plugin is not None and hasattr(plugin, "stats"):
            data = plugin.stats()
            if data:
                return self._json(200, {"ok": True, "stats": data})
        snap = progress(deck, pending=False)
        return self._json(
            200, {"ok": True, "stats": {"tally": snap.get("tally"), "total": snap.get("total")}}
        )

    def _export(self, deck_id, query):
        deck = self._opened(deck_id, self._requested_user(query, None))
        if isinstance(deck, dict):
            return self._reply(deck)
        from choice.act import _read_log

        rows = _read_log(deck)
        snap = progress(deck, pending=False)
        payload = {"ok": True, "decisions": rows, "deck": deck.id}
        if snap.get("report"):
            payload["ranking"] = snap["report"]
        if snap.get("tally"):
            payload["tally"] = snap["tally"]
        return self._json(200, payload)

    def _secret_save(self, body):
        path = self.server.config_path
        if path is None:
            return self._json(400, {"ok": False, "message": "No config."})
        name = str(body.get("name") or "").strip()
        value = str(body.get("value") or "")
        if not value:
            return self._json(400, {"ok": False, "message": "Secret value is required."})
        try:
            cfg = load_config(path)
            secret_path = write_secret(cfg, name, value)
        except ConfigProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        return self._json(200, {"ok": True, "name": name, "secrets_file": str(secret_path)})

    def _json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encoding = self.headers.get("Accept-Encoding", "")
        if "gzip" in encoding and len(data) > 280:
            data = gzip.compress(data)
            extra = [("Content-Encoding", "gzip")]
        else:
            extra = []
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)


def _rows(decks) -> list[dict]:
    rows = []
    for deck in decks:
        if deck.problem:
            rows.append(
                {
                    "id": deck.id,
                    "title": deck.title,
                    "error": deck.problem,
                    "total": 0,
                    "decided": 0,
                    "left": 0,
                }
            )
            continue
        snap = progress(deck, pending=True)
        if not snap.get("ok"):
            rows.append(
                {
                    "id": deck.id,
                    "title": deck.title,
                    "error": snap.get("message"),
                    "total": 0,
                    "decided": 0,
                    "left": 0,
                }
            )
            continue
        row = {
            "id": deck.id,
            "title": deck.title,
            "error": None,
            "total": snap["total"],
            "decided": snap["decided"],
            "left": snap["left"],
        }
        if snap.get("count_label"):
            row["count_label"] = snap["count_label"]
        if snap.get("meter") is False:
            row["meter"] = False
        rows.append(row)
    return rows


def _media_source(item, side_key: str):
    """The file for this card, or for one side of a pair. Nothing else."""
    if item is None:
        return None
    if side_key:
        if item.kind != "pair" or side_key not in {"a", "b"}:
            return None
        side = next((side for side in item.sides if side.key == side_key), None)
        return side.path if side is not None else None
    if item.kind == "image":
        return item.path
    return None


def serve(root: Path, host: str, port: int, config_path: Path | None = None) -> None:
    ChoiceSite.allow_reuse_address = True
    try:
        server = ChoiceSite((host, port), root, config_path=config_path)
    except OSError as exc:
        raise SystemExit(
            f"Cannot listen on {host}:{port} ({exc.strerror or exc})."
        ) from exc
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
