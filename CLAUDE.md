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
uv run clinical-graph ingest [snomed loinc icd10cm] [--replace]
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
- Neo4j: the Community instance from mediverse, one shared database. Every node
  here is `:Concept` plus a vocabulary label (`SNOMEDCT`, `LOINC`, `ICD10CM`,
  `ICD10PCS`); never touch nodes without `:Concept`. `GraphWriter` only writes edges
  whose endpoints share a vocabulary label; cross-vocabulary bindings are a separate
  step. Schema: `docs/graph_schema.md` (keep it in sync).
- SNOMED CT keeps its history: inactive concepts *and* inactive edges are loaded
  (`active: false`), so Cypher over `SNOMEDCT` edges must filter `r.active` for the
  current release. Edges are keyed by RF2 relationship / refset member `id`.
- The SNOMED International map targets WHO ICD-10 (`Vocabulary.ICD10`), not ICD-10-CM.
- No tests: the user does not want them. New commands go in `cli.py`.
