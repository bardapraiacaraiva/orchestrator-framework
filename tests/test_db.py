"""Tests for SQLite persistence layer."""
import json
import pytest
from db import DB


class TestTaskLifecycle:
    def test_create_task(self, test_db):
        result = test_db.create_task("X-001", "Test task", skill="dario-brand")
        assert result["id"] == "X-001"
        task = test_db.get_task("X-001")
        assert task["title"] == "Test task"
        assert task["status"] == "todo"

    def test_assign_task_success(self, test_db):
        test_db.create_task("X-001", "Test", skill="dario-brand")
        assert test_db.assign_task("X-001", "worker-brand", "test")

    def test_assign_prevents_double(self, test_db):
        test_db.create_task("X-001", "Test", skill="dario-brand")
        assert test_db.assign_task("X-001", "worker-brand", "first")
        assert not test_db.assign_task("X-001", "worker-other", "second")

    def test_checkout_requires_assignee(self, test_db):
        test_db.create_task("X-001", "Test")
        assert not test_db.checkout_task("X-001")  # No assignee

    def test_checkout_success(self, test_db):
        test_db.create_task("X-001", "Test")
        test_db.assign_task("X-001", "worker-brand")
        assert test_db.checkout_task("X-001")
        task = test_db.get_task("X-001")
        assert task["status"] == "in_progress"

    def test_checkout_prevents_double(self, test_db):
        test_db.create_task("X-001", "Test")
        test_db.assign_task("X-001", "worker-brand")
        assert test_db.checkout_task("X-001")
        assert not test_db.checkout_task("X-001")  # Already in_progress

    def test_complete_task(self, test_db):
        test_db.create_task("X-001", "Test")
        test_db.assign_task("X-001", "worker-brand")
        test_db.checkout_task("X-001")
        assert test_db.complete_task("X-001", score=88, tokens=2000, output="done")
        task = test_db.get_task("X-001")
        assert task["status"] == "done"
        assert task["quality_score"] == 88
        assert task["actual_tokens"] == 2000

    def test_complete_updates_budget(self, test_db):
        test_db.create_task("X-001", "Test")
        test_db.assign_task("X-001", "w")
        test_db.checkout_task("X-001")
        test_db.complete_task("X-001", tokens=5000)
        budget = test_db.get_budget()
        assert budget["tokens_used"] == 5000

    def test_block_task(self, test_db):
        test_db.create_task("X-001", "Test")
        test_db.block_task("X-001", "test reason")
        task = test_db.get_task("X-001")
        assert task["status"] == "blocked"
        assert task["blocked_reason"] == "test reason"


class TestQueries:
    def test_get_tasks_by_status(self, populated_db):
        tasks = populated_db.get_tasks(status="todo")
        assert len(tasks) == 3

    def test_get_tasks_by_project(self, populated_db):
        tasks = populated_db.get_tasks(project="test")
        assert len(tasks) == 3

    def test_get_unassigned(self, populated_db):
        tasks = populated_db.get_tasks(unassigned=True)
        assert len(tasks) == 3
        populated_db.assign_task("T-001", "worker-brand")
        tasks = populated_db.get_tasks(unassigned=True)
        assert len(tasks) == 2

    def test_task_counts(self, populated_db):
        counts = populated_db.get_task_counts()
        assert counts.get("todo", 0) == 3

    def test_priority_ordering(self, populated_db):
        tasks = populated_db.get_tasks()
        assert tasks[0]["priority"] == "critical"


class TestAudit:
    def test_log_event(self, test_db):
        test_db.log_event("test", "test_action", task_id="X", details="hello")
        entries = test_db.get_audit(limit=1)
        assert len(entries) == 1
        assert entries[0]["actor"] == "test"

    def test_audit_append_only(self, test_db):
        for i in range(5):
            test_db.log_event("test", f"action_{i}")
        entries = test_db.get_audit(limit=10)
        assert len(entries) == 5

    def test_audit_filter_by_task(self, test_db):
        test_db.log_event("a", "x", task_id="T-001")
        test_db.log_event("b", "y", task_id="T-002")
        entries = test_db.get_audit(task_id="T-001")
        assert len(entries) == 1


class TestScores:
    def test_record_score(self, test_db):
        test_db.record_score("T-001", "dario-brand", 92, "test")
        stats = test_db.get_skill_stats()
        assert len(stats) == 1
        assert stats[0]["avg_score"] == 92.0

    def test_multiple_scores(self, test_db):
        test_db.record_score("T-001", "dario-brand", 90, "test")
        test_db.record_score("T-002", "dario-brand", 80, "test")
        stats = test_db.get_skill_stats()
        assert stats[0]["avg_score"] == 85.0
        assert stats[0]["executions"] == 2


class TestBudget:
    def test_budget_default(self, test_db):
        b = test_db.get_budget()
        assert b["tokens_used"] == 0
        assert b["token_limit"] == 50000000

    def test_budget_accumulates(self, test_db):
        for i in range(3):
            test_db.create_task(f"X-{i}", "Test")
            test_db.assign_task(f"X-{i}", "w")
            test_db.checkout_task(f"X-{i}")
            test_db.complete_task(f"X-{i}", tokens=1000)
        b = test_db.get_budget()
        assert b["tokens_used"] == 3000


class TestStats:
    def test_stats(self, populated_db):
        s = populated_db.stats()
        assert s["tasks"] == 3
        assert s["db_size_kb"] > 0
