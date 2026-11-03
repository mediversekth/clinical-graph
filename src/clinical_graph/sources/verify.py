"""Check that the source files are present and unchanged.

``sources.lock.json`` records the size and SHA-256 of every manifest file found on
disk. Committing it pins the exact bytes a graph was built from; anyone rebuilding
can run ``clinical-graph sources verify`` to see whether their downloads match.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from clinical_graph import paths
from clinical_graph.sources.manifest import Source, load_manifest

_CHUNK = 1 << 20


class FileState(StrEnum):
    """Outcome of checking one file."""

    OK = "ok"
    MISSING = "missing"
    MISSING_OPTIONAL = "missing (optional)"
    CHANGED = "checksum differs from lock"
    UNLOCKED = "present, not in lock"


@dataclass(frozen=True, slots=True)
class FileStatus:
    """Result of checking one manifest file."""

    source: str
    path: str
    state: FileState

    @property
    def is_problem(self) -> bool:
        """Whether this result should fail verification."""
        return self.state in {FileState.MISSING, FileState.CHANGED}


def sha256(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def build_lock(
    sources: Iterable[Source], raw_dir: Path | None = None
) -> dict[str, dict[str, Any]]:
    """Compute size and checksum of every manifest file that exists.

    Args:
        sources: The sources to lock.
        raw_dir: The raw data directory; defaults to :func:`paths.raw_dir`.

    Returns:
        ``{source key: {"version": ..., "files": {path: {"size", "sha256"}}}}``.
    """
    lock: dict[str, dict[str, Any]] = {}
    for source in sources:
        files: dict[str, dict[str, int | str]] = {}
        for f in source.files:
            p = source.root(raw_dir) / f.path
            if p.is_file():
                files[f.path] = {"size": p.stat().st_size, "sha256": sha256(p)}
        lock[source.key] = {"version": source.version, "files": files}
    return lock


def write_lock(lock: dict[str, dict[str, Any]], path: Path) -> None:
    """Write a lock to disk as stable, diff-friendly JSON."""
    path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")


def read_lock(path: Path) -> dict[str, dict[str, Any]]:
    """Read a lock file; returns an empty lock if it does not exist."""
    if not path.is_file():
        return {}
    return cast(dict[str, dict[str, Any]], json.loads(path.read_text()))


def check_sources(
    sources: Iterable[Source],
    lock: dict[str, dict[str, Any]] | None = None,
    raw_dir: Path | None = None,
) -> list[FileStatus]:
    """Check each manifest file for presence and, given a lock, for its checksum.

    Args:
        sources: The sources to check.
        lock: A lock from :func:`read_lock`; without one only presence is checked.
        raw_dir: The raw data directory; defaults to :func:`paths.raw_dir`.

    Returns:
        One :class:`FileStatus` per manifest file.
    """
    results: list[FileStatus] = []
    for source in sources:
        locked = cast(
            dict[str, dict[str, Any]],
            (lock or {}).get(source.key, {}).get("files", {}),
        )
        for f in source.files:
            p = source.root(raw_dir) / f.path
            if not p.is_file():
                state = FileState.MISSING if f.required else FileState.MISSING_OPTIONAL
            elif lock is None:
                state = FileState.OK
            elif f.path not in locked:
                state = FileState.UNLOCKED
            else:
                entry = locked[f.path]
                same = (
                    p.stat().st_size == entry["size"] and sha256(p) == entry["sha256"]
                )
                state = FileState.OK if same else FileState.CHANGED
            results.append(FileStatus(source.key, f.path, state))
    return results


def verify(checksums: bool = True) -> bool:
    """Check the manifest files on disk against ``sources.lock.json`` and report.

    Args:
        checksums: Also compare checksums; ``False`` checks presence only.

    Returns:
        ``True`` if no required file is missing or changed.
    """
    lock = read_lock(paths.SOURCES_LOCK) if checksums else None
    results = check_sources(load_manifest().values(), lock or None)
    for r in results:
        if r.state != FileState.OK:
            print(f"{r.state:28} {r.source}: {r.path}")
    problems = sum(r.is_problem for r in results)
    print(f"{len(results)} files checked, {problems} problems")
    return problems == 0


def update_lock() -> None:
    """Record the checksums of the manifest files in ``sources.lock.json``."""
    write_lock(build_lock(load_manifest().values()), paths.SOURCES_LOCK)
