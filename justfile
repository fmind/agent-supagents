# https://just.systems/man/en/

# list tasks
default:
    @just --list

# clean caches
clean:
    rm -rf .pytest_cache/ .ruff_cache/ .ty_cache/ htmlcov/ .coverage
    find . -type d -name __pycache__ -exec rm -r {} \+
    find . -type f -name '*.py[co]' -delete

# format sources
format:
    uv run ruff check --select=I --fix .
    uv run ruff format .

# install dependencies
install:
    uv sync
    uv run pre-commit install --install-hooks

# run all static checks
lint:
    uv run ruff format --check .
    uv run ruff check .
    uv run ty check
    uv lock --check

# run tests (can pass extra args)
test *args="":
    uv run pytest {{ args }}

# update locked dependencies and hooks
update:
    uv sync --upgrade
    uv run pre-commit autoupdate
