# File Sharing

How opengsync shares files from the share mount with external collaborators through share links: what a link exposes, how to hide files with `.ngsignore`, how downloads are served, and where caching makes things look out of date.

- [Overview](#overview)
- [Selecting paths in the file browser](#selecting-paths-in-the-file-browser)
- [Searching (fs-index)](#searching-fs-index)
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
| Insider file browser → **Share** | Any files and folders, picked one at a time or [selected](#selecting-paths-in-the-file-browser) | Emails a browse link. Valid for 24 hours to 1 month (default 2 weeks). Not tied to a project. |
| API `release_project_data` | All data paths linked to the project | Same as **Share Data**. See [Sharing with the OpeNGSyncAPI](#sharing-with-the-opengsyncapi). |

A token's paths are fixed when it is created. Linking more data paths to a project later does not change an existing token; share the project again to get a new one.

## Selecting paths in the file browser

The insider file browser (**Files**) can share or associate several files and folders at once:

1. **Select paths.** Right-click a file or folder and choose **Select**, or Ctrl+click (Cmd+click on macOS) the row; in [search](#searching-fs-index) results, the **Select** button on a row does the same. Selected rows are highlighted. Right-click a selected row and choose **Deselect**, or Ctrl/Cmd+click it again, to remove it.
2. **Review them.** A panel in the bottom-right corner lists the selection. Remove single paths with their **×**, or empty the whole selection with **Clear selection** (the circled × in the panel's header, available while the panel is collapsed too).
3. **Act on them.**
   - **Share** opens the share form with all selected paths and creates **one** token holding them. After the email is sent, the selection is cleared.
   - **Associate** links every selected path to the chosen project, experiment, request or library. The selection is kept, so the same paths can be associated with something else next.

   Both forms list the paths the same way: one row per path, with a folder or file icon and a **×** to remove it. Removing a row drops the path from that form only; it stays selected in the browser. The last row can't be removed.

Details:

- **At most 50 paths** per selection, share and association.
- **The selection is stored in the browser** (`localStorage`), not on the server or in the account. It survives reloads, is shared by all tabs of that browser, and is not available in another browser or on another computer.
- **Paths inside a selected folder are left out.** Selecting `run_42/` and `run_42/report.html` lists, shares or associates only `run_42/`, which already covers the file; the form says how many paths it left out. To give a file inside an associated folder its own row on the project's data paths, associate the file on its own.
- **One bad path rejects the whole request.** If any path resolves outside the share root, nothing is shared or associated. Sharing also refuses paths that no longer exist, and marks the path in question.
- **Paths that are gone are flagged when the form opens.** Both forms warn **Not found on the share** on such a row, e.g. for a stale search result. Associate still accepts them, so data paths can be registered before the data is there.
- **Single paths work as before.** Right-click → **Share** or **Assign** on a row acts on that row only and leaves the selection alone.

## Data tabs

The **Data** tab of a project, sequencing request, experiment or library is a file browser over the data paths linked to it (`DataPath.project_id`, `seq_request_id`, `experiment_id`, `library_id`; the link is made with **Manage data** on the tab, or **Assign** in the insider browser). It is the same browser and the same rules for all four:

- The top level lists the linked data paths, including ones missing from storage (marked *not found on storage*). Below them the folders are listed live from the mount, with `.ngsignore`d paths and symlinks that leave the share left out, as in a share link.
- Only documents, images, tables and HTML reports (plus the assets reports load) open in the browser; everything else is listed but only downloadable through a share link (`PROJECT_SERVABLE_EXTENSIONS` in `utils/file_browser.py`).
- Admins and bioinformaticians get **Manage data**: a full-screen window with the insider browser over the whole share. The linked paths start ticked; tick files and folders (or Ctrl/Cmd+click, or right click → Select) to add them and untick linked ones to remove them, then **Save** (removing asks first, and only unlinks: the files stay on disk). Only paths inside a share root can be added, not `<root>` itself (the same for **Assign**); a ticked folder covers ticked paths inside it, and every added path must exist inside the share (at most 50 at once). Only the changes are sent, so paths linked meanwhile by someone else stay.
- Admins and bioinformaticians also get **Remove from …** on a data path (right click). It unlinks the path from that page's project, request, experiment or library only; the files stay on disk.
- With the fs-index enabled, the header has a search box limited to these data paths (see [Using search](#using-search)).

Access is the page's own: project, request and library members can open their Data tab; experiments are insider only. The routes live under the owner, e.g. `/htmx/seq_requests/{id}/browse/…`, `/htmx/seq_requests/{id}/files/…` (`routes/htmx/data_browser.py`).

## Searching (fs-index)

The share is a network mount of the cluster filesystem, far too large to search live. With `fs_index.enabled`, the worker keeps a **SQLite index** of everything under the share root, and the file browsers get a search box that queries it. The index is only used to *find* paths: browsing, downloads and share links always read the mount live.

- [Using search](#using-search)
- [How the index is built](#how-the-index-is-built)
- [Crawler: schedule and limits](#crawler-schedule-and-limits)
- [Configuration](#configuration)
- [Rolling it out](#rolling-it-out)
- [Status on the dashboard](#status-on-the-dashboard)
- [Caveats](#caveats)

### Using search

The search box sits in the file browser's header, next to the sort buttons:

- **Insider file browser** (**Files**): searches everything under the share root. Hidden paths (`.ngsignore`) are included and marked, because the insider browser shows everything.
- **Data tabs** (project, request, experiment, library): search below that page's data paths only, and only what a share link of them would serve: no `.ngsignore`d paths, no symlinks leaving the share. Results are checked against the mount before they are shown.

What a query matches:

- **Names containing all its words**, case-insensitively: `counts matrix` finds `filtered_counts_matrix.h5ad`. At least one word needs 3 or more characters.
- **A path prefix** when it contains a `/`: `BSF_PROJECTS/P123` or `/share/BSF_PROJECTS/P123` lists everything below that path.

Results show folders first, then the most recently changed. Each row has the name with the match highlighted, its parent folders (each one opens that folder), its size (a folder's total), when it changed, and badges for data paths, **Hidden from share links** and **Points outside the share**. Filters narrow results to folders or files and, in the insider browser, to one top-level folder; **Show more** loads the next 50. In the insider browser, hovering a row offers **Select**, **Share** and **Open the folder it is in**; right-click works as on any row.

A folder in the results expands into the live listing, and opening a folder shows it with a path bar on top. `/browser/<path>` opens the insider browser at that folder.

**Stale results.** The index can be behind the mount (see [Crawler](#crawler-schedule-and-limits)). Acting on a path that no longer exists says so, instead of failing silently: expanding or opening it shows **This folder no longer exists**, the Share and Associate forms warn **Not found on the share** on its row (sharing then refuses it), and a project file link answers 404 with the same hint. Opening a missing folder also asks the crawler to re-check it, so it drops out of the index within a minute or two.

### How the index is built

The index lives in `/app_data/fs_index/fs_index.sqlite3` on the `app_data` volume. The worker is its only writer; the app opens it read-only.

1. **Cluster dump (recommended for the first build).** `scripts/fs_index_dump.py` runs on the cluster, where the filesystem is local and listing is fast, and writes one `<NAME>.jsonl.gz` per top-level folder (names as in `share_path_mapping`). Each line holds an entry's path, type, size and mtime; symlinks also record their target, and `.ngsignore` files their contents.
2. **Import.** Dumps copied into `/app_data/fs_index/dumps/` are imported by the import task (every 10 minutes by default), or right away with `python -m opengsync_worker.tasks.fs_index_import` in the worker container. A dump **replaces everything indexed for its folder**, in one transaction: searches see the old index until the import commits. A dump is imported again only when the file changes (mtime or size). A dump without its final line (an interrupted run) is skipped.
3. **Crawler.** Keeps the index current by re-checking folders on the mount: see the next section. Without a dump, it builds the index itself, starting from the folders under the share root, at its usual rate limit.

What is stored:

- **Every file, folder and symlink**, except OS junk (`.DS_Store`, `._*`, …).
- **Folders matching `index_ignore`** (pipeline internals such as `*_CS`, `work`, `.nextflow`, `Rtmp*`, `BaseCalls`) are stored as one entry with their total size; their contents are not stored, not searchable and not crawled.
- **Folder totals**: size and file count of everything below, counted as a share link would serve it: hidden paths and symlinks leaving the share are left out, symlinks to files count their target, symlinks to folders count nothing (the target is counted where it lives).

### Crawler: schedule and limits

The crawler is a Celery beat task. Every `crawl_schedule` (60 s) it runs for at most `crawl_budget_s` (50 s) and checks the folders that are **due**. A Redis lock makes sure crawls and imports never overlap; a run that finds the lock taken is skipped.

**Checking a folder** costs one `stat`. If its mtime is unchanged, nothing else happens. If it changed, the folder is listed again (one `scandir` plus an `lstat` per entry) and the index is updated: new entries added, missing ones removed, sizes updated up the tree.

**When a folder is due.** Each folder has its own check interval:

| Event | Next check |
|---|---|
| Folder changed (or was just discovered) | `min_interval_s` (2 min) |
| Folder unchanged | interval doubles: 2, 4, 8 … min, up to `max_interval_s` (7 days) |
| Opened live in any browser or share link | next crawl run |
| Its `.ngsignore` was edited | next crawl run (every run stats all known `.ngsignore` files, since editing one doesn't change its folder's mtime) |

After a dump import, the first interval depends on when anything below the folder last changed, and each first check is placed at a random point within it, so an import never makes everything due at once:

| Last change below the folder | First interval |
|---|---|
| under 7 days ago | `min_interval_s` (2 min) |
| 7 to 90 days ago | 6 h (at most `max_interval_s`) |
| older | `max_interval_s` (7 days) |

So active data is checked every few minutes, finished data drifts to once a week, and both resettle on their own when something changes.

**Limits.** The crawler is built to never put burst load on the share's metadata server:

- **`crawl_rate`** (default **10 folders per second**) caps all crawler work together. Listing a big folder counts extra: every 200 entries cost as much as one more folder, so listing a folder of 10,000 files uses the budget of about 50 folders. `0` disables the limit.
- **`crawl_threads`** (default **1**): folders checked at a time. With one thread every check waits for the previous one, so the actual rate is often below `crawl_rate`.
- **`crawl_budget_s`** (default **50 s**) and **`crawl_schedule`** (default **60 s**): how long each run may work and how often runs start. A run takes only as many folders as fit in its remaining budget at `crawl_rate`, so it ends near its budget; anything left waits for the next run.
- **`crawl_batch`** (default **500**): folders per database transaction, at most.

What that means for the share, with the defaults:

| Situation | Load |
|---|---|
| Steady state after a dump import (~1.5M folders) | ~150 `stat` calls per minute, spread over the week |
| A day with lots of new data | the changed folders, still at most 10 per second |
| Building from an empty index (no dump) | at most 10 folders per second, 50 s of each minute: ~1.5M folders take a few days |

**Safety.** If a top-level folder looks offline, the crawler removes nothing below it, so a dropped mount can't empty the index. A folder is offline when its `canary_files` entry is missing, or, with no canary configured for it, when it is empty or missing. Give every share root a canary, because the fallback can't tell a mount that is up but empty from one that is down. The check runs again before every removal, since a mount can drop or come back mid-run. Once a folder fails the check, it stays offline for the rest of that run. Before a removal, the paths are also looked up once more: if they are there again, the folder is listed again on the next run instead. Unreachable folders (an sshfs error) are never removed; they just wait for their next check. A folder changed in the same second it was listed (mtimes have 1 s resolution on sshfs) is listed again on its next check, and so are folders that changed while a dump was running.

### Configuration

All settings are in the `fs_index` section of `opengsync.yaml`; every key is optional.

```yaml
fs_index:
    enabled: true
    import_schedule: 600
    crawl_schedule: 60
    crawl_budget_s: 50
    crawl_rate: 10
    crawl_threads: 1
    min_interval_s: 120
    max_interval_s: 604800
```

| Key | Default | What it does |
|---|---|---|
| `enabled` | `false` | Schedules the import and crawl tasks, shows the search boxes and the dashboard card, and queues live listings for the crawler. Off: nothing runs and nothing is shown; the manual import still works. |
| `import_schedule` | `600` | How often new dumps are imported: seconds, or a 5-field cron string. |
| `crawl_schedule` | `60` | How often a crawl run starts: seconds, or a 5-field cron string. |
| `crawl_budget_s` | `50` | Longest a crawl run works, in seconds. Keep it below `crawl_schedule`. |
| `crawl_rate` | `10` | Folders checked per second at most, all threads together; big listings count extra. `0`: no limit. |
| `crawl_threads` | `1` | Folders checked at a time. |
| `crawl_batch` | `500` | Folders per database transaction, at most. |
| `min_interval_s` | `120` | Check interval of a folder that just changed or was just found. |
| `max_interval_s` | `604800` | Longest check interval (7 days), reached by folders that stay unchanged. |
| `index_ignore` | `*_CS`, `chnk*`, `work`, `.nextflow`, `.snakemake`, `Rtmp*`, `*_temporary`, `BaseCalls` | Folder name patterns whose contents are not indexed (still counted in folder sizes). Setting it replaces the defaults. |
| `db_file` | `<app_data_folder>/fs_index/fs_index.sqlite3` | The index file. Must be on a local disk, never on a network mount: SQLite's locking doesn't work there. |
| `dump_dir` | `<app_data_folder>/fs_index/dumps` | Where the import task looks for dumps. |

The worker and beat read the file at startup: restart `opengsync-celery-beat` after changing a schedule, `opengsync-celery-worker` after any other crawler setting, and `opengsync-app` after `enabled`.

Besides the config, the worker needs the share mounts (read-only, the same as `opengsync-app`; see [Setting up the share mount](#setting-up-the-share-mount)), and the app and the worker both mount the `app_data` volume (`compose.yaml`).

### Rolling it out

To start from a dump, so the crawler never builds from an empty index:

1. Deploy with `fs_index.enabled: false`. This brings the code, the `app_data` volume and the worker's share mounts; no fs-index task runs.
2. On the cluster, make the dumps (as a SLURM job or off-peak; `--threads` controls the parallel listings there):
   ```bash
   python3 fs_index_dump.py --out ~/fs_index_dumps --threads 2
   ```
3. Copy them into the worker and import them:
   ```bash
   docker exec opengsync-celery-worker mkdir -p /app_data/fs_index/dumps
   for f in /tmp/fs_index_dumps/*.jsonl.gz; do docker cp "$f" opengsync-celery-worker:/app_data/fs_index/dumps/; done
   docker exec opengsync-celery-worker python -m opengsync_worker.tasks.fs_index_import
   ```
   It prints one line per imported folder (entries, skipped, errors, seconds).
4. Set `enabled: true` and restart `opengsync-app`, `opengsync-celery-worker` and `opengsync-celery-beat`.

A fresh dump can be imported at any time later, e.g. to resynchronize files rewritten in place.

### Status on the dashboard

The insider dashboard's **System** tab has a **Share Search Index** card:

- **State**: *Up to date*, *Working* (an import or crawl is running), *Behind* (folders more than an hour past their check; expected while building from an empty index), *Not built yet* or *Disabled*.
- **Last crawl**: when, folders checked and changed, how long it took, errors.
- **Last change found**, **Folders due** (and how many are late, and how many were queued by browsing), **Indexed data** (total size, file count, index file size).
- **Per top-level folder**: size, file count, and when its dump was imported (or *none, crawled*).
- **Dumps waiting for import**, if any.

### Caveats

- **A file rewritten in place** keeps its old size and date in the index until the next dump: a folder's mtime only changes when entries are added, removed or renamed directly in it.
- **New data can take a few minutes** to show up in search: until its parent folder's next check, or right away once someone opens that folder.
- **Symlinks** are resolved on the cluster by the dump but inside the container by the crawler. Symlinks with absolute cluster paths may count as leaving the share for folders the crawler re-lists, unless the mount resolves them.
- **The index is a cache.** Deleting `fs_index.sqlite3` is safe: the next import task re-imports the dumps still in `dump_dir`, and the crawler catches up from there. It never touches Postgres, its WAL or its backups.

## Access routes

| Route | Typical client | What it does |
|---|---|---|
| `/api/webdav/{token}/{path}` | `rclone` (WebDAV), `rclone mount`, Finder, Windows Explorer | Read-only WebDAV: `GET`, `HEAD`, `PROPFIND`, `OPTIONS`. `LOCK`/`UNLOCK` return 204 and do nothing. |
| `/api/shares/browse/{token}/{path}` | The link in share emails | Simple HTML listing; a file path downloads the file. The download bar at the top opens popups with the copy commands, and offers zip downloads behind nginx. |
| `/api/shares/zip/{token}/{path}` | Browser (**Download all (.zip)**, the **.zip** link on each folder) | The share, or one shared folder, as one zip streamed by nginx. Only behind nginx with mod_zip; see [Zip downloads](#zip-downloads). |
| `/files/share/browse/{token}/{path}` | Browser | The shared file browser (paginated, sortable); a file path downloads the file. |
| `/api/shares/rclone/{token}/{path}` | `rclone --http-url`, `wget --recursive` | Plain HTML index for recursive download tools; a file path downloads the file. |
| `/api/shares/rclone_script/{token}` | | The `rclone copy` command, as text. |
| `/api/shares/validate/{token}` | | `OK` if valid. |

Every route answers **404** for an unknown token and **403** for an expired one.

Share emails hold only the browse link. The download commands are shown on that page, rendered from `services/backend/templates/snippets/*.j2`, for example:

```sh
rclone copy ":webdav,url='https://<host>/api/webdav/<token>':/" BSF_DATA \
    --progress --transfers=8 --checkers=16 --use-server-modtime --verbose
```

**Rate limits** are counted per client IP and route: 20 requests per minute on the public `/api/shares/…` routes and on `/files/share/browse/…`, and 200 per minute plus 5000 per hour on WebDAV. A request with a valid token resets its counter, so in practice only requests with unknown or expired tokens count. The limits exist to stop token guessing.

**Audit:** every share-link access is written to the audit log, with a cooldown per token and client IP (see [Audit log](#audit-log)).

## Setting up the share mount

Three settings must agree:

1. `share_root` in `opengsync.yaml`, normally `"/share"`.
2. `compose.override.yaml` on the production host mounts the host folders under `/share`. They must be mounted into **both** `opengsync-app` and `nginx`, at the **same container paths**, read-only. The app checks each request, and nginx then reads the file from the same path (see [How downloads are served](#how-downloads-are-served)). With the [fs-index](#searching-fs-index) enabled, `opengsync-celery-worker` needs the same mounts.
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
    opengsync-celery-worker:  # fs-index crawler
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

### Zip downloads (nginx)

[Zip downloads](#zip-downloads) need two things from the deployment. Without either, the share browser shows no zip buttons and the zip route answers 404, while everything else keeps working.

1. **The nginx image** from this repository (`services/nginx/Dockerfile`). It builds mod_zip as a dynamic module, pinned to a commit, and loads it in `/etc/nginx/nginx.conf`.
2. **Two additions to the server block** in `NGINX_CONFIG_DIR`, as in `services/nginx/nginx.template.conf`:
   - `proxy_set_header X-Archive-Support zip;` in `location /`. This is how the app learns that mod_zip is available. nginx overwrites any client-sent value.
   - A `location /api/shares/zip/` block with the same proxy headers (including `X-Archive-Support`), plus `proxy_method GET;` and `proxy_read_timeout 300s;`. The app walks and `stat`s every file before nginx starts streaming, which can take longer than the default 60 s on a large share over the network mount. `proxy_method GET` lets a `HEAD` request report the zip's size.

To try it in dev, run `make dev-nginx`, which starts nginx with mod_zip on http://localhost:8080 (config: `services/nginx/nginx.dev.conf.template`). Open share links through that port. The dev app on its own port has no zip buttons.

## What a share link exposes

A path is reachable through a share link only if **all** of these hold:

1. It resolves inside the share root. `..` escapes, absolute paths and symlinks that point outside the share root are refused.
2. It is one of the token's share paths, lies below one, or is a parent folder of one.
3. It is not an [OS junk file](#os-junk-files).
4. It is not excluded by a [`.ngsignore`](#ngsignore) file.

These checks run for every requested path, including paths that were never listed. In prod, a result is [cached](#caching) for up to a minute per exact path, so a repeated request reuses it; any other spelling of the URL is a different path and is checked again. Editing the URL, for example with encoded `%2e%2e` or `%2f`, double slashes or trailing slashes, does not get around them.

### Sharing a folder shares everything below it

A folder share exposes all of its contents, recursively. It reads the live filesystem, not a snapshot. Files added to the folder after the link was created become visible, after the [caching](#caching) delay, and deleted files disappear. If other data will be written into a shared folder later, share narrower paths or exclude it with `.ngsignore`.

### Parent folders are visible, as navigation only

Collaborators browse from the share root, so the folders above a share path are listed. Each parent folder shows only the branch that leads to the shared path; siblings are not listed and cannot be fetched. The **names** of the parent folders are therefore visible to collaborators.

### One token can share unrelated paths

A token can hold any number of paths, from different mounts. When a project is shared, all of its data paths go into one token, and sharing a [selection](#selecting-paths-in-the-file-browser) from the file browser does the same with the selected paths. Paths nested inside another shared path are dropped, because the outer path already covers them.

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

Both rules also apply to a project's **Data** tab, which browses the project's data paths with the same checks. Neither applies to the insider file browser, which shows everything, including the `.ngsignore` files.

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
- **Fallback:** if a file's path does not start with the configured `share_root`, for example because `share_root` is set to a path through a symlink, `file_response` falls back to serving the file from FastAPI, reading it entirely into memory. The project **Data** tab refuses this fallback and answers 500 instead (`require_accel=True`). Keep `share_root` a real folder, with the bind mounts below it.

### Zip downloads

**Download all (.zip)** on the share browser downloads the whole share as one file. The **.zip** link on a folder row downloads that folder. Files are stored, not compressed: sequencing data is already compressed, and storing makes the size known up front, so browsers show a progress bar with time remaining.

1. FastAPI runs the usual checks (token, rate limit, audit, `.ngsignore`, junk, symlinks) and walks the files. It answers with a **file list**, not a zip, and the header `X-Archive-Files: zip` (`utils/share_zip.py`):
   ```
   0 0 @directory shared/nested/
   - 5 /nginx-share//shared/nested/child.txt shared/nested/child.txt
   ```
   Each line holds the CRC-32 (`-`: unknown), the size, the `/nginx-share/` location and the name inside the zip.
2. nginx's mod_zip replaces that body with the zip. For each file it makes a subrequest to `/nginx-share/`, as a single download does, and it computes `Content-Length` from the list.

**What goes in the zip:**
- A file is listed only if a single download of it would be served (`get_file`). So the zip holds exactly what clicking each file would download.
- Each file's real path is checked again without any cache, because nginx follows symlinks and this is the last check before nginx reads the file.
- Names that an extractor could misread are skipped and logged. These are names with line breaks or other control characters, `\`, `:`, or `..` components.
- Every line is validated once more before the list is returned.
- The whole share: each shared path becomes a top-level folder in the zip, named after its basename. Repeated names get ` (2)`, ` (3)`, … added. The zip is named `BSF_DATA.zip`.
- A folder: it must be at or below a shared path. The zip is named `<folder>.zip`, and the names inside start with the folder's name.
- Folder symlinks are followed, as WebDAV does, so a folder reachable twice is in the zip twice. A link back to a folder on its own path is not followed.

**Identity:** the list is sorted. The `ETag` is a hash of the list and each file's mtime, and `Last-Modified` is the newest mtime. Unchanged files therefore always give the same zip bytes and the same `ETag`.

**Limits:**
- **No resume.** mod_zip supports `Range` only when every file's CRC-32 is in the list. Without CRCs, an interrupted download starts again from zero. For very large shares, point people to Rclone.
- **Changes during a download.** A file that changes size or disappears while it is being streamed leaves a broken entry, or aborts the download.
- **mod_zip version.** The module is pinned to a commit after release 1.3.0. In 1.3.0, a dynamically loaded mod_zip runs before nginx reads file contents into memory, so every CRC in the zip is 0 and extractors report the files as corrupt. That release also answers `HEAD` with an empty reply.

## Caching

In prod, results are cached in Redis, and `.ngsignore` rules in each worker's memory. Dev and test cache nothing.

| What | Where | TTL | Used by |
|---|---|---|---|
| Token (paths, expiry) | Redis `share-token:<token>` | 5 min | every share-link request |
| Folder listings | Redis `share-fs:<key>:list:*` | 60 s | browse, rclone, shared browser, Data tab |
| A Data tab's data paths, top level | Redis `share-fs:<key>:roots:*` | 60 s | Data tab |
| File lookups (does the path exist, is it shared) | Redis `share-fs:<key>:file:*` | 60 s | downloads, WebDAV `GET`/`HEAD`, Data tab |
| WebDAV `PROPFIND` | Redis `share-fs:<key>:propfind:*` | 5 min | WebDAV clients |
| Each folder's parsed `.ngsignore` (or its absence) and resolved path | worker memory, at most 10,000 folders | 60 s | every check that misses the Redis caches |

`<key>` is the token for share links, and `<owner>:<id>:<hash of its data paths>` for a Data tab (`project`, `seq_request`, `experiment` or `library`). Linking or unlinking a data path changes the hash, so the Data tab shows the new set immediately.

The `.ngsignore` cache exists because every check walks all parent folders of the requested path and tries to open a `.ngsignore` in each. On a remote mount such as sshfs, every one of those attempts is a round trip, even when the file doesn't exist.

What this means in practice:

- **Listings can be out of date by up to the TTL.** That covers new files, deleted files and `.ngsignore` edits: up to 60 s for the HTML routes and the Data tab, and up to 5 min for WebDAV.
- **File lookups are cached too.** For up to 60 s a newly ignored file can still be downloaded, and a new file returns 404 if someone asked for it before it existed. A deleted file returns 404 straight away, because it is checked again before it is served.
- **An edited `.ngsignore` takes up to 60 s** to reach the worker caches, on top of the Redis TTLs above. Restarting the app clears the worker caches.
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
- **Folder symlinks** that point outside the token's share paths list their contents, but downloads from them return 404, and zip downloads leave their files out.
- **Junk filter** matches prefixes, so `.hidden*` and `.ignored*` names are hidden too (see [OS junk files](#os-junk-files)).

## Code

| What | Where |
|---|---|
| Access checks, listings, WebDAV | `services/backend/server/utils/shared_file_browser.py` |
| `.ngsignore` matching | `services/backend/server/utils/share_ignore.py`, rules shared with the fs-index in `packages/opengsync-db/opengsync_db/fs_index/ignore.py` |
| fs-index schema and read-only handler | `packages/opengsync-db/opengsync_db/fs_index/` |
| fs-index import and crawler | `packages/opengsync-worker/opengsync_worker/tasks/fs_index_*.py`, cluster dump `scripts/fs_index_dump.py` |
| Search queries and routes | `services/backend/server/utils/fs_index.py`, `routes/htmx/files.py` (`file_browser_search`, `fs_index_status`), `routes/htmx/data_browser.py` (`<owner>_browser_search`) |
| File browser and search templates | `services/backend/templates/components/file-browser/` (`browser.jinja2`, `entries.html`, `search-results.html`), dashboard card `components/fs-index-status.html` |
| Share caches | `services/backend/server/utils/share_fs_cache.py` |
| Token loading and caching, rate limits, audit | `services/backend/server/core/dependencies.py` |
| `X-Accel-Redirect` | `services/backend/server/core/responses.py` (`x_accel_redirect`) |
| Zip file list for mod_zip | `services/backend/server/utils/share_zip.py`, route `file_share.zip` in `routes/api/shares.py` |
| Share routes | `services/backend/server/routes/api/shares.py`, `routes/api/webdav.py`, `routes/pages/shared_browser.py` |
| File browser Share and Associate forms | `services/backend/server/forms/actions/SharePathAction.py`, `forms/actions/AssociatePathAction.py`, shared path list in `forms/common/SelectedPathsMixin.py` and `templates/components/selected-paths.jinja2` |
| File browser selection panel | `services/backend/static/js/path-selection.js`, `templates/files_page.html` |
| Data tabs (listing, search, file and remove routes, allowed file types) | `services/backend/server/routes/htmx/data_browser.py`, `utils/file_browser.py` |
| nginx | `services/nginx/nginx.template.conf`, image with mod_zip `services/nginx/Dockerfile`, dev `services/nginx/nginx.dev.conf.template` |

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
- **File browser Assign and Share:** every path must resolve inside the share root, and Share also requires it to exist. A request with any invalid path saves nothing.
  - Share accepts files and folders, stores each path's resolved location (symlinks followed), and refuses the share root itself and paths longer than 512 characters.
  - Both drop paths inside another submitted path, and take at most 50 paths.

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
