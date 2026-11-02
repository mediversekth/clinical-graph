"""Source release registry: what is downloaded, where it lives, and its checksums."""

from clinical_graph.sources.manifest import Source, SourceFile, load_manifest
from clinical_graph.sources.verify import (
    FileStatus,
    build_lock,
    check_sources,
    read_lock,
    update_lock,
    verify,
    write_lock,
)

__all__ = [
    "FileStatus",
    "Source",
    "SourceFile",
    "build_lock",
    "check_sources",
    "load_manifest",
    "read_lock",
    "update_lock",
    "verify",
    "write_lock",
]
