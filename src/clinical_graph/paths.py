"""Filesystem locations used by the project.

The data directory defaults to ``data/`` in the repository root and can be moved
with the ``CLINICAL_GRAPH_DATA_DIR`` environment variable. Source releases live
under ``<data dir>/raw/``, intermediate files under ``processed/`` and the built
graph under ``output/``.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCES_MANIFEST = PROJECT_ROOT / "sources.toml"
SOURCES_LOCK = PROJECT_ROOT / "sources.lock.json"


def data_dir() -> Path:
    """Return the data directory, honouring ``CLINICAL_GRAPH_DATA_DIR``."""
    override = os.environ.get("CLINICAL_GRAPH_DATA_DIR")
    return Path(override).expanduser().resolve() if override else PROJECT_ROOT / "data"


def raw_dir() -> Path:
    """Return the directory holding the unpacked source releases."""
    return data_dir() / "raw"


def processed_dir() -> Path:
    """Return the directory for intermediate, regenerable files."""
    return data_dir() / "processed"


def output_dir() -> Path:
    """Return the directory for the built graph."""
    return data_dir() / "output"
