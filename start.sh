#!/usr/bin/env bash
# Lanceur Mac / Linux : installe tout au premier lancement, connecte Phantom si besoin, démarre le bot.
#   ./start.sh            lance le bot
#   ./start.sh --status   (ou --check, --sell-all, --once)
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python) || { echo "Installe Python 3.10+ : https://www.python.org/downloads/"; exit 1; }
if [ ! -d .venv ]; then
  echo "Installation (une seule fois)…"
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements-memecoin.txt
fi
if [ "$1" = "--connect" ]; then exec .venv/bin/python -m memecoin_bot.connect; fi
[ -f .env ] || .venv/bin/python -m memecoin_bot.connect
if [ $# -eq 0 ]; then
  .venv/bin/python -m memecoin_bot.main --check || { echo "Corrige les erreurs ci-dessus (./start.sh --connect pour reconfigurer)."; exit 1; }
fi
exec .venv/bin/python -m memecoin_bot.main "$@"
