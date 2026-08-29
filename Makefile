# Prérequis : uv (https://docs.astral.sh/uv/)
UV ?= uv

setup:
	$(UV) sync --locked --all-extras

test:             ## tests fermés, sans réseau
	$(UV) run pytest

lint:
	$(UV) run ruff check .

all:              ## fetch + lab + figures (réseau requis pour fetch)
	$(UV) run svr fetch
	$(UV) run svr lab
	$(UV) run svr figures
