"""
DARIO API Auth — API key authentication + Role-Based Access Control.
=====================================================================
Config in auth_config.yaml. Keys hashed with SHA-256.

Roles:
    admin    — full access to all endpoints
    operator — tasks, dispatch, pulse, chains (CRUD + execute)
    viewer   — read-only (GET endpoints only)

Usage:
    from auth import require_auth, require_role

    @app.get("/tasks", dependencies=[Depends(require_auth)])
    @app.post("/tasks", dependencies=[Depends(require_role("operator"))])
"""

import hashlib
import logging
from pathlib import Path
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

try:
    from ruamel.yaml import YAML
    yaml_engine = YAML()
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml_engine.load(f)
    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml_engine.dump(data, f)
except ImportError:
    import yaml
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


ORCH_DIR = Path.home() / ".claude" / "orchestrator"
AUTH_CONFIG = ORCH_DIR / "auth_config.yaml"

log = logging.getLogger("auth")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Role → permitted method+path patterns
ROLE_PERMISSIONS = {
    "admin": ["*"],
    "operator": ["GET:*", "POST:/tasks", "POST:/tasks/*", "POST:/dispatch",
                 "POST:/pulse", "POST:/chains/*", "POST:/state/transition",
                 "POST:/templates/*"],
    "viewer": ["GET:*"],
}


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def load_auth_config() -> dict:
    """Load auth configuration."""
    if not AUTH_CONFIG.exists():
        return {"enabled": False, "keys": {}}
    try:
        config = load_yaml(str(AUTH_CONFIG))
        return config if config else {"enabled": False, "keys": {}}
    except Exception:
        return {"enabled": False, "keys": {}}


def create_api_key(name: str, role: str = "viewer") -> str:
    """Generate and store a new API key."""
    import secrets
    key = f"dario_{secrets.token_hex(24)}"
    key_hash = hash_key(key)

    config = load_auth_config()
    config.setdefault("enabled", True)
    config["enabled"] = True
    config.setdefault("keys", {})
    config["keys"][key_hash] = {"name": name, "role": role}
    dump_yaml(config, str(AUTH_CONFIG))

    return key


def verify_key(api_key: str) -> dict:
    """Verify API key and return user info."""
    config = load_auth_config()
    if not config.get("enabled", False):
        return {"name": "local", "role": "admin"}  # Auth disabled = full access

    if not api_key:
        return None

    key_hash = hash_key(api_key)
    user = config.get("keys", {}).get(key_hash)
    return user


def check_permission(role: str, method: str, path: str) -> bool:
    """Check if role has permission for method+path."""
    permissions = ROLE_PERMISSIONS.get(role, [])
    for perm in permissions:
        if perm == "*":
            return True
        if ":" in perm:
            perm_method, perm_path = perm.split(":", 1)
            if perm_method == method or perm_method == "*":
                if perm_path == "*" or path.startswith(perm_path.rstrip("*")):
                    return True
        elif perm == f"{method}:*":
            return True
    return False


# FastAPI dependencies

async def require_auth(api_key: str = Security(api_key_header)):
    """Dependency: require valid API key (any role)."""
    config = load_auth_config()
    if not config.get("enabled", False):
        return {"name": "local", "role": "admin"}

    user = verify_key(api_key)
    if not user:
        raise HTTPException(401, "Invalid or missing API key")
    return user


def require_role(role: str):
    """Dependency factory: require specific role."""
    async def check(api_key: str = Security(api_key_header)):
        config = load_auth_config()
        if not config.get("enabled", False):
            return {"name": "local", "role": "admin"}

        user = verify_key(api_key)
        if not user:
            raise HTTPException(401, "Invalid or missing API key")

        user_role = user.get("role", "viewer")
        role_hierarchy = {"admin": 3, "operator": 2, "viewer": 1}
        if role_hierarchy.get(user_role, 0) < role_hierarchy.get(role, 0):
            raise HTTPException(403, f"Role '{user_role}' cannot access this endpoint (requires '{role}')")
        return user

    return check


# CLI for key management
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DARIO Auth — API key management")
    parser.add_argument("--create", help="Create API key for name")
    parser.add_argument("--role", default="viewer", choices=["admin", "operator", "viewer"])
    parser.add_argument("--enable", action="store_true", help="Enable auth")
    parser.add_argument("--disable", action="store_true", help="Disable auth")
    parser.add_argument("--list", action="store_true", help="List keys")
    parser.add_argument("--json", "-j", action="store_true")

    args = parser.parse_args()

    if args.create:
        key = create_api_key(args.create, args.role)
        if args.json:
            print(json.dumps({"name": args.create, "role": args.role, "key": key}))
        else:
            print(f"API Key created for '{args.create}' ({args.role}):")
            print(f"  {key}")
            print(f"\nUse: curl -H 'X-API-Key: {key}' http://localhost:8422/health")

    elif args.enable:
        config = load_auth_config()
        config["enabled"] = True
        dump_yaml(config, str(AUTH_CONFIG))
        print("Auth ENABLED. All requests now require X-API-Key header.")

    elif args.disable:
        config = load_auth_config()
        config["enabled"] = False
        dump_yaml(config, str(AUTH_CONFIG))
        print("Auth DISABLED. All requests accepted without key.")

    elif args.list:
        config = load_auth_config()
        print(f"Auth: {'ENABLED' if config.get('enabled') else 'DISABLED'}")
        for h, info in config.get("keys", {}).items():
            print(f"  [{info['role']:10s}] {info['name']} (hash: {h[:12]}...)")
