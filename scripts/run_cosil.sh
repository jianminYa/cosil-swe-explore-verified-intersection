#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${COSIL_ENV_FILE:-}"
if [[ -z "${ENV_FILE}" && -f .env ]]; then
  ENV_FILE=".env"
elif [[ -z "${ENV_FILE}" && -f third_party/.env ]]; then
  ENV_FILE="third_party/.env"
fi

if [[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]]; then
  # Parse assignments without executing arbitrary non-assignment lines in the
  # user's env file. Values are shell-quoted before being evaluated.
  eval "$(/home/jql/miniforge3/envs/cosil/bin/python - "${ENV_FILE}" <<'PY'
import shlex
import sys
from dotenv import dotenv_values

for key, value in dotenv_values(sys.argv[1]).items():
    if key and value is not None:
        print(f"export {key}={shlex.quote(value)}")
PY
)"
fi

ACADEMIC_API_BASE="${ACADEMIC_API_BASE:-${OPENAI_API_BASE:-${OPENAI_BASE_URL:-}}}"
ACADEMIC_API_KEY="${ACADEMIC_API_KEY:-${OPENAI_API_KEY:-}}"
ACADEMIC_MODEL="${EVAL_MODEL_gpt:-${ACADEMIC_MODEL:-gpt-5.4}}"

if [[ -z "${ACADEMIC_API_BASE}" ]]; then
  echo "ACADEMIC_API_BASE/OPENAI_API_BASE is empty; refusing to start model calls." >&2
  exit 2
fi
if [[ -z "${ACADEMIC_API_KEY}" ]]; then
  echo "ACADEMIC_API_KEY/OPENAI_API_KEY is empty; refusing to start model calls." >&2
  exit 2
fi
if [[ -z "${ACADEMIC_MODEL}" ]]; then
  echo "ACADEMIC_API_BASE is empty; refusing to start model calls." >&2
  exit 2
fi

COSIL_CONDA_ENV="${COSIL_CONDA_ENV:-cosil}"
export COSIL_CONDA_ENV
export COSIL_PATH="${COSIL_PATH:-${ROOT_DIR}/third_party/CoSIL}"
export EXPLORER_CODES_ROOT="${EXPLORER_CODES_ROOT:-${ROOT_DIR}/third_party}"
TOP_K="${COSIL_TOP_K:-5}"
MAX_ITER="${COSIL_MAX_ITER:-10}"
TRACE_DIR="${COSIL_TRACE_DIR:-results/cosil_traces}"
STRUCTURE_CACHE_DIR="${COSIL_STRUCTURE_CACHE_DIR:-results/intermediates/repo_structures}"
export COSIL_STRUCTURE_CACHE_DIR="${STRUCTURE_CACHE_DIR}"
OUTPUT_PATH="${COSIL_OUTPUT:-}"
if [[ -z "${OUTPUT_PATH}" ]]; then
  OUTPUT_PATH='results/predictions/{explorer}/top{k}.jsonl'
fi
LIMIT_ARGS=()
if [[ -n "${COSIL_LIMIT:-}" ]]; then
  LIMIT_ARGS+=(--limit "${COSIL_LIMIT}")
fi

exec /home/jql/miniforge3/bin/conda run --no-capture-output -n "${COSIL_CONDA_ENV}" \
  python third_party/SWE-Explore-Bench/eval_runner.py \
  --bench data/processed/bench.verified_intersection.jsonl \
  --repos repos \
  --issue-map data/processed/issue_map.json \
  --explorers cosil \
  --top-k "${TOP_K}" \
  --academic-model "${ACADEMIC_MODEL}" \
  --academic-api-key "${ACADEMIC_API_KEY}" \
  --academic-api-base "${ACADEMIC_API_BASE}" \
  --cosil-max-iterations "${MAX_ITER}" \
  --cosil-region-mode "${COSIL_REGION_MODE:-file}" \
  --cosil-trace-dir "${TRACE_DIR}" \
  --workers "${COSIL_WORKERS:-1}" \
  "${LIMIT_ARGS[@]}" \
  --output "${OUTPUT_PATH}" \
  --resume
