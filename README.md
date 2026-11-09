# Clinical Graph

A graph of clinical vocabularies and their bindings. It covers SNOMED CT (with the
LOINC Extension), LOINC, ICD-10-CM/PCS, WHO ICD-10, ICD-9-CM, RxNorm, ATC, WHO ICF and
the MeSH disease trees, with MED-RT's drug indications and contraindications, read directly
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
ingests slower.

Set the password, then start it with `scripts/neo4j.sh`, which runs Neo4j with
its private Java 21 and waits until it answers:

```bash
JAVA_HOME=~/neo4j/jdk-21 ~/neo4j/neo4j-community-$V/bin/neo4j-admin dbms set-initial-password '<password>'
scripts/neo4j.sh start     # also: stop, restart, status
```

The script assumes the paths above; for another version or location set
`NEO4J_VERSION`, `NEO4J_HOME` or `NEO4J_JAVA`.

The browser UI is at http://localhost:7474, Bolt at `bolt://localhost:7687`.
Neo4j does not start automatically after a reboot. Community has one user
database; other projects may share the instance, since everything here carries
the `Concept` label and is the only thing this project deletes
([Sharing the database](docs/graph_schema.md#sharing-the-database)).

Copy `.env.example` to `.env` and set `NEO4J_PASSWORD` (also `NEO4J_URI`,
`NEO4J_USERNAME`, `NEO4J_DATABASE` if not the defaults).

## Elasticsearch

The full-text indexes need **Elasticsearch 9.x** (the Python client is 9.x). For
a local, single-user setup, the official tarball needs no root access:

```bash
mkdir -p ~/elasticsearch && cd ~/elasticsearch
V=9.1.10   # use the archive for your CPU: linux-x86_64 or linux-aarch64
curl -LO https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-$V-linux-aarch64.tar.gz
tar -xzf elasticsearch-$V-linux-aarch64.tar.gz
```

Append to `elasticsearch-$V/config/elasticsearch.yml`:

```yaml
network.host: 127.0.0.1        # only reachable from this machine
discovery.type: single-node
xpack.security.enabled: false  # no username/password
path.data: /home/<you>/elasticsearch/data
path.logs: /home/<you>/elasticsearch/logs
```

Optionally set the memory in `config/jvm.options.d/heap.options` (e.g. `-Xms8g`
and `-Xmx8g` on two lines). Then start it with `scripts/elasticsearch.sh`, which
runs it in the background (pid in `~/elasticsearch/pid`) and waits until the
cluster is up:

```bash
scripts/elasticsearch.sh start     # also: stop, restart, status
```

The script assumes the paths above; for another version or location set
`ES_VERSION` or `ES_HOME`. Elasticsearch does not start automatically after a
reboot. The defaults in `.env.example` (`ELASTICSEARCH_URL=http://localhost:9200`,
no credentials) match this setup. Other projects can share the cluster: everything here is named
`clinical_graph_*`, and only those indexes are created or deleted.

## Building the graph

Each vocabulary is loaded as its own graph, then linked by `MAPS_TO` edges:
SNOMED CT → WHO ICD-10, SNOMED CT → ICD-10-CM, ICD-9-CM → SNOMED CT, ICD-9-CM ↔
ICD-10-CM/PCS (GEMs), LOINC term and part → SNOMED CT, LOINC part → RxNorm,
RxNorm → ATC and SNOMED CT, and last UMLS shared CUIs for the pairs none of those
links. MED-RT adds what drugs may treat, prevent or diagnose, or are
contraindicated with: `RXNORM -[MAY_TREAT]-> MESH`, and MeSH reaches the ICDs
and SNOMED CT through UMLS.

```bash
uv run clinical-graph ingest --dry-run   # read and count only, no Neo4j
uv run clinical-graph ingest             # SNOMED CT (+ LOINC Extension), LOINC, ICD-10-CM/PCS, ICD-10, RxNorm + ATC, ICF, ICD-9-CM, MeSH
uv run clinical-graph bind --dry-run     # read and resolve the maps only, no Neo4j
uv run clinical-graph bind               # cross-vocabulary MAPS_TO edges and MED-RT associations (UMLS last)
```

Both commands take source keys (`ingest snomed loinc`, `bind umls`) and
`--replace` to delete a source's nodes or edges before writing them again. All
writes are MERGEs, so re-running changes nothing. After re-binding an official
map, run `bind umls --replace` so UMLS fills only what is still missing.

Labels, properties, relationship types and example queries:
[docs/graph_schema.md](docs/graph_schema.md).

### Embeddings

Every current concept is embedded with
[SapBERT](https://huggingface.co/cambridgeltl/SapBERT-from-PubMedBERT-fulltext)
(768-d, `[CLS]` pooling). One model is used for every vocabulary, so all vectors
share one space. Each text of a concept is embedded: its name, synonyms, SNOMED
CT FSN, LOINC display/short/consumer/related names and ICD-10-CM index entries.
They are saved per source under `data/processed/embeddings/sapbert/<source>/`.
Each node then gets its name's vector as `embedding`, and each vocabulary label
gets its own vector index:

```bash
uv run clinical-graph embed build                 # all sources (GPU if available; resumes if interrupted)
uv run clinical-graph embed load                  # name vectors onto the nodes + vector indexes (after ingest)
uv run clinical-graph embed search "HbA1c" -v loinc            # saved embeddings: names and synonyms
uv run clinical-graph embed search "HbA1c" -v loinc --graph --kind term   # Neo4j vector index: names
```

Details: [docs/graph_schema.md](docs/graph_schema.md#embeddings).

### Full-text indexes

The same texts are indexed in Elasticsearch, for BM25 search. Each source
release gets one index, and each vocabulary is searched through an alias
(`clinical_graph_icd10cm`, `clinical_graph_snomed`, ...):

```bash
uv run clinical-graph es build                     # all sources; up-to-date ones are skipped
uv run clinical-graph es build loinc --recreate    # rebuild one; searches keep working meanwhile
uv run clinical-graph es search "hba1c" -v loinc --kind term [--fuzzy] [--exact-boost 10]
```

Details: [docs/elasticsearch.md](docs/elasticsearch.md).

### Resources

Measured on the current build:

| | |
| --- | --- |
| `data/raw/` | ~15 GB, of which the UMLS full-release zip is 5.4 GB and the assembled `MRCONSO.RRF` 2.3 GB |
| Neo4j data directory | ~9 GB (`~/neo4j/data`) |
| Neo4j memory | 8 GB heap + 8 GB page cache (see above) |
| `bind umls --dry-run` | ~50 s, 1.4 GB peak RAM in the Python process |

## Layout

```text
scripts/neo4j.sh             # start | stop | restart | status the local Neo4j
scripts/elasticsearch.sh     # start | stop | restart | status the local Elasticsearch
sources.toml                 # every source release and the files read from it
sources.lock.json            # size + SHA-256 of those files, for reproducibility
docs/sources.md              # how to obtain each release; the bindings they contain
docs/graph_schema.md         # the Neo4j graph: labels, properties, relationships
docs/elasticsearch.md        # the Elasticsearch indexes: aliases, documents, analyzer
src/clinical_graph/
├── paths.py                 # data directory locations
├── model.py                 # Concept, Relation (within a vocabulary), Mapping (binding)
├── texts.py                 # which concepts and texts the search indexes hold
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
│   ├── icd9cm.py            # ICD-9-CM v32 (CMS), headers from UMLS
│   ├── mesh.py              # MeSH: C and F03 trees, and every MED-RT target
│   ├── medrt.py             # MED-RT: RxNorm -> MeSH associations (no nodes)
│   ├── snomed_icd10cm.py    # NLM SNOMED CT -> ICD-10-CM map (map only)
│   ├── icd9cm_snomed.py     # NLM ICD-9-CM -> SNOMED CT maps (map only)
│   ├── icd9cm_gems.py       # CMS GEMs ICD-9-CM <-> ICD-10-CM/PCS (map only)
│   └── umls.py              # UMLS shared CUIs (map only, supplementary, bound last)
├── graph_ingestion/         # write readers' output to Neo4j
│   ├── connection.py        # NEO4J_* settings from env / .env
│   ├── schema.py            # labels, constraint, indexes
│   ├── writer.py            # batched MERGE; relations within, MAPS_TO across vocabularies
│   ├── ingest.py            # ingest(), dry_run(), delete_vocabulary()
│   └── bindings.py          # bind(): resolve both ends, write MAPS_TO edges
├── embeddings/              # SapBERT embeddings of the concepts
│   ├── encoder.py           # SapBERT ([CLS], L2-normalised)
│   ├── store.py             # build(): readers -> data/processed/embeddings/sapbert/<source>/
│   ├── graph.py             # load(): node `embedding` + per-label vector indexes; search_graph()
│   └── search.py            # EmbeddingIndex: search over names and synonyms (memory-mapped)
├── elastic/                 # Elasticsearch full-text indexes of the concepts
│   ├── connection.py        # ELASTICSEARCH_* settings from env / .env
│   ├── mapping.py           # index / alias names, analyzer, document mapping
│   ├── build.py             # build(): one index per source release, aliases per vocabulary
│   └── search.py            # search(): BM25, collapsed per concept
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
   `bind umls --replace`; then `embed build <key>` (rebuilds, since the
   version changed), `embed load <key> --replace` and `es build <key>`.

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
