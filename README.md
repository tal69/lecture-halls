# Quadratic Lecture Hall Assignment

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21294644.svg)](https://doi.org/10.5281/zenodo.21294644)

This repository provides an exact optimization framework for the **Quadratic Lecture-Hall Assignment Problem (QLHAP)**, focused on minimizing student walking distances in university settings. By transforming real-world timetabling and registration data into optimal daily hall assignments, the project bridges the gap between theoretical Quadratic Assignment Problems (QAP) and operational campus scheduling. The revised paper reports the Gurobi MIQP and compact MIP formulations and evaluates problem-specific biclique and capacity-dominance inequalities. The repository also retains two documented revision-stage exploratory tests: an OR-Tools CP-SAT formulation and light compatibility preprocessing. Neither is used in the revised paper tables.

## Release and Data Links

- [GitHub release `v1.0.3`](https://github.com/tal69/lecture-halls/releases/tag/v1.0.3)
- [Exact `v1.0.3` archive on Zenodo](https://doi.org/10.5281/zenodo.21310605)
- [All archived versions on Zenodo](https://doi.org/10.5281/zenodo.21294644) (concept DOI)
- [Official ITC 2019 website and source instances](https://www.itc2019.org/)
- [Lancaster 2023 dataset](https://doi.org/10.17635/lancaster/researchdata/279) (CC BY)
- [Third-party data sources, rights, and reconstruction instructions](THIRD_PARTY_DATA.md)
- [Source-file checksum manifests](data_manifests/)
- [MIT software license](LICENSE) and [citation metadata](CITATION.cff)

The realistic-data pipeline currently supports:
- the ITC 2019 university course timetabling benchmark XML files,
- the Lancaster 2023 institutional timetable and anonymized registration data,
- preservation of the original hall set, capacities, and hall-to-hall distances,
- reconstruction of student-flow successor pairs from timetable and registration records,
- import or propagation of hall-assignment penalties,
- and propagation of the additional side constraints discussed in Section 3.4, in particular hard and soft `SameRoom` and `SameAttendees`.

The optimization models minimize:
- the walking burden induced by consecutive lectures that share students,
- linear hall-assignment penalties,
- and, when present in the source data, penalties for soft `SameRoom` and soft `SameAttendees` violations.

The current workflow includes:
- realistic-data preparation for ITC 2019, including peak-week selection, weekday extraction, short-break inference, student-flow construction, hall-penalty import, and side-constraint extraction,
- realistic-data preparation for Lancaster 2023, including `SameClass` contraction, peak-week selection by term, registration repair, and side-constraint projection,
- optional capacity-dominance constraints and exploratory light compatibility preprocessing,
- solver backends:
  - GUROBI bilinear `MIPQ`,
  - GUROBI linearized `MIP`,
  - OR-Tools `CP`,
- a `ROOT` mode for reporting the root-node bound of the linearized GUROBI model,
- and a synthetic single-day instance generator for controlled experiments and stress tests. These synthetic instances are not used in the numerical experiments reported in the paper.

In the revised manuscript, the exact-method tables use only 1800-second `MIPQ`
and `MIP` rows with `compatibility_preprocess_mode = none`; the root diagnostic
similarly uses only `ROOT` rows with that setting. The `CP` rows and all rows
with `compatibility_preprocess_mode = light` remain available for transparency
and exploratory comparison but are not part of the reported experiment.

The script also supports an `--instance-only` path that skips solving, prints the optimization input in a readable terminal layout, and saves the same instance in JSON.

## Requirements

Python `3.9+` with:
- `pandas`
- `numpy`
- `openpyxl`
- `gurobipy`
- `ortools`

Install the Python packages with:

```bash
pip install pandas numpy openpyxl gurobipy ortools
```

`gurobipy` requires a valid Gurobi license for the `MIPQ`, `MIP`, and `ROOT` runs.

For a clean reproducible environment, create and activate a virtual environment
before installing the requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The reported campaign used Python 3.10.16 and Gurobi 13.0 on Ubuntu 22.04, on
an AMD Ryzen 9 5950X with 128 GB of RAM and 12 solver threads per run. The
numerical results depend on the solver versions, CPU, thread count, and license
configuration available to Gurobi and OR-Tools. The scripts record the Python
version, platform, host name, time limit, solver family, and runtime metadata in
the output workbooks, but exact wall-clock times can still vary across
machines. Objective values, lower bounds, and optimality gaps are the primary
reproducibility targets.

## Reproducing the Paper Results

### Repository Layout

The paper workflow uses the following files and directories:

- `lecture_hall_experiment.py`: main experiment runner.
- `run_revision_1800.sh`: final shell entry point for reproducing the numerical results, using a 1800-second solver limit per run.
- `run_full_factorial_all.sh`: ITC 2019 exact-solver factorial campaign invoked by `run_revision_1800.sh`.
- `run_full_factorial_lancs.sh`: Lancaster exact-solver factorial campaign invoked by `run_revision_1800.sh`.
- `run_relaxations_factorial.sh`: root-relaxation factorial campaign invoked by `run_revision_1800.sh`.
- `compute_baseline_walking.py`: reconstructs and verifies the status-quo comparison reported in Table 8.
- `Numerical experiment results/`: archived result workbooks used by the manuscript figures and tables.
- `data_manifests/`: checksums identifying the exact third-party source files used.
- `THIRD_PARTY_DATA.md`: source locations, licenses, and redistribution notes.

The `ITC2019/` source-data directory is intentionally not tracked. The code,
checksums, and commands needed to recreate the processed inputs are tracked.

The scripts write new workbooks to the repository root by default. Move or copy
completed workbooks into `Numerical experiment results/` only after confirming
that they are the intended canonical outputs.

### Canonical Result Workbooks

The repository includes six archived `.xlsx` workbooks under
`Numerical experiment results/`. The revised paper is based only on the
1800-second workbooks; the 300-second workbooks are retained for provenance and
for comparing against the original submission.

| Workbook | Rows | Role |
| --- | ---: | --- |
| `full_factorial_1800s.xlsx` | 600 | Final ITC 2019 exact campaign. The paper uses the 200 no-preprocessing `MIPQ`/`MIP` rows; 200 light-preprocessing `MIPQ`/`MIP` rows and 200 `CP` rows are exploratory. |
| `lancs_yr23_full_factorial_1800s.xlsx` | 240 | Final Lancaster 2023 exact campaign. The paper uses the 80 no-preprocessing `MIPQ`/`MIP` rows; 80 light-preprocessing `MIPQ`/`MIP` rows and 80 `CP` rows are exploratory. |
| `relaxations_factorial_1800s.xlsx` | 280 | Final root-node diagnostic campaign. The paper uses the 140 rows with `compatibility_preprocess_mode = none`; the 140 light-preprocessing rows are exploratory. |
| `full_factorial_300s.xlsx` | 600 | Archived ITC 2019 300-second exact campaign from the original computational study. Not used for revised-paper results. |
| `lancs_yr23_full_factorial_300s.xlsx` | 240 | Archived Lancaster 2023 300-second exact campaign from the original computational study. Not used for revised-paper results. |
| `relaxations_factorial_300s.xlsx` | 280 | Archived 300-second root-node diagnostic campaign. Not used for revised-paper results. |

The two final exact workbooks therefore contain 840 rows: 280 no-preprocessing
`MIPQ`/`MIP` rows used by the revised manuscript, 280 light-preprocessing
`MIPQ`/`MIP` rows retained as an exploratory test, and 280 `CP` rows retained to
document the CP-SAT attempt. The final root workbook contains 140 reported
no-preprocessing `ROOT` rows and 140 exploratory light-preprocessing rows.

### Input Data and Rights

The code is released under the MIT License, but that license does not apply to
third-party input data. See `THIRD_PARTY_DATA.md` for the full source and rights
statement.

The paper uses five public ITC 2019 instances: `pu-proj-fal19`, `agh-fal17`,
`muni-pdfx-fal17`, `pu-d9-fal19`, and `muni-pdf-spr16c`. Download each source
XML and its published solution XML from the [official ITC 2019
website](https://www.itc2019.org/), then place them at:

```text
ITC2019/<instance>.xml
ITC2019/solution/<instance>.xml
```

The ITC site makes the competition files publicly available, but no explicit
redistribution license was located. To avoid assigning an MIT license to
third-party material, neither the source XML nor the derived day-level JSON is
mirrored in this repository. The checksum manifest identifies the exact files:

```bash
shasum -a 256 -c data_manifests/itc2019_paper_inputs.sha256
```

After the ten ITC files are in place, regenerate the 25 processed weekday
instances used by the paper with:

```bash
mkdir -p prepared_itc2019
PYTHON_BIN="${PYTHON_BIN:-python}"
for instance in pu-proj-fal19 agh-fal17 muni-pdfx-fal17 pu-d9-fal19 muni-pdf-spr16c; do
  "$PYTHON_BIN" lecture_hall_experiment.py \
    --source itc2019 \
    --itc-instance "$instance" \
    --instance-only \
    --output "prepared_itc2019/${instance}.xlsx" \
    --quiet
done
```

`--instance-only` performs no optimization and writes one machine-readable JSON
file for each selected weekday. Filenames contain a generation timestamp, but
the optimization-instance content is deterministic for fixed source files and
arguments.

The Lancaster 2023 source is openly available under a CC BY license from
[Lancaster University](https://doi.org/10.17635/lancaster/researchdata/279).
Download the canonical `lancs-yr23.xml` file and place it at:

```text
ITC2019/lancs-yr23.xml
```

The file is approximately 154 MB and is not duplicated in this repository. If
it is missing, the ITC and synthetic workflows remain available but the
Lancaster campaign cannot be reproduced.

Verify the Lancaster download separately with:

```bash
shasum -a 256 -c data_manifests/lancaster2023.sha256
```

### Quick Smoke Test

Before launching a long campaign, run one small deterministic case:

```bash
python lecture_hall_experiment.py \
    --source itc2019 \
    --itc-instance muni-pdf-spr16c \
    --itc-day 0 \
    --model MIP \
    --biclique \
    --time-limit 60 \
    --output smoke_test.xlsx \
    --quiet
```

This should create `smoke_test.xlsx` with one row on the `summary` sheet. Remove
the file before repeating the smoke test if you want a clean workbook.

### Full 1800-Second Paper Campaign

The final numerical results are reproduced by the shell wrapper
`run_revision_1800.sh`. It is the recommended entry point for reproducing the
paper's computational campaign:

```bash
./run_revision_1800.sh
```

By default, the script sets `TIME_LIMIT=1800`, so every solver call receives a
1800-second time budget. The wrapper runs three stages sequentially:

```text
1. bash run_full_factorial_all.sh 1800
2. bash run_full_factorial_lancs.sh 1800
3. bash run_relaxations_factorial.sh 1800
```

The stages are:
- `run_full_factorial_all.sh`: exact-solver factorial campaign on the five selected ITC 2019 instances, with five weekdays per instance.
- `run_full_factorial_lancs.sh`: exact-solver factorial campaign on the ten Lancaster day-level instances, covering five weekdays in each of two selected terms.
- `run_relaxations_factorial.sh`: root-relaxation campaign over the same 35 day-level instances.

Expected output files:

```text
full_factorial_1800s.xlsx
lancs_yr23_full_factorial_1800s.xlsx
relaxations_factorial_1800s.xlsx
```

The exact-solver stages call `lecture_hall_experiment.py` without `--model`, so
they run all three implemented exact backends: `MIPQ`, `MIP`, and `CP`. The
factorial scripts also run both `none` and `light` compatibility-preprocessing
modes. This intentional superset preserves the exploratory tests. The table
generator filters the exact workbooks to the 280 `MIPQ`/`MIP` rows with
`compatibility_preprocess_mode = none` and the root workbook to the corresponding
140 `ROOT` rows. The remaining 280 light-preprocessing `MIPQ`/`MIP` rows, 140
light-preprocessing `ROOT` rows, and 280 `CP` rows are not used in the paper.

The script also creates a timestamped log directory:

```text
logs_revision_1800s_YYYYMMDD_HHMMSS/
```

Each stage writes its own log file inside that directory. The wrapper uses
`set -e`, so a failed stage aborts the remaining campaign while preserving any
completed workbook and log files. The child scripts refuse to overwrite existing
workbooks unless `OVERWRITE=1` is set:

```bash
OVERWRITE=1 ./run_revision_1800.sh
```

The shell scripts use `python` by default. To force a particular interpreter,
for example the virtual environment created above, set `PYTHON_BIN`:

```bash
PYTHON_BIN=.venv/bin/python ./run_revision_1800.sh
```

To run the same wrapper with a different time budget, set `TIME_LIMIT`:

```bash
TIME_LIMIT=3600 ./run_revision_1800.sh
```

After verifying the generated workbooks, copy the intended canonical versions
into `Numerical experiment results/` before regenerating the paper figures and
tables.

### Reproducing the Revised Section 4 Tables

The revised manuscript's numerical tables can be regenerated directly from the
canonical 1800-second workbooks with:

```bash
python generate_paper_tables.py
```

To save CSV copies of the reproduced tables:

```bash
python generate_paper_tables.py --output-dir generated_paper_tables
```

The script reads:

```text
Numerical experiment results/full_factorial_1800s.xlsx
Numerical experiment results/lancs_yr23_full_factorial_1800s.xlsx
Numerical experiment results/relaxations_factorial_1800s.xlsx
```

It outputs:

- `results_overview`: the formulation-family summary table.
- `best_methods`: the three fastest available exact methods and their times by daily instance, with `-` for unavailable second or third qualifying methods.
- `method_summary`: the 8-row no-preprocessing MIQP/MIP method-combination table.
- `root_diagnostics`: the root-node diagnostic summary for biclique vs no biclique.
- `preprocessing_attempt_summary`: an audit of the exploratory light-preprocessing rows.
- `cp_attempt_summary`: a compact check of the retained CP-SAT rows.

The reported method-time columns use `wall_clock_seconds` from the
no-preprocessing rows. This field includes cut generation, model construction,
and the solver call. For the separate preprocessing audit, the generator adds
`compatibility_preprocess_wall_seconds` to `wall_clock_seconds` so that the
exploratory comparison charges the complete preprocessing cost. Both raw timing
components remain in the workbooks.

### Reproducing the Value-of-Optimization Comparison (Table 8)

The status-quo comparison in Subsubsection 4.2.4 (Table 8) is reproduced with:

```bash
python compute_baseline_walking.py
```

The script rebuilds all 35 daily instances from the source data through the
same loaders used by the experiment (`load_itc2019_day_instances` and
`load_lancs_yr23_term_instances`), so it requires the ITC 2019 and Lancaster
inputs to be reconstructed locally (see the third-party data notes below). For
each instance it evaluates the model-implied walking burden of the status-quo
hall assignment, that is, the hall each lecture uses in the source data
(`Lecture.hidden_hall`: the published ITC competition room and the deployed
Lancaster institutional room). Student-flow weights are reconstructed by the
same documented loaders used in the paper; they are not observed pedestrian
trajectories. The script compares the baseline with the smallest walking
component observed among no-preprocessing 1800-second MIQP/MIP runs that attain
the best full objective. It also reports the largest observed component among
those runs and the resulting percentage-point spread.

Before computing the comparison, the script checks all 35 rebuilt instances
against the solved workbooks on lecture count, hall count, total
shared-enrollment weight, and the numbers of hard `SameRoom` and
`SameAttendees` pairs. It then verifies that the status-quo assignment is
feasible for the complete hard model: all recorded halls are compatible, no
hall contains overlapping lectures, and all hard `SameRoom` and
`SameAttendees` constraints are satisfied. A per-instance CSV is written to
`tmp/baseline_value_of_optimization.csv`; the script creates this directory if
it does not already exist.

Subsubsection 4.2.4 and Table 8 of the paper report this comparison on the ten
**Lancaster** daily instances only, because their status-quo assignment is the
room plan the institution actually deployed (a genuine operational baseline),
whereas the ITC fixed schedules are winning competition solutions optimizing
the contest objective rather than deployed room plans. On the ten Lancaster
days the selected best-objective runs reduce model-implied walking by 20.5% to
45.3% (mean 31.9%, aggregate 32.7%). Selecting the largest rather than the
smallest observed walking component among best-objective runs changes each
Lancaster percentage by at most 0.31 percentage points. The script also prints
and stores the analogous ITC figures for transparency (aggregate 15.7%; pooled
19.6% over all 35 days).

For each instance the script additionally reports the **per-pair distance
floor**, `sum over active successor pairs of c * min compatible hall-to-hall
distance`, a valid lower bound on the walking cost of any feasible assignment
(each pair independently attains at least its closest compatible hall pair; a
pair whose two lectures share a compatible hall contributes zero because both
can occupy the same hall). This floor is a useful diagnostic for the ITC days
that show little or no reduction: the four lightly loaded `muni-pdf` days
(`w3d1`--`w3d4`) have selected optimized walking equal to the floor and a
status-quo assignment that already attains it, so no reassignment can improve
their walking burden; the script reports four of 35 instances at this floor.
None of the ten Lancaster days is at the floor, and all ten independently show
a positive baseline reduction. The floor condition explains the four
zero-reduction ITC days but, by itself, failure to attain the floor would not
prove that a baseline can be improved. The `walking_floor`, `at_floor`, and
`observed_best_objective_walk_spread_pp` columns are included in the exported
CSV. The floor pass adds a few seconds because it scans compatible hall pairs
on the largest instances; the whole script completes in well under a minute.

### Archived 300-Second Campaign

The earlier 300-second workbooks in `Numerical experiment results/` can be
reproduced by the three commands below. They produce the same row structure as
the 1800-second campaign: 840 exact runs (`MIPQ`, `MIP`, and `CP`) and 280
root-relaxation runs, for 1120 rows total. These commands document the archived
300-second campaign from the original computational study; the revised paper's
tables and root-gap diagnostic use only the 1800-second workbooks above.

```bash
./run_full_factorial_all.sh 300
./run_full_factorial_lancs.sh 300
./run_relaxations_factorial.sh 300
```

Expected output files:

```text
full_factorial_300s.xlsx
lancs_yr23_full_factorial_300s.xlsx
relaxations_factorial_300s.xlsx
```

The runner scripts refuse to overwrite an existing workbook. To intentionally
rerun from scratch:

```bash
OVERWRITE=1 ./run_full_factorial_all.sh 300
OVERWRITE=1 ./run_full_factorial_lancs.sh 300
OVERWRITE=1 ./run_relaxations_factorial.sh 300
```

The shell scripts use `python` by default. To force a specific interpreter,
for example the virtual environment created above, set `PYTHON_BIN`:

```bash
PYTHON_BIN=.venv/bin/python ./run_full_factorial_all.sh 300
```

### Verifying a Reported Data Claim

The cross-course successor-flow share reported in the response letter can be
recomputed with:

```bash
python verify_cross_course_share.py
```

On the checked-in data this reports 35 daily instances, a minimum share of about
75%, a maximum of 100%, and a mean of about 91%.

## Real-World Data Preparation

### ITC 2019

The deterministic ITC preparation pipeline is implemented by
`prepare_itc2019_inputs.py` and called by `lecture_hall_experiment.py`:

1. Parse the official problem XML and the matching published solution XML.
2. Reconstruct the room catalog, capacities, compatibility lists, room
   penalties, and symmetric travel-time matrix.
3. Select the teaching week with the largest number of active room-requiring
   classes unless `--itc-week-index` is supplied.
4. Expand the selected solution into daily lecture records and retain weekdays
   `0-4` unless `--itc-day` selects one day explicitly.
5. Reconstruct each lecture's registered students from the solution and form
   directed successor pairs when the same students attend temporally
   consecutive lectures within the inferred short-break threshold.
6. Apply the documented capacity correction only when the published solution
   places a class in a room smaller than its recorded enrollment.
7. Project hard and soft `SameRoom` and `SameAttendees` constraints onto each
   daily instance and retain the original room-assignment penalties.
8. Build the final hall-assignment instance containing lectures, halls,
   compatibilities, walking distances, successor weights, penalties, overlap
   cliques, and provenance metadata.

The `--instance-only` command above serializes this final optimization input to
JSON without invoking a solver.

### Lancaster 2023

The repository also supports a Lancaster-specific data-transformation path for
the CC BY `lancs-yr23.xml` dataset.
- It merges `SameClass` components into representative activities before any day-level instance is created.
- It identifies the two main teaching terms and selects the peak-load week of each term.
- It keeps weekdays `0-4` by default and discards weekend activity unless a specific source day is requested.
- It greedily repairs student registrations subject to the merged weekly timetable and hidden-hall capacities.
- It propagates the relevant side constraints from the weekly XML data to the resulting day-level hall-assignment instances exposed to `lecture_hall_experiment.py`.

## Synthetic Instance Generation

The synthetic generator is retained for controlled experiments, debugging, and stress testing. The synthetic instances are **not** part of the numerical experiment reported in the paper; the reported computational results use only the ITC 2019 and Lancaster 2023 real-world day-level instances. The generator builds a **single-day** instance because the base weekly problem is separable by day when no cross-day side constraint is imposed.

Lectures:
- have duration `2` to `4` slots,
- are initially distributed across halls to match the requested density in a way that respects hall capacities; this initial assignment is hidden from the solver,
- are assigned balanced `subject` and `study_year` labels,
- are classified as roughly `70%` compulsory and `30%` elective,
- are first assigned by a randomized greedy balancing heuristic,
- and, if that heuristic fails on a dense instance, are completed by an exact CP-SAT fallback that preserves the balanced subject/year totals and enforces the cohort-overlap rule,
- satisfy the timetable rule that for any fixed `(subject, year)` cohort and time slot there is either:
  - at most one compulsory lecture, or
  - at most two elective lectures,
  - but not both.

Students:
- are generated around active `(subject, study_year)` cohorts,
- receive cohort sizes that are anchored to the compulsory offerings of their own cohort,
- attend almost all compulsory lectures of their own topic and year,
- are frequently distributed among their own parallel elective lectures,
- may occasionally take a previous-year lecture in their own topic,
- and only very rarely take lectures from other topics.

Lecture sizes are not sampled directly. They are the realized attendance counts produced by the cohort-based day-schedule simulation. After the student-journey simulation, each lecture size is tightened toward the capacity of its hidden feasible hall so that the hall-capacity constraints remain globally feasible but materially more restrictive.

## Assignment Penalty

The objective now includes a per-assignment penalty that discourages placing a lecture in a hall that is much larger than needed.

For a lecture with `students = s` assigned to a hall with `capacity = u`:
- the penalty is `0` as long as at least `90%` of the hall is filled, equivalently while `s >= ceil(0.9 * u)`;
- otherwise the penalty is quadratic in the excess empty seats beyond that threshold:

```text
penalty(s, u) = max(0, ceil(0.9 * u) - s)^2
```

Examples for a hall of capacity `100`:
- lecture size `90` to `100`: penalty `0`
- lecture size `89`: penalty `1`
- lecture size `80`: penalty `100`

For synthetic instances, this penalty is generated automatically for every compatible class-room pair.

For ITC 2019 and Lancaster 2023 instances, the model instead uses the pre-existing assignment penalties defined in the dataset for each hall-lecture pair.

Determinism note:
- if the original greedy attribute-assignment path succeeds for a given seed, the generated instance is unchanged by the fallback patch;
- the new CP-SAT fallback only affects seeds and parameter combinations for which the old generator would previously have failed with a runtime error.

## Usage

The main entry point is `lecture_hall_experiment.py`. The paper workflow uses the real-world data-preparation modes shown below. If `--source` is omitted, the script falls back to synthetic generation, but those synthetic instances are for development and stress testing only and were not used in the paper's reported numerical experiment.

Example using an ITC 2019 instance with the paper's no-preprocessing setting and
biclique strengthening:

```bash
python lecture_hall_experiment.py \
    --source itc2019 \
    --itc-instance pu-proj-fal19 \
    --biclique \
    --time-limit 120
```

Example using the Lancaster data-preparation path:

```bash
python lecture_hall_experiment.py \
    --source lancs_yr23 \
    --itc-day 1 \
    --instance-only
```

Example with more options for synthetic generation, for development or stress testing only:

```bash
python lecture_hall_experiment.py \
    --num-halls 12 \
    --slots-per-day 12 \
    --density 0.9 \
    --time-limit 120 \
    --seed 1-10 \
    --biclique \
    --save-json
```

Example for generating and exporting the input only:

```bash
python lecture_hall_experiment.py \
    --num-halls 12 \
    --slots-per-day 12 \
    --density 0.9 \
    --seed 1-3 \
    --instance-only
```

### Factorial Experiments

The repository includes several shell scripts to automate the factorial parameter sweeps:
- `run_full_factorial_all.sh`: Runs `MIPQ`, `MIP`, and `CP` with all eight combinations of biclique strengthening, capacity-dominance constraints, and `none`/`light` compatibility preprocessing on 25 ITC 2019 daily instances. The paper uses only the four no-preprocessing configurations of `MIPQ` and `MIP`; the other rows are exploratory.
- `run_full_factorial_lancs.sh`: Runs the same exact-solver sweep on the 10 Lancaster daily instances, comprising five weekdays from the selected peak week of each term. The same paper filter applies.
- `run_relaxations_factorial.sh`: Runs the `ROOT` diagnostic over the same 35 daily instances and all eight enhancement combinations. The paper uses only the four no-preprocessing configurations; the light-preprocessing rows are exploratory.
- `run_revision_1800.sh`: Runs the complete revision campaign with a default 1800-second solver limit and timestamped logs.

The first three scripts accept the running time per instance as a positional
argument. The final wrapper `run_revision_1800.sh` uses `TIME_LIMIT=1800` by
default and can be overridden by setting the `TIME_LIMIT` environment variable.


## Command-Line Arguments

- `--source {synthetic,itc2019,lancs_yr23}`: Input source. Default: `synthetic`.
- `--num-halls` **(required and relevant for synthetic)**: number of halls.
- `--slots-per-day`: number of discrete slots in the day. Default: `12`. Relevant for the synthetic instances only.
- `--seed`: one seed, a closed range such as `1-100`, or a start-step-end pattern such as `1-3-10`. Default: `0`. Relevant for the synthetic instances only.
- `--density`: target lecture-slot utilization (synthetic only), interpreted as total lecture slots divided by total available hall-slots in the day. Default: `0.9`. Relevant for the synthetic instances only.
  - The synthetic generator also enforces the cohort-overlap rules used to create student flows. With the current `8 x 4 = 32` subject-year cohorts, at most `64` lectures can run simultaneously, so very high densities become infeasible once `num_halls > 64`.
- `--itc-instance`: ITC 2019 instance stem, filename, or XML path (required for ITC).
  - Optional for `lancs_yr23`; when omitted it defaults to `ITC2019/lancs-yr23.xml`.
- `--itc-solution`: Optional ITC 2019 solution XML path.
- `--itc-week-index`: Optional 0-based week index for ITC 2019.
  - if omitted, the data-transformation path auto-selects one peak-load week per term.
- `--itc-day`: Optional 0-based source day index for ITC 2019 or `lancs_yr23`.
  - if omitted, the importers keep only weekdays `0-4`.
- `--itc-short-break-slots`: Optional successor gap threshold for ITC 2019 and `lancs_yr23`. Inferred automatically if omitted.
- `--no-capacity-fix`: Disable the default ITC capacity fix that reduces oversized lectures to their assigned hall capacity.
- `--time-limit`: per-solver time limit in seconds. Default: `60`.
- `--biclique`: enable the anchor-based biclique strengthening described in the paper.
  - In `MIP`, this replaces the base pair-distance links by the extended biclique family built from the anchor pair `(h_1,h_2)` and also aggregates `SameAttendees` constraints over the same threshold sets.
  - In `MIPQ`, this adds the direct quadratic analogue of those biclique cuts to the bilinear walking term, and adds the analogous strengthening for soft `SameAttendees` penalties while keeping the soft penalties in the objective.
  - In `CP`, this enables the corresponding redundant propagation layer on the pair-distance variables together with the aggregated `SameAttendees` propagation.
- `--capacity-dom`: enable the capacity-dominance cardinality constraints derived from maximal overlap cliques and hall-capacity thresholds.
  - Disabled by default.
  - Applies to `MIPQ`, `MIP`, `CP`, and `ROOT`.
- `--model`: optional single model to solve.
  - `MIPQ`: bilinear GUROBI formulation.
  - `MIP`: compact linearized GUROBI formulation.
  - `CP`: OR-Tools CP-SAT formulation, retained as a documented attempted backend but excluded from the revised paper tables.
  - `ROOT`: root-node bound of the linearized GUROBI formulation.
  - If omitted, the script solves `MIPQ`, `MIP`, and `CP`.
- `--compatibility-preprocess {none,full,light}`: optional CP-SAT preprocessing that shrinks the compatible set `H(l)` before any solver is built.
  - `none`: disable preprocessing. This is the setting used for every result reported in the revised paper.
  - `light`: run the exploratory local preprocessing method documented below.
  - `full`: retained as a legacy command-line option, but it was not part of the final 1800-second campaign and is not a paper-reproduction target.
- `--instance-only`: generate the instance only, print the input in a user-friendly terminal format, and write JSON export(s). No solver is run and no Excel workbook is written.
- `--output`: Excel output path. Default: `results.xlsx`.
- `-s`, `--save-json`: also write a JSON file with the full instance and all solutions.
  - Not needed with `--instance-only` because JSON export is automatic there.
- `-q`, `--quiet`: suppress solver logs.

## Linearized GUROBI Model

The current `MIP` model uses the **compact** linearization from the paper:
- binary assignment variables `x_(l,h)`,
- one nonnegative continuous pair variable per successor pair.

Implementation note:
- Without `--biclique`, `MIP` uses the base compact pair-distance links from the paper with the original weighted objective.
- With `--biclique`, `MIP` uses the same anchor-based biclique construction as Section 3.3, and the implementation folds the common-student weight into the pair variable for scaling.
- With `--biclique`, `MIPQ` keeps the walking objective bilinear and adds the corresponding quadratic biclique inequalities directly in the assignment variables.

It does **not** use the older four-index linearization with variables `y_(l1,l2,h1,h2)`.

### Biclique pattern generation

The anchor-based biclique construction is the direct implementation of **Algorithm 1** in Section 3.3 of the paper. The routine `distance_extended_biclique_patterns` in `lecture_hall_experiment.py` enumerates, for each successor pair `(l_1, l_2)` and each anchor hall pair `(h_1, h_2) \in H(l_1) \times H(l_2)`, the triple `(S_1, S_2, δ)` with `δ = d(h_1,h_2)`, `S_2 = {h ∈ H(l_2) : d(h_1,h) ≥ δ}`, and `S_1 = {h ∈ H(l_1) : d(h,h'') ≥ δ for every h'' ∈ S_2}`. The returned triples are deduplicated before any cut (or CP propagation) is posted. The same routine is reused by `MIP`, `MIPQ`, and `CP`.

## Exploratory Light Compatibility Preprocessing

Light compatibility preprocessing was one of the exploratory tests performed
during the revision. It remains implemented and its 1800-second result rows are
archived, but it was excluded from the revised paper because its end-to-end
computational benefit was negligible.

For each target lecture `l'`, let `L'(l')` contain `l'` and every lecture whose
time interval overlaps that of `l'`. The light preprocessor builds a local
OR-Tools CP-SAT assignment model on `L'(l')`:

- every local lecture is assigned to exactly one hall in its current compatible
  set;
- lectures active at the same time are assigned to different halls; and
- walking costs and all nonlocal objective terms are omitted.

The local objective maximizes the capacity of the hall assigned to `l'`. Let
`U'(l')` be a valid upper bound returned for this maximum. The preprocessor
removes every hall `h` from `H(l')` for which `u_h > U'(l')`. This removal is
safe: the projection of any globally feasible assignment onto `L'(l')` is
feasible for the relaxed local model, so the capacity globally assignable to
`l'` cannot exceed `U'(l')`. Because the local model omits constraints outside
the overlap neighborhood, it can leave halls that a global analysis could
remove, but it cannot remove a hall needed by a globally feasible solution.

The procedure is applied to every lecture and repeated to a fixed point, with
the reduced compatible sets from one pass used in the next. If a compatible set
becomes empty, the runner reports the instance as infeasible before building the
main optimization model.

To reproduce one light-preprocessing run:

```bash
python lecture_hall_experiment.py \
    --source itc2019 \
    --itc-instance muni-pdf-spr16c \
    --itc-day 0 \
    --model MIP \
    --compatibility-preprocess light \
    --biclique \
    --time-limit 1800 \
    --output exploratory_light_preprocessing.xlsx \
    --quiet
```

Across the 35 real-data instances, the light variant was the fastest
end-to-end configuration on only one instance; a no-preprocessing configuration
was faster on the other 34. Over the archived light-preprocessing `MIPQ`/`MIP`
runs, preprocessing alone took 123.16 seconds on average, 26.56 seconds at the
median, and 1172.41 seconds at the maximum. The archived workbooks contain 280
such exact-solver rows and 140 corresponding `ROOT` rows. These rows document
the exploratory test and are not used in any table or numerical claim in the
revised paper.

## Outputs

### Excel workbook

The Excel file contains a single `summary` sheet. Repeated runs append new rows rather than overwriting prior results. The summary includes:
- experiment timestamps,
- seed and instance demographics,
- density and size statistics,
- realized successor-set statistics,
- compatibility-preprocessing statistics,
- solver status,
- objective value,
- objective components:
  - total student walking distance,
  - assignment mapping penalty,
  - soft same-hall and same-attendees penalties,
- lower bound,
- best global lower bound across solved methods for that instance,
- optimality gap and global optimality gap,
- runtime information (including detailed wall-clock timings for model construction phases),
- selected linearized cut mode.

### JSON export

If `--save-json` is enabled, the script also writes a timestamped JSON file that contains:
- the full generated instance,
- the assignment-penalty rule metadata,
- compatibility-preprocessing metadata,
- detailed lecture and hall data,
- per-lecture compatible-hall penalties,
- realized successor pairs and common-student counts,
- solver summaries,
- and full solution details for any solver that produced an assignment, including the walking and assignment-penalty contributions.

If `--instance-only` is used, the script instead writes timestamped instance JSON files containing:
- generation metadata,
- the full generated optimization input,
- hall, lecture, distance, compatibility, and successor-pair data,
- and no solver output.

### Console output

After each run, the script prints a compact summary line with:
- solver family,
- formulation,
- status,
- objective value,
- lower bound,
- gaps,
- wall-clock time.

With `--instance-only`, the terminal output switches to a readable instance report showing:
- high-level instance statistics,
- the halls table,
- the lectures table,
- realized successor pairs,
- and the hall distance matrix.

## Citation and License

The submitted code is available as [GitHub release
`v1.0.3`](https://github.com/tal69/lecture-halls/releases/tag/v1.0.3). Its
exact immutable archive is Zenodo DOI
[`10.5281/zenodo.21310605`](https://doi.org/10.5281/zenodo.21310605). This and
any later versions are grouped under concept DOI
[`10.5281/zenodo.21294644`](https://doi.org/10.5281/zenodo.21294644). Citation
metadata are provided in [`CITATION.cff`](CITATION.cff), which GitHub can render
as APA or BibTeX.

The original software and documentation are released under the [MIT
License](LICENSE). Third-party input datasets retain their own rights and are
not covered by the MIT License; see the [third-party data and reconstruction
notes](THIRD_PARTY_DATA.md).
