# FastAPI Forms, Actions, and Workflows Test TODO

> Scope: `services/backend/server/forms/` and the HTTP behavior exposed by each router.
>
> Testing convention: each checkbox should become at least one focused test. Add separate tests for happy path, invalid input, authorization, CSRF, persistence/rollback, response status/headers, and duplicate/replay submissions where applicable.
>
> Existing coverage is concentrated in `services/pytest/tests/server/workflows/library_annotation/`, `test_forms.py`, and `test_workflows.py`.

## 0. Shared test infrastructure

- [x] Add reusable authenticated-client fixtures for anonymous user, normal user, second user, insider, and admin.
- [ ] Add reusable database fixtures/factories for every model used by forms and actions.
- [x] Add helpers for GET form rendering, POST validation, CSRF failure, HTMX headers, redirects, flash messages, and database assertions.
- [ ] Add tests for `HTMXForm` route registration and generated endpoint names.
- [ ] Add tests for `HTMXForm.Init()` and `HTMXForm.Validate()` dependency behavior.
- [ ] Add tests for `HTMXForm.make_response()` and invalid-form re-rendering.
- [ ] Add tests for `SubHTMXForm` field collection, nested errors, and Pydantic validation.
- [ ] Add tests for form transaction rollback after validation and unexpected exceptions.
- [ ] Add tests for `HTMXWorkflow` state isolation, Redis serialization, expiration, cleanup, and concurrent UUIDs.
- [ ] Add tests for `HTMXWorkflowStep.is_applicable()` and conditional step navigation.
- [ ] Add tests for `BarcodeInputMixin` normalization, invalid sequences, duplicate barcodes, and reverse-complement behavior.

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

- [ ] Valid completion with a valid registration token.
- [ ] Expired token.
- [ ] Unknown or already-used token.
- [ ] Password mismatch and invalid password.
- [ ] Duplicate/invalid user state.
- [ ] CSRF failure.
- [ ] Account activation persistence.

### `ChangePasswordForm`

- [ ] Valid password change.
- [ ] Incorrect current password.
- [ ] New-password mismatch.
- [ ] New password equal to old password, if prohibited.
- [ ] Invalid password and missing fields.
- [ ] Anonymous-user rejection.
- [ ] CSRF failure.
- [ ] Session/token behavior after password change.

### `ResetPasswordForm`

- [ ] Valid reset request/token.
- [ ] Expired token.
- [ ] Unknown token.
- [ ] Already-used token.
- [ ] Password mismatch and invalid password.
- [ ] Unknown email behavior without account enumeration.
- [ ] CSRF failure.
- [ ] Password persistence and token invalidation.

### `APITokenForm`

- [ ] Render token form for an authenticated user.
- [ ] Create token.
- [ ] Duplicate token/name behavior.
- [ ] Empty/invalid token name.
- [ ] Deactivate active token.
- [ ] Deactivate already-inactive token.
- [ ] Cannot access another user’s token.
- [ ] CSRF failure.
- [ ] Token value visibility and response behavior.

## 2. Model forms

For every model form below, test **create**, **edit**, **missing/invalid ID**, **unauthorized access**, **validation failure**, **CSRF**, **persistence**, **rollback**, and **response redirect/flash**. Where create or edit is intentionally unsupported, test that the route is absent or returns a controlled error rather than a traceback.

### `ProjectForm`

- [ ] Create project.
- [ ] Edit project.
- [ ] Duplicate owner/title validation.
- [ ] Identifier uniqueness and format.
- [ ] Required, minimum, and maximum lengths.
- [ ] Owner/group/assignee permissions.
- [ ] Editing another user’s project.
- [ ] Draft versus non-draft edit behavior.

### `SampleForm`

- [ ] Create sample.
- [ ] Edit sample.
- [ ] Project ownership/access checks.
- [ ] Duplicate sample-name behavior within a project.
- [ ] Genome/reference validation.
- [ ] Required and maximum-length fields.
- [ ] Library/project relationship persistence.

### `LibraryForm`

- [ ] Create library.
- [ ] Edit library.
- [ ] Library type/status validation.
- [ ] Sample, project, and sequence-request access checks.
- [ ] Indexed/unindexed state behavior.
- [ ] Invalid relationship IDs.
- [ ] Protected status transition behavior.

### `SeqRequestForm`

- [ ] Create sequencing request.
- [ ] Edit draft request.
- [ ] Edit submitted/processed request restrictions.
- [ ] Required contact, submission-type, and metadata fields.
- [ ] Invalid project/user relationships.
- [ ] Owner/insider permission variants.
- [ ] Persistence of submission state.

### `LabPrepForm`

- [ ] Create lab prep.
- [ ] Edit lab prep, if supported.
- [ ] Invalid protocol/prep-file relationships.
- [ ] Required name/type fields.
- [ ] Insider-only behavior.
- [ ] Checklist initialization and persistence.

### `ExperimentForm`

- [ ] Create experiment.
- [ ] Edit experiment.
- [ ] Sequencer/operator selection.
- [ ] Workflow and lane configuration validation.
- [ ] Invalid status transitions.
- [ ] Insider/admin permission variants.
- [ ] Deleteability interaction with form state.

### `PoolForm`

- [ ] Create draft pool.
- [ ] Edit draft pool.
- [ ] Edit non-draft pool as insider/admin.
- [ ] Clone flow, if exposed through this form.
- [ ] Pool name uniqueness/format.
- [ ] Pool type/status/contact validation.
- [ ] Experiment/sequence-request relationships.
- [ ] Unauthorized and invalid relationship cases.

### `PlateForm`

- [ ] Create plate with a pool.
- [ ] Create plate without a pool.
- [ ] Invalid pool/plate relationship.
- [ ] Edit behavior: verify supported or controlled rejection.
- [ ] `flipped` orientation behavior.
- [ ] Plate/sample-link persistence.
- [ ] Insider permission checks.

### `GroupForm`

- [ ] Create group.
- [ ] Edit group.
- [ ] Duplicate group name.
- [ ] Owner/manager permission variants.
- [ ] Invalid owner/member IDs.
- [ ] Group membership persistence.
- [ ] Unauthorized access.

### `UserForm`

- [ ] Create user.
- [ ] Edit user.
- [ ] Insider/admin permission variants.
- [ ] Duplicate email.
- [ ] Role/status changes.
- [ ] Suspended/active transitions.
- [ ] Invalid fields and maximum lengths.

### `CommentForm`

Test each target context separately:

- [ ] Create comment on a sequencing request.
- [ ] Edit comment on a sequencing request.
- [ ] Create comment on an experiment.
- [ ] Edit comment on an experiment.
- [ ] Create comment on a lab prep.
- [ ] Edit comment on a lab prep.
- [ ] Invalid/missing target context.
- [ ] Target permission variants.
- [ ] Empty/maximum-length comment.
- [ ] Delete behavior, if exposed.

### `TODOCommentForm`

- [ ] Create TODO comment on flow-cell design.
- [ ] Create TODO comment on pool design.
- [ ] Edit TODO comment.
- [ ] Change TODO status.
- [ ] Delete TODO comment.
- [ ] Invalid target/comment ID.
- [ ] Permission variants.
- [ ] Empty/maximum-length text.

### `MediaFileForm`

Test each attachment context separately:

- [ ] Upload file to a sequencing request.
- [ ] Upload file to an experiment.
- [ ] Upload file to a lab prep.
- [ ] Edit file metadata, if supported.
- [ ] Missing context or multiple contexts.
- [ ] Unsupported extension/type.
- [ ] Empty, oversized, and malformed upload.
- [ ] Filename/path sanitization.
- [ ] Permission variants.
- [ ] File persistence and cleanup on rollback.

### `ProtocolForm`

- [ ] Create protocol.
- [ ] Edit protocol.
- [ ] Duplicate identifier/name.
- [ ] Version and kit relationship validation.
- [ ] Insider/admin permission variants.
- [ ] Invalid kit IDs.
- [ ] Persistence and deletion restrictions.

### `FlowCellDesignForm`

- [ ] Create design.
- [ ] Edit design.
- [ ] Invalid experiment/flow-cell relationships.
- [ ] Lane count/layout validation.
- [ ] TODO-comment integration.
- [ ] Permission variants.
- [ ] Persistence and rollback.

### `PoolDesignForm`

- [ ] Create design.
- [ ] Edit design.
- [ ] Invalid pool relationship.
- [ ] Layout/quantity validation.
- [ ] TODO-comment integration.
- [ ] Permission variants.
- [ ] Persistence and rollback.

### `FeatureKitForm`

- [ ] Create feature kit.
- [ ] Edit feature kit.
- [ ] Duplicate identifier/name.
- [ ] Feature type and sequence validation.
- [ ] Invalid feature relationships.
- [ ] Admin/insider permissions.

### `IndexKitForm`

- [ ] Create index kit.
- [ ] Edit index kit.
- [ ] Kit type variants.
- [ ] Duplicate identifier/name.
- [ ] Invalid kit type/barcode configuration.
- [ ] Admin-only behavior.

### `KitForm`

- [ ] Create generic kit.
- [ ] Edit generic kit.
- [ ] Kit category/type validation.
- [ ] Duplicate identifier.
- [ ] Admin/insider permissions.
- [ ] Invalid kit relationships.

### `SeqRunForm`

- [ ] Create sequencing run.
- [ ] Edit sequencing run.
- [ ] Status transition validation.
- [ ] Experiment/flow-cell/sequencer relationships.
- [ ] Run-folder and flow-cell validation.
- [ ] Insider-only behavior.
- [ ] Deleteability interaction.

### `SequencerForm`

- [ ] Create sequencer.
- [ ] Edit sequencer.
- [ ] Duplicate name.
- [ ] Model validation.
- [ ] Insider/admin permissions.
- [ ] Delete behavior when referenced.

## 3. Standalone actions

For every action, test GET/render, valid POST, invalid POST, CSRF, authorization, persistence, rollback, duplicate/replay behavior, response status, redirect, flash, and HX headers. Add target-context variants where listed.

### Request, project, group, and sharing actions

- [ ] `AddProjectAssigneeAction`: add valid assignee; duplicate assignee; invalid user; remove/access permissions.
- [ ] `AddSeqRequestAssigneeAction`: add valid assignee; duplicate; invalid user; owner/insider permissions.
- [ ] `AddSeqRequestShareEmailAction`: valid email; duplicate email; malformed/maximum-length email; permission checks.
- [ ] `ProcessSeqRequestAction`: accept; reject; invalid status; required comment/notification fields; insider permissions.
- [ ] `SubmitSeqRequestAction`: valid submission; missing required fields; invalid state; owner versus insider behavior.
- [ ] `AddUserToGroupAction`: add user; duplicate membership; invalid user; owner/manager/admin permissions.
- [ ] `ShareDirectoryAction`: share valid directory; invalid/traversal path; duplicate share; expiry and recipient variants.
- [ ] `AssociatePathAction`: associate path with project; library; experiment; sequencing request; invalid entity; duplicate association; unauthorized path.
- [ ] `MergeProjectsAction`: merge valid projects; same project; unauthorized projects; incompatible same-name samples; empty projects; rollback on failure.

### Sample, library, pool, and prep actions

- [ ] `SampleAttributeTableAction`: valid attribute update; new attribute; type/value conflict; missing sample; unauthorized project; rollback.
- [ ] `StoreSamplesAction`: store samples; store libraries; store pools; mixed selection; invalid status; unauthorized resources; idempotent repeat.
- [ ] `LibraryPrepAction`: select accepted libraries; already-prepped library; invalid lab prep; empty selection; insider permissions.
- [ ] `UploadLibraryPrepSpreadsheetAction`: valid spreadsheet; missing columns; malformed spreadsheet; duplicate libraries; invalid statuses; partial rollback.
- [ ] `SelectPoolLibrariesAction`: add libraries to pool; remove/reselect; incompatible library type; duplicate library; pool status/permission variants.
- [ ] `SamplePoolingAction`: assign samples to pools; move assignments; duplicate sample; invalid pool; status and ownership checks.
- [ ] `DilutePoolsAction`: valid dilution; zero/negative values; concentration and volume bounds; multiple pools; persistence and rollback.
- [ ] `EditLibraryPropertiesAction`: project context; sequence-request context; library context; dynamic columns; invalid/missing values; unauthorized context.
- [ ] `LibraryFeaturesAction`: add/edit/remove features; duplicate feature; invalid feature kit; library status/permission checks.
- [ ] `CheckBarcodeClashesAction`: no clash; clash; mixed kits; empty selection; invalid libraries; permission checks.
- [ ] `SelectExperimentPoolsAction`: select valid pools; already-associated pools; incompatible status; combined/separate workflow context; permission checks.

### Kit, protocol, barcode, and sequencing actions

- [ ] `AddKitsToProtocolAction`: add kit combination; duplicate combination; invalid kit; incompatible kit types; protocol permissions; rollback.
- [ ] `EditKitFeaturesAction`: create/edit/delete feature rows; duplicate sequences; invalid feature type; admin permissions; spreadsheet errors.
- [ ] `QueryBarcodeSequencesAction`: valid query; empty query; invalid sequence; limit bounds; no matches; insider permissions.
- [ ] `BarcodeConstraintsAction`: compatible set; incompatible set; missing library; duplicate barcode; invalid kit/type; controlled validation response.
- [ ] `SetExperimentCyclesAction`: valid cycles; zero/negative cycles; platform bounds; combined/separate lane variants; status/permission checks.
- [ ] `GenerateSequencerLoadingChecklistAction`: valid experiment; missing lanes/pools; invalid template parameters; output content; permission checks.
- [ ] `BillingAction`: valid experiment selection; empty selection; invalid status; duplicate export; insider/admin permissions; generated output.
- [ ] `ReseqAction`: indexed libraries; raw libraries; mixed selection; invalid status; duplicate resequencing; permission checks.

### Specialized action variants

#### Lane pooling

- [ ] `LanePoolsCombinedAction`: one combined lane; valid pool ratios; invalid/zero ratios; molarity warnings; qubit lookup; persistence.
- [ ] `LanePoolsSeparateAction`: multiple lanes; per-lane pool assignments; missing lane; invalid ratios; molarity warnings; persistence.

#### Read distribution

- [ ] `DistributeReadsCombinedAction`: combined lanes; valid read allocation; totals mismatch; zero/negative reads; persistence.
- [ ] `DistributeReadsSeparateAction`: separate lanes; per-lane allocation; missing lane; totals mismatch; persistence.

#### Flow-cell loading

- [ ] `LoadFlowCellCombinedAction`: combined-lane load; valid flow cell; missing/duplicate flow cell; status validation; persistence.
- [ ] `LoadFlowCellSeparateAction`: separate-lane load; per-lane flow cells; duplicate flow cell; missing lane; persistence.

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

- [ ] Select one eligible sample/library.
- [ ] Select multiple libraries.
- [ ] Empty/ineligible selection.
- [ ] Edit library table with valid values.
- [ ] Invalid dynamic library fields.
- [ ] Back navigation preserves selection/table state.
- [ ] Completion updates library state.
- [ ] Unauthorized and expired-state behavior.

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

- [ ] Separate-lane QC flow.
- [ ] Combined-lane QC flow.
- [ ] Valid phi-X values.
- [ ] Valid fragment-size values.
- [ ] Valid original qubit concentration.
- [ ] Missing/negative/out-of-range values.
- [ ] Missing lane and duplicate lane submissions.
- [ ] Insider-only authorization.
- [ ] Completion persists all lane metrics.
- [ ] Completion clears Redis state.
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

## 5. Cross-cutting response and security tests

- [ ] Every form/action rejects missing CSRF tokens.
- [ ] Every protected route rejects anonymous users correctly.
- [ ] Insider-only and admin-only routes reject normal users.
- [ ] Entity-level permissions are checked for every resource context.
- [ ] GET renders do not mutate database state.
- [ ] POST/PUT/DELETE methods match template `hx-*` methods.
- [ ] Successful HTMX responses contain expected `HX-Redirect`, `HX-Trigger`, and flash behavior.
- [ ] Invalid submissions return the expected `202` form response rather than a generic `500`.
- [ ] Standard browser requests return full-page responses where intended.
- [ ] Database changes are committed only after successful completion.
- [ ] Failed actions/workflows leave no partial records or files.
- [ ] Repeated submissions are safe or explicitly rejected.
- [ ] Missing resources return controlled `404` responses.
- [ ] Invalid parameters return controlled `400`/`422` responses.
- [ ] Route endpoint names used by templates resolve against the FastAPI route registry.
- [ ] Redis workflow state cannot be read or modified by another user.
- [ ] File uploads and generated files cannot escape configured roots.
