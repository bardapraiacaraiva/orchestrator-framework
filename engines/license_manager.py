#!/usr/bin/env python3
"""
DARIO License Manager — Trial enforcement + VIP key activation.
================================================================
Public install (pip/npx) gets 7-day trial with limited features.
VIP key unlocks full access permanently.

Tiers:
    TRIAL   — 7 days, 3 engines, 1 parallel, no API execution, no evolution
    PRO     — unlimited, all engines, 3 parallel, API execution, evolution
    ENTERPRISE — unlimited, all engines, 5 parallel, multi-tenant, federation

Usage:
    python license_manager.py --status          # Show current license
    python license_manager.py --activate KEY    # Activate VIP key
    python license_manager.py --init-trial      # Initialize 7-day trial
    python license_manager.py --check           # Check if license valid (exit 0=ok, 1=expired)
    python license_manager.py --generate-key TIER EMAIL  # Generate VIP key (admin only)
    python license_manager.py --json

Key format: DARIO-XXXX-XXXX-XXXX-TIER
    DARIO-A1B2-C3D4-E5F6-PRO
    DARIO-G7H8-I9J0-K1L2-ENT
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
LICENSE_FILE = ORCH_DIR / "license.json"
MASTER_SECRET = "DARIO-BARDA-2026-ORCHESTRATOR-MASTER"  # For key generation

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("license")

TIERS = {
    "trial": {
        "name": "Trial (7 dias — acesso completo)",
        "duration_days": 7,
        "max_parallel": 3,
        "engines_allowed": "all",
        "features": {
            "api_execution": True,
            "evolution_engine": True,
            "llm_judge": True,
            "predictive_dispatch": True,
            "chain_executor": True,
            "multi_tenancy": True,
            "federation": True,
            "plugins": True,
            "adaptive_rubrics": True,
            "dashboard": True,
            "task_templates": True,
        },
    },
    "pro": {
        "name": "Professional",
        "duration_days": None,  # Permanent
        "max_parallel": 3,
        "engines_allowed": "all",
        "features": {
            "api_execution": True,
            "evolution_engine": True,
            "llm_judge": True,
            "predictive_dispatch": True,
            "chain_executor": True,
            "multi_tenancy": False,
            "federation": False,
            "plugins": True,
            "adaptive_rubrics": True,
            "dashboard": True,
            "task_templates": True,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "duration_days": None,
        "max_parallel": 5,
        "engines_allowed": "all",
        "features": {
            "api_execution": True,
            "evolution_engine": True,
            "llm_judge": True,
            "predictive_dispatch": True,
            "chain_executor": True,
            "multi_tenancy": True,
            "federation": True,
            "plugins": True,
            "adaptive_rubrics": True,
            "dashboard": True,
            "task_templates": True,
        },
    },
}


# =============================================================================
# KEY GENERATION + VALIDATION
# =============================================================================

def generate_key(tier: str, email: str) -> str:
    """Generate a license key. Admin only — NEVER distribute this function."""
    tier_suffixes = {"starter": "STR", "pro": "PRO", "enterprise": "ENT"}
    if tier not in tier_suffixes:
        return None
    suffix = tier_suffixes[tier]
    payload = f"{MASTER_SECRET}:{tier}:{email}:{datetime.now().isoformat()}"
    h = hashlib.sha256(payload.encode()).hexdigest().upper()
    key = f"DARIO-{h[:4]}-{h[4:8]}-{h[8:12]}-{suffix}"
    return key


def validate_key(key: str) -> dict:
    """Validate a license key format and determine tier."""
    if not key or not key.startswith("DARIO-"):
        return {"valid": False, "reason": "Invalid key format"}

    parts = key.split("-")
    if len(parts) != 5:
        return {"valid": False, "reason": "Key must have 5 segments (DARIO-XXXX-XXXX-XXXX-TIER)"}

    suffix = parts[4].upper()
    tier_map = {"STR": "starter", "PRO": "pro", "ENT": "enterprise"}
    if suffix in tier_map:
        return {"valid": True, "tier": tier_map[suffix]}
    else:
        return {"valid": False, "reason": f"Unknown tier suffix: {suffix}"}


# =============================================================================
# LICENSE FILE
# =============================================================================

def load_license() -> dict:
    """Load current license."""
    if LICENSE_FILE.exists():
        try:
            return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_license(lic: dict):
    """Save license to file."""
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(json.dumps(lic, indent=2), encoding="utf-8")


def init_trial() -> dict:
    """Initialize a 7-day trial license."""
    now = datetime.now(timezone.utc)
    lic = {
        "tier": "trial",
        "name": TIERS["trial"]["name"],
        "key": None,
        "email": None,
        "activated_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
        "max_parallel": TIERS["trial"]["max_parallel"],
        "features": TIERS["trial"]["features"],
        "engines_allowed": TIERS["trial"]["engines_allowed"],
        "status": "active",
    }
    save_license(lic)
    return lic


def activate_key(key: str) -> dict:
    """Activate a VIP license key."""
    validation = validate_key(key)
    if not validation["valid"]:
        return {"success": False, "error": validation["reason"]}

    tier = validation["tier"]
    tier_config = TIERS[tier]
    now = datetime.now(timezone.utc)

    lic = {
        "tier": tier,
        "name": tier_config["name"],
        "key": key,
        "email": None,
        "activated_at": now.isoformat(),
        "expires_at": None,  # Permanent
        "max_parallel": tier_config["max_parallel"],
        "features": tier_config["features"],
        "engines_allowed": tier_config["engines_allowed"],
        "status": "active",
    }
    save_license(lic)
    return {"success": True, "tier": tier, "name": tier_config["name"]}


def check_license() -> dict:
    """Check if current license is valid. Returns status."""
    lic = load_license()

    if not lic:
        return {"valid": False, "reason": "No license found. Run: python license_manager.py --init-trial",
                "tier": "none", "action": "init_trial"}

    tier = lic.get("tier", "trial")
    status = lic.get("status", "unknown")

    # Check expiration for trial
    if tier == "trial" and lic.get("expires_at"):
        try:
            expires = datetime.fromisoformat(lic["expires_at"])
            now = datetime.now(timezone.utc)
            if now > expires:
                lic["status"] = "expired"
                save_license(lic)
                remaining = 0
                return {
                    "valid": False,
                    "tier": "trial",
                    "reason": "Trial expired",
                    "expired_at": lic["expires_at"],
                    "action": "activate_key",
                    "message": "Your 7-day trial has expired. Activate a VIP key: python license_manager.py --activate DARIO-XXXX-XXXX-XXXX-PRO",
                }
            remaining = (expires - now).days
            return {
                "valid": True,
                "tier": "trial",
                "days_remaining": remaining,
                "expires_at": lic["expires_at"],
                "max_parallel": lic.get("max_parallel", 1),
                "features": lic.get("features", {}),
            }
        except Exception:
            pass

    # Pro/Enterprise = permanent
    if tier in ("pro", "enterprise"):
        return {
            "valid": True,
            "tier": tier,
            "name": lic.get("name"),
            "key": lic.get("key", "")[:15] + "...",
            "max_parallel": lic.get("max_parallel", 3),
            "features": lic.get("features", {}),
            "permanent": True,
        }

    return {"valid": False, "tier": tier, "reason": "Unknown license state"}


def is_feature_allowed(feature: str) -> bool:
    """Quick check if a specific feature is allowed."""
    lic = check_license()
    if not lic.get("valid"):
        return False
    features = lic.get("features", {})
    return features.get(feature, False)


def get_max_parallel() -> int:
    """Get allowed max parallel from license."""
    lic = check_license()
    if not lic.get("valid"):
        return 0
    return lic.get("max_parallel", 1)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO License Manager")
    parser.add_argument("--status", "-s", action="store_true", help="Show license status")
    parser.add_argument("--activate", "-a", help="Activate VIP key")
    parser.add_argument("--init-trial", action="store_true", help="Start 7-day trial")
    parser.add_argument("--check", "-c", action="store_true", help="Check if valid (exit code)")
    parser.add_argument("--generate-key", nargs=2, metavar=("TIER", "EMAIL"), help="Generate key (admin)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.init_trial:
        lic = init_trial()
        if args.json:
            print(json.dumps(lic, indent=2))
        else:
            expires = lic["expires_at"][:10]
            print(f"""
╔══════════════════════════════════════════╗
║  DARIO ORCHESTRATOR — 7-DAY TRIAL       ║
║                                          ║
║  Status:   ACTIVE                        ║
║  Expires:  {expires}                    ║
║  Parallel: 1 (max)                       ║
║  Engines:  6 of 26                       ║
║                                          ║
║  To unlock full access:                  ║
║  python license_manager.py --activate    ║
║    DARIO-XXXX-XXXX-XXXX-PRO             ║
╚══════════════════════════════════════════╝
""")
        return 0

    elif args.activate:
        result = activate_key(args.activate)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["success"]:
                print(f"""
╔══════════════════════════════════════════╗
║  DARIO ORCHESTRATOR — LICENSE ACTIVATED  ║
║                                          ║
║  Tier:     {result['name']:30s}  ║
║  Status:   PERMANENT                     ║
║  Parallel: {TIERS[result['tier']]['max_parallel']}                              ║
║  Engines:  ALL 26                        ║
║  Features: ALL UNLOCKED                  ║
║                                          ║
║  Thank you for supporting DARIO!         ║
╚══════════════════════════════════════════╝
""")
            else:
                print(f"  ERROR: {result['error']}")
        return 0 if result.get("success") else 1

    elif args.check:
        result = check_license()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["valid"]:
                tier = result["tier"]
                if tier == "trial":
                    print(f"  TRIAL — {result.get('days_remaining', '?')} days remaining")
                else:
                    print(f"  {result.get('name', tier).upper()} — permanent license")
            else:
                print(f"  INVALID — {result.get('reason', '?')}")
                if result.get("message"):
                    print(f"  {result['message']}")
        return 0 if result["valid"] else 1

    elif args.generate_key:
        tier, email = args.generate_key
        if tier not in ("starter", "pro", "enterprise"):
            print("Tier must be 'starter', 'pro' or 'enterprise'")
            return 1
        key = generate_key(tier, email)
        if args.json:
            print(json.dumps({"key": key, "tier": tier, "email": email}))
        else:
            print(f"  Generated key for {email} ({tier}):")
            print(f"  {key}")
            print(f"\n  Send to customer. They run:")
            print(f"  python license_manager.py --activate {key}")
        return 0

    elif args.status:
        lic = load_license()
        result = check_license()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if not lic:
                print("  No license. Run: python license_manager.py --init-trial")
            else:
                print(f"  Tier:      {lic.get('tier', '?')}")
                print(f"  Name:      {lic.get('name', '?')}")
                print(f"  Status:    {lic.get('status', '?')}")
                print(f"  Parallel:  {lic.get('max_parallel', '?')}")
                if lic.get("expires_at"):
                    print(f"  Expires:   {lic['expires_at'][:10]}")
                    if result.get("days_remaining") is not None:
                        print(f"  Remaining: {result['days_remaining']} days")
                else:
                    print(f"  Expires:   NEVER (permanent)")
                if lic.get("key"):
                    print(f"  Key:       {lic['key'][:15]}...")
                # Feature summary
                features = lic.get("features", {})
                locked = [k for k, v in features.items() if not v]
                unlocked = [k for k, v in features.items() if v]
                print(f"  Unlocked:  {len(unlocked)} features")
                if locked:
                    print(f"  Locked:    {', '.join(locked[:5])}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
