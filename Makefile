.PHONY: help install sync run cli server test test-watch help-cli review security docker ai-detect clean

UV ?= uv
PORT ?= 8765
HOST ?= 127.0.0.1

help:
	@echo "Turtles CLI project commands"
	@echo ""
	@echo "  make install      Install/sync dependencies with dev extras"
	@echo "  make sync         Alias for install"
	@echo "  make run          Start the interactive turtle CLI"
	@echo "  make cli          Alias for run"
	@echo "  make server       Start the local FastAPI server"
	@echo "  make test         Run tests"
	@echo "  make help-cli     Show Turtles CLI command help"
	@echo "  make review       Run local code review command"
	@echo "  make security     Run local security audit command"
	@echo "  make docker       Run Docker audit command"
	@echo "  make ai-detect    Run AI-generated-code marker scan"
	@echo "  make install-global Install the turtle command globally (editable mode)"
	@echo "  make uninstall-global Uninstall the global turtle command"
	@echo "  make docker-build   Build the Alpine-based Docker image"
	@echo "  make docker-run     Run the interactive turtle CLI inside Docker"
	@echo "  make clean          Remove local caches"

install:
	$(UV) sync --extra dev

sync: install

install-global:
	$(UV) tool install --editable .

uninstall-global:
	$(UV) tool uninstall turtles-cli

run:
	$(UV) run turtle

cli: run

server:
	$(UV) run turtles-server --host $(HOST) --port $(PORT)

test:
	$(UV) run --extra dev pytest

test-watch:
	$(UV) run --extra dev pytest -q -x

help-cli:
	$(UV) run turtle help

review:
	$(UV) run turtle /code-review

security:
	$(UV) run turtle /security

docker:
	$(UV) run turtle /docker

ai-detect:
	$(UV) run turtle /ai-detect

docker-build:
	docker build -t turtles-cli .

docker-run:
	docker run -it -v $(shell pwd):/app turtles-cli

clean:
	$(UV) cache clean
