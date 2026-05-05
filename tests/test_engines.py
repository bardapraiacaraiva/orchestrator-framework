"""Tests for orchestrator engines (dispatch, state, guardrails, replanner, etc)."""
import json
import subprocess
import sys
import pytest
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
PY = sys.executable


def run(script, args):
    r = subprocess.run([PY, str(ORCH_DIR / script)] + args,
                       capture_output=True, text=True, timeout=15, cwd=str(ORCH_DIR))
    return r


class TestDispatchEngine:
    def test_status_runs(self):
        r = run("dispatch_engine.py", ["--status"])
        assert r.returncode == 0
        assert "WORKER AVAILABILITY" in r.stdout

    def test_dry_run(self):
        r = run("dispatch_engine.py", ["--dry-run"])
        assert r.returncode == 0

    def test_json_output(self):
        r = run("dispatch_engine.py", ["--json"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "dispatched" in data
        assert "queued" in data


class TestStateMachine:
    def test_show_state(self):
        r = run("state_machine.py", ["--json"])
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["state"] in ["ACTIVE", "REFLECTIVE_PAUSE", "GUARDIAN", "EXPANSION"]
        assert "system_health" in data

    def test_evaluate(self):
        r = run("state_machine.py", ["--evaluate", "--json"])
        data = json.loads(r.stdout)
        assert "transitioned" in data

    def test_history(self):
        r = run("state_machine.py", ["--history"])
        assert r.returncode == 0


class TestGuardrails:
    def test_valid_task(self):
        r = run("guardrails.py", ["--task", "MNB-001", "--json"])
        data = json.loads(r.stdout)
        assert data["verdict"] in ["PASS", "WARN", "FAIL"]
        assert "checks" in data

    def test_missing_task(self):
        r = run("guardrails.py", ["--task", "NONEXISTENT-999", "--json"])
        data = json.loads(r.stdout)
        assert data["verdict"] == "FAIL"


class TestAutodiag:
    def test_all_checks_run(self):
        r = run("autodiag_runner.py", ["--json"])
        data = json.loads(r.stdout)
        assert data["total"] == 7
        assert "passed" in data

    def test_single_check(self):
        r = run("autodiag_runner.py", ["--check", "coherence_check", "--json"])
        data = json.loads(r.stdout)
        assert data["total"] == 1


class TestReplanner:
    def test_timeout_retry(self, populated_db):
        # Set task to allow replan
        populated_db.assign_task("T-001", "worker-brand")
        r = run("replanner.py", ["--task", "T-001", "--failure", "agent_timeout", "--json"])
        data = json.loads(r.stdout)
        assert data["action"] in ["retry_same", "retry_sibling", "escalate"]

    def test_unknown_failure(self, populated_db):
        r = run("replanner.py", ["--task", "T-001", "--failure", "unknown", "--json"])
        data = json.loads(r.stdout)
        assert "action" in data


class TestEvolution:
    def test_status(self):
        r = run("evolution_runner.py", ["--status", "--json"])
        data = json.loads(r.stdout)
        assert "journals" in data
        assert "mutations" in data

    def test_journal_only(self):
        r = run("evolution_runner.py", ["--journal", "--json"])
        assert r.returncode == 0


class TestTracer:
    def test_start_end(self):
        run("tracer.py", ["--start", "--task", "TEST-TRACE", "--skill", "test"])
        r = run("tracer.py", ["--end", "--task", "TEST-TRACE", "--status", "success",
                               "--tokens", "100", "--score", "85"])
        assert r.returncode == 0

    def test_view(self):
        r = run("tracer.py", ["--view", "TEST-TRACE", "--json"])
        data = json.loads(r.stdout)
        assert data["total_attempts"] >= 1

    def test_list(self):
        r = run("tracer.py", ["--list", "--json"])
        data = json.loads(r.stdout)
        assert isinstance(data, list)


class TestChainExecutor:
    def test_dry_run(self):
        r = run("chain_executor.py", ["--chain", "brand_to_market", "--dry-run", "--json"])
        data = json.loads(r.stdout)
        assert data["total_steps"] == 5
        assert data["total_waves"] == 5

    def test_list(self):
        r = run("chain_executor.py", ["--list", "--json"])
        assert r.returncode == 0


class TestContextInjector:
    def test_context_for_task(self):
        r = run("context_injector.py", ["--task", "MNB-001", "--json"])
        data = json.loads(r.stdout)
        assert "sections" in data
        assert "context_block" in data


class TestAdaptiveRubric:
    def test_brand_rubric(self):
        r = run("adaptive_rubric.py", ["--skill", "dario-brand", "--json"])
        data = json.loads(r.stdout)
        assert data["dimensions_count"] == 5
        assert data["pass_threshold"] >= 60

    def test_financial_rubric(self):
        r = run("adaptive_rubric.py", ["--skill", "dario-financial-model", "--policy", "financial", "--json"])
        data = json.loads(r.stdout)
        assert data["pass_threshold"] >= 80  # Financial = strict


class TestTaskTemplates:
    def test_list(self):
        r = run("task_templates.py", ["--list", "--json"])
        data = json.loads(r.stdout)
        assert "brand_audit" in data
        assert "client_onboard" in data

    def test_preview(self):
        r = run("task_templates.py", ["--template", "wp_health",
                 "--vars", '{"client":"Test","url":"test.com"}', "--json"])
        data = json.loads(r.stdout)
        assert data["tasks_count"] == 4
        assert "Test" in data["tasks"][0]["title"]


class TestQualityScorer:
    def test_dashboard(self):
        r = run("quality_scorer.py", ["--dashboard", "--json"])
        data = json.loads(r.stdout)
        assert "total_scored" in data

    def test_record(self):
        r = run("quality_scorer.py", ["--task", "TEST-QS", "--score", "75",
                 "--skill", "dario-brand", "--json"])
        data = json.loads(r.stdout)
        assert data["action"] in ["ship", "revision", "success_pattern", "escalate"]
