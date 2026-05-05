"""
DARIO FileLock — Cross-platform advisory file locking for YAML atomicity.
==========================================================================
Prevents corruption when 2 Claude sessions write to the same YAML simultaneously.

Usage:
    from filelock import atomic_yaml_write, atomic_yaml_read

    # Safe write (acquires lock, writes .tmp, renames)
    atomic_yaml_write(data, "/path/to/file.yaml")

    # Safe read (acquires shared lock during read)
    data = atomic_yaml_read("/path/to/file.yaml")

    # Context manager for multiple operations on same file
    with YAMLLock("/path/to/file.yaml") as lock:
        data = lock.read()
        data["field"] = "value"
        lock.write(data)

Mechanism:
    - Creates .lock file adjacent to target
    - Uses fcntl (Unix) or msvcrt (Windows) for OS-level locking
    - Write: lock → write .tmp → rename → unlock (atomic on POSIX, near-atomic on Windows)
    - Timeout: 5s default, raises TimeoutError if can't acquire
"""

import os
import sys
import time
from pathlib import Path
from contextlib import contextmanager

# YAML engine (same as other orchestrator modules)
try:
    from ruamel.yaml import YAML
    _yaml = YAML()
    _yaml.preserve_quotes = True
    _yaml.width = 200

    def _load(path):
        with open(path, 'r', encoding='utf-8') as f:
            return _yaml.load(f)

    def _dump(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            _yaml.dump(data, f)
except ImportError:
    import yaml
    def _load(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    def _dump(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


# Platform-specific locking
if sys.platform == 'win32':
    import msvcrt

    def _lock_file(f, timeout=5):
        deadline = time.time() + timeout
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except (IOError, OSError):
                if time.time() > deadline:
                    raise TimeoutError(f"Could not acquire lock within {timeout}s")
                time.sleep(0.05)

    def _unlock_file(f):
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass
else:
    import fcntl

    def _lock_file(f, timeout=5):
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except (IOError, OSError):
                if time.time() > deadline:
                    raise TimeoutError(f"Could not acquire lock within {timeout}s")
                time.sleep(0.05)

    def _unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class YAMLLock:
    """Context manager for locked YAML file operations."""

    def __init__(self, filepath, timeout=5):
        self.filepath = Path(filepath)
        self.lockfile = self.filepath.with_suffix(self.filepath.suffix + '.lock')
        self.timeout = timeout
        self._lock_fh = None
        self._data = None

    def __enter__(self):
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fh = open(self.lockfile, 'w')
        _lock_file(self._lock_fh, self.timeout)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._lock_fh:
            _unlock_file(self._lock_fh)
            self._lock_fh.close()
        # Clean up lock file (best effort)
        try:
            if self.lockfile.exists():
                self.lockfile.unlink()
        except OSError:
            pass
        return False

    def read(self):
        """Read YAML file while holding lock."""
        if self.filepath.exists():
            self._data = _load(str(self.filepath))
        else:
            self._data = None
        return self._data

    def write(self, data):
        """Write YAML atomically while holding lock (write .tmp then rename)."""
        tmp_path = self.filepath.with_suffix('.yaml.tmp')
        _dump(data, str(tmp_path))
        # Atomic rename (Windows needs target removed first)
        if sys.platform == 'win32' and self.filepath.exists():
            self.filepath.unlink()
        tmp_path.rename(self.filepath)
        self._data = data


def atomic_yaml_write(data, filepath, timeout=5):
    """Write YAML file with exclusive lock. Atomic via tmp+rename."""
    filepath = Path(filepath)
    with YAMLLock(filepath, timeout) as lock:
        lock.write(data)


def atomic_yaml_read(filepath, timeout=5):
    """Read YAML file with advisory lock (prevents read during write)."""
    filepath = Path(filepath)
    if not filepath.exists():
        return None
    with YAMLLock(filepath, timeout) as lock:
        return lock.read()


# =============================================================================
# WRITE-AHEAD LOG — Crash recovery for YAML mutations
# =============================================================================
# Pattern: Before mutating, write intent to WAL. After success, mark complete.
# On startup, check WAL for incomplete operations → replay or rollback.

WAL_DIR = Path.home() / ".claude" / "orchestrator" / "wal"


def wal_begin(filepath, operation: str, data) -> str:
    """Write intent to WAL before mutation. Returns wal_id."""
    import hashlib
    WAL_DIR.mkdir(parents=True, exist_ok=True)

    ts = time.time()
    wal_id = hashlib.md5(f"{filepath}{ts}".encode()).hexdigest()[:12]

    entry = {
        "wal_id": wal_id,
        "target": str(filepath),
        "operation": operation,
        "status": "pending",
        "timestamp": ts,
        "data_snapshot": data,
    }

    wal_file = WAL_DIR / f"{wal_id}.wal"
    _dump(entry, str(wal_file))
    return wal_id


def wal_commit(wal_id: str):
    """Mark WAL entry as committed (mutation succeeded)."""
    wal_file = WAL_DIR / f"{wal_id}.wal"
    if wal_file.exists():
        wal_file.unlink()  # Clean — committed ops don't need replay


def wal_rollback(wal_id: str):
    """Mark WAL entry as rolled back."""
    wal_file = WAL_DIR / f"{wal_id}.wal"
    if wal_file.exists():
        entry = _load(str(wal_file))
        entry["status"] = "rolled_back"
        _dump(entry, str(wal_file))


def wal_recover():
    """
    Check for incomplete WAL entries and replay/rollback.
    Call at startup (session_boot). Returns count of recovered ops.
    """
    if not WAL_DIR.exists():
        return 0

    recovered = 0
    for wal_file in WAL_DIR.glob("*.wal"):
        try:
            entry = _load(str(wal_file))
            if not entry or entry.get("status") != "pending":
                continue

            # Pending entry = crash happened mid-mutation
            target = Path(entry.get("target", ""))
            age = time.time() - entry.get("timestamp", 0)

            if age > 300:  # >5 min old = definitely a crash, not in-flight
                # Rollback: restore from snapshot if target exists but is corrupt
                if target.exists():
                    try:
                        _load(str(target))  # Test if readable
                    except Exception:
                        # Target is corrupt — restore from WAL snapshot
                        data = entry.get("data_snapshot")
                        if data:
                            _dump(data, str(target))
                            recovered += 1

                # Clean up WAL entry
                wal_file.unlink()

        except Exception:
            pass

    return recovered


def wal_write(filepath, data, timeout=5):
    """
    Transactional YAML write with WAL:
    1. WAL begin (write intent)
    2. Lock + write
    3. WAL commit (clean up)

    If crash between 1 and 3, wal_recover() will handle on next boot.
    """
    filepath = Path(filepath)

    # Read current state for rollback snapshot
    current = None
    if filepath.exists():
        try:
            current = _load(str(filepath))
        except Exception:
            pass

    # WAL: record intent with current state as snapshot
    wal_id = wal_begin(filepath, "write", current)

    try:
        # Perform the actual write
        with YAMLLock(filepath, timeout) as lock:
            lock.write(data)
        # Success — commit WAL
        wal_commit(wal_id)
    except Exception as e:
        # Failed — WAL stays pending for recovery
        wal_rollback(wal_id)
        raise
