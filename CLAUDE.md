# CLAUDE.md

## What it is
Single-user 1:1 meeting companion for a team lead with ~4 engineers; 1:1s every 2–3 months.
Only the manager uses it. Server-rendered FastAPI + Jinja + HTMX, SQLite file, one container.

Non-goals: multi-user / engineer access / SSO / roles; calendar, Slack, email, notifications; mobile app, SPA, microservices.

## How to run
- Dev: `.env` with `DB_PATH=data/one_on_one.db` and `LOG_DIR=data/logs`, then `uv sync && uv run uvicorn app.main:app --reload --port 8080`.
- Lint/format: `uv run ruff check app && uv run ruff format app` (config in `pyproject.toml`).
- Docker: `docker compose up -d --build` → http://localhost:8080 (bound to 127.0.0.1). Stop: `docker compose down`.
- Data: `data/one_on_one.db` (WAL), logs: `data/logs/app.log` (+ stderr → `docker logs one-on-one`).
- Backup/move: copy `data/`, or Settings → Export/Import JSON. See README.
- CI (`.github/workflows/ci.yml`): ruff lint/format check, then a multi-arch image pushed to `ghcr.io/psychemisss/one-to-one-companion` (`latest` on main, semver on `v*` tags, `sha-*` always; PRs build without pushing). `docker-compose.yml` names that image, so `docker compose pull` uses it and `--build` builds locally.
- Dependencies are managed with uv (`pyproject.toml` + `uv.lock`); the Dockerfile runs `uv sync --frozen --no-dev`.

## Architecture
Request → auth dependency (`require_auth`, app-wide) → language middleware (`request.state.lang` from `lang` cookie)
→ route in `main.py` → `repo.py` (plain SQL) → SQLite. Full pages extend `base.html`; HTMX endpoints return
partials from `templates/partials/` or a plain "Saved" string that goes into a `.saved` span.

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, lifespan (logging, i18n check, DB init), all routes, Jinja globals/filters |
| `app/config.py` | All settings (decouple + pydantic), `settings` singleton |
| `app/logging_setup.py` | loguru sinks + stdlib `InterceptHandler` |
| `app/timeutils.py` | pendulum helpers: `now`, `today`, `to_date`, `days_since`, `next_due`, `humanize`, `fmt_date` |
| `app/i18n.py`, `app/i18n/{en,ru}.json` | `t(key, lang, **kw)`, cookie → lang, startup key-sync warning |
| `app/db.py` | connection, schema (`IF NOT EXISTS`), seed questions, `TABLES` order for backup |
| `app/repo.py` | all queries; one connection per call |
| `app/blocks.py` | meeting block sets and first-session → profile prefill mapping |
| `app/auth.py` | optional HTTP Basic auth |
| `app/templates/` | pages, `session.md` (Markdown export), `partials/` (HTMX fragments) |
| `app/static/` | vendored `htmx.min.js`, `pico.min.css`, Onest font (`onest-{latin,cyrillic}.woff2`); `app.css`; `timer.js` (timers + ←/→ shortcuts) |

**Meeting mode** (`/sessions/{id}/run?block=<key>`): each block is a full page load. Notes textarea autosaves
with `hx-trigger="keyup changed delay:800ms, change"` to `POST /sessions/{id}/notes/{block}` (upsert on
`UNIQUE(session_id, block_key)`). Mood, date and private notes post to `/sessions/{id}/field` (whitelisted).
Overall timer counts from `session.started_at`; the per-block countdown start is kept in `sessionStorage`.
Blocks before the current one are ticked. Finish → `completed`, `ended_at` set (kept on later edits) → session view.
A 4xx/5xx from any HTMX call is shown via `alert()` (listener in `base.html`).

Profile fields autosave on `change` to `/engineers/{id}/field` (whitelisted in `repo.ENGINEER_FIELDS`).

## Data model
Tables: `engineer`, `session` (→ engineer), `session_note` (→ session, cascade), `agenda_item` (→ engineer,
`session_id` set when discussed), `action_item` (→ engineer, `session_id` = session where created), `question`.
- **Carry-over:** the `review` block shows the engineer's actions not created in this session that are `open`,
  or were closed at/after this session's `started_at`. "Keep" leaves status `open`.
- "Actions closed" in a session = `closed_at` between the session's `started_at` and `ended_at`.
- Dashboard "last 1:1" = latest `completed` session by `date`; next due = that date + `cadence_days`.
- Dates are `YYYY-MM-DD`; timestamps are ISO-8601 with offset (from `timeutils.now()`). Parse with pendulum.
- Engineers are archived (`active=0`), never hard-deleted from the UI; archived engineers and their actions are hidden from the dashboard.

## Meeting blocks
`app/blocks.py`: `BLOCKS = {"regular": [...], "first": [...]}` of `(key, minutes)`. To add a block: add the tuple,
add `block.<key>.title` / `block.<key>.purpose` to both JSON files, optionally seed questions. Block-specific
widgets are `{% if block == ... %}` branches in `session_run.html`. A new session type = a new `BLOCKS` key +
`session.type.<key>` strings + an option in `partials/start_form.html`. First-session notes are copied into empty
profile fields on finish via `FIRST_SESSION_PREFILL`.

## Configuration (`app/config.py`)
| Env var | Default | Meaning |
|---|---|---|
| `APP_NAME` | `1:1 Companion` | Title in the nav |
| `TIMEZONE` | `Europe/Kyiv` | Timezone for "now"/"today" |
| `DEFAULT_LANGUAGE` | `en` | Language when no cookie (`en`/`ru`) |
| `DEFAULT_CADENCE_DAYS` | `75` | Cadence for new engineers |
| `DUE_SOON_DAYS` | `14` | "Due soon" highlight window |
| `DB_PATH` | `/data/one_on_one.db` | SQLite file (compose pins it to `/data`) |
| `APP_PASSWORD` | unset | Enables Basic auth when set |
| `LOG_LEVEL` | `INFO` | loguru level |
| `LOG_TO_FILE` | `true` | Also write `LOG_DIR/app.log` |
| `LOG_DIR` | `/data/logs` | Log directory (compose pins it) |
| `LOG_ROTATION` | `10 MB` | loguru rotation |
| `LOG_RETENTION` | `14 days` | loguru retention |

`HOST`, `PORT` and `SECRET_KEY` from the original plan were dropped: nothing read them.

## UI
Pico is the base; `app.css` overrides Pico variables with the app tokens (`--paper`, `--surface`, `--ink`, `--muted`,
`--pine`, `--amber`, `--brick`), with light and dark sets. Font: Onest (variable, Latin + Cyrillic, vendored).
- Dashboard (`.roster`): one row per engineer; the cadence track spans 1.25× cadence, so the due marker sits at 80%
  (`fill` is computed in `main.card`). Pine = ok, amber = due soon / never met, brick = overdue.
- Meeting mode: `.rail` blocks get `--min` (minutes) and their height scales with it; `.stage` holds the current block.
- Content sits in `.panel` surfaces. Avoid middle-dot meta strings; use commas.
- Pico gotcha: `button[type=submit]` has `width:100%` and outranks a class selector; `.inline-form button` resets it.

## Technical decisions
- SQLite over Postgres: single user, ~10 meetings/year, backup = copy one file.
- HTMX + Jinja over a SPA: no build step. Assets are vendored so the app runs offline.
- stdlib `sqlite3`, no ORM; schema via `CREATE TABLE IF NOT EXISTS`; `foreign_keys=ON`, WAL.
- Config: decouple reads `.env`/env, pydantic models hold it; nothing else touches the environment.
- pendulum for all dates (locale-aware formatting/humanize for RU).
- loguru; logs contain IDs only, never note/action/agenda text.
- Basic auth is optional (off when `APP_PASSWORD` is empty).
- JSON import validates column names against `PRAGMA table_info` and runs in one transaction.

## Conventions
- Keep it simple: plain functions, no speculative abstractions. If something gets complicated, propose a simpler option first.
- Comments only for non-obvious *why*.
- Validate by running the app and exercising routes with `curl` + `sqlite3` (no test suites).
- Config only via `from app.config import settings`. Dates only via `timeutils` (no `datetime.now()`). Logging via `logger` (no `print`).
- UI text only via `t("key")` in templates / `tr(request, "key")` in routes. Add every key to **both** `en.json` and `ru.json`;
  startup logs a WARNING for mismatched keys. Avoid count-dependent phrasing (e.g. "{n} d ago"/"{n} дн. назад").
  Third language: add `xx.json`, add `"xx"` to `i18n.LANGS`, add a link in `base.html`, add `text_xx` handling in `qtext` if questions need it.
- New page: route in `main.py` → template extending `base.html`; HTMX fragments go in `partials/`.
- Schema change: add `ALTER TABLE ... ADD COLUMN` in `db.init_db` guarded by a `PRAGMA table_info` check; keep it backwards compatible.
- No new dependencies without writing the reason here. Current: fastapi, uvicorn[standard], jinja2, python-multipart, pydantic, python-decouple, pendulum, loguru (dev: ruff).

## Known limitations / ideas
- One DB connection per query; fine for one user.
- No hard delete of sessions or engineers from the UI (use sqlite3 if needed).
- Container logs use UTC timestamps (no `TZ` set in the image).
- Per-block timer resets if the browser tab is closed (sessionStorage).
- Agenda items only surface in "Their topics", not "Work".
