# Contributing

## Setup

```sh
git clone https://github.com/aohana182/gonzo-funnel
cd gonzo-funnel
uv sync --extra dev
cp .env.example .env
uv run python -m cli --config-check
uv run python -m pytest tests/ -q
```

## Workflow

1. Branch from `master`: `git checkout -b feat/your-feature`
2. Make changes and run tests
3. Commit with [Conventional Commits](https://www.conventionalcommits.org): `feat(scope): description`
4. Open a PR against `master`

## Commit format

```
type(scope): subject (max 72 chars)

- What changed: files and key code changes
- Why this matters: problem solved or risk mitigated
- How verified: tests run, manual checks
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

## Code style

```sh
uv run ruff check .
uv run ruff format .
uv run python -m pytest tests/ -q
```

All three must pass before pushing.

## Spec files

`spec/` is gitignored and never committed. Do not add spec content to Python source or tests.

## Agent output contract

Every agent returns a typed Pydantic model. Do not change output schemas without updating downstream agents and tests.
