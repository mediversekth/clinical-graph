# clinical-graph

A graph of clinical vocabularies and their bindings. The first version covers
SNOMED CT, LOINC, ICD-10-CM/PCS, WHO ICD-10, RxNorm and ATC, read directly from
their official releases.

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

## Neo4j

The vocabularies are loaded into Neo4j, one graph per vocabulary, then linked by
the maps the releases publish (`MAPS_TO` edges: SNOMED CT → WHO ICD-10, SNOMED CT → ICD-10-CM, LOINC term and
part → SNOMED CT, LOINC part → RxNorm, RxNorm → ATC and SNOMED CT). LOINC terms are also in SNOMED CT through the LOINC Extension..
Copy `.env.example` to `.env` and set `NEO4J_PASSWORD`, then:

```bash
uv run clinical-graph ingest --dry-run   # read and count only
uv run clinical-graph ingest             # SNOMED CT (+ LOINC Extension), LOINC, ICD-10-CM/PCS, ICD-10, RxNorm + ATC
uv run clinical-graph bind               # cross-vocabulary MAPS_TO edges
```

Labels, properties, relationship types and example queries:
[docs/graph_schema.md](docs/graph_schema.md).

## Layout

```text
sources.toml                 # every source release and the files read from it
sources.lock.json            # size + SHA-256 of those files, for reproducibility
docs/sources.md              # how to obtain each release; the bindings they contain
docs/graph_schema.md         # the Neo4j graph: labels, properties, relationships
src/clinical_graph/
├── paths.py                 # data directory locations
├── model.py                 # Concept, Relation (within a vocabulary), Mapping (binding)
├── sources/                 # manifest loading, presence and checksum checks
├── vocabularies/            # one reader per source: snomed, loinc, icd10cm, icd10
│   └── base.py              # VocabularyReader: iter_concepts / iter_relations / iter_mappings
├── graph_ingestion/         # write readers' output to Neo4j
│   ├── connection.py        # NEO4J_* settings from env / .env
│   ├── schema.py            # labels, constraint, indexes
│   ├── writer.py            # batched MERGE; relations within, MAPS_TO across vocabularies
│   ├── ingest.py            # ingest(), dry_run(), delete_vocabulary()
│   └── bindings.py          # bind(): resolve map targets, write MAPS_TO edges
└── cli.py                   # `clinical-graph` command
```

Readers turn one release into vocabulary-neutral records and know nothing about
Neo4j; `graph_ingestion` consumes them. Concept ids are `<vocabulary>:<code>` with the code as published
(`snomed:44054006`, `loinc:4548-4`, `icd10cm:E11.9`).

## Development

```bash
uv run ruff check . && uv run ruff format .
uv run pyright
```
