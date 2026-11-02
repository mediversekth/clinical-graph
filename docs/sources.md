# Sources

The graph is built from three vocabulary releases. None of them is stored in this
repository: two need a (free) licence, and all are large. This page says what to
download, where to put it, and how to check you have the same files.

`sources.toml` is the machine-readable version of this page: it lists every file the
code reads. `sources.lock.json` holds the size and SHA-256 of each of those files as
used for the current build.

| Key | Release | Version | Licence | Size unpacked |
| --- | --- | --- | --- | --- |
| `snomed` | SNOMED CT International Edition, RF2 | 2025-09-01 | SNOMED CT Affiliate Licence | ~1.2 GB (Snapshot ~0.7 GB) |
| `loinc` | LOINC | 2.83 | LOINC licence | ~1.0 GB |
| `icd10cm` | ICD-10-CM + ICD-10-PCS (CMS, US) | FY2027 | Public domain | ~150 MB |

## Directory layout

Releases are unpacked under `data/raw/` as they come out of the archive. To keep the
data somewhere else, set `CLINICAL_GRAPH_DATA_DIR` (the code then reads
`$CLINICAL_GRAPH_DATA_DIR/raw/...`).

```text
data/raw/
├── snomed/
│   └── SnomedCT_InternationalRF2_PRODUCTION_20250901T120000Z/   # unzipped as-is
│       ├── Snapshot/{Terminology,Refset}/
│       └── Full/                                               # not used
├── loinc/
│   └── Loinc_2.83/                                             # unzipped Loinc_2.83.zip
│       ├── LoincTable/
│       └── AccessoryFiles/
└── icd10cm/
    └── 2027/                                                   # one folder per CMS zip
        ├── 2027-code-descriptions-tabular-order/
        ├── 2027-code-tables-tabular-index/
        └── 2027-icd-10-pcs-order-file-long-abbreviated-titles/
```

After downloading:

```bash
uv run clinical-graph sources list     # where each release goes
uv run clinical-graph sources verify   # all required files present, checksums match the lock
```

`verify` exits non-zero and reports if a required file is missing or differs from
`sources.lock.json`. After switching to a new release (see
[Updating a release](#updating-a-release)), run `uv run clinical-graph sources lock`
and commit the new lock file.

---

## SNOMED CT International Edition

- **Publisher:** SNOMED International
- **Release:** `SnomedCT_InternationalRF2_PRODUCTION_20250901T120000Z.zip`
  (effective time 20250901)
- **Licence:** SNOMED CT Affiliate Licence. Free in member countries (Sweden and the
  US are members). The licence does not allow redistributing the files.
- **Download:** [Member Licensing and Distribution Service (MLDS)](https://mlds.ihtsdotools.org/).
  Create an account, apply for an affiliate licence for your country, then download
  the *International Edition* release package. In the US, the same package is also
  available through the [NLM UMLS Terminology Services](https://uts.nlm.nih.gov/).
- **Unpack to:** `data/raw/snomed/` (the zip contains the top-level folder).

Files used (all in `Snapshot/`; the `Full/` history is not needed):

| File | Used for |
| --- | --- |
| `Terminology/sct2_Concept_Snapshot_INT_20250901.txt` | concepts, active flag |
| `Terminology/sct2_Description_Snapshot-en_INT_20250901.txt` | FSNs and synonyms |
| `Refset/Language/der2_cRefset_LanguageSnapshot-en_INT_20250901.txt` | preferred terms (US/GB) |
| `Terminology/sct2_Relationship_Snapshot_INT_20250901.txt` | inferred `ISA` hierarchy and attributes |
| `Terminology/sct2_RelationshipConcreteValues_Snapshot_INT_20250901.txt` | concrete-valued attributes (optional) |
| `Terminology/sct2_TextDefinition_Snapshot-en_INT_20250901.txt` | text definitions (optional) |
| `Refset/Content/der2_cRefset_AssociationSnapshot_INT_20250901.txt` | `REPLACEDBY`, `SAMEAS`, … for inactive concepts |
| `Refset/Content/der2_cRefset_AttributeValueSnapshot_INT_20250901.txt` | inactivation reasons (optional) |
| `Refset/Map/der2_iisssccRefset_ExtendedMapSnapshot_INT_20250901.txt` | **binding** SNOMED CT → WHO ICD-10 |
| `Refset/Map/der2_sRefset_SimpleMapSnapshot_INT_20250901.txt` | **binding** SNOMED CT → ICD-O-3, CTV3 (optional) |

## LOINC

- **Publisher:** Regenstrief Institute
- **Release:** `Loinc_2.83.zip` (the complete download, not "LOINC Table Core" only)
- **Licence:** [LOINC licence](https://loinc.org/license/). Free; needs a loinc.org
  account. Redistribution is allowed under the licence's terms, but this repository
  doesn't redistribute the files.
- **Download:** [loinc.org/downloads](https://loinc.org/downloads/). Sign in, then
  download *LOINC* (complete). Older versions are under *Archive*.
- **Unpack to:** `data/raw/loinc/Loinc_2.83/` (the zip has no top-level folder, so
  create it first: `unzip Loinc_2.83.zip -d data/raw/loinc/Loinc_2.83`).

Files used:

| File | Used for |
| --- | --- |
| `LoincTable/Loinc.csv` | LOINC terms, six axes, names, status |
| `LoincTable/MapTo.csv` | deprecated term → replacement |
| `AccessoryFiles/PartFile/Part.csv` | parts (LP codes) |
| `AccessoryFiles/PartFile/LoincPartLink_Primary.csv` | term → part on the six axes |
| `AccessoryFiles/PartFile/LoincPartLink_Supplementary.csv` | term → part, other links |
| `AccessoryFiles/PartFile/PartRelatedCodeMapping.csv` | **binding** parts → SNOMED CT, RxNorm, ChEBI, … |
| `AccessoryFiles/ComponentHierarchyBySystem/ComponentHierarchyBySystem.csv` | component hierarchy |
| `AccessoryFiles/GroupFile/{Group,GroupLoincTerms,ParentGroup}.csv` | groups (optional) |
| `AccessoryFiles/PanelsAndForms/PanelsAndForms.csv` | panel membership (optional) |
| `AccessoryFiles/AnswerFile/{AnswerList,LoincAnswerListLink}.csv` | answer lists (optional) |

## ICD-10-CM and ICD-10-PCS (US)

- **Publisher:** CMS and CDC NCHS
- **Release:** FY2027 (valid 2026-10-01 to 2027-09-30)
- **Licence:** public domain
- **Download:** [cms.gov ICD-10 codes](https://www.cms.gov/medicare/coding-billing/icd-10-codes)
  — three zips:

  ```bash
  mkdir -p data/raw/icd10cm/2027 && cd data/raw/icd10cm/2027
  for f in 2027-code-descriptions-tabular-order \
           2027-code-tables-tabular-index \
           2027-icd-10-pcs-order-file-long-abbreviated-titles; do
    curl -fLO "https://www.cms.gov/files/zip/$f.zip" && unzip -q "$f.zip" -d "$f"
  done
  ```

Files used:

| File | Used for |
| --- | --- |
| `2027-code-tables-tabular-index/Table and Index/icd10cm_tabular_2027.xml` | chapters, blocks, codes, tabular notes |
| `2027-code-descriptions-tabular-order/Code Descriptions/icd10cm_order_2027.txt` | all codes + headers with titles |
| `2027-code-descriptions-tabular-order/Code Descriptions/icd10cm_codes_2027.txt` | billable codes (optional) |
| `2027-code-tables-tabular-index/Table and Index/icd10cm_index_2027.xml` | alphabetic index (optional) |
| `2027-icd-10-pcs-order-file-long-abbreviated-titles/icd10pcs_order_2027.txt` | ICD-10-PCS codes + table headers |

This is the **US clinical modification**, not WHO ICD-10. The two share most
three-character categories, but ICD-10-CM adds many more specific codes and some
categories differ.

---

## Bindings

What links one vocabulary to another, and where it comes from:

| From → to | Source | In the downloads above? |
| --- | --- | --- |
| SNOMED CT → WHO ICD-10 (2016) | SNOMED refset 447562003, `ExtendedMap` | yes |
| SNOMED CT → ICD-O-3 | SNOMED refset 446608001, `SimpleMap` | yes |
| LOINC part → SNOMED CT | `PartRelatedCodeMapping.csv` | yes |
| LOINC part → RxNorm, ChEBI, HGNC, NCBI Gene/Taxonomy, RadLex, UNII, PubChem | `PartRelatedCodeMapping.csv` | yes (targets are codes only; those vocabularies aren't loaded) |
| SNOMED CT → **ICD-10-CM** | NLM map, refset 6011000124106 | **no** — see below |
| LOINC term ↔ SNOMED CT concept | LOINC Ontology | **no** — see below |

So with the current downloads there is **no direct SNOMED CT → ICD-10-CM binding**:
the SNOMED International map targets WHO ICD-10. Matching those targets to ICD-10-CM
codes by string works for many but not all codes; the proper source is NLM's map.

### Not yet included (candidates)

- **SNOMED CT to ICD-10-CM map** (NLM). Part of the SNOMED CT *US Edition*: file
  `Snapshot/Refset/Map/der2_iisssccRefset_ExtendedMapSnapshot_US1000124_<date>.txt`,
  refset 6011000124106, updated each March and September. Needs a free
  [UMLS licence](https://uts.nlm.nih.gov/) (UTS account). See
  [the NLM page](https://www.nlm.nih.gov/research/umls/mapping_projects/snomedct_to_icd10cm.html).
- **LOINC Ontology** (SNOMED International and Regenstrief): LOINC terms modelled as
  SNOMED CT concepts. Distributed through MLDS as a SNOMED extension.

Add a new source by adding a `[sources.<key>]` table to `sources.toml`, a section
here, and a reader in `src/clinical_graph/vocabularies/`.

## Updating a release

1. Download and unpack the new release next to the old one (new `release_dir`).
2. Update `version`, `archive`, `release_dir` and the dated file names in
   `sources.toml`, and the matching section of this page.
3. `uv run clinical-graph sources verify --no-checksums`, then
   `uv run clinical-graph sources lock`, and commit `sources.toml`,
   `sources.lock.json` and this page together.
