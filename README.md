# Copy Factory v1

Single-user copy review system for mock Xueqiu/Reddit source sync, dedupe, Huajiao-style draft generation, and manual approval.

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

Open `http://127.0.0.1:8000` and log in with `admin / password`.

## Checks

```bash
make lint
make typecheck
make test
make build
```

No package install is required. The app uses Python standard library only.

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
python3 scripts/sync_once.py
```

The sync checks `/api/health` first. If `health.generated_at` matches the last processed snapshot, it skips export. If it changed, it pulls `/api/export/v1/items?source=xueqiu,reddit&limit=500` and SQLite dedupe keeps only new rows.

## Environment

Required for production:

- `COPY_FACTORY_ENV=production`
- `COPY_FACTORY_DB`
- `COPY_FACTORY_USER`
- `COPY_FACTORY_PASSWORD`
- `COPY_FACTORY_SESSION_SECRET`
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

Platform scheduler:

- Run the web process with `python3 -m app.web --host 0.0.0.0 --port 8000`.
- Run `python3 scripts/sync_once.py` every 30 minutes.
- Put DeepSeek and source credentials in platform secrets.

## What Works Now

- Login-protected public website.
- Manual or scheduled mock sync.
- Deduped SQLite storage.
- Raw text, source, URL, media references, sync batch, generation status, and errors.
- Huajiao writer bridge with fake local writer or DeepSeek script.
- Review pool with edit and `draft` / `approved` / `rejected` save.

## Still Needed For Real Sources

- A production export token in `NEWS_HARNESS_EXPORT_TOKEN` or `NEWS_HARNESS_EXPORT_TOKEN_FILE`.
- DeepSeek production key or key file.
