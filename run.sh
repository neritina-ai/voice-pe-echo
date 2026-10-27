#!/usr/bin/env sh
# Start voice-pe-echo (macOS / Linux). The first run creates .venv and installs
# the dependencies; later runs reinstall only when pyproject.toml changed.
# Any arguments are passed through, e.g.: ./run.sh --host 192.168.1.50
set -e
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
    echo "第一次執行：建立 Python 虛擬環境（.venv）…"
    "$PYTHON" -m venv .venv
fi
if ! cmp -s pyproject.toml .venv/pyproject.installed; then
    echo "安裝／更新相依套件…"
    .venv/bin/python -m pip install --upgrade pip >/dev/null
    .venv/bin/python -m pip install -e .
    cp pyproject.toml .venv/pyproject.installed
fi
exec .venv/bin/python -m voice_pe_echo "$@"
