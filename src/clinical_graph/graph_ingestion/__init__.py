"""Load the vocabulary graphs into Neo4j.

Each vocabulary becomes its own graph inside one Neo4j database: nodes carry the
shared ``Concept`` label plus a vocabulary label (``SNOMEDCT``, ``LOINC``,
``ICD10CM``, ``ICD10PCS``), and relationships only ever join two nodes with the
same vocabulary label. Bindings between vocabularies are a separate, later step.
"""

from clinical_graph.graph_ingestion.connection import Neo4jSettings, connect
from clinical_graph.graph_ingestion.ingest import delete_vocabulary, dry_run, ingest
from clinical_graph.graph_ingestion.schema import LABELS, create_schema
from clinical_graph.graph_ingestion.writer import GraphWriter

__all__ = [
    "LABELS",
    "GraphWriter",
    "Neo4jSettings",
    "connect",
    "create_schema",
    "delete_vocabulary",
    "dry_run",
    "ingest",
]
