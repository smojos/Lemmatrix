#!/bin/sh
# Starts Lemmatrix on Mac or Linux. The first run sets up a Python environment in .venv.
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-python3.13}
if [ ! -x .venv/bin/python ]; then
    echo "Setting up Lemmatrix for the first time..."
    "$PY" -m venv .venv || { echo "Couldn't find Python 3.13 ($PY)."; exit 1; }
fi
if ! cmp -s requirements.txt .venv/requirements.installed; then
    .venv/bin/python -m pip install --upgrade pip >/dev/null
    .venv/bin/python -m pip install -r requirements.txt && cp requirements.txt .venv/requirements.installed
fi
exec .venv/bin/python -m lemmatrix "$@"
