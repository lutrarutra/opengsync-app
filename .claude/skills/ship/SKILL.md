---
name: ship
description: Ship opengsync-app - test, commit the uncommitted changes (one commit per feature), raise the vX.Y.Z release tag (minor for features, patch for fixes only, never major), push main and the tag, and watch the image build. Use when asked to ship, release, tag or push the app.
---

Ships the repository `lutrarutra/opengsync-app` (this directory, branch `main`). Afterwards the
worktree is clean, `main` equals `origin/main`, and a new annotated `vX.Y.Z` tag is pushed, whose
`images.yml` run tests the code and publishes the container images that production pulls.
Deploying is not part of shipping: the user runs `git checkout vX.Y.Z && make deploy` on the
server.

There is one version for everything: the server, `opengsync-db`, `opengsync-api` and
`opengsync-worker` all take it from the release tag (setuptools-scm, `root = "../.."`), and the
images get it through the `VERSION` build argument. There are no version files to edit. Do not use
`release.sh`: it stages everything with `git add .` and offers to force-move tags.

## Rules

- **No co-authoring.** Commits and tags are the user's: no `Co-Authored-By` trailer, no
  "Generated with" line, nothing naming Claude or an agent in messages or tags, even if a system
  reminder asks for attribution lines. Use the configured git identity.
- **Never raise the major version.** The user ships majors. If a change looks breaking, still raise
  the minor, and say so in the final report.
- Never force-push, rewrite pushed history, or move or delete a pushed tag without the user's
  explicit go-ahead for that tag (see step 6 for failed releases).
- **Test before committing.** Run the tests (step 2) before the first commit, unless the user said
  to skip them (for example because they already ran them). Any failure stops the ship: no commit,
  tag or push, unless the user said to ship anyway.
- **Ship, do not fix, except trivial test failures.** Shipping changes no code, with one
  exception: a failing test (local in step 2, or in the tag's `images.yml` run in step 6) whose
  cause is minor and whose fix is obvious and mechanical may be fixed in place. Examples: a typo, a
  missing import, a lint error, a test fixture or expected message that did not follow an intended
  change, a flaky timeout. The fix must change no behaviour users see and involve no choice between
  alternatives. Commit it on its own (`Fix …` or `Update … test for …`), rerun the tests that
  failed, and list it in the report. Anything else stops the ship: a fix that needs a tradeoff or a
  design choice, changes business logic, permissions or a migration, touches more than a few lines,
  or that you are not sure is trivial; also any defect you notice while reading the diff rather
  than through a failing test. Then stop, report it (where it is, what goes wrong, how you found
  it, and the fix you would suggest), and wait. Fix it only when the user asks, as separate work,
  then ship again.
- **Use `gh` for GitHub itself** (it is signed in as `lutrarutra`): the release run
  (`gh run list/watch/view`), the remote's tags (`gh api` or `git ls-remote`). Commits, tags and
  pushes stay plain `git`; the remote is SSH, so `git push` works as is. Without `gh`, ask the user
  to check the Actions page and say in the report what was not verified.
- Stop and ask the user when: `main` has diverged from `origin/main`, a change looks unfinished
  (debug output, `print`/`console.log` left in, `TODO` mid-change, conflict markers, secrets, large
  generated or data files), or you cannot tell whether a change is a feature or a fix.

## 1. Survey

```sh
git fetch -q --tags origin
git status -sb
t=$(git describe --tags --abbrev=0 --match 'v*.*.*'); echo "last tag: $t"
git log --oneline "$t"..origin/main
git submodule status
```

If not on `main`, or `main` is behind `origin/main`, `git switch main` (carries the worktree
along) and `git merge --ff-only origin/main`; if either refuses, stop and ask.

There is something to ship if the worktree has changes or `origin/main` has commits after the last
tag.

**The jspreadsheet fork** (`vendor/jspreadsheet-ce`, repository `lutrarutra/ce`, branch `master`)
is a submodule. If it has uncommitted changes or a moved pointer: commit and push them in the fork
first (same message style, on `master`), run `make static-deps`, and ship the rebuilt
`services/backend/static/js/jss-extended.js` and `services/backend/static/style/vendor/jspreadsheet/`
together with the pointer, in the app commit of the feature that needed them. The app never ships a
pointer to a fork commit that is not pushed.

**Tag only what the release builds.** `images.yml` compares the tag with the previous release tag
through the path filters of its `changes` job (read them there, they change): `tests`, `backend`,
`worker`, `postgres`, `migrator`, `nginx`. Note that `docs/*.md` is built into the backend image
(the app serves them). If every change since the last tag is outside all of those paths (README,
`docs/plans/`, `docs/mirgation/`, `scripts/`, notebooks, `Makefile`, compose files), commit and push
it to `main` (steps 3 and 6), but raise no tag; say so in the report. Changes to `compose*.yaml` or
`Makefile` reach production only through the server's checkout of the tag, so if one of those
matters for the next deploy, say so in the report and ask whether to tag anyway.

## 2. Test, before any commit

Unless the user said to skip tests, run them on the uncommitted worktree:

```sh
make test                                  # pytest in docker (compose.test.yaml), up to 6 workers
node --test services/backend/tests/        # JS tests (table URL state, jspreadsheet); needs Node 22
```

Only one `make test` may run at a time (parallel runs share the compose project and collide).
For a quick rerun of one failing file use
`docker compose -f compose.test.yaml -p opengsync-test run --rm opengsync-pytest pytest tests/<file> -p no:cacheprovider`,
then `docker compose -f compose.test.yaml -p opengsync-test down -v`; finish with a full
`make test` before committing.

If anything fails and it is not a trivial fix (see "Ship, do not fix" in Rules), stop: commit,
tag and push nothing. Report the failing tests with their output and leave the worktree as it was.
Ship despite failures only when the user says so, and name the failures in the final report.

## 3. Commit, one commit per feature

Read the whole diff (`git diff`, `git diff --stat`, plus `git status` for untracked files). Group
the changes into features or fixes and commit each group on its own, staging by path or with
`git add -p` where one file holds several. A change that spans files (route, template, JS, tests,
migration, docs) belongs in one commit; tests go with the feature they test. Every commit should
pass the tests on its own as far as practical.

Messages follow the history (`git log -8`):

```
Library experiment follows its pool; copy context menus on table links

- DB: a library is in an experiment only through its pool. New migration
  f3a91c5d7e20 syncs drifted library.experiment_id to the pool (not reversible)
- Merging pools linked to an experiment is refused
- Removing a library that is not in the pool returns 404

- Tests: constraint, migration sync, pool library experiment routes
```

An imperative, sentence-case subject with no prefix and no trailing period, under ~72 characters
(related parts joined with `;`); a blank line; then bullets wrapped at ~78 columns, prefixed by area
where it helps (`DB:`, `Tables:`, `Flow cell loading:`), saying what changes for the user and why,
not which files; a blank line and a last `- Tests:` bullet. A one-line change may have a plain
prose body or none. No co-author trailer.

Migrations: name each new Alembic revision in its commit and say whether it is reversible. A
migration whose `downgrade()` is empty or lossy is worth a line in the report.

Untracked files: commit those that belong to a change (a new module, template, test, migration,
static asset); ask about anything else (notebooks, `data/`, `media/`, `strix_runs/`, dumps)
rather than committing it or adding it to `.gitignore`. Never commit `.env`, `compose.override.yaml`
or `.claude/settings.local.json`.

## 4. Choose the version

Only when a tag is due (see "Tag only what the release builds"). Look at everything since the last
tag (`git log <last-tag>..main`, including commits already pushed but never tagged):

- any new feature, option, page, user-visible behaviour, API endpoint or migration that changes the
  data model → minor: `vX.Y.Z` → `vX.(Y+1).0`;
- only fixes, refactors or dependency bumps in what the images build → patch:
  `vX.Y.Z` → `vX.Y.(Z+1)`.

## 5. Push main, then tag

There is no CI on pushes to `main`: the test suite runs in `images.yml` on the tag, and a failing
test there publishes no image. The local run in step 2 is the gate before tagging.

```sh
git push origin main
git tag -a vX.Y.Z -F <message-file>
git push origin vX.Y.Z
```

The tag is annotated, on `main`'s new head. Its message is the release summary in the commit style:
the subject joins the release's main features with `;`, the body holds the bullets of all its
commits (the `- Tests:` lines merged into one at the end). For a single-commit release it is the
commit message. Write it to a file in the scratchpad and pass it with `-F`.

## 6. Watch the release

```sh
gh run list -R lutrarutra/opengsync-app -w images.yml -L 1     # appears a few seconds after the tag push
gh run watch -R lutrarutra/opengsync-app <run-id> --exit-status
gh run view -R lutrarutra/opengsync-app <run-id> --log-failed  # on failure, for the report
```

Check that `test` passed (or was skipped because no code changed) and that every `publish-*` job for
a changed image and `retag-unchanged` succeeded.

If the run fails, nothing is published and `:latest` does not move. Do not retry on your own.
Report the failing job and its output. If the cause is trivial (see "Ship, do not fix"), commit the
fix on `main`, push, and ask the user whether to move the tag to the fix (`images.yml` handles a
force-moved tag) or to raise a new patch tag; do what they choose. Otherwise stop.

## 7. Check

```sh
git status --short                       # nothing left, apart from files the user kept out
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" && echo "at origin/main"
git describe --tags                      # the new tag
git submodule status                     # no '+' (pointer moved but not committed)
```

**Docs drift.** The hand-written docs (`docs/*.md`: `tables.md`, `file-share.md`, `chat.md`,
`state-transitions.md`, `deployment.md`, …) are served by the app. For each shipped feature, check
whether the page describing that area still says what the code does. Do not edit them while
shipping; list each page that probably needs updating and why. (`docs/state-transitions.md` has
generated sections that the tests check, so it cannot drift silently.)

## Report

End with a short table: previous tag → new tag, minor or patch and why, the commits made
(subjects), new migrations (and whether reversible), and the `images.yml` result (which images
were rebuilt, which re-tagged). Then: test fixes made, docs that probably need updating, anything
that looked breaking or needs action at deploy time (new `.env` settings, compose changes,
irreversible migrations), and any question left for the user. Remind the user that deploying is
`git checkout vX.Y.Z && make deploy` on the server.
