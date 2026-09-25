# FastAPI Forms, Actions, and Workflows Test TODO

> Scope: `services/backend/server/forms/` and the HTTP behavior exposed by each router.
>
> Testing convention: each checkbox should become at least one focused test. Add separate tests for happy path, invalid input, authorization, CSRF, persistence/rollback, response status/headers, and duplicate/replay submissions where applicable.
>
> Existing coverage lives in `services/pytest/tests/server/forms/auth/` (login, register, complete registration, change password, reset password, API token), `server/forms/test_htmx_form.py`, `server/forms/test_sub_htmx_form.py`, `server/forms/test_seq_request_form.py`, `server/forms/test_project_form.py`, `server/forms/test_sample_form.py`, `server/forms/test_library_form.py`, `server/forms/test_experiment_form.py`, `server/test_forms.py`, `server/test_access.py`, `server/workflows/test_htmx_workflow.py`, and `server/workflows/` (library annotation, relib, split project, lane QC).

## 0. Shared test infrastructure

- [x] Add reusable authenticated-client fixtures for anonymous user, normal user, second user, insider, and admin.
- [ ] Add reusable database fixtures/factories for every model used by forms and actions. *(Partial: 13 factories in `db/create_units.py` — user, project, contact, seq request, sample, library, pool, feature, feature kit, sequencer, experiment, file, group. Kits, plates, lanes, seq runs, protocols, and designs are missing.)*
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
- [ ] `ShareDirectoryAction`: share valid directory; invalid/traversal path; duplicate share; expiry and recipient variants. *(Partial: valid share and traversal/absolute/symlink/sibling-prefix rejection in `test_share_root_abuse.py`.)*
- [ ] `AssociatePathAction`: associate path with project; library; experiment; sequencing request; invalid entity; duplicate association; unauthorized path. *(Partial: project association and insider-only in `forms/test_associate_path_action.py`; share-root escapes in `test_share_root_abuse.py`. GET `Begin` is unreachable — shadowed by the `/htmx/files/{subpath:path}` catch-all.)*
- [ ] `MergeProjectsAction`: merge valid projects; same project; unauthorized projects; incompatible same-name samples; empty projects; rollback on failure.



### Sample, library, pool, and prep actions

- [ ] `SampleAttributeTableAction`: valid attribute update; new attribute; type/value conflict; missing sample; unauthorized project; rollback.
- [ ] `StoreSamplesAction`: store samples; store libraries; store pools; mixed selection; invalid status; unauthorized resources; idempotent repeat.
- [x] `LibraryPrepAction`: add accepted libraries; empty selection rejected; insider-only; CSRF; 404.
- [ ] `UploadLibraryPrepSpreadsheetAction`: valid spreadsheet; missing columns; malformed spreadsheet; duplicate libraries; invalid statuses; partial rollback.
- [x] `SelectPoolLibrariesAction`: add libraries; empty selection; insider-only; CSRF; 404.
- [ ] `SamplePoolingAction`: assign samples to pools; move assignments; duplicate sample; invalid pool; status and ownership checks.
- [ ] `DilutePoolsAction`: valid dilution; zero/negative values; concentration and volume bounds; multiple pools; persistence and rollback.
- [ ] `EditLibraryPropertiesAction`: project context; sequence-request context; library context; dynamic columns; invalid/missing values; unauthorized context.
- [ ] `LibraryFeaturesAction`: add/edit/remove features; duplicate feature; invalid feature kit; library status/permission checks.
- [ ] `CheckBarcodeClashesAction`: no clash; clash; mixed kits; empty selection; invalid libraries; permission checks.
- [x] `SelectExperimentPoolsAction`: link pools; skip already-linked; empty selection; insider-only; CSRF; 404.



### Kit, protocol, barcode, and sequencing actions

- [ ] `AddKitsToProtocolAction`: add kit combination; duplicate combination; invalid kit; incompatible kit types; protocol permissions; rollback.
- [ ] `EditKitFeaturesAction`: create/edit/delete feature rows; duplicate sequences; invalid feature type; admin permissions; spreadsheet errors.
- [x] `QueryBarcodeSequencesAction`: render form; empty/no-match search; CSRF ignored (no Validate).
- [ ] `BarcodeConstraintsAction`: compatible set; incompatible set; missing library; duplicate barcode; invalid kit/type; controlled validation response.
- [x] `SetExperimentCyclesAction`: update cycles; empty cycles; insider-only; pre-fill; CSRF; 404.
- [ ] `GenerateSequencerLoadingChecklistAction`: valid experiment; missing lanes/pools; invalid template parameters; output content; permission checks.
- [ ] `BillingAction`: valid experiment selection; empty selection; invalid status; duplicate export; insider/admin permissions; generated output.
- [ ] `ReseqAction`: indexed libraries; raw libraries; mixed selection; invalid status; duplicate resequencing; permission checks.



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

- [ ] `EditSingleIndexKitBarcodes`: valid single-index spreadsheet; missing columns; duplicate wells/sequences; reverse-complement behavior; rollback.
- [ ] `EditDualIndexKitBarcodes`: valid i7/i5 spreadsheet; duplicate i7/i5 pairs; missing index; reverse-complement behavior; rollback.
- [ ] `EditCombinatorialKitBarcodes`: valid combinatorial matrix; duplicate combinations; invalid matrix dimensions; sequence validation; rollback.
- [ ] `EditKitTENXATACBarcodes`: valid four-sequence ATAC rows; missing `sequence_1`–`sequence_4`; duplicate rows; sequence validation; rollback.
- [ ] `EditKitBarcodes` base dispatch: supported kit-type selection; unsupported type; base-class methods never reached accidentally; controlled error.



## 4. Workflows

Every workflow needs tests for: begin, initial state, each valid step, invalid step input, previous/back navigation, forward navigation, conditional-step selection, direct access to an inapplicable step, Redis state isolation, expired/missing state, CSRF, authorization, completion persistence, rollback, and cleanup.

### `LibraryAnnotationWorkflow`

Existing tests cover simple raw bulk RNA-seq and simple pooled bulk RNA-seq. Extend them with the following separate flows:

- [x] Raw samples → bulk RNA-seq happy path.
- [x] Pooled libraries → bulk RNA-seq happy path.
- [ ] Raw samples → each supported service type.
- [ ] Pooled libraries → each supported service type.
- [ ] Existing project flow.
- [ ] New project flow.
- [ ] Existing project without write access.
- [ ] Project selection validation and duplicate title.
- [ ] Empty/malformed sample spreadsheet.
- [ ] Sample attribute creation.
- [ ] Existing sample attribute reuse.
- [ ] Pooled-library mapping flow.
- [ ] New pool mapping flow.
- [ ] Existing/taken pool name failure.
- [ ] Oligo multiplexing branch.
- [ ] Parse multiplexing branch.
- [ ] On-chip multiplexing branch.
- [ ] Flex branch.
- [ ] Flex + antibody branch.
- [ ] Feature annotation branch.
- [ ] Custom assay branch.
- [ ] Define multiplexed samples branch.
- [ ] OpenST branch.
- [ ] Visium branch.
- [ ] Parse CRISPR guide branch.
- [ ] Standard barcode input and barcode-match branch.
- [ ] 10X ATAC barcode branch.
- [ ] Barcode clash/duplicate validation.
- [ ] Back navigation from every applicable step.
- [ ] Inapplicable-step rejection.
- [ ] Completion creates all expected projects, samples, libraries, pools, indices, and attributes.
- [ ] Completion failure rolls back all created records.
- [ ] Expired workflow UUID and cross-user UUID isolation.



### `BAReportWorkflow`

- [ ] Select one sample.
- [ ] Select multiple samples.
- [ ] Empty selection.
- [ ] Upload valid BA Excel file.
- [ ] Missing/renamed columns.
- [ ] Malformed or empty Excel file.
- [ ] Parse multiple supported report formats.
- [ ] Enter valid metrics.
- [ ] Invalid numeric/range metrics.
- [ ] Complete and persist report.
- [ ] Back navigation and Redis cleanup.
- [ ] Permission and insider-only variants.



### `QubitMeasureWorkflow`

- [ ] Select one sample.
- [ ] Select multiple samples.
- [ ] Empty/invalid selection.
- [ ] Valid concentration measurements.
- [ ] Missing, negative, zero, and malformed concentrations.
- [ ] Optional volume/dilution fields.
- [ ] Persist measurements.
- [ ] Back navigation, completion, rollback, and cleanup.



### `AddKitsToProtocolWorkflow`

- [ ] Begin action-backed flow.
- [ ] Add valid kit combinations.
- [ ] Remove/revise combinations before submit.
- [ ] Duplicate/incompatible kits.
- [ ] Invalid protocol and permission failures.
- [ ] Completion persistence and rollback.



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

- [ ] Select one eligible library.
- [ ] Select multiple libraries.
- [ ] Empty/ineligible selection.
- [ ] Standard barcode input.
- [ ] 10X ATAC barcode input with sequences 1–4.
- [ ] Barcode-match flow with known kit.
- [ ] Custom kit forward option.
- [ ] Custom kit reverse-complement option.
- [ ] Missing/duplicate/invalid barcode values.
- [ ] Completion updates indices and library status.
- [ ] Back navigation through every branch.
- [ ] Rollback and cleanup.



### `MuxPrepWorkflow`

- [ ] Oligo mux flow.
- [ ] Flex mux flow.
- [ ] Flex + ABC flow.
- [ ] On-chip mux flow.
- [ ] Select valid libraries/samples.
- [ ] Invalid or mixed mux types.
- [ ] Valid index plate/layout data.
- [ ] Duplicate wells and invalid assignments.
- [ ] Empty selection.
- [ ] Back navigation and conditional form selection.
- [ ] Completion persists mux annotations.
- [ ] Failure rolls back all changes.



### `LibraryPoolingWorkflow`

- [ ] Select valid libraries.
- [ ] Empty/ineligible selection.
- [ ] Valid pool assignments and ratios.
- [ ] Barcode-clash preview with no clash.
- [ ] Barcode-clash rejection.
- [ ] Invalid pool names/contact information.
- [ ] Completion persists pools and library state.
- [ ] Back navigation, rollback, and cleanup.



### `LibraryRemuxWorkflow`

- [ ] Oligo remux flow.
- [ ] Flex remux flow.
- [ ] Unsupported mux type.
- [ ] Valid remux assignments.
- [ ] Duplicate/invalid barcodes.
- [ ] Permission and library-status failures.
- [ ] Completion persistence and rollback.



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



### `ShareProjectDataWorkflow`

- [ ] Share one project.
- [ ] Valid internal/external access options.
- [ ] Expiration/time-validity variants.
- [ ] Recipient email variants.
- [ ] Anonymous-send option.
- [ ] Mark-project-delivered option.
- [ ] Missing/invalid data paths.
- [ ] Unauthorized project.
- [ ] Completion creates/updates share token and paths.
- [ ] Rollback and duplicate submission behavior.



### `SelectExperimentPoolsWorkflow`

- [ ] Select valid stored pools.
- [ ] Exclude pools already associated with an experiment.
- [ ] Empty selection.
- [ ] Invalid/ineligible pool.
- [ ] Combined-lane experiment.
- [ ] Separate-lane experiment.
- [ ] Experiment permission and insider checks.
- [ ] Completion updates experiment checklist and associations.
- [ ] Back navigation and cleanup.



### `MergeProjectsWorkflow`

- [ ] Merge two compatible projects.
- [ ] Merge multiple projects, if supported.
- [ ] Same project selected twice.
- [ ] No source/target project.
- [ ] Incompatible same-name sample attributes.
- [ ] Conflicting projects/owners/groups.
- [ ] Unauthorized project access.
- [ ] Completion moves expected samples/libraries/requests.
- [ ] Failure rolls back all changes.

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
- [x] Insider-only and admin-only routes reject normal users. *(test_access.py)*
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
