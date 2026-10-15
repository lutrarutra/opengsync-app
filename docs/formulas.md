# Lab Formulas

The calculations behind molarity, dilutions, lane pooling, flow-cell loading and pool merging: what is computed, from which values, where in the code, and what is saved.

Most calculations are done twice. The **backend** (Python/SQL) computes the values that are saved or exported. The **browser** (JS in the templates) recomputes the same formulas live while you type. The browser values are only a preview and are shown rounded. Exceptions are marked *browser only*: their result is used as shown.

- [Units](#units)
- [Molarity](#molarity)
- [Lane values](#lane-values)
- [Pool dilution](#pool-dilution)
- [Lane pooling](#lane-pooling)
- [Reads per lane](#reads-per-lane)
- [Flow-cell loading](#flow-cell-loading)
- [Merging pools](#merging-pools)
- [Average fragment size from a BioAnalyzer report](#average-fragment-size-from-a-bioanalyzer-report)
- [Read statistics](#read-statistics)
- [Known limitations](#known-limitations)

## Units

| Quantity | Unit | Measured with |
|---|---|---|
| Concentration (`qubit_concentration`) | ng/µL | Qubit (dsDNA) |
| Average fragment size (`avg_fragment_size`) | bp | BioAnalyzer / TapeStation |
| Molarity | nM | computed |
| Volumes | µL | |
| Reads | M reads (10⁶) | |

## Molarity

Converts a mass concentration into a molar one, as described by [Illumina](https://knowledge.illumina.com/library-preparation/dna-library-prep/library-preparation-dna-library-prep-reference_material-list/000001240):

```
molarity [nM] = concentration [ng/µL] × 10⁶ / (660 [g/mol per bp] × average fragment size [bp])
```

660 g/mol is the average mass of one base pair of double-stranded DNA. Example: 2 ng/µL at 400 bp is 2 × 10⁶ / (660 × 400) = **7.58 nM**.

The molarity is unknown (`None`/`NULL`) when the concentration is missing or the size is missing or 0.

| Object | Property | Code |
|---|---|---|
| Library | `Library.molarity` | [Library.py](../packages/opengsync-db/opengsync_db/models/Library.py) |
| Pool | `Pool.molarity` (also as SQL) | [Pool.py](../packages/opengsync-db/opengsync_db/models/Pool.py) |
| Pool dilution | `PoolDilution.molarity(pool)`, using the dilution's concentration and the **pool's** size | [PoolDilution.py](../packages/opengsync-db/opengsync_db/models/PoolDilution.py) |
| Lane | see [Lane values](#lane-values) | [Lane.py](../packages/opengsync-db/opengsync_db/models/Lane.py) |

**Colour thresholds** (pools and lanes):

| Colour | Molarity |
|---|---|
| green | 1 – 5 nM |
| yellow | 0.5 – 1 nM or 5 – 10 nM |
| red | below 0.5 nM or above 10 nM |

## Lane values

A lane has two concentrations:

- **Original** (`original_qubit_concentration`): the lane pool measured in lane QC. Lane QC saves this value, and it is the one prefilled when lane QC is opened again.
- **Sequencing** (`sequencing_qubit_concentration`): measured after diluting for loading, entered at flow-cell loading.

If a lane has no size or original concentration of its own and holds exactly **one** pool, it uses that pool's values.

| Property | Formula |
|---|---|
| `original_molarity`, `lane_molarity` | molarity from the original concentration (the same value) |
| `sequencing_molarity` | molarity from the sequencing concentration |
| `molarity` | `sequencing_molarity` if a sequencing concentration was measured, else `original_molarity` |

The library volume at flow-cell loading always uses `original_molarity`. Measuring the diluted concentration does not change it.

## Pool dilution

*Action:* Experiment → Dilute Pools ([DilutePoolsAction.py](../services/backend/server/forms/actions/DilutePoolsAction.py), [dilute-pools.html](../services/backend/templates/actions/dilute-pools.html))

For each pool, the volumes to dilute it to a target molarity (C₁V₁ = C₂V₂). These are *browser only* and not saved:

```
sample volume [µL] = target molarity / pool molarity × target volume
EB volume [µL]     = target volume − sample volume
```

Defaults are 3 nM and 50 µL. You then measure the concentration after dilution. **Only that concentration is saved**, as a new dilution (A, B, C, …). The browser shows its molarity using the pool's size.

## Lane pooling

*Actions:* Experiment → Lane Pools, Separate or Combined ([lane_pools/](../services/backend/server/forms/actions/lane_pools/), [lane-pools-separate.html](../services/backend/templates/actions/lane-pools-separate.html), [lane-pools-combined.html](../services/backend/templates/actions/lane-pools-combined.html))

Mixes the pools of a lane so that each pool gets its share of the reads. Each pool's molar amount must be proportional to its reads, because clusters form per molecule, not per mass. The pool molarity comes from the chosen dilution, or from the pool itself (`Orig.`).

```
share       = reads of the pool / reads of all pools on the lane
pipet [µL]  = target molarity / pool molarity × share × target total volume
library volume = Σ pipet
EB volume      = target total volume − library volume
```

Defaults are 3 nM and 50 µL. The pool molarity is the chosen dilution's molarity, or the pool's own. Submitting saves the reads, the chosen dilution, the target molarity and the target volume per lane. It also saves a **lane pooling table** (TSV) with every value above, attached to the experiment. This table holds the precise values to pipet.

**Combined lanes:** all lanes get the same mix. The reads entered are the total over all lanes, and each lane stores reads / number of lanes. Shares are the same as for one lane.

## Reads per lane

*Code:* `add_pool_to_lane` and `remove_pool_from_lane` in [actions.py](../packages/opengsync-db/opengsync_db/core/actions.py)

When a pool is put on lanes, the reads requested for the pool are split evenly:

- **Combined lanes:** reads per lane = requested reads / number of lanes of the flow cell.
- **Separate lanes:** reads per lane = requested reads / number of lanes the pool is on. This is recomputed for all of the pool's lanes when a lane is added or removed.

You can change the split afterwards with Distribute Reads or in lane pooling.

## Flow-cell loading

*Actions:* Experiment → Load Flow Cell, Separate or Combined ([load_flowcell/](../services/backend/server/forms/actions/load_flowcell/), [load-flow-cell-separate.html](../services/backend/templates/actions/load-flow-cell-separate.html), [load-flow-cell-combined.html](../services/backend/templates/actions/load-flow-cell-combined.html))

Dilutes the lane pool to the loading molarity (C₁V₁ = C₂V₂):

```
library volume [µL] = total volume × target molarity / lane original molarity
EB volume [µL]      = total volume − library volume
```

The total volume defaults to the workflow's `volume_target_ul`. The backend saves `library_volume_ul`, together with the target molarity, total volume, PhiX % and the sequencing concentration. The experiment becomes LOADED when every lane is loaded. With combined lanes, that means a library volume could be computed for every lane. With separate lanes, every lane also needs QC values, the sequencing concentration and PhiX.

The concentration measured after dilution is shown as *sequencing molarity*, as a check against the target.

## Merging pools

*Workflow:* Merge Pools ([MergePoolsForm.py](../services/backend/server/forms/workflows/merge_pools/MergePoolsForm.py), [merge-pools.html](../services/backend/templates/workflows/merge_pools/merge-pools.html))

This is *browser only*: the pipet volumes are computed in the browser and saved as entered (`Pool.merge_ratios`). Each pool's volume is set so that its molar amount is proportional to its requested reads, and the volumes add up to the total volume:

```
share  = requested reads of the pool / requested reads of all pools
ratio  = share × highest pool molarity / pool molarity
pipet [µL] = ratio / Σ ratio × total volume
```

There is no buffer: the merged pool is more dilute than the most concentrated input. The merged pool gets no concentration or size, so measure it again.

## Average fragment size from a BioAnalyzer report

*Workflow:* BA Report ([ba_report/](../services/backend/server/forms/workflows/ba_report/))

From the BioAnalyzer CSV export, the value **"Average Size [bp]"** of the sample's **Region Table** is used. A size of 0 or below counts as unknown, and decimals are cut off (412.7 → 412). The size can also be entered by hand. A value must be ≥ 1, because molarity divides by it.

## Read statistics

| Value | Formula | Code |
|---|---|---|
| Read share per lane (plots) | reads of the library or pool on the lane / all reads on the lane | [plots.py](../services/backend/server/routes/htmx/plots.py) |
| Sequenced vs planned (pool) | sequenced reads / Σ planned reads over the pool's lanes × 100 % | `pool_num_reads_stats` in [pd_transforms.py](../packages/opengsync-db/opengsync_db/core/blueprints/pd_transforms.py) |
| Overview progress bar | sequenced reads / requested reads; marked low below 80 % | [overview-graph.js](../services/backend/static/js/overview-graph.js) |

## Known limitations

- **Rounding in the browser.** The dilution and flow-cell previews read the molarity from the rounded value shown (2 decimals). This is up to about 0.5 % off at normal molarities. Dilution volumes are only computed in the browser.
- **No warning for impossible volumes.** If a pool or lane is weaker than the target, the pipet or library volume is larger than the total volume, and the EB volume becomes negative. It is shown, but not rejected.
- **Merging pools with a pool of unknown molarity.** That pool keeps its default 20 µL and is not part of the scaling, so the volumes don't add up to the total.
- **Only the first BA region is read.** If the report has several regions (e.g. adapter dimers and the library), only the first row of the Region Table is used.
- **Lane sequencing molarity in tables.** In SQL (tables, sorting), `sequencing_molarity` and `molarity` use only the lane's own size, without the single-pool fallback.
- **PhiX** is recorded but not part of any volume.
- **Mass-based quantification.** Qubit plus average size gives the molarity of all DNA. qPCR measures only clusterable molecules and is more accurate for overamplified libraries or adapter dimers.
