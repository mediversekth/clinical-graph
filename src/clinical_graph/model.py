"""Vocabulary-neutral graph model.

Every vocabulary reader produces the same three record types:

* :class:`Concept` - a node: one code of one vocabulary.
* :class:`Relation` - an edge *inside* a vocabulary (hierarchy, attributes,
  replacements, tabular notes).
* :class:`Mapping` - an edge *between* vocabularies: a binding.

Concepts are identified by a CURIE-like id, ``<vocabulary>:<code>``, with the code
exactly as the source publishes it (``icd10cm:E11.9``, not ``icd10cm:E119``).
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Vocabulary(StrEnum):
    """Code systems that can appear as concept ids or mapping targets."""

    SNOMED = "snomed"
    LOINC = "loinc"
    ICD10CM = "icd10cm"
    ICD10PCS = "icd10pcs"
    ICD10 = "icd10"  # WHO ICD-10: target of the SNOMED International map
    ICDO3 = "icdo3"
    RXNORM = "rxnorm"
    CHEBI = "chebi"


class MappingEquivalence(StrEnum):
    """How a source concept relates to its mapped target.

    Follows the FHIR ConceptMap equivalence codes that LOINC uses.
    """

    EQUIVALENT = "equivalent"
    NARROWER = "narrower"  # target is narrower than the source
    WIDER = "wider"  # target is wider than the source
    RELATED = "relatedto"
    UNSPECIFIED = "unspecified"


def concept_id(vocabulary: Vocabulary, code: str) -> str:
    """Build a concept id from a vocabulary and a source code.

    Args:
        vocabulary: The code system.
        code: The code as published by the source.

    Returns:
        The id, e.g. ``"snomed:44054006"``.
    """
    return f"{vocabulary}:{code}"


@dataclass(frozen=True, slots=True)
class Concept:
    """One code of one vocabulary."""

    vocabulary: Vocabulary
    code: str
    name: str
    kind: str = "concept"
    active: bool = True
    synonyms: tuple[str, ...] = ()
    properties: dict[str, str] = field(default_factory=dict[str, str], hash=False)

    @property
    def id(self) -> str:
        """The concept id, ``<vocabulary>:<code>``."""
        return concept_id(self.vocabulary, self.code)


@dataclass(frozen=True, slots=True)
class Relation:
    """A directed edge between two concepts of the same vocabulary.

    ``type`` is an upper-case relationship name without underscores (``ISA``,
    ``REPLACEDBY``, ``EXCLUDES1``, ``COMPONENT``, ...).
    """

    source: str
    type: str
    target: str
    properties: dict[str, str] = field(default_factory=dict[str, str], hash=False)


@dataclass(frozen=True, slots=True)
class Mapping:
    """A directed binding from a concept to a concept of another vocabulary.

    ``provenance`` names the file or map the binding comes from, so bindings of
    different origin and quality can be told apart in the graph.
    """

    source: str
    target: str
    equivalence: MappingEquivalence
    provenance: str
    properties: dict[str, str] = field(default_factory=dict[str, str], hash=False)
