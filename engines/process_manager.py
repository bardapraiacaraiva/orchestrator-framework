#!/usr/bin/env python3
"""
ORCH Process Manager — Start, stop, and monitor services.

Usage:
  python3 process_manager.py start rag        Start RAG engine
  python3 process_manager.py start dashboard   Start dashboard server
  python3 process_manager.py stop rag          Stop RAG engine
  python3 process_manager.py list              List running services
  python3 process_manager.py health            Health check all services
"""

import os
import sys
import json
import signal
import socket
import subprocess
import time
from pathlib import Path
from datetime import datetime

HOME = Path.home()
ORCH = HOME / ".claude" / "orchestrator"
PID_DIR = ORCH / "pids"
LOG_DIR = ORCH / "service_logs"

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

# === SERVICE DEFINITIONS ===
SERVICES = {
    "rag": {
        "name": "RAG Engine",
        "cmd": ["/c/dario-rag/engine/.venv/Scripts/python.exe", "/c/dario-rag/engine/main.py"],
        "cwd": "/c/dario-rag/engine",
        "port": 8420,
        "health_url": "http://localhost:8420",
    },
    "dashboard": {
        "name": "Dashboard Server",
        "cmd": [sys.executable, "-m", "http.server", "8766", "--directory", str(ORCH)],
        "cwd": str(ORCH),
        "port": 8766,
        "health_url": "http://localhost:8766/dashboard.html",
    },
}

def ensure_dirs():
    PID_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

def is_port_open(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("localhost", port))
        s.close()
        return True
    except:
        return False

def get_pid(service):
    pid_file = PID_DIR / f"{service}.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            # Check if process is alive
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)
    return None

def start_service(service):
    ensure_dirs()
    if service not in SERVICES:
        print(f"  {RED}Unknown service: {service}{RESET}")
        print(f"  Available: {', '.join(SERVICES.keys())}")
        return

    svc = SERVICES[service]
    pid = get_pid(service)

    if pid:
        print(f"  {YELLOW}!{RESET} {svc['name']} already running (PID {pid})")
        return

    if is_port_open(svc["port"]):
        print(f"  {YELLOW}!{RESET} Port {svc['port']} already in use")
        return

    log_file = LOG_DIR / f"{service}.log"
    print(f"  {DIM}Starting {svc['name']}...{RESET}")

    try:
        with open(log_file, "a") as lf:
            lf.write(f"\n--- START {datetime.now().isoformat()} ---\n")
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=svc.get("cwd"),
                stdout=lf, stderr=lf,
                start_new_session=True
            )

        # Save PID
        (PID_DIR / f"{service}.pid").write_text(str(proc.pid))

        # Wait for port
        for _ in range(10):
            time.sleep(0.5)
            if is_port_open(svc["port"]):
                print(f"  {GREEN}✓{RESET} {svc['name']} started on port {svc['port']} (PID {proc.pid})")
                return

        print(f"  {YELLOW}!{RESET} {svc['name']} started (PID {proc.pid}) but port {svc['port']} not responding yet")

    except Exception as e:
        print(f"  {RED}✗{RESET} Failed to start {svc['name']}: {e}")

def stop_service(service):
    if service not in SERVICES:
        print(f"  {RED}Unknown service: {service}{RESET}")
        return

    svc = SERVICES[service]
    pid = get_pid(service)

    if not pid:
        print(f"  {DIM}{svc['name']} not running{RESET}")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        (PID_DIR / f"{service}.pid").unlink(missing_ok=True)
        print(f"  {GREEN}✓{RESET} {svc['name']} stopped (PID {pid})")
    except Exception as e:
        print(f"  {RED}✗{RESET} Failed to stop {svc['name']}: {e}")
        (PID_DIR / f"{service}.pid").unlink(missing_ok=True)

def list_services():
    print(f"\n  {BOLD}{CYAN}Running Services{RESET}\n")
    print(f"  {DIM}{'Service':<15} {'Status':<10} {'Port':<8} {'PID':<8} {'Name'}{RESET}")
    print(f"  {DIM}{'─'*15} {'─'*10} {'─'*8} {'─'*8} {'─'*20}{RESET}")

    for key, svc in SERVICES.items():
        pid = get_pid(key)
        port_up = is_port_open(svc["port"])

        if pid and port_up:
            status = f"{GREEN}running{RESET}"
        elif pid:
            status = f"{YELLOW}started{RESET}"
        elif port_up:
            status = f"{YELLOW}port up{RESET}"
        else:
            status = f"{DIM}stopped{RESET}"

        pid_str = str(pid) if pid else "—"
        print(f"  {key:<15} {status:<21} {svc['port']:<8} {pid_str:<8} {svc['name']}")

    print()

def health_check():
    print(f"\n  {BOLD}{CYAN}Health Check{RESET}\n")

    all_ok = True
    for key, svc in SERVICES.items():
        port_up = is_port_open(svc["port"])
        if port_up:
            print(f"  {GREEN}●{RESET} {svc['name']:<20} {GREEN}UP{RESET}  (port {svc['port']})")
        else:
            print(f"  {RED}●{RESET} {svc['name']:<20} {RED}DOWN{RESET}  (port {svc['port']})")
            all_ok = False

    # Check orchestrator files
    files_ok = True
    for name, path in [("company.yaml", ORCH / "company.yaml"), ("budget_tracker.py", ORCH / "budget_tracker.py"), ("generate_dashboard.py", ORCH / "generate_dashboard.py")]:
        if path.exists():
            print(f"  {GREEN}●{RESET} {name:<20} {GREEN}OK{RESET}")
        else:
            print(f"  {RED}●{RESET} {name:<20} {RED}MISSING{RESET}")
            all_ok = False
            files_ok = False

    print(f"\n  Overall: {GREEN+'HEALTHY' if all_ok else YELLOW+'DEGRADED' if files_ok else RED+'UNHEALTHY'}{RESET}\n")

def main():
    args = sys.argv[1:]
    if not args:
        list_services()
        return

    cmd = args[0]
    target = args[1] if len(args) > 1 else None

    if cmd == "start" and target:
        if target == "all":
            for svc in SERVICES:
                start_service(svc)
        else:
            start_service(target)
    elif cmd == "stop" and target:
        if target == "all":
            for svc in SERVICES:
                stop_service(svc)
        else:
            stop_service(target)
    elif cmd == "restart" and target:
        stop_service(target)
        time.sleep(1)
        start_service(target)
    elif cmd == "list":
        list_services()
    elif cmd == "health":
        health_check()
    elif cmd == "logs" and target:
        log_file = LOG_DIR / f"{target}.log"
        if log_file.exists():
            lines = log_file.read_text().split("\n")
            for line in lines[-30:]:
                print(f"  {DIM}{line}{RESET}")
        else:
            print(f"  {DIM}No logs for {target}{RESET}")
    else:
        print(f"""
  {BOLD}{CYAN}Process Manager{RESET}

  {BOLD}Commands:{RESET}
    start <service|all>    Start a service
    stop <service|all>     Stop a service
    restart <service>      Restart a service
    list                   List all services
    health                 Health check
    logs <service>         View service logs

  {BOLD}Services:{RESET}
    rag          RAG Engine (localhost:8420)
    dashboard    Dashboard Server (localhost:8766)
""")

if __name__ == "__main__":
    main()
