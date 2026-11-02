# Neo4j graph schema

`clinical-graph ingest` loads each vocabulary as its own graph inside one Neo4j
database. This page describes the nodes and relationships it creates.

```bash
uv run clinical-graph ingest --dry-run          # read and count, no Neo4j
uv run clinical-graph ingest                    # all sources: snomed loinc icd10cm
uv run clinical-graph ingest loinc icd10cm      # some of them
uv run clinical-graph ingest snomed --replace   # delete SNOMEDCT nodes first (after a release update)
```

The connection is configured by `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
and `NEO4J_DATABASE`, from the environment or a git-ignored `.env` (copy
`.env.example`). All writes are MERGEs, so running the ingestion again changes
nothing. Without `--replace`, concepts removed from a newer release stay in the
graph.

## Sharing the database

The local Neo4j is the Community instance set up in the mediverse project.
Community has a single user database, so this graph lives next to mediverse's
nodes (`ObjectConcept`, `ICD10Concept`, `LOINCConcept`, `ClinGraphNode`, MIMIC
nodes, ...). The two never mix:

- every node created here has the `Concept` label, which mediverse does not use;
- `--replace` and `delete_vocabulary` only delete `Concept` nodes;
- relationship types such as `ISA` exist in both, so always anchor queries on a
  label: `MATCH (:SNOMEDCT)-[:ISA]->(:SNOMEDCT)`, not `MATCH ()-[:ISA]->()`.

## Nodes

Every node: `:Concept` plus exactly one vocabulary label.

| Label | Vocabulary | Nodes (current releases) | `kind` values |
| --- | --- | --- | --- |
| `SNOMEDCT` | SNOMED CT International 20250901, with history | 525,649 (including inactive) | `concept` |
| `LOINC` | LOINC 2.83 | 238,424 | `term`, `part`, `hierarchy`, `group`, `parentgroup` |
| `ICD10CM` | ICD-10-CM FY2027 | 98,722 | `chapter`, `block`, `code` |
| `ICD10PCS` | ICD-10-PCS FY2027 | 80,174 | `table`, `code` |

Constraint and indexes: `concept_id` (unique `Concept.id`), range indexes on
`Concept.code` and `Concept.kind`, full-text index `concept_name` on `Concept.name`.

### Common properties

| Property | Description |
| --- | --- |
| `id` | `<vocabulary>:<key>`, unique; see below |
| `vocabulary` | `snomed`, `loinc`, `icd10cm`, `icd10pcs` |
| `code` | code as published (`44054006`, `4548-4`, `E11.9`, block range `E08-E13`) |
| `name` | display name (see per vocabulary) |
| `kind` | node type within the vocabulary |
| `active` | `false` for inactive / deprecated codes |
| `synonyms` | list of other names |

| `id` example | Node |
| --- | --- |
| `snomed:44054006` | SNOMED CT concept |
| `loinc:4548-4`, `loinc:LP16413-4`, `loinc:LG100-4` | LOINC term, part, group |
| `icd10cm:E11.9` | ICD-10-CM code (with dot) |
| `icd10cm:block:E08-E13`, `icd10cm:chapter:4` | ICD-10-CM block, chapter |
| `icd10pcs:0016070`, `icd10pcs:table:001` | ICD-10-PCS code, table |

### `SNOMEDCT`

SNOMED CT is loaded **with its history**, so codes, terms and hierarchies used in
older records (10-year-old EHRs, annotations made on older releases) are still in
the graph. Every concept ever published is a node, inactive ones included
(`active: false`). `name` is the US-English preferred term; `synonyms` are the
other US-acceptable synonyms. Extra properties:

| Property | Description |
| --- | --- |
| `fsn`, `semantic_tag` | fully specified name and its tag (`disorder`, `procedure`, ...) |
| `definition_status` | `primitive` / `defined` |
| `definition` | text definition, where one exists |
| `inactive_terms` | retired descriptions (`NIDDM` on Type 2 diabetes mellitus), for matching old text |
| `effective_time` | when the concept last changed (for an inactive concept: when it was retired) |
| `first_active` | when it was first active (from the Full release) |
| `inactivation_reason` | inactive concepts: `Duplicate component`, `Ambiguous component`, `Outdated component`, ... |
| `module_id` | |

### `LOINC`

| `kind` | Source | `name` | Extra properties |
| --- | --- | --- | --- |
| `term` | `Loinc.csv` | `LONG_COMMON_NAME` | `status`, `short_name`, `class`, `component`, `property`, `time_aspect`, `system`, `scale`, `method`, `order_obs` |
| `part` | `Part.csv` | `PartName` | `status`, `part_type`, `display_name` |
| `hierarchy` | `ComponentHierarchyBySystem.csv`, LP codes that are not parts | `CODE_TEXT` | |
| `group`, `parentgroup` | `GroupFile/` | group name | `status` |

`active` is `false` for `DEPRECATED` terms and for parts and groups whose status
is not `ACTIVE`.

### `ICD10CM` / `ICD10PCS`

`name` is the long title. Codes have `billable` and `short_name`; ICD-10-CM codes
also have `code_no_dot` (`E119`, the form MIMIC uses), and their `synonyms` are
the tabular inclusion terms. Chapters and blocks have `chapter` (the chapter
number); a chapter's `code` is its range (`E00-E89`).

## Relationships

Relationships only join two nodes with the same vocabulary label; the writer
refuses anything else. Types are UPPER_SNAKE_CASE, and `ISA` is the hierarchy
(child → parent) in every vocabulary.

### `SNOMEDCT`

**Edges are active and inactive.** Every relationship ever published is loaded,
and retired ones have `active: false`. Filter on `active` whenever you want the
current release: `MATCH (c:SNOMEDCT)-[r:ISA*]->(p) WHERE all(x IN r WHERE x.active)`.
Without the filter, `ISA*` also follows hierarchies that no longer exist.

| Type | Source | Properties |
| --- | --- | --- |
| `ISA` | inferred relationships, type 116680003 (622k active, 584k inactive) | see below |
| attribute types: `FINDING_SITE`, `ASSOCIATED_MORPHOLOGY`, `CAUSATIVE_AGENT`, `HAS_ACTIVE_INGREDIENT`, `METHOD`, `PROCEDURE_SITE_DIRECT`, ... (about 100) | inferred relationships, named after the attribute's FSN | see below |
| `PART_OF` (all inactive) | inferred and retired *additional* relationships, type 123005000 | see below |
| `REPLACED_BY`, `SAME_AS`, `POSSIBLY_EQUIVALENT_TO`, `POSSIBLY_REPLACED_BY`, `PARTIALLY_EQUIVALENT_TO`, `WAS_A`, `ALTERNATIVE`, `MOVED_TO` | historical association refsets, inactive → active concept | `id` (refset member UUID), `active`, `effective_time`, `first_active`, `refset_id` |
| `ANATOMY_STRUCTURE_AND_ENTIRE`, `ANATOMY_STRUCTURE_AND_PART` | anatomy association refsets | same as above |

Properties of relationships from `sct2_Relationship`:

| Property | Description |
| --- | --- |
| `id` | RF2 relationship id; the edge's identity (a retired and a current edge can join the same concepts in the same role group) |
| `active` | `false` when retired |
| `effective_time` | when the edge last changed: for a retired edge, when it was retired |
| `first_active` | when it was first active (from the Full release) |
| `group` | role group (`0` = ungrouped) |
| `type_id` | SCTID of the attribute type |
| `characteristic` | `inferred`, or `additional` (old, all inactive) |

`first_active` and `effective_time` give the period an edge was valid, except for
edges that were retired and then reactivated, which are rare. Querying the
hierarchy as of a date `d` (`'20150131'`):
`WHERE all(x IN r WHERE x.first_active <= d AND (x.active OR x.effective_time > d))`.

Relationships with concrete values (drug strengths) have no target node and are
not loaded.

### `LOINC`

| Type | From → to | Properties |
| --- | --- | --- |
| `COMPONENT`, `PROPERTY`, `TIME`, `SYSTEM`, `SCALE`, `METHOD` | term → part (six primary axes) | |
| `CLASS`, `ANALYTE`, `ANALYTE_CORE`, `ANALYTE_SUFFIX`, `ANALYTE_DIVISOR`, `ANALYTE_NUMERATOR`, `ANALYTE_GENE`, `SYSTEM_CORE`, `SUPER_SYSTEM`, `TIME_CORE`, `TIME_MODIFIER`, `CHALLENGE`, `ADJUSTMENT`, `COUNT` | term → part (supplementary links) | |
| `RADIOLOGY`, `DOCUMENT` | term → part (RSNA playbook, document ontology) | `axis` (e.g. `modality-type`) |
| `ISA` | child → parent in the component hierarchy | |
| `REPLACED_BY` | deprecated term → replacement | `comment` |
| `IN_GROUP` | term → group, group → parent group | |
| `IN_PANEL` | term → panel it is a direct member of | `sequence` |

### `ICD10CM` / `ICD10PCS`

| Type | From → to | Properties |
| --- | --- | --- |
| `ISA` | code → parent code / block; block → chapter (CM); code → table (PCS) | |
| `EXCLUDES1`, `EXCLUDES2`, `CODE_FIRST`, `CODE_ALSO`, `USE_ADDITIONAL` | chapter / block / code holding the tabular note → each code or block it references | `notes` (note texts) |

## Example queries

```cypher
// Ancestors of type 2 diabetes in the current SNOMED CT release
MATCH (c:SNOMEDCT {code: '44054006'})-[r:ISA*1..]->(a:SNOMEDCT)
WHERE all(x IN r WHERE x.active)
RETURN DISTINCT a.code, a.name;

// An inactive SNOMED CT code from an old record: why it was retired, and what replaces it
// (15394000 Toxemia of pregnancy -> 398254007 Pre-eclampsia)
MATCH (old:SNOMEDCT {code: '15394000'})
OPTIONAL MATCH (old)-[h:REPLACED_BY|SAME_AS|POSSIBLY_EQUIVALENT_TO WHERE h.active]->(new)
RETURN old.name, old.inactivation_reason, type(h), new.code, new.name;

// A LOINC term and its six primary axes
MATCH (t:LOINC {code: '4548-4'})-[r:COMPONENT|PROPERTY|TIME|SYSTEM|SCALE|METHOD]->(p:LOINC)
RETURN type(r), p.code, p.name;

// What an ICD-10-CM code excludes
MATCH (c:ICD10CM {code: 'E11.9'})-[:ISA*0..]->(h)-[r:EXCLUDES1|EXCLUDES2]->(x:ICD10CM)
RETURN h.id, type(r), x.id, x.name;

// Full-text search across all vocabularies
CALL db.index.fulltext.queryNodes('concept_name', 'hemoglobin a1c') YIELD node, score
RETURN node.id, node.name, score LIMIT 10;
```
