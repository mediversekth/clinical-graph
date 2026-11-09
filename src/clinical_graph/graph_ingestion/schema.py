"""Node labels, constraints and indexes."""

from neo4j import Driver

from clinical_graph.model import Vocabulary

CONCEPT_LABEL = "Concept"
"""Label shared by every vocabulary node; ``id`` is unique across it."""

LABELS: dict[Vocabulary, str] = {
    Vocabulary.SNOMED: "SNOMEDCT",
    Vocabulary.LOINC: "LOINC",
    Vocabulary.ICD10CM: "ICD10CM",
    Vocabulary.ICD10PCS: "ICD10PCS",
    Vocabulary.ICD10: "ICD10",
    Vocabulary.ICD9CM: "ICD9CM",
    Vocabulary.RXNORM: "RXNORM",
    Vocabulary.ATC: "ATC",
    Vocabulary.ICF: "ICF",
    Vocabulary.MESH: "MESH",
}
"""Neo4j label of each vocabulary that is loaded as a graph."""

_STATEMENTS = (
    f"CREATE CONSTRAINT concept_id IF NOT EXISTS "
    f"FOR (n:{CONCEPT_LABEL}) REQUIRE n.id IS UNIQUE",
    f"CREATE INDEX concept_code IF NOT EXISTS FOR (n:{CONCEPT_LABEL}) ON (n.code)",
    f"CREATE INDEX concept_kind IF NOT EXISTS FOR (n:{CONCEPT_LABEL}) ON (n.kind)",
    f"CREATE FULLTEXT INDEX concept_name IF NOT EXISTS "
    f"FOR (n:{CONCEPT_LABEL}) ON EACH [n.name]",
)


def create_schema(driver: Driver, database: str) -> None:
    """Create the constraint and indexes if they do not exist yet."""
    with driver.session(database=database) as session:  # pyright: ignore[reportUnknownMemberType]
        for statement in _STATEMENTS:
            session.run(statement).consume()
        session.run("CALL db.awaitIndexes(600)").consume()
