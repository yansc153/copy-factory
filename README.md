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

Adapters live in `app/adapters.py`. The contract returns:

- `source`
- `source_id`
- `url`
- `title`
- `text`
- `author`
- `published_at`
- `media_urls`

Replace the `real_adapter()` branch for `xueqiu` and `reddit` after you provide endpoint and credential environment variables. Keep secrets in environment variables or secret files, never in code.

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

- Xueqiu endpoint and credential/cookie method.
- Reddit endpoint/client credentials or approved API route.
- DeepSeek production key or key file.
