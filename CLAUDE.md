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
uv run clinical-graph ingest [snomed loinc_extension loinc icd10cm icd10 rxnorm] [--replace]
uv run clinical-graph bind [snomed snomed_icd10cm loinc loinc_extension rxnorm] [--dry-run] [--replace]   # MAPS_TO, after ingest
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
  `ICD10PCS`, `ICD10`, `RXNORM`, `ATC`); never touch nodes without `:Concept`. Relations only join
  nodes with the same vocabulary label; the only edges across vocabularies are
  `MAPS_TO`, written by `bind` from readers' `iter_mappings` after resolving each
  target with the target reader's `match`. Schema: `docs/graph_schema.md` (keep it
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
- No tests: the user does not want them. New commands go in `cli.py`.
