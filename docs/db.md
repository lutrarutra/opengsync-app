# API Documentation

The following functions allow you to query and retrieve various datasets from your database. Each function is designed to return a `pandas.DataFrame` based on the query and parameters provided. The main focus is to extract and structure data from various models related to experiments, libraries, pools, and more.

## Table of Contents

1. [get_experiment_libraries_df](#get_experiment_libraries_df)
2. [get_experiment_barcodes_df](#get_experiment_barcodes_df)
3. [get_experiment_pools_df](#get_experiment_pools_df)
4. [get_plate_df](#get_plate_df)
5. [get_experiment_lanes_df](#get_experiment_lanes_df)
6. [get_experiment_laned_pools_df](#get_experiment_laned_pools_df)
7. [get_pool_libraries_df](#get_pool_libraries_df)
8. [get_seq_requestor_df](#get_seq_requestor_df)
9. [get_seq_request_share_emails_df](#get_seq_request_share_emails_df)
10. [get_library_features_df](#get_library_features_df)
11. [get_library_samples_df](#get_library_samples_df)
12. [get_seq_request_libraries_df](#get_seq_request_libraries_df)
13. [get_seq_request_samples_df](#get_seq_request_samples_df)
14. [get_experiment_seq_qualities_df](#get_experiment_seq_qualities_df)
15. [get_index_kit_barcodes_df](#get_index_kit_barcodes_df)
16. [get_feature_kit_features_df](#get_feature_kit_features_df)
17. [get_seq_request_features_df](#get_seq_request_features_df)
18. [get_sample_attributes_df](#get_sample_attributes_df)
19. [get_project_samples_df](#get_project_samples_df)
20. [get_lab_prep_libraries_df](#get_lab_prep_libraries_df)
21. [get_lab_prep_samples_df](#get_lab_prep_samples_df)
22. [query_barcode_sequences_df](#query_barcode_sequences_df)

---

### `get_experiment_libraries_df`

```python
get_experiment_libraries_df(
    self, experiment_id: int, 
    include_sample: bool = False, include_index_kit: bool = False,
    include_visium: bool = False, include_seq_request: bool = False,
    collapse_lanes: bool = False, include_indices: bool = True,
    drop_empty_columns: bool = True, collapse_indicies: bool = True
) -> pd.DataFrame
```

Retrieve a DataFrame of experiment libraries with optional details.

- **Parameters**:
  - `experiment_id`: ID of the experiment.
  - `include_sample`: Include sample information.
  - `include_index_kit`: Include index kit details.
  - `include_visium`: Include visium annotation details.
  - `include_seq_request`: Include sequencing request details.
  - `collapse_lanes`: Collapse lane details into lists.
  - `include_indices`: Include library indices.
  - `drop_empty_columns`: Drop columns with all null values.
  - `collapse_indicies`: Collapse indices into lists for i7 and i5.

- **Returns**: A `DataFrame` with experiment library details.

---

### `get_experiment_barcodes_df`

```python
get_experiment_barcodes_df(self, experiment_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of barcodes associated with a specific experiment.

- **Parameters**:
  - `experiment_id`: ID of the experiment.

- **Returns**: A `DataFrame` with experiment barcode details.

---

### `get_experiment_pools_df`

```python
get_experiment_pools_df(self, experiment_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of pools associated with a specific experiment.

- **Parameters**:
  - `experiment_id`: ID of the experiment.

- **Returns**: A `DataFrame` with experiment pool details.

---

### `get_plate_df`

```python
get_plate_df(self, plate_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of details for a specific plate.

- **Parameters**:
  - `plate_id`: ID of the plate.

- **Returns**: A `DataFrame` with plate details including samples and libraries.

---

### `get_experiment_lanes_df`

```python
get_experiment_lanes_df(self, experiment_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of lanes associated with a specific experiment.

- **Parameters**:
  - `experiment_id`: ID of the experiment.

- **Returns**: A `DataFrame` with lane details.

---

### `get_experiment_laned_pools_df`

```python
get_experiment_laned_pools_df(self, experiment_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of laned pools associated with a specific experiment.

- **Parameters**:
  - `experiment_id`: ID of the experiment.

- **Returns**: A `DataFrame` with laned pool details.

---

### `get_pool_libraries_df`

```python
get_pool_libraries_df(self, pool_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of libraries associated with a specific pool.

- **Parameters**:
  - `pool_id`: ID of the pool.

- **Returns**: A `DataFrame` with pool library details.

---

### `get_seq_requestor_df`

```python
get_seq_requestor_df(self, seq_request: int) -> pd.DataFrame
```

Retrieve a DataFrame of sequence requestor details.

- **Parameters**:
  - `seq_request`: ID of the sequencing request.

- **Returns**: A `DataFrame` with sequence requestor information.

---

### `get_seq_request_share_emails_df`

```python
get_seq_request_share_emails_df(self, seq_request: int) -> pd.DataFrame
```

Retrieve a DataFrame of shareable emails for a sequence request.

- **Parameters**:
  - `seq_request`: ID of the sequencing request.

- **Returns**: A `DataFrame` with email share information.

---

### `get_library_features_df`

```python
get_library_features_df(self, library_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of features associated with a specific library.

- **Parameters**:
  - `library_id`: ID of the library.

- **Returns**: A `DataFrame` with library feature details.

---

### `get_library_samples_df`

```python
get_library_samples_df(self, library_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of samples associated with a specific library.

- **Parameters**:
  - `library_id`: ID of the library.

- **Returns**: A `DataFrame` with library sample details.

---

### `get_seq_request_libraries_df`

```python
get_seq_request_libraries_df(
    self, seq_request_id: int, 
    include_indices: bool = False, collapse_indicies: bool = False
) -> pd.DataFrame
```

Retrieve a DataFrame of libraries associated with a specific sequencing request.

- **Parameters**:
  - `seq_request_id`: ID of the sequencing request.
  - `include_indices`: Include library indices.
  - `collapse_indicies`: Collapse indices into lists for i7 and i5.

- **Returns**: A `DataFrame` with sequencing request library details.

---

### `get_seq_request_samples_df`

```python
get_seq_request_samples_df(self, seq_request_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of samples associated with a specific sequencing request.

- **Parameters**:
  - `seq_request_id`: ID of the sequencing request.

- **Returns**: A `DataFrame` with sequencing request sample details.

---

### `get_experiment_seq_qualities_df`

```python
get_experiment_seq_qualities_df(self, experiment_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of sequencing qualities for a specific experiment.

- **Parameters**:
  - `experiment_id`: ID of the experiment.

- **Returns**: A `DataFrame` with sequencing quality details.

---

### `get_index_kit_barcodes_df`

```python
get_index_kit_barcodes_df(self, index_kit_id: int, per_adapter: bool = True) -> pd.DataFrame
```

Retrieve a DataFrame of barcodes within an index kit.

- **Parameters**:
  - `index_kit_id`: ID of the index kit.
  - `per_adapter`: Group by adapters if `True`.

- **Returns**: A `DataFrame` with index kit barcode details.

---

### `get_feature_kit_features_df`

```python
get_feature_kit_features_df(self, feature_kit_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of features within a feature kit.

- **Parameters**:
  - `feature_kit_id`: ID of the feature kit.

- **Returns**: A `DataFrame` with feature kit details.

---

### `get_seq_request_features_df`

```python
get_seq_request_features_df(self, seq_request_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of features associated with a specific sequencing request.

- **Parameters**:
  - `seq_request_id`: ID of the sequencing request.

- **Returns**: A `DataFrame` with sequencing request feature details.

---

### `get_sample_attributes_df`

```python
get_sample_attributes_df(self, sample_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of attributes associated with a specific sample.

- **Parameters**:
  - `sample_id`: ID of the sample.

- **Returns**: A `DataFrame` with sample attributes.

---

### `get_project_samples_df`

```python
get_project_samples_df(self, project_id: int, pivot: bool = True) -> pd.DataFrame
```

Retrieve a DataFrame of sample attributes within a project.

- **Parameters**:
  - `project_id`: ID of the project.
  - `pivot`: Pivot the DataFrame for attributes.

- **Returns**: A `DataFrame` with project sample attributes.

---

### `get_lab_prep_libraries_df`

```python
get_lab_prep_libraries_df(self, lab_prep_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of libraries prepared in a specific lab prep.

- **Parameters**:
  - `lab_prep_id`: ID of the lab preparation.

- **Returns**: A `DataFrame` with lab prep library details.

---

### `get_lab_prep_samples_df`

```python
get_lab_prep_samples_df(self, lab_prep_id: int) -> pd.DataFrame
```

Retrieve a DataFrame of samples prepared in a specific lab prep.

- **Parameters**:
  - `lab_prep_id`: ID of the lab preparation.

- **Returns**: A `DataFrame` with lab prep sample details.

---

### `query_barcode_sequences_df`

```python
query_barcode_sequences_df(self, sequence: str, limit: int = 10) -> pd.DataFrame
```

Find similar barcode sequences in the database based on the provided sequence.

- **Parameters**:
  - `sequence`: The sequence to search for.
  - `limit`: Maximum number of results to return.

- **Returns**: A `DataFrame` with the most similar barcode sequences sorted by similarity.