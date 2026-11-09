"""Vocabulary-neutral graph model.

Every vocabulary reader produces the same record types:

* :class:`Concept` - a node: one code of one vocabulary.
* :class:`Relation` - an edge *inside* a vocabulary (hierarchy, attributes,
  replacements, tabular notes).
* :class:`Mapping` - an edge *between* vocabularies: a binding (same meaning).
* :class:`Association` - an edge *between* vocabularies that is not a binding:
  a fact about two different things (a drug that may treat a disease).

Concepts are identified by ``<vocabulary>:<key>``. The key is the code exactly as
the source publishes it (``icd10cm:E11.9``, not ``icd10cm:E119``), prefixed with
the kind for grouping nodes that have no code of their own
(``icd10cm:block:E08-E13``, ``icd10pcs:table:001``).
"""

from dataclasses import dataclass, field
from enum import StrEnum

type PropertyValue = str | int | float | bool | list[str] | None
"""A value Neo4j can store as a node or relationship property."""


class Vocabulary(StrEnum):
    """Code systems that can appear as concept ids or mapping targets."""

    SNOMED = "snomed"
    LOINC = "loinc"
    ICD10CM = "icd10cm"
    ICD10PCS = "icd10pcs"
    ICD9CM = "icd9cm"  # ICD-9-CM, diagnoses and procedures
    ICD10 = "icd10"  # WHO ICD-10: target of the SNOMED International map
    ICDO3 = "icdo3"
    RXNORM = "rxnorm"
    ATC = "atc"  # WHO ATC classification, from the RxNorm release
    CHEBI = "chebi"
    ICF = "icf"  # WHO ICF (functioning, disability and health)
    MESH = "mesh"  # MeSH concepts (M...), the diseases MED-RT refers to


class MappingEquivalence(StrEnum):
    """How a source concept relates to its mapped target.

    Follows the FHIR ConceptMap equivalence codes that LOINC uses.
    """

    EQUIVALENT = "equivalent"
    NARROWER = "narrower"  # target is narrower than the source
    WIDER = "wider"  # target is wider than the source
    RELATED = "relatedto"
    UNSPECIFIED = "unspecified"


def concept_id(vocabulary: Vocabulary, key: str) -> str:
    """Build a concept id.

    Args:
        vocabulary: The code system.
        key: The code as published by the source, or ``<kind>:<code>`` for
            grouping nodes such as ICD-10-CM blocks.

    Returns:
        The id, e.g. ``"snomed:44054006"``.
    """
    return f"{vocabulary}:{key}"


def vocabulary_of(id_: str) -> Vocabulary:
    """Return the vocabulary a concept id belongs to.

    Raises:
        ValueError: If the prefix is not a known vocabulary.
    """
    return Vocabulary(id_.split(":", 1)[0])


@dataclass(frozen=True, slots=True)
class Concept:
    """One code of one vocabulary.

    ``key`` overrides the code in the id for grouping nodes (``block:E08-E13``);
    leave it unset for ordinary codes.
    """

    vocabulary: Vocabulary
    code: str
    name: str
    kind: str = "concept"
    key: str | None = None
    active: bool = True
    synonyms: tuple[str, ...] = ()
    properties: dict[str, PropertyValue] = field(
        default_factory=dict[str, PropertyValue], hash=False
    )

    @property
    def id(self) -> str:
        """The concept id, ``<vocabulary>:<key or code>``."""
        return concept_id(self.vocabulary, self.key or self.code)


@dataclass(frozen=True, slots=True)
class Relation:
    """A directed edge between two concepts of the same vocabulary.

    ``type`` is an UPPER_SNAKE_CASE relationship name (``ISA``, ``FINDING_SITE``,
    ``REPLACED_BY``, ``EXCLUDES1``, ...). ``key`` holds the properties that tell
    parallel edges of the same type apart (SNOMED CT relationship ``id``, LOINC
    ``axis``); ``properties`` are descriptive only.
    """

    source: str
    type: str
    target: str
    key: dict[str, PropertyValue] = field(
        default_factory=dict[str, PropertyValue], hash=False
    )
    properties: dict[str, PropertyValue] = field(
        default_factory=dict[str, PropertyValue], hash=False
    )


@dataclass(frozen=True, slots=True)
class Mapping:
    """A directed binding from a concept to a concept of another vocabulary.

    ``provenance`` names the file or map the binding comes from, so bindings of
    different origin and quality can be told apart in the graph. ``key`` tells
    apart several rows of one map between the same two concepts (e.g. the refset
    member id); leave it unset when there is at most one.
    """

    source: str
    target: str
    equivalence: MappingEquivalence
    provenance: str
    key: str | None = None
    properties: dict[str, PropertyValue] = field(
        default_factory=dict[str, PropertyValue], hash=False
    )


@dataclass(frozen=True, slots=True)
class Association:
    """A directed edge between concepts of two vocabularies that is not a binding.

    The two ends are different things (a drug and a disease), so it is no
    ``MAPS_TO``: ``type`` is an UPPER_SNAKE_CASE relationship name (``MAY_TREAT``).
    Both ends hold the codes as the source publishes them; ``bind`` resolves them
    like map targets. ``provenance`` names the source, as for :class:`Mapping`.
    """

    source: str
    type: str
    target: str
    provenance: str
    properties: dict[str, PropertyValue] = field(
        default_factory=dict[str, PropertyValue], hash=False
    )
