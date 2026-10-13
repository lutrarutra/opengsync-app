# FastAPI Forms, Actions, and Workflows Test TODO

> Scope: `services/backend/server/forms/` and the HTTP behavior exposed by each router.
>
> Testing convention: each checkbox should become at least one focused test. Add separate tests for happy path, invalid input, authorization, CSRF, persistence/rollback, response status/headers, and duplicate/replay submissions where applicable.
>
> Existing coverage (see Progress for the current list) lives in `services/pytest/tests/server/forms/auth/` (login, register, complete registration, change password, reset password, API token), `server/forms/test_htmx_form.py`, `server/forms/test_sub_htmx_form.py`, `server/forms/test_seq_request_form.py`, `server/forms/test_project_form.py`, `server/forms/test_sample_form.py`, `server/forms/test_library_form.py`, `server/forms/test_experiment_form.py`, `server/test_forms.py`, `server/test_access.py`, `server/workflows/test_htmx_workflow.py`, and `server/workflows/` (library annotation, relib, split project, lane QC).

## Progress (2026-10-12)

- `tests/server/forms` + `tests/server/workflows` + `test_action_access.py` + `tests/db`: 1440 passed; all of `tests/server`: 2118 passed, 6 strict xfails (unported lane-step templates). Full suite not rerun for this snapshot.
- §3 actions with suites: assignees (project, request), share email, process/submit request, add user to group, merge projects, sample attribute table, store samples, library prep, select pool libraries, check barcode clashes, select experiment pools, query barcode sequences, set cycles, sequencer loading checklist, billing, library features, sample pooling, add kits to protocol, barcode constraints, upload prep table, edit kit features, edit kit barcodes (all four variants), edit library properties. Partial: share directory, associate path, lane pools / read distribution / flow-cell loading (routing + access only).
- §3 actions without suites: `ReseqAction` and `DilutePoolsAction` (templates not ported).
- Cross-cutting: `test_action_access.py` (every insider/admin-only action and workflow, dependency check + client GET), `test_route_shadowing.py`, `test_share_root_abuse.py`.
- §4 order agreed 2026-10-13: `LibraryPoolingWorkflow` (done), `MuxPrepWorkflow` (done), `ReindexWorkflow` (done), `QubitMeasureWorkflow` (done), `BAReportWorkflow` (done).
- Done 2026-10-13: `LibraryRemuxWorkflow`; `SelectExperimentPoolsWorkflow` and `MergeProjectsWorkflow` are re-exports of tested actions.
- Next: `SelectLibraryProtocolsWorkflow`; then leftovers in relib, lane QC, split project, share project data; `MergePoolsWorkflow` once its template is ported.

## 0. Shared test infrastructure

- [x] Add reusable authenticated-client fixtures for anonymous user, normal user, second user, insider, and admin.
- [ ] Add reusable database fixtures/factories for every model used by forms and actions. *(Partial: 22 factories in `db/create_units.py` — user, project, contact, seq request, sample, library, pool, feature, feature kit, sequencer, experiment, file, group, kit, index kit, protocol, seq run, pool design, flow-cell design, TODO comment, plate, lab prep. Lanes (and lane–pool links) are still missing.)*
- [x] Add helpers for GET form rendering, POST validation, CSRF failure, HTMX headers, redirects, flash messages, and database assertions.
- [x] Add tests for `HTMXForm` route registration and generated endpoint names. *(`forms/test_htmx_form.py`: route collection, default paths, inheritance/override, `Router()` names and prefixes, app registry + `url_path_for` resolution.)*
- [x] Add tests for `HTMXForm.Init()` and `HTMXForm.Validate()` dependency behavior. *(Fresh isolated instances; CSRF cookie/field matching, missing cookie, non-POST/PUT rejection, required-field and Pydantic length errors, value preservation, error clearing.)*
- [x] Add tests for `HTMXForm.make_response()` and invalid-form re-rendering. *(Covered through the form endpoint suites: GET renders with CSRF token, invalid POST re-renders with 202 and preserved values.)*
- [x] Add tests for `SubHTMXForm` field collection, nested errors, and Pydantic validation.
- [ ] Add tests for form transaction rollback after validation and unexpected exceptions.
- [x] Add tests for `HTMXWorkflow` state isolation, Redis serialization, expiration, cleanup, and concurrent UUIDs. *(`workflows/test_htmx_workflow.py`: UUID generation/preservation, key prefixes, table/JSON/header round trips, cross-workflow isolation, TTL, `complete()` scoping, step tracker, previous-URL, copy on step switch, forward-navigation replacement.)*
- [x] Add tests for `HTMXWorkflowStep.is_applicable()` and conditional step navigation. *(Default true, override false, active-step switching. Conditional navigation itself is exercised by the workflow suites.)*
- [ ] Add tests for `BarcodeInputMixin` normalization, invalid sequences, duplicate barcodes, and reverse-complement behavior. *(Needs a session-backed workflow context; the barcode-input branches are partially exercised by the library-annotation workflow tests.)*



## 1. Authentication forms



### `LoginForm`

- [x] Valid login.
- [x] Unknown email.
- [x] Wrong password.
- [x] Suspended user.
- [x] Inactive/unverified user.
- [x] Already authenticated user.
- [x] Missing fields and malformed email.
- [x] GET form rendering.
- [x] CSRF failure.
- [x] HTMX response versus browser redirect.



### `RegisterForm`

- [x] Valid registration.
- [x] Duplicate email.
- [x] Invalid email.
- [x] Password mismatch. *(N/A — form has no password fields.)*
- [x] Password length/complexity failures. *(N/A — form has no password fields.)*
- [x] Required-field and maximum-length failures. *(Required email covered; form does not set email max_length.)*
- [x] Registration token/invitation validation, if applicable.
- [x] CSRF failure.
- [x] Persistence and rollback on failure.



### `CompleteRegistrationForm`

- [x] Valid completion with a valid registration token.
- [x] Expired token.
- [x] Unknown or already-used token.
- [x] Password mismatch and invalid password.
- [x] Duplicate/invalid user state.
- [x] CSRF failure.
- [x] Account activation persistence.



### `ChangePasswordForm`

- [x] Valid password change.
- [x] Incorrect current password.
- [x] New-password mismatch.
- [x] New password equal to old password, if prohibited. *(N/A — current logic does not prohibit reuse.)*
- [x] Invalid password and missing fields.
- [x] Anonymous-user rejection.
- [x] CSRF failure.
- [x] Session/token behavior after password change. *(Cookie deletion covered; JWT revocation is not implemented.)*



### `ResetPasswordForm`

- [x] Valid reset request/token.
- [x] Expired token.
- [x] Unknown token.
- [x] Already-used token.
- [x] Password mismatch and invalid password.
- [x] Unknown email behavior without account enumeration. *(N/A — the reset request route is user-ID based; unknown user returns 404.)*
- [x] CSRF failure.
- [x] Password persistence and token invalidation.



### `APITokenForm`

- [x] Render token form for an authenticated user.
- [x] Create token.
- [x] Duplicate token/name behavior. *(N/A — tokens are UUID-only; there is no name field.)*
- [x] Empty/invalid token name. *(N/A — no name field; invalid `time_valid_min` covered instead.)*
- [x] Deactivate active token.
- [x] Deactivate already-inactive token.
- [x] Cannot access another user’s token.
- [x] CSRF failure.
- [x] Token value visibility and response behavior.



## 2. Model forms

For every model form below, test **create**, **edit**, **missing/invalid ID**, **unauthorized access**, **validation failure**, **CSRF**, **persistence**, **rollback**, and **response redirect/flash**. Where create or edit is intentionally unsupported, test that the route is absent or returns a controlled error rather than a traceback.

### `ProjectForm`

- [x] Create project.
- [x] Edit project.
- [x] Duplicate owner/title validation.
- [x] Identifier uniqueness and format. *(Uniqueness covered. No format/pattern validation exists in either the legacy or FastAPI form — identifier is free text up to 16 chars with a `BSA_XXXX` placeholder.)*
- [x] Required, minimum, and maximum lengths. *(Required + max covered. Legacy `title` had `min_length=6` and required `description`; the FastAPI form dropped both — see findings.)*
- [x] Owner/group/assignee permissions. *(Create: non-insiders may only set themselves as owner; edit: owner/status/identifier changes are insider-only; group membership enforced server-side. Project assignees are handled by `AddProjectAssigneeAction` in §3.)*
- [x] Editing another user’s project. *(GET and POST edit both 403 for strangers; the GET previously had no permission check at all.)*
- [x] Draft versus non-draft edit behavior. *(Non-draft projects grant owners only READ, so GET/POST edit is 403 for them; non-insiders cannot change status on drafts.)*

Open findings from `ProjectForm` tests:

- The `group` field is declared on the form but **not rendered** by `forms/project.html` (the legacy Flask template did not render it either), so group validation is only reachable via a direct POST.
- Legacy enforced `title` `min_length=6` and a required `description`; the FastAPI form accepts shorter titles and an optional description.
- Legacy gave insiders an additional cross-owner title uniqueness check; the FastAPI form scopes title uniqueness to the owner.



### `SampleForm`

- [x] Create sample. *(N/A — `SampleForm` is edit-only. Samples are created by the library-annotation and sequencing-request flows; there is no create route.)*
- [x] Edit sample.
- [x] Project ownership/access checks. *(Read gate via `sample_permissions`: strangers 403, project owner/group member/insider allowed; edit stays allowed on non-draft projects, matching the legacy READ gate.)*
- [x] Duplicate sample-name behavior within a project. *(Same name in the same project rejected; same name in another project and keeping the sample's own name allowed.)*
- [x] Genome/reference validation. *(Belongs to `LibraryForm` (`genome_ref`) — not a `SampleForm` field.)*
- [x] Required and maximum-length fields. *(Required, min 3, max 64. Legacy used `min_length=6`.)*
- [x] Library/project relationship persistence. *(Sample↔library links are created by the library-annotation/seq-request flows and `SampleAttributeTableAction`, not by this form.)*



### `LibraryForm`

- [x] Create library. *(N/A — `LibraryForm` is edit-only. Libraries are created by the library-annotation, library-prep, remux, and reindex flows.)*
- [x] Edit library.
- [x] Library type/status validation. *(Type and status persist; changing the type now re-derives the display name from the new type identifier.)*
- [x] Sample, project, and sequence-request access checks. *(Access is derived from the sequencing request: WRITE requires a DRAFT request owned by or shared with the viewer, matching the legacy route — strangers and owners of submitted requests get 403/404; group members and insiders allowed.)*
- [x] Indexed/unindexed state behavior. *(`index_type` is not editable here and is preserved across edits; indexing is handled by the barcode/reindex workflows.)*
- [x] Invalid relationship IDs. *(N/A — the form has no relationship inputs.)*
- [x] Protected status transition behavior. *(No transition guard: any `LibraryStatus` can be set while the request is DRAFT. Access is request-based, so unlike legacy `edit_properties` there is no non-draft/insider restriction here.)*

Open findings from `LibraryForm` tests:

- The display name is `"{sample_name}_{type.identifier}"`; the form caps `sample_name` at 64 (the `sample_name` column) while `name` allows 86, so a long sample name plus a long identifier can still exceed the `name` column. Legacy capped at 86 (which overran the 64-char `sample_name` column instead).



### `SeqRequestForm`

- [x] Create sequencing request.
- [x] Edit draft request.
- [x] Required contact, submission-type, and metadata fields.
- [x] Invalid project/user relationships (mixed/partial manual details, duplicate email).
- [x] Billing-contact/persist and PI-contact round-trip.
- [x] Insider-assigned requestor and deactivated-user requestor.
- [x] Optional fields omitted on create keep legacy defaults.



### `LabPrepForm`

- [x] Create lab prep (auto-named, explicit name, prep number increments).
- [x] Edit lab prep (name, service type; checklist type cannot change).
- [x] Required name/type fields.
- [x] Insider-only create and edit.
- [x] CSRF; 404.



### `ExperimentForm`

- [x] Create experiment. *(Insider-only; lanes are created for the workflow's flow cell.)*
- [x] Edit experiment.
- [x] Sequencer/operator selection. *(Both resolved against the DB — unknown ids return a controlled `404` (via `session.get_one`) instead of a foreign-key `500`.)*
- [x] Workflow and lane configuration validation. *(Changing the workflow resizes lanes via the `Experiment.workflow` listener: grows to the new flow cell's lane count and trims lanes beyond it.)*
- [x] Invalid status transitions. *(No transition guard — any `ExperimentStatus` is accepted, matching the legacy form. `can_be_edited = status < SEQUENCING` exists only on the checklist route and is not enforced here.)*
- [x] Insider/admin permission variants. *(`require_insider` on GET/POST create and edit; clients get 403. Legacy parity.)*
- [x] Deleteability interaction with form state. *(Deletion is a separate route gated on `experiment.is_deleteable()` (admin override); the edit form does not depend on it.)*

Open findings from `ExperimentForm` tests:

- Legacy enforced `min_length=3` on the experiment name; the FastAPI form has no minimum.
- Cycles (`r1`/`r2`/`i1`/`i2`) accept any integer — no non-negative or platform-specific bounds, in either implementation.
- Editing an experiment that is already `SEQUENCING`/`SEQUENCED` is allowed (insider-only), matching legacy.



### `PoolForm`

- [x] Create draft pool (with contact fields, existing user as contact).
- [x] Edit draft pool.
- [x] Clone pool (insider-only; rejects changed pool type).
- [x] Name required, min/max length.
- [x] Contact name/email required when no user selected.
- [x] Unknown contact user falls back to manual contact.
- [x] CSRF; 404.



### `PlateForm`

**Deleted** — `PlateForm.py` was dead code. Its routes at `/htmx/pools/create` were shadowed by `PoolForm`, and no frontend code referenced it. Removed entirely.



### `GroupForm`

- [x] Create group.
- [x] Edit group.
- [x] Duplicate group name.
- [x] WRITE permission for edit (group_permissions + affiliation).
- [x] Any user can create (require_user).
- [x] CSRF; 404.



### `UserForm`

- [x] Edit own name; cannot change own role or email.
- [x] Edit another user denied for non-owner/stranger.
- [x] Insider can change name; cannot change role or email.
- [x] Admin can change name, role, and email.
- [x] CSRF; 404.

*Create is N/A — `UserForm` is edit-only. New users are created via `RegisterForm` (auth).*



### `CommentForm`

Test each target context separately:

- [x] Create comment on a sequencing request.
- [x] WRITE permission check.
- [x] Empty comment rejected.
- [x] Missing context returns error.
- [x] CSRF; 404.



### `TODOCommentForm`

- [x] Create TODO on pool design.
- [x] Edit TODO comment.
- [x] Insider-only.
- [x] Pool design context via query param.
- [x] CSRF; 404.



### `MediaFileForm`

Test each attachment context separately:

- [x] Upload file to a sequencing request.
- [x] WRITE permission check.
- [x] Missing context returns error.
- [x] CSRF; 404.



### `ProtocolForm`

- [x] Create protocol.
- [x] Edit protocol.
- [x] Duplicate name.
- [x] Required name min_length=6.
- [x] Insider-only create/edit; render edit no auth gate.
- [x] CSRF; 404.



### `FlowCellDesignForm`

- [x] Edit design (edit-only form).
- [x] Insider-only.
- [x] CSRF; 404.



### `PoolDesignForm`

- [x] Create pool design.
- [x] Edit pool design.
- [x] Insider-only.
- [x] Cycle counts required.
- [x] CSRF; 404.



### `FeatureKitForm`

- [x] Create feature kit.
- [x] Edit feature kit.
- [x] Duplicate identifier.
- [x] Feature type_id cannot change on edit.
- [x] Admin/insider permissions.
- [x] CSRF; 404.



### `IndexKitForm`

- [x] Create index kit.
- [x] Edit index kit.
- [x] Duplicate name/identifier.
- [x] Insider permissions.
- [x] CSRF; 404.



### `KitForm`

- [x] Create kit.
- [x] Edit kit.
- [x] Duplicate name/identifier.
- [x] Hash/comma validation.
- [x] Insider permissions.
- [x] CSRF; 404.



### `SeqRunForm`

- [x] Create seq run.
- [x] Edit seq run.
- [x] Insider-only create/edit; render edit no auth gate.
- [x] CSRF; 404.



### `SequencerForm`

- [x] Create sequencer.
- [x] Edit sequencer.
- [x] Duplicate name.
- [x] Insider required for create/edit; render edit no auth.
- [x] CSRF; 404.



## 3. Standalone actions

For every action, test GET/render, valid POST, invalid POST, CSRF, authorization, persistence, rollback, duplicate/replay behavior, response status, redirect, flash, and HX headers. Add target-context variants where listed.

### Request, project, group, and sharing actions

- [x] `AddProjectAssigneeAction`: add valid assignee; duplicate assignee; invalid user; CSRF; insider permissions; 404.
- [x] `AddSeqRequestAssigneeAction`: add valid assignee; assign another user (not the submitter); duplicate; non-insider rejected; insider permissions; CSRF; 404. Dashboard `self_assign_seq_request` route tested separately. *(See §6.)*
- [x] `AddSeqRequestShareEmailAction`: valid email; duplicate email; permission checks; CSRF; 404.
- [x] `ProcessSeqRequestAction`: accept; reject; pending revision; comment; assign to self; insider permissions; CSRF; 404.
- [x] `SubmitSeqRequestAction`: valid submission; missing required fields; invalid state; owner versus insider behavior; CSRF; 404.
- [x] `AddUserToGroupAction`: add member; nonexistent user; owner affiliation rejected; duplicate user; WRITE permission; CSRF; 404.
- [ ] `ShareDirectoryAction`: share valid directory; invalid/traversal path; duplicate share; expiry and recipient variants. *(Partial: valid share and traversal/absolute/symlink/sibling-prefix rejection in `test_share_root_abuse.py`; GET form render in `forms/test_experiment_lane_actions.py`. Duplicate share, expiry and recipient variants still open.)*
- [ ] `AssociatePathAction`: associate path with project; library; experiment; sequencing request; invalid entity; duplicate association; unauthorized path. *(Partial: project association and insider-only in `forms/test_associate_path_action.py`; share-root escapes in `test_share_root_abuse.py`. GET form render covered in `forms/test_experiment_lane_actions.py` (it used to be shadowed by the `/htmx/files/{subpath:path}` catch-all — see §6).)*
- [x] `MergeProjectsAction`: merge valid projects; same project; unauthorized projects; incompatible same-name samples; empty projects; rollback on failure. *(`forms/test_merge_projects_action.py`: unique samples move, same-name samples merge (links, attributes, measurements, status), assignees, conflicts, same/missing/unknown/non-numeric project, CSRF, rollback via a failure injected after the merge; insider-only check in `test_action_access.py`. Three failures found here were fixed in `e31216ed` — see findings.)*



### Sample, library, pool, and prep actions

- [x] `SampleAttributeTableAction`: valid attribute update; new attribute; type/value conflict; missing sample; unauthorized project; rollback. *(`forms/test_sample_attribute_table_action.py`: predefined/custom typing, clear cell, delete/rename column, unknown/foreign/mismatched/missing/duplicate rows, short and duplicate headers, max length, all-or-nothing save, insider-only, CSRF. Failures found here were fixed 2026-10-07 — see findings.)*
- [x] `StoreSamplesAction`: store samples/libraries/pools; pooled library keeps POOLED; request progression per submission type (raw → SAMPLES_RECEIVED, pooled → PREPARED, unpooled → SAMPLES_RECEIVED, QC-only → libraries QC_PENDING); empty selection rejected; unknown ID and CSRF change nothing; repeat is harmless; request context limits all tables and redirects back. *(Invalid status is not re-checked server-side — the status filter only narrows the browse table, same as legacy.)*
- [x] `LibraryPrepAction`: add accepted libraries; empty selection rejected; insider-only; CSRF; 404.
- [x] `UploadLibraryPrepSpreadsheetAction`: render; insider-only (incl. invalid upload), 404, CSRF; file stored as the prep's `LIBRARY_PREP_FILE` and readable as `prep_table`; re-upload replaces file record and plates (old plates deleted); libraries placed in wells (cleaned, zero-padded); one plate per `plate` value, numeric plates named as integers, unused template rows create no plate; pool `x` → FAILED; `lib_conc_ng_ul` → qubit concentration; missing file, empty sheet, missing (non-optional) column, missing `prep_table` sheet, non-`.xlsx` (csv/tsv), unsupported or corrupt file, library not in prep, name mismatch, missing name, duplicate well per plate, well outside A1–H12, non-numeric concentration rejected; invalid upload keeps plates and file. *(`forms/test_upload_library_prep_spreadsheet_action.py`. Fixed 2026-10-12, see findings. Placing libraries in wells is FastAPI-only: legacy computed the well index but the link was commented out.)*
- [x] `SelectPoolLibrariesAction`: add libraries; empty selection; insider-only; CSRF; 404.
- [x] `SamplePoolingAction`: render lists multiplexed samples only; insider-only, 404, CSRF; unchanged pools; move sample; new pool; emptied library deleted; pool `x` → FAILED `canceled_samples_*`; new libraries copy type/status/mux/genome/owner/request/features; every library type of a pool follows the sample; non-multiplexed libraries and other lab preps untouched; missing pool rejected. *(Legacy had no role check on this route; FastAPI is insider-only.)*
- [ ] `DilutePoolsAction`: valid dilution; zero/negative values; concentration and volume bounds; multiple pools; persistence and rollback.
- [x] `EditLibraryPropertiesAction`: render in request/project/library context (only the context's libraries, one column per property); no context 400, unknown context 404, other user's context 403, anonymous, CSRF; rows naming a library outside the context (incl. another library in library context) 404; edit values, empty cell → `None`, new column adds, deleted column removes the property; redirects per context; library without properties; too-long value rejected; editing needs WRITE on every library of the context via `Q.library.access_level` (insiders always; others while the library's request is DRAFT), otherwise read-only and POST 403; mixed project (draft + submitted request) is read-only for clients. *(`forms/test_edit_library_properties_action.py`. Decided 2026-10-13, see design note 5.)*
- [x] `LibraryFeaturesAction`: render prefill and kit list; insider-only (design note 5), 404, CSRF; antibody library types only (400 otherwise); custom features replace existing; sequence whitespace removed and identifiers normalized to ASCII; kit rows link the existing kit feature (by identifier and/or name); validation (missing definition, kit + custom, duplicate identifier/name/sequence+pattern+read/kit feature, invalid read, unknown kit, feature or identifier not in kit, identifier and name of different kit features). *(Fixed 2026-10-12: type check, clean-up, kit-feature linking, unreachable "not both" check, `IndexError` on unknown identifier, insider check before validation. Legacy raised "Logic error" on every kit row.)*
- [x] `CheckBarcodeClashesAction`: no clash; clash; mixed kits; empty selection; invalid libraries; permission checks. *(`forms/test_check_barcode_clashes_action.py`: error/warning/no clash, single-index, per-pool and per-lane grouping, forged library IDs hidden, request/pool/experiment access. Failures found here were fixed 2026-10-07 — see findings.)*
- [x] `SelectExperimentPoolsAction`: link pools; skip already-linked; empty selection; insider-only; CSRF; 404.



### Kit, protocol, barcode, and sequencing actions

- [x] `AddKitsToProtocolAction`: render lists kits and prefills current links; insider-only, 404, CSRF; submit replaces links; no combination numbers → all 1; same kit in different combinations; other protocols untouched; duplicate kit + combination, partially missing combination, unknown/missing kit, non-integer combination, empty spreadsheet rejected with links unchanged. *(`forms/test_add_kits_to_protocol_action.py`. Fixed 2026-10-12: missing `template_path` (every render 500'd); current links not prefilled (legacy used `Q.pd.protocol_kits`, so a resubmit dropped them); insider check after validation; an empty optional `Combination` cell 500'd in `SpreadsheetInputField` (`Int64` `<NA>` replaced with `""`). The action is also mounted twice, under `/htmx/protocols` and `/htmx/workflows`.)*
- [x] `EditKitFeaturesAction`: render prefill; insider-only (design note 5; legacy admin), 404, CSRF; submit replaces features (sorted, kit type, identifier/targets optional); resubmitting the prefill keeps them; other kits untouched; whitespace removed from sequence/read/target name/ID, identifier normalized to ASCII; duplicate sequence + pattern + read, duplicate identifier, duplicate name in CMO kits (allowed in antibody kits), missing name/sequence/pattern/read, short name, too-long sequence rejected. *(`forms/test_edit_kit_features_action.py`. Fixed 2026-10-12: legacy clean-up and validation of the columns (ASCII identifier + `check_string` + unique; whitespace removal) were missing; insider check ran after validation. Replaced features are unlinked from the kit, not deleted (`FeatureKit.features` has no delete-orphan), as in legacy.)*
- [x] `QueryBarcodeSequencesAction`: render form; empty/no-match search; CSRF ignored (no Validate).
- [x] `BarcodeConstraintsAction`: render; insider-only, CSRF; nothing provided; dual/i7-only/i5-only sets satisfying or failing the constraints (per-position check); i7/i5 length mismatch; invalid min samples; kit-only, failing dual, failing i7/i5 sets get kit suggestions; `min_samples` limits suggestion size; ATAC kit, kit with mixed i7 lengths, single-index kit with dual sequences rejected; unknown kit 404. *(`forms/test_barcode_constraints_action.py`. Fixed 2026-10-12: insider check after validation; single-index i7 kits 500'd on the missing i5 (also in legacy, although the kit search offers them). Still open: combinatorial dual-index kits are offered too, but their rows hold either an i7 or an i5, so the kit-length check rejects them (missing `well` column fixed 2026-10-13). Legacy's "number of i7 and i5 sequences must be the same" check is unreachable (the i5 length check catches it first).)*
- [x] `SetExperimentCyclesAction`: update cycles; empty cycles; insider-only; pre-fill; CSRF; 404.
- [x] `GenerateSequencerLoadingChecklistAction`: valid experiment; missing lanes/pools; invalid template parameters; output content; permission checks. *(`forms/test_generate_sequencer_loading_checklist_action.py`: per-lane inputs, file + DB record, volume scaling and lane merging, zero cells, missing/non-numeric values, no-template workflow, insider-only, CSRF. Failures found here were fixed 2026-10-07 — see findings.)*
- [x] `BillingAction`: valid experiment selection; empty selection; invalid status; duplicate export; insider/admin permissions; generated output. *(`forms/test_billing_action.py`: workbook sheets, lane/flow-cell share, capacity and missing-reads warnings, request resolution for request-less pools, multiple experiments, unknown ID, CSRF. Invalid status is not re-checked server-side — the status filter only narrows the browse table, same as legacy.)*
- [ ] `ReseqAction`: indexed libraries; raw libraries; mixed selection; invalid status; duplicate resequencing; permission checks.



Findings from §3 tests (fixed 2026-10-07):

- `merge_projects` (`opengsync_db/core/actions.py`, same code as legacy `ActionsBP`) — fixed in `e31216ed`:
  - same-name merge deleted the moved library links: `Sample.library_links` is `delete-orphan`, and the links stayed in the source sample's collection when it was deleted. Links are now re-parented through the relationship (duplicates dropped).
  - attributes were only copied inside the per-link loop, so a source sample without libraries lost its source-only attributes.
  - `dst.status >= src.status` raised `TypeError` when the source sample had no status (the default); the comparison is now `None`-safe.
- `SampleAttributeTableAction.Submit` — deleting a column raised `KeyError` for samples without that attribute (legacy had the same loop). Now guarded with `get_attribute()`, like the empty-cell branch.
- `CheckBarcodeClashesAction.SelectSamples` only required a login. Now insider-only on GET (legacy `begin`) and POST (legacy POST only required a login, which exposed any library's barcodes).
- `CheckBarcodeClashesAction.Render?experiment_id=` returned 200 for an unknown experiment. Now 404, as legacy.
- `GenerateSequencerLoadingChecklistAction.Begin` wrote `field._data` without marking the field validated, so labels, defaults and hidden `var_name`s rendered empty and the form could not be submitted. Now uses the `.data` setter, matching legacy `append_entry({...})`.
- `GenerateSequencerLoadingChecklistAction.Submit` raised `TypeError` for an experiment without laned pools (empty lane column is string-typed under pandas 3). The lane count is now cast to `int`.

Fixed while testing (trivial): `GenerateSequencerLoadingChecklistAction.template_path` pointed at the pre-rename `forms/sequencer_loading_checklist_form.html`; it now uses `actions/sequencer-loading-checklist.html`, which was ported off the WTForms API (`subform.csrf_token`, bare `{{ subform.var_name }}`). Removed two stray `</div>` from `forms/sample_attribute_table_form.html`.

Findings from §3 tests (fixed 2026-10-12):

- `LibraryFeaturesAction` — no library-type check (legacy: 400 unless 10x Antibody Capture / SC ABC Flex); identifier/sequence clean-up missing; kit rows created a copy of the kit feature instead of linking it, and an identifier-only kit row 500'd; an identifier not in the kit raised `IndexError`; the "kit + custom, not both" check was unreachable (also in legacy); insider check ran after validation. Legacy itself raised "Logic error" for every kit row. New, not in legacy: identifier and name of two different kit features are rejected, and duplicate kit rows are detected by the resolved feature.
- `AddKitsToProtocolAction` — no `template_path` (every render 500'd); current links were not prefilled (legacy used `Q.pd.protocol_kits`), so a resubmit dropped them; insider check ran after validation.
- `BarcodeConstraintsAction` — insider check ran after validation; selecting a single-index i7 kit 500'd on the missing i5 (`len(None)`, same in legacy although the kit search offers these kits).
- `UploadLibraryPrepSpreadsheetAction` / `SpreadsheetFileField` (`components/inputs/file.py`) — every upload was rejected ("File type '.xmlpk…' is not allowed"): the form-data middleware stores uploads as dicts, the field expected an `UploadFile`. Also: the file was optional (legacy: "File is required."); missing non-optional columns were silently filled with blanks (legacy: "Column '…' is missing in the spreadsheet."); re-upload by the same insider 500'd (the cached, detached `current_user` clashed with the prep file's uploader in the session — plates now get a session-bound owner); a row with an ID but no name 500'd (`NA` comparison); wells outside A1–H12 were saved at a wrong index (`A13` → `B1`) or 500'd (`foo`); template rows without a library created an empty `P-<prep>` plate; a plate column with blanks named plates `P-<prep>-1.0` (legacy: `int(plate)`); replacing an `.xlsx` prep file with a `.csv` kept the old extension, so the record pointed at a missing file; insider check ran after validation. Uploads are now `.xlsx` only (decided 2026-10-12): legacy also accepted csv/tsv but saved them as `.xlsx`, and every reader of the stored prep file (reindex, library pooling, protocol selection) reads its `prep_table` sheet.
- `SpreadsheetInputField` (`components/inputs/spreadsheet.py`) — an empty cell in an optional `IntegerColumn`/`FloatColumn` 500'd after validation (`replace(np.nan, "")` on a nullable `Int64`/`Float64` column). Affected `AddKitsToProtocolAction` (`Combination`) and likely `UploadLibraryPrepSpreadsheetAction` (`lib_conc_ng_ul`).

- `EditKitFeaturesAction` — the legacy column clean-up/validation was dropped: identifiers were not normalized to ASCII, checked or unique, and whitespace stayed in sequence, read and target name/ID; insider check ran after validation.

- `EditKitBarcodesForm` variants — combinatorial kits 500'd on render and submit: `pd_transforms.index_kit_barcodes_per_index` built no `well` column for them (same in legacy); 10x ATAC prefill was empty: the shared transform yields one `name_i7`/`sequence_i7` row per sequence, the form expects `name` + `sequence_1`–`sequence_4` per well (same in legacy) — `EditKitTENXATACBarcodes.barcode_table` now pivots; admin check ran after validation.

- Checkboxes (`HTMXForm`, `SubHTMXForm`, 2026-10-13) — a submission read a missing field as its default, but an unchecked checkbox sends nothing, so a `BooleanInputField(default=True)` could never be turned off (`ProcessSeqRequestAction` "Assign request to me", `OligoReMuxForm` "apply to all samples in pool"); and booleans are always `required`, so an empty value was rejected as missing (`SubmitSeqRequestAction`: a sample submission time alone was refused — its test had documented the bug). On submission a missing boolean is now False and booleans skip the required check.
- Test warnings (2026-10-13) — the suite now runs warning-free (`-W default`). `actions.remove_all_barcodes_from_kit` issued each barcode's DELETE twice (a barcode is reached through both `Adapter.barcodes_i7` and `barcodes_i5` and deleted explicitly too; SAWarning "0 rows matched"), now two bulk deletes; the form middleware copied uploads into memory but never closed their temp files (ResourceWarning); test helpers passed `cookies=` per request (Starlette deprecation) — they now send a Cookie header via `_http.cookie_header`.

Fixed while testing (trivial): removed two stray `</div>` from `forms/library-features-table.html`.

Still open: combinatorial dual-index kits are offered by the `BarcodeConstraintsAction` kit search; the missing `well` column is fixed (above), but their rows hold either an i7 or an i5, so the kit-length check rejects them (not tested yet).

### Specialized action variants



#### Lane pooling

- [ ] `LanePoolsCombinedAction`: one combined lane; valid pool ratios; invalid/zero ratios; molarity warnings; qubit lookup; persistence. *(Routing and access covered in `forms/test_experiment_lane_actions.py`. Template not yet ported from WTForms, so Begin returns 500 — xfail.)*
- [ ] `LanePoolsSeparateAction`: multiple lanes; per-lane pool assignments; missing lane; invalid ratios; molarity warnings; persistence. *(Routing and access covered in `forms/test_experiment_lane_actions.py`. Template not yet ported from WTForms, so Begin returns 500 — xfail.)*



#### Read distribution

- [ ] `DistributeReadsCombinedAction`: combined lanes; valid read allocation; totals mismatch; zero/negative reads; persistence. *(Routing and access covered in `forms/test_experiment_lane_actions.py`. Template not yet ported from WTForms, so Begin returns 500 — xfail.)*
- [ ] `DistributeReadsSeparateAction`: separate lanes; per-lane allocation; missing lane; totals mismatch; persistence. *(Routing and access covered in `forms/test_experiment_lane_actions.py`. Template not yet ported from WTForms, so Begin returns 500 — xfail.)*



#### Flow-cell loading

- [ ] `LoadFlowCellCombinedAction`: combined-lane load; valid flow cell; missing/duplicate flow cell; status validation; persistence. *(Routing and access covered in `forms/test_experiment_lane_actions.py`. Template not yet ported from WTForms, so Begin returns 500 — xfail.)*
- [ ] `LoadFlowCellSeparateAction`: separate-lane load; per-lane flow cells; duplicate flow cell; missing lane; persistence. *(Routing and access covered in `forms/test_experiment_lane_actions.py`. Template not yet ported from WTForms, so Begin returns 500 — xfail.)*



#### Index-kit barcode editing

- [x] `EditSingleIndexKitBarcodes`: prefill; replace barcodes (wells normalized, whitespace removed, one adapter per row); reverse complement; missing/duplicate well, name, sequence rejected with barcodes unchanged. *(`forms/test_edit_kit_barcodes_action.py`)*
- [x] `EditDualIndexKitBarcodes`: prefill; replace barcodes (i7 + i5 per adapter); missing i5 name takes the i7 name; reverse complement per index; duplicate well, duplicate i7 + i5 pair, name↔sequence conflicts, missing well/sequences rejected. *(`forms/test_edit_kit_barcodes_action.py`; legacy's save raised `KeyError` on `row["name"]`, FastAPI is correct.)*
- [x] `EditCombinatorialKitBarcodes`: prefill; replace barcodes (no wells, one adapter per barcode, i7-only rows); reverse complement; name without sequence (and vice versa), duplicate i7 + i5 pair, name with two sequences rejected. *(`forms/test_edit_kit_barcodes_action.py`. Fixed 2026-10-13: render and submit 500'd, see findings.)*
- [x] `EditKitTENXATACBarcodes`: prefill (one row per well with four sequences); replace barcodes (four i7 barcodes per adapter); reverse complement; duplicate/missing well, missing name or sequence rejected. *(`forms/test_edit_kit_barcodes_action.py`. Fixed 2026-10-13: prefill was empty, see findings. Duplicate sequences are not checked — legacy had a TODO.)*
- [x] `EditKitBarcodes` base dispatch: each kit type gets its own columns (no leak between requests); admin-only incl. invalid submissions (insider and client 403), anonymous, 404, CSRF; other kits untouched. *(`forms/test_edit_kit_barcodes_action.py`. Unsupported types raise 400; every `IndexType` with barcodes is mapped, so not reachable through the UI.)*



## 4. Workflows

Every workflow needs tests for: begin, initial state, each valid step, invalid step input, previous/back navigation, forward navigation, conditional-step selection, direct access to an inapplicable step, Redis state isolation, expired/missing state, CSRF, authorization, completion persistence, rollback, and cleanup.

### `LibraryAnnotationWorkflow`

Tests live in `services/pytest/tests/server/workflows/library_annotation/`, one scenario per file, driven by `_workflow.AnnotationWorkflow`. The two `test_simple_*_bulk_rna_seq.py` files also hold the step-by-step validation cases.

- [x] Raw samples → bulk RNA-seq happy path.
- [x] Pooled libraries → bulk RNA-seq happy path.
- [x] Raw samples → each supported service type. *(Remaining services in `test_service_type_matrix.py`.)*
- [x] Pooled libraries → each supported service type. *(Remaining services in `test_service_type_matrix.py`.)*
- [x] Existing project flow. *(`test_raw_existing_project_samples.py`, `test_duplicate_libraries_in_request.py`.)*
- [x] New project flow.
- [x] Existing project without write access. *(Another user's draft and own non-DRAFT project are rejected; unknown ID is 404.)*
- [x] Project selection validation and duplicate title.
- [x] Empty/malformed sample spreadsheet. *(Empty, missing columns, invalid JSON, empty/short/long/invalid names, unknown genome, duplicates incl. after space → `_`.)*
- [x] Sample attribute creation.
- [x] Existing sample attribute reuse. *(Existing sample is matched by name, its attributes incl. custom ones are pre-filled and kept.)*
- [x] Pooled-library mapping flow.
- [x] New pool mapping flow. *(Contact and pool-name validation in `test_simple_pooled_bulk_rna_seq.py`.)*
- [x] Existing/taken pool name failure.
- [x] Oligo multiplexing branch.
- [x] Parse multiplexing branch.
- [x] On-chip multiplexing branch.
- [x] Flex branch. *(Raw 4-/16-plex with auto pools, pooled 16-plex, unpooled 4-plex.)*
- [x] Flex + antibody branch.
- [x] Feature annotation branch. *(`test_input_features.py` for validation.)*
- [x] Custom assay branch.
- [x] Define multiplexed samples branch.
- [x] OpenST branch.
- [x] Visium branch.
- [x] Parse CRISPR guide branch.
- [x] Standard barcode input and barcode-match branch. *(Kit well/name lookup, custom sequences, custom-kit forward/rc options; `test_input_index_barcodes.py` for validation.)*
- [x] 10X ATAC barcode branch. *(Kit and custom indices.)*
- [x] Barcode clash/duplicate validation. *(`test_barcode_clash_review.py`. As in legacy, clashes are not rejected: the review step flags identical indices within a pool and submission goes through.)*
- [x] Back navigation from every applicable step. *(`test_back_navigation_every_step.py` re-runs every scenario with Back + re-submit after each step.)*
- [x] Inapplicable-step rejection. *(`test_step_order.py`.)*
- [x] Completion creates all expected projects, samples, libraries, pools, indices, and attributes. *(Asserted per scenario; Redis cleanup via `assert_cleaned_up()`.)*
- [x] Completion failure rolls back all created records. *(`test_completion_rollback.py`: nothing persisted, state kept, retry succeeds.)*
- [x] Expired workflow UUID and cross-user UUID isolation. *(`test_workflow_state.py`.)*



Findings from `LibraryAnnotationWorkflow` tests:

- ~~**Run not bound to its request.**~~ Fixed 2026-10-08. `require_seq_request_write` only checks the request in the URL, so a run (UUID) of request A could be read and completed on any other writable request. Project selection now stores `header["seq_request_id"]`, and `LibraryAnnotationWorkflow.Init` rejects (400) a run bound to another request on every step, and a run without state on every step but project selection. This also turns unknown/expired UUIDs into a 400.
- ~~**Out-of-order steps are a 500.**~~ Fixed 2026-10-08. Posting a step that does not apply, a `Previous` of a step never reached, or skipping ahead now gives 400: `LibraryAnnotationWorkflow.Init` only allows steps in the run's step tracker (every step routed to so far, incl. the current one).
- ~~**Back from feature annotation crashes for multiplexed custom pools.**~~ Fixed 2026-10-08: `FeatureAnnotationForm.Previous` drops duplicate library names before mapping them to samples.

Not a finding: project selection posts without the UUID (as legacy `select_project`), so going back to it and submitting starts a new run.

### `BAReportWorkflow`

Tests: `workflows/test_ba_report.py`.

- [x] Select one sample.
- [x] Select multiple samples. *(samples, libraries, pools and lanes together.)*
- [x] Empty selection. *(→ 202; duplicate names → 202.)*
- [x] Upload valid BA Excel file. *(BioAnalyzer CSV export, one `Region Table` per well.)*
- [x] Missing/renamed columns. *(a well without `Average Size [bp]` is kept with an empty size.)*
- [x] Malformed or empty Excel file. *(missing file or nothing parsable → 202.)*
- [x] Parse multiple supported report formats. *(Only the CSV export is supported, as legacy.)*
- [x] Enter valid metrics. *(manual tab and the excel flow's well ↔ object assignment.)*
- [x] Invalid numeric/range metrics. *(negative or non-numeric size → 202; malformed assignment → 202.)*
- [x] Complete and persist report. *(PDF required and stored as `BIOANALYZER_REPORT` (on the lab prep in lab-prep context); each object's size saved and linked to the report, empty size clears both; ACCEPTED pool → STORED.)*
- [x] Back navigation and Redis cleanup. *(completion clears the state; report step without a run → 400.)*
- [x] Permission and insider-only variants. *(client 403 on every step; rows for objects that were not selected → 400.)*

Fixed 2026-10-13: the report and confirmation templates rendered only `sample_forms`, so libraries, pools and lanes could not be measured; saving never linked the objects to the report, did not attach it to the lab prep, and did not move ACCEPTED pools to STORED (legacy did all three); the state was never cleared and the steps did not record themselves, so steps worked without a run (now 400) and trusted the submitted IDs; an empty selection was accepted; an unparsable export was a 400 instead of a form error; malformed well assignments 500'd; `FileInputField.save` did not create the media sub-directory. Average fragment sizes must be ≥ 1 everywhere (decided 2026-10-13: molarity divides by them): manual entry and confirmation reject 0, the export parser and the well assignment turn ≤ 0 into an empty size, and the lane QC forms (`QCLanesForm`, `UnifiedQCLanesForm`) now require ≥ 1 (were ≥ 0).



### `QubitMeasureWorkflow`

Tests: `workflows/test_qubit_measure.py`.

- [x] Select one sample. *(listed with its current value.)*
- [x] Select multiple samples. *(samples, libraries, pools and lanes together.)*
- [x] Empty/invalid selection. *(nothing selected → 202; unknown ID → 404.)*
- [x] Valid concentration measurements. *(zero is valid — legacy's `DataRequired` rejected it.)*
- [x] Missing, negative, zero, and malformed concentrations. *(missing, negative, non-numeric → 202, value unchanged.)*
- [x] Optional volume/dilution fields. *(None in this workflow.)*
- [x] Persist measurements. *(sample/library/pool `qubit_concentration`, lane `original_qubit_concentration`; ACCEPTED pool → STORED; redirect to experiment / lab prep / dashboard.)*
- [x] Back navigation, completion, rollback, and cleanup. *(back to selection; completion clears the state; measurement step without a run → 400; rows for objects that were not selected → 400, nothing saved.)*

Fixed 2026-10-13: an empty selection was accepted (legacy: "Select at least one sample"); an empty concentration was accepted and cleared the stored value (legacy: required); the measurement step worked without a run and trusted the submitted IDs, so a direct POST could set the concentration of any object — it now needs a run that went through selection and only accepts the selected objects (legacy trusted the IDs too).



### `AddKitsToProtocolWorkflow`

Not a separate workflow: `wf.add_kits_to_protocol` re-exports `AddKitsToProtocolAction` (single step, no Redis state), covered by `forms/test_add_kits_to_protocol_action.py` (see §3 and design note 7).

- [x] Begin action-backed flow. *(render, kit list, prefill of current links)*
- [x] Add valid kit combinations.
- [x] Remove/revise combinations before submit. *(submit replaces the prefilled links; resubmit keeps them)*
- [x] Duplicate/incompatible kits. *(duplicate kit + combination, unknown/missing kit; legacy had no kit-type compatibility check, so none is tested)*
- [x] Invalid protocol and permission failures. *(404, insider-only incl. invalid submissions, anonymous, CSRF)*
- [x] Completion persistence and rollback. *(invalid submissions leave links unchanged; other protocols untouched)*



### `RelibWorkflow`

- [x] Select one eligible sample/library.
- [x] Select multiple libraries.
- [x] Empty selection.
- [x] Ineligible/forged selection regression test added (currently `xfail`; server-side context validation is missing).
- [x] Edit library table with valid values.
- [x] Invalid dynamic library fields.
- [x] Back navigation preserves selection/table state.
- [x] Completion updates library state and clears workflow Redis state.
- [x] Unauthorized begin and invalid context behavior.
- [ ] Expired/missing workflow-state rejection.

Relib business-logic findings:

- `SelectSamplesForm.Submit` accepts library IDs outside the requested sequence request or lab prep because the query parameters only filter the browse table.
- `LibraryEditTableForm.Submit` trusts submitted `library_id` values instead of restricting rows to the libraries selected in the workflow; an insider can edit an unselected library.
- A fresh or expired workflow UUID is not distinguished from a new workflow when the table endpoint is posted directly, so the missing-state path can still reach persistence.



### `MergePoolsWorkflow`

- [ ] Select two compatible pools.
- [ ] Select more than two pools.
- [ ] Empty/one-pool selection.
- [ ] Set valid pipet ratios.
- [ ] Invalid/zero/negative ratios.
- [ ] Barcode clash preview with no clash.
- [ ] Barcode clash rejection.
- [ ] Name/contact validation.
- [ ] Back navigation.
- [ ] Completion creates merged pool and updates source state.
- [ ] Failure rolls back all changes.



### `ReindexWorkflow`

Tests: `workflows/test_reindex.py`, `workflows/test_reindex_barcode_match.py` (custom orientation options), `workflows/test_reindex_prep_table_prefill.py`.

- [x] Select one eligible library. *(prefilled with its current index.)*
- [x] Select multiple libraries.
- [x] Empty/ineligible selection. *(empty → 202; library outside the context → 404; unselected or unparseable library in the barcode table → 202.)*
- [x] Standard barcode input. *(kit by well (zero-padded) or by name — a dual kit's empty i5 name takes the i7 name, as legacy; several indices per library; `del` drops a library's indices; every selected library must be listed.)*
- [x] 10X ATAC barcode input with sequences 1–4. *(ATAC-only and mixed selections; kit + well fills name and sequences and links the kit; unknown kit well and missing sequence rejected.)*
- [x] Barcode-match flow with known kit. *(custom sequences of a kit offer it; choosing it fills names and kit, FORWARD.)*
- [x] Custom kit forward option. *(`test_reindex_barcode_match.py`)*
- [x] Custom kit reverse-complement option. *(`test_reindex_barcode_match.py`; primer stored as a request comment.)*
- [x] Missing/duplicate/invalid barcode values. *(well/name not in kit, kit without well/name, no kit and no sequence, invalid base.)*
- [x] Completion updates indices and library status. *(indices and index type replaced; library status is not changed — neither did legacy.)*
- [x] Back navigation through every branch. *(barcode input keeps resolved barcodes; select step reachable again.)*
- [x] Rollback and cleanup. *(completion clears the state; replay → 400; later step without state → 400; a run cannot be completed under another request → 400.)*

Access: request context needs WRITE (owner of a draft request; insiders always); lab prep, pool and no context are insider-only; unknown context 404.

Fixed 2026-10-13: later steps without state raised `KeyError`, and a run's state could be completed under a different context — the run is now bound to the context it was started for (400 "This reindexing has expired" / "belongs to another context"), like `LibraryAnnotationWorkflow`; the ATAC step had lost legacy's kit handling (kit + well/name did not fill the sequences, `kit_id` was never stored, sequences were not cleaned/validated) — ported from the library-annotation ATAC step; `SpreadsheetInputField` never validated `DBObjectColumn` cells (the column is expanded and dropped before per-column validation), so any `"name [id]"` was accepted and an unparseable cell raised — now checked against the column's categories (affects reindex and index check).



### `MuxPrepWorkflow`

Tests: `workflows/test_mux_prep.py`.

- [x] Oligo mux flow. *(custom sequence + pattern + read; kit + feature fills them from the CMO kit.)*
- [x] Flex mux flow. *(barcodes saved per sample link; redirect to the mux tab.)*
- [x] Flex + ABC flow. *(second step prefilled from GEX `BC###` → `AB###`; both saved at the end.)*
- [x] On-chip mux flow. *(`1`/`OB2`/`2;1` normalized to `OB1`/`OB2`/`OB1;OB2`.)*
- [x] Select valid libraries/samples. *(only the prep's libraries of the chosen mux type are listed.)*
- [x] Invalid or mixed mux types. *(unknown `mux_type_id` and unsupported ABC hashing → 400.)*
- [x] Valid index plate/layout data. *(ABC barcodes limited to `AB001`–`AB016`, OCM to `OB1`–`OB4`.)*
- [x] Duplicate wells and invalid assignments. *(duplicate barcode per pool in every flow; oligo: missing definition, kit + custom, unknown kit feature, duplicate definition.)*
- [x] Empty selection. *(missing OCM barcode rejected.)*
- [x] Back navigation and conditional form selection. *(ABC step only when the prep has ABC Flex libraries; Previous keeps GEX barcodes; ABC step without the GEX state → 400.)*
- [x] Completion persists mux annotations. *(completion clears the Redis state.)*
- [x] Failure rolls back all changes. *(invalid submissions and CSRF leave `link.mux` unchanged.)*

Pool membership is read-only here; legacy OCM could re-pool samples, FastAPI moved that to `SamplePoolingAction`.

Fixed 2026-10-13: unknown `mux_type_id` 500'd (`MUXType.get` raises instead of returning `None`); ABC prefill lost legacy's `BC` → `AB`; ABC barcodes were not limited to `AB001`–`AB016`; Flex/ABC completion no longer opened the mux tab; the ABC step without the GEX step's state raised `KeyError` (now 400, like the other workflows).



### `LibraryPoolingWorkflow`

Tests: `workflows/test_library_pooling.py`, `workflows/test_library_pooling_prep_table.py` (prefill from the prep table).

- [x] Select valid libraries. *(Begin lists only the prep's libraries.)*
- [x] Empty/ineligible selection. *(library outside the prep, name mismatch, `t` on a library, missing pool → 202.)*
- [x] Valid pool assignments and ratios. *(several pools → `<prep>_<value>`, one → `<prep>`, prefix not doubled; `x` → FAILED, `skip` untouched, all `x` → no pool.)*
- [x] Barcode-clash preview with no clash. *(also: same index in different pools is no clash.)*
- [x] Barcode-clash rejection. *(Clashes are only previewed (red tab), completion still pools — as legacy.)*
- [x] Invalid pool names/contact information. *(pool contact/owner = the insider; no free-text contact in this workflow.)*
- [x] Completion persists pools and library state. *(POOLED; rerun deletes old pools and keeps an unchanged pool's experiment; ACCEPTED request → PREPARED once all its libraries are pooled — FastAPI-only, legacy's request set was never filled.)*
- [x] Back navigation, rollback, and cleanup. *(Previous keeps the assignment; completion clears the Redis state; replayed or out-of-order completion → 400.)*

Fixed 2026-10-13: every invalid step-1 submission 500'd (the prep-file warning sat in `_context["flash"]`, and the re-render passed `flash=` again); with a single pool value all rows were pooled as `1`, so an all-`x` prep was pooled instead of failed (also in legacy); completing without state (replay after completion, or skipping step 1) raised `KeyError` — later steps now need a run that reached them (400 "This pooling has expired"), like `LibraryAnnotationWorkflow`.



### `LibraryRemuxWorkflow`

Tests: `workflows/test_library_remux.py`.

- [x] Oligo remux flow. *(custom sequence + pattern + read; kit + feature fills them; only this library, or all libraries of the samples with "apply to all samples in pool".)*
- [x] Flex remux flow. *(barcodes per sample saved; redirect to the library.)*
- [x] Unsupported mux type. *(on-chip → 400; Flex mux on a non-Flex library → 400.)*
- [x] Valid remux assignments.
- [x] Duplicate/invalid barcodes. *(duplicate Flex barcode; missing or duplicate oligo definition.)*
- [x] Permission and library-status failures. *(WRITE on the library; non-insiders only while the library is DRAFT — as legacy; other user 403, unknown 404, anonymous, CSRF.)*
- [x] Completion persistence and rollback. *(invalid submissions leave `link.mux` unchanged.)*

Fixed 2026-10-13: unchecking "apply to all samples in pool" had no effect — see the checkbox fix under Findings.



### `SelectLibraryProtocolsWorkflow`

- [ ] Prep file with `library_kits` requiring protocol mapping.
- [ ] Prep file without `library_kits` skipping mapping.
- [ ] Valid protocol mapping.
- [ ] Missing/incompatible mapping.
- [ ] Protocol selection for every library type.
- [ ] Empty/partial selection.
- [ ] Completion persistence.
- [ ] Back navigation and conditional-step behavior.



### `LaneQCWorkflow`

Test the two execution flavors separately:

- [x] Separate-lane QC flow. *(Combined-lane flavor still untested.)*
- [ ] Combined-lane QC flow.
- [x] Valid phi-X values.
- [x] Valid fragment-size values.
- [x] Valid original qubit concentration.
- [ ] Missing/negative/out-of-range values.
- [ ] Missing lane and duplicate lane submissions.
- [x] Insider-only authorization.
- [x] Completion persists all lane metrics.
- [x] Completion clears Redis state.
- [ ] Failure rolls back lane updates.



### `ShareProjectDataAction`

Covered by `forms/test_share_project_data_action.py`.

- [x] Share one project.
- [ ] Valid internal/external access options. *(Tests always submit `internal_share=false`.)*
- [x] Expiration/time-validity variants.
- [x] Recipient email variants.
- [ ] Anonymous-send option. *(Tests always submit `anonymous_send=false`.)*
- [x] Mark-project-delivered option.
- [x] Missing/invalid data paths.
- [x] Unauthorized project.
- [x] Completion creates/updates share token and paths.
- [x] Rollback and duplicate submission behavior. *(A new share expires the previous token.)*



### `SelectExperimentPoolsWorkflow`

Not a separate workflow: `wf.select_experiment_pools` re-exports `SelectExperimentPoolsAction` (single step, not mounted under `/workflows`), covered by `forms/test_select_experiment_pools_action.py` (§3).

- [x] Select valid stored pools.
- [x] Exclude pools already associated with an experiment. *(already-linked pools are skipped.)*
- [x] Empty selection.
- [x] Invalid/ineligible pool. *(unknown pool 404.)*
- [x] Combined-lane experiment. *(Pools are only linked to the experiment here; lane assignment is the lane-pools action — see "Lane pooling", template not ported.)*
- [x] Separate-lane experiment. *(as above.)*
- [x] Experiment permission and insider checks. *(insider-only GET/POST, unknown experiment 404, CSRF.)*
- [x] Completion updates experiment checklist and associations. *(pool ↔ experiment links; the checklist is derived from them.)*
- [x] Back navigation and cleanup. *(single step, no state.)*



### `MergeProjectsWorkflow`

Not a separate workflow: `wf.merge_projects` re-exports `MergeProjectsAction` (single step, not mounted under `/workflows`), covered by `forms/test_merge_projects_action.py` (§3).

- [x] Merge two compatible projects. *(unique samples move; source left empty, not deleted.)*
- [x] Merge multiple projects, if supported. *(Not supported: one source into one destination.)*
- [x] Same project selected twice.
- [x] No source/target project. *(missing, unknown, non-numeric.)*
- [x] Incompatible same-name sample attributes.
- [x] Conflicting projects/owners/groups. *(same-name samples merged — measurements, status, attributes; assignees merged without duplicates.)*
- [x] Unauthorized project access. *(insider-only — `test_action_access.py`.)*
- [x] Completion moves expected samples/libraries/requests. *(samples with their library links.)*
- [x] Failure rolls back all changes.

### `SplitProjectWorkflow`

Not present in the legacy Flask app — FastAPI-only workflow. Moves samples from a source project to an existing or newly created destination project.

- [x] Insider-only begin and submit.
- [x] Move samples to an existing destination project.
- [x] Empty/missing sample selection and forged (foreign-project) sample IDs rejected.
- [x] New destination project inherits source owner and group, with chosen status.
- [ ] Back navigation between steps.
- [ ] Unauthorized source-project access.
- [ ] Rollback on failure.



## 5. Cross-cutting response and security tests

- [ ] Every form/action rejects missing CSRF tokens. *(Covered for all auth forms, seq request form, group membership, comments, API tokens; not yet for the remaining forms/actions.)*
- [x] Every protected route rejects anonymous users correctly. *(test_access.py, test_auth.py)*
- [x] Insider-only and admin-only routes reject normal users. *(test_access.py for pages; `test_action_access.py` for every action/workflow that was insider- or admin-only in legacy: dependency check on every route plus a real client GET.)*
- [x] Entity-level permissions are checked for every resource context. *(Core entities — project, sample, library, pool, seq request, group, user — covered in test_access.py.)*
- [ ] GET renders do not mutate database state.
- [ ] POST/PUT/DELETE methods match template `hx-*` methods.
- [x] Successful HTMX responses contain expected `HX-Redirect`, `HX-Trigger`, and flash behavior. *(Helpers in `_http.py`; asserted throughout auth and workflow tests.)*
- [x] Invalid submissions return the expected `202` form response rather than a generic `500`. *(assert_form_invalid used widely.)*
- [ ] Standard browser requests return full-page responses where intended.
- [ ] Database changes are committed only after successful completion.
- [ ] Failed actions/workflows leave no partial records or files. *(Partially covered by registration and seq-request validation tests.)*
- [ ] Repeated submissions are safe or explicitly rejected. *(Reset-token reuse covered; rest open.)*
- [x] Missing resources return controlled `404` responses. *(test_access.py)*
- [ ] Invalid parameters return controlled `400`/`422` responses.
- [x] Route endpoint names used by templates resolve against the FastAPI route registry. *(Form route names are asserted against the app registry and `url_path_for` in `forms/test_htmx_form.py`.)*
- [x] No route is shadowed by an earlier route. *(`test_route_shadowing.py`: Starlette matches in registration order, unlike Flask, so a same-path or catch-all route registered first makes later routes unreachable.)*
- [ ] Redis workflow state cannot be read or modified by another user.
- [ ] File uploads and generated files cannot escape configured roots. *(Share root covered by `test_share_root_abuse.py`: every staff and public share-link entry point attacked with `..`, encoded traversal, absolute paths, sibling-prefix dirs, and symlinks out, plus unshared paths for share links. Media uploads still open.)*

## 6. Design Notes

| # | File | Detail |
|---|------|--------|
| 1 | `routes/htmx/seq_requests.py:810` | Assigning a seq request has two separate routes. `POST /{seq_request_id}/self-assign` (`self_assign_seq_request`) is the dashboard "Assign yourself" button and only assigns the current user. `POST /{seq_request_id}/add-assignee` (`AddSeqRequestAssigneeAction.Submit`) is the form on the request page for assigning any insider via `user_id`. Previously both used `/add-assignee`, the raw route was registered first and shadowed the form, so picking another user in the modal assigned the submitter instead. |
| 2 | `forms/actions/{lane_pools,load_flowcell,dist_reads}/` | Each lane step has a Separate and a Combined action. Legacy used one URL per step and chose the form from `experiment.workflow.combined_lanes`; the FastAPI templates choose the action by name, so each variant has its own path (`/{experiment_id}/lane-pools/separate` vs `/combined`, same for `load-flow-cell` and `distribute-reads`). Previously both variants shared a path and the Separate one, registered first, made every Combined action unreachable. Access matches legacy: insider-only for GET and POST (`DistributeReadsSeparateAction` had no auth, lane-pools `Begin` had none); read distribution on non-draft experiments is admin-only. |
| 3 | `routes/htmx/files.py` | `ShareDirectoryAction` and `AssociatePathAction` routers are registered before the `/{subpath:path}` catch-all, otherwise their GET forms render the file browser. |
| 4 | templates | 15 templates are still in legacy WTForms style (`form.csrf_token()`, legacy `*_form` context names) and raise when rendered: `workflows/experiment/lane_pools-1.{1,2}.html`, `workflows/experiment/load_flow_cell-1.{1,2}.html`, `workflows/dist_reads/{combined,separate}.html`, `workflows/merge_pools.html`, `workflows/reseq/reseq.html`, `actions/dilute-pools.html`, `forms/edit-index.html`, `forms/library-properties-table.html`, `forms/seq_request/seq_auth.html`, `components/popups/file-input-form.html`, `components/search_select.jinja2`, `components/table_input.jinja2`. |
| 5 | access | The `/htmx` routers only require a login, so each action must enforce its role. Missing checks restored to legacy: `StoreSamplesAction` (both routes), `DilutePoolsAction` and `SetExperimentCyclesAction` (`Begin`), every step of `BAReportWorkflow` and `QubitMeasureWorkflow` (router-level `require_insider`; `Begin` previously only checked in lab-prep/experiment context). Differs from legacy, not changed: `SampleAttributeTableAction` and `LibraryFeaturesAction` are insider-only (legacy: WRITE on project/library, so clients could edit); kit, index-kit and feature-kit create/edit plus `EditKitFeaturesAction` allow insiders (legacy: admin-only). Insider check moved before validation (into `Init`) for `LibraryFeaturesAction`, `AddKitsToProtocolAction` and `BarcodeConstraintsAction`; with `Validate()` first, a client's invalid POST got the form back (202) instead of 403. `SamplePoolingAction` is insider-only (legacy: login only). `EditLibraryPropertiesAction` (decided 2026-10-13): editing needs WRITE on every library of the context, from `Q.library.access_level` (insiders always; others only while the library's request is DRAFT), otherwise the table is read-only and POST is 403 (legacy: DRAFT-only for non-insiders in library context, insider-only in project/request context, UI-only). |
| 6 | `StoreSamplesAction` | Restored legacy behaviour: empty selection is rejected; pools can be selected (template had no pools tab, so pooled requests could not reach PREPARED); started from a request, all three tables are limited to it and submitting returns to the request page. The QC-only branch is FastAPI-only. |
| 7 | `routes/htmx/{protocols,workflows}.py` | `AddKitsToProtocolAction.Router()` is included twice, under `/htmx/protocols/{id}/add-kits` and `/htmx/workflows/{id}/add-kits`, with the same route names. The workflows router is registered first, so `url_for` (and the button in `protocol_page.html`) resolves to `/htmx/workflows/...`; the tests use `/htmx/protocols/...`. Both behave the same; one mount can be removed. |
