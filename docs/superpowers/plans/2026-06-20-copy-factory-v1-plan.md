# Copy Factory v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable single-user Copy Factory v1 with mock source sync, dedupe, Huajiao-style draft generation, review/edit UI, and deployment docs.

**Architecture:** A tiny Python standard-library web app with SQLite storage and cron-friendly sync script. Source adapters and writer harness are replaceable at clear function boundaries, but v1 ships only the code paths needed to run today.

**Tech Stack:** Python 3 standard library (`http.server`, `sqlite3`, `unittest`, `urllib`, `subprocess`), Makefile, Dockerfile.

---

## File Structure

- Create `app/config.py`: environment parsing and production safety checks.
- Create `app/db.py`: schema, dedupe, item queries, status saves.
- Create `app/adapters.py`: mock adapters and real adapter contract errors.
- Create `app/writer.py`: fake writer and DeepSeek script bridge.
- Create `app/sync.py`: fetch, dedupe, generate, persist.
- Create `app/web.py`: login, review pages, manual sync, save actions.
- Create `scripts/sync_once.py`: scheduler entrypoint.
- Create `tests/test_flow.py`: runnable end-to-end mock flow.
- Create `Makefile`: install/lint/typecheck/test/build/run/sync.
- Create `README.md`, `env.example`, `Dockerfile`.

## Task 1: Storage And Config

- [ ] Create `app/config.py` with env variables for auth, session, db path, sources, app env, and DeepSeek key presence.
- [ ] Create `app/db.py` with SQLite schema and dedupe insert by source identifiers/hash.
- [ ] Add a small self-check through `tests/test_flow.py` proving dedupe keeps one row.
- [ ] Run `make test`.

## Task 2: Adapters And Sync Loop

- [ ] Create mock Xueqiu and Reddit adapters returning deterministic finance/news items with media URLs.
- [ ] Add real adapter stubs for `xueqiu` and `reddit` that fail with clear messages.
- [ ] Create `app/sync.py` and `scripts/sync_once.py`.
- [ ] Extend the test to run one sync and assert raw items plus generated drafts exist.
- [ ] Run `make test`.

## Task 3: Writing Harness

- [ ] Create `app/writer.py` with deterministic fake writer for local/test.
- [ ] Add DeepSeek bridge using `DEEPSEEK_API_KEY` or `DEEPSEEK_API_KEY_FILE` and the existing huajiao script.
- [ ] Make production mode without a key fail clearly.
- [ ] Run `make test`.

## Task 4: Website

- [ ] Create `app/web.py` with login, logout, review list, item detail, save, and manual sync routes.
- [ ] Use native HTML forms and signed cookies.
- [ ] Extend the test with HTTP login, review visibility, edit save, and status assertion.
- [ ] Run `make test`.

## Task 5: Project Checks And Deployment Notes

- [ ] Create `Makefile`, `README.md`, `env.example`, and `Dockerfile`.
- [ ] Run `make install`, `make lint`, `make typecheck`, `make test`, and `make build`.
- [ ] Start the website locally.
- [ ] Run a mock sync and browser/HTTP edit-save proof.
- [ ] Report commands, URL, test account, key pages, and remaining source configuration.

## Self-Review

- Spec coverage: auth, adapters, 30-minute scheduler entry, dedupe, raw/media/batch/status/error persistence, writing harness, review pool, edit save, deployment docs, and verification are covered.
- Placeholder scan: no `TBD`, `TODO`, or undefined future tasks.
- Type consistency: functions and file names match the design.

## 2026-06-21 Publish Queue Addendum

- Add SQLite publish status fields to scheduled items.
- Add browser confirmation for approved scheduled items.
- Add publish API for queue listing, due-task claiming, and `published` / `failed` writeback.
- Keep Mac mini posting, X/Twitter login, browser cookies, and external publishing outside this repo.
