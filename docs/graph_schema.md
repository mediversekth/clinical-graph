# Neo4j graph schema

`clinical-graph ingest` loads each vocabulary as its own graph inside one Neo4j
database; `clinical-graph bind` then links the graphs with `MAPS_TO` edges from
the maps the releases publish. This page describes the nodes and relationships
they create.

```bash
uv run clinical-graph ingest --dry-run          # read and count, no Neo4j
uv run clinical-graph ingest                    # all: snomed loinc_extension loinc icd10cm icd10 rxnorm icf
uv run clinical-graph ingest loinc icd10cm      # some of them
uv run clinical-graph ingest snomed --replace   # delete the source's nodes first (after a release update)
uv run clinical-graph bind --dry-run            # read and resolve the maps, no Neo4j
uv run clinical-graph bind snomed [--replace]   # SNOMED CT -> ICD-10 (WHO) MAPS_TO edges
uv run clinical-graph bind snomed_icd10cm       # SNOMED CT -> ICD-10-CM (NLM map)
uv run clinical-graph bind loinc                # LOINC part -> SNOMED CT, RxNorm
uv run clinical-graph bind rxnorm               # RxNorm -> ATC, SNOMED CT
uv run clinical-graph bind loinc_extension      # LOINC term -> SNOMED CT (LOINC Extension)
uv run clinical-graph bind umls                 # UMLS shared CUIs: the links still missing (last)
uv run clinical-graph embed build               # SapBERT embeddings to data/processed (see Embeddings)
uv run clinical-graph embed load                # node `embedding` + one vector index per label
```

The connection is configured by `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`
and `NEO4J_DATABASE`, from the environment or a git-ignored `.env` (copy
`.env.example`). All writes are MERGEs, so running the ingestion again changes
nothing. Without `--replace`, concepts removed from a newer release stay in the
graph. `--replace` deletes only the nodes of the sources named: `snomed` the
International nodes, `loinc_extension` the LOINC Extension ones (`extension:
'loinc'`). Replacing `snomed` also deletes the extension's edges into the
International hierarchy, so run `ingest loinc_extension` after it.

## Sharing the database

Neo4j is set up as described in the [README](../README.md#neo4j). Community has a
single user database, so if other projects use the same instance (locally,
mediverse: `ObjectConcept`, `ICD10Concept`, `LOINCConcept`, `ClinGraphNode`, MIMIC
nodes, ...), this graph lives next to their nodes. They never mix:

- every node created here has the `Concept` label, which the others must not use
  (mediverse does not);
- `--replace` and `delete_vocabulary` only delete `Concept` nodes;
- relationship types such as `ISA` exist in both, so always anchor queries on a
  label: `MATCH (:SNOMEDCT)-[:ISA]->(:SNOMEDCT)`, not `MATCH ()-[:ISA]->()`.

## Nodes

Every node: `:Concept` plus exactly one vocabulary label.

| Label | Vocabulary | Nodes (current releases) | `kind` values |
| --- | --- | --- | --- |
| `SNOMEDCT` | SNOMED CT International 20250901 and the LOINC Extension 20261021, with history | 525,649 + 47,998 (including inactive) | `concept` |
| `LOINC` | LOINC 2.83 | 238,424 | `term`, `part`, `hierarchy`, `group`, `parentgroup` |
| `ICD10CM` | ICD-10-CM FY2027 | 98,722 | `chapter`, `block`, `code` |
| `ICD10PCS` | ICD-10-PCS FY2027 | 80,174 | `table`, `code` |
| `ICD10` | WHO ICD-10 2019 | 16,751 | `chapter`, `block`, `code` |
| `RXNORM` | RxNorm full release 20261102, with obsolete concepts | 230,470 (125k current) | `ingredient`, `clinical_drug`, `branded_drug`, ... (one per term type) |
| `ATC` | WHO ATC, as in RxNorm (ATC 2026-01-28) | 7,000 | `anatomical_group`, `therapeutic_group`, `pharmacological_group`, `chemical_group`, `substance` |
| `ICF` | WHO ICF, 2026-01 release | 1,665 | `section`, `component`, `chapter`, `block`, `category`, `qualifier_group`, `qualifier` |

Constraint and indexes: `concept_id` (unique `Concept.id`), range indexes on
`Concept.code` and `Concept.kind`, full-text index `concept_name` on `Concept.name`,
and after `embed load` one vector index per label on `embedding` (see
[Embeddings](#embeddings)).

### Common properties

| Property | Description |
| --- | --- |
| `id` | `<vocabulary>:<key>`, unique; see below |
| `vocabulary` | `snomed`, `loinc`, `icd10cm`, `icd10pcs`, `icd10`, `rxnorm`, `atc`, `icf` |
| `code` | code as published (`44054006`, `4548-4`, `E11.9`, block range `E08-E13`) |
| `name` | display name (see per vocabulary) |
| `kind` | node type within the vocabulary |
| `active` | `false` for inactive / deprecated codes |
| `synonyms` | list of other names |
| `embedding` | SapBERT vector of `name` (768 floats), on current concepts after `embed load`; see [Embeddings](#embeddings) |

| `id` example | Node |
| --- | --- |
| `snomed:44054006` | SNOMED CT concept |
| `loinc:4548-4`, `loinc:LP16413-4`, `loinc:LG100-4` | LOINC term, part, group |
| `icd10cm:E11.9` | ICD-10-CM code (with dot) |
| `icd10cm:block:E08-E13`, `icd10cm:chapter:4` | ICD-10-CM block, chapter |
| `icd10pcs:0016070`, `icd10pcs:table:001` | ICD-10-PCS code, table |
| `icd10:E11.9`, `icd10:block:E10-E14`, `icd10:chapter:4` | WHO ICD-10 code, block, chapter |
| `rxnorm:6809`, `rxnorm:861007` | RxNorm concept (RXCUI): metformin; metformin hydrochloride 500 MG Oral Tablet |
| `atc:A10BA02`, `atc:A10` | ATC code: metformin; drugs used in diabetes |
| `icf:d4500`, `icf:block:b110-b139`, `icf:chapter:b1`, `icf:component:b` | ICF category (*Walking short distances*), block, chapter, component |

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
| `extension` | `loinc` on LOINC Extension nodes; absent on International ones |
| `loinc_code` | LOINC Extension: the LOINC term the concept models (`2345-7`) |

#### LOINC Extension (LOINC Ontology)

Not LOINC again: a SNOMED CT release whose concepts are new (only 33 of them are in
the International Edition). The `LOINC` node of a test and its LOINC Extension node
are linked by `MAPS_TO` (see *Bindings*); where to download it:
`docs/sources.md`.

The SNOMED CT LOINC Extension (source `loinc_extension`, module 11010000107) models
LOINC terms as SNOMED CT concepts: 46,981 observable entities, one per LOINC term
(`loinc_code`), plus about 1,000 substances, qualifiers and specimens they need.
Its nodes are ordinary `SNOMEDCT` nodes with `extension: 'loinc'`, and its edges are
ordinary SNOMED CT edges (below): `ISA` into the International hierarchy and the
observable attributes `COMPONENT`, `PROPERTY`, `DIRECT_SITE`, `INHERES_IN`,
`TIME_ASPECT`, `SCALE_TYPE`, `TECHNIQUE`, `RELATIVE_TO`, `TOWARDS`, `PROCESS_*`,
`PRECONDITION`, `USING_DEVICE`, ... It covers 46,958 of the 107,397 active LOINC
terms (44%).

The extension is built on International 20260701, newer than the loaded release:
1,938 of its edges point to International concepts that are not in the graph and are
skipped, and 33 International concepts it re-publishes keep their International
node. Loading a newer International release recovers both.

### `LOINC`

| `kind` | Source | `name` | Extra properties |
| --- | --- | --- | --- |
| `term` | `Loinc.csv` | `LONG_COMMON_NAME` | `status`, `short_name`, `display_name`, `consumer_name` (`ConsumerName.csv`), `related_names` (`RELATEDNAMES2`, list), `class`, `component`, `property`, `time_aspect`, `system`, `scale`, `method`, `order_obs` |
| `part` | `Part.csv` | `PartName` | `status`, `part_type`, `display_name` |
| `hierarchy` | `ComponentHierarchyBySystem.csv`, LP codes that are not parts | `CODE_TEXT` | |
| `group`, `parentgroup` | `GroupFile/` | group name | `status` |

`active` is `false` for `DEPRECATED` terms and for parts and groups whose status
is not `ACTIVE`.

### `ICD10CM` / `ICD10PCS`

`name` is the long title. Codes have `billable` and `short_name`; ICD-10-CM codes
also have `code_no_dot` (`E119`, the form MIMIC uses), their `synonyms` are
the tabular inclusion terms, and `index_terms` lists the alphabetic index entries
that point to the code, each subterm joined to its parents (`Diabetes, diabetic
type 2 with ketoacidosis`; nonessential modifiers left out). Chapters and blocks have `chapter` (the chapter
number); a chapter's `code` is its range (`E00-E89`).

### `ICD10` (WHO)

From WHO's ClaML file, 2019 edition. `name` is the title as WHO's own expanded
code list prints it (the long form where there is one, `C00.0` *Malignant
neoplasm: External upper lip*; `short_name` then holds the short one);
`synonyms` are the inclusion terms. A chapter's `code` is its range (`E00-E90`).

ClaML defines shared subdivisions once, as modifiers; they are expanded into
codes. 4,234 of the 16,455 codes are such optional subdivisions (5th-character
site codes in chapter XIII, `M00.01`; closed / open for fractures, `S72.01`)
that WHO's text edition does not list. Code properties:

| Property | Description |
| --- | --- |
| `code_no_dot` | `E119`, as many EHRs store it |
| `terminal` | no subdivisions under it |
| `generated` | created from a modifier (`E11.9` = `E11` + *.9 Without complications*) |
| `optional` | a subdivision WHO provides "for optional use" |
| `usage` | `dagger` or `asterisk` (dagger: cause, asterisk: manifestation) |
| `short_name`, `definition` | where WHO gives one |

WHO switches off the place and activity subdivisions of the external causes
(`W19.0`), so those are not generated.

### `RXNORM`

From the RxNorm full monthly release (`RXNCONSO`, `RXNSAT`). One node per RXCUI
with an RxNorm atom, **current and obsolete**: `active: false` for the 101k
concepts NLM has retired but still publishes (kept, like SNOMED CT's history, for
old prescriptions). `name` is the string of the concept's main atom; `kind` follows
its term type (`tty`):

| `tty` | `kind` | Example |
| --- | --- | --- |
| `IN`, `PIN`, `MIN` | `ingredient`, `precise_ingredient`, `multiple_ingredients` | metformin; metformin hydrochloride; glipizide / metformin |
| `SCDC`, `SCDF`, `SCDG`, `SCD` | `clinical_drug_component`, `clinical_drug_form`, `clinical_dose_form_group`, `clinical_drug` | metformin hydrochloride 500 MG; metformin Oral Tablet; metformin Oral Product; metformin hydrochloride 500 MG Oral Tablet |
| `SCDFP`, `SCDGP` | `clinical_drug_form_precise`, `clinical_dose_form_group_precise` | the same with the precise ingredient |
| `BN`, `SBDC`, `SBDF`, `SBDFP`, `SBDG`, `SBD` | `brand_name`, `branded_drug_component`, ... `branded_drug` | Glucophage; Glucophage 500 MG Oral Tablet |
| `GPCK`, `BPCK` | `generic_pack`, `branded_pack` | |
| `DF`, `DFG`, `ET` | `dose_form`, `dose_form_group`, `entry_term` | Oral Tablet; Oral Product |

| Property | Description |
| --- | --- |
| `tty` | term type of the main atom |
| `ndc` | current NDCs (11 digits, as RxNorm normalises them; the form MIMIC uses) on drugs and packs; 252k on 19,880 concepts |
| `prescribable_name` | the RxNorm prescribable name (`PSN`), where there is one |
| `strength`, `available_strength` | `RXN_STRENGTH` (components), `RXN_AVAILABLE_STRENGTH` (drugs) |
| `suppress` | the main atom's RxNorm suppress flag when not `N`: `O` obsolete, `E` suppressed by NLM editors |

`synonyms` are the other RxNorm strings (`SY`, `TMSY`, `PSN`). Retired RXCUIs that
were merged into another concept (`RXNCUI.RRF`) are not nodes; map targets naming
one resolve to its successor (`match: remapped`).

### `ATC`

The WHO Anatomical Therapeutic Chemical classification as distributed inside
RxNorm (`SAB=ATC`, version 2026-01-28), all five levels: 14 anatomical groups
(`A`), 94 therapeutic (`A10`), 271 pharmacological (`A10B`), 939 chemical groups
(`A10BA`) and 5,682 chemical substances (`A10BA02`). `level` is 1-5; `name` is
WHO's title (level 1 in capitals, as published), `synonyms` RxNorm's normalised
titles. A substance code is a substance *for one therapeutic use*: the same
substance can have several codes (mesna `R05CB05`, `V03AF01`). About 1,900
substances have no RxNorm ingredient (not marketed in the US). No DDDs: those are
only in WHO's paid ATC/DDD index.

### `ICF`

WHO's International Classification of Functioning, Disability and Health, from
the simple tabulation of the 2026-01 ICD-11 platform release. `name` is WHO's
title. The hierarchy:

| `kind` | Nodes | Example (`id`, `name`) |
| --- | --- | --- |
| `section` | 2 | `icf:section:category` *ICF Category*, `icf:section:qualifier` *ICF Qualifier* |
| `component` | 4 | `icf:component:b` *Body functions* (`s` body structures, `d` activities and participation, `e` environmental factors) |
| `chapter` | 30 | `icf:chapter:b1` *Mental functions* |
| `block` | 37 | `icf:block:b110-b139` *Global mental functions* |
| `category` | 1,543 | `icf:b110` *Consciousness functions* (1st level) ... `icf:b11420` *Orientation to self* (4th level) |
| `qualifier_group` | 5 | `icf:qualifier_group:1437901287` *Extent or magnitude of impairment* |
| `qualifier` | 44 | `icf:qi0` ... `icf:qi9`; `icf:qb0` *NO barrier*, `icf:qf0` *NO facilitator*, ... |

The tabulation gives groupings no code; component, chapter and block codes are
derived from the categories under them (`b`, `b1`, `b110-b139`), as ICF and UMLS
write them; WHO's own block identifier is kept as `block_id` (`BlockL3-b11`).
Qualifier groups are keyed by their WHO entity number. Properties:

| Property | Description |
| --- | --- |
| `uri` | ICF linearization URI (`http://id.who.int/icd/release/11/icf/1060289548`) |
| `foundation_uri` | WHO-FIC Foundation entity, shared with ICD-11; not on the 507 residual categories, which exist only in ICF |
| `component` | `b`, `s`, `d`, `e`, or `q` for qualifiers (not on `section:category`) |
| `is_residual` | *other specified* (`…8`) or *unspecified* (`…9`) category |
| `is_leaf` | no children |
| `block_id` | WHO's block identifier, on components, chapters and blocks |
| `coding_note` | where WHO gives one (1 category) |

No definitions, inclusions or exclusions (not in the tabulation; ICD API only).

## Relationships

Within a vocabulary, relationships only join two nodes with the same vocabulary
label; between vocabularies there are only `MAPS_TO` edges (see
[Bindings](#bindings-maps_to)). Types are UPPER_SNAKE_CASE, and `ISA` is the
hierarchy (child → parent) in every vocabulary.

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

LOINC Extension edges are keyed and described the same way; they start at extension
nodes (and 72 at International nodes the extension re-classifies), so
`(:SNOMEDCT {extension: 'loinc'})-[:COMPONENT]->(:SNOMEDCT)` reads the component of
a LOINC term.

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

### `ICD10` (WHO)

| Type | From → to | Properties |
| --- | --- | --- |
| `ISA` | code → parent code / block; block → parent block / chapter | |
| `EXCLUDES` | chapter / block / code with an exclusion note → each code, block or chapter it references | `notes` (note texts) |
| `PAIRED_WITH` | dagger code → its asterisk counterpart(s), and asterisk → dagger, as WHO names them in the title (`A17.0` *Tuberculous meningitis* → `G01`) | |

WHO ICD-10 has one kind of exclusion, unlike ICD-10-CM's `EXCLUDES1` / `EXCLUDES2`.

### `RXNORM`

From `RXNREL` (`SAB=RXNORM`, concept level), one direction of each inverse pair,
named after the published relationship attribute. **`active`** is whether both ends
are current concepts (RXNREL has no status of its own); filter on it for the current
drug model.

| Type | From → to | Example |
| --- | --- | --- |
| `ISA` | `SCD` → `SCDF` / `SCDG`, `SBD` → `SBDF` / `SBDG`, ... | metformin hydrochloride 500 MG Oral Tablet → metformin Oral Tablet |
| `HAS_INGREDIENT` | `SCDC` / `SCDF` / `SCDG` → `IN`; `SBD` / `SBDF` → `BN` | → metformin |
| `HAS_PRECISE_INGREDIENT` | `SCDC` / `BN` → `PIN` | |
| `HAS_INGREDIENTS` | `SCD` → `MIN` | |
| `HAS_PART` | `MIN` → `IN` / `PIN` | glipizide / metformin → metformin |
| `HAS_BOSS` | `SCDFP` → `IN` / `PIN` (basis of strength substance) | |
| `FORM_OF` | `PIN` → `IN`, `SCDFP` → `SCDF`, ... | metformin hydrochloride → metformin |
| `CONSISTS_OF` | `SCD` / `SBD` → `SCDC` / `SBDC` | → metformin hydrochloride 500 MG |
| `TRADENAME_OF` | branded → clinical: `BN` → `IN`, `SBD` → `SCD`, ... | Glucophage → metformin |
| `HAS_DOSE_FORM`, `HAS_DOSEFORMGROUP` | drug → `DF`, `DFG` | → Oral Tablet |
| `QUANTIFIED_FORM_OF` | quantified `SCD` / `SBD` → its unquantified drug | |
| `CONTAINS` | `GPCK` / `BPCK` → `SCD` / `SBD` | |
| `REFORMULATED_TO` | `BN` → `BN` | |

### `ATC`

| Type | From → to |
| --- | --- |
| `ISA` | each code → the code of the level above (`A10BA02` → `A10BA` → `A10B` → `A10` → `A`) |

### `ICF`

| Type | From → to |
| --- | --- |
| `ISA` | each node → its parent in the tabulation (`b1100` → `b110` → `block:b110-b139` → `chapter:b1` → `component:b` → `section:category`; `qi0` → its qualifier group → `section:qualifier`) |

## Bindings (`MAPS_TO`)

`clinical-graph bind` writes each map row as a `MAPS_TO` edge from a concept of
one vocabulary to a concept of another; nothing else crosses vocabularies.
Before writing, each target is checked against the target graph: `match` is
`exact`, `normalised` (upper-cased, or the `X` placeholder removed: `M45.X2` →
`M45.2`) or `ancestor` (the code is not in the target release, so the edge goes
to its longest prefix that is: `W19.9` → `W19`; equivalence `wider`) or
`remapped` (a retired RxNorm RXCUI, replaced by the concept it was merged into).
Rows
whose code matches nothing are skipped and logged, as are rows whose source concept
is not in the graph. `bind <source> --replace` first deletes only that source's
edges (by `provenance`).

Common properties: `provenance` (which map), `id` (the map row's id; edge
identity together with `provenance`), `equivalence`, `target_code` (code as the
map publishes it), `match`. UMLS edges also have `source_code` and `source_match`
(both ends come from UMLS's copies of the vocabularies).

| Edges by `provenance` | From → to | Edges |
| --- | --- | --- |
| `SNOMED CT International map to ICD-10 (refset 447562003)` | `SNOMEDCT` → `ICD10` | 179,449 |
| `NLM SNOMED CT map to ICD-10-CM (refset 6011000124106)` | `SNOMEDCT` → `ICD10CM` | 252,218 |
| `SNOMED CT LOINC Extension: LOINC code identifiers` | `LOINC` → `SNOMEDCT` | 46,981 |
| `LOINC part map to SNOMED CT (PartRelatedCodeMapping)` | `LOINC` → `SNOMEDCT` | 6,662 |
| `LOINC part map to RxNorm (PartRelatedCodeMapping)` | `LOINC` → `RXNORM` | 988 |
| `RxNorm: ATC codes of RxNorm concepts (SAB=ATC)` | `RXNORM` → `ATC` | 3,761 |
| `RxNorm: SNOMED CT US atoms of RxNorm concepts (SAB=SNOMEDCT_US)` | `RXNORM` → `SNOMEDCT` | 18,520 |
| `UMLS Metathesaurus (shared CUI)` | all pairs, see below | 38,764 |

The official maps come first; UMLS only adds pairs none of them has. To use only
reviewed maps: `WHERE m.provenance <> 'UMLS Metathesaurus (shared CUI)'`.

### `SNOMEDCT` → `ICD10`

SNOMED CT International map to WHO ICD-10 (refset 447562003), active and
inactive rows (128,221 active, 51,228 inactive; 162 rows, 14 of them active, point
to codes retired before 2019 with no broader code to fall back to). Like the
SNOMED CT edges, filter on `active` for the current map.

| Property | Description |
| --- | --- |
| `active`, `effective_time`, `first_active` | as for SNOMED CT edges |
| `map_group` | one target per group; a concept needing two codes (dagger + asterisk, condition + cause) has groups 1, 2, ... |
| `map_priority` | order of the alternatives within a group; take the first whose rule holds |
| `map_rule` | `TRUE`, `OTHERWISE TRUE`, or a condition: `IFA 248152002 \| Female (finding) \|`, age at onset, or another concept being present |
| `map_advice` | human-readable advice, e.g. `ALWAYS E11.9`, `IF FEMALE CHOOSE ...` |
| `map_category`, `correlation` | SNOMED's classification of the row (`Map source concept is properly classified`, ...) |

This map targets WHO ICD-10, **not** ICD-10-CM; for ICD-10-CM see below.

### `SNOMEDCT` → `ICD10CM`

NLM's SNOMED CT to ICD-10-CM map (refset 6011000124106, source `snomed_icd10cm`),
`provenance` `NLM SNOMED CT map to ICD-10-CM (refset 6011000124106)`: 252,218 edges
(active rows only; rows from concepts newer than the loaded SNOMED CT release or
from the US extension are skipped). Same properties as the ICD-10 map, without
`first_active`; `map_rule` also uses `IFA` conditions on sex and age, and
`map_advice` repeats the choice in words.

A target ending in `?` (`S72.001?`, 58,689 rows) leaves the 7th character
(encounter: initial `A`, subsequent `D`, sequela `S`, ...) to the coder. The edge
goes to the code the 7th character extends (`S72.001`; `M48.40X?` → `M48.40`), with
`match: ancestor`, equivalence `wider` and the published code in `target_code`.
The 7-character codes are its `ISA` children.

There are no `MAPS_TO` edges to `ICD10PCS`: no official map exists.

### `LOINC` → `SNOMEDCT` (LOINC Extension)

LOINC term → the LOINC Extension concept that models it, from the extension's
`sct2_Identifier` (LOINC code identifiers, scheme 30051010000102; source
`loinc_extension`), `provenance` `SNOMED CT LOINC Extension: LOINC code identifiers`:
46,981 edges, one to one, `equivalence: equivalent`, with `active` and
`effective_time`. The target also has the code as `loinc_code`.

### `LOINC` → `SNOMEDCT` (parts)

LOINC's `PartRelatedCodeMapping.csv` (source `loinc`), `provenance`
`LOINC part map to SNOMED CT (PartRelatedCodeMapping)`: 6,662 edges from LOINC
**parts** to SNOMED CT concepts, mostly components (analytes, organisms, substances),
then systems (specimens), methods, properties and challenges. A part can map to
several concepts. LOINC terms have no map of their own: go through their parts
(`(:LOINC {kind: 'term'})-[:COMPONENT]->(p)-[:MAPS_TO]->(:SNOMEDCT)`).

| Property | Description |
| --- | --- |
| `equivalence` | as LOINC publishes it, FHIR ConceptMap codes: `equivalent` (5,818), `narrower` (810; the SNOMED CT concept is narrower than the part), `wider` (31), `relatedto` (3) |
| `part_type` | `COMPONENT`, `SYSTEM`, `DIVISORS`, `METHOD`, `PROPERTY`, `CHALLENGE`, ... |
| `content_origin` | `loinc_snomed` (made jointly with SNOMED International, 4,945) or `loinc` |
| `target_version` | SNOMED CT version the row was made against (20260101) |

The map is made against a newer SNOMED CT release than the one loaded: 62 targets
are inactive in it; follow their `REPLACED_BY` / `SAME_AS` edges.

### `LOINC` → `RXNORM`

Same file, `provenance` `LOINC part map to RxNorm (PartRelatedCodeMapping)`: 988
edges from LOINC parts (drug analytes: `LP16306-0` *Vancomycin* → `rxnorm:11124`) to RxNorm
concepts, nearly all ingredients (`IN`, some `PIN`), `equivalent`; 4 rows name an
RXCUI that RxNorm does not have and are skipped. Same properties as above. With
`LOINC` → `RXNORM` → `ATC` a drug-level test reaches its ATC class.

The mappings to ChEBI, HGNC, NCBI Gene/Taxonomy, RadLex, UNII, PubChem and ClinVar
in the same file are not loaded (those vocabularies are not in the graph).

### `RXNORM` → `ATC`

From RxNorm (`SAB=ATC` atoms of RxNorm concepts; source `rxnorm`), `provenance`
`RxNorm: ATC codes of RxNorm concepts (SAB=ATC)`: 3,761 edges from ingredients
(`IN`; some `PIN`, `MIN` for combination codes) to ATC 5th-level codes,
`equivalence: relatedto` (an ATC code is a substance for a use; an ingredient can
have several). Clinical and branded drugs reach ATC through `HAS_INGREDIENT`; ATC
has no direct link to SNOMED CT or LOINC, only through RxNorm.

### `RXNORM` → `SNOMEDCT`

From RxNorm (`SAB=SNOMEDCT_US` atoms that RxNorm puts in an RxNorm concept;
SNOMED CT US Edition 2026-07-31), `provenance` `RxNorm: SNOMED CT US atoms of
RxNorm concepts (SAB=SNOMEDCT_US)`: 18,520 edges, `equivalent`: ingredients to
substances, clinical drugs to SNOMED CT clinical drugs (`SCD`, `SCDG`: medicinal
product forms, `IN`/`PIN`/`MIN`: substances). 353 SNOMED CT codes are US-only drugs
not in the loaded release and are skipped. The release has 28k more SNOMED CT drug
concepts in concepts without an RxNorm atom; they have no RxNorm counterpart.

### UMLS (shared CUIs)

From the UMLS Metathesaurus 2026AA (`MRCONSO.RRF`, source `umls`), `provenance`
`UMLS Metathesaurus (shared CUI)`: two codes of two loaded vocabularies in the same
UMLS concept (CUI) are synonyms, `equivalent`; `id` and `cui` are the CUI. Only
current atoms (`SUPPRESS=N`) of SNOMEDCT_US, LNC, RXNORM, ATC, ICD10CM, ICD10PCS,
ICD10, ICF and ICF-CY (both `ICF`) are used. Both codes are resolved against the graph (`source_code`,
`source_match`, `target_code`, `match`: `exact` or `normalised`, never a broader
code), and **only pairs that no official map links** are written (once, whatever
the direction): 82k pairs resolve, 43k of them are linked already.

| From → to | New edges | Examples |
| --- | --- | --- |
| `ICD10CM` → `ICD10` | 11,342 | `B71.0` Hymenolepiasis → `B71.0`; `T36.2X1` → `T36.2` |
| `LOINC` → `SNOMEDCT` | 9,004 | parts: *Blood* → Blood; *Calorie intake* → Energy intake |
| `SNOMEDCT` → `ATC` | 6,748 | Ferrous fumarate → `B03AA02` |
| `SNOMEDCT` → `ICD10CM` | 5,051 | Posterior scleritis → `H15.03` |
| `LOINC` → `ATC` | 1,704 | *Phentermine* → `A08AA01` |
| `SNOMEDCT` → `ICD10` | 1,445 | Malignant neoplasm of gum → `C03` |
| `RXNORM` → `SNOMEDCT` | 1,152 | cinoxate → Cinoxate |
| `LOINC` → `RXNORM` | 944 | *Methamphetamine* → methamphetamine |
| `LOINC` → `ICD10CM`, `ICD10`, `ICD10PCS` | 373, 204, 4 | *Fever* → `R50.9` |
| `SNOMEDCT` → `ICD10PCS` | 90 | Fluoroscopy of colon → `BD14ZZZ` |
| `RXNORM` → `ATC` | 8 | |
| `SNOMEDCT` → `ICF` | 354 | Adrenal structure → `s5803` Adrenal gland; Kingdom Animalia → `e2201` Animals |
| `LOINC` → `ICF` | 313 | parts: *Adrenal gland* → `s5803` |
| `ICD10CM` → `ICF`, `ICD10` → `ICF` | 19, 9 | `M54.9` Dorsalgia, unspecified → `b28013` Pain in back |

Edges point from the earlier vocabulary of LOINC, RxNorm, SNOMED CT, ATC,
ICD-10-CM, ICD-10-PCS, ICD-10, ICF, following the official maps. Blocks and chapters
match by their range (`E08-E13`; WHO's `D55-D59.9`), PCS tables by their 3
characters, ICF blocks, chapters and components by their derived code
(`b110-b139`, `b1`, `b`). Not linked: LOINC answers (`LA`, not nodes), UMLS-made codes
(`MTHU...`), PCS axis codes, US-only or newer SNOMED CT concepts, the 1998 WHO
codes UMLS has that the 2019 edition dropped, and the 3 ICF 2008 codes the
2026-01 release no longer has (`b7209`, `s2302`, `s76009`).

UMLS synonymy is looser than the reviewed maps: an *unspecified* code often shares
a CUI with its category (`Q70.9` *Syndactyly, unspecified* → `Q70`), and LOINC parts
naming a condition link to diagnosis codes. ICD-10-PCS barely appears in UMLS
CUIs with other vocabularies (94 edges): there is still no real map for it.
ICF links are mostly body structures (`s`) to anatomy and body functions (`b`) to
findings; activities and participation (`d`) and environmental factors (`e`)
barely share CUIs, and no official map to ICF exists.
After re-binding an official map, run `bind umls --replace` so UMLS fills only
what is still missing.

## Embeddings

`clinical-graph embed build` embeds every current concept with SapBERT
(`cambridgeltl/SapBERT-from-PubMedBERT-fulltext`, `[CLS]` pooling,
L2-normalised, 768-d). Inactive, deprecated and obsolete concepts are left out,
as are the grouping nodes: ICD-10-CM / ICD-10 `chapter` and `block`, ICD-10-PCS
`table`, LOINC `hierarchy`, `group` and `parentgroup`, and ICF `section`,
`component`, `qualifier_group` and `qualifier`. One model is used for every
vocabulary, so scores compare across vocabularies.

Each distinct text of a concept is one vector (case and spacing ignored):

| Vocabulary | Texts |
| --- | --- |
| all | `name`, each of `synonyms` |
| `SNOMEDCT` | + the FSN without its semantic tag |
| `LOINC` terms | + `display_name`, `short_name`, `consumer_name`, and the `related_names` that at most 20 terms share (the rest are words such as *Blood* or *Level*) |
| `LOINC` parts | + `display_name` |
| `ICD10CM` codes | + `index_terms` |

They are saved per source in `data/processed/embeddings/sapbert/<source>/`:
`texts.tsv` (`concept_id`, `origin`, `text`), `vectors.npy` (float16, row-aligned)
and `info.json` (model, release version, counts). A build is skipped when
`info.json` matches the model and the release in `sources.toml`.

`clinical-graph embed load` puts the vector of each concept's **name** on its
node as `embedding`. Synonym vectors stay on disk. It also creates one cosine
vector index per label, with `kind` as a filter property:

| Index | Label |
| --- | --- |
| `concept_embedding_snomedct` | `SNOMEDCT` (International and LOINC Extension) |
| `concept_embedding_loinc` | `LOINC` |
| `concept_embedding_icd10cm`, `concept_embedding_icd10pcs` | `ICD10CM`, `ICD10PCS` |
| `concept_embedding_icd10` | `ICD10` |
| `concept_embedding_rxnorm`, `concept_embedding_atc` | `RXNORM`, `ATC` |
| `concept_embedding_icf` | `ICF` |

With one index per label, a large vocabulary does not push a small one's hits
out of the top k. Community Edition cannot store the `VECTOR` type, so the
property is a float list (`LIST<FLOAT>`) written with
`db.create.setNodeVectorProperty`. `ingest --replace` deletes the nodes and so
their embeddings; run `embed load <source>` again after it. `embed load
--replace` first removes the embeddings of the source's nodes, so concepts
retired since lose theirs.

To find a concept by any of its texts, not only its name, use
`clinical-graph embed search` without `--graph`
(`clinical_graph.embeddings.EmbeddingIndex`), which searches the saved
synonym vectors. It memory-maps the float16 files and scores them in chunks, so
the vectors sit once in the OS page cache, shared by every process, instead of
in a private float32 copy in each (SNOMED CT: 1.2 GB shared vs 2.4 GB per
process).

```cypher
// LOINC terms nearest to a SNOMED CT concept's name (the shared vector space)
MATCH (s:SNOMEDCT {code: '43396009'})          // Hemoglobin A1c measurement
MATCH (t:LOINC)
  SEARCH t IN (VECTOR INDEX concept_embedding_loinc FOR s.embedding
               WHERE t.kind = 'term' LIMIT 10) SCORE AS score
RETURN t.code, t.name, score ORDER BY score DESC;
```

`SEARCH` is Cypher 25, the default language of this database. On a database
that still defaults to Cypher 5, start the query with `CYPHER 25`.

## Example queries

```cypher
// The current ICD-10 code(s) for a SNOMED CT concept, in map order
MATCH (s:SNOMEDCT {code: '44054006'})-[m:MAPS_TO WHERE m.active]->(i:ICD10)
RETURN m.map_group, m.map_priority, m.map_rule, i.code, i.name
ORDER BY m.map_group, m.map_priority;

// The ICD-10-CM codes for a SNOMED CT concept (NLM map), in map order
MATCH (s:SNOMEDCT {code: '10001005'})-[m:MAPS_TO]->(c:ICD10CM)
RETURN m.map_group, m.map_priority, m.map_rule, m.target_code, c.code, c.name
ORDER BY m.map_group, m.map_priority;

// A LOINC term as a SNOMED CT observable, its parents and attributes
MATCH (:LOINC {code: '2345-7'})-[:MAPS_TO]->(o:SNOMEDCT {extension: 'loinc'})
MATCH (o)-[r WHERE r.active]->(t:SNOMEDCT)
RETURN o.name, type(r), t.code, t.name;

// SNOMED CT concepts for the analyte and specimen of a LOINC term
// (2345-7 Glucose [Mass/volume] in Serum or Plasma)
MATCH (:LOINC {code: '2345-7'})-[a:COMPONENT|SYSTEM]->(p:LOINC)-[m:MAPS_TO]->(s:SNOMEDCT)
RETURN type(a), p.code, p.name, m.equivalence, s.code, s.name;

// A drug from an NDC (as in MIMIC prescriptions): its ingredients and their ATC codes
MATCH (d:RXNORM) WHERE '00093104801' IN d.ndc
MATCH (d)-[:CONSISTS_OF]->(:RXNORM)-[:HAS_INGREDIENT]->(i:RXNORM)
OPTIONAL MATCH (i)-[:MAPS_TO]->(a:ATC)-[:ISA*0..]->(c:ATC)
RETURN d.name, i.name, a.code, collect(c.code + ' ' + c.name) AS atc_path;

// Every current RxNorm clinical drug in an ATC class (A10B: blood glucose lowering)
MATCH (:ATC {code: 'A10B'})<-[:ISA*0..]-(:ATC)<-[:MAPS_TO]-(i:RXNORM)
MATCH (d:RXNORM {kind: 'clinical_drug', active: true})-[:CONSISTS_OF]->()-[:HAS_INGREDIENT]->(i)
RETURN DISTINCT d.code, d.name;

// ICF categories for a SNOMED CT concept and its descendants, through UMLS
MATCH (d:SNOMEDCT)(()-[r:ISA WHERE r.active]->())*(:SNOMEDCT {code: '23451007'})
MATCH (d)-[:MAPS_TO]->(f:ICF)
RETURN DISTINCT f.code, f.name;

// The WHO ICD-10 code(s) for an ICD-10-CM code, through UMLS
MATCH (cm:ICD10CM {code: 'B71.0'})-[m:MAPS_TO]-(w:ICD10)
RETURN cm.code, w.code, w.name, m.provenance;

// SNOMED CT concepts an ICD-10 code from an EHR (stored without dot) stands for
MATCH (i:ICD10 {code_no_dot: 'E119'})<-[m:MAPS_TO WHERE m.active AND m.map_rule = 'TRUE']-(s:SNOMEDCT)
WHERE s.active
RETURN s.code, s.name;

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
