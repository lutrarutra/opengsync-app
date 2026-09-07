# QC-only sequencing request type

## Goal

Add a fourth sequencing request type for libraries submitted for quality control only. QC-only must be unmistakable in request creation and request views, must not enter sequencing/preparation workflows, and must use library-level QC statuses after receipt:

```text
Request:  DRAFT -> SUBMITTED -> ACCEPTED -> SAMPLES_RECEIVED -> ARCHIVED
Libraries:                         ... -> QC_PENDING -> QC_COMPLETED
                                           \-> failed/rejected/archived terminal outcomes
```

The QC workflow is included in this plan. It will select samples from a received QC-only request, collect custom spreadsheet values for one row per linked library, save them to `Library.properties`, complete selected libraries, and archive the request when every library is beyond QC pending. The later design of additional QC-specific validation/reporting remains deferred.

## Decisions confirmed

- Add QC-only as a fourth `SubmissionType`; preserve the existing Un-Pooled Libraries type and its meaning.
- QC-only requests contain submitted libraries, not raw samples.
- Acceptance does not immediately start QC. The request remains `ACCEPTED` until all submitted libraries are received/stored; then the request becomes `SAMPLES_RECEIVED` and its libraries enter library-level `QC_PENDING`.
- Implement the first QC workflow: select samples from a QC-only request, present one spreadsheet row per linked library, save custom QC columns to `Library.properties`, mark selected libraries `QC_COMPLETED`, and archive the request when all its libraries have reached a terminal QC status.
- Completion is tracked per library: each received QC-only request starts library QC at `QC_PENDING`, selected libraries become `QC_COMPLETED`, and the request moves directly from its received state to `ARCHIVED` once all libraries are beyond QC pending. No request-level `QC_COMPLETED` state is needed.

## Existing implementation map

- `packages/opengsync-db/opengsync_db/categories/SubmissionType.py` defines the three request types and form option lists.
- `packages/opengsync-db/opengsync_db/categories/SeqRequestStatus.py` defines the request lifecycle and numeric ordering used by status comparisons and the progress bar.
- `services/backend/server/forms/models/SeqRequestForm.py` creates/edits request metadata and currently hides Un-Pooled Libraries in the public form option list.
- `services/opengsync-app/templates/forms/seq_request/seq_request.html` renders the submission type and descriptions.
- `services/backend/server/forms/actions/ProcessSeqRequestAction.py` accepts/rejects submitted requests.
- `services/backend/server/forms/actions/StoreSamplesAction.py` advances accepted requests after material is stored; it currently branches between raw samples, pooled libraries, and unpooled libraries.
- `services/opengsync-app/templates/seq_request_page.html` and the table/search/feed templates expose the request type and status; workflow cards are currently selected by submission type.
- `services/opengsync-app/templates/components/status_bar.jinja2` assumes the normal status sequence is numerically ordered through `FINISHED`.
- `packages/opengsync-db/opengsync_db/core/actions.py` contains submit/clone actions and must not accidentally route QC-only requests through sequencing clone semantics.
- `services/pytest/tests/server/forms/test_seq_request_form.py` is the existing request-form integration-test location; DB/action tests and store-sample tests should be extended nearby or added in their corresponding test directories.
- `alembic/versions/` contains schema migrations, but this feature appears to require no new database column because request type and status are integer enum values.

## Implementation plan

### 1. Extend domain enums and shared type helpers

1. Add `QC_ONLY` to `SubmissionType` with a stable new ID (do not renumber existing values), a clear label such as `QC Only`, abbreviation, and description stating that libraries are submitted for QC and are not sequenced.
2. Do not add request-level `QC_COMPLETED`; retain the request's received state while QC is in progress and transition directly to `ARCHIVED` after all libraries are terminal. If a request-level `QC_PENDING` label is still desired for visibility, define it separately from the received state and document the transition clearly; otherwise avoid adding an unused request status.
3. Add stable library-level QC statuses (`QC_PENDING`, `QC_COMPLETED`) without renumbering existing library statuses. Explicitly define which library statuses count as beyond QC pending for automatic request archival.
3. Add status descriptions/icons suitable for customer-facing tables and tooltips.
4. Audit enum helper methods (`as_list`, `as_selectable`, `get`, serialization/query parsing) so QC-only is selectable while existing callers that intentionally exclude Un-Pooled Libraries retain their current behavior.
5. Add small domain predicates/helpers if useful (for example `is_qc_only`) rather than repeating raw enum comparisons throughout routes/templates.

### 2. Update request creation/edit behavior

1. Include QC Only in the request form's selectable submission types.
2. Keep the existing library attachment workflow applicable to QC-only requests and validate that raw-sample-specific paths are not offered or accepted for this type.
3. Ensure edit forms round-trip QC Only correctly without silently converting it to another type.
4. Update the explanatory list in `forms/seq_request/seq_request.html` so the QC-only option explicitly says “libraries submitted for QC only; no sequencing”.
5. Add/adjust form tests covering creation, edit persistence, option visibility, and preservation of the existing three types.

### 3. Implement the acceptance/receipt status transition

1. Leave `ProcessSeqRequestAction` acceptance behavior as `ACCEPTED` for QC-only requests.
2. Extend `StoreSamplesAction` with a QC-only branch. Once every library belonging to the request has reached the stored/received threshold, keep/set the request at `SAMPLES_RECEIVED`, initialize eligible libraries at library-level `QC_PENDING`, and persist the request/material state.
3. Make the branch robust for partial receipt: do not mark the request received or initialize QC until all libraries are stored; do not transition an empty request; do not run raw-sample, pooling, or sequencing advancement logic for QC-only.
4. Define the exact accepted library statuses used by the existing store action and ensure QC-only libraries can be selected for receipt under the same permissions as submitted libraries.
5. Add action/integration tests for accepted-but-not-yet-received, partially received, and fully received QC-only requests, plus a regression test showing normal request types keep their existing transitions.
6. Expose the QC workflow only when a QC-only request is `SAMPLES_RECEIVED` and its libraries have QC pending work (or when insiders need to review/reopen it, according to the final permission policy).

### 4. Implement the QC workflow

1. Add a QC workflow/action entry point on the QC-only request page. It should first present a selectable list of samples associated with the request, restricted to libraries belonging to that request.
2. After sample selection, load all linked libraries for the selected samples. The editable spreadsheet must use one row per library because values are saved to `Library.properties`; if a sample has multiple linked libraries, each library gets its own row.
3. Build spreadsheet columns following the existing dynamic sample-attribute implementation in `services/backend/server/forms/actions/SampleAttributeTableAction.py` and `services/backend/server/components/tables/spreadsheet.py`: immutable database-object identity columns, an initially empty editable QC column, and support for adding, renaming, and deleting custom columns.
4. Use a stable identity representation for the first column, preferably a read-only library identifier/name pair or a single `name + id` value that is validated against the selected request. Do not trust submitted names alone; validate every row's library ID and request membership.
5. On submit, validate column names, duplicate columns, row identities, and spreadsheet cell values using the existing spreadsheet input machinery. Define how blank cells are handled: blank values should remove an existing property for that column, while untouched columns should not create meaningless values.
6. Save QC values in `Library.properties` as JSONB. Preserve unrelated existing properties, use stable column keys, and normalize values to JSON-compatible scalar values. Follow the merge/update semantics of `Sample.set_attribute` rather than replacing the whole properties object.
7. Mark every selected library as the library-level QC-completed status. Keep unselected libraries at the library-level QC-pending status so QC can be completed in batches.
8. After saving, inspect all libraries belonging to the QC-only request. If every library is beyond library-level `QC_PENDING`—including completed, failed, rejected, or archived terminal outcomes—set the request status to `SeqRequestStatus.ARCHIVED`; otherwise leave the request at `SAMPLES_RECEIVED`.
9. Make the transition atomic: validate all rows and selections before mutating libraries, then save properties/statuses and request archival in one transaction. Return a request-page redirect and a useful summary flash.
10. Add tests for sample selection, one-row-per-library expansion, multiple libraries per sample, custom column add/rename/delete, preservation of unrelated `Library.properties`, partial completion, failed/rejected terminal libraries, invalid library IDs, and automatic request archival.

### 5. Make QC-only visible and prevent sequencing UI paths

1. Make the request header display a prominent QC-only badge/label in addition to the submission type text; use the same label in request tables/search/feed where space permits.
2. Add a dedicated status-bar branch or status presentation for QC-only requests. It must not render library QC statuses as if they were normal sequencing milestones; it should show the request's `ACCEPTED`, `SAMPLES_RECEIVED`, and `ARCHIVED` states and expose library QC progress separately.
3. Update request-page copy/tooltips to state that the libraries are for QC only and are not scheduled for sequencing.
4. Hide or disable sequencing-only workflow cards and controls for QC-only requests (library annotation/preparation, pooling, re-indexing, barcode-clash checks, sequencing/preparation feeds, and any “ready for sequencing” actions). Keep metadata, files, samples/libraries, comments, assignees, and future QC workflow areas available as appropriate.
5. Audit dashboard/feed filters and status lists so QC-only requests remain visible to insiders and request owners while in `ACCEPTED`/`SAMPLES_RECEIVED`, and do not appear in sequencing-preparation queues.
6. Add a consistent visual QC marker in tables and search/select lists for both QC-only libraries and QC-only sequencing requests. Use a muted superscript marker such as `<sup class="text-muted">(QC)</sup>` (or an equivalent shared template macro) next to the displayed name, without changing the underlying searchable/selectable value.
7. Apply the marker to shared and repeated presentation points, including library search results, library tables, sample-library/request-library tables, workflow selection tables, sequencing-request search results, request tables, dashboard feeds, and request-related links where the object is identifiable as QC-only. Prefer shared macros/components to prevent inconsistent markup.
8. Ensure backend query/select-list objects load enough context to determine QC-only status (`library.seq_request.submission_type` or an equivalent query projection), without introducing N+1 queries. Add rendering tests or endpoint checks for both marked and unmarked objects.
9. Audit exports and clone actions. The export should identify QC Only. For QC-only requests, hide and disable all clone variants and the Re-Sequence Libraries action in the request-page Manage/workflow UI, and reject direct clone/re-sequence endpoint calls server-side with a clear bad-request response. QC-only requests must never be silently converted into sequencing requests.

### 6. Database/migration and compatibility review

1. Confirm no schema migration is needed for integer-backed enum additions. If the project maintains DB constraints/reference data for enum IDs, add the corresponding migration instead of relying only on Python enums.
2. Check API/query filtering and any generated OpenAPI/select options for the new enum value.
3. Check older records and all `SubmissionType` comparisons so existing raw, pooled, and unpooled requests remain unchanged.
4. Check status ordering, archived/rejected/failed handling, permissions, and timestamp semantics. Decide whether QC archival sets `timestamp_finished_utc`; follow existing archival semantics and do not mark completion prematurely.

### 7. Verification

- Unit/integration tests for enum serialization and form creation/edit.
- Store/receipt transition tests for all QC-only receipt states.
- QC workflow tests for selection, spreadsheet editing, JSONB persistence, library completion, partial completion, and automatic archival.
- Template/render tests or endpoint checks for visible QC-only labels and status display.
- Regression tests for normal submission types, review/acceptance, dashboard feeds, and sequencing workflow visibility.
- Run the repository's configured lint/type/test tasks after implementation and manually inspect the request page, request list, dashboard, and store-material dialog for QC-only requests.

## Acceptance criteria

- A user can select “QC Only” as a fourth request type.
- The creation form describes it as libraries submitted for QC only and not for sequencing.
- The request page, tables, feeds, search results, and selectable lists clearly identify QC-only requests and libraries with a muted superscript `(QC)` marker.
- QC-only request pages do not show or enable Clone (Pooled), Clone (Indexed), Clone (Raw), or Re-Sequence Libraries; direct endpoint calls are rejected server-side.
- The marker is visual-only and does not alter names, IDs, search terms, form values, or copy/export values.
- Acceptance leaves a QC-only request in `ACCEPTED`.
- Receipt of only some libraries leaves it in `ACCEPTED`.
- Receipt of all libraries changes the request to `SAMPLES_RECEIVED` and libraries to library-level `QC_PENDING`.
- QC can be performed in batches by selecting samples; each selected sample expands to its linked library rows.
- QC values are saved to `Library.properties` without overwriting unrelated properties.
- Selected libraries become library-level `QC_COMPLETED`; once all libraries are beyond QC pending, the request moves from `SAMPLES_RECEIVED` to `ARCHIVED`.
- No sequencing/pooling/preparation workflow is offered or triggered for QC-only requests.
- Existing request types and their status transitions continue to work.
