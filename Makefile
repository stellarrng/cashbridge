# CashBridge tasks. Uses .venv if present.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: seed test story eval run anchor ui

seed:    ## write deterministic SYNTHETIC inputs to data/sandbox_inputs/
	$(PY) data/seed_sandbox.py

test:
	$(PY) -m pytest

story:   ## run the 11-step demo story headless and regenerate data/execution_evidence/
	$(PY) scripts/run_demo_story.py

eval:    ## run the evaluation harness and write eval_report.md
	$(PY) eval/run_eval.py

run:     ## serve the dashboard and API at http://localhost:8000
	$(PY) -m uvicorn api.main:app --host 127.0.0.1 --port 8000

ui:      ## rebuild the React bundle (needs Node 20+); the built ui/web/dist is committed
	cd ui/web && npm install && npm run build

anchor:  ## write chain head hashes to data/execution_evidence/ANCHORS.md
	$(PY) scripts/anchor_head.py
