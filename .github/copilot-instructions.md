# InstaTrack • Copilot instructions

## Project snapshot
- `main.py` is the single CLI entrypoint; subcommands (`run`, `report`, `web`, `schedule`) all compose `TrackerService` and `ReportService` instances.
- Business code lives in `services/`, shared helpers in `utils/`, Flask assets under `web/`, and configuration in `config/settings.py` (loads `.env`, ensures `data/cache` & `data/logs`).
- User-facing strings are in French—keep translations consistent when adding CLI or web copy.

## Runtime expectations
- Always hydrate settings via `from config.settings import settings`; it lazily loads `.env` from repo root and ensures required directories exist.
- Instagram access must go through `utils/insta_client.InstaClient`, which manages session persistence at `data/cache/insta_session.json`, retries, and `INSTAGRAM_SESSIONID` overrides.
- MongoDB access is abstracted by `utils.storage.MongoStorage`; it auto-falls back to `mongomock` when `USE_MOCK_DB=1` or a connection fails.

## Core services & flow
- `TrackerService.run_once()` iterates `settings.target_accounts`, fetches followers/following, diffs them with `utils.comparer.diff_users`, stores snapshots, and emits change docs.
- Extend collection logic by hooking into `_process_list` or injecting a custom `InstaClient`/`MongoStorage`; avoid bypassing those layers.
- `ReportService` is the read side; CLI, APIs, and templates expect its return shapes (ISO 8601 strings, keys like `followers_net`, `top_new_followers`).

## Reporting layer
- Date handling relies on `_resolve_range`, `_parse_date`, and `_iso_or_none` to keep everything timezone-aware (UTC). Respect these helpers when adding new filters.
- Bulk exports reuse `recent_changes` + `csv.DictWriter` with the fixed field list (`detected_at`, `target_account`, `list_type`, `change_type`, `username`, `full_name`).
- Snapshot comparisons (`compare_snapshots`) return sorted, truncated lists; dashboard depends on keys such as `added_total`, `removed_total`, `baseline`.

## Web dashboard
- `web/app.py` wires Flask routes to `ReportService`; HTML lives in `web/templates/dashboard.html`, JS charts in `web/static/js/chart.js`.
- REST endpoints: `/api/snapshot` triggers `TrackerService.run_once`, `/api/report` aggregates metrics, `/api/changes|daily|snapshots` provide JSON feeds, `/export.csv` streams CSV.
- When changing payloads, update both the Flask JSON responses and the front-end code that consumes them.

## Scheduling & automation
- The scheduler is `utils.scheduler.TrackerScheduler`, configured via `settings.scrape_time` (UTC). `python main.py schedule` blocks on an APScheduler background job.
- `_get_scheduler` in `web/app.py` caches a singleton; guard against multiple scheduler instances when extending scheduling APIs.

## Data & storage
- Mongo collections: `snapshots` for full follower/following lists, `changes` for events with embedded `user` dicts and `detected_at` timestamps.
- `MongoStorage` configures indexes (`snapshot_lookup`, `changes_lookup`) and exposes helpers (`latest_snapshot`, `snapshot_history`, `snapshot_at`, `changes_since`). Use them instead of raw pymongo calls.

## Configuration knobs
- Required env vars: `TARGET_ACCOUNTS`, Instagram credentials (`INSTAGRAM_USERNAME`/`PASSWORD` or `INSTAGRAM_SESSIONID`), optional Mongo overrides (`MONGO_URI`, `MONGO_DB_NAME`).
- Rate limiting & retries are tunable via `MIN_REQUEST_DELAY`, `MAX_REQUEST_DELAY`, `MAX_RETRIES`, `RETRY_BACKOFF_SECONDS`.
- Logging level and output path come from `LOG_LEVEL`, `LOG_DIR`; logs rotate via `utils.logger` and accumulate in `data/logs/instatrack.log`.

## Testing & dev workflow
- Run `pytest` with `USE_MOCK_DB=1` (tests set this automatically). They rely on `mongomock` and cover diffing, storage queries, tracker orchestration, and report calculations.
- For manual smoke tests, use `python main.py run` (console JSON) or `python main.py web --debug` and hit `/api/report`.

## Usage patterns & gotchas
- All service methods assume timezone-aware `datetime` objects; convert naive timestamps before storing.
- Keep change events small—`ReportService.recent_changes` and dashboard routes expect `user` dicts to only expose `pk`, `username`, `full_name`.
- When adding new CLI options, register them in `_build_parser` and thread them through `ReportService`/`TrackerService` instead of reaching into lower layers directly.
