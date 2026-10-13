# SPDX-License-Identifier: AGPL-3.0-only
"""Canonical choice.toml keys and admin UI coverage registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Surface = Literal["server", "deck", "source"]


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    help: str
    surface: Surface
    field_type: str  # text, number, bool, select, path, secret, string_list, json
    default: Any = None
    advanced: bool = False
    section: str = ""
    options: tuple[tuple[str, str], ...] = ()
    source_types: tuple[str, ...] = ()  # empty = all deck keys; for source fields
    restart: bool = False


# Keys intentionally not in admin UI (with reason for drift test).
NOT_EXPOSED: dict[str, str] = {
    "client.preload": "Alias of client.buffer; loader accepts either, UI exposes buffer only.",
    "network.trust_proxy": "Alias of network.trust_forwarded.",
    "decks.path": "Alias of decks.mount in loader.",
    "sources.root": "Alias of sources.path.",
    "sources.user": "Alias of sources.username for WebDAV.",
    "sources.key": "Alias of sources.api_key for Immich.",
    "decks.output_mode": "Alias of decks.output.",
    "decks.include_globs": "Alias of decks.include.",
    "decks.exclude_globs": "Alias of decks.exclude.",
    "decks.undo": "Alias of decks.allow_undo.",
    "decks.sort": "Use sort_right/sort_left or nested sort_targets; no separate control.",
    "decks.sort_targets": "Derived from sort_* keys in folder decks.",
    "decks.directions": "Swipe/plugin JSON; edit deck.json offline.",
    "decks.hook": "deck.json only; not used in choice.toml decks.",
    "decks.story": "deck.json only.",
    "decks.score": "deck.json only.",
    "decks.buttons": "deck.json only.",
    "decks.show": "deck.json only.",
    "decks.legacy_log": "Rejected by loader.",
    "sources.output": "Folder output belongs on deck row.",
    "sources.recursive": "Folder recursion belongs on deck row.",
    "sources.include": "Folder globs belong on deck row.",
    "sources.exclude": "Folder globs belong on deck row.",
    "decks.id": "Generated in deck wizard from title; structural [[decks]] key.",
    "decks.title": "Primary deck wizard field.",
    "decks.source": "Picked via source linkage in wizard.",
    "sources.id": "Generated when adding a deck.",
    "sources.type": "Wizard step 1 source type.",
}


def _fields() -> list[ConfigField]:
    return [
        ConfigField(
            "title",
            "Instance title",
            "Tab and header name (CHOICE_TITLE / --title override at runtime).",
            "server",
            "text",
            "Choice",
            section="general",
        ),
        ConfigField(
            "state.dir",
            "State directory",
            "Per-instance state, indexes, and media cache roots.",
            "server",
            "path",
            ".choice-state",
            section="state",
            restart=True,
        ),
        ConfigField(
            "state.secrets_file",
            "Secrets file",
            "Optional key=value file for API keys (config stores env var names only).",
            "server",
            "path",
            "",
            section="state",
            advanced=True,
        ),
        ConfigField(
            "state.users_file",
            "Users file",
            "Override path to users.json (People mode).",
            "server",
            "path",
            "",
            section="state",
            advanced=True,
        ),
        ConfigField(
            "client.buffer",
            "Decide buffer",
            "Cards preloaded ahead on the client (CHOICE_CLIENT_BUFFER).",
            "server",
            "number",
            30,
            section="client",
        ),
        ConfigField(
            "network.host",
            "Bind host",
            "Address the server listens on after restart.",
            "server",
            "text",
            "127.0.0.1",
            section="network",
            restart=True,
        ),
        ConfigField(
            "network.port",
            "Port",
            "TCP port after restart.",
            "server",
            "number",
            8741,
            section="network",
            restart=True,
        ),
        ConfigField(
            "network.base_path",
            "Base path",
            "URL prefix when behind a subpath (CHOICE_BASE_PATH).",
            "server",
            "text",
            "",
            section="network",
            restart=True,
        ),
        ConfigField(
            "network.public_url",
            "Public URL",
            "Displayed link for operators (does not change bind).",
            "server",
            "text",
            "",
            section="network",
            advanced=True,
        ),
        ConfigField(
            "network.tls_cert",
            "TLS certificate",
            "Path to certificate (terminate TLS in proxy or future native TLS).",
            "server",
            "path",
            "",
            section="network",
            advanced=True,
            restart=True,
        ),
        ConfigField(
            "network.tls_key",
            "TLS private key",
            "Path to private key file.",
            "server",
            "path",
            "",
            section="network",
            advanced=True,
            restart=True,
        ),
        ConfigField(
            "network.trust_forwarded",
            "Trust forwarded headers",
            "Behind reverse proxy: trust X-Forwarded-* for client IP/scheme.",
            "server",
            "bool",
            False,
            section="network",
            restart=True,
        ),
        ConfigField(
            "http.compress",
            "Compression",
            "Compress JSON/text responses when the client accepts encoding.",
            "server",
            "select",
            "gzip",
            section="http",
            options=(("off", "Off"), ("gzip", "Gzip"), ("brotli", "Brotli"), ("both", "Brotli then gzip")),
        ),
        ConfigField(
            "images.transcode",
            "Transcode on serve",
            "Serve smaller variants for large images (original still via full=).",
            "server",
            "bool",
            False,
            section="images",
        ),
        ConfigField(
            "images.format",
            "Transcode format",
            "AVIF/JXL only when optional codecs are installed.",
            "server",
            "select",
            "original",
            section="images",
            options=(
                ("original", "Original"),
                ("webp", "WebP"),
                ("avif", "AVIF"),
                ("jxl", "JXL"),
            ),
        ),
        ConfigField(
            "images.max_edge",
            "Max long edge (px)",
            "Resize cap for transcoded variants.",
            "server",
            "number",
            2048,
            section="images",
        ),
        ConfigField(
            "images.quality",
            "Quality",
            "Encoder quality for lossy formats (1–100).",
            "server",
            "number",
            85,
            section="images",
        ),
        ConfigField(
            "images.min_bytes",
            "Min file size (bytes)",
            "Only transcode files at least this large.",
            "server",
            "number",
            512_000,
            section="images",
            advanced=True,
        ),
        ConfigField(
            "images.min_edge",
            "Min long edge (px)",
            "Only transcode when the source long edge exceeds this.",
            "server",
            "number",
            1280,
            section="images",
            advanced=True,
        ),
        ConfigField(
            "images.hw_accel",
            "Hardware path",
            "Optional ffmpeg/libvips; Pillow CPU is always available.",
            "server",
            "select",
            "auto",
            section="images",
            advanced=True,
            options=(
                ("auto", "Auto"),
                ("off", "CPU only"),
                ("pillow", "Pillow pool"),
                ("ffmpeg", "ffmpeg"),
                ("vips", "libvips"),
            ),
        ),
        # --- Source fields (per [[sources]]) ---
        ConfigField(
            "sources.path",
            "Source path",
            "Folder or swipe plugin root on disk.",
            "source",
            "path",
            "",
            section="source",
            source_types=("folder", "swipe", "swipe_plugin", "ursala_swipe"),
        ),
        ConfigField(
            "sources.url",
            "URL",
            "Immich base URL, RSS feed, or WebDAV endpoint.",
            "source",
            "text",
            "",
            section="source",
            source_types=("immich", "rss", "atom", "webdav"),
        ),
        ConfigField(
            "sources.username",
            "Username",
            "WebDAV username (env ref recommended).",
            "source",
            "text",
            "",
            section="source",
            source_types=("webdav",),
        ),
        ConfigField(
            "sources.api_key",
            "API key env name",
            "Immich: name of env var holding the key (not the secret value).",
            "source",
            "secret",
            "IMMICH_API_KEY",
            section="source",
            source_types=("immich",),
        ),
        ConfigField(
            "sources.password",
            "Password env name",
            "WebDAV: env var name for password.",
            "source",
            "secret",
            "WEBDAV_PASSWORD",
            section="source",
            source_types=("webdav",),
            advanced=True,
        ),
        ConfigField(
            "sources.exclude_archived",
            "Exclude archived",
            "Immich: skip archived assets.",
            "source",
            "bool",
            True,
            section="source",
            source_types=("immich",),
            advanced=True,
        ),
        # --- Deck fields (per [[decks]] options) ---
        ConfigField(
            "decks.mount",
            "Mount path",
            "Subpath within the source (folder relative path or plugin id).",
            "deck",
            "text",
            ".",
            section="deck",
        ),
        ConfigField(
            "decks.output",
            "Output mode",
            "Log decisions only or move files into sort folders.",
            "deck",
            "select",
            "results",
            section="deck",
            source_types=("folder",),
            options=(("results", "Results"), ("sort", "Sort into folders")),
        ),
        ConfigField(
            "decks.recursive",
            "Recursive scan",
            "Include subfolders when scanning.",
            "deck",
            "bool",
            False,
            section="deck",
            source_types=("folder",),
        ),
        ConfigField(
            "decks.include",
            "Include globs",
            "Comma-separated globs (e.g. *.jpg).",
            "deck",
            "string_list",
            [],
            section="deck",
            source_types=("folder",),
            advanced=True,
        ),
        ConfigField(
            "decks.exclude",
            "Exclude globs",
            "Comma-separated globs to skip.",
            "deck",
            "string_list",
            [],
            section="deck",
            source_types=("folder",),
            advanced=True,
        ),
        ConfigField(
            "decks.sort_right",
            "Sort folder: right",
            "Target folder for right swipes when output=sort.",
            "deck",
            "text",
            "keep",
            section="deck",
            source_types=("folder",),
            advanced=True,
        ),
        ConfigField(
            "decks.sort_left",
            "Sort folder: left",
            "Target folder for left swipes.",
            "deck",
            "text",
            "reject",
            section="deck",
            source_types=("folder",),
            advanced=True,
        ),
        ConfigField(
            "decks.sort_up",
            "Sort folder: up",
            "Optional up direction folder.",
            "deck",
            "text",
            "",
            section="deck",
            source_types=("folder",),
            advanced=True,
        ),
        ConfigField(
            "decks.sort_down",
            "Sort folder: down",
            "Optional down direction folder.",
            "deck",
            "text",
            "",
            section="deck",
            source_types=("folder",),
            advanced=True,
        ),
        ConfigField(
            "decks.sort_mode",
            "Sort mode",
            "How folder piles are ordered in the UI.",
            "deck",
            "text",
            "",
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.file_types",
            "File types",
            "Restrict folder view (e.g. image).",
            "deck",
            "string_list",
            [],
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.include_folders",
            "Include folders",
            "Limit scan to folder names.",
            "deck",
            "string_list",
            [],
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.exclude_folders",
            "Exclude folders",
            "Folder names to skip.",
            "deck",
            "string_list",
            [],
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.random_seed",
            "Random seed",
            "Seed for shuffled folder order.",
            "deck",
            "text",
            "",
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.blind",
            "Blind mode default",
            "Start with faces/text hidden.",
            "deck",
            "bool",
            False,
            section="deck",
        ),
        ConfigField(
            "decks.private",
            "Private feed",
            "Hide deck activity from shared home feed.",
            "deck",
            "bool",
            False,
            section="deck",
        ),
        ConfigField(
            "decks.notify",
            "Show in feed",
            "When false, same as private feed.",
            "deck",
            "bool",
            True,
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.allow_undo",
            "Allow undo",
            "Let users undo the last swipe.",
            "deck",
            "bool",
            True,
            section="deck",
        ),
        ConfigField(
            "decks.show_filename",
            "Show filename",
            "Show file names on cards.",
            "deck",
            "bool",
            False,
            section="deck",
        ),
        ConfigField(
            "decks.pair_layout",
            "Pair layout",
            "Layout for A/B pair cards.",
            "deck",
            "select",
            "auto",
            section="deck",
            advanced=True,
            options=(("auto", "Auto"), ("stack", "Stack"), ("side_by_side", "Side by side")),
        ),
        ConfigField(
            "decks.counts",
            "Counts display",
            "Count label mode: auto, on, off, or JSON prefs.",
            "deck",
            "text",
            "",
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.view",
            "View JSON",
            "Advanced view/sort JSON (merged with sort_mode/file_types).",
            "deck",
            "json",
            None,
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.images",
            "Image delivery override",
            "Per-deck transcode override (inline table).",
            "deck",
            "json",
            None,
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.page_size",
            "Page size",
            "Immich deck page size.",
            "deck",
            "number",
            0,
            section="deck",
            source_types=("immich",),
            advanced=True,
        ),
        ConfigField(
            "decks.favourite",
            "Favourites only",
            "Immich: only favourite assets.",
            "deck",
            "bool",
            False,
            section="deck",
            source_types=("immich",),
            advanced=True,
        ),
        ConfigField(
            "decks.contest",
            "Contest mode",
            "Contest/taste/rated shorthand on deck.",
            "deck",
            "text",
            "",
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.taste",
            "Taste mode",
            "Enable taste-ranking contest.",
            "deck",
            "bool",
            False,
            section="deck",
            advanced=True,
        ),
        ConfigField(
            "decks.rated",
            "Rated mode",
            "Enable rated contest.",
            "deck",
            "bool",
            False,
            section="deck",
            advanced=True,
        ),
    ]


FIELDS: tuple[ConfigField, ...] = tuple(_fields())


def schema_for_api() -> dict[str, Any]:
    return {
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "help": f.help,
                "surface": f.surface,
                "type": f.field_type,
                "default": f.default,
                "advanced": f.advanced,
                "section": f.section,
                "options": [{"value": v, "label": l} for v, l in f.options],
                "source_types": list(f.source_types),
                "restart": f.restart,
            }
            for f in FIELDS
        ],
        "not_exposed": NOT_EXPOSED,
    }


def ui_exposed_keys() -> set[str]:
    return {f.key for f in FIELDS}


def all_loader_keys() -> set[str]:
    """Every key choice.toml loader may consume (including aliases)."""
    keys = set(ui_exposed_keys()) | set(NOT_EXPOSED.keys())
    keys.update(
        {
            "decks.id",
            "decks.title",
            "decks.source",
            "sources.id",
            "sources.type",
        }
    )
    return keys


def validate_ui_coverage(js_text: str) -> list[str]:
    """Return config keys that must appear as data-config-key in JS but do not."""
    import re

    found = set(re.findall(r'data-config-key="([^"]+)"', js_text))
    found |= set(re.findall(r'setAttribute\("data-config-key",\s*"([^"]+)"\)', js_text))
    if "ChoiceConfigUi.renderFields" in js_text:
        found |= {f.key for f in FIELDS if f.surface == "server"}
    if "ChoiceConfigUi.appendDeckFields" in js_text:
        found |= {f.key for f in FIELDS if f.surface == "deck"}
    missing = sorted(ui_exposed_keys() - found)
    return missing


def validate_registry_complete() -> list[str]:
    """Keys known to loader but neither exposed nor allowlisted."""
    problems = []
    for key in sorted(all_loader_keys()):
        if key in ui_exposed_keys() or key in NOT_EXPOSED:
            continue
        problems.append(key)
    return problems
