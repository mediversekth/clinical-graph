# clinical-graph

A graph of clinical vocabularies and their bindings. The first version covers
SNOMED CT, LOINC and ICD-10-CM/PCS, read directly from their official releases.

## Setup

Needs [uv](https://docs.astral.sh/uv/) and Python 3.13+ (uv installs it if needed).

```bash
uv sync                      # .venv with the package and dev tools
uv run pre-commit install    # ruff on every commit
```

## Data

The vocabulary releases aren't in the repository. [docs/sources.md](docs/sources.md)
lists what to download, the licence each needs, and where to unpack it
(`data/raw/` by default, or `$CLINICAL_GRAPH_DATA_DIR/raw/`). Then check the files
are present and match `sources.lock.json`:

```bash
uv run clinical-graph sources list     # each source and where it goes
uv run clinical-graph sources verify   # files present, checksums match the lock
uv run clinical-graph sources lock     # record new checksums after updating a release
```

## Layout

```text
sources.toml                 # every source release and the files read from it
sources.lock.json            # size + SHA-256 of those files, for reproducibility
docs/sources.md              # how to obtain each release; the bindings they contain
src/clinical_graph/
├── paths.py                 # data directory locations
├── model.py                 # Concept, Relation (within a vocabulary), Mapping (binding)
├── sources/                 # manifest loading, presence and checksum checks
├── vocabularies/            # one reader per source: snomed, loinc, icd10cm
│   └── base.py              # VocabularyReader: iter_concepts / iter_relations / iter_mappings
└── cli.py                   # `clinical-graph` command
```

Readers turn one release into vocabulary-neutral records and know nothing about the
graph backend, so building or exporting the graph is a separate step that consumes
them. Concept ids are `<vocabulary>:<code>` with the code as published
(`snomed:44054006`, `loinc:4548-4`, `icd10cm:E11.9`).

## Development

```bash
uv run ruff check . && uv run ruff format .
uv run pyright
```
