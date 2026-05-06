#!/usr/bin/env python3
"""
DARIO Task Store v2 — Unified task access layer (DB-first, YAML fallback).
============================================================================
Safe abstraction over DB. Column whitelist prevents SQL injection.
All state transitions go through DB methods with proper guards.

Usage:
    from task_store import TaskStore
    store = TaskStore()
    tasks = store.get_all()
    store.create({"id": "T-001", "title": "...", "skill": "dario-brand"})
    store.update("T-001", {"priority": "high"})
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TASKS_DIR = ORCH_DIR / "tasks" / "active"
sys.path.insert(0, str(ORCH_DIR))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("task_store")


class TaskStore:
    """Unified task access — DB-first with safe operations."""

    def __init__(self):
        self._db = None
        self._use_db = False
        try:
            from db import DB
            self._db = DB()
            self._use_db = True
        except Exception as e:
            log.warning(f"DB unavailable, YAML fallback: {e}")

    def create(self, data: dict) -> dict:
        """Create a task (new: was missing from v1)."""
        if self._use_db:
            return self._db.create_task(data)
        raise NotImplementedError("Create requires DB")

    def get_all(self, status: str = None, project: str = None) -> list:
        if self._use_db:
            return self._db.get_tasks(status=status, project=project)
        return self._yaml_fallback(status=status, project=project)

    def get(self, task_id: str) -> dict:
        if self._use_db:
            return self._db.get_task(task_id)
        return self._yaml_get(task_id)

    def get_by_status(self, status: str) -> list:
        return self.get_all(status=status)

    def get_unassigned(self) -> list:
        if self._use_db:
            return self._db.get_tasks(unassigned=True)
        return [t for t in self.get_all() if not t.get("assignee") and t.get("status") == "todo"]

    def update(self, task_id: str, fields: dict) -> bool:
        """Safe update with column whitelist (fixed: was SQL injection vulnerable)."""
        if self._use_db:
            return self._db.update_task(task_id, fields)
        return False

    def counts(self) -> dict:
        if self._use_db:
            return self._db.get_task_counts()
        tasks = self.get_all()
        from collections import Counter
        return dict(Counter(t.get("status", "?") for t in tasks))

    def worker_workload(self, worker_id: str) -> dict:
        if self._use_db:
            tasks = self._db.get_tasks(assignee=worker_id)
        else:
            tasks = [t for t in self.get_all() if t.get("assignee") == worker_id]
        in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
        todo = sum(1 for t in tasks if t.get("status") == "todo")
        return {"worker": worker_id, "in_progress": in_progress, "todo": todo, "total": len(tasks)}

    # YAML fallback (read-only, for cold start before DB exists)

    def _yaml_fallback(self, status=None, project=None) -> list:
        if not TASKS_DIR.exists():
            return []
        tasks = []
        for f in TASKS_DIR.glob("*.yaml"):
            try:
                import yaml
                with open(f, 'r', encoding='utf-8') as fh:
                    data = yaml.safe_load(fh)
                if data:
                    if status and data.get("status") != status:
                        continue
                    if project and data.get("project") != project:
                        continue
                    tasks.append(data)
            except Exception:
                pass
        return tasks

    def _yaml_get(self, task_id: str) -> dict:
        path = TASKS_DIR / f"{task_id}.yaml"
        if not path.exists():
            return None
        try:
            import yaml
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return None
