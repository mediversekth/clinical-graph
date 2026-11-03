"""Neo4j connection settings.

Read from the environment, with a git-ignored ``.env`` in the repository root as
fallback (see ``.env.example``):

* ``NEO4J_URI`` (default ``bolt://localhost:7687``)
* ``NEO4J_USERNAME`` (default ``neo4j``)
* ``NEO4J_PASSWORD`` (required)
* ``NEO4J_DATABASE`` (default ``neo4j``)
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from clinical_graph import paths


@dataclass(frozen=True, slots=True)
class Neo4jSettings:
    """Where and how to connect to Neo4j."""

    uri: str
    username: str
    password: str
    database: str

    @classmethod
    def from_env(cls) -> "Neo4jSettings":
        """Build settings from the environment and ``.env``.

        Raises:
            RuntimeError: If ``NEO4J_PASSWORD`` is not set.
        """
        load_dotenv(paths.PROJECT_ROOT / ".env", override=False)
        password = os.environ.get("NEO4J_PASSWORD")
        if not password:
            raise RuntimeError(
                "NEO4J_PASSWORD is not set; export it or put it in .env "
                "(see .env.example)"
            )
        return cls(
            uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            username=os.environ.get("NEO4J_USERNAME", "neo4j"),
            password=password,
            database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        )


def connect(settings: Neo4jSettings) -> Driver:
    """Open a driver and check that the server is reachable.

    The caller closes it, e.g. ``with connect(settings) as driver: ...``.
    """
    driver = GraphDatabase.driver(  # pyright: ignore[reportUnknownMemberType]
        settings.uri,
        auth=(settings.username, settings.password),
        notifications_min_severity="WARNING",
    )
    driver.verify_connectivity()  # pyright: ignore[reportUnknownMemberType]
    return driver
