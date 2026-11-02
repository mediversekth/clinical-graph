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
```

## Conventions

- Python 3.13, src layout (`src/clinical_graph`), Google docstrings, ruff line length 88.
- Every source file the code reads must be listed in `sources.toml`; get its path with
  `VocabularyReader.path(...)` / `Source.file(...)`, never hard-code paths. When a
  release changes, update `sources.toml`, `docs/sources.md` and `sources.lock.json`
  together.
- Readers (`vocabularies/`) yield `Concept`, `Relation` and `Mapping` records from
  `model.py` as generators and stay backend-agnostic.
- Concept ids: `<vocabulary>:<code>`, code exactly as published (`icd10cm:E11.9`).
  Relationship types: upper case, no underscores (`ISA`, `REPLACEDBY`, `EXCLUDES1`).
- The SNOMED International map targets WHO ICD-10 (`Vocabulary.ICD10`), not ICD-10-CM.
- No tests: the user does not want them. New commands go in `cli.py`.
