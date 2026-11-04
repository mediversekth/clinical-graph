"""Command-line entry point: ``clinical-graph``."""

import argparse
import logging
import sys
from collections.abc import Sequence

from clinical_graph import __version__, paths
from clinical_graph.sources import load_manifest, update_lock, verify


def _cmd_list(_: argparse.Namespace) -> int:
    for source in load_manifest().values():
        print(f"{source.key:10} {source.title} ({source.version})")
        print(f"{'':10} download: {source.download}")
        print(f"{'':10} unpack to: {source.root()}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    return 0 if verify(checksums=not args.no_checksums) else 1


def _cmd_lock(_: argparse.Namespace) -> int:
    update_lock()
    print(f"wrote checksums to {paths.SOURCES_LOCK}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from clinical_graph.graph_ingestion import dry_run, ingest

    keys = args.source or None
    if args.dry_run:
        for key, counts in dry_run(keys).items():
            print(f"[{key}]")
            for name, n in counts.items():
                print(f"  {name:50} {n:>10,}")
        return 0
    ingest(keys, batch_size=args.batch_size, replace=args.replace)
    return 0


def _cmd_bind(args: argparse.Namespace) -> int:
    from clinical_graph.graph_ingestion import bind, dry_run_bind

    keys = args.source or None
    if args.dry_run:
        for key, counts in dry_run_bind(keys).items():
            print(f"[{key}]")
            for name, n in counts.items():
                print(f"  {name:50} {n:>10,}")
        return 0
    bind(keys, batch_size=args.batch_size, replace=args.replace)
    return 0


def _cmd_embed_build(args: argparse.Namespace) -> int:
    from clinical_graph.embeddings import build, embedding_sources

    for key in args.source or embedding_sources():
        build(
            key,
            batch_size=args.batch_size,
            overwrite=args.overwrite,
            device=args.device,
        )
    return 0


def _cmd_embed_load(args: argparse.Namespace) -> int:
    from clinical_graph.embeddings import load

    for key, counts in load(
        args.source or None, batch_size=args.batch_size, replace=args.replace
    ).items():
        print(f"[{key}]")
        for name, n in counts.items():
            print(f"  {name:50} {n:>10,}")
    return 0


def _cmd_embed_search(args: argparse.Namespace) -> int:
    from clinical_graph.embeddings import EmbeddingIndex, search_graph
    from clinical_graph.model import Vocabulary

    vocabulary = Vocabulary(args.vocabulary)
    if args.graph:
        results = search_graph(args.text, vocabulary, top_k=args.top_k, kind=args.kind)
        for text, hits in zip(args.text, results, strict=True):
            print(f"{text}:")
            for hit in hits:
                print(f"  {hit['score']:.3f}  {hit['id']:28} {hit['name']}")
        return 0
    index = EmbeddingIndex.load(vocabulary)
    for text, hits in zip(args.text, index.search(args.text, args.top_k), strict=True):
        print(f"{text}:")
        for hit in hits:
            print(
                f"  {hit['score']:.3f}  {hit['id']:28} {hit['text']} ({hit['origin']})"
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="clinical-graph", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources", help="inspect the source releases")
    ssub = sources.add_subparsers(dest="action", required=True)
    ssub.add_parser("list", help="show sources and where to put them").set_defaults(
        func=_cmd_list
    )
    check = ssub.add_parser("verify", help="check files exist and match the lock")
    check.add_argument("--no-checksums", action="store_true", help="presence only")
    check.set_defaults(func=_cmd_verify)
    ssub.add_parser("lock", help="record checksums in sources.lock.json").set_defaults(
        func=_cmd_lock
    )

    ing = sub.add_parser(
        "ingest",
        help="load the vocabulary graphs into Neo4j (nodes + same-vocabulary edges)",
    )
    ing.add_argument(
        "source",
        nargs="*",
        help="sources.toml keys (default: all): "
        "snomed loinc_extension loinc icd10cm icd10 rxnorm icf",
    )
    ing.add_argument(
        "--batch-size", type=int, default=10_000, help="rows per transaction"
    )
    ing.add_argument(
        "--replace",
        action="store_true",
        help="delete the vocabulary's nodes first (use after a release update)",
    )
    ing.add_argument(
        "--dry-run", action="store_true", help="read and count only; no Neo4j"
    )
    ing.set_defaults(func=_cmd_ingest)

    bnd = sub.add_parser(
        "bind",
        help="write cross-vocabulary mappings as MAPS_TO edges (after ingest)",
    )
    bnd.add_argument(
        "source",
        nargs="*",
        help="sources.toml keys whose maps to write (default: all): "
        "snomed snomed_icd10cm loinc loinc_extension rxnorm umls",
    )
    bnd.add_argument(
        "--batch-size", type=int, default=10_000, help="rows per transaction"
    )
    bnd.add_argument(
        "--replace",
        action="store_true",
        help="delete the source's MAPS_TO edges first, by provenance "
        "(use after a release update)",
    )
    bnd.add_argument(
        "--dry-run", action="store_true", help="read and resolve only; no Neo4j"
    )
    bnd.set_defaults(func=_cmd_bind)

    emb = sub.add_parser("embed", help="SapBERT embeddings of the concepts")
    esub = emb.add_subparsers(dest="action", required=True)
    keys_help = (
        "sources.toml keys (default: all): "
        "snomed loinc_extension loinc icd10cm icd10 rxnorm icf"
    )
    ebuild = esub.add_parser(
        "build", help="embed the concepts' texts and save them under data/processed"
    )
    ebuild.add_argument("source", nargs="*", help=keys_help)
    ebuild.add_argument("--batch-size", type=int, default=256, help="texts per pass")
    ebuild.add_argument(
        "--overwrite", action="store_true", help="rebuild even if up to date"
    )
    ebuild.add_argument("--device", help="torch device (default: cuda if available)")
    ebuild.set_defaults(func=_cmd_embed_build)

    eload = esub.add_parser(
        "load",
        help="write the name vectors onto the Neo4j nodes and create the vector "
        "indexes (after ingest)",
    )
    eload.add_argument("source", nargs="*", help=keys_help)
    eload.add_argument(
        "--batch-size", type=int, default=2_000, help="nodes per transaction"
    )
    eload.add_argument(
        "--replace",
        action="store_true",
        help="remove the source's node embeddings first (after a release update)",
    )
    eload.set_defaults(func=_cmd_embed_load)

    esearch = esub.add_parser("search", help="nearest concepts of one vocabulary")
    esearch.add_argument("text", nargs="+", help="query texts")
    esearch.add_argument(
        "--vocabulary",
        "-v",
        required=True,
        help="snomed loinc icd10cm icd10pcs icd10 rxnorm atc icf",
    )
    esearch.add_argument("--top-k", "-k", type=int, default=10)
    esearch.add_argument(
        "--graph",
        action="store_true",
        help="search the Neo4j vector index (names only) instead of the saved "
        "embeddings (names and synonyms)",
    )
    esearch.add_argument("--kind", help="with --graph: only concepts of this kind")
    esearch.set_defaults(func=_cmd_embed_search)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for name in ("httpx", "httpx2"):  # HuggingFace Hub requests
        logging.getLogger(name).setLevel(logging.WARNING)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
