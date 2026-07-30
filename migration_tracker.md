# Flask → FastAPI Migration Tracker

> Last updated: 2026-07-30

## Legend
- ✅ **Migrated** — Fully implemented in FastAPI
- 🔶 **Shell only** — Workflow class exists but form implementations are not migrated
- ❌ **Not started** — No FastAPI counterpart exists
- ⚠️ **Partial** — Some parts migrated, others not

---

## 1. Workflows (Multi-Step)

### 1.1 Fully Migrated Workflows

| # | Workflow | Legacy Path | FastAPI Path | Notes |
|---|----------|-------------|--------------|-------|
| 1 | **Library Annotation** | `workflows/library_annotation/` | `workflows/library_annotation/` | Full multi-step: ProjectSelect → SampleAnnotation → SampleAttributeAnnotation → SelectService → (Feature/OpenST/Visium/CRISPR/PooledLibrary) → BarcodeInput → BarcodeMatch → CompleteSAS. All sub-forms migrated. |
| 2 | **BA Report** | `workflows/ba_report/` | `workflows/ba_report/` | Multi-step: SelectSamples → UploadBA/ParseBAExcel → CompleteBA. All forms migrated. |
| 3 | **Qubit Measure** | `workflows/qubit_measure/` | `workflows/qubit_measure/` | Multi-step: SelectSamples → QubitMeasure → CompleteQubitMeasure. All forms migrated. |
| 4 | **Add Kits to Protocol** | `workflows/add_protocol_kits/` | `workflows/add_kits_to_protocol/` | Delegates to `AddKitsToProtocolAction`. Fully migrated. |

### 1.2 Shell-Only Workflows (Forms Not Migrated)

These have `HTMXWorkflow` class with `Begin()`, `Init()`, `Router()` but the actual form classes are not yet implemented in FastAPI.

| # | Workflow | Legacy Path | FastAPI Path | Missing Forms | Notes |
|---|----------|-------------|--------------|---------------|-------|
| 5 | **Reindex** | `workflows/reindex/` | `workflows/reindex/` | BarcodeInputForm, TENXATACBarcodeInputForm, BarcodeMatchForm, CompleteReindexForm | Multi-step: SelectSamples → BarcodeInput → (TENXATAC or BarcodeMatch) → CompleteReindex. Full workflow structure implemented — step forms need refinement. |
| 6 | **Relib** | `workflows/relib/` | `workflows/relib/` | LibraryEditTableForm | Multi-step: SelectSamples → LibraryEditTable. |
| 7 | **Merge Pools** | `workflows/` (MergePoolsForm.py) | `workflows/merge_pools/` | MergePoolsForm | Multi-step: SelectSamples → MergePools. |
| 8 | **Mux Prep** | `workflows/mux_prep/` | `workflows/mux_prep/` | OligoMuxForm, OCMMuxForm, FlexABCForm | ⚠️ FlexMuxForm partially covered by `FlexMuxPrepAction`. SamplePooling covered by `SamplePoolingAction`. |
| 9 | **Library Pooling** | `workflows/library_pooling/` | `workflows/library_pooling/` | CompleteLibraryPoolingForm | ⚠️ LibraryPoolingForm covered by `LibraryPoolingAction`. |
| 10 | **Library Remux** | `workflows/remux/` | `workflows/library_remux/` | FlexReMuxForm, OligoReMuxForm | Single-step per library. |
| 11 | **Select Library Protocols** | `workflows/select_library_protocols/` | `workflows/select_library_protocols/` | LibraryProtocolSelectForm, ProtocolMappingForm | Multi-step: LibraryProtocolSelect → ProtocolMapping. |
| 12 | **Share Project Data** | `workflows/share/` | `workflows/share_project_data/` | ShareProjectDataForm, AssociatePathForm | Single form. |
| 13 | **Lane QC** | `workflows/lane_qc.py` | `workflows/lane_qc/` | QCLanesForm, UnifiedQCLanesForm | Single form (separate or combined lanes). |
| 14 | **Select Experiment Pools** | `workflows/select_experiment_pools` (via SelectSamplesForm) | `workflows/select_experiment_pools/` | SelectSamplesForm integration | ⚠️ `SelectExperimentPoolsAction` exists as action. |

---

## 2. Actions (Single-Step, Migrated)

| # | Action | FastAPI Path | Legacy Source | Notes |
|---|--------|-------------|---------------|-------|
| 1 | **AddKitsToProtocolAction** | `actions/AddKitsToProtocolAction.py` | `workflows/add_protocol_kits/AddKitCombinationsFrom.py` | Spreadsheet-based kit management |
| 2 | **AddSeqRequestAssigneeAction** | `actions/AddSeqRequestAssigneeAction.py` | `AddSeqRequestAssigneeForm.py` | User search + assign |
| 3 | **AddSeqRequestShareEmailAction** | `actions/AddSeqRequestShareEmailAction.py` | `SeqRequestShareEmailForm.py` | Email sharing |
| 4 | **AddUserToGroupAction** | `actions/AddUserToGroupAction.py` | `AddUserToGroupForm.py` | Group membership |
| 5 | **BillingAction** | `actions/BillingAction.py` | `workflows/billing/SelectExperimentsForm.py` | Experiment selection for billing export |
| 6 | **CheckBarcodeClashesAction** | `actions/CheckBarcodeClashesAction.py` | `workflows/check_barcode_clashes/CheckBarcodeClashesForm.py` | Library selection + clash analysis |
| 7 | **DilutePoolsAction** | `actions/DilutePoolsAction.py` | `workflows/dilute_pools/DilutePoolsForm.py` | Pool dilution with molarity calculations |
| 8 | **EditLibraryPropertiesAction** | `actions/EditLibraryPropertiesAction.py` | `LibraryPropertiesForm.py` / `LibraryPropertyForm.py` | Spreadsheet-based property editing |
| 9 | **FlexMuxPrepAction** | `actions/FlexMuxPrepAction.py` | `workflows/mux_prep/FlexMuxForm.py` | Flex probe barcode assignment |
| 10 | **GenerateSequencerLoadingChecklistAction** | `actions/GenerateSequencerLoadingChecklistAction.py` | `SequencerLoadingChecklistForm.py` | Markdown template parameter filling |
| 11 | **LibraryPoolingAction** | `actions/LibraryPoolingAction.py` | `workflows/library_pooling/LibraryPoolingForm.py` | Spreadsheet-based library pooling |
| 12 | **LibraryPrepAction** | `actions/LibraryPrepAction.py` | `workflows/library_prep/LibraryPrepForm.py` | Library selection for prep |
| 13 | **ProcessSeqRequestAction** | `actions/ProcessSeqRequestAction.py` | `ProcessRequestForm.py` | Accept/reject sequencing requests |
| 14 | **ReseqAction** | `actions/ReseqAction.py` | `workflows/reseq/ReseqLibrariesForm.py` | Library resequencing (indexed/raw) |
| 15 | **SamplePoolingAction** | `actions/SamplePoolingAction.py` | `workflows/mux_prep/SamplePoolingForm.py` | Sample-to-pool assignment |
| 16 | **SelectExperimentPoolsAction** | `actions/SelectExperimentPoolsAction.py` | `workflows/select_experiment_pools` (SelectSamplesForm) | Pool selection for experiment |
| 17 | **SelectPoolLibrariesAction** | `actions/SelectPoolLibrariesAction.py` | N/A (new) | Library selection for a pool |
| 18 | **SetExperimentCyclesAction** | `actions/SetExperimentCyclesAction.py` | `EditExperimentCyclesForm.py` | R1/R2/I1/I2 cycle configuration |
| 19 | **StoreSamplesAction** | `actions/StoreSamplesAction.py` | `SelectSamplesForm.py` (store_samples context) | Sample/library/pool storage |
| 20 | **SubmitSeqRequestAction** | `actions/SubmitSeqRequestAction.py` | `SubmitSeqRequestForm.py` | Seq request submission with time/comment |
| 21 | **UploadLibraryPrepSpreadsheetAction** | `actions/UploadLibraryPrepSpreadsheetAction.py` | `workflows/library_prep/LibraryPrepForm.py` | Prep table spreadsheet upload |

### 2.1 Action Subdirectories (Combined/Separate Lane Variants)

| # | Action | FastAPI Path | Legacy Source |
|---|--------|-------------|---------------|
| 22 | **DistributeReadsCombinedAction** | `actions/dist_reads/DistributeReadsCombinedAction.py` | `workflows/dist_reads.py` (combined lanes) |
| 23 | **DistributeReadsSeparateAction** | `actions/dist_reads/DistributeReadsSeparateAction.py` | `workflows/dist_reads.py` (separate lanes) |
| 24 | **LanePoolsCombinedAction** | `actions/lane_pools/LanePoolsCombinedAction.py` | `workflows/lane_pools/UnifiedLanePoolingForm.py` |
| 25 | **LanePoolsSeparateAction** | `actions/lane_pools/LanePoolsSeparateAction.py` | `workflows/lane_pools/LanePoolingForm.py` |
| 26 | **LoadFlowCellCombinedAction** | `actions/load_flowcell/LoadFlowCellCombinedAction.py` | `workflows/load_flow_cell/UnifiedLoadFlowCellForm.py` |
| 27 | **LoadFlowCellSeparateAction** | `actions/load_flowcell/LoadFlowCellSeparateAction.py` | `workflows/load_flow_cell/LoadFlowCellForm.py` |

---

## 3. Legacy Workflows → Should Be Actions

These legacy workflow directories contain single-step forms that should be migrated as actions (not workflows):

| # | Legacy | Description | Recommendation |
|---|--------|-------------|----------------|
| 1 | `workflows/edit_kit_barcodes/` | EditCombinatorialKitBarcodesForm, EditDualIndexKitBarcodesForm, EditKitTENXATACBarcodesForm, EditSingleIndexKitBarcodesForm | **Action** — Single-step spreadsheet forms for editing index kit barcodes |

---

## 4. Legacy Top-Level Forms — Not Yet Migrated

These are in `packages/opengsync-server/opengsync_server/forms/` (not in workflows/):

| # | Legacy Form | Type | Recommendation |
|---|------------|------|----------------|
| 1 | `AddProjectAssigneeForm.py` | `actions/AddProjectAssigneeAction.py` | ✅ Migrated as action |
| 2 | `DirectoryShareForm.py` | `actions/ShareDirectoryAction.py` | ✅ Migrated as action |
| 3 | `EditKitFeaturesForm.py` | `actions/EditKitFeaturesAction.py` | ✅ Migrated as action |
| 4 | `LibraryFeaturesForm.py` | `actions/LibraryFeaturesAction.py` | ✅ Migrated as action |
| 5 | `QueryBarcodeSequencesForm.py` | `actions/QueryBarcodeSequencesAction.py` | ✅ Migrated as action |
| 6 | `SampleAttributeTableForm.py` | `actions/SampleAttributeTableAction.py` | ✅ Migrated as action |
| 7 | `SeqAuthForm.py` | `models/MediaFileForm.py` | ✅ Migrated (combined into MediaFileForm) |

## 5. Legacy Subdirectories — Migration Status

### 5.1 Auth Forms
| Legacy | FastAPI | Status |
|--------|---------|--------|
| `auth/ChangePasswordForm.py` | `auth/ChangePasswordForm.py` | ✅ Migrated |
| `auth/CompleteRegistrationForm.py` | `auth/CompleteRegistrationForm.py` | ✅ Migrated |
| `auth/LoginForm.py` | `auth/LoginForm.py` | ✅ Migrated |
| `auth/RegisterUserForm.py` | `auth/RegisterForm.py` | ✅ Migrated |
| `auth/ResetPasswordForm.py` | `auth/ResetPasswordForm.py` | ✅ Migrated |

### 5.2 Comment Forms

All legacy comment forms are combined into a single `models/CommentForm.py` that uses optional query parameters (`seq_request_id`, `experiment_id`, `lab_prep_id`) to determine the comment target.

| Legacy | FastAPI | Status |
|--------|---------|--------|
| `comment/CommentForm.py` | `models/CommentForm.py` | ✅ Migrated (combined) |
| `comment/ExperimentCommentForm.py` | `models/CommentForm.py` | ✅ Migrated (combined) |
| `comment/LabPrepCommentForm.py` | `models/CommentForm.py` | ✅ Migrated (combined) |
| `comment/SeqRequestCommentForm.py` | `models/CommentForm.py` | ✅ Migrated (combined) |

### 5.3 File/Attachment Forms

All legacy file/attachment forms are combined into a single `models/MediaFileForm.py` that uses optional query parameters (`seq_request_id`, `experiment_id`, `lab_prep_id`) to determine the upload target.

| Legacy | FastAPI | Status |
|--------|---------|--------|
| `file/ExperimentAttachmentForm.py` | `models/MediaFileForm.py` | ✅ Migrated (combined) |
| `file/FileInputForm.py` | `models/MediaFileForm.py` | ✅ Migrated (combined) |
| `file/LabPrepAttachmentForm.py` | `models/MediaFileForm.py` | ✅ Migrated (combined) |
| `file/SeqRequestAttachmentForm.py` | `models/MediaFileForm.py` | ✅ Migrated (combined) |

### 5.4 Model Forms
| Legacy | FastAPI | Status |
|--------|---------|--------|
| `models/ExperimentForm.py` | `models/ExperimentForm.py` | ✅ Migrated |
| `models/GroupForm.py` | `models/GroupForm.py` | ✅ Migrated |
| `models/LabPrepForm.py` | `models/LabPrepForm.py` | ✅ Migrated |
| `models/LibraryForm.py` | `models/LibraryForm.py` | ✅ Migrated |
| `models/PoolForm.py` | `models/PoolForm.py` | ✅ Migrated |
| `models/PoolDesignForm.py` | `models/PoolDesignForm.py` | ✅ Migrated |
| `models/ProjectForm.py` | `models/ProjectForm.py` | ✅ Migrated |
| `models/ProtocolForm.py` | `models/ProtocolForm.py` | ✅ Migrated |
| `models/SampleForm.py` | `models/SampleForm.py` | ✅ Migrated |
| `models/SeqRequestForm.py` | `models/SeqRequestForm.py` | ✅ Migrated |
| `models/UserForm.py` | `models/UserForm.py` | ✅ Migrated |
| `models/TODOCommentForm.py` | `models/TODOCommentForm.py` | ✅ Migrated |
| `models/APIToken.py` | `auth/APITokenForm.py` | ✅ Migrated |
| `models/FeatureKitForm.py` | `models/FeatureKitForm.py` | ✅ Migrated |
| `models/FlowCellDesignForm.py` | `models/FlowCellDesignForm.py` | ✅ Migrated |
| `models/IndexKitForm.py` | `models/IndexKitForm.py` | ✅ Migrated |
| `models/KitForm.py` | `models/KitForm.py` | ✅ Migrated |
| `models/PlateForm.py` | `models/PlateForm.py` | ✅ Migrated |
| `models/SeqRunForm.py` | `models/SeqRunForm.py` | ✅ Migrated |
| `models/SequencerForm.py` | `models/SequencerForm.py` | ✅ Migrated |

---

## 6. Summary

| Category | Count |
|----------|-------|
| ✅ Fully migrated workflows | 4 |
| 🔶 Shell-only workflows (forms not migrated) | 10 |
| ✅ Migrated actions | 34 |
| ❌ Legacy workflows → should be actions | 1 (4 forms) |
| ✅ Legacy top-level forms migrated | 7 |
| ✅ Auth forms migrated | 5 |
| ✅ Comment forms migrated (combined into one) | 4 |
| ✅ File forms migrated (combined into one) | 4 |
| ✅ Model forms migrated | 19 |

### Priority Order (Recommended)
1. **Shell-only workflows with missing forms** — These have the workflow infrastructure ready; just need form implementations
2. **edit_kit_barcodes** — Single-step, should be actions