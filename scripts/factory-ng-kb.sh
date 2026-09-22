#!/usr/bin/env bash
# Read-only query wrapper around the card-knowledge FTS5 service for agentic
# workers whose Bash permission is limited to this one command.
#
# Usage:
#   factory-ng-kb.sh find <query words...>        search everything
#   factory-ng-kb.sh find-<kind> <query words...> kind: primitive|helper|handler|engine
#   factory-ng-kb.sh toc                          compact primitive index
#   factory-ng-kb.sh caps <event_or_case_label>   engine-readiness check
#   factory-ng-kb.sh similar <oracle text...>     nearest existing handlers
set -uo pipefail
exec python3 "$(dirname "$0")/factory_ng_knowledge.py" "$@"
