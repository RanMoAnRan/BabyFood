# Repository Guidelines

## Project Structure & Module Organization

- `miniprogram/`: WeChat Mini Program source (WXML/JS/WXSS).
  - `miniprogram/pages/<page>/index.{js,wxml,wxss,json}`: page modules (`home`, `list`, `detail`, `profile`).
  - `miniprogram/utils/`: shared utilities (CDN fetch, caching, age calc, favorites).
  - `miniprogram/seed/`: built-in offline “seed” data used when CDN is unavailable.
- `backend/`: Python backend utilities (single-site importer + dataset generator).
  - `backend/daily_job.py`: dataset generator (runs locally and in GitHub Actions).
  - `backend/sources/`: single-site import adapters (currently `nutrition_gov.py`).
- `backend/data/`: generated static dataset served via GitHub + jsDelivr.
  - `backend/data/manifest.json`: update entrypoint (version + latest ids).
  - `backend/data/recipes_index.json`: list/index data for browsing/search.
  - `backend/data/recipes/<id>.json`: per-recipe detail documents.
  - `backend/data/images/`: downloaded/converted cover images (WebP).
- `.github/workflows/daily.yml`: scheduled run + auto-commit for `backend/data/`.

## Build, Test, and Development Commands

- Create venv + install deps: `python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt`
- Validate importer without writing files: `.venv/bin/python3 backend/daily_job.py --dry-run --limit 1`
- Generate dataset locally (writes `backend/data/`): `.venv/bin/python3 backend/daily_job.py --limit 20`
- Open Mini Program: import repo root in WeChat DevTools (`miniprogram/` is the app root).

## Coding Style & Naming Conventions

- JavaScript/WXML/WXSS: 2-space indentation; page entry files are always `index.*`.
- Python: 4-space indentation; keep importer logic in `sources/<site>.py`.
- Data naming: recipe ids are `md5(source_url)`; detail path must be `backend/data/recipes/<id>.json`.

## Testing Guidelines

No automated test suite yet. If you add one, keep it lightweight and runnable offline (e.g., parsing/unit tests for `backend/sources/` and `backend/daily_job.py`).

## Commit & Pull Request Guidelines

- This repo may start without Git history; use conventional prefixes going forward: `feat:`, `fix:`, `chore:`, `docs:`.
- PRs should include: summary, affected paths (e.g., `miniprogram/utils/api.js`), and screenshots for UI changes. Link any relevant issue/task.

## Configuration & Safety

- Set CDN base in `miniprogram/config.js` (`CDN_BASE`) and whitelist `https://cdn.jsdelivr.net` in Mini Program “request/download” domains.
- Only ingest content you’re allowed to redistribute; preserve `source_url`/`origin_url` for traceability.
