# SPDX-License-Identifier: AGPL-3.0-only
"""The command. `python -m choice --help` is the short version of the README."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import webbrowser
from pathlib import Path

from choice import __version__
from choice.act import tally_lines
from choice.config import resolve_app_title
from choice.env_config import env_flag, env_int
from choice.httpd import normalize_base_path, serve
from choice.load import DeckProblem
from choice.open import config_root, open_path
from choice.people import Roster, load_roster


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    args = _parser().parse_args(argv if argv is not None else None)
    config_path = None
    if args.config:
        config_path = Path(args.config).expanduser()
    elif os.environ.get("CHOICE_CONFIG"):
        config_path = Path(os.environ["CHOICE_CONFIG"]).expanduser()
    if config_path is not None:
        path = config_path
    else:
        path = Path(args.path).expanduser()
    try:
        opened = open_path(path)
    except DeckProblem as exc:
        print(exc)
        return 2

    roster = _roster(path)
    if isinstance(roster, str):
        print(roster)
        if args.tally:
            return 2
        roster = None

    if args.tally:
        _print_tally(opened.decks, roster)
        return 0

    if args.port < 1 or args.port > 65535:
        print("Port must be between 1 and 65535.")
        return 2

    host = "0.0.0.0" if args.lan else args.host
    exposed = host not in {"127.0.0.1", "::1", "localhost"}
    base_path = normalize_base_path(args.base_path)
    app_title = resolve_app_title(config_path, args.title)
    url = f"http://127.0.0.1:{args.port}{_base_href(base_path)}"
    print(f"{app_title} {__version__}", flush=True)
    if opened.direct and len(opened.decks) == 1:
        print(f"  {opened.decks[0].title}")
    else:
        print(f"  {len(opened.decks)} decks")
    if roster is not None and roster.enabled:
        word = "person" if len(roster.people) == 1 else "people"
        print(f"  {len(roster.people)} {word}")
    print(f"  {url}")
    if exposed:
        lan = _lan_ip()
        if lan and host in {"0.0.0.0", "::"}:
            print(f"  http://{lan}:{args.port}{_base_href(base_path)}")
        print(
            "WARNING: listening on the network. Anyone who can reach this port "
            "can label cards and move files."
        )
    else:
        print("Listening on this computer only. Pass --lan to use a phone on the same network.")
    print("Stop with Ctrl+C.", flush=True)
    sys.stdout.flush()
    if args.open:
        webbrowser.open(url)
    root = config_root(path) if config_path else path.expanduser().resolve()
    from choice.state_cleanup import cleanup_state_dirs

    cleanup_dirs = []
    if config_path is not None:
        try:
            from choice.config import load_config

            cfg = load_config(config_path)
            cleanup_dirs.append(cfg.state_dir)
        except Exception:
            pass
    for deck in opened.decks:
        cleanup_dirs.append(deck.state_dir)
    cleanup_state_dirs(cleanup_dirs)
    client_buffer = args.client_buffer
    if client_buffer is None and config_path is not None:
        try:
            from choice.config import load_config

            client_buffer = load_config(config_path).client_buffer
        except Exception:
            client_buffer = None
    from choice.client_buffer import buffer_size_from_env

    if client_buffer is None:
        client_buffer = buffer_size_from_env()
    serve(
        root,
        host,
        args.port,
        config_path=config_path.resolve() if config_path else None,
        base_path=base_path,
        app_title=app_title,
        client_buffer_size=client_buffer,
        restart_argv=[sys.executable, "-m", "choice", *sys.argv[1:]],
    )
    return 0


def _base_href(base_path: str) -> str:
    if not base_path:
        return "/"
    return base_path.rstrip("/") + "/"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m choice",
        description=(
            "Swipe through a pile and decide. Photos, rows, a quiz, "
            "a ranking, a bracket, or a branching story."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python -m choice examples\n"
            "  python -m choice examples/yes-no\n"
            "  python -m choice D:\\photos\n"
            "  python -m choice --lan D:\\photos\n"
            "  python -m choice --tally examples/yes-no\n"
            "\n"
            "A deck is a folder with deck.json, or a folder you point at.\n"
            "The format is DECKS.md. Decisions land in .choice/decisions.jsonl.\n"
            "Trash moves a file into .choice/trash. It does not delete it.\n"
            "People are optional: .choice/users.json gives each person a log\n"
            "and a list of decks. A name is not a password."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=os.environ.get("CHOICE_PATH", "."),
        help="deck folder, library folder, photo folder, or data file (CHOICE_PATH)",
    )
    parser.add_argument(
        "--config", help="choice.toml with sources and decks (or set CHOICE_CONFIG)"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("CHOICE_HOST", "127.0.0.1"),
        help="address to listen on (default: this computer only; CHOICE_HOST)",
    )
    parser.add_argument(
        "--lan",
        action="store_true",
        default=env_flag("CHOICE_LAN"),
        help="listen on the network, so a phone can open the page (CHOICE_LAN)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=env_int("CHOICE_PORT", 8741),
        help="port (default: 8741; CHOICE_PORT)",
    )
    parser.add_argument(
        "--base-path",
        default=os.environ.get("CHOICE_BASE_PATH", ""),
        help="URL prefix when behind a reverse proxy (e.g. /choice)",
    )
    parser.add_argument(
        "--title",
        default=os.environ.get("CHOICE_TITLE"),
        help="App name in the tab, header, and PWA manifest (overrides choice.toml title)",
    )
    parser.add_argument(
        "--client-buffer",
        type=int,
        default=None,
        help="Cards to preload and hold order-stable (default 30; CHOICE_CLIENT_BUFFER)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        default=env_flag("CHOICE_OPEN"),
        help="open the page in this computer's browser (CHOICE_OPEN)",
    )
    parser.add_argument("--tally", action="store_true", help="print decision counts and exit")
    parser.add_argument("--version", action="version", version=f"choice {__version__}")
    return parser


def _roster(path: Path) -> Roster | str | None:
    try:
        return load_roster(path)
    except DeckProblem as exc:
        return str(exc)


def _print_tally(decks, roster: Roster | None) -> None:
    people = roster.people if roster is not None and roster.enabled else []
    for deck in decks:
        print(deck.title)
        holders = [person for person in people if person.sees(deck.id)]
        if people and not holders:
            print("  Not assigned.")
            continue
        if not holders:
            for line in tally_lines(deck):
                print("  " + line)
            continue
        for person in holders:
            deck.actor = person.id
            print(f"  {person.name}")
            for line in tally_lines(deck):
                print("    " + line)
        deck.actor = None


def _lan_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 1))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()
