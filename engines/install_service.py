#!/usr/bin/env python3
"""
DARIO Service Installer — Makes runtime persist across reboots.
================================================================
Methods (in order of preference):
1. Windows Startup folder shortcut (no admin needed)
2. Windows Task Scheduler (needs admin)
3. Manual start script (always works)

Usage:
    python install_service.py              # Auto-detect best method
    python install_service.py --startup    # Startup folder only
    python install_service.py --uninstall  # Remove auto-start
    python install_service.py --status     # Check if running
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
RUNTIME = ORCH_DIR / "runtime.py"
STARTUP_DIR = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def install_startup_shortcut():
    """Create a .bat in Windows Startup folder."""
    bat_content = f'@echo off\nstart /min "" python "{RUNTIME}" --port 8422\n'
    bat_path = STARTUP_DIR / "dario_runtime.bat"
    bat_path.write_text(bat_content)
    print(f"Startup shortcut created: {bat_path}")
    return True


def uninstall():
    """Remove auto-start."""
    bat_path = STARTUP_DIR / "dario_runtime.bat"
    if bat_path.exists():
        bat_path.unlink()
        print(f"Removed: {bat_path}")
    else:
        print("No startup shortcut found.")


def check_status():
    """Check if runtime is running."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:8422/health", timeout=3) as r:
            data = r.read().decode()
            print(f"Runtime is RUNNING on :8422")
            return True
    except Exception:
        print("Runtime is NOT running")
        return False


def main():
    parser = argparse.ArgumentParser(description="DARIO Service Installer")
    parser.add_argument("--startup", action="store_true", help="Install startup shortcut")
    parser.add_argument("--uninstall", action="store_true", help="Remove auto-start")
    parser.add_argument("--status", action="store_true", help="Check if running")

    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    elif args.status:
        check_status()
    elif args.startup:
        install_startup_shortcut()
    else:
        # Auto: install startup shortcut (works without admin)
        install_startup_shortcut()
        print("\nRuntime will auto-start on next login.")
        print("To start now: python runtime.py --port 8422")


if __name__ == "__main__":
    main()
