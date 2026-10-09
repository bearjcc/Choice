# SPDX-License-Identifier: AGPL-3.0-only
"""Persistent async work queue for file moves and plugin side effects."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from choice.load import Deck, inside

_QUEUE_NAME = "work_queue.json"
_MAX_ATTEMPTS = 12
_BACKOFF = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2)

_deck_resolver: Callable[[str, str], Deck | None] | None = None
_workers: dict[str, threading.Thread] = {}
_worker_lock = threading.Lock()
_dest_locks: dict[str, threading.Lock] = {}
_dest_guard = threading.Lock()


@dataclass
class WorkJob:
    id: str
    decision_id: str
    kind: str
    status: str = "pending"
    attempts: int = 0
    last_error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    file_op: dict | None = None
    plugin: dict | None = None
    deck_id: str = ""
    actor: str = ""
    deck_root: str = ""
    state_dir: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(row: dict) -> WorkJob:
        return WorkJob(
            id=str(row.get("id") or ""),
            decision_id=str(row.get("decision_id") or ""),
            kind=str(row.get("kind") or ""),
            status=str(row.get("status") or "pending"),
            attempts=int(row.get("attempts") or 0),
            last_error=str(row.get("last_error") or ""),
            created_at=float(row.get("created_at") or 0),
            updated_at=float(row.get("updated_at") or 0),
            file_op=row.get("file_op") if isinstance(row.get("file_op"), dict) else None,
            plugin=row.get("plugin") if isinstance(row.get("plugin"), dict) else None,
            deck_id=str(row.get("deck_id") or ""),
            actor=str(row.get("actor") or ""),
            deck_root=str(row.get("deck_root") or ""),
            state_dir=str(row.get("state_dir") or ""),
        )


@dataclass
class QueueSnapshot:
    pending: int
    running: int
    failed: int

    def to_dict(self) -> dict:
        return {"pending": self.pending, "running": self.running, "failed": self.failed}


def set_deck_resolver(fn: Callable[[str, str], Deck | None]) -> None:
    global _deck_resolver
    _deck_resolver = fn


def queue_path(deck: Deck) -> Path:
    return deck.state_dir / _QUEUE_NAME


def snapshot_for(deck: Deck) -> QueueSnapshot:
    jobs = _load_jobs(deck.state_dir)
    pending = sum(1 for j in jobs if j.status == "pending")
    running = sum(1 for j in jobs if j.status == "running")
    failed = sum(1 for j in jobs if j.status == "failed")
    return QueueSnapshot(pending=pending, running=running, failed=failed)


def enqueue_file_op(deck: Deck, decision_id: str, file_op: dict, *, reverse: bool = False) -> str:
    kind = "file_reverse" if reverse else "file"
    job = WorkJob(
        id=uuid.uuid4().hex,
        decision_id=decision_id,
        kind=kind,
        file_op=dict(file_op),
        deck_id=deck.id,
        actor=deck.actor or "",
        deck_root=str(deck.root.resolve()),
        state_dir=str(deck.state_dir.resolve()),
    )
    _append_job(deck.state_dir, job)
    _ensure_worker(deck.state_dir)
    return job.id


def enqueue_plugin(
    deck: Deck,
    decision_id: str,
    item_id: str,
    direction: str,
    note: str,
    *,
    undo: bool = False,
    undo_token: str | None = None,
) -> str:
    job = WorkJob(
        id=uuid.uuid4().hex,
        decision_id=decision_id,
        kind="plugin_undo" if undo else "plugin",
        plugin={
            "item_id": item_id,
            "direction": direction,
            "note": note,
            "undo_token": undo_token,
        },
        deck_id=deck.id,
        actor=deck.actor or "",
        deck_root=str(deck.root.resolve()),
        state_dir=str(deck.state_dir.resolve()),
    )
    _append_job(deck.state_dir, job)
    _ensure_worker(deck.state_dir)
    return job.id


def cancel_for_decision(deck: Deck, decision_id: str) -> int:
    jobs = _load_jobs(deck.state_dir)
    n = 0
    for job in jobs:
        if job.decision_id != decision_id:
            continue
        if job.status in {"pending"}:
            job.status = "cancelled"
            job.updated_at = time.time()
            n += 1
    if n:
        _save_jobs(deck.state_dir, jobs)
    return n


def resume_workers(state_root: Path) -> None:
    if not state_root.is_dir():
        return
    for child in state_root.iterdir():
        if not child.is_dir():
            continue
        path = child / _QUEUE_NAME
        if not path.is_file():
            continue
        jobs = _load_jobs(child)
        if any(j.status in {"pending", "running"} for j in jobs):
            _ensure_worker(child)


def _ensure_worker(state_dir: Path) -> None:
    if os.environ.get("CHOICE_SYNC_WORK"):
        _worker_loop(state_dir)
        return
    key = str(state_dir.resolve())
    with _worker_lock:
        thread = _workers.get(key)
        if thread and thread.is_alive():
            return
        thread = threading.Thread(
            target=_worker_loop,
            args=(state_dir,),
            name=f"work-{state_dir.name}",
            daemon=True,
        )
        _workers[key] = thread
        thread.start()


def _worker_loop(state_dir: Path) -> None:
    while True:
        jobs = _load_jobs(state_dir)
        next_job = next((j for j in jobs if j.status == "pending"), None)
        if next_job is None:
            return
        next_job.status = "running"
        next_job.updated_at = time.time()
        _save_jobs(state_dir, jobs)
        ok = _run_job(state_dir, next_job)
        jobs = _load_jobs(state_dir)
        for job in jobs:
            if job.id != next_job.id:
                continue
            if ok:
                job.status = "done"
                job.last_error = ""
            elif job.status == "cancelled":
                break
            else:
                job.attempts += 1
                if job.attempts >= _MAX_ATTEMPTS:
                    job.status = "failed"
                else:
                    job.status = "pending"
                    delay = _BACKOFF[min(job.attempts - 1, len(_BACKOFF) - 1)]
                    time.sleep(delay)
            job.updated_at = time.time()
            break
        _save_jobs(state_dir, jobs)
        if not ok and next_job.status == "pending":
            continue


def _run_job(state_dir: Path, job: WorkJob) -> bool:
    if job.status == "cancelled":
        return True
    if job.kind in {"file", "file_reverse"}:
        return _run_file_job(job)
    if job.kind in {"plugin", "plugin_undo"}:
        return _run_plugin_job(job)
    return True


def _run_file_job(job: WorkJob) -> bool:
    if not job.file_op:
        return True
    root = Path(job.deck_root)
    op = job.file_op
    reverse = job.kind == "file_reverse"
    try:
        if reverse:
            _reverse_file_op(root, op)
        else:
            _apply_file_op(root, op)
        from pathlib import Path as P

        from choice.folder_index import apply_move

        state = P(job.state_dir) if job.state_dir else None
        if state is not None:
            apply_move(state, op.get("from") or "", op.get("to") or "", reverse=reverse)
        return True
    except _RetryLater as exc:
        job.last_error = str(exc)
        return False
    except Exception as exc:
        job.last_error = str(exc)[:400]
        return False


def _run_plugin_job(job: WorkJob) -> bool:
    if _deck_resolver is None or not job.plugin:
        return True
    deck = _deck_resolver(job.deck_id, job.actor)
    if deck is None:
        job.last_error = "Deck unavailable"
        return False
    from choice.act import _plugin_handle, _plugin_undo
    from choice.load import Item

    payload = job.plugin
    item = Item(
        id=str(payload.get("item_id") or ""),
        kind="file",
        title=str(payload.get("item_id") or ""),
        body="",
        path=None,
        fields={},
    )
    try:
        if job.kind == "plugin_undo":
            result = _plugin_undo(deck, item.id, payload.get("undo_token"))
        else:
            result = _plugin_handle(
                deck,
                item,
                str(payload.get("direction") or ""),
                str(payload.get("note") or ""),
            )
        if not result.get("ok", True):
            job.last_error = str(result.get("message") or "Plugin failed")[:400]
            return False
        return True
    except Exception as exc:
        job.last_error = str(exc)[:400]
        return False


def _apply_file_op(root: Path, file_op: dict) -> None:
    src = _under(root, str(file_op.get("from") or ""))
    dest = _under(root, str(file_op.get("to") or ""))
    if dest.is_file() and not src.is_file():
        return
    if not src.is_file():
        if dest.is_file():
            return
        raise _RetryLater("source missing")
    dest.parent.mkdir(parents=True, exist_ok=True)
    lock = _dest_lock(str(dest.parent))
    with lock:
        if dest.is_file():
            return
        _safe_move_retry(src, dest)


def _reverse_file_op(root: Path, file_op: dict) -> None:
    src = _under(root, str(file_op.get("from") or ""))
    dest = _under(root, str(file_op.get("to") or ""))
    if file_op.get("op") == "copy":
        if dest.is_file():
            dest.unlink()
        return
    if not dest.is_file():
        if src.is_file():
            return
        raise _RetryLater("destination missing for undo")
    if src.exists():
        return
    src.parent.mkdir(parents=True, exist_ok=True)
    lock = _dest_lock(str(src.parent))
    with lock:
        _safe_move_retry(dest, src)


def _safe_move_retry(src: Path, dest: Path) -> None:
    last: Exception | None = None
    for delay in (*_BACKOFF, 5.0, 5.0):
        try:
            if _same_volume(src, dest):
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(src, dest)
                src.unlink()
            return
        except OSError as exc:
            last = exc
            time.sleep(delay)
    raise _RetryLater(str(last) if last else "move failed")


def _same_volume(a: Path, b: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b.parent).st_dev
    except OSError:
        return True


def _dest_lock(key: str) -> threading.Lock:
    with _dest_guard:
        lock = _dest_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _dest_locks[key] = lock
        return lock


def _under(root: Path, relative: str) -> Path:
    parts = Path(relative.replace("\\", "/")).parts
    if not relative or relative.startswith("/") or ".." in parts or Path(relative).is_absolute():
        raise ValueError("bad path")
    path = (root / relative).resolve()
    if not inside(root, path):
        raise ValueError("path outside deck")
    return path


class _RetryLater(Exception):
    pass


def _load_jobs(state_dir: Path) -> list[WorkJob]:
    path = state_dir / _QUEUE_NAME
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[WorkJob] = []
    for row in rows:
        if isinstance(row, dict):
            job = WorkJob.from_dict(row)
            if job.status == "running":
                job.status = "pending"
            out.append(job)
    return out


def _save_jobs(state_dir: Path, jobs: list[WorkJob]) -> None:
    path = state_dir / _QUEUE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"jobs": [job.to_dict() for job in jobs]}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _append_job(state_dir: Path, job: WorkJob) -> None:
    jobs = _load_jobs(state_dir)
    jobs.append(job)
    _save_jobs(state_dir, jobs)
