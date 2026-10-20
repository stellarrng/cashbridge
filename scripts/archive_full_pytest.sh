#!/usr/bin/env bash
# Run the full regression and archive the output with the environment it ran in.
#   bash scripts/archive_full_pytest.sh reports/full_pytest_v9_1.txt
set -u
OUT=${1:-reports/full_pytest_v9_1.txt}
PY=${PY:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}
{
  echo "# CashBridge full regression"
  echo "# commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)  date (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# python: $($PY --version 2>&1)  pytest: $($PY -m pytest --version 2>&1 | head -1)"
  echo "# optional packages: $($PY - <<'PYEOF'
import importlib.metadata as m
for p in ("web3", "eth-tester", "py-evm", "vyper", "PyMuPDF", "scikit-learn", "playwright"):
    try: print(f"{p}=={m.version(p)}", end="  ")
    except Exception: print(f"{p}=absent", end="  ")
PYEOF
)"
  echo "# command: $PY -m pytest -p no:cacheprovider -o addopts= -q -rs"
  echo
  $PY -m pytest -p no:cacheprovider -o addopts= -q -rs 2>&1
} > "$OUT"
tail -3 "$OUT"
