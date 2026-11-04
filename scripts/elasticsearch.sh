#!/usr/bin/env bash
# Start, stop or check the local Elasticsearch (installed as in the README).
#
# Usage: scripts/elasticsearch.sh start|stop|restart|status
#
# Defaults match the README; override with environment variables:
#   ES_VERSION  (9.1.10)
#   ES_HOME     (~/elasticsearch/elasticsearch-$ES_VERSION)
#   ES_PIDFILE  (~/elasticsearch/pid)
#   ES_URL      (http://localhost:9200, polled until the cluster is up)
set -euo pipefail

ES_VERSION="${ES_VERSION:-9.1.10}"
ES_HOME="${ES_HOME:-$HOME/elasticsearch/elasticsearch-$ES_VERSION}"
ES_PIDFILE="${ES_PIDFILE:-$HOME/elasticsearch/pid}"
ES_URL="${ES_URL:-http://localhost:9200}"

[ -x "$ES_HOME/bin/elasticsearch" ] || {
    echo "Elasticsearch not found at $ES_HOME (see README)" >&2
    exit 1
}

pid() {
    # The pid of the running Elasticsearch, if any
    [ -f "$ES_PIDFILE" ] && kill -0 "$(cat "$ES_PIDFILE")" 2>/dev/null && cat "$ES_PIDFILE"
}

health() {
    curl -s -m 5 "$ES_URL/_cluster/health" | sed -n 's/.*"status":"\([a-z]*\)".*/\1/p'
}

start() {
    if pid >/dev/null; then
        echo "Elasticsearch is already running (pid $(pid))"
        return
    fi
    "$ES_HOME/bin/elasticsearch" -d -p "$ES_PIDFILE" >/dev/null
    echo -n "waiting for $ES_URL "
    for _ in $(seq 1 120); do
        status="$(health || true)"
        if [ "$status" = green ] || [ "$status" = yellow ]; then
            echo " $status (pid $(pid))"
            return
        fi
        echo -n "."
        sleep 1
    done
    echo " not up after 120 s; see $HOME/elasticsearch/logs" >&2
    exit 1
}

stop() {
    local p
    if ! p="$(pid)"; then
        echo "Elasticsearch is not running"
        return
    fi
    kill "$p"
    echo -n "stopping (pid $p) "
    for _ in $(seq 1 60); do
        if ! kill -0 "$p" 2>/dev/null; then
            echo " stopped"
            return
        fi
        echo -n "."
        sleep 1
    done
    echo " still running after 60 s" >&2
    exit 1
}

status() {
    if p="$(pid)"; then
        echo "Elasticsearch is running (pid $p), cluster $(health || echo "not answering")"
    else
        echo "Elasticsearch is not running"
        exit 3
    fi
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    *) echo "usage: $0 start|stop|restart|status" >&2; exit 2 ;;
esac
