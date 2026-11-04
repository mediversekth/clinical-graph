# Elasticsearch indexes

`clinical-graph es build` indexes the vocabulary concepts in Elasticsearch for
full-text (BM25) search. The indexes hold the same concepts and texts as the
SapBERT embeddings ([graph_schema.md](graph_schema.md#embeddings)): both are
built from `src/clinical_graph/texts.py`, so a BM25 hit and a SapBERT hit can be
compared and merged by `concept_id`, which is also the Neo4j `Concept.id`.

```bash
uv run clinical-graph es build                     # all sources; up-to-date ones are skipped
uv run clinical-graph es build icd10cm --recreate  # rebuild one source
uv run clinical-graph es search "type 2 diabetes ketoacidosis" -v icd10cm -k 5
uv run clinical-graph es search "hba1c" -v loinc --kind term --exact-boost 10
uv run clinical-graph es search "metformn" -v rxnorm --fuzzy
```

Setup and connection (`ELASTICSEARCH_URL`, optional API key or user and
password): [README](../README.md#elasticsearch).

## Indexes and aliases

Each **source release** is one physical index,
`clinical_graph_<source>_<version>_<built>` (e.g.
`clinical_graph_loinc_2.83_20261104t135523`). Its `_meta` records the source,
version, build time and document count. Each **vocabulary** is searched through
an alias, `clinical_graph_<vocabulary>`, filtered on `vocabulary`. Search the
alias, never the physical index:

| Alias | Index (source) | Documents | Concepts |
| --- | --- | ---: | ---: |
| `clinical_graph_snomed` | `snomed` + `loinc_extension` | 809,006 | 423,822 |
| `clinical_graph_loinc` | `loinc` | 571,741 | 181,324 |
| `clinical_graph_icd10cm` | `icd10cm` | 165,759 | 98,403 |
| `clinical_graph_icd10pcs` | `icd10cm` | 79,256 | 79,256 |
| `clinical_graph_icd10` | `icd10` | 36,248 | 16,455 |
| `clinical_graph_rxnorm` | `rxnorm` | 173,290 | 125,244 |
| `clinical_graph_atc` | `rxnorm` | 7,656 | 7,000 |
| `clinical_graph_icf` | `icf` | 1,610 | 1,610 |
| **Total** | 7 indexes, ~300 MB | **1,844,566** | **933,114** |

Several aliases can be searched together: `index="clinical_graph_icd10cm,clinical_graph_icd10pcs"`.

A build fills a **new** index. When it is complete, one atomic alias update
points the aliases at it and deletes the source's earlier indexes. Searches
never see a half-built index and keep working during a rebuild, and a release
update leaves no old index behind. A source is skipped if a complete index of
its current `sources.toml` version exists; `--recreate` builds it anew anyway.

Everything here is named `clinical_graph_*`, and only those indexes are created
or deleted, so the cluster can be shared with other projects' indexes.

## Documents

One document per (concept, text). The concepts are the current, non-grouping
ones, and the texts are each concept's name, synonyms, SNOMED CT FSN, LOINC
display/short/consumer/related names and ICD-10-CM index entries. The rules
and per-vocabulary details are in
[graph_schema.md](graph_schema.md#embeddings). `_id` is
`<concept_id>#<n>`, the n-th text of the concept (`#0` is its name).

| Field | Type | Example | |
| --- | --- | --- | --- |
| `concept_id` | keyword | `icd10cm:E11.10` | Neo4j `Concept.id`; collapse on it for one hit per concept |
| `vocabulary` | keyword | `icd10cm` | |
| `code` | keyword | `E11.10` | as published |
| `kind` | keyword | `code`, `term`, `part`, `clinical_drug` | node `kind` |
| `name` | keyword | `Type 2 diabetes mellitus with ketoacidosis without coma` | the concept's name |
| `origin` | keyword | `name`, `synonym`, `fsn`, `index_term`, `related_name`, ... | where `text` comes from |
| `text` | text (`en_folded`) | `Diabetes, diabetic type 2 with ketoacidosis` | the searched text |
| `text.keyword` | keyword | | as published, for display and aggregations |
| `text.exact` | keyword, lowercased + ASCII-folded | | whole-text match, for exact-match boosts |
| `semantic_tag`, `extension` | keyword | `disorder`, `loinc` | `SNOMEDCT` |
| `class`, `order_obs`, `part_type` | keyword | `CHEM`, `Both`, `COMPONENT` | `LOINC` terms / parts |
| `billable` | boolean | | `ICD10CM`, `ICD10PCS` |
| `code_no_dot` | keyword | `E1110` | `ICD10CM` (the form MIMIC uses) |

The mapping is `dynamic: strict`. The concept fields have the same names as the
node properties.

## Analyzer

`en_folded` (used by every vocabulary): standard tokenizer, lowercase, ASCII
folding, English possessive and stemmer, and Lucene's English stop words **minus** *no* and *not*, since in
clinical text they change the meaning (*No known allergies*).

## Searching

`clinical_graph.elastic.search` matches `text` (`operator` `or`/`and`, optional
`fuzziness`, `minimum_should_match`), optionally boosts phrase and exact matches
of the span, filters on exact field values and collapses on `concept_id`:

```python
from clinical_graph.elastic import QueryOptions, search
from clinical_graph.model import Vocabulary

hits = search(
    ["acute kidney injury"],
    Vocabulary.SNOMED,
    top_k=10,
    options=QueryOptions(exact_boost=10, phrase_boost=2),
    filters={"semantic_tag": "disorder"},
)  # [[{"id": "snomed:14669001", "text": ..., "origin": ..., "name": ..., "score": ...}]]
```

The raw query, for other clients:

```json
POST clinical_graph_snomed/_search
{
  "query": {"bool": {
    "must":   [{"match": {"text": {"query": "acute kidney injury"}}}],
    "should": [{"term": {"text.exact": {"value": "acute kidney injury", "boost": 10}}}],
    "filter": [{"term": {"semantic_tag": "disorder"}}]
  }},
  "collapse": {"field": "concept_id"},
  "size": 10
}
```
