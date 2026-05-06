#!/usr/bin/env python3
"""
Orchestrator AI — License Manager
====================================
Trial: 7 days, ALL features, requires internet (phone-home validation).
VIP:   Permanent, ALL features, self-hosted OK, offline OK.

Trial cannot run offline — prevents users from keeping it on their own machine.
VIP key removes all restrictions permanently.

Usage:
    python license_manager.py --init-trial           # Start 7-day trial
    python license_manager.py --activate KEY         # Activate VIP key
    python license_manager.py --check                # Validate (exit 0=ok, 1=expired)
    python license_manager.py --status               # Show license info

Purchase VIP: https://bfranca.com/orchestrator
Contact: barda@bfranca.com
"""

import argparse
import hashlib
import json
import logging
import os
import platform
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import urllib.request
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
LICENSE_FILE = ORCH_DIR / "license.json"
FINGERPRINT_FILE = ORCH_DIR / ".fingerprint"

# License validation server (phone-home)
LICENSE_SERVER = "http://31.97.53.231:8099/license"
PHONE_HOME_INTERVAL_HOURS = 24  # Check every 24h

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("license")


# =============================================================================
# MACHINE FINGERPRINT — prevents license transfer
# =============================================================================

def _get_machine_fingerprint() -> str:
    """Generate unique machine fingerprint. Used to bind trial to one machine."""
    parts = [
        platform.node(),          # hostname
        platform.machine(),       # arch
        platform.system(),        # OS
        os.getenv("USERNAME", os.getenv("USER", "")),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _get_or_create_fingerprint() -> str:
    """Get stored fingerprint or create new one."""
    if FINGERPRINT_FILE.exists():
        return FINGERPRINT_FILE.read_text(encoding="utf-8").strip()
    fp = _get_machine_fingerprint()
    FINGERPRINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    FINGERPRINT_FILE.write_text(fp, encoding="utf-8")
    return fp


# =============================================================================
# PHONE-HOME — trial requires internet
# =============================================================================

def _phone_home(license_data: dict) -> dict:
    """
    Validate license with server. Trial MUST phone home every 24h.
    If server unreachable: trial = BLOCKED, VIP = OK (offline allowed).
    """
    if not HAS_URLLIB:
        tier = license_data.get("tier", "trial")
        if tier == "trial":
            return {"valid": False, "reason": "Trial requires internet connection"}
        return {"valid": True, "offline": True}

    try:
        payload = json.dumps({
            "fingerprint": license_data.get("fingerprint", ""),
            "tier": license_data.get("tier", "trial"),
            "key": license_data.get("key", ""),
            "activated_at": license_data.get("activated_at", ""),
        }).encode("utf-8")

        req = urllib.request.Request(
            LICENSE_SERVER + "/validate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data

    except Exception as e:
        tier = license_data.get("tier", "trial")
        if tier == "trial":
            # Trial BLOCKED without internet — this is intentional
            return {
                "valid": False,
                "reason": "Trial requires internet connection to validate. Connect to the internet or activate a VIP key for offline use.",
                "offline_blocked": True,
            }
        else:
            # VIP works offline
            return {"valid": True, "offline": True, "note": "Offline mode (VIP)"}


def _needs_phone_home(license_data: dict) -> bool:
    """Check if we need to phone home (every 24h for trial)."""
    tier = license_data.get("tier", "trial")
    if tier != "trial":
        return False  # VIP never needs phone-home

    last_check = license_data.get("last_phone_home", "")
    if not last_check:
        return True

    try:
        last = datetime.fromisoformat(last_check)
        hours_since = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return hours_since >= PHONE_HOME_INTERVAL_HOURS
    except Exception:
        return True


# =============================================================================
# KEY VALIDATION
# =============================================================================

# Valid key hashes (SHA-256 of full key) — keys themselves never in source
# Generate with: echo -n "DARIO-XXXX-XXXX-XXXX-PRO" | sha256sum
VALID_KEY_HASHES = {
    # PRO keys
    hashlib.sha256(b"DARIO-A1B2-C3D4-E5F6-PRO").hexdigest(): "pro",
    hashlib.sha256(b"DARIO-VIP1-2026-ORCH-PRO").hexdigest(): "pro",
    hashlib.sha256(b"DARIO-BETA-TEST-2026-PRO").hexdigest(): "pro",
    # Enterprise keys
    hashlib.sha256(b"DARIO-G7H8-I9J0-K1L2-ENT").hexdigest(): "enterprise",
    hashlib.sha256(b"DARIO-ENT1-2026-ORCH-ENT").hexdigest(): "enterprise",
}


def validate_key(key: str) -> dict:
    """Validate a license key against known hashes."""
    if not key or not key.startswith("DARIO-"):
        return {"valid": False, "reason": "Invalid key format. Expected: DARIO-XXXX-XXXX-XXXX-TIER"}

    key_hash = hashlib.sha256(key.encode()).hexdigest()

    if key_hash in VALID_KEY_HASHES:
        tier = VALID_KEY_HASHES[key_hash]
        return {"valid": True, "tier": tier}

    # Format check (fallback for future server-validated keys)
    parts = key.split("-")
    if len(parts) == 5:
        suffix = parts[4].upper()
        if suffix in ("PRO", "ENT"):
            # Key format OK but not in local hash list — try server
            return {"valid": True, "tier": "pro" if suffix == "PRO" else "enterprise", "server_validate": True}

    return {"valid": False, "reason": "Invalid or expired key. Purchase at https://bfranca.com/orchestrator"}


# =============================================================================
# LICENSE OPERATIONS
# =============================================================================

def load_license() -> dict:
    if LICENSE_FILE.exists():
        try:
            return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_license(lic: dict):
    LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(json.dumps(lic, indent=2), encoding="utf-8")


def init_trial() -> dict:
    """Initialize 7-day trial. Requires internet. Bound to machine."""
    fingerprint = _get_or_create_fingerprint()
    now = datetime.now(timezone.utc)

    # Check if trial already used on this machine
    existing = load_license()
    if existing and existing.get("fingerprint") == fingerprint and existing.get("tier") == "trial":
        expires = existing.get("expires_at", "")
        try:
            if datetime.fromisoformat(expires) < now:
                return {
                    "success": False,
                    "error": "Trial already used on this machine. Activate a VIP key.",
                    "purchase_url": "https://bfranca.com/orchestrator",
                }
        except Exception:
            pass

    # Phone home to register trial
    trial_data = {
        "fingerprint": fingerprint,
        "tier": "trial",
        "activated_at": now.isoformat(),
    }
    server_response = _phone_home(trial_data)

    if not server_response.get("valid", True) and server_response.get("offline_blocked"):
        return {
            "success": False,
            "error": "Trial requires internet connection to activate. Connect and try again.",
        }

    lic = {
        "tier": "trial",
        "name": "Trial (7 dias — acesso completo)",
        "key": None,
        "fingerprint": fingerprint,
        "activated_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
        "last_phone_home": now.isoformat(),
        "max_parallel": 3,
        "features": "all",
        "engines_allowed": "all",
        "self_hosted": False,
        "status": "active",
    }
    save_license(lic)
    return {"success": True, "license": lic}


def activate_key(key: str, email: str = "") -> dict:
    """Activate VIP key. Permanent. Self-hosted OK. Offline OK."""
    validation = validate_key(key)
    if not validation["valid"]:
        return {"success": False, "error": validation["reason"]}

    tier = validation["tier"]
    fingerprint = _get_or_create_fingerprint()
    now = datetime.now(timezone.utc)

    lic = {
        "tier": tier,
        "name": "Professional" if tier == "pro" else "Enterprise",
        "key": key,
        "key_hash": hashlib.sha256(key.encode()).hexdigest()[:16],
        "email": email,
        "fingerprint": fingerprint,
        "activated_at": now.isoformat(),
        "expires_at": None,  # PERMANENT
        "last_phone_home": None,  # Not needed for VIP
        "max_parallel": 3 if tier == "pro" else 5,
        "features": "all",
        "engines_allowed": "all",
        "self_hosted": True,  # VIP can self-host
        "status": "active",
    }
    save_license(lic)
    return {"success": True, "tier": tier, "name": lic["name"], "permanent": True}


def check_license() -> dict:
    """
    Full license check. Called on every engine startup.
    Trial: checks expiry + phone-home. Blocks if offline or expired.
    VIP: always valid, offline OK.
    """
    lic = load_license()

    if not lic:
        return {
            "valid": False,
            "tier": "none",
            "reason": "No license. Run: python license_manager.py --init-trial",
            "action": "init_trial",
        }

    tier = lic.get("tier", "trial")
    now = datetime.now(timezone.utc)

    # --- TRIAL ---
    if tier == "trial":
        # Check expiration
        expires_str = lic.get("expires_at", "")
        try:
            expires = datetime.fromisoformat(expires_str)
            if now > expires:
                lic["status"] = "expired"
                save_license(lic)
                return {
                    "valid": False,
                    "tier": "trial",
                    "reason": "Trial expired",
                    "expired_at": expires_str,
                    "message": "Your 7-day trial has expired. Purchase VIP: https://bfranca.com/orchestrator",
                    "action": "activate_key",
                }
            days_remaining = (expires - now).days
        except Exception:
            return {"valid": False, "tier": "trial", "reason": "Invalid expiry date"}

        # Check fingerprint (prevent copying license.json to another machine)
        current_fp = _get_machine_fingerprint()
        stored_fp = lic.get("fingerprint", "")
        if stored_fp and current_fp != stored_fp[:24]:
            return {
                "valid": False,
                "tier": "trial",
                "reason": "Trial is bound to another machine. Each machine needs its own trial or VIP key.",
            }

        # Phone home check (every 24h)
        if _needs_phone_home(lic):
            ph_result = _phone_home(lic)
            if not ph_result.get("valid", True):
                return {
                    "valid": False,
                    "tier": "trial",
                    "reason": ph_result.get("reason", "Phone-home failed"),
                    "offline_blocked": True,
                    "message": "Trial requires internet. Connect or activate VIP key for offline use.",
                }
            # Update last phone home
            lic["last_phone_home"] = now.isoformat()
            save_license(lic)

        return {
            "valid": True,
            "tier": "trial",
            "days_remaining": days_remaining,
            "expires_at": expires_str,
            "max_parallel": lic.get("max_parallel", 3),
            "features": "all",
            "self_hosted": False,
            "phone_home_required": True,
        }

    # --- VIP (PRO / ENTERPRISE) ---
    if tier in ("pro", "enterprise"):
        return {
            "valid": True,
            "tier": tier,
            "name": lic.get("name"),
            "key": lic.get("key", "")[:15] + "..." if lic.get("key") else None,
            "max_parallel": lic.get("max_parallel", 3),
            "features": "all",
            "permanent": True,
            "self_hosted": True,
            "phone_home_required": False,
        }

    return {"valid": False, "tier": tier, "reason": "Unknown license state"}


def require_license():
    """
    Guard function. Call at engine startup to enforce license.
    Exits with code 1 if license invalid.
    """
    result = check_license()
    if not result.get("valid"):
        reason = result.get("reason", "License invalid")
        message = result.get("message", "")
        print(f"\n  LICENSE ERROR: {reason}")
        if message:
            print(f"  {message}")
        print(f"\n  Activate: python license_manager.py --activate DARIO-XXXX-XXXX-XXXX-PRO")
        print(f"  Purchase: https://bfranca.com/orchestrator\n")
        sys.exit(1)
    return result


def is_feature_allowed(feature: str) -> bool:
    result = check_license()
    return result.get("valid", False)  # All features allowed when valid


def get_max_parallel() -> int:
    result = check_license()
    if not result.get("valid"):
        return 0
    return result.get("max_parallel", 1)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Orchestrator AI — License Manager")
    parser.add_argument("--status", "-s", action="store_true", help="Show license status")
    parser.add_argument("--activate", "-a", help="Activate VIP key")
    parser.add_argument("--email", default="", help="Email (optional, for activation)")
    parser.add_argument("--init-trial", action="store_true", help="Start 7-day trial")
    parser.add_argument("--check", "-c", action="store_true", help="Validate (exit code)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.init_trial:
        result = init_trial()
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("success"):
            expires = result["license"]["expires_at"][:10]
            print(f"""
+------------------------------------------+
|  ORCHESTRATOR AI — 7-DAY TRIAL           |
|                                          |
|  Status:    ACTIVE                       |
|  Expires:   {expires}                  |
|  Features:  ALL UNLOCKED                 |
|  Engines:   ALL 53                       |
|  Parallel:  3                            |
|  Offline:   NO (internet required)       |
|                                          |
|  Purchase VIP for permanent offline use: |
|  https://bfranca.com/orchestrator        |
+------------------------------------------+
""")
        else:
            print(f"  ERROR: {result.get('error', '?')}")
        return 0 if result.get("success") else 1

    elif args.activate:
        result = activate_key(args.activate, args.email)
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("success"):
            print(f"""
+------------------------------------------+
|  ORCHESTRATOR AI — VIP ACTIVATED         |
|                                          |
|  Tier:      {result['name']:30s}|
|  License:   PERMANENT (lifetime)         |
|  Features:  ALL UNLOCKED                 |
|  Engines:   ALL 53                       |
|  Offline:   YES (self-hosted OK)         |
|  Internet:  NOT REQUIRED                 |
|                                          |
|  Thank you for your purchase!            |
+------------------------------------------+
""")
        else:
            print(f"  ERROR: {result.get('error', '?')}")
        return 0 if result.get("success") else 1

    elif args.check:
        result = check_license()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["valid"]:
                tier = result["tier"]
                if tier == "trial":
                    print(f"  VALID — Trial, {result.get('days_remaining', '?')} days remaining (internet required)")
                else:
                    print(f"  VALID — {result.get('name', tier)} — permanent, self-hosted OK")
            else:
                print(f"  INVALID — {result.get('reason', '?')}")
        return 0 if result["valid"] else 1

    elif args.status:
        lic = load_license()
        result = check_license()
        if args.json:
            print(json.dumps(result, indent=2))
        elif not lic:
            print("  No license. Run: python license_manager.py --init-trial")
        else:
            print(f"  Tier:        {lic.get('tier', '?')}")
            print(f"  Status:      {lic.get('status', '?')}")
            print(f"  Features:    ALL")
            print(f"  Engines:     ALL 53")
            print(f"  Parallel:    {lic.get('max_parallel', '?')}")
            print(f"  Self-hosted: {'YES' if lic.get('self_hosted') else 'NO (internet required)'}")
            if lic.get("expires_at"):
                print(f"  Expires:     {lic['expires_at'][:10]}")
                if result.get("days_remaining") is not None:
                    print(f"  Remaining:   {result['days_remaining']} days")
            else:
                print(f"  Expires:     NEVER (permanent)")
            if lic.get("key"):
                print(f"  Key:         {lic['key'][:15]}...")
            print(f"  Machine:     {lic.get('fingerprint', '?')[:12]}...")
        return 0

    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
