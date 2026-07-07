.PHONY: help up down status status-lite logs seed demo demo-digest eval test test-lite dev clean pull-models install

help:
	@echo "SignalCare Agentic Demo — commands"
	@echo ""
	@echo "  Docker-based (Phase 3+, see ADR-0003):"
	@echo "    make up            Start the full docker stack"
	@echo "    make down          Stop all services"
	@echo "    make status        Show service health"
	@echo "    make logs          Tail app logs"
	@echo "    make pull-models   Pull required Ollama models (in-container)"
	@echo "    make test          Run pytest suite in the app container"
	@echo "    make clean         Nuke volumes (WARNING: destroys demo data)"
	@echo ""
	@echo "  Native / no-docker (Weeks 1-2):"
	@echo "    make status-lite   Ping native Ollama + OpenRouter"
	@echo "    make dev           uvicorn main:app --reload from app/"
	@echo "    make test-lite     Run pytest from repo root, native Python"
	@echo "    make demo-digest   POST /digest/generate for a live Founder Mode brief"
	@echo ""
	@echo "  Utility:"
	@echo "    make install       Install Python deps (uv)"
	@echo "    make seed          Load synthetic referrals + PDFs"
	@echo "    make demo          Run 5-minute demo walkthrough"
	@echo "    make eval          Run evaluation harness against golden set"

up:
	docker compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@$(MAKE) status

down:
	docker compose down

status:
	@docker compose ps

# status-lite — Week 1/2 replacement for `make status` while the docker stack is deferred.
# Pings native Ollama at OLLAMA_HOST and verifies OpenRouter reachability. Uses curl,
# which is present on Windows 10+ and Git Bash. No jq dependency.
status-lite:
	@echo "Ollama (native):"
	@curl -sS -o /dev/null -w "  %{http_code}  $${OLLAMA_HOST:-http://localhost:11434}/api/tags\n" $${OLLAMA_HOST:-http://localhost:11434}/api/tags || echo "  UNREACHABLE"
	@echo "OpenRouter (hosted):"
	@curl -sS -o /dev/null -w "  %{http_code}  https://openrouter.ai/api/v1/models\n" https://openrouter.ai/api/v1/models || echo "  UNREACHABLE"

# dev — run the FastAPI app natively (no docker). Requires `make install` first.
dev:
	cd app && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# test-lite — pytest against native Python. Runs unit + skip-guarded integration tests.
test-lite:
	pytest -v

# demo-digest — Phase 2 CLOSE proof-point (ADR-0008). Live end-to-end:
# regex log parse -> psutil host stats -> httpx adapter probes -> hardening JSON
# -> L0 prompt registry -> L2 guardrail stack -> Anthropic Balanced (Sonnet) ->
# renderer -> data/digests/YYYY-MM-DD.{json,md}. Requires:
#   1. `make dev` running in another shell
#   2. ALLOW_ONDEMAND_DIGEST=true in .env (or exported)
#   3. ANTHROPIC_API_KEY set (real Anthropic call, cost ~$0.02/run)
# The digest surface returns the on-disk paths; those files are what the
# admin UI's /digest page (C-frontend session) will read.
demo-digest:
	@echo "POST http://localhost:8000/digest/generate"
	@curl -sS -X POST -H "Content-Type: application/json" http://localhost:8000/digest/generate | python -m json.tool || echo "  request failed — is 'make dev' running and ALLOW_ONDEMAND_DIGEST=true?"
	@echo ""
	@echo "Digest files landed in ./data/digests/ :"
	@ls -1t data/digests/ 2>/dev/null | head -4 | sed 's|^|  |' || echo "  (empty — check server logs)"

logs:
	docker compose logs -f app

pull-models:
	docker exec sc-ollama ollama pull llama3.2:3b
	@echo "For Balanced-tier local, also run: docker exec sc-ollama ollama pull qwen2.5:14b"

seed:
	docker compose exec app python -m app.scripts.seed_synthetic_data

demo:
	docker compose exec app python -m app.scripts.demo_walkthrough

eval:
	docker compose exec app python -m evals.run_evals

test:
	docker compose exec app pytest tests/ -v

install:
	cd app && uv sync

clean:
	docker compose down -v
	@echo "Volumes destroyed. Run 'make up' to recreate."
