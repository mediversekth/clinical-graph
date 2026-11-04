# clinical-graph

A graph of clinical vocabularies and their bindings. It covers SNOMED CT (with the
LOINC Extension), LOINC, ICD-10-CM/PCS, WHO ICD-10, RxNorm, ATC and WHO ICF, read directly
from their official releases, linked by the maps those releases publish and, for
the pairs no official map links, by UMLS shared concepts (CUIs).

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

The graph is loaded into a local Neo4j **Community 2026.09** (Cypher 25), which
needs **Java 21**. Install both under `~/neo4j`, outside the repository:

```bash
mkdir -p ~/neo4j && cd ~/neo4j
V=2026.09.0
curl -LO https://dist.neo4j.org/neo4j-community-$V-unix.tar.gz && tar -xzf neo4j-community-$V-unix.tar.gz
# Java 21 from https://adoptium.net (Eclipse Temurin JDK 21), unpacked into ~/neo4j/jdk-21
```

Append to `~/neo4j/neo4j-community-$V/conf/neo4j.conf` (data outside the install
directory, so upgrading Neo4j keeps the database):

```properties
server.default_listen_address=127.0.0.1
server.directories.data=/home/<you>/neo4j/data
server.directories.logs=/home/<you>/neo4j/logs
server.memory.heap.initial_size=8g
server.memory.heap.max_size=8g
server.memory.pagecache.size=8g
```

8 GB heap + 8 GB page cache is what the full graph was built with; less works but
ingests slower. Neo4j must run with Java 21, so use a small wrapper:

```bash
cat > ~/neo4j/neo4j.sh <<EOF
#!/bin/sh
# Run Neo4j with its private Java 21. Usage: ~/neo4j/neo4j.sh start|stop|status|restart
export JAVA_HOME=$HOME/neo4j/jdk-21
exec $HOME/neo4j/neo4j-community-$V/bin/neo4j "\$@"
EOF
chmod +x ~/neo4j/neo4j.sh
```

Set the password, then start it:

```bash
JAVA_HOME=~/neo4j/jdk-21 ~/neo4j/neo4j-community-$V/bin/neo4j-admin dbms set-initial-password '<password>'
~/neo4j/neo4j.sh start    # also: stop, status, restart
```

The browser UI is at http://localhost:7474, Bolt at `bolt://localhost:7687`.
Neo4j does not start automatically after a reboot. Community has one user
database; other projects may share the instance, since everything here carries
the `Concept` label and is the only thing this project deletes
([Sharing the database](docs/graph_schema.md#sharing-the-database)).

Copy `.env.example` to `.env` and set `NEO4J_PASSWORD` (also `NEO4J_URI`,
`NEO4J_USERNAME`, `NEO4J_DATABASE` if not the defaults).

## Building the graph

Each vocabulary is loaded as its own graph, then linked by `MAPS_TO` edges:
SNOMED CT → WHO ICD-10, SNOMED CT → ICD-10-CM, LOINC term and part → SNOMED CT,
LOINC part → RxNorm, RxNorm → ATC and SNOMED CT, and last UMLS shared CUIs for
the pairs none of those links.

```bash
uv run clinical-graph ingest --dry-run   # read and count only, no Neo4j
uv run clinical-graph ingest             # SNOMED CT (+ LOINC Extension), LOINC, ICD-10-CM/PCS, ICD-10, RxNorm + ATC, ICF
uv run clinical-graph bind --dry-run     # read and resolve the maps only, no Neo4j
uv run clinical-graph bind               # cross-vocabulary MAPS_TO edges (UMLS last)
```

Both commands take source keys (`ingest snomed loinc`, `bind umls`) and
`--replace` to delete a source's nodes or edges before writing them again. All
writes are MERGEs, so re-running changes nothing. After re-binding an official
map, run `bind umls --replace` so UMLS fills only what is still missing.

Labels, properties, relationship types and example queries:
[docs/graph_schema.md](docs/graph_schema.md).

### Resources

Measured on the current build:

| | |
| --- | --- |
| `data/raw/` | ~15 GB, of which the UMLS full-release zip is 5.4 GB and the assembled `MRCONSO.RRF` 2.3 GB |
| Neo4j data directory | ~9 GB (`~/neo4j/data`, shared here with mediverse's nodes) |
| Neo4j memory | 8 GB heap + 8 GB page cache (see above) |
| `bind umls --dry-run` | ~50 s, 1.4 GB peak RAM in the Python process |

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
├── vocabularies/            # one reader per source, READERS in __init__.py
│   ├── base.py              # VocabularyReader: iter_concepts / iter_relations / iter_mappings / match
│   ├── snomed.py            # SNOMED CT International (RF2) + its map to WHO ICD-10
│   ├── loinc_extension.py   # SNOMED CT LOINC Extension: LOINC terms as SNOMED CT concepts
│   ├── loinc.py             # LOINC terms, parts, part maps to SNOMED CT and RxNorm
│   ├── icd10cm.py           # ICD-10-CM and ICD-10-PCS (CMS)
│   ├── icd10.py             # WHO ICD-10 (ClaML)
│   ├── rxnorm.py            # RxNorm + ATC, maps to ATC and SNOMED CT
│   ├── icf.py               # WHO ICF (simple tabulation)
│   ├── snomed_icd10cm.py    # NLM SNOMED CT -> ICD-10-CM map (map only)
│   └── umls.py              # UMLS shared CUIs (map only, supplementary, bound last)
├── graph_ingestion/         # write readers' output to Neo4j
│   ├── connection.py        # NEO4J_* settings from env / .env
│   ├── schema.py            # labels, constraint, indexes
│   ├── writer.py            # batched MERGE; relations within, MAPS_TO across vocabularies
│   ├── ingest.py            # ingest(), dry_run(), delete_vocabulary()
│   └── bindings.py          # bind(): resolve both ends, write MAPS_TO edges
└── cli.py                   # `clinical-graph` command
```

Readers turn one release into vocabulary-neutral records (`Concept`, `Relation`,
`Mapping` from `model.py`, as generators) and know nothing about Neo4j;
`graph_ingestion` consumes them. Concept ids are `<vocabulary>:<code>` with the
code as published (`snomed:44054006`, `loinc:4548-4`, `icd10cm:E11.9`); grouping
nodes add their kind (`icd10cm:block:E08-E13`). Relationship types are
UPPER_SNAKE_CASE, `ISA` (child → parent) is the hierarchy in every vocabulary, and
`MAPS_TO` is the only edge between vocabularies.

## Development

```bash
uv run ruff check . && uv run ruff format .   # lint + format (line length 88, Google docstrings)
uv run pyright                                # strict type checking
```

There is no test suite; check changes with `ingest --dry-run` / `bind --dry-run`
and against the counts in [docs/graph_schema.md](docs/graph_schema.md).
New commands go in `cli.py`.

### Updating a release

1. Download the new release as described in [docs/sources.md](docs/sources.md)
   and unpack it next to the old one.
2. Update the source's `version` (and `release_dir`, file paths) in `sources.toml`;
   reader paths are templates, `{v}` is filled from `version`.
3. `uv run clinical-graph sources verify --no-checksums`, then
   `uv run clinical-graph sources lock` to record the new checksums.
4. Update `docs/sources.md` (release, sizes) and any counts in
   `docs/graph_schema.md`.
5. Re-load: `ingest <key> --replace`, then `bind <key> --replace`, then
   `bind umls --replace`.

### Adding a source

1. Add a `[sources.<key>]` entry to `sources.toml` with every file the code reads
   (never hard-code paths; get them with `VocabularyReader.path(...)`), lock it,
   and document it in `docs/sources.md`.
2. Write a reader in `vocabularies/<key>.py` subclassing `VocabularyReader`: set
   `source_key`, `vocabularies` (a new vocabulary needs a `model.Vocabulary`
   member and a label in `graph_ingestion/schema.py` `LABELS`),
   `provenances` for its maps, and implement `iter_concepts`, `iter_relations`,
   `iter_mappings` and `match` (how codes published elsewhere resolve to its
   concepts: `exact`, `normalised` or `ancestor`).
3. Register it in `READERS` (`vocabularies/__init__.py`), before `umls`, which
   stays last.
4. Describe its labels, properties, relationships and maps in
   `docs/graph_schema.md`.
