# Sources

The graph is built from seven vocabulary releases (RxNorm also brings ATC), one
SNOMED CT extension, three map releases and the UMLS Metathesaurus (links only). None of them is stored in this
repository: two need a (free) licence, and all are large. This page says what to
download, where to put it, and how to check you have the same files.

`sources.toml` is the machine-readable version of this page: it lists every file the
code reads. `sources.lock.json` holds the size and SHA-256 of each of those files as
used for the current build.

| Key | Release | Version | Licence | Size unpacked |
| --- | --- | --- | --- | --- |
| `snomed` | SNOMED CT International Edition, RF2 | 2025-09-01 | SNOMED CT Affiliate Licence | ~1.2 GB (Snapshot ~0.7 GB) |
| `loinc_extension` | SNOMED CT LOINC Extension (LOINC Ontology), RF2 | 2026-10-21 | SNOMED CT + LOINC licences | ~330 MB |
| `loinc` | LOINC | 2.83 | LOINC licence | ~1.0 GB |
| `icd10cm` | ICD-10-CM + ICD-10-PCS (CMS, US) | FY2027 | Public domain | ~150 MB |
| `icd10` | ICD-10 (WHO), ClaML | 2019 | WHO terms of use | ~10 MB |
| `icf` | ICF (WHO), simple tabulation | 2026-01 | CC BY-ND 3.0 IGO | ~0.5 MB |
| `rxnorm` | RxNorm Full Monthly Release (with ATC) | 2026-11-02 | UMLS licence (+ SNOMED CT for its SNOMED atoms) | ~1.3 GB |
| `umls` | UMLS Metathesaurus, `MRCONSO.RRF` only | 2026AA | UMLS licence | ~2.3 GB (`MRCONSO`) |
| `snomed_icd10cm` | SNOMED CT to ICD-10-CM Map (NLM), human-readable | 2026-09-01 | UMLS + SNOMED CT licence | ~110 MB |
| `icd9cm` | ICD-9-CM Version 32 (CMS), code titles | FY2015 (final) | Public domain | ~1.3 MB |
| `icd9cm_snomed` | ICD-9-CM to SNOMED CT Maps (NLM), diagnoses + procedures | 2025-12 | UMLS + SNOMED CT licence | ~7.5 MB |
| `icd9cm_gems` | General Equivalence Mappings ICD-9-CM ↔ ICD-10-CM/PCS (CMS) | 2018 (final) | Public domain | ~13 MB |

## Directory layout

Releases are unpacked under `data/raw/` as they come out of the archive. To keep the
data somewhere else, set `CLINICAL_GRAPH_DATA_DIR` (the code then reads
`$CLINICAL_GRAPH_DATA_DIR/raw/...`).

```text
data/raw/
├── snomed/
│   └── SnomedCT_InternationalRF2_PRODUCTION_20250901T120000Z/   # unzipped as-is
│       ├── Snapshot/{Terminology,Refset}/
│       └── Full/                                               # history dates only
├── loinc/
│   └── Loinc_2.83/                                             # unzipped Loinc_2.83.zip
│       ├── LoincTable/
│       └── AccessoryFiles/
├── icd10cm/
│   └── 2027/                                                   # one folder per CMS zip
│       ├── 2027-code-descriptions-tabular-order/
│       ├── 2027-code-tables-tabular-index/
│       └── 2027-icd-10-pcs-order-file-long-abbreviated-titles/
├── icd10/
│   └── 2019/                                                   # unzipped icd102019en.xml.zip
│       └── icd102019en.xml
├── icf/
│   └── 2026-01/                                                # unzipped SimpleTabulation-ICF-en.zip
│       └── SimpleTabulation-ICF-en.txt
├── umls/
│   └── 2026AA/META/MRCONSO.RRF                                 # assembled, see UMLS below
├── RxNorm_full_11022026/                                     # unzipped RxNorm_full_11022026.zip
│   └── rrf/
├── SnomedCT_LOINCExtension_PRODUCTION_LO1010000_20261021T120000Z/  # unzipped as-is
│   ├── Snapshot/{Terminology,Refset}/
│   └── Full/
├── SNOMED_CT_to_ICD-10-CM_Resources_20260901/                   # unzipped as-is
│   └── tls_Icd10cmHumanReadableMap_US1000124_20260901.tsv
└── icd9/                                                       # icd9cm, icd9cm_snomed, icd9cm_gems
    ├── ICD-9-CM-v32-master-descriptions/                       # one folder per zip, named after it
    ├── ICD9CM_SNOMED_MAP_diagnosis_202512/
    ├── ICD9CMV3_SNOMED_MAP_Procedure_202512/
    ├── diagnosis_gems_2018/                                    # 2018_I9gem.txt, 2018_I10gem.txt
    └── pcs_gems_2018/                                          # gem_i9pcs.txt, gem_pcsi9.txt
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

Files used. The Snapshot has every component in its latest state, inactive ones
included; the `Full/` files only add when each one was first active (optional):

| File | Used for |
| --- | --- |
| `Terminology/sct2_Concept_Snapshot_INT_20250901.txt` | concepts, active flag |
| `Terminology/sct2_Description_Snapshot-en_INT_20250901.txt` | FSNs and synonyms |
| `Refset/Language/der2_cRefset_LanguageSnapshot-en_INT_20250901.txt` | preferred terms (US/GB) |
| `Terminology/sct2_Relationship_Snapshot_INT_20250901.txt` | inferred `ISA` hierarchy and attributes |
| `Terminology/sct2_RelationshipConcreteValues_Snapshot_INT_20250901.txt` | concrete-valued attributes (optional) |
| `Terminology/sct2_TextDefinition_Snapshot-en_INT_20250901.txt` | text definitions (optional) |
| `Refset/Content/der2_cRefset_AssociationSnapshot_INT_20250901.txt` | `REPLACED_BY`, `SAME_AS`, … for inactive concepts |
| `Refset/Content/der2_cRefset_AttributeValueSnapshot_INT_20250901.txt` | inactivation reasons (optional) |
| `Full/Terminology/sct2_Concept_Full_INT_20250901.txt` | `first_active` of concepts (optional) |
| `Full/Terminology/sct2_Relationship_Full_INT_20250901.txt` | `first_active` of relationships (optional) |
| `Full/Refset/Content/der2_cRefset_AssociationFull_INT_20250901.txt` | `first_active` of associations (optional) |
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
| `AccessoryFiles/ConsumerName/ConsumerName.csv` | consumer names of the terms (optional) |
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
| `2027-code-tables-tabular-index/Table and Index/icd10cm_index_2027.xml` | alphabetic index: index terms of the codes (optional) |
| `2027-icd-10-pcs-order-file-long-abbreviated-titles/icd10pcs_order_2027.txt` | ICD-10-PCS codes + table headers |

This is the **US clinical modification**, not WHO ICD-10. The two share most
three-character categories, but ICD-10-CM adds many more specific codes and some
categories differ.

## ICD-10 (WHO)

- **Publisher:** World Health Organization
- **Release:** ICD-10 2019 edition (with the 2020 COVID-19 codes), ClaML (XML)
- **Licence:** WHO's ICD-10 terms of use; the download needs no account. Don't
  redistribute the files.
- **Download:** [icdcdn.who.int/icd10](https://icdcdn.who.int/icd10/index.html):

  ```bash
  mkdir -p data/raw/icd10/2019 && cd data/raw/icd10/2019
  curl -fLO https://icdcdn.who.int/icd10/claml/icd102019en.xml.zip && unzip -q icd102019en.xml.zip
  ```

Files used:

| File | Used for |
| --- | --- |
| `icd102019en.xml` | chapters, blocks, categories, modifiers (4th/5th-character subdivisions), inclusion and exclusion notes |

Use the ClaML file, not the plain-text edition (`icd102019syst_*.txt`): the text
files leave out the optional 5th-character subdivisions (site codes in chapter
XIII, closed / open fractures), which 8% of the SNOMED CT map rows target. The
reader reproduces every code and title of the text edition.

The SNOMED CT map targets the 2016 edition; codes deleted by 2019 fall back to
their broader code (see `docs/graph_schema.md`, *Bindings*).

## ICF (WHO)

- **Publisher:** World Health Organization
- **Release:** ICF, 2026-01 release of the WHO ICD-11 platform (ICF is updated
  with it; the release id is in the download URL). WHO no longer publishes ICF
  as ClaML: the *simple tabulation* is the only file download.
- **Licence:** WHO: "the same rules apply for ICF as for ICD", i.e. ICD-11's
  CC BY-ND 3.0 IGO. No account needed.
- **Download:** the [ICF browser](https://icd.who.int/browse/latest-release/icf/en),
  *Info* menu, *Spreadsheet File*:

  ```bash
  mkdir -p data/raw/icf/2026-01 && cd data/raw/icf/2026-01
  curl -fLO https://icdcdn.who.int/static/releasefiles/2026-01/SimpleTabulation-ICF-en.zip
  unzip -q SimpleTabulation-ICF-en.zip
  ```

Files used:

| File | Used for |
| --- | --- |
| `SimpleTabulation-ICF-en.txt` | sections, components, chapters, blocks, categories and qualifiers, with their parents and Foundation / linearization URIs |

Not read: `SimpleTabulation-ICF-en.xlsx` (the same table) and `readme.txt`. The
tabulation has no definitions, inclusions or exclusions; those are only in the
[ICD API](https://icd.who.int/docs/icd-api/APIDoc-Version2/) (linearization
`icf`, free registration). ICF publishes no maps to other vocabularies; it is
linked through UMLS (`ICF` and `ICF-CY` 2008 in UMLS 2026AA).

## SNOMED CT LOINC Extension (LOINC Ontology)

**What it is.** A SNOMED CT release, not a LOINC one: SNOMED International and
Regenstrief model LOINC terms as *new SNOMED CT concepts* (observable entities, e.g.
`57121010000107` for LOINC `2345-7` Glucose [Mass/volume] in Serum or Plasma), in
their own module (11010000107) and namespace (`…1010000…`). The International Edition
has the building blocks (substances, specimens, properties, generic observables) but
no concept per LOINC test, so these concepts are not in the `snomed` source (33 of
48,031 are). Each extension concept carries its LOINC code, which is the LOINC term →
SNOMED CT binding; the `loinc` source stays the LOINC side. After loading, one test is
two linked nodes: `(:LOINC {code:'2345-7'})-[:MAPS_TO]->(:SNOMEDCT {extension:'loinc'})`,
the SNOMED CT one placed in the SNOMED CT hierarchy (`ISA`) with `COMPONENT`,
`DIRECT_SITE`, ... edges to International concepts.

- **Publisher:** SNOMED International and Regenstrief Institute
  ([loincsnomed.org](https://loincsnomed.org/))
- **Release:** `SnomedCT_LOINCExtension_PRODUCTION_LO1010000_20261021T120000Z.zip`
  (effective time 20261021), built on SNOMED CT International 20260701 and
  LOINC 2.83.
- **Licence:** SNOMED CT Affiliate Licence and the LOINC licence. Don't redistribute.
- **Download:** [MLDS](https://mlds.ihtsdotools.org/), with the same account and
  affiliate licence as the International Edition: under SNOMED International's
  release packages, the *LOINC Extension* package
  (`SnomedCT_LOINCExtension_PRODUCTION_LO1010000_<date>T120000Z.zip`). Project site,
  browser and documentation: [loincsnomed.org](https://loincsnomed.org/).
- **Unpack to:** `data/raw/` (the zip contains the top-level folder).
- **Load:** after `snomed` and `loinc`:

  ```bash
  uv run clinical-graph ingest loinc_extension   # its SNOMEDCT nodes and edges
  uv run clinical-graph bind loinc_extension     # LOINC term -> SNOMEDCT MAPS_TO
  ```

Files used (same RF2 layout as the International Edition, `_LO1010000_` names):

| File | Used for |
| --- | --- |
| `Snapshot/Terminology/sct2_Concept_Snapshot_LO1010000_20261021.txt` | concepts |
| `Snapshot/Terminology/sct2_Description_Snapshot-en_LO1010000_20261021.txt` | FSNs and synonyms |
| `Snapshot/Refset/Language/der2_cRefset_LanguageSnapshot-en_LO1010000_20261021.txt` | preferred terms (US English) |
| `Snapshot/Terminology/sct2_Relationship_Snapshot_LO1010000_20261021.txt` | inferred `ISA` and observable attributes |
| `Snapshot/Terminology/sct2_Identifier_Snapshot_LO1010000_20261021.txt` | **binding** LOINC code of each concept |
| `Snapshot/Refset/Content/der2_cRefset_AssociationSnapshot_LO1010000_20261021.txt` | historical associations |
| `Snapshot/Terminology/sct2_TextDefinition_Snapshot-en_LO1010000_20261021.txt`, `Snapshot/Refset/Content/der2_cRefset_AttributeValueSnapshot_LO1010000_20261021.txt`, `Full/...` (concept, relationship, association) | text definitions, inactivation reasons, first-active dates (optional) |

Not read: the OWL expressions (the inferred relationships carry the same
content), the LOINC Observation / Orderable simple refsets (LOINC's own `order_obs`
says the same) and the *Discouraged* annotations (LOINC's `status`).

The extension depends on a newer International release (20260701) than the one
loaded; see `docs/graph_schema.md` (*LOINC Extension*) for what that leaves out.

## SNOMED CT to ICD-10-CM Map (NLM)

- **Publisher:** U.S. National Library of Medicine
- **Release:** `SNOMED_CT_to_ICD-10-CM_Resources_20260901.zip`, the map that comes
  with the SNOMED CT US Edition 20260901 (refset 6011000124106). NLM releases it
  each March and September.
- **Licence:** UMLS Metathesaurus Licence (free, UTS account) plus a SNOMED CT
  affiliate licence (Sweden and the US are members). Don't redistribute it.
- **Download:** sign in to [UTS](https://uts.nlm.nih.gov/) (create an account and
  accept the UMLS licence first), then on
  [NLM's SNOMED CT files page](https://www.nlm.nih.gov/research/umls/licensedcontent/snomedctfiles.html)
  download *SNOMED CT to ICD-10-CM Map* (`SNOMED_CT_to_ICD-10-CM_Resources_<date>.zip`).
  It is a separate download from the US Edition, which is not needed. About the map:
  [NLM map page](https://www.nlm.nih.gov/research/umls/mapping_projects/snomedct_to_icd10cm.html).
- **Unpack to:** `data/raw/` (the zip contains the top-level folder).
- **Load:** `uv run clinical-graph bind snomed_icd10cm` (after `snomed` and `icd10cm`).

Files used:

| File | Used for |
| --- | --- |
| `tls_Icd10cmHumanReadableMap_US1000124_20260901.tsv` | **binding** SNOMED CT → ICD-10-CM: the RF2 map columns plus source and target names, active rows only |

The graph keeps the SNOMED CT *International* Edition, not the US Edition, so only
the map is used. Rows starting from a concept that is not in the loaded release are
skipped: with International 20250901, 13,704 of 266k rows (11,091 newer
International concepts, 2,613 US-extension concepts). A newer International release
recovers most of the first group.

## ICD-9-CM (US)

- **Publisher:** CMS / CDC NCHS
- **Release:** *ICD-9-CM Diagnosis and Procedure Codes: Abbreviated and Full Code
  Titles*, Version 32, effective 2014-10-01 (FY2015). The last one: ICD-9-CM was
  frozen in 2012 and replaced by ICD-10-CM/PCS on 2015-10-01.
- **Licence:** public domain.
- **Download:** [CMS](https://www.cms.gov/medicare/coding-billing/icd-10-codes/icd-9-cm-diagnosis-procedure-codes-abbreviated-and-full-code-titles),
  *Version 32 Full and Abbreviated Code Titles – Effective October 1, 2014 (ZIP)*:

  ```bash
  mkdir -p data/raw/icd9 && cd data/raw/icd9
  unzip -q ICD-9-CM-v32-master-descriptions.zip -d ICD-9-CM-v32-master-descriptions
  ```

Files used:

| File | Used for |
| --- | --- |
| `CMS32_DESC_LONG_DX.txt` | billable diagnosis codes (volumes 1-2), full titles; Latin-1 |
| `CMS32_DESC_SHORT_DX.txt` | billable diagnosis codes, abbreviated titles |
| `CMS32_DESC_LONG_SG.txt` | billable procedure codes (volume 3), full titles |
| `CMS32_DESC_SHORT_SG.txt` | billable procedure codes, abbreviated titles |

Not read: the two `.xlsx` files (the same content). The CMS files list billable
codes only, no headers (`250`, `250.0`) or chapters. Those come from the UMLS
release (`umls`, `META/MRCONSO.RRF`, `SAB=ICD9CM`, `TTY=HT`: 3,957 headers and
ranges with names); without it ICD-9-CM loads as a flat list. The NCHS tabular
(RTF) is not needed.

## ICD-9-CM to SNOMED CT Maps (NLM)

- **Publisher:** U.S. National Library of Medicine
- **Release:** December 2025 (`202512`), on the SNOMED CT US Edition 2025-09. NLM
  updates it each December. Two zips: *ICD-9-CM Diagnostic Codes to SNOMED CT Map*
  and *ICD-9-CM Procedure Codes to SNOMED CT Map*.
- **Licence:** UMLS Metathesaurus Licence (free, UTS account) plus a SNOMED CT
  affiliate licence. Don't redistribute it.
- **Download:** [NLM map page](https://www.nlm.nih.gov/research/umls/mapping_projects/icd9cm_to_snomedct.html)
  (UTS login). Without a browser, with the UTS API key:

  ```bash
  cd data/raw/icd9
  for f in ICD9CM_SNOMED_MAP_diagnosis_202512 ICD9CMV3_SNOMED_MAP_Procedure_202512; do
    curl -fL -o $f.zip "https://uts-ws.nlm.nih.gov/download?url=https://download.nlm.nih.gov/umls/kss/mappings/ICD9CM_TO_SNOMEDCT/$f.zip&apiKey=$UMLS_API_KEY"
    unzip -q $f.zip -d $f
  done
  ```

- **Load:** `uv run clinical-graph bind icd9cm_snomed` (after `icd9cm` and `snomed`).

Files used:

| File | Used for |
| --- | --- |
| `ICD9CM_SNOMED_MAP_diagnosis_202512/ICD9CM_SNOMED_MAP_1TO1_202512.txt` | **binding** diagnosis → one SNOMED CT concept |
| `ICD9CM_SNOMED_MAP_diagnosis_202512/ICD9CM_SNOMED_MAP_1TOM_202512.txt` | **binding** diagnosis → several narrower SNOMED CT concepts |
| `ICD9CMV3_SNOMED_MAP_Procedure_202512/ICD9CMV3_SNOMED_MAP_1T1_202512.txt` | **binding** procedure → one SNOMED CT concept |
| `ICD9CMV3_SNOMED_MAP_Procedure_202512/ICD9CMV3_SNOMED_MAP_1TM_202512.txt` | **binding** procedure → several narrower SNOMED CT concepts |

The maps target the US Edition: 16 target concepts are US-only and are skipped.

## ICD-9-CM General Equivalence Mappings (CMS)

- **Publisher:** CMS
- **Release:** the 2018 GEMs, the last edition (CMS stopped them after FY2018).
  Their ICD-10 codes are FY2018 codes; `bind` resolves them against the loaded
  ICD-10-CM/PCS release, a retired ICD-10-CM code falling back to its parent.
- **Licence:** public domain.
- **Download:** [CMS ICD-10 codes](https://www.cms.gov/medicare/coding-billing/icd-10-codes),
  the *2018 ICD-10-CM and GEMs* page (*2018 Diagnosis GEMs*) and the *2018
  ICD-10-PCS and GEMs* page (*2018 ICD-10-PCS General Equivalence Mappings*,
  `2018icd10pcsgeneralequivalencemappings.zip`). Unpack to
  `data/raw/icd9/diagnosis_gems_2018/` and `data/raw/icd9/pcs_gems_2018/`.
- **Load:** `uv run clinical-graph bind icd9cm_gems` (after `icd9cm` and `icd10cm`).

Files used:

| File | Used for |
| --- | --- |
| `diagnosis_gems_2018/2018_I9gem.txt` | **binding** ICD-9-CM → ICD-10-CM (forward) |
| `diagnosis_gems_2018/2018_I10gem.txt` | **binding** ICD-10-CM → ICD-9-CM (backward) |
| `pcs_gems_2018/gem_i9pcs.txt` | **binding** ICD-9-CM → ICD-10-PCS (forward) |
| `pcs_gems_2018/gem_pcsi9.txt` | **binding** ICD-10-PCS → ICD-9-CM (backward) |

Not read: the PDF guides. Backward rows from an ICD-10 code deleted since 2018 are
skipped (9,840), as are forward rows to a deleted ICD-10-PCS code (1,029).

## RxNorm (with ATC)

- **Publisher:** U.S. National Library of Medicine
- **Release:** `RxNorm_full_11022026.zip`, the Full Monthly Release of 2026-11-02
  (RxNorm `20AA_261102F`). NLM publishes one each month (first Monday) and weekly
  updates in between; use the full release.
- **Licence:** UMLS Metathesaurus Licence (free, UTS account). RxNorm's own content
  and ATC are restriction level 0 (free use); the SNOMED CT atoms inside are level 9
  and need a SNOMED CT affiliate licence, which a member country (Sweden, the US)
  gives for free. Don't redistribute it.
- **Download:** sign in to [UTS](https://uts.nlm.nih.gov/), then on
  [NLM RxNorm files](https://www.nlm.nih.gov/research/umls/rxnorm/docs/rxnormfiles.html)
  download the **RxNorm Full Monthly Release** (`RxNorm_full_<MMDDYYYY>.zip`). Not
  *Prescribable Content* (no other sources, so no ATC) and not the weekly updates.
- **Unpack to:** `data/raw/` (the zip contains the `RxNorm_full_<MMDDYYYY>` folder).
- **Load:** `uv run clinical-graph ingest rxnorm`, then
  `uv run clinical-graph bind rxnorm loinc` (RxNorm → ATC, SNOMED CT; LOINC → RxNorm).

Files used (pipe-delimited RRF):

| File | Used for |
| --- | --- |
| `rrf/RXNCONSO.RRF` | RxNorm concepts and names (`SAB=RXNORM`); ATC codes and titles (`SAB=ATC`); **bindings** to ATC and to SNOMED CT (`SAB=SNOMEDCT_US`) |
| `rrf/RXNREL.RRF` | RxNorm relationships (`isa`, `has_ingredient`, `tradename_of`, ...) |
| `rrf/RXNSAT.RRF` | NDC codes, strengths |
| `rrf/RXNCUI.RRF` | retired RXCUIs and their successors (optional) |

**ATC** comes with RxNorm: the release includes the WHO ATC classification (ATC
2026-01-28, all five levels) as one of its sources, so no separate download is
needed. WHO's own ATC/DDD index (with the defined daily doses) is sold by the
[WHO Collaborating Centre](https://atcddd.fhi.no/); the codes can be browsed there
for free.

Not read: the other drug sources in the release (Multum, Micromedex, First
Databank, Gold Standard, VANDF, DrugBank, CVX, FDA SPL, USP), `RXNATOMARCHIVE`
(retired atoms) and the AUI-level relationships.

## UMLS Metathesaurus

- **Publisher:** U.S. National Library of Medicine
- **Release:** 2026AA (May 2026). NLM releases in May (AA) and November (AB).
- **Licence:** UMLS Metathesaurus Licence (free, UTS account). Each source keeps
  its own restriction level (licence Appendix 2): here SNOMEDCT_US 9 (SNOMED CT
  affiliate licence), ICD10 3, ICD10CM, ICF and ICF-CY 4 (WHO-derived), LNC,
  RXNORM, ATC, ICD10PCS, ICD9CM 0. Only codes and CUIs are used, plus the names of
  the ICD-9-CM headers, which CMS does not publish; the other codes and names come
  from the releases above. Don't redistribute.
- **Download:** sign in to [UTS](https://uts.nlm.nih.gov/), then on
  [UMLS Knowledge Sources](https://www.nlm.nih.gov/research/umls/licensedcontent/umlsknowledgesources.html)
  take either
  - **UMLS Metathesaurus Full Subset** (`umls-<release>-metathesaurus-full.zip`):
    unzip it and move its `<release>/META` folder to `data/raw/umls/<release>/META`;
    or
  - the **full release** (`umls-<release>-full.zip`, ~5.7 GB, what this build used).
    Its Metathesaurus is in nested archives; assemble `MRCONSO.RRF` without
    MetamorphoSys:

    ```bash
    cd data/raw && mkdir -p umls && cd umls
    unzip ../umls-2026AA-full.zip '2026AA-full/2026aa-*-meta.nlm'
    for f in 2026AA-full/*-meta.nlm; do unzip -o "$f" '2026AA/META/MRCONSO.RRF.*' '2026AA/META/MRSAB.RRF.gz'; done
    cd 2026AA/META && cat $(ls MRCONSO.RRF.*.gz | sort) | gunzip > MRCONSO.RRF && rm MRCONSO.RRF.*.gz
    wc -l MRCONSO.RRF    # 18,064,970 rows; must match MRFILES.RRF
    rm ../../2026AA-full/*-meta.nlm   # the zip stays the original
    ```
- **Load:** after all other `bind`s: `uv run clinical-graph bind umls`.

Files used:

| File | Used for |
| --- | --- |
| `META/MRCONSO.RRF` | **binding** codes of ICD9CM, SNOMEDCT_US, LNC, RXNORM, ATC, ICD10CM, ICD10PCS, ICD10, ICF, ICF-CY that share a CUI; the ICD-9-CM headers (`SAB=ICD9CM`, `TTY=HT`) for `icd9cm` |

UMLS 2026AA carries its own versions: SNOMED CT US 2026-03-01, LOINC 2.82, RxNorm
2026-03-02, ATC 2026-01-28, ICD-10-CM and ICD-10-PCS 2026, ICF and ICF-CY **2008**,
and WHO ICD-10 **1998**.
Codes are resolved against the releases loaded here; those that are not in them
are skipped.

---

## Bindings

What links one vocabulary to another, and where it comes from:

| From → to | Source | In the downloads above? |
| --- | --- | --- |
| SNOMED CT → WHO ICD-10 (2016) | SNOMED refset 447562003, `ExtendedMap` | yes — loaded by `clinical-graph bind` |
| SNOMED CT → ICD-O-3 | SNOMED refset 446608001, `SimpleMap` | yes |
| LOINC part → SNOMED CT | `PartRelatedCodeMapping.csv` | yes — loaded by `clinical-graph bind` |
| LOINC part → RxNorm | `PartRelatedCodeMapping.csv` | yes — loaded by `clinical-graph bind` |
| LOINC part → ChEBI, HGNC, NCBI Gene/Taxonomy, RadLex, UNII, PubChem | `PartRelatedCodeMapping.csv` | yes (targets are codes only; those vocabularies aren't loaded) |
| RxNorm → ATC | RxNorm (`SAB=ATC`), `rxnorm` | yes — loaded by `clinical-graph bind` |
| RxNorm → SNOMED CT | RxNorm (`SAB=SNOMEDCT_US`), `rxnorm` | yes — loaded by `clinical-graph bind` |
| ATC → SNOMED CT, LOINC | none official | through RxNorm; and UMLS |
| Any pair of loaded vocabularies (ICD-10-CM ↔ WHO ICD-10, LOINC ↔ ICD, SNOMED CT ↔ ATC / ICD-10-PCS / ICF, ...) | UMLS shared CUIs, `umls` | yes — `clinical-graph bind umls`, only the pairs no official map has |
| SNOMED CT → **ICD-10-CM** | NLM map, refset 6011000124106, `snomed_icd10cm` | yes — loaded by `clinical-graph bind` |
| ICD-9-CM → SNOMED CT | NLM ICD-9-CM to SNOMED CT maps, `icd9cm_snomed` | yes — loaded by `clinical-graph bind` |
| ICD-9-CM ↔ ICD-10-CM, ICD-10-PCS | CMS GEMs 2018, both directions, `icd9cm_gems` | yes — loaded by `clinical-graph bind` |
| ICD-9-CM ↔ WHO ICD-10 | none official | UMLS; or through ICD-10-CM / SNOMED CT |
| LOINC term → SNOMED CT concept | LOINC Extension, `sct2_Identifier`, `loinc_extension` | yes — loaded by `clinical-graph bind` |
| ICF ↔ anything | none official (ICD-11 Chapter V is built from ICF, but ICD-11 isn't loaded) | UMLS only |

The SNOMED International map targets WHO ICD-10; ICD-10-CM comes from NLM's map.

### Not yet included (candidates)

- **ICD-10-PCS ↔ anything.** No official map to SNOMED CT or any other clinical
  code system exists. Options, best first:
  - [AHRQ HCUP CCSR for ICD-10-PCS](https://hcup-us.ahrq.gov/toolssoftware/ccsr/prccsr.jsp):
    every PCS code in one of ~320 clinical categories (free CSV, yearly). A grouper,
    not a map: would be a small `CCSR` vocabulary.
  - UMLS Metathesaurus: loaded (`umls`), but only 94 PCS codes share a CUI with
    SNOMED CT or LOINC (mostly imaging), so it is no substitute for a map.
  - ICD-9-CM chain: CMS GEMs (PCS ↔ ICD-9-CM procedures, frozen since FY2018) plus
    NLM's ICD-9-CM → SNOMED CT procedure map; both loaded (`icd9cm_gems`,
    `icd9cm_snomed`), so the two-step path PCS → ICD-9-CM → SNOMED CT is in the
    graph. Lossy.
  - The PCS Body Part / Device / Substance keys (CMS code tables download), as raw
    material for matching PCS axis values to SNOMED CT body structures and devices.
  - OHDSI Athena has ICD-10-PCS as standard concepts, so almost no maps.
- **LOINC answers → SNOMED CT.** `AnswerList.csv` gives 2,428 answers (`LA` codes) a
  SNOMED CT code; needs answer nodes first (not loaded).
- **LOINC parts → ChEBI, NCBI, ...** in `PartRelatedCodeMapping.csv`: needs
  those vocabularies.
- **MED-RT** (NLM, free): drug mechanism of action, indications and
  contraindications linked to RxNorm (`MAY_TREAT` → conditions).
- **ATC DDDs**: only in WHO's paid ATC/DDD index.
- **SNOMED CT US-extension concepts** (2,613 rows of the NLM map start from one):
  would need the US Edition.

Add a new source by adding a `[sources.<key>]` table to `sources.toml`, a section
here, and a reader in `src/clinical_graph/vocabularies/`.

## Updating a release

1. Download and unpack the new release next to the old one (new `release_dir`).
2. Update `version`, `archive`, `release_dir` and the dated file names in
   `sources.toml`, and the matching section of this page.
3. `uv run clinical-graph sources verify --no-checksums`, then
   `uv run clinical-graph sources lock`, and commit `sources.toml`,
   `sources.lock.json` and this page together.
