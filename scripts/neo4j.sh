#!/usr/bin/env bash
# Start, stop or check the local Neo4j (installed as in the README).
#
# Usage: scripts/neo4j.sh start|stop|restart|status
#
# Defaults match the README; override with environment variables:
#   NEO4J_VERSION  (2026.09.0)
#   NEO4J_HOME     (~/neo4j/neo4j-community-$NEO4J_VERSION)
#   NEO4J_JAVA     (~/neo4j/jdk-21; Neo4j needs Java 21)
#   NEO4J_HTTP     (http://localhost:7474, polled until it answers after a start)
set -euo pipefail

NEO4J_VERSION="${NEO4J_VERSION:-2026.09.0}"
NEO4J_HOME="${NEO4J_HOME:-$HOME/neo4j/neo4j-community-$NEO4J_VERSION}"
export JAVA_HOME="${NEO4J_JAVA:-$HOME/neo4j/jdk-21}"
NEO4J_HTTP="${NEO4J_HTTP:-http://localhost:7474}"
neo4j="$NEO4J_HOME/bin/neo4j"

[ -x "$neo4j" ] || { echo "Neo4j not found at $NEO4J_HOME (see README)" >&2; exit 1; }

start() {
    if "$neo4j" status >/dev/null 2>&1; then
        echo "Neo4j is already running"
        return
    fi
    "$neo4j" start
    echo -n "waiting for $NEO4J_HTTP "
    for _ in $(seq 1 120); do
        if curl -s -o /dev/null "$NEO4J_HTTP"; then
            echo " up"
            return
        fi
        echo -n "."
        sleep 1
    done
    echo " no answer after 120 s; see $HOME/neo4j/logs" >&2
    exit 1
}

case "${1:-}" in
    start) start ;;
    stop) "$neo4j" stop ;;
    restart) "$neo4j" stop || true; start ;;
    status) "$neo4j" status ;;
    *) echo "usage: $0 start|stop|restart|status" >&2; exit 2 ;;
esac
