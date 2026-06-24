# Mac Mini Downstream Publisher Handoff

This spec is for the next Codex session that will build the downstream publisher on the Mac mini.

## Current Decision

Do not use Codex automation for scheduling.

Use a Mac mini local worker instead:

```text
launchd or local scheduler
  -> starts one Codex/Chrome publish pass
  -> Copy Factory claim_due
  -> Chrome control publishes through logged-in browser
  -> Copy Factory publish/result
```

Reason: frequent Codex automation wakeups would spend automation quota. The Mac mini can do local scheduling without using that quota.

## System Boundary

Copy Factory VPS owns:

- upstream sync
- rewrite/generation
- review decisions
- schedule decisions
- publish queue state
- atomic task claiming
- result storage

Mac mini downstream owns:

- keeping the target social account logged in
- waking locally on a schedule
- claiming due tasks
- using Chrome control to publish
- writing publish success or failure back to Copy Factory

Mac mini must not:

- crawl News Harness
- choose content on its own
- bypass `claim_due`
- store Copy Factory queue state locally except transient runtime state
- decide whether `scheduled_at` is due
- inspect browser cookies directly

## Copy Factory API

Base URL:

```text
https://hardness-content.hellopepper.work
```

Auth header:

```http
Authorization: Bearer <COPY_FACTORY_PUBLISH_TOKEN>
```

Token source:

- On VPS: `COPY_FACTORY_PUBLISH_TOKEN` or `COPY_FACTORY_PUBLISH_TOKEN_FILE`
- On Mac mini: store the same token as a local secret/env var

Never commit the token.

## Endpoints

### Queue Read

Use for diagnostics only:

```http
GET /api/publish/queue
```

Expected response:

```json
{
  "tasks": []
}
```

This includes confirmed, claimed, published, and failed items. Do not use it to decide what to publish.

### Claim Due

Use this as the real work source:

```http
POST /api/publish/claim_due
Content-Type: application/json

{"limit":1}
```

Expected response:

```json
{
  "tasks": [
    {
      "item_id": 123,
      "scheduled_at": "2026-06-22T09:00:00.000Z",
      "status": "claimed",
      "copy": "final approved copy",
      "source": "xueqiu_hot",
      "source_id": "upstream-id",
      "source_url": "https://example.com/source",
      "title": "source title",
      "media_urls": ["https://example.com/image.jpg"],
      "selected_media_url": "https://example.com/image.jpg",
      "claim_token": "server-generated-lock-token",
      "confirmed_at": "2026-06-22T08:50:00Z",
      "claimed_at": "2026-06-22T09:00:01Z",
      "result_at": "",
      "error": ""
    }
  ]
}
```

If no task is due:

```json
{"tasks":[]}
```

Contract guarantees:

- Every returned task is `confirmed`.
- Every returned task is due by the Copy Factory server clock.
- Published, failed, and unexpired claimed tasks are never returned.
- Browser-side cancellations or reschedules remove tasks from future claim responses until they are confirmed again.
- A claimed task that misses the server claim TTL is released back to `confirmed` and can be claimed again.

The Mac mini should not re-check `scheduled_at`. If the server returns a task, publish it or release/fail it.

### Browser Cancellation Boundary

Copy Factory operators can cancel confirmation, unschedule, or reschedule a task while it is still `confirmed`.

The downstream worker does not need a cancel endpoint. It must only trust `POST /api/publish/claim_due`; if a human cancels before the scheduled time, the task simply will not be returned. Once a task is `claimed`, ordinary browser cancellation is blocked and the worker owns the next transition: `published`, `failed`, or explicit `release`.

### Release Claim

Use this when preflight passes claim but the worker then discovers it cannot publish safely:

```http
POST /api/publish/release
Content-Type: application/json

{"item_id":123,"claim_token":"...","reason":"chrome_unavailable"}
```

`claim_token` is mandatory. A stale or mismatched token returns `409`.

### Result Writeback

Success:

```http
POST /api/publish/result
Content-Type: application/json

{"item_id":123,"claim_token":"...","status":"published"}
```

Failure:

```http
POST /api/publish/result
Content-Type: application/json

{"item_id":123,"claim_token":"...","status":"failed","error":"compose_box_missing"}
```

`claim_token` is mandatory. It prevents a stale worker from writing to the wrong task.

## Worker Loop

Build the smallest loop first:

```text
start
  -> preflight Chrome/opencli health
  -> unhealthy: exit 0 without claiming
  -> POST claim_due limit=1
  -> no tasks: exit 0
  -> one task: publish through Chrome
  -> success: POST result published
  -> cannot safely publish before submit: POST release
  -> submit attempted but failed/uncertain: POST result failed
  -> exit
```

Do not build a long-running daemon for v1.

Local scheduling can call this one-shot worker every minute. Missed runs self-heal on the next minute.

## Local Scheduling

Use Mac mini local scheduling, not Codex automation.

Recommended v1:

- `launchd` runs once per minute
- worker exits quickly when no due tasks exist
- one task per run

This keeps the browser interaction small and debuggable.

## Chrome Control Requirements

The publisher depends on an existing logged-in Chrome session on the Mac mini.

The downstream Codex session should use `chrome:control-chrome` when it needs browser control.

The worker should:

- run preflight before claiming
- claim or open the target posting page
- verify login state from visible UI
- paste `copy`
- attach media if available
- submit
- verify visible success
- write result back

The worker should not:

- read cookies
- export browser profile data
- attempt password recovery
- publish if login state is unclear
- keep a permanent processed-items cache for Copy Factory tasks
- skip tasks because local time thinks they are not due

## Media Handling

Use media in this order:

1. `selected_media_url`
2. first usable item from `media_urls`
3. no media

If media upload fails, mark the task as failed unless the product owner explicitly accepts text-only fallback.

For v1, do not cache images permanently. Temporary downloads are fine.

## Failure Codes

Use short strings:

- `not_logged_in`
- `claim_failed`
- `compose_box_missing`
- `copy_paste_failed`
- `media_download_failed`
- `media_upload_failed`
- `submit_not_confirmed`
- `unexpected_error`

Put extra detail after the code if useful:

```json
{"status":"failed","error":"media_upload_failed: upload button disabled"}
```

## Safety Rules

- Claim only one task at a time.
- Never publish a task without a fresh `claim_token`.
- Release the claim if the worker cannot publish safely before attempting submission.
- Write `failed` after claiming if submission was attempted but failed or is uncertain.
- If unsure whether a post was submitted, do not retry blindly. Mark `failed` with `submit_not_confirmed`.
- Do not run two local workers at once.

For v1, rely on launchd not overlapping plus `claim_due` locking. Add a local lockfile only if overlap actually happens.

## Suggested File Layout For Downstream Repo

Keep it small:

```text
mac-mini-publisher/
  README.md
  publisher.py
  launchd/com.copyfactory.publisher.plist
  .env.example
```

`publisher.py` should own:

- API calls
- one-shot worker flow
- calling into the Codex/Chrome-control publishing step

The Chrome-control step can start as a runbook-driven Codex task before being hardened.

## Environment Variables

Required:

```text
COPY_FACTORY_BASE_URL=https://hardness-content.hellopepper.work
COPY_FACTORY_PUBLISH_TOKEN=...
PUBLISH_TARGET_URL=...
```

Optional:

```text
COPY_FACTORY_CLAIM_LIMIT=1
PUBLISH_DRY_RUN=0
```

`PUBLISH_DRY_RUN=1` may claim then immediately write `failed` in early tests, or skip claiming and only print queue diagnostics. Pick one behavior and document it before running.

## First Test Plan

1. Confirm Copy Factory has at least one approved, scheduled, confirmed item.
2. Run `GET /api/publish/queue` with bearer token.
3. Run `POST /api/publish/claim_due` with `{"limit":1}`.
4. Confirm response includes `claim_token`, `copy`, `scheduled_at`.
5. Do not publish externally on the first run.
6. Write back `failed` with `error=test_dry_run`.
7. Confirm Copy Factory shows the item as failed.
8. Reconfirm or reschedule that item from the UI before real publishing.

## Real Publish Acceptance Criteria

The downstream is ready when:

- a due task can be claimed
- Chrome-control can reach the posting UI
- text can be inserted exactly once
- media can be attached when present
- submit success can be verified visibly
- `published` is written back with the right `claim_token`
- failure writes `failed` instead of leaving tasks stuck as `claimed`

## Handoff Prompt For New Codex Session

Use this prompt in the downstream session:

```text
You are building the Mac mini downstream publisher for Copy Factory.

Read docs/mac-mini-downstream-handoff.md first.

Goal:
Create a local one-shot worker that claims one due task from Copy Factory, publishes it through the existing logged-in Chrome session using chrome:control-chrome, then writes published/failed back to Copy Factory.

Do not use Codex automation. Scheduling should be Mac mini local scheduling, preferably launchd.

API:
Base URL: https://hardness-content.hellopepper.work
Auth: Authorization: Bearer <COPY_FACTORY_PUBLISH_TOKEN>
Claim: POST /api/publish/claim_due {"limit":1}
Result: POST /api/publish/result

Safety:
Claim one task at a time.
Never publish without claim_token.
If anything is uncertain after claiming, write failed with a short error code.
Do not inspect cookies or move browser login state.

First deliverable:
publisher.py + .env.example + launchd plist + README with dry-run instructions.
```

## What Not To Build Yet

- no Codex automation
- no multi-account routing
- no multi-platform fan-out
- no retries beyond the next scheduled run
- no permanent image cache
- no external database
- no daemon supervisor

Build the tiny loop first. Let reality earn the next feature.
