# File Sharing

How opengsync shares files from the share mount with external collaborators through share links: what a link exposes, how to hide files with `.ngsignore`, how downloads are served, and where caching makes things look out of date.

- [Overview](#overview)
- [Access routes](#access-routes)
- [Setting up the share mount](#setting-up-the-share-mount)
- [What a share link exposes](#what-a-share-link-exposes)
- [Hidden files](#hidden-files)
- [How downloads are served](#how-downloads-are-served)
- [Caching](#caching)
- [Sharing with the OpeNGSyncAPI](#sharing-with-the-opengsyncapi)
- [Known quirks](#known-quirks)
- [Code](#code)
- [Security](#security)

## Overview

A **share token** (a share link) is a UUID with an expiry time and a list of **share paths**. Each share path is a file or a folder, relative to the share root (`share_root` in `opengsync.yaml`, `/share` inside the containers). Anyone who has the token can list and download everything those paths expose, without logging in, until the token expires.

Insiders create share tokens in three ways:

| How | What gets shared | Notes |
|---|---|---|
| Project page → **Share Data** | All data paths linked to the project | Emails the recipients. Expires the project's previous token. |
| Insider file browser → **Share directory** | One folder | Emails a browse link. Valid for 24 hours to 1 month (default 2 weeks). Not tied to a project. |
| API `release_project_data` | All data paths linked to the project | Same as **Share Data**. See [Sharing with the OpeNGSyncAPI](#sharing-with-the-opengsyncapi). |

A token's paths are fixed when it is created. Linking more data paths to a project later does not change an existing token; share the project again to get a new one.

## Access routes

| Route | Typical client | What it does |
|---|---|---|
| `/api/webdav/{token}/{path}` | `rclone` (WebDAV), `rclone mount`, Finder, Windows Explorer | Read-only WebDAV: `GET`, `HEAD`, `PROPFIND`, `OPTIONS`. `LOCK`/`UNLOCK` return 204 and do nothing. |
| `/api/shares/browse/{token}/{path}` | The link in share emails | Simple HTML listing; a file path downloads the file. |
| `/files/share/browse/{token}/{path}` | Browser | The shared file browser (paginated, sortable); a file path downloads the file. |
| `/api/shares/rclone/{token}/{path}` | `rclone --http-url`, `wget --recursive` | Plain HTML index for recursive download tools; a file path downloads the file. |
| `/api/shares/rclone_script/{token}` | | The `rclone copy` command, as text. |
| `/api/shares/validate/{token}` | | `OK` if valid. |

Every route answers **404** for an unknown token and **403** for an expired one.

The download commands in share emails are rendered from `services/backend/templates/snippets/*.j2`, for example:

```sh
rclone copy ":webdav,url='https://<host>/api/webdav/<token>':/" BSF_DATA \
    --progress --transfers=8 --checkers=16 --use-server-modtime --verbose
```

**Rate limits** are counted per client IP and route: 20 requests per minute on the public `/api/shares/…` routes and on `/files/share/browse/…`, and 200 per minute plus 5000 per hour on WebDAV. A request with a valid token resets its counter, so in practice only requests with unknown or expired tokens count. The limits exist to stop token guessing.

**Audit:** every share-link access is written to the audit log, with a cooldown per token and client IP (see [Audit log](#audit-log)).

## Setting up the share mount

Three settings must agree:

1. `share_root` in `opengsync.yaml`, normally `"/share"`.
2. `compose.override.yaml` on the production host mounts the host folders under `/share`. They must be mounted into **both** `opengsync-app` and `nginx`, at the **same container paths**, read-only. The app checks each request, and nginx then reads the file from the same path (see [How downloads are served](#how-downloads-are-served)).
3. `share_path_mapping` in `opengsync.yaml` maps each top-level folder under the share root to its host path. The API uses it to turn host paths into share paths, and "internal access" emails use it to show host paths.

Example:

```yaml
# compose.override.yaml
services:
    opengsync-app:
        volumes:
            - /nobackup/lab_bsf/projects:/share/BSF_PROJECTS:ro
            - /research/lab_bsf/sequences:/share/BSF_SEQUENCES:ro
    nginx:
        volumes:
            - /nobackup/lab_bsf/projects:/share/BSF_PROJECTS:ro
            - /research/lab_bsf/sequences:/share/BSF_SEQUENCES:ro
```

```yaml
# opengsync.yaml
share_root: "/share"
share_path_mapping:
    BSF_PROJECTS: "/nobackup/lab_bsf/projects"
    BSF_SEQUENCES: "/research/lab_bsf/sequences"
```

With this setup, the host path `/nobackup/lab_bsf/projects/P123_Smith` becomes the share path `BSF_PROJECTS/P123_Smith`, which is `/share/BSF_PROJECTS/P123_Smith` in both containers.

## What a share link exposes

A path is reachable through a share link only if **all** of these hold:

1. It resolves inside the share root. `..` escapes, absolute paths and symlinks that point outside the share root are refused.
2. It is one of the token's share paths, lies below one, or is a parent folder of one.
3. It is not an [OS junk file](#os-junk-files).
4. It is not excluded by a [`.ngsignore`](#ngsignore) file.

These checks run on every request, including direct requests for paths that were never listed. Editing the URL, for example with encoded `%2e%2e` or `%2f`, double slashes or trailing slashes, does not get around them.

### Sharing a folder shares everything below it

A folder share exposes all of its contents, recursively. It reads the live filesystem, not a snapshot. Files added to the folder after the link was created become visible, after the [caching](#caching) delay, and deleted files disappear. If other data will be written into a shared folder later, share narrower paths or exclude it with `.ngsignore`.

### Parent folders are visible, as navigation only

Collaborators browse from the share root, so the folders above a share path are listed. Each parent folder shows only the branch that leads to the shared path; siblings are not listed and cannot be fetched. The **names** of the parent folders are therefore visible to collaborators.

### One token can share unrelated paths

A token can hold any number of paths, from different mounts. When a project is shared, all of its data paths go into one token. Paths nested inside another shared path are dropped, because the outer path already covers them.

For example, a token with the paths `BSF_PROJECTS/P123_Smith/fastq` and `BSF_SEQUENCES/run_42/P123_multiqc.html` shows collaborators:

```
/                                   <- token root, e.g. /api/webdav/<token>/
├── BSF_PROJECTS/                   <- navigation only; other projects are not listed
│   └── P123_Smith/                 <- navigation only; other folders of P123 are not listed
│       └── fastq/                  <- shared folder: everything below is visible
│           ├── S1_R1.fastq.gz
│           └── S1_R2.fastq.gz
└── BSF_SEQUENCES/
    └── run_42/                     <- navigation only; the rest of run_42 is not listed
        └── P123_multiqc.html       <- shared file
```

### Symlinks

- A symlink is followed as long as its target is inside the share root. It is shown under the link's own name.
- A symlink is hidden if its **target** is excluded by `.ngsignore`, even when the link's own path is not.
- **A file symlink inside a shared folder exposes its target, even when the target is outside the token's share paths.** Anything in the share root can be reached this way, so don't leave links to other projects' data inside shared folders.
- A folder symlink that points outside the token's share paths is inconsistent: its contents are listed, but downloading them returns 404.
- An absolute symlink must resolve inside the containers, i.e. under `/share/...`. Links to host paths such as `/nobackup/...` are broken inside the containers and are hidden. Relative links avoid this.

## Hidden files

Share links hide two kinds of files: OS junk files, which are always hidden, and anything excluded by a `.ngsignore` file. To a collaborator, a hidden path looks exactly like a path that doesn't exist: WebDAV answers 404, and the HTML routes show an empty listing and serve no file.

Neither rule applies to the insider file browser, which shows everything, including the `.ngsignore` files.

### OS junk files

Defined in `SharedFileBrowser.OS_JUNK_REGEX`. Matching ignores case. A path is junk if any of its folder or file names **starts with** one of:

`._`, `.DS_Store`, `Thumbs.db`, `desktop.ini`, `.Spotlight-V100`, `.Trashes`, `.metadata_`, `.com.apple.timemachine`, `.hidden`, `.ignored`

or is named exactly `Network Trash Folder` or `Temporary Items`.

Because these are prefix matches, a file such as `.ignored_samples.csv` or a folder such as `.hidden_results/` is also hidden, together with everything inside that folder.

### `.ngsignore`

A `.ngsignore` file uses [`.gitignore` syntax](https://git-scm.com/docs/gitignore) and hides paths from share links. Put one in any folder under the share root. It is parsed with the [`pathspec`](https://pypi.org/project/pathspec/) library, and the rules match git's:

- **Scope:** a `.ngsignore` applies to its own folder and everything below it. Its patterns are relative to that folder.
- **Every file from the share root down applies**, including `.ngsignore` files in folders **above** the shared path. Sharing `BSF_PROJECTS/P123_Smith/fastq` still obeys `BSF_PROJECTS/.ngsignore` and `BSF_PROJECTS/P123_Smith/.ngsignore`.
- **The nearest file wins.** For each path, the closest `.ngsignore` with a matching rule decides, so a subfolder can re-include what a parent folder excludes. Within one file, the last matching line wins.
- **An ignored folder hides everything below it.** Nothing inside it can be re-included, and direct requests for anything inside it are refused.
- **Pattern syntax:**
  - A pattern without a slash, such as `*.bam`, matches at any depth.
  - A leading or middle slash anchors the pattern to the `.ngsignore` folder, as in `/report.html` or `qc/*.html`.
  - A trailing slash matches folders only, as in `work/`.
  - `**` matches any number of folders, `!` negates a pattern, `#` starts a comment, and `\` escapes a leading `#` or `!`.
  - Matching is case-sensitive.
- **The `.ngsignore` files are always hidden**, even with a `!.ngsignore` line, because they reveal the names of the hidden files.
- **Rules apply to all tokens at once.** They belong to the filesystem, not to a token.
- **Errors:** an invalid line, such as a bare `!`, is skipped and logged, and the other lines still apply. A `.ngsignore` that exists but cannot be read hides everything in its folder.
- **When changes take effect:** direct downloads follow a `.ngsignore` edit immediately. Listings can lag behind (see [Caching](#caching)).

#### Example: hide scratch files, logs and checksums

```
BSF_PROJECTS/P123_Smith/            <- shared
├── .ngsignore
├── fastq/
│   ├── S1_R1.fastq.gz
│   └── S1_R1.fastq.gz.md5
├── work/
│   └── tmp/x.bam
├── logs/
│   └── run.log
└── report.html
```

```gitignore
# BSF_PROJECTS/P123_Smith/.ngsignore
# pipeline scratch and logs
work/
*.log
```

| Path | Result |
|---|---|
| `fastq/S1_R1.fastq.gz` | visible |
| `fastq/S1_R1.fastq.gz.md5` | hidden |
| `work/`, `work/tmp/x.bam` | hidden |
| `logs/` | visible, but empty. Add `logs/` to hide the folder itself. |
| `logs/run.log` | hidden |
| `report.html` | visible |
| `.ngsignore` | hidden |

#### Example: a subfolder re-includes a file

```gitignore
# BSF_PROJECTS/P123_Smith/.ngsignore
*.bam
```

```gitignore
# BSF_PROJECTS/P123_Smith/alignments/.ngsignore
!final.bam
```

| Path | Result |
|---|---|
| `raw.bam` | hidden |
| `alignments/S1.bam` | hidden |
| `alignments/final.bam` | visible (the nearest file re-includes it) |
| `alignments/v2/final.bam` | visible (`final.bam` has no slash, so it matches at any depth) |
| `other/final.bam` | hidden (the re-include only applies below `alignments/`) |

#### Example: anchored and unanchored patterns

| `.ngsignore` in `P123_Smith/` | Hides | Does not hide |
|---|---|---|
| `/report.html` | `report.html` | `sub/report.html` |
| `report.html` | `report.html`, `sub/report.html` | |
| `qc/*.html` | `qc/a.html` | `sub/qc/b.html`, `qc/deep/c.html` |
| `**/qc/*.html` | `qc/a.html`, `sub/qc/b.html` | |
| `tmp/` | any folder named `tmp` at any depth, and its contents | a *file* named `sub/tmp` |

#### Example: keep one subfolder of an ignored folder

This does **not** work, because `work/` is ignored and nothing below it can be re-included:

```gitignore
work/
!work/final/
```

Ignore the folder's *contents* instead, and re-include the subfolder:

```gitignore
work/*
!work/final/
```

Result: `work/final/` and everything in it is visible; `work/tmp/` and `work/notes.txt` are hidden.

#### Example: a rule above the shared folder

```gitignore
# BSF_PROJECTS/.ngsignore
undetermined*
```

A share of `BSF_PROJECTS/P123_Smith/fastq` hides `fastq/undetermined.fastq.gz`, even though the rule lives two folders above the shared path.

## How downloads are served

File contents are served by nginx, not by FastAPI:

1. FastAPI handles the request and runs all the checks in [What a share link exposes](#what-a-share-link-exposes).
2. It answers with an empty response and the header `X-Accel-Redirect: /nginx-share/<path>` (`responses.accel_redirect_response`). WebDAV `GET` calls it directly. The browse, rclone and shared-browser routes call `responses.file_response`, which does the same.
3. nginx serves the file from its `/nginx-share/` location, which is an alias for `/share/`.

So `.ngsignore` and the other checks always run before nginx sees the request. Details:

- **`/nginx-share/` is `internal`** in `services/nginx/nginx.template.conf`, so clients cannot request it directly.
- **nginx refuses `..` in `X-Accel-Redirect`** with 404, logged as `unsafe URI`. A request whose path contains `..` therefore gets a 404, even when it points at a visible file. It can never make nginx serve a different file from the one the app checked.
- **`HEAD`** requests are answered by FastAPI with headers only.
- **Fallback:** if a file's path does not start with the configured `share_root`, for example because `share_root` is set to a path through a symlink, `file_response` falls back to serving the file from FastAPI, reading it entirely into memory. Keep `share_root` a real folder, with the bind mounts below it.

## Caching

Share responses are cached in Redis:

| What | Redis key | TTL | Used by |
|---|---|---|---|
| Token (paths, expiry) | `share-token:<token>` | 5 min | every request |
| Folder listings | `share-fs:<token>:list:*` | 60 s | browse, rclone, shared browser |
| WebDAV `PROPFIND` | `share-fs:<token>:propfind:*` | 5 min | WebDAV clients |

What this means in practice:

- **Listings can be out of date by up to the TTL.** That covers new files, deleted files and `.ngsignore` edits: up to 60 s for the HTML routes and up to 5 min for WebDAV.
- **Access checks on the requested path are not cached.** A newly ignored file stops downloading immediately, even while it is still listed. A deleted file returns 404. A new file can be downloaded by its path before it appears in listings.
- **Expiry by time is checked on every request**, even when the token itself is cached.
- **Sharing a project again** (in the UI or with the API) expires its previous token and clears that token's caches immediately. Other changes made directly in the database, such as setting `expired` or editing a token's paths with SQL, take up to 5 minutes to apply.
- **WebDAV clients cache too.** Finder, Windows Explorer and `rclone mount --vfs-cache-mode full` keep their own copies of listings, so they may need a refresh or a remount to show changes.

To clear a token's caches by hand:

```sh
docker exec redis-cache sh -c "redis-cli --scan --pattern 'share-fs:<token>:*' | xargs -r redis-cli del; redis-cli del share-token:<token>"
```

or, from Python in the app, call `share_fs_cache.invalidate(redis, token)`.

## Sharing with the OpeNGSyncAPI

The `opengsync_api` package (`packages/opengsync-api`) wraps the share endpoints. You need an **insider's** API token, and the project must have an identifier.

Paths passed to the API are **host paths**. The server translates them with `share_path_mapping`. A path must exist on the server and must lie below one of the mapping's prefixes; the prefix itself, such as `/nobackup/lab_bsf/projects`, cannot be added.

This example shares a project folder and a QC report from a different mount through **one** token, hiding scratch files first:

```python
from pathlib import Path

from pydantic import SecretStr
from opengsync_api import OpeNGSyncAPI
from opengsync_db import categories

api = OpeNGSyncAPI("https://opengsync.example.org", api_token=SecretStr("<insider API token>"))
api.authenticate()

project_id = 123

# 1. Hide what collaborators should not see. .ngsignore is a plain file,
#    written on the host where the data lives.
Path("/nobackup/lab_bsf/projects/P123_Smith/.ngsignore").write_text(
    "work/\n*.log\n*.md5\n"
)

# 2. Link data paths to the project. They can come from different mounts.
#    path_type is inferred from the path if omitted (folder -> DIRECTORY, .html -> HTML, ...).
api.add_data_path("/nobackup/lab_bsf/projects/P123_Smith", project_id=project_id)
api.add_data_path(
    "/research/lab_bsf/sequences/run_42/P123_multiqc.html",
    project_id=project_id,
    path_type=categories.DataPathType.HTML,
)

# 3. Check what will be shared: host paths, with nested paths removed.
print(api.get_project_data_paths(project_id))

# 4. Create the share link and email it. This expires the project's previous link.
result = api.release_project_data(
    project_id=project_id,
    internal_access=False,
    time_valid_min=60 * 24 * 14,  # 2 weeks
    recipients=["collaborator@example.org"],
    comment="FASTQ files and QC report for P123.",
)
print(result["recipients"])
```

Collaborators then see `BSF_PROJECTS/P123_Smith/` (without `work/`, logs or checksums) and `BSF_SEQUENCES/run_42/P123_multiqc.html`, as in [One token can share unrelated paths](#one-token-can-share-unrelated-paths).

Notes on `release_project_data`:

- **The response does not include the token.** Find it in the email or on the **Share Tokens** page (`/share_tokens`).
- **Recipients:** with `recipients=None`, the email goes to every address on the Share tab of the project's latest sequencing request.
- **`internal_access=True`** adds instructions for internal users, rendered from `personalization.internal_share_template`, showing the host paths.
- **Status changes:**
  - The project is marked **DELIVERED** if all its libraries are sequenced. `mark_project_delivered=True` forces it, and `False` never marks it.
  - The request's share emails are marked **DISPATCHED**.
  - Sequenced libraries are marked **SHARED**.

`api.remove_data_paths(project_id=...)` unlinks all data paths from the project. Existing tokens keep their paths until they expire or the project is shared again.

## Known quirks

- **`..` in paths:** paths containing `..` return 404 from nginx, even when they point at a visible file (see [How downloads are served](#how-downloads-are-served)).
- **Folder symlinks** that point outside the token's share paths list their contents, but downloads from them return 404.
- **Junk filter** matches prefixes, so `.hidden*` and `.ignored*` names are hidden too (see [OS junk files](#os-junk-files)).

## Code

| What | Where |
|---|---|
| Access checks, listings, WebDAV | `services/backend/server/utils/shared_file_browser.py` |
| `.ngsignore` matching | `services/backend/server/utils/share_ignore.py` |
| Share caches | `services/backend/server/utils/share_fs_cache.py` |
| Token loading and caching, rate limits, audit | `services/backend/server/core/dependencies.py` |
| `X-Accel-Redirect` | `services/backend/server/core/responses.py` |
| Share routes | `services/backend/server/routes/api/shares.py`, `routes/api/webdav.py`, `routes/pages/shared_browser.py` |
| nginx | `services/nginx/nginx.template.conf` |

## Security

### Share links are bearer tokens

- **Anyone with the link has access.** Whoever holds the link can list and download everything it exposes, without logging in, and forwarding the email forwards the access. Treat links like passwords: share only what is needed, and keep validity periods short.
- **Tokens can't be guessed.** A token is a UUIDv7: a 48-bit creation timestamp followed by 74 random bits from Python's `secrets` module. That's far too many values to guess, and [rate limiting](#rate-limiting) makes trying impractical. The timestamp only reveals when the link was created.
- **Tokens appear in logs.** They are part of the URL, so they show up in nginx access logs and in collaborators' browser history.
- **Access is read-only.** WebDAV accepts only `GET`, `HEAD`, `PROPFIND` and `OPTIONS`, and `LOCK`/`UNLOCK` do nothing. `PUT`, `DELETE`, `MOVE` and every other method get 405. The share folders are also mounted read-only (`:ro`) in both containers.

### Expiry and revocation

- **Expiry:** a token expires `time_valid_min` minutes after it was created. The expiry is checked on every request, even when the token is [cached](#caching). An expired token gets **403** on every route; an unknown token gets **404**.
- **Sharing a project again** expires the project's previous token immediately and clears its cache.
- **There is no button to revoke a link early.** To revoke one before it expires:
  - For a project link, share the project again.
  - Otherwise, set `expired = true` for the token in the `share_token` table, then clear its cache (see [Caching](#caching)). Until the cache is cleared, the token keeps working for up to 5 minutes.
- **Expiry only stops new access.** Files a collaborator has already downloaded can't be taken back.

### Rate limiting

- **Limits**, per client IP and route:

  | Routes | Limit |
  |---|---|
  | Public `/api/shares/…` routes and `/files/share/browse/…` | 20 requests per minute |
  | `/api/webdav/…` | 200 requests per minute and 5000 per hour |

  Going over a limit returns **429**.
- **Only failed attempts count.** A request with a valid token resets its counter, so the limits slow down token guessing without affecting normal downloads.
- **Client IP:** the app takes the client IP from the `X-Real-IP` header, which nginx sets from the actual connection, overwriting anything the client sent. The app's port (5000) is only exposed inside the Docker network, not published on the host. Keep it that way: a client that could reach the app directly could send its own `X-Real-IP` and get around the limits.
- **Redis outage:** if Redis is unavailable, the rate limiter lets requests through and logs an error.

### Path handling

Every path in a share URL is treated as **relative to the share root** and checked on every request, as described in [What a share link exposes](#what-a-share-link-exposes). Percent-encoding (`%2e%2e` for `..`, `%2f` for `/`) is decoded first, so it doesn't change the outcome. For a token that shares `BSF_PROJECTS/P123_Smith/fastq`, requests to `/api/webdav/<token>/…` give:

| Path after the token | Result |
|---|---|
| `BSF_PROJECTS/P123_Smith/fastq/S1_R1.fastq.gz` | served |
| `/etc/passwd`, `%2fetc%2fpasswd` (absolute path) | refused: outside the share root |
| `%2e%2e/%2e%2e/etc/passwd` (walks up out of the share root) | refused: outside the share root |
| `%2e%2e/share-evil/data.txt` (folder next to `/share` with a similar name) | refused: paths are compared by folder, not by text prefix |
| `BSF_PROJECTS/P124_Other/report.html` (an unshared sibling) | refused: inside the share root, but not shared |
| `BSF_PROJECTS/P123_Smith/fastq/%2e%2e/%2e%2e/P124_Other/report.html` (walks up from the shared folder into a sibling) | refused: the resolved path is not shared |
| `BSF_PROJECTS/P123_Smith/fastq/sub/%2e%2e/S1_R1.fastq.gz` (walks up and back into the shared folder) | the app allows it, but nginx refuses any path containing `..`: **404** |
| `BSF_PROJECTS/P123_Smith/fastq/link` → a symlink pointing outside the share root | refused |
| `BSF_PROJECTS/P123_Smith/` (parent of the shared folder) | lists only `fastq/`, as navigation |

**Refused requests never return file contents.** WebDAV `GET` and `HEAD` answer 404, and `PROPFIND` answers 403 for paths outside the shared paths. The HTML routes show an empty listing. Paths hidden as junk or by `.ngsignore` answer 404, the same as a missing file.

**Two symlink cases** need care (see [Symlinks](#symlinks)):
- A symlink that points outside the share root is always refused.
- A file symlink inside a shared folder serves its target from anywhere in the share root, even when that target is not shared.

**nginx:** the `/nginx-share/` location is `internal`, so clients can't request it directly. It is reached only through the app's `X-Accel-Redirect` header, after the checks have passed.

### Paths entered by staff

Paths that insiders provide are checked before anything is stored:

- **API `add_data_path`:**
  - The host path is resolved, following symlinks and `..`.
  - It must lie below a `share_path_mapping` prefix, exist on the server, and still resolve inside the share root.
  - A mapping root itself, such as `/nobackup/lab_bsf/projects`, is refused.
- **File browser Assign and Share directory:** the path must resolve inside the share root, and Share directory also requires a folder.

Share tokens store paths relative to the share root, never host paths.

### Audit log

Every share-link request is written to the audit log. Successful requests have a cooldown, so a recursive download of thousands of files doesn't produce thousands of lines.

**Where:** `/logs/audits/<YYYY-MM-DD>.jsonl` in the `opengsync-app` container, which is `${LOG_DIR}/opengsync/audits/` on the host. Each line is one JSON object, and a new file starts every day. Older days are compressed to zip files and are never deleted automatically.

**What gets logged:**

- **Successful requests, with a cooldown:**
  - The first successful request for a token from a client IP is logged.
  - Further successful requests from that IP for that token are skipped until the cooldown ends. The cooldown ends when the link expires (and lasts at least 60 seconds), so in practice each client IP appears once per link.
  - A request from a different IP gets its own line.
  - The cooldown is tracked in Redis under `share-audit:<token>:<ip>`. If Redis is unavailable, every request is logged.
- **Failed requests, without a cooldown:** every request that ends in an error status (400 or higher) is logged. That includes unknown or expired tokens, refused paths and rate-limit hits (429).

**Fields** (under `record.extra` in each line; the time is in `record.time`):

| Field | Content |
|---|---|
| `ip` | Client IP, from the `X-Real-IP` header set by nginx |
| `agent` | User agent, e.g. `rclone/v1.68.0` |
| `method`, `path`, `route` | HTTP method, full request path (including the token), and the matched route |
| `status_code` | Response status |
| `resource_id` | The token |
| `metadata.owner_id` | ID of the insider who created the link |
| `query_params`, `process_time` | Query string parameters, and processing time in seconds |

For requests with an unknown or expired token, `resource_id` and `metadata` are empty, and the token appears only in `path`.

Example: list who used a link, and when:

```sh
jq -c 'select(.record.extra.resource_id == "<token>")
       | {time: .record.time.repr, ip: .record.extra.ip, agent: .record.extra.agent,
          status: .record.extra.status_code, path: .record.extra.path}' \
    ${LOG_DIR}/opengsync/audits/*.jsonl
```

Older, zipped days can be read with `unzip -p <file>.zip | jq …`.
