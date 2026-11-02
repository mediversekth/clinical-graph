"""Load ``sources.toml``, the list of source releases and the files used from each."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from clinical_graph import paths


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One file of a source release."""

    path: str
    purpose: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class Source:
    """One source release, e.g. SNOMED CT International 20250901."""

    key: str
    title: str
    version: str
    publisher: str
    licence: str
    homepage: str
    download: str
    archive: str
    release_dir: str
    files: tuple[SourceFile, ...]

    def root(self, raw_dir: Path | None = None) -> Path:
        """Return the directory the release is unpacked into.

        Args:
            raw_dir: The raw data directory; defaults to :func:`paths.raw_dir`.
        """
        return (raw_dir or paths.raw_dir()) / self.release_dir

    def file(self, path: str, raw_dir: Path | None = None) -> Path:
        """Return the absolute path of one file of the release.

        Args:
            path: The file's path as listed in the manifest.
            raw_dir: The raw data directory; defaults to :func:`paths.raw_dir`.

        Raises:
            KeyError: If the file is not listed in the manifest.
        """
        if path not in {f.path for f in self.files}:
            raise KeyError(f"{path!r} is not listed for source {self.key!r}")
        return self.root(raw_dir) / path


def _parse_source(key: str, raw: dict[str, Any]) -> Source:
    files = tuple(
        SourceFile(
            path=str(f["path"]),
            purpose=str(f["purpose"]),
            required=bool(f.get("required", True)),
        )
        for f in cast(list[dict[str, Any]], raw.get("files", []))
    )
    return Source(
        key=key,
        title=str(raw["title"]),
        version=str(raw["version"]),
        publisher=str(raw["publisher"]),
        licence=str(raw["licence"]),
        homepage=str(raw["homepage"]),
        download=str(raw["download"]),
        archive=str(raw["archive"]),
        release_dir=str(raw["release_dir"]),
        files=files,
    )


def load_manifest(path: Path | None = None) -> dict[str, Source]:
    """Read the source manifest.

    Args:
        path: The manifest file; defaults to ``sources.toml`` in the repository.

    Returns:
        The sources, keyed by their manifest key (``snomed``, ``loinc``, ...).
    """
    with (path or paths.SOURCES_MANIFEST).open("rb") as fh:
        data = tomllib.load(fh)
    sources = cast(dict[str, dict[str, Any]], data.get("sources", {}))
    return {key: _parse_source(key, raw) for key, raw in sources.items()}
