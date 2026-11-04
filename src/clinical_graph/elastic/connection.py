"""Elasticsearch connection settings.

Read from the environment, with a git-ignored ``.env`` in the repository root as
fallback (see ``.env.example``):

* ``ELASTICSEARCH_URL`` (default ``http://localhost:9200``)
* ``ELASTICSEARCH_API_KEY``, or ``ELASTICSEARCH_USERNAME`` and
  ``ELASTICSEARCH_PASSWORD`` (optional: a local single-node setup has no
  security, see the README)
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

from clinical_graph import paths


@dataclass(frozen=True, slots=True)
class ElasticSettings:
    """Where and how to connect to Elasticsearch."""

    url: str
    api_key: str | None = None
    username: str | None = None
    password: str | None = None

    @classmethod
    def from_env(cls) -> "ElasticSettings":
        """Build settings from the environment and ``.env``."""
        load_dotenv(paths.PROJECT_ROOT / ".env", override=False)
        return cls(
            url=os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200"),
            api_key=os.environ.get("ELASTICSEARCH_API_KEY") or None,
            username=os.environ.get("ELASTICSEARCH_USERNAME") or None,
            password=os.environ.get("ELASTICSEARCH_PASSWORD") or None,
        )


def connect(settings: ElasticSettings | None = None) -> Elasticsearch:
    """Open a client and check that the cluster answers.

    The caller closes it, e.g. ``with connect() as es: ...``.

    Raises:
        ConnectionError: If the cluster cannot be reached.
    """
    settings = settings or ElasticSettings.from_env()
    basic_auth = (
        (settings.username, settings.password)
        if settings.username and settings.password
        else None
    )
    client = Elasticsearch(
        settings.url,
        api_key=settings.api_key,
        basic_auth=basic_auth,
        request_timeout=120,
    )
    if not client.ping():
        client.close()
        raise ConnectionError(
            f"Elasticsearch does not answer at {settings.url}; is it running? "
            "(see the README)"
        )
    return client
