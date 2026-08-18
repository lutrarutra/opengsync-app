# Template `url_for` audit (Flask → FastAPI)

Compared every `url_for(...)` in `services/opengsync-app/templates/` against:

- Flask-era templates (commit before `69527ef0` “send it”)
- Flask route functions in `packages/opengsync-server/`
- FastAPI route names in `services/backend/server/`

**655** template calls. All live-template mismatches below are resolved (struck through). Flask package `packages/opengsync-server/` still contains old `*_htmx.*` / `*_workflow.*` names as reference.

Legend:

- **Wrong** — FastAPI name exists, but this call site should hit a *different* route (the seq-request clone-all bug).
- **Stale Flask name** — template still uses `*_htmx.*` / `*_workflow.*`; FastAPI has a renamed equivalent.
- **Name mismatch** — close but not the actual FastAPI `name=`.
- **Missing route** — no FastAPI endpoint found; fixing the name is not enough.
- ~~Struck through~~ — template (and any companion route tweak) already updated.

Last reviewed: 2026-08-18.

---

## 1. Wrong: same FastAPI URL used for different Flask endpoints

These were the “many buttons go to the same URL” cases. All three leftover mistakes on `seq_request_page.html` are fixed. Clone (pooled/indexed/raw) was already correct.

| Template | Flask (correct target) | Current (wrong) | FastAPI (correct) |
|---|---|---|---|
| ~~`seq_request_page.html:551` Add Email~~ | ~~`seq_requests_htmx.add_share_email`~~ | ~~`clone_seq_request`~~ | ~~`AddSeqRequestShareEmailAction.Begin`~~ |
| ~~`seq_request_page.html:570` Remove email~~ | ~~`seq_requests_htmx.remove_share_email`~~ | ~~`clone_seq_request`~~ | ~~`remove_seq_request_share_email`~~ |
| ~~`seq_request_page.html:603` Data paths tab~~ | ~~`share_htmx.get_data_paths`~~ | ~~`clone_seq_request`~~ | ~~`render_data_path_table`~~ |

Correct clone buttons (leave these):

| Template | Flask | Current / FastAPI |
|---|---|---|
| `seq_request_page.html:95` Clone (Pooled) | `seq_requests_htmx.clone` + `method='pooled'` | `clone_seq_request` |
| `seq_request_page.html:105` Clone (Indexed) | `seq_requests_htmx.clone` + `method='indexed'` | `clone_seq_request` |
| `seq_request_page.html:115` Clone (Raw) | `seq_requests_htmx.clone` + `method='raw'` | `clone_seq_request` |

Same data-path table is already correct on experiment/library pages (`render_data_path_table`).

---

## 2. Stale Flask `*_htmx.*` / `*_workflow.*` names

Templates still call Flask blueprint endpoints. FastAPI uses the function / form name on the right.

### Search / create / pages

| Current (wrong) | FastAPI (correct) | Where |
|---|---|---|
| ~~`users_htmx.search`~~ | ~~`search_users`~~ | ~~`forms/pool.html`, `forms/experiment.html`, `workflows/merge_pools.html`~~ |
| ~~`sequencers_htmx.search`~~ | ~~`search_sequencers`~~ | ~~`forms/experiment.html`~~ |
| ~~`sequencers_htmx.create`~~ | ~~`SequencerForm.Create`~~ | ~~`devices_page.html`~~ |
| ~~`sequencers_htmx.update`~~ | ~~`SequencerForm.Edit`~~ | ~~`device_page.html`~~ |
| ~~`sequencers_htmx.delete`~~ | ~~`delete_sequencer`~~ | ~~`sequencer_page.html`~~ |
| ~~`sequencers_htmx.get`~~ | ~~`render_sequencer_table`~~ | ~~`sequencers_page.html`~~ |
| ~~`experiments_htmx.create`~~ | ~~`ExperimentForm.Create`~~ | ~~`forms/experiment.html` (POST; GET create on `experiments_page.html` is already correct)~~ |
| ~~`experiments_htmx.browse`~~ | ~~`render_experiment_table` (`browse=billing`)~~ | ~~`workflows/billing/billing.html`~~ |
| ~~`seq_runs_htmx.get`~~ | ~~`render_seq_run_table`~~ | ~~`seq_runs_page.html`~~ |
| ~~`share_htmx.get_share_tokens`~~ | ~~`render_share_token_table`~~ | ~~`share_tokens_page.html`~~ |
| ~~`pools_htmx.get_recent`~~ | ~~`render_pool_feed`~~ | ~~`components/dashboard/pools-feed.html`~~ |
| ~~`protocols_page.protocol`~~ | ~~`protocol_page`~~ | ~~`library_page.html`~~ |

### Auth

| Current (wrong) | FastAPI (correct) | Where |
|---|---|---|
| ~~`auth_htmx.reset_password`~~ | ~~`ResetPasswordForm.ResetPassword`~~ | ~~`reset_password_page.html`~~ |
| ~~`auth_htmx.change_password`~~ | ~~`ChangePasswordForm.Submit`~~ | ~~`forms/auth/change_password.html`~~ |

### Tables / files

| Current (wrong) | FastAPI (correct) | Where |
|---|---|---|
| ~~`img_file`~~ | ~~`serve_media_file` (`media_file_id=`, not `file_id=`)~~ | ~~`components/file-list.html`~~ |
| ~~`files_htmx.render_markdown_file`~~ | ~~`render_markdown_file` (`media_file_id=`, not `file_id=`)~~ | ~~`components/file-list.html`~~ |
| ~~`libraries_htmx.render_feature_table`~~ | ~~`render_feature_table`~~ | ~~`library_page.html`~~ |
| ~~`libraries_htmx.remove_sample`~~ | ~~`remove_sample_from_library`~~ | ~~`components/tables/library-sample.html`~~ |
| ~~`samples_htmx.delete`~~ | ~~`delete_sample`~~ | ~~`sample_page.html`~~ |
| ~~`projects_htmx.remove_assignee`~~ | ~~`remove_project_assignee`~~ | ~~`components/tables/project-assignee.html`~~ |
| ~~`projects_htmx.remove_data_path`~~ | ~~`remove_project_data_path`~~ | ~~`components/tables/project-data_path.html`~~ |
| ~~`api_tokens_htmx.deactivate`~~ | ~~`deactivate_api_token`~~ | ~~`components/tables/user-api_token.html`~~ |
| ~~`seq_requests_htmx.upload_auth_form`~~ | ~~`MediaFileForm.Upload` with `type=SEQ_AUTH_FORM`~~ | ~~`forms/seq_request/seq_auth.html`~~ |
| ~~`index_kits_htmx.edit_barcodes`~~ | ~~`EditKitBarcodesForm.Submit` (POST from the form)~~ | ~~`forms/edit_kit_barcodes.html`~~ |

### Workflow templates still posting to Flask workflow blueprints

Live workflow POSTs are renamed. Unused Flask `select_experiment_pools_workflow.*` template `sp-1.html` is deleted; live UI is `actions/select-experiment-pools.html`.

| Current (wrong) | FastAPI (correct) | Template |
|---|---|---|
| ~~`lane_pools_workflow.lane_pools`~~ | ~~`LanePoolsCombinedAction.Submit` / `LanePoolsSeparateAction.Submit`~~ | ~~`workflows/experiment/lane_pools-1.1.html`, `lane_pools-1.2.html`~~ |
| ~~`load_flow_cell_workflow.load`~~ | ~~`LoadFlowCellCombinedAction.Submit` / `LoadFlowCellSeparateAction.Submit`~~ | ~~`workflows/experiment/load_flow_cell-1.1.html`, `1.2.html`~~ |
| ~~`dist_reads_workflow.submit`~~ | ~~`DistributeReadsCombinedAction.Submit` / `DistributeReadsSeparateAction.Submit`~~ | ~~`workflows/dist_reads/combined.html`, `separate.html`~~ |
| ~~`dilute_pools_workflow.dilute`~~ | ~~`DilutePoolsAction.Submit`~~ | ~~`workflows/dilute_pools/dilute-1.html`~~ |
| ~~`select_experiment_pools_workflow.get_pools`~~ | ~~`render_pool_table` (`browse=select-experiment-pools`)~~ | ~~deleted `workflows/select_experiment_pools/sp-1.html`~~ |
| ~~`select_experiment_pools_workflow.complete`~~ | ~~`SelectExperimentPoolsAction.Submit`~~ | ~~deleted `workflows/select_experiment_pools/sp-1.html`~~ |

---

## 3. Name mismatches (almost FastAPI, not quite)

| Current (wrong) | FastAPI (correct) | Where |
|---|---|---|
| ~~`feature_kit_pages`~~ | ~~`feature_kits_page`~~ | ~~`instructions/oligo-mux.html`, `instructions/feature_annotation.html`~~ |
| ~~`index_kit_pages`~~ | ~~`index_kits_page`~~ | ~~`instructions/barcode_input_prep.html` (`barcode_input.html` is already `index_kits_page`)~~ |
| ~~`group_pages`~~ | ~~`groups_page`~~ | ~~`help.html`~~ |
| ~~`render_seq_request_table_recent`~~ | ~~`render_seq_request_feed`~~ | ~~`dashboard-user.html`, `dashboard-insider.html`~~ |
| ~~`render_api_tokens_table`~~ | ~~`render_api_token_table` (`owner_id=`)~~ | ~~`user_page.html`~~ |
| ~~`render_edit_user_form`~~ | ~~`UserForm.RenderEdit`~~ | ~~`user_page.html`~~ |
| ~~`render_change_password_form`~~ | ~~`ChangePasswordForm.Render`~~ | ~~`user_page.html`~~ |
| ~~`complete_registration_form`~~ | ~~`CompleteRegistrationForm.Begin`~~ | ~~`complete_registration_page.html`~~ |
| ~~`render_project_sample_attributes_form`~~ | ~~`SampleAttributeTableAction.Begin`~~ | ~~`project_page.html`~~ |
| ~~`index_kit_page.html` Edit barcodes~~ | ~~`EditKitBarcodesForm.Begin` (already used; OK)~~ | — |

`help` and `dashboard` are defined on `main.py` as those function names — they resolve. Flask `retrieve_flash_messages` is gone; flash is cookie + `HX-Trigger` in `callbacks.js`.

`share_status_check` and `storage_availability_check` live on `routes/htmx/files.py` (paths `/htmx/files/...`). Dashboard, files page, and share browse `url_for` those names.

---

## 4. Missing FastAPI routes (name in template, no matching endpoint)

These Flask-era names were never given a FastAPI counterpart:

| Template name | Flask | Notes |
|---|---|---|
| ~~`render_project_table_recent`~~ | ~~dashboard recent projects~~ | ~~`render_project_feed`~~ |
| ~~`render_experiment_table_recent`~~ | ~~dashboard recent experiments~~ | ~~`render_experiment_feed`~~ |
| ~~`storage_availability_check`~~ | ~~core route~~ | ~~`htmx/files.py`; used by `dashboard-insider.html`~~ |
| ~~`render_library_table_crispr_guides`~~ | ~~`libraries_htmx.get_crispr_guides`~~ | ~~`GET /htmx/libraries/{id}/crispr-guides`~~ |
| ~~`render_library_table_mux_table`~~ | ~~`libraries_htmx.get_mux_table`~~ | ~~`GET /htmx/libraries/{id}/mux-table`~~ |
| ~~`render_library_table_service_type_todo_libraries`~~ | ~~`libraries_htmx.get_service_type_todo_libraries`~~ | ~~`render_prep_feed_detail`~~ |
| ~~`sequencers_htmx.get`~~ | ~~sequencer table~~ | ~~`render_sequencer_table` on `sequencers_page.html`~~ |
| ~~`seq_runs_htmx.get`~~ | ~~seq-run table~~ | ~~`render_seq_run_table` on `seq_runs_page.html`~~ |
| ~~`samples_htmx.delete`~~ | ~~delete sample~~ | ~~`delete_sample` on `sample_page.html`~~ |
| ~~`api_tokens_htmx.deactivate`~~ | ~~`api_tokens_htmx.deactivate`~~ | ~~`POST /htmx/api-tokens/{id}/deactivate` (`deactivate_api_token`)~~ |
| ~~`projects_htmx.remove_assignee`~~ | ~~remove project assignee~~ | ~~`remove_project_assignee`~~ |
| ~~`projects_htmx.remove_data_path`~~ | ~~remove project data path~~ | ~~`remove_project_data_path`~~ |
| ~~`ChangePasswordForm` GET~~ | ~~`auth_htmx.change_password` GET~~ | ~~added `ChangePasswordForm.Render`~~ |

`render_project_overview` and `render_project_sample_attribute_spreadsheet` **do** exist on FastAPI (`projects.py`).

---

## 5. Already correct (do not change)

These were renamed from Flask and match FastAPI. Included so they are not “fixed” again.

| Pattern | Example |
|---|---|
| Pages | `seq_request_page`, `project_page`, `library_page`, `pool_page`, `experiment_page`, `user_page`, `kit_page`, `feature_kits_page`, `index_kits_page`, `sequencers_page`, … |
| Tables | `render_library_table`, `render_pool_table`, `render_sample_table`, `render_project_table`, `render_data_path_table`, `serve_data_file`, `serve_media_file`, `download_media_file`, `remove_project_data_path` |
| Workflows | `MuxPrepWorkflow.Begin`, `LibraryPoolingWorkflow.Begin`, `ReindexWorkflow.Begin`, `RelibWorkflow.Begin`, `MergePoolsWorkflow.Begin`, `BAReportWorkflow.Begin`, `QubitMeasureWorkflow.Begin`, `LibraryAnnotationWorkflow.Begin`, `ShareProjectDataWorkflow.Begin`, `SelectLibraryProtocolsWorkflow.Begin`, `LaneQCWorkflow.Begin` |
| Actions | `StoreSamplesAction.Begin`, `ReseqAction.Begin`, `ProcessSeqRequestAction.Begin`, `CheckBarcodeClashesAction.Render` / `.SelectSamples`, `MediaFileForm.Upload`, `CommentForm.Begin`, `SeqRequestForm.Edit` / `.Create`, `SelectExperimentPoolsAction.Begin` / `.Submit`, most other `*Action.Begin` |
| Calendar | `events_week`, `events_month`, `events_day` |
| Share / status | `file_share.browse`, `file_share.rclone`, `file_share.rclone_script`, `share_status_check`, `storage_availability_check` |

---

## Suggested fix order

1. ~~**`seq_request_page.html` clone overwrite** (§1) — three call sites, user-visible.~~
2. ~~**Stale Flask names in live pages** (§2 search/auth/files/tables).~~
3. ~~**Workflow POST templates** (§2 last table) — experiment checklist submits.~~
4. ~~**Plural / typo names** (§3).~~
5. ~~**Missing routes** (§4) — CRISPR guides, mux table, API token deactivate.~~
6. ~~Unused `workflows/select_experiment_pools/sp-1.html` deleted.~~

Live templates in `services/opengsync-app/templates/` have no remaining Flask `*_htmx.*` / `*_workflow.*` names. Flask package `packages/opengsync-server/` is still in the repo as reference.
