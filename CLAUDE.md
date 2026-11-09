# CLAUDE.md

A graph of clinical vocabularies (SNOMED CT, LOINC, ICD-10-CM/PCS) and their
bindings, built from the official releases. Independent of mediverse: do not import
from or read data paths of that project.

## Commands

```bash
uv sync
uv run ruff check . && uv run ruff format .
uv run pyright                      # strict
uv run clinical-graph sources verify
uv run clinical-graph ingest --dry-run   # readers only, no Neo4j
uv run clinical-graph ingest [snomed loinc_extension loinc icd10cm icd10 rxnorm icf icd9cm mesh] [--replace]
uv run clinical-graph bind [snomed snomed_icd10cm icd9cm_snomed icd9cm_gems loinc loinc_extension rxnorm medrt umls] [--dry-run] [--replace]   # MAPS_TO + associations, after ingest
uv run clinical-graph embed build [sources] [--overwrite]   # SapBERT -> data/processed/embeddings/sapbert/<source>/
uv run clinical-graph embed load [sources] [--replace]      # node `embedding` + vector indexes, after ingest
uv run clinical-graph embed search TEXT -v VOCABULARY [--graph]
uv run clinical-graph es build [sources] [--recreate]       # Elasticsearch, one index per source release
uv run clinical-graph es search TEXT -v VOCABULARY [--kind K] [--fuzzy]
```

## Conventions

- Python 3.13, src layout (`src/clinical_graph`), Google docstrings, ruff line length 88.
- Every source file the code reads must be listed in `sources.toml`; get its path with
  `VocabularyReader.path(...)` / `Source.file(...)`, never hard-code paths. When a
  release changes, update `sources.toml`, `docs/sources.md` and `sources.lock.json`
  together.
- Readers (`vocabularies/`) yield `Concept`, `Relation` and `Mapping` records from
  `model.py` as generators and stay backend-agnostic.
- Concept ids: `<vocabulary>:<code>`, code exactly as published (`icd10cm:E11.9`);
  grouping nodes use `<vocabulary>:<kind>:<code>` (`icd10cm:block:E08-E13`).
  Relationship types: UPPER_SNAKE_CASE (`ISA`, `FINDING_SITE`, `REPLACED_BY`);
  `ISA` (child -> parent) is the hierarchy in every vocabulary.
- Reader file paths are templates: `{v}` is filled from the source's `version`.
- Neo4j: Community 2026.09 set up as in the README (one database, possibly shared
  with other projects such as mediverse). Every node
  here is `:Concept` plus a vocabulary label (`SNOMEDCT`, `LOINC`, `ICD10CM`,
  `ICD10PCS`, `ICD10`, `ICD9CM`, `RXNORM`, `ATC`, `ICF`, `MESH`); never touch nodes without `:Concept`. Relations only join
  nodes with the same vocabulary label; the only edges across vocabularies are
  `MAPS_TO` (same meaning), written by `bind` from readers' `iter_mappings` after
  resolving each target with the target reader's `match`, and associations
  (`Association`, different things: MED-RT's `MAY_TREAT`, ...), written by `bind`
  from `iter_associations` with both ends resolved; the reader lists their types
  in `association_types`. Schema: `docs/graph_schema.md` (keep it
  in sync).
- SNOMED CT keeps its history: inactive concepts *and* inactive edges are loaded
  (`active: false`), so Cypher over `SNOMEDCT` edges must filter `r.active` for the
  current release. Edges are keyed by RF2 relationship / refset member `id`.
- The SNOMED International map targets WHO ICD-10 (`Vocabulary.ICD10`), not ICD-10-CM;
  SNOMED -> ICD-10-CM is NLM's map, its own map-only source `snomed_icd10cm`
  (reader with no `vocabularies`, skipped by `ingest`). `bind --replace` deletes by
  the reader's `provenances`.
- The SNOMED CT LOINC Extension (`loinc_extension`, `LoincExtensionReader`, a
  `SnomedReader` on `_LO1010000_` files) adds `SNOMEDCT` nodes with
  `extension: "loinc"`; `ingest --replace` deletes by reader `extension` (`None` =
  nodes without one), so `snomed` and `loinc_extension` never delete each other's
  nodes.
- RxNorm (`rxnorm`) brings two vocabularies, `RXNORM` and `ATC` (the ATC atoms of
  the release); RxNorm keeps obsolete concepts (`active: false`), and an RxNorm
  edge's `active` is "both ends current".
- ICD-9-CM (`icd9cm`, label `ICD9CM`) holds diagnoses and procedures; codes are
  dotted (`dotted()`: undotted `0010` is ambiguous). CMS lists only billable codes:
  the headers and ranges come from the UMLS `ICD9CM` `HT` atoms (the `umls`
  source's MRCONSO, read through its manifest entry). Its maps are map-only
  sources: `icd9cm_snomed` (NLM) and `icd9cm_gems` (CMS GEMs, 2018, both directions).
- MeSH (`mesh`, label `MESH`) is partial: descriptors in trees C and F03, plus
  every descriptor or supplementary record MED-RT names (it reads the `medrt`
  file through its manifest entry); ids are record UIs (`mesh:D003924`,
  `mesh:C562385`), `ISA` from tree numbers and `HeadingMappedTo`. MeSH reaches
  SNOMED CT and the ICDs only through UMLS.
- MED-RT (`medrt`) has no nodes: only `RXNORM -> MESH` associations
  (`MAY_TREAT`, `MAY_PREVENT`, `MAY_DIAGNOSE`, `CONTRAINDICATED_WITH`, `INDUCES`,
  `provenance: "MED-RT"`), naming MeSH concept UIs (`M...`) that
  `MeshReader.match` resolves to their record. Bind it after `ingest mesh`.
- UMLS (`umls`) is a `supplementary` reader: shared-CUI pairs, both ends resolved,
  no `ancestor` matches, and only pairs no other `MAPS_TO` links; it stays last in
  `READERS` and is bound after the official maps.
- `texts.py` decides which concepts and which of their texts are searchable; the
  embeddings and the Elasticsearch indexes both use it, so they hold the same texts.
- Embeddings (SapBERT only) live in `embeddings/`: texts from `texts.py`, one folder per
  source on disk, one vector index per vocabulary label in Neo4j
  (`concept_embedding_<label>`, on `embedding`, the name's vector). Community
  Edition cannot store the `VECTOR` type: write with
  `db.create.setNodeVectorProperty`.
- Elasticsearch lives in `elastic/`: one index per source release
  (`clinical_graph_<source>_<version>_<built>`, `_meta.source` / `version`), searched
  through one filtered alias per vocabulary (`clinical_graph_<vocabulary>`); a
  build swaps the aliases atomically and deletes the source's older indexes. Only
  touch indexes named `clinical_graph_*` (the cluster is shared with mediverse).
- No tests: the user does not want them. New commands go in `cli.py`.
