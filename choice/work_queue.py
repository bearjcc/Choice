# SPDX-License-Identifier: AGPL-3.0-only
"""Persistent async work queue for file moves and plugin side effects."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from choice.atomic_io import atomic_replace
from choice.bounded_cache import LruDict
from choice.dest_plan import allocate_dest_rel, replan_dest_rel, taken_destinations
from choice.file_moves import (
    MoveNotReady,
    copy_file,
    files_equal,
    move_file,
    remove_source,
)
from choice.load import Deck, inside

_QUEUE_NAME = "work_queue.json"
_MAX_ATTEMPTS = 12
_BACKOFF = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2)

_deck_resolver: Callable[[str, str], Deck | None] | None = None
_workers: dict[str, threading.Thread] = {}
_worker_lock = threading.Lock()
_dest_locks: dict[str, threading.Lock] = {}
_dest_guard = threading.Lock()
_queue_locks: LruDict[str, threading.RLock] = LruDict(64)
_job_lists: LruDict[str, list[WorkJob]] = LruDict(64)
_loaded: set[str] = set()


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
    jobs = _snapshot_jobs(deck.state_dir)
    pending = sum(1 for j in jobs if j.status == "pending")
    running = sum(1 for j in jobs if j.status == "running")
    failed = sum(1 for j in jobs if j.status == "failed")
    return QueueSnapshot(pending=pending, running=running, failed=failed)


def failures_for(deck: Deck, limit: int = 20) -> list[dict]:
    jobs = _snapshot_jobs(deck.state_dir)
    out: list[dict] = []
    for job in jobs:
        if job.status != "failed":
            continue
        row = {"id": job.id, "error": job.last_error or "Failed"}
        if job.file_op:
            row["from"] = job.file_op.get("from")
            row["to"] = job.file_op.get("to")
        if job.plugin:
            row["item"] = job.plugin.get("item_id")
        out.append(row)
        if len(out) >= limit:
            break
    return out


def wait_idle(state_dir: Path, timeout: float = 180.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = _snapshot_jobs(state_dir)
        if not any(j.status in {"pending", "running"} for j in jobs):
            return True
        time.sleep(0.02)
    return False


def allocate_transfer_dest(
    deck: Deck, does: str, from_rel: str, into: str, item
) -> dict:
    planned: dict = {}

    def _reserve(jobs: list[WorkJob]) -> None:
        planned.clear()
        planned.update(_plan_transfer_op(deck, does, from_rel, into, item, jobs))

    _mutate_jobs(deck.state_dir, _reserve)
    return dict(planned)


def enqueue_planned_transfer(
    deck: Deck,
    decision_id: str,
    item,
    does: str,
    into: str,
) -> dict:
    from choice.act import _validate_transfer

    _validate_transfer(deck, item, does, into)
    from_rel = item.path.resolve().relative_to(deck.root.resolve()).as_posix()
    planned: dict = {}
    job = WorkJob(
        id=uuid.uuid4().hex,
        decision_id=decision_id,
        kind="file",
        deck_id=deck.id,
        actor=deck.actor or "",
        deck_root=str(deck.root.resolve()),
        state_dir=str(deck.state_dir.resolve()),
    )

    def _add(jobs: list[WorkJob]) -> None:
        planned.clear()
        planned.update(_plan_transfer_op(deck, does, from_rel, into, item, jobs))
        job.file_op = dict(planned)
        jobs.append(job)

    _mutate_jobs(deck.state_dir, _add)
    _ensure_worker(deck.state_dir)
    return dict(planned)


def _plan_transfer_op(
    deck: Deck, does: str, from_rel: str, into: str, item, jobs: list[WorkJob]
) -> dict:
    from choice.dest_plan import preferred_dest_rel

    preferred = preferred_dest_rel(deck, item, into)
    root = deck.root.resolve()
    taken = taken_destinations(jobs, root)
    to_rel = allocate_dest_rel(root, preferred, taken)
    return {"op": does, "from": from_rel, "to": to_rel}


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

    def _add(jobs: list[WorkJob]) -> None:
        jobs.append(job)

    _mutate_jobs(deck.state_dir, _add)
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

    def _add(jobs: list[WorkJob]) -> None:
        jobs.append(job)

    _mutate_jobs(deck.state_dir, _add)
    _ensure_worker(deck.state_dir)
    return job.id


def cancel_for_decision(deck: Deck, decision_id: str) -> int:
    cancelled = 0

    def _cancel(jobs: list[WorkJob]) -> None:
        nonlocal cancelled
        for job in jobs:
            if job.decision_id != decision_id:
                continue
            if job.status == "pending":
                job.status = "cancelled"
                job.updated_at = time.time()
                cancelled += 1

    _mutate_jobs(deck.state_dir, _cancel)
    return cancelled


def reconcile_deck(deck: Deck) -> int:
    """Re-enqueue sort moves logged but not applied on disk."""
    from choice.act import _read_log, patch_decision_file_op
    from choice.folder_index import readmit_path

    if deck.folder_scan is None or deck.folder_scan.output != "sort":
        return 0
    root = deck.root.resolve()
    n = 0
    pending_patch: list[tuple[str, dict]] = []

    def _scan(jobs: list[WorkJob]) -> None:
        nonlocal n
        active = {
            j.decision_id
            for j in jobs
            if j.status in {"pending", "running", "failed"}
            and j.kind in {"file", "file_reverse"}
        }
        undone = {row.get("ref") for row in _read_log(deck) if row.get("type") == "undo"}
        for row in _read_log(deck):
            if row.get("type") != "decision" or row.get("id") in undone:
                continue
            if row.get("later"):
                continue
            op = row.get("file_op")
            if not isinstance(op, dict):
                continue
            decision_id = str(row.get("id") or "")
            if not decision_id or decision_id in active:
                continue
            from_rel = str(op.get("from") or "")
            if not from_rel:
                continue
            src = (root / from_rel).resolve()
            if not src.is_file():
                continue
            to_rel = str(op.get("to") or "")
            dest = (root / to_rel).resolve() if to_rel else None
            if dest is not None and dest.is_file() and not src.is_file():
                continue
            if dest is not None and dest.is_file() and src.is_file() and files_equal(src, dest):
                try:
                    remove_source(src)
                except MoveNotReady:
                    jobs.append(
                        WorkJob(
                            id=uuid.uuid4().hex,
                            decision_id=decision_id,
                            kind="file",
                            file_op=dict(op),
                            deck_id=deck.id,
                            actor=deck.actor or "",
                            deck_root=str(root),
                            state_dir=str(deck.state_dir.resolve()),
                        )
                    )
                    active.add(decision_id)
                    n += 1
                continue
            new_op = dict(op)
            new_to = replan_dest_rel(root, from_rel, new_op, jobs)
            if new_to != new_op.get("to"):
                new_op["to"] = new_to
                pending_patch.append((decision_id, dict(new_op)))
            readmit_path(deck.state_dir, from_rel, deck=deck)
            jobs.append(
                WorkJob(
                    id=uuid.uuid4().hex,
                    decision_id=decision_id,
                    kind="file",
                    file_op=dict(new_op),
                    deck_id=deck.id,
                    actor=deck.actor or "",
                    deck_root=str(root),
                    state_dir=str(deck.state_dir.resolve()),
                )
            )
            active.add(decision_id)
            n += 1

    _mutate_jobs(deck.state_dir, _scan)
    for decision_id, new_op in pending_patch:
        patch_decision_file_op(deck, decision_id, new_op)
    if n:
        _ensure_worker(deck.state_dir)
    return n


def resume_workers(state_root: Path) -> None:
    if not state_root.is_dir():
        return
    candidates: list[Path] = []
    if (state_root / _QUEUE_NAME).is_file():
        candidates.append(state_root)
    for child in state_root.iterdir():
        if child.is_dir() and (child / _QUEUE_NAME).is_file():
            candidates.append(child)
    for state_dir in candidates:
        _ensure_loaded(state_dir)
        jobs = _snapshot_jobs(state_dir)
        if any(j.status in {"pending", "running"} for j in jobs):
            _ensure_worker(state_dir)


def boot_deck(deck: Deck) -> None:
    reconcile_deck(deck)
    jobs = _snapshot_jobs(deck.state_dir)
    if any(j.status in {"pending", "running"} for j in jobs):
        _ensure_worker(deck.state_dir)


def _ensure_worker(state_dir: Path) -> None:
    if os.environ.get("CHOICE_SYNC_WORK"):
        _worker_supervisor(state_dir)
        return
    key = str(state_dir.resolve())
    with _worker_lock:
        thread = _workers.get(key)
        if thread and thread.is_alive():
            return
        thread = threading.Thread(
            target=_worker_supervisor,
            args=(state_dir,),
            name=f"work-{state_dir.name}",
            daemon=True,
        )
        _workers[key] = thread
        thread.start()


def _worker_supervisor(state_dir: Path) -> None:
    while True:
        try:
            if not _worker_loop(state_dir):
                return
        except Exception:
            time.sleep(0.05)
            jobs = _snapshot_jobs(state_dir)
            if not any(j.status in {"pending", "running"} for j in jobs):
                return


def _worker_loop(state_dir: Path) -> bool:
    job: WorkJob | None = None
    with _queue_lock(state_dir):
        jobs = _ensure_loaded(state_dir)
        next_job = next((j for j in jobs if j.status == "pending"), None)
        if next_job is None:
            return False
        next_job.status = "running"
        next_job.updated_at = time.time()
        job = next_job
        _persist_jobs(state_dir, jobs)
    assert job is not None
    ok = _run_job(state_dir, job)
    with _queue_lock(state_dir):
        jobs = _ensure_loaded(state_dir)
        for row in jobs:
            if row.id != job.id:
                continue
            if ok:
                row.status = "done"
                row.last_error = ""
            elif row.status == "cancelled":
                break
            else:
                row.attempts += 1
                if row.attempts >= _MAX_ATTEMPTS:
                    row.status = "failed"
                else:
                    row.status = "pending"
                    delay = _BACKOFF[min(row.attempts - 1, len(_BACKOFF) - 1)]
                    time.sleep(delay)
            row.updated_at = time.time()
            break
        _persist_jobs(state_dir, jobs)
        retry = any(j.id == job.id and j.status == "pending" for j in jobs)
        pending = any(j.status == "pending" for j in jobs)
    if retry or pending:
        return True
    return False


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
    state_dir = Path(job.state_dir)
    op = job.file_op
    reverse = job.kind == "file_reverse"
    try:
        if reverse:
            _reverse_file_op(root, op)
        else:
            _apply_file_op(root, op, job, state_dir)
        if job.kind == "file" and str(op.get("op") or "move") == "move":
            src = _under(root, str(op.get("from") or ""))
            if src.is_file():
                raise MoveNotReady("source remains")
        return True
    except (MoveNotReady, _RetryLater) as exc:
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


def _apply_file_op(
    root: Path, file_op: dict, job: WorkJob, state_dir: Path
) -> None:
    from choice.act import patch_decision_file_op

    src = _under(root, str(file_op.get("from") or ""))
    dest = _under(root, str(file_op.get("to") or ""))
    op = str(file_op.get("op") or "move")
    lock = _dest_lock(str(dest.parent))
    with lock:
        if op == "copy":
            copy_file(src, dest)
            return
        if not src.is_file():
            if dest.is_file():
                return
            raise _RetryLater("source missing")
        if dest.is_file() and not files_equal(src, dest):
            new_to = _replan_dest_locked(root, file_op, job, state_dir)
            dest = _under(root, new_to)
            if _deck_resolver is not None:
                deck = _deck_resolver(job.deck_id, job.actor)
                if deck is not None:
                    patch_decision_file_op(deck, job.decision_id, dict(job.file_op or {}))
        move_file(src, dest)
        if src.is_file():
            raise MoveNotReady("source remains")


def _replan_dest_locked(
    root: Path, file_op: dict, job: WorkJob, state_dir: Path
) -> str:
    from_rel = str(file_op.get("from") or "")

    def _fn(jobs: list[WorkJob]) -> None:
        new_to = replan_dest_rel(root, from_rel, file_op, jobs)
        file_op["to"] = new_to
        job.file_op = dict(file_op)

    _mutate_jobs(state_dir, _fn)
    return str(file_op.get("to") or "")


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
    lock = _dest_lock(str(src.parent))
    with lock:
        move_file(dest, src)


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


def _queue_lock(state_dir: Path) -> threading.RLock:
    key = str(state_dir.resolve())
    lock = _queue_locks.get(key)
    if lock is None:
        lock = threading.RLock()
        _queue_locks.set(key, lock)
    return lock


def _state_key(state_dir: Path) -> str:
    return str(state_dir.resolve())


def _read_disk(state_dir: Path) -> list[WorkJob]:
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


def _ensure_loaded(state_dir: Path) -> list[WorkJob]:
    key = _state_key(state_dir)
    if key not in _loaded:
        jobs = _read_disk(state_dir)
        _job_lists.set(key, jobs)
        _loaded.add(key)
    hit = _job_lists.get(key)
    if hit is None:
        hit = []
        _job_lists.set(key, hit)
    return hit


def _persist_jobs(state_dir: Path, jobs: list[WorkJob]) -> None:
    path = state_dir / _QUEUE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = [j for j in jobs if j.status in {"pending", "running", "failed"}]
    payload = {"jobs": [job.to_dict() for job in kept]}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    atomic_replace(tmp, path)


def _mutate_jobs(state_dir: Path, fn: Callable[[list[WorkJob]], None]) -> None:
    with _queue_lock(state_dir):
        jobs = _ensure_loaded(state_dir)
        fn(jobs)
        _persist_jobs(state_dir, jobs)


def _snapshot_jobs(state_dir: Path) -> list[WorkJob]:
    with _queue_lock(state_dir):
        jobs = _ensure_loaded(state_dir)
        return list(jobs)


def _load_jobs(state_dir: Path) -> list[WorkJob]:
    """Tests only: current in-memory queue snapshot."""
    return _snapshot_jobs(state_dir)


def _save_jobs(state_dir: Path, jobs: list[WorkJob]) -> None:
    """Tests only: replace queue under lock."""
    with _queue_lock(state_dir):
        key = _state_key(state_dir)
        _job_lists.set(key, list(jobs))
        _loaded.add(key)
        _persist_jobs(state_dir, jobs)


def drop_memory_state(state_dir: Path) -> None:
    """Simulate process restart for tests."""
    key = _state_key(state_dir)
    with _queue_lock(state_dir):
        _loaded.discard(key)
        _job_lists.pop(key)
