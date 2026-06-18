# Flask → FastAPI Migration

> **Source:** `packages/opengsync_server/` (Flask) → **Target:** `services/backend/server/` (FastAPI)

---

## Migration Conventions

### HTMX Routes: `routes/htmx/*_htmx.py` → `server/routes/htmx/*.py`

Reference implementations: `projects.py`, `samples.py`, `seq_requests.py`, `users.py`, `experiments.py`

- GET routes render `HTMXTable` or form templates.
- POST/PUT/DELETE routes process actions and return `htmx_response()`.
- Use `selectin()` for eager loading relationships.
- Use `orm.with_expression(Model._hybrid_prop, Model.hybrid_prop.expression)` for hybrid properties (lazy loading is impossible with async sessions).

### Forms: `forms/*_form.py` → `server/forms/*_form.py`

WTForms → custom Pydantic `BaseModel`-based `HTMXForm`. Reference: `ProjectForm`, `LoginForm`, `SeqRequestForm`.

- **GET** route renders the form as an HTMX modal via `form.make_response()`.
- **POST** route processes submission:
  - Two actions per form: static methods `FormClass.create()` and `FormClass.edit()`.
  - Validation errors raise `FormValidationException` → handled in `handlers.py` → re-renders form with errors.
- Input field types: `StringInputField`, `EmailInputField`, `PasswordInputField`, `TextAreaInputField`, `SelectableInputField`, `SearchableInputField`.

### Page Routes: `routes/pages/*_page.py` → `server/routes/pages/*.py`

Reference: `projects.py`, `seq_requests.py`, `groups.py`, `kits.py`, `libraries.py`, `pools.py`, `samples.py`, `users.py`.

- Render full HTML pages via `html_response()`.
- Use permission deps: `require_user`, `require_insider`, `require_admin`.
- Access checks via `*_permissions()` deps (e.g. `project_permissions()`, `seq_request_permissions()`).

### Dependencies (FastAPI DI)

All in `server/core/dependencies.py`:

| Dependency | Purpose |
|---|---|
| `db_session()` | Async DB session |
| `redis()` | Redis client |
| `mail_client()` | Email sender |
| `get_bcrypt()` | Bcrypt hasher |
| `require_user()` | Authenticated user |
| `require_insider()` | Insider role |
| `require_admin()` | Admin role |
| `*_permissions()` | Entity-level access checks (project, seq_request, sample, library, pool, user) |
| `parse_order_by()` | Order-by query param parser |
| `parse_enum_ids()` | Enum ID list query param parser |

### Responses

All in `server/core/responses.py`:

- `html_response(template, **ctx)` — full page render or redirect.
- `htmx_response(template?, redirect?, flash?, **ctx)` — HTMX partial with HX-Trigger/HX-Redirect headers.
- Flash messages specified via `flash=FlashMessage(...)` in the response.

### Workflows: `routes/workflows/*.py` → `server/routes/htmx/workflows/*.py`

Started via `begin_<workflow_name>` route. Multi-step wizards with forms extending `MultiStepForm` (Flask) → to be ported to `HTMXForm` (FastAPI).

---

## Inventory: Flask Blueprints

### Page Routes (18 blueprints)

| Blueprint | File | Endpoints | FastAPI Status |
|---|---|---|---|
| `samples_page_bp` | `routes/pages/samples_page.py` | `/samples`, `/samples/<id>` | Done |
| `libraries_page_bp` | `routes/pages/libraries_page.py` | `/libraries`, `/libraries/<id>` | Done |
| `projects_page_bp` | `routes/pages/projects_page.py` | `/projects`, `/projects/<id>` | Done |
| `pools_page_bp` | `routes/pages/pools_page.py` | `/pools`, `/pools/<id>` | Done |
| `auth_page_bp` | `routes/pages/auth_page.py` | `/auth/`, `/auth/reset_password/<token>`, `/auth/register/<token>` | Done |
| `experiments_page_bp` | `routes/pages/experiments_page.py` | `/experiments`, `/experiments/<id>` | Done |
| `users_page_bp` | `routes/pages/users_page.py` | `/users`, `/users/<id>` | Done |
| `lab_preps_page_bp` | `routes/pages/lab_preps_page.py` | `/lab_preps`, `/lab_preps/<id>` | Done |
| `seq_runs_page_bp` | `routes/pages/seq_runs_page.py` | `/seq_runs`, `/seq_runs/<id>` | Done |
| `seq_requests_page_bp` | `routes/pages/seq_requests_page.py` | `/seq_requests`, `/seq_requests/<id>` | Done |
| `devices_page_bp` | `routes/pages/devices_page.py` | `/devices`, `/devices/<id>` | Done |
| `kits_page_bp` | `routes/pages/kits_page.py` | `/kits`, `/kits/<id>`, `/index_kits`, `/index_kits/<id>`, `/feature_kits`, `/feature_kits/<id>`, `/feature_kits/<id>/export` | Done |
| `share_tokens_page_bp` | `routes/pages/share_tokens_page.py` | `/share_tokens`, `/share_tokens/<id>` | Done |
| `protocols_page_bp` | `routes/pages/protocols_page.py` | `/protocols`, `/protocols/<id>` | Done |
| `design_page_bp` | `routes/pages/design_page.py` | `/design` | Done |
| `groups_page_bp` | `routes/pages/groups_page.py` | `/groups`, `/groups/<id>` | Done |
| `browser_page_bp` | `routes/pages/browser_page.py` | `/browser/`, `/browser/<path:subpath>` | Done |
| `admin_pages_bp` | `routes/pages/admin_page.py` | `/admin` | Done |

### HTMX Route Blueprints (24 blueprints)

| Blueprint | File | FastAPI Status |
|---|---|---|
| `samples_htmx` | `routes/htmx/samples_htmx.py` | Mostly done (table page) |
| `projects_htmx` | `routes/htmx/projects_htmx.py` | Mostly done (crud, export, overview) |
| `experiments_htmx` | `routes/htmx/experiments_htmx.py` | Partial (table only) |
| `pools_htmx` | `routes/htmx/pools_htmx.py` | **Not started** |
| `auth_htmx` | `routes/htmx/auth_htmx.py` | Mostly done |
| `barcodes_htmx` | `routes/htmx/barcodes_htmx.py` | **Not started** |
| `seq_requests_htmx` | `routes/htmx/seq_requests_htmx.py` | Partial (table, create, edit, add-assignee) |
| `sequencers_htmx` | `routes/htmx/sequencers_htmx.py` | **Not started** |
| `users_htmx` | `routes/htmx/users_htmx.py` | Mostly done |
| `libraries_htmx` | `routes/htmx/libraries_htmx.py` | **Not started** |
| `feature_kits_htmx` | `routes/htmx/feature_kits_htmx.py` | **Not started** |
| `index_kits_htmx` | `routes/htmx/index_kits_htmx.py` | **Not started** |
| `plates_htmx` | `routes/htmx/plates_htmx.py` | **Not started** |
| `lanes_htmx` | `routes/htmx/lanes_htmx.py` | **Not started** |
| `seq_runs_htmx` | `routes/htmx/seq_runs_htmx.py` | **Not started** |
| `files_htmx` | `routes/htmx/files_htmx.py` | **Not started** |
| `lab_preps_htmx` | `routes/htmx/lab_preps_htmx.py` | Partial (create only) |
| `events_htmx` | `routes/htmx/events_htmx.py` | Stubs only |
| `groups_htmx` | `routes/htmx/groups_htmx.py` | **Not started** |
| `kits_htmx` | `routes/htmx/kits_htmx.py` | **Not started** |
| `share_htmx` | `routes/htmx/share_htmx.py` | **Not started** |
| `protocols_htmx` | `routes/htmx/protocols_htmx.py` | **Not started** |
| `api_tokens_htmx` | `routes/htmx/api_tokens_htmx.py` | **Not started** |
| `design_htmx` | `routes/htmx/design_htmx.py` | **Not started** |

### Workflow Blueprints (26 blueprints) — **All stubs**

`select_experiment_pools`, `select_pool_libraries`, `share_project_data`, `billing`, `add_kits_to_protocol`, `select_library_protocols`, `merge_projects`, `library_annotation`, `lane_pools`, `ba_report`, `dilute_pools`, `check_barcode_clashes`, `lane_qc`, `load_flow_cell`, `qubit_measure`, `store_samples`, `library_pooling`, `library_prep`, `mux_prep`, `dist_reads`, `reindex`, `reseq`, `merge_pools`, `library_remux`, `relib`, `check_barcode_constraints`

---

## Form Inventory

### Already Ported (9)

| Form | File | Status |
|---|---|---|
| `ProjectForm` | `server/forms/models/ProjectForm.py` | Done |
| `SeqRequestForm` | `server/forms/models/SeqRequestForm.py` | Done |
| `UserForm` | `server/forms/models/UserForm.py` | Done |
| `LabPrepForm` | `server/forms/models/LabPrepForm.py` | Done |
| `LoginForm` | `server/forms/auth/LoginForm.py` | Done |
| `RegisterForm` | `server/forms/auth/RegisterForm.py` | Done |
| `CompleteRegistrationForm` | `server/forms/auth/CompleteRegistrationForm.py` | Done |
| `ChangePasswordForm` | `server/forms/auth/ChangePasswordForm.py` | Done |
| `APITokenForm` | `server/forms/auth/APITokenForm.py` | Done |

### Not Yet Ported — Model Forms (16)

| Flask | FastAPI target |
|---|---|
| `SampleForm` | `server/forms/models/SampleForm.py` |
| `ExperimentForm` | `server/forms/models/ExperimentForm.py` |
| `PoolForm` | `server/forms/models/PoolForm.py` |
| `SeqRunForm` | `server/forms/models/SeqRunForm.py` |
| `PlateForm` | `server/forms/models/PlateForm.py` |
| `GroupForm` | `server/forms/models/GroupForm.py` |
| `IndexKitForm` | `server/forms/models/IndexKitForm.py` |
| `FeatureKitForm` | `server/forms/models/FeatureKitForm.py` |
| `KitForm` | `server/forms/models/KitForm.py` |
| `ProtocolForm` | `server/forms/models/ProtocolForm.py` |
| `PoolDesignForm` | `server/forms/models/PoolDesignForm.py` |
| `FlowCellDesignForm` | `server/forms/models/FlowCellDesignForm.py` |
| `TODOCommentForm` | `server/forms/models/TODOCommentForm.py` |
| `LibraryForm` | `server/forms/models/LibraryForm.py` |
| `SequencerForm` | `server/forms/models/SequencerForm.py` |
| `APITokenForm` (model) | `server/forms/models/APITokenForm.py` |

### Not Yet Ported — Auth Forms (1)

| Flask | FastAPI target |
|---|---|
| `ResetPasswordForm` | `server/forms/auth/ResetPasswordForm.py` |

### Not Yet Ported — Comment/File Forms (8)

| Flask | FastAPI target |
|---|---|
| `CommentForm` | `server/forms/CommentForm.py` |
| `ExperimentCommentForm` | `server/forms/ExperimentCommentForm.py` |
| `SeqRequestCommentForm` | `server/forms/SeqRequestCommentForm.py` |
| `LabPrepCommentForm` | `server/forms/LabPrepCommentForm.py` |
| `FileInputForm` | `server/forms/FileInputForm.py` |
| `ExperimentAttachmentForm` | `server/forms/ExperimentAttachmentForm.py` |
| `SeqRequestAttachmentForm` | `server/forms/SeqRequestAttachmentForm.py` |
| `LabPrepAttachmentForm` | `server/forms/LabPrepAttachmentForm.py` |

### Not Yet Ported — Misc/Specialty Forms (17)

| Flask | FastAPI target |
|---|---|
| `MultiStepForm` | `server/forms/MultiStepForm.py` |
| `SubmitSeqRequestForm` | `server/forms/SubmitSeqRequestForm.py` |
| `SampleAttributeTableForm` | `server/forms/SampleAttributeTableForm.py` |
| `SeqAuthForm` | `server/forms/SeqAuthForm.py` |
| `LibraryFeaturesForm` | `server/forms/LibraryFeaturesForm.py` |
| `AddSeqRequestAssigneeForm` | `server/forms/AddSeqRequestAssigneeForm.py` |
| `ProcessRequestForm` | `server/forms/ProcessRequestForm.py` |
| `SelectSamplesForm` | `server/forms/SelectSamplesForm.py` |
| `AddUserToGroupForm` | `server/forms/AddUserToGroupForm.py` |
| `SeqRequestShareEmailForm` | `server/forms/SeqRequestShareEmailForm.py` |
| `AddProjectAssigneeForm` | `server/forms/AddProjectAssigneeForm.py` |
| `EditKitFeaturesForm` | `server/forms/EditKitFeaturesForm.py` |
| `QueryBarcodeSequencesForm` | `server/forms/QueryBarcodeSequencesForm.py` |
| `LibraryPropertyForm` | `server/forms/LibraryPropertyForm.py` |
| `LibraryPropertiesForm` | `server/forms/LibraryPropertiesForm.py` |
| `SearchBar` | `server/forms/SearchBar.py` |
| `DirectoryShareForm` | `server/forms/DirectoryShareForm.py` |
| `SequencerLoadingChecklistForm` | `server/forms/SequencerLoadingChecklistForm.py` |

### Not Yet Ported — Workflow Forms (~50+)

Organized under `server/forms/workflows/`:

| Subdirectory | Forms |
|---|---|
| `share/` | `ShareProjectDataForm`, `AssociatePathForm` |
| `lane_pools/` | `LanePoolingForm`, `UnifiedLanePoolingForm` |
| `remux/` | `FlexReMuxForm`, `OligoReMuxForm` |
| `reindex/` | `BarcodeInputForm`, `TENXATACBarcodeInputForm`, `CompleteReindexForm`, `BarcodeMatchForm` |
| `common/` | `CommonBarcodeInputForm`, `CommonTENXATACBarcodeInputForm`, `CommonBarcodeMatchForm`, `CommonFlexMuxForm`, `CommonFlexABCForm`, `CommonOligoMuxForm`, `CommonFeatureAnnotationForm` |
| `library_annotation/` | `LibraryAnnotationWorkflow`, `FeatureAnnotationForm`, `SampleAnnotationForm`, `SampleAttributeAnnotationForm`, `FlexAnnotationForm`, `OligoMuxAnnotationForm`, `OCMAnnotationForm`, `VisiumAnnotationForm`, `OpenSTAnnotationForm`, `CustomAssayAnnotationForm`, `PooledLibraryAnnotationForm`, `BarcodeMatchForm`, `BarcodeInputForm`, `TENXATACBarcodeInputForm`, `ProjectSelectForm`, `SelectServiceForm`, `DefineMultiplexedSamplesForm`, `PoolMappingForm`, `CompleteSASForm`, `ParseMuxAnnotationForm`, `ParseCRISPRGuideAnnotationForm` |
| `library_pooling/` | `LibraryPoolingForm`, `CompleteLibraryPoolingForm` |
| `library_prep/` | `LibraryPrepForm` |
| `ba_report/` | `UploadBAForm`, `ParseBAExcelFile`, `CompleteBAForm` |
| `mux_prep/` | `FlexMuxForm`, `FlexABCForm`, `OligoMuxForm`, `OCMMuxForm`, `SamplePoolingForm` |
| `load_flow_cell/` | `LoadFlowCellForm`, `UnifiedLoadFlowCellForm` |
| `qubit_measure/` | `CompleteQubitMeasureForm` |
| `dilute_pools/` | `DilutePoolsForm` |
| `check_barcode_clashes/` | `CheckBarcodeClashesForm` |
| `reseq/` | `ReseqLibrariesForm` |
| `relib/` | `LibraryEditTableForm` |
| `billing/` | `SelectExperimentsForm` |
| `edit_kit_barcodes/` | `EditSingleIndexKitBarcodesForm`, `EditDualIndexKitBarcodesForm`, `EditCombinatorialKitBarcodesForm`, `EditKitTENXATACBarcodesForm` |
| `select_library_protocols/` | `LibraryProtocolSelectForm`, `ProtocolMappingForm` |
| `add_protocol_kits/` | `AddKitCombinationsFrom` |

---

## Migration Plan

### Phase 1 — Core HTMX CRUD (Priority: High)

Frequently used entity routes. Each module needs both the form and the full HTMX route file.

#### 1a. Pools
- **Form:** `PoolForm` (create/edit)
- **Routes:** table, search, create, edit, delete, clone, `get_form`, remove_libraries, plate, dilutions, browse, recent

#### 1b. Libraries
- **Form:** `LibraryForm`
- **Routes:** table, search, edit, features, crispr_guides, reads, browse, select_all, remove_sample, mux_table, todo_libraries, properties, edit_properties, edit_features

#### 1c. Experiments (complete routes)
- **Missing routes:** create, edit, delete, search, set_cycles, lane_pool/unlane_pool, comment_form, file_form, delete_file, add_comment, remove_pool, overview, comments, files, stats, checklist, browse, dilutions, sequencer_loading_checklist, recent
- **Forms needed:** `ExperimentForm`, `ExperimentCommentForm`, `ExperimentAttachmentForm`, `SequencerLoadingChecklistForm`, `EditExperimentCyclesForm`

#### 1d. Seq Requests (complete routes)
- **Missing routes:** search, export, delete, archive/unarchive, submit, upload_auth_form, comment_form, file_form, delete_file, remove_auth_form, remove_library, reseq_library, remove_sample, remove_all_libraries, process, add_share_email, remove_share_email, overview, comments, files, clone, store_samples, assignees (add/remove/form), submit_checklist, review_checklist, sample_table, confirm_barcodes
- **Forms needed:** `SubmitSeqRequestForm`, `SeqAuthForm`, `SeqRequestCommentForm`, `SeqRequestAttachmentForm`, `SeqRequestShareEmailForm`, `AddSeqRequestAssigneeForm`, `ProcessRequestForm`

#### 1e. Projects (complete routes)
- **Missing routes:** search, render_sample_table, edit_sample_attributes, get_recent, assignees (add/remove/form), remove_data_path
- **Forms needed:** `SampleAttributeTableForm`, `AddProjectAssigneeForm`

---

### Phase 2 — Insider-Only HTMX CRUD (Priority: Medium)

#### 2a. Seq Runs
- **Form:** `SeqRunForm`
- **Routes:** table, search, create, edit, delete

#### 2b. Lab Preps (complete routes)
- **Missing routes:** table, search, edit, delete, comment, files
- **Forms needed:** `LabPrepCommentForm`, `LabPrepAttachmentForm`

#### 2c. Kits / Index Kits / Feature Kits
- **Forms:** `KitForm`, `IndexKitForm`, `FeatureKitForm`
- **Routes:** table, search, create, edit, delete for each
- **Extra forms:** `EditKitFeaturesForm`, `LibraryFeaturesForm`, `LibraryPropertyForm`, `LibraryPropertiesForm`

#### 2d. Groups
- **Form:** `GroupForm`
- **Routes:** table, create, edit, delete, add/remove users
- **Extra form:** `AddUserToGroupForm`

#### 2e–2n. Remaining Modules
| Module | Form | Notes |
|---|---|---|
| Sequencers | `SequencerForm` | Table, search, create, edit, delete |
| Protocols | `ProtocolForm` | Table, create, edit, delete |
| Plates | `PlateForm` | Table, create, edit, delete |
| Lanes | — | Experiment sub-resource |
| Share Tokens | `DirectoryShareForm` | Read-only table done; need assign/revoke |
| Barcodes | `QueryBarcodeSequencesForm` | Table, query |
| API Tokens | `APITokenForm` (model) | CRUD |
| Design | `PoolDesignForm`, `FlowCellDesignForm` | CRUD |
| Events | — | Stubs to implement |
| Files | — | Upload/download/delete |

---

### Phase 3 — Workflows (Priority: Medium-Low)

All 24 workflow modules are stubs. Each needs form porting + route implementation.

Most complex workflows (ordered by effort):

| Workflow | Forms to port | Complexity |
|---|---|---|
| library_annotation | ~20 forms | Very High |
| reindex | ~6 forms | High |
| mux_prep | ~5 forms | High |
| library_pooling | ~3 forms | Medium |
| load_flow_cell | ~2 forms | Medium |
| lane_pools | ~2 forms | Medium |
| select_library_protocols | ~2 forms | Medium |
| add_kits_to_protocol | ~1 form | Medium |
| ba_report | ~3 forms | Medium |
| share_project_data | ~2 forms | Medium |
| library_remux | ~2 forms | Medium |
| billing | ~1 form | Low |
| reseq | ~1 form | Low |
| relib | ~1 form | Low |
| dilute_pools | ~1 form | Low |
| qubit_measure | ~1 form | Low |
| merge_pools | ~1 form | Low |
| merge_projects | ~1 form | Low |
| store_samples | ~1 form | Low |
| check_barcode_clashes | ~1 form | Low |
| check_barcode_constraints | ~1 form | Low |
| dist_reads | ~1 form | Low |
| lane_qc | ~1 form | Low |
| select_experiment_pools | ~1 form | Low |
| select_pool_libraries | ~1 form | Low |

---

## Appendix: Key Differences to Remember

1. **Async sessions** — all DB queries must use `await`, no lazy loading. Use `selectin()` and `orm.with_expression()` for hybrid properties.
2. **No Flask globals** — `request`, `session`, `current_user`, `g` are gone. Use FastAPI DI or `ctx.request` / `ctx.current_user`.
3. **No WTForms** — all forms extend `HTMXForm` with `InputField` class attributes → dynamic Pydantic model generation.
4. **No `url_for` string lookups** — use `url_for()` from `responses.py` or `ctx.url_for()`.
5. **Permissions are explicit** — use `*_permissions()` dependency functions, not ad-hoc checks.
6. **Flash messages** — set via `flash=FlashMessage(...)` in `htmx_response()` or `html_response()`, not Flask's `flash()`.
7. **Cache invalidation** — use `invalidate_cache()` dependency (appends keys, deleted after request), not Flask-Caching decorators.
8. **Workflow prefix** — Flask: `routes/workflows/` → FastAPI: `server/routes/htmx/workflows/`.
