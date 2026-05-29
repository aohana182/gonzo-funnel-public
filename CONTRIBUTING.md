# Contributing

Contributions are welcome — bug reports, feature requests, and pull requests.

## Setup

```sh
git clone https://github.com/aohana182/gonzo-funnel-public.git
cd gonzo-funnel-public
uv sync
cp .env.example .env   # fill in API keys
uv run python -m cli --dry-run --limit 5
```

Run tests:

```sh
uv run pytest
```

## Workflow

1. Branch from `main`: `git checkout -b feat/your-feature`
2. Make changes and run tests
3. Commit with [Conventional Commits](https://www.conventionalcommits.org): `feat(scope): description`
4. Open a PR against `main`

## Commit format

```
type(scope): subject

- What changed
- Why it matters
- How verified
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`
