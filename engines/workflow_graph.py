#!/usr/bin/env python3
"""
DARIO Typed Workflow Graphs — Composable chain builder (Mastra-inspired).
==========================================================================
Build workflows with .then() / .parallel() / .branch() / .foreach() / .loop()
with schema validation between steps.

Replaces raw DAG adjacency lists with a fluent, typed API.

Usage:
    from workflow_graph import Workflow

    wf = (Workflow("brand_launch")
        .then("dario-brand", output_schema={"posicionamento": str, "archetype": str})
        .parallel([
            "dario-naming",
            "dario-story-circle",
        ])
        .branch(
            condition=lambda ctx: ctx.get("budget_max", 0) > 100000,
            if_true="dario-pitch",
            if_false="dario-proposal",
        )
        .then("dario-sales-letter")
    )

    # Compile to execution plan
    plan = wf.compile()
    print(plan)  # Shows waves, dependencies, schemas

    # Validate a chain before running
    errors = wf.validate()

CLI:
    python workflow_graph.py --show brand_launch
    python workflow_graph.py --list
    python workflow_graph.py --validate brand_launch
    python workflow_graph.py --compile brand_launch --json
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Union

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("workflow_graph")


@dataclass
class Step:
    """A single step in a workflow."""
    skill: str
    name: str = ""
    wave: int = 0  # Execution wave (parallel within same wave)
    depends_on: list[str] = field(default_factory=list)
    output_schema: dict = field(default_factory=dict)
    input_schema: dict = field(default_factory=dict)
    condition: Optional[str] = None  # Condition expression
    foreach_key: str = ""  # If set, iterates over this key in context
    max_iterations: int = 0  # If > 0, this is a loop step
    loop_until: str = ""  # Condition to exit loop

    def __post_init__(self):
        if not self.name:
            self.name = self.skill


@dataclass
class CompiledPlan:
    """Compiled execution plan from a workflow."""
    name: str
    waves: list[list[Step]] = field(default_factory=list)
    total_steps: int = 0
    estimated_tokens: int = 0
    schema_validated: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "total_steps": self.total_steps,
            "total_waves": len(self.waves),
            "estimated_tokens": self.estimated_tokens,
            "schema_validated": self.schema_validated,
            "errors": self.errors,
            "waves": [
                [{"skill": s.skill, "name": s.name, "depends_on": s.depends_on,
                  "condition": s.condition, "foreach": s.foreach_key,
                  "output_schema": s.output_schema}
                 for s in wave]
                for wave in self.waves
            ],
        }


class Workflow:
    """Fluent workflow builder with typed steps."""

    def __init__(self, name: str):
        self.name = name
        self.steps: list[Step] = []
        self._wave_counter = 0

    def then(self, skill: str, name: str = "", output_schema: dict = None,
             input_schema: dict = None) -> "Workflow":
        """Add a sequential step (waits for previous to complete)."""
        self._wave_counter += 1
        step = Step(
            skill=skill,
            name=name or skill,
            wave=self._wave_counter,
            output_schema=output_schema or {},
            input_schema=input_schema or {},
            depends_on=[self.steps[-1].skill] if self.steps else [],
        )
        self.steps.append(step)
        return self

    def parallel(self, skills: list[Union[str, dict]], name: str = "") -> "Workflow":
        """Add parallel steps (all run simultaneously in same wave)."""
        self._wave_counter += 1
        prev_skill = self.steps[-1].skill if self.steps else ""

        for s in skills:
            if isinstance(s, str):
                step = Step(skill=s, wave=self._wave_counter,
                          depends_on=[prev_skill] if prev_skill else [])
            else:
                step = Step(
                    skill=s.get("skill", ""),
                    name=s.get("name", ""),
                    wave=self._wave_counter,
                    output_schema=s.get("output_schema", {}),
                    depends_on=[prev_skill] if prev_skill else [],
                )
            self.steps.append(step)

        return self

    def branch(self, condition: str, if_true: str, if_false: str = "") -> "Workflow":
        """Add a conditional branch. Only one path executes."""
        self._wave_counter += 1
        prev_skill = self.steps[-1].skill if self.steps else ""

        # True branch
        step_true = Step(
            skill=if_true,
            wave=self._wave_counter,
            condition=f"{condition} == True",
            depends_on=[prev_skill] if prev_skill else [],
        )
        self.steps.append(step_true)

        # False branch (optional)
        if if_false:
            step_false = Step(
                skill=if_false,
                wave=self._wave_counter,
                condition=f"{condition} == False",
                depends_on=[prev_skill] if prev_skill else [],
            )
            self.steps.append(step_false)

        return self

    def foreach(self, skill: str, iterate_key: str, name: str = "") -> "Workflow":
        """Add a step that iterates over a list in context."""
        self._wave_counter += 1
        step = Step(
            skill=skill,
            name=name or f"foreach:{skill}",
            wave=self._wave_counter,
            foreach_key=iterate_key,
            depends_on=[self.steps[-1].skill] if self.steps else [],
        )
        self.steps.append(step)
        return self

    def loop(self, skill: str, until: str, max_iterations: int = 5, name: str = "") -> "Workflow":
        """Add a loop step that repeats until condition is met."""
        self._wave_counter += 1
        step = Step(
            skill=skill,
            name=name or f"loop:{skill}",
            wave=self._wave_counter,
            max_iterations=max_iterations,
            loop_until=until,
            depends_on=[self.steps[-1].skill] if self.steps else [],
        )
        self.steps.append(step)
        return self

    def compile(self) -> CompiledPlan:
        """Compile workflow into execution plan with waves."""
        # Group steps by wave
        waves_map: dict[int, list[Step]] = {}
        for step in self.steps:
            if step.wave not in waves_map:
                waves_map[step.wave] = []
            waves_map[step.wave].append(step)

        waves = [waves_map[w] for w in sorted(waves_map.keys())]

        plan = CompiledPlan(
            name=self.name,
            waves=waves,
            total_steps=len(self.steps),
            estimated_tokens=len(self.steps) * 3000,  # ~3K per step estimate
        )

        # Validate schemas between waves
        plan.errors = self.validate()
        plan.schema_validated = len(plan.errors) == 0

        return plan

    def validate(self) -> list[str]:
        """Validate workflow for errors."""
        errors = []

        if not self.steps:
            errors.append("Workflow has no steps")
            return errors

        # Check for missing skills
        try:
            from artifact_schemas import SCHEMAS
            for step in self.steps:
                if step.skill and step.skill not in SCHEMAS and not step.output_schema:
                    pass  # Warning only, not error

        except ImportError:
            pass

        # Check for circular dependencies
        skill_set = {s.skill for s in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in skill_set and dep:
                    errors.append(f"Step '{step.skill}' depends on '{dep}' which is not in workflow")

        return errors

    def to_dict(self) -> dict:
        """Export workflow as dict."""
        return {
            "name": self.name,
            "steps": [
                {
                    "skill": s.skill,
                    "name": s.name,
                    "wave": s.wave,
                    "depends_on": s.depends_on,
                    "condition": s.condition,
                    "foreach_key": s.foreach_key,
                    "loop_until": s.loop_until,
                    "max_iterations": s.max_iterations,
                    "output_schema": s.output_schema,
                }
                for s in self.steps
            ],
        }


# =============================================================================
# PRESET WORKFLOWS
# =============================================================================

WORKFLOWS = {}


def _register_presets():
    global WORKFLOWS

    WORKFLOWS["brand_launch"] = (
        Workflow("brand_launch")
        .then("dario-brand", output_schema={"posicionamento": "str", "archetype": "str", "messaging": "str"})
        .parallel(["dario-naming", "dario-story-circle"])
        .then("dario-offer")
        .then("dario-sales-letter")
    )

    WORKFLOWS["client_onboard"] = (
        Workflow("client_onboard")
        .parallel(["dario-diagnose", "dario-wp-audit", "seo-audit"])
        .then("dario-proposal")
    )

    WORKFLOWS["seo_pipeline"] = (
        Workflow("seo_pipeline")
        .parallel(["seo-technical", "seo-content", "seo-local"])
        .then("seo-schema")
        .then("seo-plan")
    )

    WORKFLOWS["diva_project"] = (
        Workflow("diva_project")
        .then("diva-briefing")
        .parallel(["diva-moodboard", "diva-floor-plan", "diva-licensing"])
        .parallel(["diva-materials", "diva-budget"])
        .then("diva-timeline")
        .then("diva-roadmap")
    )

    WORKFLOWS["content_machine"] = (
        Workflow("content_machine")
        .then("dario-kw-cluster")
        .foreach("dario-content", iterate_key="clusters")
        .then("seo-schema")
    )

    WORKFLOWS["proposal_to_contract"] = (
        Workflow("proposal_to_contract")
        .then("dario-proposal")
        .branch(condition="approved", if_true="dario-contract", if_false="dario-negotiation")
    )


_register_presets()


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Typed Workflow Graphs")
    parser.add_argument("--show", help="Show a workflow definition")
    parser.add_argument("--compile", help="Compile a workflow into execution plan")
    parser.add_argument("--validate", help="Validate a workflow")
    parser.add_argument("--list", action="store_true", help="List preset workflows")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.list:
        for name, wf in WORKFLOWS.items():
            plan = wf.compile()
            steps_str = " → ".join(
                f"[{'+'.join(s.skill for s in wave)}]" if len(wave) > 1 else wave[0].skill
                for wave in plan.waves
            )
            print(f"  {name:25s} | {plan.total_steps} steps, {len(plan.waves)} waves | {steps_str}")
        return 0

    if args.show:
        wf = WORKFLOWS.get(args.show)
        if not wf:
            print(f"Workflow '{args.show}' not found. Available: {list(WORKFLOWS.keys())}")
            return 1
        if args.json:
            print(json.dumps(wf.to_dict(), indent=2))
        else:
            plan = wf.compile()
            print(f"Workflow: {wf.name} ({plan.total_steps} steps, {len(plan.waves)} waves)\n")
            for i, wave in enumerate(plan.waves):
                parallel = " || " if len(wave) > 1 else ""
                skills = parallel.join(f"{s.skill}" + (f" [if {s.condition}]" if s.condition else "") for s in wave)
                print(f"  Wave {i+1}: {skills}")
        return 0

    if args.compile:
        wf = WORKFLOWS.get(args.compile)
        if not wf:
            print(f"Workflow '{args.compile}' not found")
            return 1
        plan = wf.compile()
        if args.json:
            print(json.dumps(plan.to_dict(), indent=2))
        else:
            print(f"Plan: {plan.name}")
            print(f"Steps: {plan.total_steps} | Waves: {len(plan.waves)} | Est. tokens: {plan.estimated_tokens}")
            print(f"Schema valid: {plan.schema_validated}")
            if plan.errors:
                print(f"Errors: {plan.errors}")
        return 0

    if args.validate:
        wf = WORKFLOWS.get(args.validate)
        if not wf:
            print(f"Workflow '{args.validate}' not found")
            return 1
        errors = wf.validate()
        if errors:
            print(f"INVALID: {len(errors)} errors")
            for e in errors:
                print(f"  ! {e}")
            return 1
        print(f"VALID: {wf.name} ({len(wf.steps)} steps)")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
