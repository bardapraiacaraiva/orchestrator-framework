#!/usr/bin/env python3
"""
DARIO Self-Editing Memory Blocks — Agent-driven dynamic context (Letta-inspired).
===================================================================================
Agents can read and modify their own persona and project context mid-session.
Blocks are fixed-size (max 2K chars), persisted to files, and prepended to prompts.

Block types:
    persona  — Agent's identity, capabilities, behavioral rules
    project  — Current project context, decisions, constraints
    client   — Client preferences, communication style, history
    learned  — Patterns the agent has learned from past tasks

Tools exposed to agents:
    memory_read(block_name)              — Read a block
    memory_replace(block, old, new)      — Replace text in a block
    memory_insert(block, text, index)    — Insert text at position
    memory_clear(block)                  — Reset a block to default

Usage:
    python memory_blocks.py --read persona
    python memory_blocks.py --read project --scope mar-brasa
    python memory_blocks.py --replace persona --old "conservative" --new "bold and creative"
    python memory_blocks.py --insert project --text "Client prefers minimalist style" --index 0
    python memory_blocks.py --list
    python memory_blocks.py --export --json
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
BLOCKS_DIR = ORCH_DIR / "memory_blocks"

MAX_BLOCK_SIZE = 2048  # chars

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("memory_blocks")

# Default block content
DEFAULTS = {
    "persona": (
        "Tu es o DARIO — orchestrator digital para agencias de marketing, design e tecnologia.\n"
        "Especializado em: brand positioning, SEO, WordPress, gestao de obras, SaaS.\n"
        "Tom: profissional, directo, orientado a resultados.\n"
        "Sempre em portugues de Portugal. Dados concretos, nunca vago."
    ),
    "project": "",
    "client": "",
    "learned": "",
}


def _block_path(name: str, scope: str = "global") -> Path:
    """Get path for a memory block file."""
    scope_dir = BLOCKS_DIR / scope
    scope_dir.mkdir(parents=True, exist_ok=True)
    return scope_dir / f"{name}.txt"


def _read_raw(name: str, scope: str = "global") -> str:
    """Read raw block content."""
    path = _block_path(name, scope)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return DEFAULTS.get(name, "")


def _write_raw(name: str, content: str, scope: str = "global") -> bool:
    """Write block content with size enforcement."""
    if len(content) > MAX_BLOCK_SIZE:
        content = content[:MAX_BLOCK_SIZE]
        log.warning(f"Block '{name}' truncated to {MAX_BLOCK_SIZE} chars")

    path = _block_path(name, scope)
    path.write_text(content, encoding="utf-8")

    # Log mutation
    _log_mutation(name, scope, "write", len(content))
    return True


def _log_mutation(name: str, scope: str, action: str, size: int):
    """Log block mutations for audit trail."""
    log_file = BLOCKS_DIR / "mutations.jsonl"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "block": name,
        "scope": scope,
        "action": action,
        "size": size,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# =============================================================================
# AGENT-FACING TOOLS
# =============================================================================

def memory_read(block_name: str, scope: str = "global") -> dict:
    """Read a memory block. Returns content + metadata."""
    content = _read_raw(block_name, scope)
    return {
        "block": block_name,
        "scope": scope,
        "content": content,
        "size": len(content),
        "max_size": MAX_BLOCK_SIZE,
        "remaining": MAX_BLOCK_SIZE - len(content),
    }


def memory_replace(block_name: str, old_text: str, new_text: str, scope: str = "global") -> dict:
    """Replace text in a memory block."""
    content = _read_raw(block_name, scope)

    if old_text not in content:
        return {"success": False, "error": f"Text '{old_text[:50]}...' not found in block '{block_name}'"}

    new_content = content.replace(old_text, new_text, 1)
    _write_raw(block_name, new_content, scope)

    return {
        "success": True,
        "block": block_name,
        "old_size": len(content),
        "new_size": len(new_content),
        "remaining": MAX_BLOCK_SIZE - len(new_content),
    }


def memory_insert(block_name: str, text: str, index: int = -1, scope: str = "global") -> dict:
    """Insert text at position in a memory block. -1 = append."""
    content = _read_raw(block_name, scope)

    if index == -1 or index >= len(content):
        new_content = content + ("\n" if content else "") + text
    elif index == 0:
        new_content = text + "\n" + content
    else:
        new_content = content[:index] + text + content[index:]

    if len(new_content) > MAX_BLOCK_SIZE:
        return {
            "success": False,
            "error": f"Insert would exceed max size ({len(new_content)} > {MAX_BLOCK_SIZE}). "
                    f"Remove {len(new_content) - MAX_BLOCK_SIZE} chars first.",
        }

    _write_raw(block_name, new_content, scope)

    return {
        "success": True,
        "block": block_name,
        "new_size": len(new_content),
        "remaining": MAX_BLOCK_SIZE - len(new_content),
    }


def memory_clear(block_name: str, scope: str = "global") -> dict:
    """Reset a block to its default content."""
    default = DEFAULTS.get(block_name, "")
    _write_raw(block_name, default, scope)
    return {"success": True, "block": block_name, "reset_to_default": True, "size": len(default)}


def memory_rethink(block_name: str, new_content: str, scope: str = "global") -> dict:
    """Completely replace a block's content (full rewrite)."""
    _write_raw(block_name, new_content, scope)
    return {
        "success": True,
        "block": block_name,
        "new_size": len(new_content),
        "remaining": MAX_BLOCK_SIZE - len(new_content),
    }


# =============================================================================
# SHARED MEMORY — DARIO + DIVA unified project context (Letta-inspired)
# =============================================================================

def share_block(block_name: str, from_scope: str, to_scope: str) -> dict:
    """Share a memory block from one scope to another (symlink-style copy)."""
    content = _read_raw(block_name, from_scope)
    if not content:
        return {"success": False, "error": f"Block '{block_name}' empty in scope '{from_scope}'"}
    _write_raw(block_name, content, to_scope)
    _log_mutation(block_name, to_scope, "shared_from:" + from_scope, len(content))
    return {"success": True, "block": block_name, "from": from_scope, "to": to_scope, "size": len(content)}


def sync_project_blocks(project: str, agents: list[str] = None) -> list[dict]:
    """Sync project memory blocks across multiple agent scopes."""
    if agents is None:
        agents = ["dario", "diva", "lucas"]

    results = []
    # Read the canonical project block
    project_content = _read_raw("project", project)
    client_content = _read_raw("client", project)

    for agent in agents:
        agent_scope = f"{agent}/{project}"
        if project_content:
            r = share_block("project", project, agent_scope)
            results.append(r)
        if client_content:
            r = share_block("client", project, agent_scope)
            results.append(r)

    return results


# =============================================================================
# CONTEXT ASSEMBLY — for prompt injection
# =============================================================================

def assemble_context(scope: str = "global", blocks: list[str] = None) -> str:
    """
    Assemble all memory blocks into a single context string for prompt prepending.
    Used by context_injector.py and executor.py.
    """
    if blocks is None:
        blocks = ["persona", "project", "client", "learned"]

    parts = []
    for block_name in blocks:
        content = _read_raw(block_name, scope)
        if content and content.strip():
            header = block_name.upper()
            parts.append(f"[{header} CONTEXT]\n{content}\n[/{header} CONTEXT]")

    return "\n\n".join(parts)


def list_blocks(scope: str = "global") -> list[dict]:
    """List all blocks and their sizes for a scope."""
    scope_dir = BLOCKS_DIR / scope
    if not scope_dir.exists():
        return [{"block": name, "scope": scope, "size": len(DEFAULTS.get(name, "")), "source": "default"}
                for name in DEFAULTS]

    result = []
    for name in DEFAULTS:
        path = scope_dir / f"{name}.txt"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            result.append({
                "block": name,
                "scope": scope,
                "size": len(content),
                "remaining": MAX_BLOCK_SIZE - len(content),
                "source": "file",
            })
        else:
            default = DEFAULTS.get(name, "")
            result.append({
                "block": name,
                "scope": scope,
                "size": len(default),
                "remaining": MAX_BLOCK_SIZE - len(default),
                "source": "default",
            })

    return result


def list_scopes() -> list[str]:
    """List all scopes (global + per-project)."""
    if not BLOCKS_DIR.exists():
        return ["global"]
    return [d.name for d in BLOCKS_DIR.iterdir() if d.is_dir()]


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Self-Editing Memory Blocks")
    parser.add_argument("--read", help="Read a block (persona/project/client/learned)")
    parser.add_argument("--replace", help="Block to replace text in")
    parser.add_argument("--old", help="Text to find (for --replace)")
    parser.add_argument("--new", help="Replacement text (for --replace)")
    parser.add_argument("--insert", help="Block to insert into")
    parser.add_argument("--text", help="Text to insert")
    parser.add_argument("--index", type=int, default=-1, help="Position (-1=append, 0=prepend)")
    parser.add_argument("--clear", help="Reset block to default")
    parser.add_argument("--rethink", help="Block to fully rewrite")
    parser.add_argument("--content", help="New content for --rethink")
    parser.add_argument("--scope", default="global", help="Scope (global or project name)")
    parser.add_argument("--list", action="store_true", help="List all blocks")
    parser.add_argument("--scopes", action="store_true", help="List all scopes")
    parser.add_argument("--assemble", action="store_true", help="Assemble full context")
    parser.add_argument("--export", action="store_true", help="Export all blocks")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.read:
        r = memory_read(args.read, args.scope)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"[{r['block']}] ({r['size']}/{r['max_size']} chars)\n")
            print(r["content"])
        return 0

    if args.replace and args.old and args.new:
        r = memory_replace(args.replace, args.old, args.new, args.scope)
        print(json.dumps(r, indent=2))
        return 0 if r["success"] else 1

    if args.insert and args.text:
        r = memory_insert(args.insert, args.text, args.index, args.scope)
        print(json.dumps(r, indent=2))
        return 0 if r["success"] else 1

    if args.clear:
        r = memory_clear(args.clear, args.scope)
        print(json.dumps(r, indent=2))
        return 0

    if args.rethink and args.content:
        r = memory_rethink(args.rethink, args.content, args.scope)
        print(json.dumps(r, indent=2))
        return 0

    if args.list:
        blocks = list_blocks(args.scope)
        if args.json:
            print(json.dumps(blocks, indent=2))
        else:
            for b in blocks:
                pct = int(b["size"] / MAX_BLOCK_SIZE * 100)
                bar = "#" * (pct // 5) + "." * (20 - pct // 5)
                print(f"  {b['block']:10s} [{bar}] {b['size']:4d}/{MAX_BLOCK_SIZE} ({pct}%)")
        return 0

    if args.scopes:
        scopes = list_scopes()
        print(json.dumps(scopes) if args.json else "\n".join(f"  {s}" for s in scopes))
        return 0

    if args.assemble:
        ctx = assemble_context(args.scope)
        print(ctx)
        return 0

    if args.export:
        blocks = list_blocks(args.scope)
        data = {}
        for b in blocks:
            data[b["block"]] = memory_read(b["block"], args.scope)
        print(json.dumps(data, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
