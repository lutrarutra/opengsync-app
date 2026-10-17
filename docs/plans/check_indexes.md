## Plan: IndexCheckWorkflow — New barcode orientation validation workflow

**TL;DR**: Create a new 3-step FastAPI workflow (`IndexCheckWorkflow`) that lets insiders select libraries with unvalidated barcode orientations, verify whether indexes come from kits or are custom, correct orientations (including reverse-complementing if needed), and finalize all to `FORWARD`. Add as a **new accordion section in the seq_request-review checklist, positioned before "Check Barcodes"**. **Replace the "Mark as Checked" button** with this workflow. Default to not-applicable for non-POOLED/UNPOOLED submissions.

---

### Decisions
- **Not replacing** `CheckBarcodeClashesAction` — keep that separate
- **Remove** the "Mark as Checked" (`confirm_barcodes`) button — IndexCheckWorkflow is the only way to validate orientations
- **`check_barcodes` is derived, not a flag**: complete when every index of every library in the request is `FORWARD` or a kit index (`LibraryIndex.is_kit_index()`); manual check/uncheck returns 400
- **Unvalidated** means `None`, `FORWARD_NOT_VALIDATED` or `REVERSE_COMPLEMENT_NOT_VALIDATED` — `None` happens when a submission mixes kit and custom barcodes (the library annotation `BarcodeMatchForm` is skipped)
- **Kit index** in the verify step uses the same rule as `is_kit_index()`; a kit i7 with a custom i5 is verified manually and reverse-complementing only changes the custom barcode
- **Verify step is a spreadsheet** (jspreadsheet, like the barcode input): "Library [Index ID]" (library name + library index id), Orientation (Forward / Reverse Complement), i7/i5 names and sequences. Only Orientation is editable; rows are matched to their stored index by the index id (sorting is safe), and everything else is taken from the stored table. The confirmation step shows each index as it will be saved (`library_index_cell`) and the assigned orientation. `REVERSE_COMPLEMENT_NOT_VALIDATED` is pre-filled as Reverse Complement; Reverse Complement on a kit index is rejected
- **No manual check** for the `index_check` review step — it is only marked checked by completing the workflow (`review-check/index_check` returns 400); an Uncheck button remains
- **3 steps**: Select Libraries → Verify/Correct Orientation → Complete
- **Not-applicable**: `index_check` step defaults to `None` for `RAW_SAMPLES` and `QC_ONLY`
- **Context**: Supports `seq_request_id`, `lab_prep_id`, `pool_id` (like ReindexWorkflow)
- **Pattern**: Follows `ReindexWorkflow` architecture (FastAPI + HTMXWorkflow)

---

### Steps

#### Phase 1: Create workflow directory and base classes

**Step 1.1** — Create `services/backend/server/forms/workflows/index_check/__init__.py`
- Export all step classes and `IndexCheckWorkflow`
- Follow pattern of `reindex/__init__.py`

**Step 1.2** — Create `services/backend/server/forms/workflows/index_check/IndexCheckWorkflow.py`
- `IndexCheckWorkflowStep(HTMXWorkflowStep)` — same pattern as `ReindexWorkflowStep` with `post_url`, `Init`, `Validate`
- `IndexCheckWorkflow(HTMXWorkflow)` — stores `seq_request_id`, `lab_prep_id`, `pool_id`, `_query_params`
- `get_next_step()`: `SelectLibrariesForm` → `VerifyOrientationsForm` → `CompleteIndexCheckForm`
- `Begin()` route → `SelectLibrariesForm.Init()`
- `Router()` → assembles all step routers under `/index-check` prefix

#### Phase 2: Create workflow step forms

**Step 2.1** — Create `SelectLibrariesForm.py`
- Extends `IndexCheckWorkflowStep`
- Uses `LibrarySelectTableField` with `browse_context="index-check"`
- **Default filter**: `status_in` = active libraries, `indexed` = `True` (libraries with indices)
- On init, pre-filter libraries to only those with `FORWARD_NOT_VALIDATED` or `REVERSE_COMPLEMENT_NOT_VALIDATED` orientations
- On submit: builds `library_table` DataFrame (library_id, library_name, library_type) and `barcode_table` DataFrame (library_id, sequence_i7, sequence_i5, orientation_i7, orientation_i5, kit_i7, kit_i5) — only rows with unvalidated orientations
- Stores tables in `workflow.tables`
- Advances to `VerifyOrientationsForm`

**Step 2.2** — Create `VerifyOrientationsForm.py`
- Extends `IndexCheckWorkflowStep`
- For each library in the barcode table, shows:
  - Library name and current index sequences
  - Whether the index is from a kit (kit_i7/kit_i5 not null) → auto-set to `FORWARD`
  - If custom (no kit): orientation selector (Forward / Reverse Complement) — same pattern as `BarcodeMatchForm`
  - If user selects "Reverse Complement": reverse-complement the sequence using `barcodes.reverse_complement()`
- On submit:
  - For kit-matched indexes: set `orientation = BarcodeOrientation.FORWARD`
  - For custom "Forward": set `orientation = BarcodeOrientation.FORWARD`
  - For custom "Reverse Complement": reverse-complement sequence, set `orientation = BarcodeOrientation.FORWARD`
  - Store results in `workflow.metadata["orientation_results"]`
- Advances to `CompleteIndexCheckForm`

**Step 2.3** — Create `CompleteIndexCheckForm.py`
- Extends `IndexCheckWorkflowStep`
- Shows summary of changes made (which libraries had orientations corrected, which were reverse-complemented)
- On submit: persists changes to DB
  - For each library in results: update `LibraryIndex.orientation` to `FORWARD`
  - If sequence was reverse-complemented: update `LibraryIndex.sequence_i7` / `LibraryIndex.sequence_i5`
  - Saves via `session.save()`
- If started from a seq_request and no unvalidated indices remain in that request: sets `review_checklist["index_check"] = True`; otherwise flashes a warning and leaves the step unchecked
- Calls `workflow.complete()` to clean up Redis
- Returns redirect to the originating context (seq_request page, lab_prep page, etc.)

#### Phase 3: Register workflow

**Step 3.1** — Update `services/backend/server/forms/workflows/__init__.py`
- Add `from . import index_check`

**Step 3.2** — Update `services/backend/server/routes/htmx/workflows.py`
- Add `router.include_router(wf.index_check.IndexCheckWorkflow.Router())`

#### Phase 4: Integrate into review checklist

**Step 4.1** — Update `services/backend/server/routes/htmx/seq_requests.py`
- Add `index_check` to `get_review_checklist()` defaults:
  - Default to `None` for `RAW_SAMPLES` and `QC_ONLY`
  - Default to `False` for `POOLED_LIBRARIES` and `UNPOOLED_LIBRARIES`
- Update `indices_checked` logic to also check for `REVERSE_COMPLEMENT_NOT_VALIDATED` (currently only checks `None` and `FORWARD_NOT_VALIDATED`)

**Step 4.2** — Update `services/backend/templates/components/checklists/seq_request-review.html`
- **Add a new accordion section** for `index_check` **before** the "Check Barcodes" section (between "Check Multiplexing" and "Check Barcodes")
  - Header: `{% if index_check %}✅{% else %}⚠️{% endif %} Check Index Orientations`
  - Disabled (🚫) for `RAW_SAMPLES` submissions
  - Body contains:
    - Instructions explaining what to look for
    - Button launching `IndexCheckWorkflow.Begin` with `seq_request_id`
    - Library index table (same as currently in "Check Barcodes" section)
    - No Check button (step is checked by completing the workflow); Uncheck button when checked
- In the "Check Barcodes" accordion body:
  - **Remove** the "Mark as Checked" (`confirm_action_button`) button
  - Keep "Check Clashes" and "Reindex Libraries" buttons as-is

**Step 4.3** — Remove `confirm_seq_request_barcodes` endpoint
- Delete the `confirm_seq_request_barcodes` route from `services/backend/server/routes/htmx/seq_requests.py`
- Remove any references in templates

#### Phase 5: Templates

**Step 5.1** — Create `services/backend/templates/workflows/index_check/select-libraries.html`
- Library selection table with pre-filtered unvalidated libraries
- Follow pattern of `workflows/reindex/select-samples.html`

**Step 5.2** — Create `services/backend/templates/workflows/index_check/verify-orientations.html`
- For each library: show current index info, kit status, orientation selector
- Show reverse-complement preview when RC is selected
- Follow pattern of `workflows/reindex/barcode-match.html`

**Step 5.3** — Create `services/backend/templates/workflows/index_check/complete.html`
- Summary of changes
- Follow pattern of `workflows/reindex/complete.html`

---

### Relevant files

**New files to create:**
- `services/backend/server/forms/workflows/index_check/__init__.py`
- `services/backend/server/forms/workflows/index_check/IndexCheckWorkflow.py`
- `services/backend/server/forms/workflows/index_check/SelectLibrariesForm.py`
- `services/backend/server/forms/workflows/index_check/VerifyOrientationsForm.py`
- `services/backend/server/forms/workflows/index_check/CompleteIndexCheckForm.py`
- `services/backend/templates/workflows/index_check/select-libraries.html`
- `services/backend/templates/workflows/index_check/verify-orientations.html`
- `services/backend/templates/workflows/index_check/complete.html`
- `services/pytest/tests/server/workflows/test_index_check.py`

**Files to modify:**
- `services/backend/server/forms/workflows/__init__.py` — add `index_check` import
- `services/backend/server/routes/htmx/workflows.py` — register `IndexCheckWorkflow.Router()`
- `services/backend/server/routes/htmx/seq_requests.py` — add `index_check` to checklist defaults, update `indices_checked` logic, remove `confirm_seq_request_barcodes`
- `services/backend/templates/components/checklists/seq_request-review.html` — add IndexCheck button, remove "Mark as Checked" button
- `packages/opengsync-db/opengsync_db/models/SeqRequest.py` — add `index_check` to `get_review_checklist()` defaults

**Reference files (patterns to follow):**
- `services/backend/server/forms/workflows/reindex/ReindexWorkflow.py` — workflow structure
- `services/backend/server/forms/workflows/reindex/SelectSamplesForm.py` — library selection pattern
- `services/backend/server/forms/workflows/reindex/BarcodeMatchForm.py` — orientation/kit matching pattern
- `services/backend/server/forms/workflows/reindex/CompleteReindexForm.py` — completion pattern
- `services/backend/server/utils/barcodes.py` — `reverse_complement()` utility
- `packages/opengsync-db/opengsync_db/categories/BarcodeOrientation.py` — orientation enum

---

### Verification

#### Automated Tests

Create `services/pytest/tests/server/workflows/test_index_check.py` with the following test cases:

**Phase A: Workflow step navigation**
1. `test_index_check_begin` — GET `/htmx/workflows/index-check/begin` with `seq_request_id` returns 200 with select-libraries template
2. `test_index_check_select_libraries_submit` — POST select-libraries with library IDs, verify `library_table` and `barcode_table` stored in workflow.tables
3. `test_index_check_verify_orientations_submit` — POST verify-orientations with orientation choices, verify metadata stored
4. `test_index_check_complete_submit` — POST complete, verify DB updated and Redis cleaned up

**Phase B: Library filtering (SelectLibrariesForm)**
5. `test_select_libraries_filters_unvalidated_only` — Create libraries with mixed orientations (FORWARD, FORWARD_NOT_VALIDATED, REVERSE_COMPLEMENT_NOT_VALIDATED). Verify only unvalidated ones appear in pre-filtered selection.
6. `test_select_libraries_all_validated` — All libraries already have FORWARD orientation. Verify workflow shows empty selection or skips gracefully.
7. `test_select_libraries_no_indices` — Libraries exist but have no LibraryIndex rows. Verify they are excluded from selection.

**Phase C: Orientation verification (VerifyOrientationsForm)**
8. `test_verify_kit_index_auto_forward` — Kit-matched index (`is_kit_index()` returns True). Verify it auto-sets to FORWARD without user input.
9. `test_verify_custom_index_forward` — Custom index with user selecting "Forward". Verify orientation set to FORWARD, sequence unchanged.
10. `test_verify_custom_index_reverse_complement` — Custom index with user selecting "Reverse Complement". Verify sequence is reverse-complemented and orientation set to FORWARD.
11. `test_verify_tenx_atac_4_indices` — 10x ATAC library with 4 i7 indices, all unvalidated. Verify all 4 LibraryIndex rows get orientation set to FORWARD. If one is REVERSE_COMPLEMENT_NOT_VALIDATED, verify its sequence is reverse-complemented.
12. `test_verify_dual_index_both_orientations` — Dual-index library where i7 is FORWARD_NOT_VALIDATED and i5 is REVERSE_COMPLEMENT_NOT_VALIDATED. Verify both get corrected.
13. `test_verify_mixed_libraries` — Multiple libraries with different index types (single, dual, ATAC). Verify each is handled correctly.

**Phase D: Completion (CompleteIndexCheckForm)**
14. `test_complete_persists_orientation` — After completion, verify `LibraryIndex.orientation == BarcodeOrientation.FORWARD` for all affected indices.
15. `test_complete_reverse_complements_sequence` — After completion with RC selected, verify `LibraryIndex.sequence_i7` is the reverse complement of the original.
16. `test_complete_redis_cleanup` — After completion, verify all Redis keys for the workflow UUID are deleted.
17. `test_complete_redirects_to_context` — After completion, verify redirect goes back to the originating seq_request/lab_prep page.

**Phase E: Review checklist integration**
18. `test_index_check_checklist_default_pooled` — For POOLED_LIBRARIES submission, `index_check` defaults to `False`.
19. `test_index_check_checklist_default_unpooled` — For UNPOOLED_LIBRARIES submission, `index_check` defaults to `False`.
20. `test_index_check_checklist_default_raw_samples` — For RAW_SAMPLES submission, `index_check` defaults to `None` (not-applicable).
21. `test_index_check_checklist_default_qc_only` — For QC_ONLY submission, `index_check` defaults to `None` (not-applicable).
22. `test_index_check_manual_check_rejected` — POST `review-check/index_check` returns 400 and leaves the checklist unchanged; `test_complete_marks_review_checklist` / `test_complete_partial_does_not_mark_review_checklist` cover the workflow marking the step.
23. `test_index_check_template_renders_before_barcodes` — Verify the `index_check` accordion section appears before `check_barcodes` in the rendered HTML.

**Phase F: Edge cases**
24. `test_index_check_reverse_complement_not_validated` — Library with REVERSE_COMPLEMENT_NOT_VALIDATED orientation. Verify it's included in pre-filter and gets reverse-complemented.
25. `test_index_check_mixed_validated_and_not` — Library with 2 indices: one FORWARD, one FORWARD_NOT_VALIDATED. Verify only the unvalidated one is processed.
26. `test_index_check_lab_prep_context` — Start workflow with `lab_prep_id` instead of `seq_request_id`. Verify it works.
27. `test_index_check_pool_context` — Start workflow with `pool_id`. Verify it works.
28. `test_index_check_insider_only` — Non-insider user gets 403 when accessing workflow.
29. `test_index_check_previous_navigation` — Test back/previous button returns to previous step with preserved state.

#### Manual Verification
1. Run the seq_request-review checklist page and confirm the new "Check Index Orientations" accordion section appears **before** "Check Barcodes" for POOLED/UNPOOLED submissions
2. Confirm the "Mark as Checked" button is gone from the "Check Barcodes" section
3. Launch IndexCheckWorkflow from seq_request context → confirm libraries with unvalidated orientations are pre-selected
4. Verify that kit-matched indexes auto-set to FORWARD without requiring user input
5. Verify that custom indexes show orientation selector, and selecting "Reverse Complement" reverse-complements the sequence
6. Confirm that after completion, all selected libraries' indexes have `orientation = BarcodeOrientation.FORWARD`
7. Confirm that `index_check` step shows as not-applicable (❗) for RAW_SAMPLES submissions
8. Run existing tests to ensure no regressions