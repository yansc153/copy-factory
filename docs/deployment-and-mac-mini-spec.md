# Copy Factory Deployment And Mac Mini Contract

## Decision

Copy Factory runs on the VPS. It owns upstream sync, DeepSeek/Huajiao writing, manual review, scheduling, and the server publish queue.

The Mac mini owns external posting only. It never crawls upstream feeds and never decides what should be published. It polls the VPS publish API, claims due tasks, publishes them with its own browser/session, then writes the result back.

Copy Factory is the only source of truth for publish task state. The Mac mini is a stateless executor: preflight, claim, publish, write result or release.

## Upstream Sync

Run sync every 30 minutes on the VPS:

```bash
python3 scripts/sync_once.py
```

Use the upstream health endpoint before consuming:

- `NEWS_HARNESS_EXPORT_BASE_URL=https://newshardness.hellopepper.work`
- Health source: `/api/health`
- Current recommended feed source: `/api/timeline`
- Full frontend metadata source if needed: `/web/data/radar-timeline/timeline_feed.json`

Current app behavior:

- Uses `health.generated_at` to skip unchanged snapshots.
- Fetches `xueqiu` and `reddit` independently so one noisy source cannot hide the other.
- Dedupes in SQLite by source id, URL, and content hash.
- Stores new items under the local `work_date`, so the morning workbench stays clean.
- Sends new items through `huajiao-finance-writer` plus DeepSeek when a key is configured.
- For newly generated items with no upstream `media_urls`, optionally searches Brave Search Image API and stores up to 3 validated local candidates under `/media/google/...`.

Morning use:

- The scheduler may run all day.
- The human opens the site around 7am Beijing time and reviews the current `work_date`.
- Yesterday's unselected drafts remain available under Yesterday / All.

## Data Freshness Rules

If upstream health reports either of these, the VPS should not consume new feed items:

- `feed_stale=true`
- `feed_age_minutes > 90`

If downstream only wants verified items later, add a feed filter for upstream `eval_status` / `outcome_status`. For now Copy Factory can ingest predictions because the human review step is still mandatory.

## Review And Schedule States

Content states:

```text
draft -> approved -> scheduled -> confirmed -> claimed -> published
                                         claimed -> failed
```

Meaning:

- `draft`: generated, waiting for human review.
- `approved`: human accepted it for possible publishing.
- `scheduled`: human saved a target time as a schedule draft; Mac mini cannot claim it yet.
- `confirmed`: human clicked Enter Publish Queue; Mac mini may claim/export it on the next due polling loop.
- `claimed`: Mac mini has locked the task.
- `published`: Mac mini reported success.
- `failed`: Mac mini reported failure; human can edit/reschedule/reconfirm.

Before claim, a confirmed item can be cancelled from the browser. It cannot be edited, rescheduled, or unscheduled until cancellation succeeds, so a human must confirm the plan again after any later change.
Once an item is `claimed` or `published`, normal web edits, reschedules, and cancellations are locked.
Claimed tasks automatically return to `confirmed` after the 20-minute server claim TTL if no result is written.

## Mac Mini API Contract

Mac mini authenticates with:

```http
Authorization: Bearer <COPY_FACTORY_PUBLISH_TOKEN>
```

Read queue:

```http
GET /api/publish/queue
```

Claim due confirmed scheduled tasks:

```http
POST /api/publish/claim_due
Content-Type: application/json

{"limit":1}
```

The server decides whether `scheduled_at` is due. The Mac mini publisher must not apply its own due-time gate; if a task is returned here, it is ready to publish.
If a browser user cancels before claim, that task will not be returned by `claim_due` until it is confirmed again. Rescheduling requires cancelling confirmation first.
`claim_due` returns tasks after atomically changing them from `confirmed` to `claimed`; returned tasks are not still `confirmed`.

Claim response task shape:

```json
{
  "item_id": 123,
  "scheduled_at": "2026-06-21T09:00:00.000Z",
  "status": "claimed",
  "copy": "final approved copy",
  "source": "xueqiu_hot",
  "source_id": "upstream-id",
  "source_url": "https://example.com/source",
  "title": "source title",
  "media_urls": ["https://example.com/image.jpg"],
  "selected_media_url": "https://example.com/image.jpg",
  "claim_token": "server-generated-lock-token"
}
```

Mac mini should prefer `selected_media_url` when present and fall back to `media_urls`.

Release a claim when the worker cannot safely publish after claiming:

```http
POST /api/publish/release
Content-Type: application/json

{"item_id":123,"claim_token":"...","reason":"chrome_unavailable"}
```

Write result:

```http
POST /api/publish/result
Content-Type: application/json

{"item_id":123,"claim_token":"...","status":"published"}
```

Failure:

```json
{"item_id":123,"claim_token":"...","status":"failed","error":"reason"}
```

`claim_token` makes result writeback single-owner. Retrying the same `item_id`, `claim_token`, `status`, and `error` is idempotent; a stale or mismatched token returns `409`.

Executable smoke:

```bash
export COPY_FACTORY_BASE_URL=https://hardness-content.hellopepper.work
export COPY_FACTORY_PUBLISH_TOKEN=...

curl -fsS -H "Authorization: Bearer $COPY_FACTORY_PUBLISH_TOKEN" \
  "$COPY_FACTORY_BASE_URL/api/publish/queue"

claim_json="$(curl -fsS -X POST \
  -H "Authorization: Bearer $COPY_FACTORY_PUBLISH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit":1}' \
  "$COPY_FACTORY_BASE_URL/api/publish/claim_due")"
printf '%s\n' "$claim_json"

eval "$(python3 - "$claim_json" <<'PY'
import json, sys
task = (json.loads(sys.argv[1]).get("tasks") or [None])[0]
if task:
    assert task["status"] == "claimed"
    assert task["claim_token"]
    assert task["copy"]
    print(f"ITEM_ID={task['item_id']}")
    print(f"CLAIM_TOKEN={task['claim_token']!r}")
PY
)"

if [ -n "${ITEM_ID:-}" ]; then
  curl -fsS -X POST \
    -H "Authorization: Bearer $COPY_FACTORY_PUBLISH_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"item_id\":$ITEM_ID,\"claim_token\":\"$CLAIM_TOKEN\",\"status\":\"failed\",\"error\":\"test_dry_run\"}" \
    "$COPY_FACTORY_BASE_URL/api/publish/result"
fi
```

## Deployment

VPS can run as one Docker container:

```bash
docker compose up -d
```

`docker-compose.yml` starts `scripts/serve_with_sync.py`, which serves the website and runs upstream sync every 30 minutes. On Hostinger, Traefik reads the service's Docker labels and routes `https://hardness-content.hellopepper.work`; Traefik handles HTTPS certificates automatically after DNS points the hostname to the VPS IP.

Production secrets:

- `COPY_FACTORY_PASSWORD`
- `COPY_FACTORY_SESSION_SECRET`
- `COPY_FACTORY_PUBLISH_TOKEN` or `COPY_FACTORY_PUBLISH_TOKEN_FILE`
- `NEWS_HARNESS_EXPORT_TOKEN` or `NEWS_HARNESS_EXPORT_TOKEN_FILE`
- `DEEPSEEK_API_KEY` or `DEEPSEEK_API_KEY_FILE`
- `BRAVE_SEARCH_API_KEY` if automatic image candidates are enabled

## What Not To Build Yet

- No separate frontend deployment. The Python app serves HTML/CSS/JS already.
- No Mac mini publisher in this repo.
- No browser cookies on the VPS.
- No queue service until SQLite locking is actually insufficient.
- No separate gallery, similarity ranking, copyright workflow, or image moderation system. Image candidates are only a small fallback for drafts that arrive without upstream images.
