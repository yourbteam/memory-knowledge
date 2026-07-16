#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cache_root="${TMPDIR:-/private/tmp}/memory-knowledge-python-cache"

mkdir -p "${cache_root}/uv" "${cache_root}/pycache"

cd "${repo_root}"
export UV_CACHE_DIR="${cache_root}/uv"
export PYTHONPYCACHEPREFIX="${cache_root}/pycache"
export PYTHONDONTWRITEBYTECODE=1

pytest_python="${MK_PYTEST_PYTHON:-${repo_root}/.venv/bin/python}"
if [[ -x "${pytest_python}" ]]; then
  exec "${pytest_python}" -m pytest -p no:cacheprovider "$@"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "run_pytest: neither ${pytest_python} nor uv is executable" >&2
  exit 2
fi

exec uv run pytest -p no:cacheprovider "$@"
