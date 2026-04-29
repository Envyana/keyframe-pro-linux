#!/usr/bin/env bash
# Convenience launcher. Activates venv if present, else uses system python.
set -e
cd "$(dirname "$0")"

if [ -d .venv ]; then
    . .venv/bin/activate
fi

export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
exec python -m keyframe_pro "$@"
