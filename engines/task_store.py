"""
DARIO Task Store — Unified task access layer (DB-first, YAML fallback).
=========================================================================
All engines import from here instead of reading YAML directly.
Single source of truth: SQLite DB. YAML is fallback for legacy compat.

Usage:
    from task_store import TaskStore
    store = TaskStore()

    tasks = store.get_all()
    todo = store.get_by_status("todo")
    task = store.get("MNB-002")
    store.update("MNB-002", {"status": "in_progress", "checked_out_at": "..."})
    counts = store.counts()
    workload = store.worker_workload()
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TASKS_DIR = ORCH_DIR / "tasks" / "active"

sys.path.insert(0, str(ORCH_DIR))


class TaskStore:
    """DB-first task access. Falls back to YAML if DB unavailable."""

    def __init__(self):
        self._db = None
        self._use_db = False
        try:
            from db import DB
            self._db = DB()
            self._use_db = True
        except Exception:
            pass

    def get_all(self) -> list:
        if self._use_db:
            return self._db.get_tasks()
        return self._read_yaml_tasks()

    def get(self, task_id: str) -> dict:
        if self._use_db:
            return self._db.get_task(task_id)
        return self._read_yaml_task(task_id)

    def get_by_status(self, status: str) -> list:
        if self._use_db:
            return self._db.get_tasks(status=status)
        return [t for t in self._read_yaml_tasks() if t.get("status") == status]

    def get_unassigned(self) -> list:
        if self._use_db:
            return self._db.get_tasks(unassigned=True)
        return [t for t in self._read_yaml_tasks()
                if t.get("status") == "todo" and not t.get("assignee")]

    def counts(self) -> dict:
        if self._use_db:
            return self._db.get_task_counts()
        tasks = self._read_yaml_tasks()
        counts = {}
        for t in tasks:
            s = t.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts

    def worker_workload(self) -> dict:
        """Count active tasks per worker."""
        tasks = self.get_all()
        workload = {}
        for t in tasks:
            assignee = t.get("assignee")
            if not assignee:
                continue
            status = t.get("status", "")
            if status in ("todo", "in_progress", "in_review"):
                workload[assignee] = workload.get(assignee, 0) + 1
        return workload

    def update(self, task_id: str, fields: dict) -> bool:
        """Update task fields."""
        if self._use_db:
            # Build SQL SET clause dynamically
            with self._db._conn() as conn:
                sets = ", ".join(f"{k} = ?" for k in fields)
                vals = list(fields.values()) + [task_id]
                conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
            return True
        # YAML fallback
        task_file = TASKS_DIR / f"{task_id}.yaml"
        if not task_file.exists():
            return False
        try:
            from filelock import YAMLLock
            with YAMLLock(str(task_file)) as lock:
                data = lock.read() or {}
                data.update(fields)
                lock.write(data)
            return True
        except Exception:
            return False

    def _read_yaml_tasks(self) -> list:
        """Fallback: read YAML files."""
        tasks = []
        if not TASKS_DIR.exists():
            return tasks
        try:
            from ruamel.yaml import YAML
            y = YAML()
            loader = lambda p: y.load(open(p, 'r', encoding='utf-8'))
        except ImportError:
            import yaml
            loader = lambda p: yaml.safe_load(open(p, 'r', encoding='utf-8'))

        for f in TASKS_DIR.glob("*.yaml"):
            try:
                data = loader(str(f))
                if data and isinstance(data, dict):
                    data["_file"] = str(f)
                    tasks.append(data)
            except Exception:
                pass
        return tasks

    def _read_yaml_task(self, task_id: str) -> dict:
        task_file = TASKS_DIR / f"{task_id}.yaml"
        if not task_file.exists():
            return None
        try:
            from ruamel.yaml import YAML
            y = YAML()
            return y.load(open(str(task_file), 'r', encoding='utf-8'))
        except Exception:
            return None
