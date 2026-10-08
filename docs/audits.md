# Audit Log

How opengsync records who did what: which requests produce an audit line, what a line contains, where the files live, and how to query them with DuckDB.

- [Overview](#overview)
- [Where the files are](#where-the-files-are)
- [What triggers an audit line](#what-triggers-an-audit-line)
- [Record format](#record-format)
- [Audited routes](#audited-routes)
- [Querying with DuckDB](#querying-with-duckdb)
- [Limitations](#limitations)
- [Code](#code)

## Overview

Every HTTP request that **commits a database write** produces exactly one audit line, listing which tables and rows it inserted, updated or deleted. Nothing has to be added to a route for this; the write itself is detected on the SQLAlchemy session.

A few routes are audited **even though they don't write to the database**, because the action itself is security-relevant: login and the other auth routes, passkeys, and share-link access. These use an explicit `audit_log` (or `audit_share_access`) dependency.

Error responses (status ≥ 400) are always audited.

Workflows store intermediate steps in Redis, not in the database, so a multi-step workflow produces one audit line: the step that commits (usually the last one).

## Where the files are

| | Path |
|---|---|
| Inside the container | `/logs/audits/YYYY-MM-DD.jsonl` (`log_folder` in `opengsync.yaml`) |
| On the host | `${LOG_DIR}/opengsync/audits/YYYY-MM-DD.jsonl` |

- One file per day, one JSON object per line.
- At midnight the previous day's file is compressed to `YYYY-MM-DD.jsonl.gz`.
- Audit files are **never deleted** (the sink has no retention). Older files may still be `.jsonl.zip` from before the switch to gzip; DuckDB can't read those directly, so unzip them first.
- Audit lines are kept out of the normal `.log` and `.err` files.

## What triggers an audit line

A request is written to the audit log when any of these is true:

1. **It committed DB changes.** The request's session was committed (2xx response, no rollback requested) and the commit included at least one insert, update or delete.
2. **The route is explicitly audited** with `Depends(dependencies.audit_log)` or `Depends(dependencies.audit_share_access)`. Logged whatever the outcome, including failed logins.
3. **The response status is ≥ 400** (any route).

Not written:

- Read-only requests (GET pages, tables, searches) on routes without the explicit dependency.
- Form validation errors. `FormValidationException` returns 202 and rolls the session back, so nothing is committed.
- Requests whose transaction was rolled back (any non-2xx status, or `request.state.rollback = True`). Their `changes` are discarded with the rollback; if the status is ≥ 400 the line is still written, with `changes: []`.

**Share access is debounced.** On the share-link routes (the ones with `audit_share_access`), only the **first successful request per token and client IP** is written. It claims the Redis key `share-audit:{token}:{ip}` (`SET NX`), which lives until the token expires (at least 60 s). Every later successful request from that IP for that token is skipped, whatever the route or file: browsing, WebDAV, rclone and downloads all share the one key. So the log shows *that* an IP used a token and its first request, not every file it downloaded. This is unrelated to the share listing cache (`share-fs:*`); it is a separate Redis key used only for debouncing.

- Errors (≥ 400) are always written.
- A new IP for the same token gets its own first line.
- If Redis is unreachable, nothing is debounced and every request is written.
- Flushing Redis, or Redis evicting the key, starts the debounce over.

**Commit before response.** The session is committed before the response is sent. If the commit fails, the client gets a 500 instead of the original success response, and the audit line has `status_code: 500` and no changes.

## Record format

Each line is a flat JSON object. Two real examples, formatted here (on disk each is one line). An insider sharing a project's data:

```json
{
  "ts": "2026-10-08T11:03:21.461298+02:00",
  "user_id": 2,
  "method": "POST",
  "path": "/htmx/projects/1/share-data",
  "route": "/htmx/projects/{project_id}/share-data",
  "status_code": 204,
  "process_time": 0.0106,
  "resource_id": null,
  "metadata": {},
  "changes": [
    {"table": "project", "op": "update", "count": 1, "ids": [1], "fields": ["share_token", "share_token_uuid", "status"]},
    {"table": "share_path", "op": "insert", "count": 1, "ids": [1]},
    {"table": "share_token", "op": "insert", "count": 1, "ids": ["01a11ac0-bd71-76ea-afc2-fe5a966b92da"]}
  ],
  "query_params": {},
  "ip": "10.0.0.5",
  "agent": "Mozilla/5.0 ..."
}
```

Someone downloading a file through that kind of share link:

```json
{
  "ts": "2026-10-08T11:03:35.332668+02:00",
  "user_id": null,
  "method": "GET",
  "path": "/api/webdav/01a11ac0-f39f-77a3-b112-7fd9af5db6f9/shared/root.txt",
  "route": "/api/webdav/{token}/{subpath:path}",
  "status_code": 200,
  "process_time": 0.0026,
  "resource_id": "01a11ac0-f39f-77a3-b112-7fd9af5db6f9",
  "metadata": {"owner_id": 1, "path": "/api/webdav/01a11ac0-f39f-77a3-b112-7fd9af5db6f9/shared/root.txt"},
  "changes": [],
  "query_params": {},
  "ip": "198.51.100.12",
  "agent": "rclone/v1.68.0"
}
```

| Field | Meaning |
|---|---|
| `ts` | Time the line was written (ISO 8601 with offset). Cast with `ts::TIMESTAMPTZ`. |
| `user_id` | Authenticated user: the login cookie's user, or the owner of the `X-API-Token`. `null` for anonymous requests (share links, failed login, reset-by-link). Look up in `lims_user`. |
| `method`, `path` | HTTP method and actual URL path. |
| `route` | Route template, e.g. `/htmx/protocols/{protocol_id}/delete`. Group by this, not `path`. |
| `status_code` | Response status. 500 when the app raised or the commit failed. |
| `process_time` | Seconds spent handling the request (number). |
| `resource_id` | Only set by explicit audits; share access sets the token UUID. |
| `metadata` | Only set by explicit audits; share access sets `owner_id` and `path`. |
| `changes` | Committed DB changes, one entry per table and operation. Always present: `[]` when nothing was committed, i.e. on read-only explicit audits (share access, login page, failed login) and on errors. Explicitly audited routes that do write have it filled (e.g. passkey login updates `user_passkey`, reset password updates `lims_user`). |
| `query_params` | Query string as an object. |
| `ip` | `X-Real-IP` header, else the client address. `1.1.1.1` means unknown. |
| `agent` | User-Agent header. |

A `changes` entry:

| Field | Meaning |
|---|---|
| `table` | Table name (e.g. `lims_user`, `seq_request`, `library`, `sample_library_link`). |
| `op` | `insert`, `update` or `delete`. |
| `count` | Number of rows (exact). For bulk statements: number of statements. |
| `ids` | Primary keys, at most 100 (`count` stays exact). Integers, UUID strings, or lists for composite keys (in primary-key column order). Empty for bulk statements. |
| `fields` | For updates: names of the changed attributes. **Values are never logged**, so password hashes and personal data stay out of the log. Relationship attributes appear too (e.g. `features` when only a many-to-many link changed). |
| `bulk` | `true` when the write was a bulk `insert()`/`update()`/`delete()` statement rather than ORM objects. |

### How `changes` is recorded

All of it happens on the request's SQLAlchemy session (`request.state.db_session`, the one `dependencies.db_session` and `ctx.session` return), in `core/audit.py`:

1. **Flush** (`after_flush`): for every object the flush inserted, updated or deleted, the table name and primary key are added to a *pending* entry for `(table, op)`. For updates, the changed attributes are taken from SQLAlchemy's attribute history; objects whose history shows no change are skipped. Bulk `insert()`/`update()`/`delete()` statements sent through `session.execute` are caught by `do_orm_execute` and recorded with `bulk: true` and no ids.
2. **Commit** (`after_commit`): pending entries move to *committed*.
3. **Rollback** (`after_rollback`): pending entries are dropped; committed ones stay.
4. **End of request** (`DBSessionCleanupMiddleware`): the middleware commits (2xx and no rollback requested) or rolls back, then takes the committed entries (`audit.pop_changes`). Sets of fields become sorted lists; empty `fields` and `bulk: false` are left out.
5. **Writing**: the list is passed to loguru with the rest of the line, and the audit sink's formatter writes the line with `json.dumps(..., default=str)`. Integer ids stay numbers, UUIDs and anything else non-JSON become strings, and composite keys (tuples) become JSON lists.

A route that writes doesn't need to do anything; and nothing in `changes` comes from the route itself, so a route can't misreport what it wrote.

## Audited routes

The rule is what counts: **any request that commits a DB write is audited**. The lists below come from the code and from a full test run with every audit line recorded (`services/pytest`); a new route that writes is audited without being added here.

### Always audited (explicit dependency)

Logged on every request, whether or not anything is written, including GETs and failures.

| Area | Routes | Notes |
|---|---|---|
| Login, logout | `GET, POST /htmx/auth/login`, `POST /htmx/auth/logout` | Login: 204 = success, 202 = wrong credentials (form re-rendered), 429 = rate-limited. |
| Registration | `GET, POST /htmx/auth/register`, `GET, POST /htmx/auth/complete-registration/{token}` | |
| Passwords | `GET, POST /htmx/auth/change-password`, `GET, POST /htmx/auth/reset-password/{token}`, `POST /htmx/auth/{user_id}/reset-password` | `{user_id}/reset-password` emails a reset link (to yourself, or an admin for another user); the password itself changes in `reset-password/{token}`. |
| Admin user actions | `POST /htmx/auth/{user_id}/activate`, `POST /htmx/auth/{user_id}/start-user-session` | `activate`: an insider re-activates a deactivated user. `start-user-session`: an admin logs in as another user (`user_id` is the admin). |
| Passkeys | `POST /api/passkeys/register/{options,verify}`, `POST /api/passkeys/login/{options,verify}`, `GET /htmx/passkeys/list`, `DELETE /htmx/passkeys/{passkey_id}` | |
| Share-link access | `/api/shares/{browse,rclone,rclone_script,validate}/{token}/...`, `/api/webdav/{token}/...` (all WebDAV methods), `/files/share/browse/{token}/...` | `resource_id` = token UUID, `metadata.owner_id` = token owner. Only the first successful request per token and IP is written (see [debouncing](#what-triggers-an-audit-line)). Anonymous (`user_id` is `null`). |

### Audited when they write

#### Workflows

Intermediate steps (select samples, parse/upload a table, barcode input and match, mapping steps) keep their state in Redis and write nothing, so they produce no line. The step that commits does:

| Workflow | Step that writes | Changes seen in tests |
|---|---|---|
| Library annotation (SAS) | `POST /htmx/workflows/library-annotation/{seq_request_id}/complete-s-a-s` | `library`, `sample`, `sample_library_link`, `pool`, `project`, `library_index`, `feature`, `library_feature_link`, `contact`, `comment`, `seq_request` |
| Library pooling | `POST /htmx/workflows/library-pooling/complete-library-pooling` | — |
| Index check | `POST /htmx/workflows/index-check/complete-index-check` | `library_index`, `seq_request` (`review_checklist`) |
| Lane QC | `POST /htmx/workflows/lane-qc/q-c-lanes`, `POST /htmx/workflows/lane-qc/unified-q-c-lanes` | `lane` |
| Reindex | `POST /htmx/workflows/reindex/complete-reindex` | `library`, `library_index`, `comment` |
| Relib | `POST /htmx/workflows/relib/library-edit-table` | `library` |
| Split project | `POST /htmx/workflows/split-project/confirm-split` | `project`, `sample` |
| Merge pools | `POST /htmx/workflows/merge-pools/merge-pools` | — |
| Mux prep | `POST /htmx/workflows/mux-prep/{flex-mux,flex-a-b-c,oligo-mux,o-c-m-mux}` | — |
| Library remux | `POST /htmx/workflows/library-remux/{flex-re-mux,oligo-re-mux}` | — |
| Select library protocols | `POST /htmx/workflows/select-library-protocols/library-protocol-select` | — (sets `library.protocol_id`) |
| Qubit measure | `POST /htmx/workflows/qubit-measure/qubit-measure` | — |
| BA report | `POST /htmx/workflows/ba-report/complete-b-a-report` (or `b-a-report` when it finishes directly) | — (stores a `media_file`) |
| Add kits to protocol | `POST /htmx/workflows/{protocol_id}/add-kits` | — |

`—`: the step isn't covered by the test suite, so no changes were recorded for this list. It's still audited when it writes.

#### Actions

| Action | Route |
|---|---|
| Share project data | `POST /htmx/projects/{project_id}/share-data` (creates `share_token`, `share_path`) |
| Share directory | `POST /htmx/files/share-directory` |
| Merge projects | `POST /htmx/projects/merge-projects` |
| Edit sample attributes | `POST /htmx/projects/{project_id}/edit-sample-attributes` |
| Add project assignee | `POST /htmx/projects/add-assignee/{project_id}`, `POST /htmx/projects/{project_id}/add-assignee` |
| Submit seq request | `POST /htmx/seq_requests/{seq_request_id}/submit` |
| Process seq request (accept/reject) | `POST /htmx/seq_requests/{seq_request_id}/process-request` |
| Seq request assignee / share email | `POST /htmx/seq_requests/{seq_request_id}/add-assignee`, `.../self-assign`, `.../share-email` |
| Store samples | `POST /htmx/actions/store-samples-action` |
| Library prep, sample pooling | `POST /htmx/actions/library-prep/{lab_prep_id}`, `POST /htmx/actions/sample-pooling/{lab_prep_id}` |
| Upload prep table | `POST /htmx/lab_preps/upload-prep-table/{lab_prep_id}` |
| Select pool libraries | `POST /htmx/actions/select-pool-libraries/{pool_id}` |
| Re-sequence | `POST /htmx/actions/reseq-action`, `POST /htmx/seq_requests/{seq_request_id}/reseq-library/{library_id}` |
| Edit library properties / features | `POST /htmx/actions/edit-library-properties-action`, `POST /htmx/libraries/{library_id}/edit-features` |
| Experiment: select pools, cycles, dilutions | `POST /htmx/experiments/{experiment_id}/select-pools`, `.../cycles`, `POST /htmx/experiments/{experiment_id}` (dilute pools) |
| Experiment: lane pools, distribute reads, load flow cell | `POST /htmx/experiments/{experiment_id}/{lane-pools,distribute-reads,load-flow-cell}/{combined,separate}` |
| Sequencer loading checklist | `POST /htmx/experiments/{experiment_id}/sequencer-loading-checklist` (stores a `media_file`) |
| Kits: edit features / barcodes | `POST /htmx/kits/{feature_kit_id}/edit-features`, `POST /htmx/index_kits/{index_kit_id}/edit-barcodes` |
| Group membership | `POST /htmx/groups/{group_id}/add-user`, `DELETE .../remove-user/{user_id}`, `POST .../make-owner/{user_id}` |
| Associate data path | `POST /htmx/files/associate-path` |

Read-only actions (`check-barcode-constraints`, `query-barcode-sequences`, `select-samples` of the barcode clash check, billing export, plots) don't write and aren't audited.

#### Create / edit forms

`POST .../create` and `POST .../{id}/edit` of: projects, seq requests, samples, libraries, pools (also `.../clone`), experiments, lab preps, protocols, kits, index kits, feature kits, sequencers, seq runs, groups, users, pool designs, flow cell designs, comments and TODO comments; file upload (`POST /htmx/files/upload`); API token creation (`POST /htmx/users/{user_id}/create-api-token`).

The seq request form's intermediate `.../step` posts don't write.

#### Delete, archive and other state changes

- **Delete:** `DELETE` on `/htmx/{projects,seq_requests,samples,pools,experiments,lab_preps,sequencers,protocols}/{id}/delete`, `/htmx/kits/delete`, `/htmx/files/{media_file_id}/delete`, `/htmx/comments/delete`, flow cell and pool designs.
- **Archive / complete:** `/htmx/projects/{project_id}/{archive,unarchive,complete}`, `/htmx/seq_requests/{seq_request_id}/{archive,unarchive,clone}`, `/htmx/lab_preps/{lab_prep_id}/{complete,uncomplete}`, flow cell design archive.
- **Remove links:** `remove-library`, `remove-libraries`, `remove-sample`, `remove-assignee`, `remove-pool`, `lane-pool`, `remove-kit`, `remove-kit-combination`, `remove-data_path`, `remove-share-email`, `remove-auth-form`, `delete-file`.
- **Review checklist:** `/htmx/seq_requests/{seq_request_id}/{review-check,review-uncheck}/{step}`.
- **API tokens:** `POST /htmx/api-tokens/{token_id}/deactivate`.

#### JSON API (`/api`)

`POST /api/libraries/add-qc`, `DELETE /api/libraries/delete-qc`, `POST /api/projects/add-software`, `DELETE /api/projects/delete-software`, `POST /api/stats/set-library-lane-reads`, `POST /api/shares/add-data_path`, `DELETE /api/shares/remove-data_paths`, `POST /api/shares/release-project_data`. API calls authenticate with `X-API-Token`; `user_id` is the token's owner.

## Querying with DuckDB

Run DuckDB (the `duckdb` CLI or the `duckdb` Python package) from the repository root, or adjust the paths. DuckDB reads `.jsonl` and `.jsonl.gz` directly; unzip any old `.jsonl.zip` files first.

### From Python

`pip install duckdb pandas`. Save the [Setup](#setup) SQL below as `audit_setup.sql`, then:

```python
from pathlib import Path

import duckdb

con = duckdb.connect()  # in-memory; duckdb.connect("audits.duckdb") keeps the views between sessions
con.execute(Path("audit_setup.sql").read_text())  # creates the `audit` and `audit_changes` views

# any query as a pandas DataFrame (.pl() for polars, .fetchall() for a list of tuples)
df = con.sql("""
    SELECT ts, user_id, method, route, status_code, changes
    FROM audit
    WHERE ts >= now() - INTERVAL 7 DAY
    ORDER BY ts DESC
""").df()

# pass values as parameters instead of formatting them into the SQL string
token = "01a11ac0-f39f-77a3-b112-7fd9af5db6f9"
accesses = con.execute(
    "SELECT ts, ip, agent, path, status_code FROM audit WHERE resource_id = ? ORDER BY ts",
    [token],
).df()

password_changes = con.execute(
    "SELECT ts, user_id, route, ids, fields FROM audit_changes WHERE tbl = ? AND list_contains(fields, ?)",
    ["lims_user", "password"],
).df()
```

In the DataFrame, `ts` is a timezone-aware datetime, `user_id` a nullable integer, `changes` a list of dicts, and `fields` an array of strings. `ids` elements are JSON text (`'1'`, `'"01a1..."'`); use `json.loads` on them, or select `list_transform(ids, x -> x::BIGINT)` in SQL when the table has integer ids. Every SQL example below works the same way with `con.sql(...)`.

### Setup

Declaring the columns keeps the types stable across files: `ids` can be integers, UUID strings or composite-key lists, and fields missing from a line become `NULL`. Lines written before the flat format (loguru's nested `{"text": ..., "record": ...}`) come back with every column `NULL`; the `WHERE` drops them.

```sql
CREATE OR REPLACE VIEW audit AS
SELECT * FROM read_json(
    ['logs/opengsync/audits/*.jsonl', 'logs/opengsync/audits/*.jsonl.gz'],
    format = 'newline_delimited',
    columns = {
        ts: 'TIMESTAMPTZ',
        user_id: 'BIGINT',
        method: 'VARCHAR',
        path: 'VARCHAR',
        route: 'VARCHAR',
        status_code: 'INTEGER',
        process_time: 'DOUBLE',
        resource_id: 'VARCHAR',
        metadata: 'JSON',
        changes: 'STRUCT("table" VARCHAR, op VARCHAR, count BIGINT, ids JSON[], fields VARCHAR[], bulk BOOLEAN)[]',
        query_params: 'JSON',
        ip: 'VARCHAR',
        agent: 'VARCHAR'
    }
)
WHERE ts IS NOT NULL;

-- one row per (request, table, op)
CREATE OR REPLACE VIEW audit_changes AS
SELECT a.* EXCLUDE (changes), c."table" AS tbl, c.op, c.count, c.ids, c.fields, coalesce(c.bulk, false) AS bulk
FROM audit a, unnest(a.changes) AS t(c);
```

To keep the views, start DuckDB with a database file (`duckdb audits.duckdb`) instead of in-memory.

### Who completed a workflow or action

Who completed the library annotation for seq request 42:

```sql
SELECT ts, user_id, status_code
FROM audit
WHERE route = '/htmx/workflows/library-annotation/{seq_request_id}/complete-s-a-s'
  AND path = '/htmx/workflows/library-annotation/42/complete-s-a-s'
  AND status_code < 300
ORDER BY ts;
```

Who shared project data, how often, and when last (swap the route for any action in [Audited routes](#audited-routes)):

```sql
SELECT user_id, count(*) AS n, max(ts) AS last
FROM audit
WHERE route = '/htmx/projects/{project_id}/share-data'
  AND status_code < 300
GROUP BY ALL ORDER BY last DESC;
```

### Who changed a password this week

Matches every route that changes `lims_user.password`: change password, reset by link, and anything else. `changed_by` is `NULL` for a reset by link (nobody is logged in); `users_changed` is whose password changed.

```sql
SELECT ts, user_id AS changed_by, ids AS users_changed, route
FROM audit_changes
WHERE tbl = 'lims_user' AND op = 'update' AND list_contains(fields, 'password')
  AND ts >= date_trunc('week', now())
ORDER BY ts;
```

### Who accessed data through a share token

Every access to one token (one line per client IP while the token is valid, plus every error):

```sql
SELECT ts, ip, agent, method, path, status_code, metadata->>'owner_id' AS owner_id
FROM audit
WHERE resource_id = '01a11ac0-f39f-77a3-b112-7fd9af5db6f9'
ORDER BY ts;
```

All tokens, with how many distinct IPs used them:

```sql
SELECT resource_id AS token, count(DISTINCT ip) AS ips, min(ts) AS first_access, max(ts) AS last_access
FROM audit
WHERE resource_id IS NOT NULL
GROUP BY ALL ORDER BY last_access DESC;
```

Who created the token (the share actions insert into `share_token`; the id is the token UUID):

```sql
SELECT ts, user_id, route
FROM audit_changes
WHERE tbl = 'share_token' AND op = 'insert'
  AND list_contains(ids, '"01a11ac0-f39f-77a3-b112-7fd9af5db6f9"'::JSON);
```

### History of one row

Everything that touched seq request 42 (integer ids are matched as JSON, `'42'::JSON`; UUIDs as `'"<uuid>"'::JSON`):

```sql
SELECT ts, user_id, route, op, fields
FROM audit_changes
WHERE tbl = 'seq_request' AND list_contains(ids, '42'::JSON)
ORDER BY ts;
```

`ids` holds at most 100 ids per table and operation, so a row touched by a very large batch may be missing; check `count` against `len(ids)`.

### Deletes

```sql
SELECT ts, user_id, route, tbl, count, ids
FROM audit_changes
WHERE op = 'delete'
ORDER BY ts DESC;
```

### Everything one user did on a day

```sql
SELECT ts, method, route, status_code, list_transform(changes, c -> c."table" || ':' || c.op) AS changed
FROM audit
WHERE user_id = 12 AND ts::DATE = DATE '2026-10-08'
ORDER BY ts;
```

### Failed logins per IP, last 24 hours

202 = wrong credentials, 429 = rate-limited.

```sql
SELECT ip, count(*) AS failed, min(ts) AS first, max(ts) AS last
FROM audit
WHERE route = '/htmx/auth/login' AND method = 'POST' AND status_code IN (202, 429)
  AND ts >= now() - INTERVAL 1 DAY
GROUP BY ip ORDER BY failed DESC;
```

### Errors and slow writes

```sql
SELECT route, status_code, count(*) AS n
FROM audit
WHERE status_code >= 400
GROUP BY ALL ORDER BY n DESC;

SELECT route, count(*) AS n, round(median(process_time), 3) AS p50, round(max(process_time), 3) AS max
FROM audit
WHERE len(changes) > 0
GROUP BY route ORDER BY p50 DESC;
```

### Names instead of user ids

Attach the database read-only with DuckDB's `postgres` extension. Fill in `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` from `.env`; the database port must be reachable from where DuckDB runs.

```sql
INSTALL postgres; LOAD postgres;
ATTACH 'host=<POSTGRES_HOST> port=<POSTGRES_PORT> dbname=<POSTGRES_DB> user=<POSTGRES_USER> password=<POSTGRES_PASSWORD>'
    AS pg (TYPE postgres, READ_ONLY);

SELECT a.ts, u.email, a.route, a.status_code
FROM audit a
LEFT JOIN pg.public.lims_user u ON u.id = a.user_id
ORDER BY a.ts DESC
LIMIT 50;
```

### Export

```sql
COPY (SELECT * FROM audit WHERE ts >= now() - INTERVAL 30 DAY) TO 'audit_30d.parquet' (FORMAT parquet);
```

## Limitations

What a line says is reliable: every entry in `changes` was flushed by the ORM and then committed. But the log is not a complete or tamper-proof record. Things it can miss or get slightly wrong:

**Writes that bypass the request session**

- **Cascade deletes in SQLAlchemy listeners.** `opengsync_db/core/listeners.py` deletes orphaned samples and features, and a deleted request's external pools, directly on the connection. The parent delete is logged; the orphans aren't.
- **Database-level cascades and triggers** (`ON DELETE CASCADE`): only the row the app deleted is listed.
- **Raw SQL.** `sa.text("UPDATE ...")` through `session.execute`, or anything run on `session.connection()`, isn't recognised as a write. No route does this today.
- **Other sessions.** Taskiq/background jobs (`taskiq_session`), any session opened with `db_handler.get_session()` outside the request, `psql` and Alembic migrations aren't audited.

**Precision of `changes`**

- **No values.** Only which rows and columns changed, not old or new values. For row history, use Postgres triggers or the DB backups.
- **`fields` can over-report.** If an attribute was set while not loaded (or expired), SQLAlchemy can't compare it, so it's listed even if the new value equals the old one.
- **`ids` are capped at 100** per table and operation; `count` stays exact.
- **Savepoints.** Changes inside a rolled-back `begin_nested()` savepoint would still be listed. No route uses savepoints today.
- **Non-DB side effects** (emails, files written to disk) only appear if the route also writes to the DB or is explicitly audited.

**Delivery and integrity**

- **Written after the commit, not in the same transaction.** If the process dies between the commit and the log write, the change is in the DB but not in the log. A failing log write is logged as an error and doesn't fail the request.
- **Plain files.** Anyone who can write to the log folder can edit or delete lines; there's no signing or hash chain. If the log must hold up in an investigation, ship it to append-only storage (e.g. a remote syslog or object storage with retention lock).
- **Share access is debounced** (see [above](#what-triggers-an-audit-line)): the log shows the first request per token and IP, not every download.
- **3xx responses roll back.** The session is only committed on 2xx; a route that writes and then returns a plain redirect would lose its changes (htmx routes redirect with 204 + `HX-Redirect`, which is fine).
- **`ts` is when the line was written**, after the response; it can be a few ms after the commit.

## Code

| What | Where |
|---|---|
| Change tracking (`after_flush`, `do_orm_execute`, `after_rollback` listeners), `IGNORED_TABLES` | `services/backend/server/core/audit.py` |
| Commit, rollback, writing the audit line | `DBSessionCleanupMiddleware` and `_write_audit_log` in `services/backend/server/core/middleware.py` |
| Explicit audit dependencies | `audit_log`, `audit_share_access` in `services/backend/server/core/dependencies.py` |
| `user_id` attribution | `get_user_id` stores the authenticated id on `request.state.user_id` (cookie or API token), in `services/backend/server/core/dependencies.py` |
| File sink, JSON format, rotation | `_audit_format` and the `audits/` sink in `services/backend/server/core/lifespan.py` |
| Share-access debounce | `claim_share_audit` in `services/backend/server/utils/share_fs_cache.py` |
| Tests | `services/pytest/tests/server/test_audit_log.py` |

To audit a route that doesn't write to the DB, add `Depends(dependencies.audit_log)`. To attach context, take the returned `AuditLogger` and set `resource_id` and `metadata`. To stop a noisy table from producing audit lines on its own, add it to `IGNORED_TABLES` in `audit.py`.
