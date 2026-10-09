# SPDX-License-Identifier: AGPL-3.0-only
"""The local site.

It binds to this computer unless you pass --lan. A name is not a password.
A POST must be JSON, which blocks a plain cross-site form.
Media URLs only serve a file that is currently a card.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from choice.act import (
    decide,
    index_summary,
    item_by_id,
    progress,
    run_plugin_action,
    save_deck_counts,
    save_deck_view,
    undo,
)
from choice.config import ConfigProblem, load_config, mask_secrets, save_config, write_secret
from choice.load import DeckProblem
from choice.media import ServedMedia, prepare_bytes, prepare_file, snap_edge
from choice.media_warm import warm_file_paths
from choice.open_cache import bust_config, open_library
from choice.people import (
    assignment_warnings,
    drop_deck_from_roster,
    load_roster,
    parse_users,
    remove_roster,
    save_roster,
)
from choice.queue import page_items
from choice.sources.registry import build_source, source_types
from choice.web_paths import web_root

_WEB = web_root()
_LICENSE = Path(__file__).resolve().parents[1] / "LICENSE"
_ID = re.compile(r"[a-z0-9_-]+")
_STATIC = {
    "app.js": "text/javascript; charset=utf-8",
    "pile_nav.js": "text/javascript; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
}


class ChoiceSite(ThreadingHTTPServer):
    def __init__(
        self,
        address,
        root: Path,
        config_path: Path | None = None,
        base_path: str = "",
    ):
        self.choice_root = root
        self.config_path = config_path
        self.base_path = normalize_base_path(base_path)
        super().__init__(address, Handler)
        _boot_work_queue(self)


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

    def _route_parts(self, path: str) -> list[str] | None:
        parts = [p for p in path.split("/") if p]
        base = self.server.base_path
        if not base:
            return parts
        base_parts = [p for p in base.split("/") if p]
        if len(parts) < len(base_parts):
            return None
        if parts[: len(base_parts)] != base_parts:
            return None
        return parts[len(base_parts) :]

    def _get(self):
        parsed = urlparse(self.path)
        parts = self._route_parts(parsed.path)
        if parts is None:
            return self._json(404, {"ok": False, "message": "No such page."})
        if not parts:
            return self._index_page()
        if len(parts) == 1 and parts[0] in _STATIC:
            return self._static(parts[0], _STATIC[parts[0]])
        if parts == ["license"]:
            return self._license()
        if parts == ["api", "health"]:
            base = self.server.base_path
            return self._json(
                200,
                {"ok": True, "service": "choice", "base_path": base or "/"},
            )
        if parts == ["api", "index"]:
            return self._index(parse_qs(parsed.query))
        if parts == ["api", "feed"]:
            return self._feed(parse_qs(parsed.query))
        if parts == ["api", "config"]:
            return self._config_get()
        if parts == ["api", "source-types"]:
            return self._json(200, {"ok": True, "types": source_types()})
        if parts == ["api", "browse"]:
            return self._browse(parse_qs(parsed.query))
        if len(parts) == 5 and parts[:3] == ["api", "sources", "test"]:
            return self._source_test(parts[3], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "stats":
            return self._stats(parts[2], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "export":
            return self._export(parts[2], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "view":
            return self._deck_view(parts[2])
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "items":
            return self._items(parts[2], parse_qs(parsed.query))
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "decks" and parts[3] == "media":
            return self._media(parts[2], parse_qs(parsed.query))
        self._json(404, {"ok": False, "message": "No such page."})

    def _post(self):
        parsed = urlparse(self.path)
        parts = self._route_parts(parsed.path)
        if parts is None:
            return self._json(404, {"ok": False, "message": "No such page."})
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
        if kind == "action":
            deck = self._opened(parts[2], self._requested_user(parse_qs(parsed.query), body))
            if isinstance(deck, dict):
                return self._reply(deck)
            action_id = str(body.get("action") or body.get("id") or "")
            result = run_plugin_action(deck, action_id)
            return self._json(200 if result.get("ok") else 400, result)
        if kind == "view":
            deck = self._opened(parts[2], self._requested_user(parse_qs(parsed.query), body))
            if isinstance(deck, dict):
                return self._reply(deck)
            result = save_deck_view(deck, body)
            return self._json(200 if result.get("ok") else 400, result)
        if kind == "counts":
            deck = self._opened(parts[2], self._requested_user(parse_qs(parsed.query), body))
            if isinstance(deck, dict):
                return self._reply(deck)
            result = save_deck_counts(deck, body)
            return self._json(200 if result.get("ok") else 400, result)
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
            opened = open_library(self._library_path())
            roster = load_roster(self.server.choice_root)
        except DeckProblem as exc:
            return self._json(200, {"ok": False, "message": str(exc), "direct": True, "decks": []})
        deck_meta = _config_deck_meta(self.server.config_path)
        if not roster.enabled:
            return self._json(
                200,
                {
                    "ok": True,
                    "direct": opened.direct,
                    "decks": _rows(opened.decks, deck_meta),
                    "users": None,
                },
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
        payload["decks"] = _rows(chosen, deck_meta)
        self._json(200, payload)

    def _feed(self, query):
        try:
            opened = open_library(self._library_path())
            roster = load_roster(self.server.choice_root)
        except DeckProblem as exc:
            return self._json(200, {"ok": False, "message": str(exc), "decks": []})
        deck_meta = _config_deck_meta(self.server.config_path)
        decks = [d for d in opened.decks if not d.private_feed]
        if roster.enabled:
            user_id = self._requested_user(query, None)
            person = roster.get(user_id) if user_id else None
            if person is None:
                return self._json(200, {"ok": True, "decks": []})
            decks = [d for d in decks if person.sees(d.id)]
            for deck in decks:
                deck.actor = person.id
        return self._json(200, {"ok": True, "decks": _rows(decks, deck_meta)})

    def _deck_view(self, deck_id: str):
        deck = self._opened(deck_id, None)
        if isinstance(deck, dict):
            return self._reply(deck)
        from choice.view_prefs import public_view

        self._json(200, {"ok": True, "view": public_view(deck)})

    def _items(self, deck_id, query):
        deck = self._opened(deck_id, self._requested_user(query, None))
        if isinstance(deck, dict):
            return self._reply(deck)
        pending = query.get("pending", ["1"])[0] != "0"
        limit = int((query.get("limit") or ["0"])[0] or 0)
        offset = int((query.get("offset") or ["0"])[0] or 0)
        if deck.folder_scan is not None and limit <= 0:
            limit = 200
        snap = progress(deck, pending=pending, limit=limit, offset=offset)
        if limit > 0 and snap.get("ok") and snap.get("items") and deck.folder_scan is None:
            items = snap["items"]
            paged, token = page_items(deck.id, items, offset=offset, limit=limit)
            snap["items"] = paged
            snap["page_token"] = token
        if not snap.get("ok"):
            return self._json(200, snap)
        warnings = list(snap.get("warnings") or [])
        snap.update(deck.public_meta())
        snap["warnings"] = warnings
        self._warm_upcoming(deck, snap.get("items") or [], query)
        self._json(200, snap)

    def _media(self, deck_id, query):
        deck = self._opened(deck_id, self._requested_user(query, None))
        if isinstance(deck, dict):
            return self._reply(deck)
        item_id = (query.get("item") or [""])[0]
        side_key = (query.get("side") or [""])[0]
        version = (query.get("v") or [""])[0]
        n_raw = (query.get("n") or [""])[0]
        image_index = int(n_raw) if str(n_raw).isdigit() else None
        full, width = self._media_options(query)
        cache_dir = (deck.state_dir / "media_cache").resolve()
        try:
            item = item_by_id(deck, item_id)
        except DeckProblem as exc:
            return self._json(404, {"ok": False, "message": str(exc)})
        plugin = deck.plugin
        if plugin is not None and callable(getattr(plugin, "media_bytes", None)):
            if item is None:
                return self._json(404, {"ok": False, "message": "No such image."})
            row = item.plugin_row
            blob = plugin.media_bytes(item_id, item=row, index=image_index)
            if blob:
                data, ctype = blob[0], blob[1]
                identity = self._media_cache_identity(
                    deck.id, item_id, side_key, image_index, version
                )
                served = prepare_bytes(
                    data,
                    ctype,
                    cache_dir,
                    identity,
                    full=full,
                    width=width,
                    etag_version=version,
                )
                return self._send_media(served)
        source = _media_source(item, side_key, image_index)
        if source is None or not source.is_file():
            return self._json(404, {"ok": False, "message": "No such image."})
        served = prepare_file(
            source.resolve(),
            cache_dir,
            full=full,
            width=width,
            etag_version=version,
        )
        cache = cache_dir
        if served.path is not None:
            path = served.path.resolve()
            if path != source.resolve() and cache not in path.parents:
                served = prepare_file(source.resolve(), cache_dir, full=True, etag_version=version)
        return self._send_media(served)

    def _media_options(self, query) -> tuple[bool, int | None]:
        full = (query.get("full") or ["0"])[0].lower() in {"1", "true", "yes"}
        w_raw = (query.get("w") or [""])[0]
        if str(w_raw).isdigit() and int(w_raw) > 0:
            return full, snap_edge(int(w_raw))
        return full, None

    def _warm_upcoming(self, deck, rows: list[dict], query) -> None:
        if not rows or getattr(deck, "folder_scan", None) is None:
            return
        w_raw = (query.get("w") or [""])[0]
        width = snap_edge(int(w_raw)) if str(w_raw).isdigit() else None
        root = deck.root.resolve()
        paths: list[Path] = []
        for row in rows[:4]:
            item_id = str(row.get("id") or "")
            if not item_id:
                continue
            candidate = (root / item_id).resolve()
            if candidate.is_file():
                paths.append(candidate)
        if paths:
            warm_file_paths(paths, deck.state_dir / "media_cache", width)

    def _media_cache_identity(
        self,
        deck_id: str,
        item_id: str,
        side_key: str,
        image_index: int | None,
        version: str,
    ) -> str:
        side = side_key or "-"
        index = str(image_index) if image_index is not None else "-"
        token = version or "-"
        return f"{deck_id}|{item_id}|{side}|{index}|{token}"

    def _send_media(self, served: ServedMedia) -> None:
        if served.etag and self.headers.get("If-None-Match") == served.etag:
            self.send_response(304)
            self.send_header("ETag", served.etag)
            self.send_header("Cache-Control", served.cache_control)
            self.end_headers()
            return
        try:
            if served.data is not None:
                payload = served.data
            elif served.path is not None:
                payload = served.path.read_bytes()
            else:
                return self._json(404, {"ok": False, "message": "No such image."})
        except OSError:
            return self._json(404, {"ok": False, "message": "That image could not be read."})
        self.send_response(200)
        self.send_header("Content-Type", served.content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", served.cache_control)
        if served.etag:
            self.send_header("ETag", served.etag)
        self.end_headers()
        self.wfile.write(payload)

    def _save_users(self, body):
        try:
            opened = open_library(self._library_path())
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
            opened = open_library(self._library_path())
        except DeckProblem as exc:
            return {"ok": False, "message": str(exc)}
        for deck in opened.decks:
            if deck.id == deck_id:
                return deck
        return {"ok": False, "message": "No such deck."}

    def _index_page(self):
        path = _WEB / "index.html"
        if not path.is_file():
            return self._json(500, {"ok": False, "message": "Choice is missing its page files."})
        text = path.read_text(encoding="utf-8")
        base = self.server.base_path
        content = base if base else "/"
        href = _base_href(base)
        inject = (
            f'<meta name="choice-base" content="{html.escape(content, quote=True)}">\n'
            f'<base href="{html.escape(href, quote=True)}">'
        )
        if "<head>" in text:
            text = text.replace("<head>", "<head>\n" + inject, 1)
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

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
        old_ids = {d.id for d in cfg.decks}
        save_config(cfg, sources, decks)
        new_ids = {str(row.get("id") or "") for row in decks if isinstance(row, dict)}
        removed = old_ids - new_ids
        if removed:
            bust_config(path)
            for deck_id in removed:
                drop_deck_from_roster(self.server.choice_root, deck_id)
        else:
            bust_config(path)
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
        from choice.work_queue import failures_for
        from choice.work_queue import snapshot_for as queue_snapshot

        plugin = deck.plugin
        qsnap = queue_snapshot(deck)
        queue_payload = qsnap.to_dict()
        if qsnap.failed:
            queue_payload["failures"] = failures_for(deck)
        if plugin is not None and hasattr(plugin, "stats"):
            data = plugin.stats()
            if data:
                data = dict(data)
                data["queue"] = queue_payload
                return self._json(200, {"ok": True, "stats": data})
        snap = progress(deck, pending=False, limit=1, offset=0)
        payload = {"tally": snap.get("tally"), "total": snap.get("total")}
        payload["queue"] = queue_payload
        return self._json(200, {"ok": True, "stats": payload})

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

    def _browse(self, query):
        path = self.server.config_path
        if path is None:
            return self._json(400, {"ok": False, "message": "No config."})
        source_id = (query.get("source") or query.get("source_id") or [""])[0]
        sub = (query.get("path") or [""])[0] or ""
        try:
            cfg = load_config(path)
        except ConfigProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        if not source_id:
            roots = []
            for spec in cfg.sources:
                if spec.type not in {"folder", "swipe", "swipe_plugin"}:
                    continue
                try:
                    src = build_source(spec, cfg)
                    root = _folder_source_root(src)
                    roots.append(
                        {
                            "source": spec.id,
                            "type": spec.type,
                            "label": spec.id,
                            "path": str(root),
                        }
                    )
                except ConfigProblem:
                    continue
            return self._json(200, {"ok": True, "roots": roots})
        spec = cfg.source(source_id)
        if spec is None:
            return self._json(404, {"ok": False, "message": "No such source."})
        if spec.type not in {"folder", "swipe", "swipe_plugin"}:
            return self._json(
                400,
                {"ok": False, "message": "Browse only works for folder sources."},
            )
        try:
            src = build_source(spec, cfg)
            entries = _list_folder_entries(src, sub)
        except ConfigProblem as exc:
            return self._json(400, {"ok": False, "message": str(exc)})
        return self._json(200, {"ok": True, "path": sub, "entries": entries})

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


def _config_deck_meta(config_path: Path | None) -> dict[str, dict]:
    if config_path is None or not config_path.is_file():
        return {}
    try:
        cfg = load_config(config_path)
    except ConfigProblem:
        return {}
    src_type = {s.id: s.type for s in cfg.sources}
    out: dict[str, dict] = {}
    for spec in cfg.decks:
        out[spec.id] = {"source": spec.source, "source_type": src_type.get(spec.source, "")}
    return out


def _folder_source_root(src) -> Path:
    from choice.sources.folder import FolderSource

    if isinstance(src, FolderSource):
        return src._root()
    raw = src.options.get("path") or src.options.get("root") or "."
    base = src.app_config.path.parent
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return path.resolve()


def _list_folder_entries(src, sub: str) -> list[dict]:
    from choice.load import inside

    root = _folder_source_root(src)
    sub = sub.strip().replace("\\", "/").strip("/")
    target = (root / sub).resolve() if sub else root.resolve()
    if not inside(root, target) and target != root.resolve():
        raise ConfigProblem("Path escapes source folder.")
    if not target.is_dir():
        raise ConfigProblem("Not a folder.")
    entries: list[dict] = []
    try:
        children = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise ConfigProblem(str(exc)) from exc
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            rel = child.relative_to(root).as_posix()
            entries.append({"name": child.name, "path": rel, "kind": "dir"})
    return entries


def _rows(decks, deck_meta: dict[str, dict] | None = None) -> list[dict]:
    deck_meta = deck_meta or {}
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
        snap = index_summary(deck)
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
            "total": snap.get("total"),
            "decided": snap["decided"],
            "left": snap.get("left"),
            "private": deck.private_feed,
        }
        if snap.get("list_size") is not None:
            row["list_size"] = snap["list_size"]
        meta = deck_meta.get(deck.id)
        if meta:
            row["source"] = meta.get("source")
            row["source_type"] = meta.get("source_type")
        if snap.get("count_label"):
            row["count_label"] = snap["count_label"]
        if snap.get("stale"):
            row["stale"] = True
        if snap.get("meter") is False:
            row["meter"] = False
        elif snap.get("meter") is True:
            row["meter"] = True
        if snap.get("counts_hidden"):
            row["counts_hidden"] = True
        rows.append(row)
    return rows


def normalize_base_path(raw: str | None) -> str:
    """URL prefix without trailing slash; '' means site root."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text or text == "/":
        return ""
    if not text.startswith("/"):
        text = "/" + text
    parts = [p for p in text.split("/") if p]
    if not parts:
        return ""
    return "/" + "/".join(parts)


def _base_href(base: str) -> str:
    if not base:
        return "/"
    return base.rstrip("/") + "/"


def _media_source(item, side_key: str, image_index: int | None = None):
    """The file for this card, or for one side of a pair. Nothing else."""
    if item is None:
        return None
    if side_key:
        if item.kind != "pair" or side_key not in {"a", "b"}:
            return None
        side = next((side for side in item.sides if side.key == side_key), None)
        return side.path if side is not None else None
    if image_index is not None and item.images:
        if 0 <= image_index < len(item.images):
            from pathlib import Path

            candidate = Path(item.images[image_index]["path"])
            if candidate.is_file():
                return candidate
            return None
    if item.kind in {"image", "gallery"}:
        if item.path is not None and item.path.is_file():
            return item.path
    return None


def _boot_work_queue(server: ChoiceSite) -> None:
    from choice.folder_index import kick_background_scan
    from choice.work_queue import boot_deck, resume_workers, set_deck_resolver

    def _resolve(deck_id: str, actor: str):
        lib = server.config_path if server.config_path is not None else server.choice_root
        try:
            opened = open_library(lib)
        except DeckProblem:
            return None
        for deck in opened.decks:
            if deck.id == deck_id:
                if actor:
                    deck.actor = actor
                return deck
        return None

    set_deck_resolver(_resolve)
    lib = server.config_path if server.config_path is not None else server.choice_root
    try:
        opened = open_library(lib)
    except DeckProblem:
        opened = None
    if opened is not None:
        if server.config_path is not None and server.config_path.is_file():
            try:
                cfg = load_config(server.config_path)
                resume_workers(cfg.state_dir)
            except ConfigProblem:
                pass
        else:
            seen: set[Path] = set()
            for deck in opened.decks:
                key = deck.state_dir.resolve()
                if key in seen:
                    continue
                seen.add(key)
                resume_workers(deck.state_dir)
        for deck in opened.decks:
            boot_deck(deck)
            kick_background_scan(deck)


def serve(
    root: Path,
    host: str,
    port: int,
    config_path: Path | None = None,
    base_path: str = "",
) -> None:
    ChoiceSite.allow_reuse_address = True
    try:
        server = ChoiceSite(
            (host, port),
            root,
            config_path=config_path,
            base_path=base_path,
        )
    except OSError as exc:
        raise SystemExit(f"Cannot listen on {host}:{port} ({exc.strerror or exc}).") from exc
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
