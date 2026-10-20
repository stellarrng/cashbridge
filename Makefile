# CashBridge tasks. Uses .venv if present.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: install seed test test-fast story eval trust bench ops run anchor

install: ## install the full local stack (runtime + scikit-learn + test tools)
	$(PY) -m pip install -r requirements-dev.txt

seed:    ## write deterministic SYNTHETIC inputs to data/sandbox_inputs/
	$(PY) data/seed_sandbox.py

test:
	$(PY) -m pytest

test-fast:  ## all tests except the slow end-to-end trust scorecard run (about a minute)
	$(PY) -m pytest -m "not slow"

story:   ## run the 11-step demo story headless and regenerate data/execution_evidence/
	$(PY) scripts/run_demo_story.py

eval:    ## run the evaluation harness and write eval_report.md
	$(PY) eval/run_eval.py

trust:   ## run the security + agent + model trust scorecard and write data/execution_evidence/trust_scorecard.json
	$(PY) eval/trust_scorecard.py

ops:     ## operations benchmark: 100 synthetic events, Director alerts vs baselines, SIMULATED (about 30 s)
	$(PY) eval/ops_benchmark.py

bench:   ## planner benchmark (fixed workflow vs Intelligence Core with memory vs with learning), SIMULATED, about 1 minute
	$(PY) eval/planner_benchmark.py

run:     ## serve the built web app and the API at http://localhost:8000
	$(PY) -m uvicorn api.main:app --host 127.0.0.1 --port 8000

anchor:  ## write chain head hashes to data/execution_evidence/ANCHORS.md
	$(PY) scripts/anchor_head.py

# ---- Web app (frontend/, React + TypeScript). The built app in frontend/dist is committed, so `make run` needs no Node.
dev:         ## develop the UI: one command starts the API (:8100) and the UI with hot reload (http://localhost:5173)
	cd frontend && npm run dev

web-install: ## install the frontend's packages (Node 20+)
	cd frontend && npm install

web-build:   ## type-check and rebuild frontend/dist (commit the result)
	cd frontend && npm run build
