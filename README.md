# Copy Factory v1

Single-user copy review workbench for Xueqiu/Reddit snapshot sync, dedupe, Huajiao-style draft generation, manual approval, drag-to-schedule planning, and a server-side publish queue for a future Mac mini publisher.

Deployment and Mac mini API contract: [docs/deployment-and-mac-mini-spec.md](docs/deployment-and-mac-mini-spec.md).
Mac mini downstream handoff: [docs/mac-mini-downstream-handoff.md](docs/mac-mini-downstream-handoff.md).

## Local Run

```bash
make install
cp env.example .env
export COPY_FACTORY_ENV=local
export COPY_FACTORY_USER=admin
export COPY_FACTORY_PASSWORD=password
export COPY_FACTORY_SESSION_SECRET=dev-secret-change-me
make sync
make run
```

Open `http://127.0.0.1:8000` and log in with `admin / password`. The app has three main work areas:

- Review: Twitter-like feed for generated copy, source text, and media references.
- Daily workbench: synced items are grouped by work date, with Today / Yesterday / All filters so skipped drafts stay available without cluttering the next morning.
- Sync: automatic status plus a manual "sync now" action.
- Schedule: drag approved copy into time slots, then confirm the publish plan.

Morning flow:

1. Open the site and run sync if the scheduler has not already pulled the latest snapshot.
2. Review generated drafts, edit today's copy, and save approved items.
3. Drag approved items into time slots on Schedule. The browser stores UTC ISO timestamps and displays them in local time.
4. Click "确认发布计划". The server marks scheduled approved work as confirmed queue tasks.
5. Stop there for the local morning workflow. The Mac mini publisher claims confirmed tasks later; the server decides whether a task is due.

Local smoke for that exact workflow:

```bash
make morning-smoke
```

It starts a temporary local server and SQLite DB, runs sync/generation through the web API, approves one generated draft, schedules it, confirms the plan, and prints the confirmed queue evidence.

## Checks

```bash
make lint
make typecheck
make test
make build
make morning-smoke
```

No package install is required. The app uses Python standard library only.

Real DeepSeek writing smoke:

```bash
DEEPSEEK_API_KEY_FILE=/run/secrets/deepseek_api_key make deepseek-smoke
```

This uses the real writer bridge on an English Reddit-style source and checks that the final review copy is Chinese, non-empty, and does not keep raw English source sentences. It exits clearly if neither `DEEPSEEK_API_KEY` nor `DEEPSEEK_API_KEY_FILE` is configured.

Regenerate existing drafts through the same Huajiao + DeepSeek path:

```bash
DEEPSEEK_API_KEY_FILE=/run/secrets/deepseek_api_key make regenerate-deepseek
```

By default this only rewrites draft, unpublished rows. Use `scripts/regenerate_deepseek.py --include-approved` only when changed approved copy should return to draft for review.

## 30-Minute Sync

Any scheduler can call:

```bash
COPY_FACTORY_DB=/absolute/path/copy_factory.sqlite3 python3 scripts/sync_once.py
```

Cron example:

```cron
*/30 * * * * cd /app && /usr/local/bin/python3 scripts/sync_once.py >> /var/log/copy-factory-sync.log 2>&1
```

For the hosted latest-snapshot API, use:

```bash
export COPY_FACTORY_SOURCES=xueqiu,reddit
export NEWS_HARNESS_EXPORT_TOKEN_FILE=/run/secrets/news_harness_export_token
export NEWS_HARNESS_EXPORT_LIMIT=500
python3 scripts/sync_once.py
```

The sync checks `/api/health` first. If `health.generated_at` matches the last processed snapshot, it skips export. If it changed, it pulls `/api/export/v1/items?source=xueqiu,reddit&limit=500` and SQLite dedupe keeps only new rows.

To run a 7am "yesterday only" batch, set a half-open date window:

```bash
export COPY_FACTORY_IMPORT_SINCE=2026-06-20
export COPY_FACTORY_IMPORT_UNTIL=2026-06-21
python3 scripts/sync_once.py
```

## Environment

Required for production:

- `COPY_FACTORY_ENV=production`
- `COPY_FACTORY_DB`
- `COPY_FACTORY_USER`
- `COPY_FACTORY_PASSWORD`
- `COPY_FACTORY_SESSION_SECRET`
- `COPY_FACTORY_PUBLISH_TOKEN` or `COPY_FACTORY_PUBLISH_TOKEN_FILE`
- `DEEPSEEK_API_KEY` or `DEEPSEEK_API_KEY_FILE`

Local/test may omit DeepSeek credentials and will use deterministic fake writing. Production refuses generation without a key.

## Real Data Sources

`xueqiu,reddit` can already read the hosted latest-snapshot API. Adapters live in `app/adapters.py`. The internal contract returns:

- `source`
- `source_id`
- `url`
- `title`
- `text`
- `author`
- `published_at`
- `media_urls`

Keep tokens in environment variables or secret files, never in code.

## Deployment

Hostinger compose path:

```text
docker-compose.yml
```

Production URL:

```text
https://hardness-content.hellopepper.work
```

The compose file is ready for Hostinger Docker Manager with the built-in Traefik project. It declares Docker labels for `hardness-content.hellopepper.work`, exposes the app only inside Docker, and lets Traefik handle HTTPS certificates through Let's Encrypt. The container starts the authenticated website and a built-in 30-minute sync loop.

Docker:

```bash
docker build -t copy-factory .
docker run --rm -p 8000:8000 \
  -e COPY_FACTORY_ENV=production \
  -e COPY_FACTORY_DB=/app/data/copy_factory.sqlite3 \
  -e COPY_FACTORY_USER="$COPY_FACTORY_USER" \
  -e COPY_FACTORY_PASSWORD="$COPY_FACTORY_PASSWORD" \
  -e COPY_FACTORY_SESSION_SECRET="$COPY_FACTORY_SESSION_SECRET" \
  -e DEEPSEEK_API_KEY_FILE=/run/secrets/deepseek_api_key \
  -v copy-factory-data:/app/data \
  copy-factory
```

Single-container production:

- Run the compose service from `docker-compose.yml`.
- It starts `scripts/serve_with_sync.py`, which serves the website and runs `run_sync` every 30 minutes.
- Point `hardness-content.hellopepper.work` to the VPS IP before relying on Traefik HTTPS.
- Put DeepSeek, source, and Mac mini publish API credentials in platform secrets.
- Keep the site behind HTTPS and basic platform firewall rules; the app itself is single-user session login, not a team permission system.

VPS responsibilities:

- Serve the authenticated review/schedule website.
- Run the 30-minute sync job.
- Store drafts, review status, schedule status, and publish queue state in SQLite.
- Expose the publish API for the Mac mini worker.

Mac mini responsibilities:

- Keep its own browser/X login/session outside this project.
- Poll and claim due tasks with `COPY_FACTORY_PUBLISH_TOKEN`.
- Publish claimed copy and media through its own module.
- Write the result back to this server.

## Web/API Surface

The browser app is served by `app.web` and talks to JSON endpoints:

- `GET /api/items`
- `GET /api/items/:id`
- `GET /api/settings/status`
- `POST /api/sync/preview`
- `POST /api/sync/run`
- `POST /api/items/:id/review`
- `POST /api/items/:id/schedule`
- `POST /api/items/:id/unschedule`
- `POST /api/publish/confirm_plan` browser session only; confirms approved and scheduled items.
- `POST /api/publish/cancel` browser session only; body `{"item_id":1}`; cancels an unclaimed confirmed task and keeps its schedule editable.
- `GET /api/publish/queue` browser session or `Authorization: Bearer <COPY_FACTORY_PUBLISH_TOKEN>`; lists confirmed/claimed/published/failed tasks.
- `POST /api/publish/claim_due` bearer token or browser session; body `{"limit":1}`; atomically marks due confirmed tasks as `claimed`, and returns `claim_token`. The server only returns tasks whose `scheduled_at` is due by server clock.
- `POST /api/publish/release` bearer token or browser session; body `{"item_id":1,"claim_token":"...","reason":"chrome_unavailable"}`; returns a claimed task to `confirmed`.
- `POST /api/publish/result` bearer token or browser session; body `{"item_id":1,"claim_token":"...","status":"published"}` or `{"item_id":1,"claim_token":"...","status":"failed","error":"..."}`.

Publish state flow:

`none -> confirmed -> claimed -> published`

Failure flow:

`none -> confirmed -> claimed -> failed`

Claimed tasks automatically return to `confirmed` if no result is written back before the claim TTL expires. The Mac mini can also release a claim explicitly when preflight fails.

Before a task is claimed, the browser can cancel confirmation and keep the scheduled slot. Rescheduling or unscheduling a confirmed item also clears publish state back to `none`, so confirmation remains an explicit final step after any time change.
Confirmed or failed items can be edited and then reconfirmed. Claimed or published items are locked from ordinary edit/reschedule/cancel actions.

## What Works Now

- Login-protected public website.
- Manual or scheduled mock sync.
- Deduped SQLite storage.
- Raw text, source, URL, media references, sync batch, generation status, and errors.
- Huajiao writer bridge with fake local writer or DeepSeek script. Chinese sources such as Xueqiu are rewritten in Chinese directly; English sources such as Reddit are first localized into Chinese investment context before draft generation.
- Review pool with edit and `draft` / `approved` / `rejected` save.
- Sync status with manual run feedback and recent batch history.
- Drag schedule timeline for approved copy.
- Confirmed server publish queue with atomic due-task claiming and result writeback.

## Still Needed For Real Sources

- A production export token in `NEWS_HARNESS_EXPORT_TOKEN` or `NEWS_HARNESS_EXPORT_TOKEN_FILE`.
- DeepSeek production key or key file.
- A production Mac mini publish token in `COPY_FACTORY_PUBLISH_TOKEN` or `COPY_FACTORY_PUBLISH_TOKEN_FILE`.
- The Mac mini publisher module that claims tasks and performs external posting. This repo intentionally stops at the server API contract.
