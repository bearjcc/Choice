# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP handlers for /api/admin/* (Server Admin panel)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from choice import __version__
from choice.config import ConfigProblem, load_config, save_config
from choice.hw_probe import probe_codecs, probe_hw_accel
from choice.image_delivery import preview_transcode
from choice.load import DeckProblem
from choice.people import load_roster, parse_users, roster_path, save_roster
from choice.config import _expand
from choice.config_schema import schema_for_api
from choice.server_settings import merge_server_patch, network_restart_required


def apply_admin_settings(cfg, patch: dict) -> None:
    """Merge admin UI patch into AppConfig (not yet saved)."""
    title = patch.get("title")
    if title is not None and str(title).strip():
        cfg.app_title = str(title).strip()
    state = patch.get("state")
    if isinstance(state, dict):
        if state.get("dir"):
            cfg.state_dir = _expand(str(state["dir"]), cfg.path.parent)
        if state.get("secrets_file"):
            cfg.secrets_file = _expand(str(state["secrets_file"]), cfg.path.parent)
        elif "secrets_file" in state and not state.get("secrets_file"):
            cfg.secrets_file = None
        if state.get("users_file"):
            cfg.roster_path = _expand(str(state["users_file"]), cfg.path.parent)
        elif "users_file" in state and not state.get("users_file"):
            cfg.roster_path = None
    client = patch.get("client")
    if isinstance(client, dict) and client.get("buffer"):
        cfg.client_buffer = max(1, int(client["buffer"]))
    server_bits = {
        k: patch[k]
        for k in ("network", "http", "images")
        if isinstance(patch.get(k), dict)
    }
    if server_bits:
        cfg.server = merge_server_patch(cfg.server, server_bits)


def admin_config_schema_get(handler: "Handler", query) -> None:
    user_id = handler._requested_user(query, None)
    if not handler._config_admin_allowed(user_id):
        handler._json(403, {"ok": False, "message": "Only the server owner can use Server admin."})
        return
    payload = schema_for_api()
    payload["ok"] = True
    handler._json(200, payload)

if TYPE_CHECKING:
    from choice.httpd import Handler


def _require_admin(handler: "Handler", body: dict | None) -> bool:
    user_id = handler._requested_user(None, body or {})
    if not handler._config_admin_allowed(user_id):
        handler._json(
            403,
            {"ok": False, "message": "Only the server owner can use Server admin."},
        )
        return False
    return True


def admin_server_get(handler: "Handler", query) -> None:
    user_id = handler._requested_user(query, None)
    if not handler._config_admin_allowed(user_id):
        handler._json(
            403,
            {"ok": False, "message": "Only the server owner can use Server admin."},
        )
        return
    path = handler.server.config_path
    if path is None or not path.is_file():
        handler._json(400, {"ok": False, "message": "No config file."})
        return
    try:
        cfg = load_config(path)
    except ConfigProblem as exc:
        handler._json(400, {"ok": False, "message": str(exc)})
        return
    codecs = probe_codecs()
    hw = probe_hw_accel(cfg.server.images.hw_accel if cfg.server else "auto")
    handler._json(
        200,
        {
            "ok": True,
            "version": __version__,
            "uptime_sec": max(0, int(time.time() - handler.server.started_at)),
            "settings": cfg.server.public_dict() if cfg.server else {},
            "app_title": cfg.app_title,
            "state_dir": str(cfg.state_dir),
            "secrets_file": str(cfg.secrets_file) if cfg.secrets_file else "",
            "users_file": str(cfg.roster_path) if cfg.roster_path else "",
            "client_buffer": cfg.client_buffer,
            "codecs": codecs,
            "hw_accel": hw.public(),
            "running": {
                "host": handler.server.bind_host,
                "port": handler.server.bind_port,
                "base_path": handler.server.base_path,
            },
        },
    )


def admin_server_patch(handler: "Handler", body: dict) -> None:
    if not _require_admin(handler, body):
        return
    path = handler.server.config_path
    if path is None:
        handler._json(400, {"ok": False, "message": "No config."})
        return
    confirm = bool(body.get("confirm_restart"))
    patch = body.get("settings")
    if patch is None:
        handler._json(400, {"ok": False, "message": "Send settings object."})
        return
    try:
        before = load_config(path)
        cfg = load_config(path)
        apply_admin_settings(cfg, patch)
        merged = cfg.server
        restart = network_restart_required(
            merged.network,
            handler.server.bind_host,
            handler.server.bind_port,
            handler.server.base_path,
        )
        if str(before.state_dir) != str(cfg.state_dir):
            restart = True
        if restart and not confirm:
            handler._json(
                409,
                {
                    "ok": False,
                    "restart_required": True,
                    "message": "Network changes need a restart. Confirm to save.",
                },
            )
            return
        sources = [
            {"id": s.id, "type": s.type, **s.options} for s in cfg.sources
        ]
        decks = [
            {"id": d.id, "title": d.title, "source": d.source, "mount": d.mount, **d.options}
            for d in cfg.decks
        ]
        save_config(cfg, sources, decks)
        handler._json(
            200,
            {"ok": True, "restart_required": restart, "settings": merged.public_dict()},
        )
    except ConfigProblem as exc:
        handler._json(400, {"ok": False, "message": str(exc)})


def admin_sessions_get(handler: "Handler", query) -> None:
    user_id = handler._requested_user(query, None)
    if not handler._config_admin_allowed(user_id):
        handler._json(403, {"ok": False, "message": "Only the server owner can use Server admin."})
        return
    handler._json(200, {"ok": True, "sessions": handler.server.sessions.list_sessions()})


def admin_sessions_revoke(handler: "Handler", body: dict) -> None:
    if not _require_admin(handler, body):
        return
    sid = str(body.get("session_id") or "").strip()
    if not sid:
        handler._json(400, {"ok": False, "message": "Send session_id."})
        return
    handler.server.sessions.revoke(sid)
    handler._json(200, {"ok": True})


def admin_restart(handler: "Handler", body: dict) -> None:
    if not _require_admin(handler, body):
        return
    if not body.get("confirm"):
        handler._json(400, {"ok": False, "message": "Send confirm: true to restart."})
        return
    argv = (
        getattr(handler.server, "restart_argv", None)
        or getattr(sys, "orig_argv", None)
        or [sys.executable, "-m", "choice"]
    )
    handler._json(200, {"ok": True, "restarting": True})
    handler.wfile.flush()
    try:
        os.execv(argv[0], argv)
    except OSError:
        os._exit(75)


def admin_transcode_preview(handler: "Handler", body: dict) -> None:
    if not _require_admin(handler, body):
        return
    path = handler.server.config_path
    if path is None:
        handler._json(400, {"ok": False, "message": "No config."})
        return
    sample = body.get("sample_path")
    if not sample:
        handler._json(400, {"ok": False, "message": "Send sample_path to an image on disk."})
        return
    try:
        cfg = load_config(path)
        patch = body.get("settings") or {}
        profile = merge_server_patch(cfg.server, {"images": patch}).images
        src = Path(str(sample)).expanduser()
        if not src.is_file():
            handler._json(400, {"ok": False, "message": "Sample image not found."})
            return
        result = preview_transcode(src.resolve(), profile)
        handler._json(200, result)
    except ConfigProblem as exc:
        handler._json(400, {"ok": False, "message": str(exc)})


def admin_users_patch(handler: "Handler", body: dict) -> None:
    if not _require_admin(handler, body):
        return
    root = handler.server.choice_root
    users_raw = body.get("users")
    owner = body.get("owner")
    if users_raw is None and owner is None:
        handler._json(400, {"ok": False, "message": "Send users and/or owner."})
        return
    try:
        roster = load_roster(root)
        deck_ids = set()
        path = handler.server.config_path
        if path and path.is_file():
            cfg = load_config(path)
            deck_ids = {d.id for d in cfg.decks}
        people = roster.people
        if users_raw is not None:
            people = parse_users(users_raw, deck_ids)
        save_roster(root, people)
        if owner is not None:
            data_path = roster_path(root)
            import json

            data = json.loads(data_path.read_text(encoding="utf-8"))
            data["owner"] = str(owner).strip()
            data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        handler._json(200, {"ok": True})
    except (ConfigProblem, DeckProblem) as exc:
        handler._json(400, {"ok": False, "message": str(exc)})

