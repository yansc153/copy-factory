# Copy Factory v1 Design

## Context

The workspace is empty except OMX state files. The user wants a runnable v1 that is ready for real source credentials/endpoints later, but works now with mock Xueqiu and Reddit data.

## Options

### Option A: Python standard library app

Use `http.server`, `sqlite3`, `unittest`, and small scripts. No package install, no external database, easy cron entry, easy Docker image.

Trade-off: the UI is server-rendered HTML and intentionally simple.

### Option B: Next.js + SQLite

Use a full web framework with API routes and richer UI.

Trade-off: more files, package install, build chain, and dependency ownership for a single-user internal tool.

### Option C: Flask + SQLite

Use a small Python web framework.

Trade-off: nicer routing than stdlib, but adds a dependency the v1 does not need.

## Decision

Choose Option A. It is the smallest reliable system that satisfies the v1: login-protected website, 30-minute scheduler entry, adapters, dedupe, writing harness, review pool, manual edits, tests, and deployment notes.

## Architecture

Copy Factory is a single-process Python app backed by SQLite. It can run as a website or as a one-shot sync command. Scheduler platforms call the same sync script every 30 minutes.

Files are split by responsibility:

- `app/config.py`: reads environment variables and refuses unsafe production settings.
- `app/db.py`: owns schema, inserts, dedupe, status updates, and queries.
- `app/adapters.py`: defines source item shape plus mock and real adapter contract.
- `app/writer.py`: deterministic fake writer for local/test and DeepSeek harness for production.
- `app/sync.py`: source fetch, dedupe, writer call, generated draft persistence.
- `app/web.py`: login, review list, item detail, manual save, manual sync.
- `scripts/sync_once.py`: cron/platform scheduler entry.

## Data Flow

1. A scheduler or user clicks "sync now".
2. `app.sync.run_sync()` fetches items from enabled adapters.
3. `app.db.insert_source_item()` dedupes by `source + source_id`, `source + url`, or `source + content_hash`.
4. New items are passed to `app.writer.generate_copy()`.
5. The generated draft is saved as `draft` with generation status and errors.
6. The website shows today's draft/approved/rejected pool.
7. The editor opens an item, reviews original text, media references, generated copy, edits, and saves `draft`, `approved`, or `rejected`.

## Adapter Contract

Adapters expose `fetch_items()` and return dictionaries with:

- `source`
- `source_id`
- `url`
- `title`
- `text`
- `author`
- `published_at`
- `media_urls`

`mock-xueqiu` and `mock-reddit` are complete. `xueqiu` and `reddit` adapters raise clear configuration errors until endpoint/credential environment variables are supplied and implemented.

## Writing Harness

The chain semantics mirror `huajiao-finance-writer`:

`source -> DeepSeek 花椒 voice imitation -> anti-ai/say-it-human/renwei cleanup -> editable draft`

Implementation:

- Local/test without a DeepSeek key uses deterministic fake output.
- Production without a DeepSeek key raises a clear error.
- With a DeepSeek key or key file, the app shells out to `/Users/oxjames/.codex/skills/huajiao-finance-writer/scripts/deepseek_generate.py` using temp files, without printing or storing secrets.

## Auth

The site is single-user. `COPY_FACTORY_USER` and `COPY_FACTORY_PASSWORD` are read from the environment. A signed session cookie protects all non-login pages.

## Error Handling

Sync stores per-item generation errors and keeps the raw item. Adapter-level failures are returned in the sync result and shown by CLI or web trigger. Production refuses missing auth credentials, missing session secret, and missing DeepSeek credentials.

## Testing

One focused test file covers the complete mock loop:

`sync -> dedupe -> generated draft -> web login -> review page -> edit save -> status update`

Project checks:

- `make install`
- `make lint`
- `make typecheck`
- `make test`
- `make build`

## Current Publish Boundary

The app now owns drag-and-drop scheduling plus a server-side publish queue. The browser stores scheduled times as UTC ISO strings and renders them locally. Clicking confirm moves approved, scheduled items into `confirmed`; a future Mac mini worker can claim due tasks by server clock and write back `published` or `failed`.

Still out of scope: Mac mini auto posting implementation, X/Twitter login, browser cookie storage, image publishing automation, team permissions, billing, analytics dashboard, or commercial admin backend.

## Self-Review

- No placeholders remain.
- Scope is one implementation plan.
- Real data sources are intentionally adapter-contract-only until credentials/endpoints exist.
- Production missing secret behavior is explicit.
