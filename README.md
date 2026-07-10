# Quadratic Lecture Hall Assignment

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21294644.svg)](https://doi.org/10.5281/zenodo.21294644)

This repository provides an exact optimization framework for the **Quadratic Lecture-Hall Assignment Problem (QLHAP)**, focused on minimizing student walking distances in university settings. By transforming real-world timetabling and registration data into optimal daily hall assignments, the project bridges the gap between theoretical Quadratic Assignment Problems (QAP) and operational campus scheduling. The revised paper reports the GUROBI MIQP and compact MIP formulations, strengthened by problem-specific biclique distance cuts. The repository also retains the OR-Tools CP-SAT implementation and result rows as a documented revision-stage attempt; those CP-SAT rows are not used in the revised paper tables because the compact MIP dominated them empirically.

## Release and Data Links

- [GitHub release `v1.0.1`](https://github.com/tal69/lecture-halls/releases/tag/v1.0.1)
- [Archived releases on Zenodo](https://doi.org/10.5281/zenodo.21294644) ([concept DOI `10.5281/zenodo.21294644`](https://doi.org/10.5281/zenodo.21294644))
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
- optional capacity-dominance constraints and compatibility preprocessing,
- solver backends:
  - GUROBI bilinear `MIPQ`,
  - GUROBI linearized `MIP`,
  - OR-Tools `CP`,
- a `ROOT` mode for reporting the root-node bound of the linearized GUROBI model,
- and a synthetic single-day instance generator for controlled experiments and stress tests. These synthetic instances are not used in the numerical experiments reported in the paper.

In the revised manuscript, the main exact-method tables use only `MIPQ` and
`MIP` rows from the 1800-second workbooks. `CP` remains available for
replication and comparison but is treated as an archived attempt.

The script also supports an `--instance-only` path that skips solving, prints the optimization input in a readable terminal layout, and saves the same instance in JSON.

## Requirements

Python `3.9+` with:
- `pandas`
- `openpyxl`
- `gurobipy`
- `ortools`

Install the Python packages with:

```bash
pip install pandas openpyxl gurobipy ortools
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

The numerical results in the paper depend on the solver versions, CPU, thread
count, and license configuration available to Gurobi and OR-Tools. The scripts
record the Python version, platform, host name, time limit, and solver/runtime
metadata in the output workbooks, but exact wall-clock times can still vary
across machines. Objective values, lower bounds, and optimality gaps are the
primary reproducibility targets.

## Reproducing the Paper Results

### Repository Layout

The paper workflow uses the following files and directories:

- `lecture_hall_experiment.py`: main experiment runner.
- `run_revision_1800.sh`: final shell entry point for reproducing the numerical results, using a 1800-second solver limit per run.
- `run_full_factorial_all.sh`: ITC 2019 exact-solver factorial campaign invoked by `run_revision_1800.sh`.
- `run_full_factorial_lancs.sh`: Lancaster exact-solver factorial campaign invoked by `run_revision_1800.sh`.
- `run_relaxations_factorial.sh`: root-relaxation factorial campaign invoked by `run_revision_1800.sh`.
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
| `full_factorial_1800s.xlsx` | 600 | Final ITC 2019 exact campaign. Contains `MIPQ`, `MIP`, and archived `CP` rows. The revised paper uses only the `MIPQ` and `MIP` rows. |
| `lancs_yr23_full_factorial_1800s.xlsx` | 240 | Final Lancaster 2023 exact campaign. Contains `MIPQ`, `MIP`, and archived `CP` rows. The revised paper uses only the `MIPQ` and `MIP` rows. |
| `relaxations_factorial_1800s.xlsx` | 280 | Final root-node diagnostic campaign for the compact `MIP` formulation. Used for the revised paper's root-gap diagnostic. |
| `full_factorial_300s.xlsx` | 600 | Archived ITC 2019 300-second exact campaign from the original computational study. Not used for revised-paper results. |
| `lancs_yr23_full_factorial_300s.xlsx` | 240 | Archived Lancaster 2023 300-second exact campaign from the original computational study. Not used for revised-paper results. |
| `relaxations_factorial_300s.xlsx` | 280 | Archived 300-second root-node diagnostic campaign. Not used for revised-paper results. |

The two final exact workbooks therefore contain 840 exact-run rows in total:
560 `MIPQ`/`MIP` rows used by the revised manuscript and 280 `CP` rows retained
to document the CP-SAT attempt. The final root workbook contributes 280
diagnostic `ROOT` rows.

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
    --compatibility-preprocess light \
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

The exact-solver stages call `lecture_hall_experiment.py` without `--model`,
so they run all three implemented exact backends: `MIPQ`, `MIP`, and `CP`.
This is intentional for replication. The revised paper filters the resulting
exact workbooks to the 560 `MIPQ`/`MIP` rows when producing the reported tables;
the 280 `CP` rows document the CP-SAT attempt that was left out of the revised
paper narrative.

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
- `best_methods`: the fastest and second-fastest exact methods by daily instance.
- `method_summary`: the 16-row MIQP/MIP method-combination table.
- `root_diagnostics`: the root-node diagnostic summary for biclique vs no biclique.
- `cp_attempt_summary`: a compact check of the retained CP-SAT rows.

The method-time columns use end-to-end wall time. For each run, the table
generator adds `compatibility_preprocess_wall_seconds` to `wall_clock_seconds`;
the latter times cut generation, model construction, and the solver call after
compatibility preprocessing has been applied. The raw components remain in the
workbooks, and the manuscript also summarizes the preprocessing component
separately.

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

Example using an ITC 2019 instance with preprocessing and biclique strengthening:

```bash
python lecture_hall_experiment.py \
    --source itc2019 \
    --itc-instance pu-proj-fal19 \
    --compatibility-preprocess light \
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
    --compatibility-preprocess full \
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

The repository includes several shell scripts to automate running comprehensive factorial parameter sweeps across the dataset:
- `run_full_factorial_all.sh`: Runs the exact solvers (`MIPQ`, `MIP`, `CP`) with all eight combinations of biclique strengthening, capacity-dominance constraints, and compatibility preprocessing on the 5 largest ITC 2019 instances (5 daily instances of the quadratic hall assignment problem for each, so 25 instances in total). The revised paper uses the `MIPQ` and `MIP` rows; the `CP` rows document the CP-SAT attempt.
- `run_full_factorial_lancs.sh`: Runs the same exact solver sweep over the 10 individual weekdays extracted from the Lancaster `lancs_yr23` instance (10 daily instances - 5 from the weekdays of the most loaded week in the first and second terms). The revised paper again uses only the `MIPQ` and `MIP` rows.
- `run_relaxations_factorial.sh`: Evaluates only the `ROOT` node linear relaxation bound across the same 35 daily instances (25 ITC 2019 days + 10 Lancaster days) to benchmark the gap-closing impact of the different biclique and preprocessing combinations.
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
  - `none`: disable preprocessing.
  - `full`: for each lecture `l'`, solve the hard-feasibility assignment model on all lectures while maximizing the capacity assigned to `l'`, then remove from `H(l')` every hall whose capacity is larger than the resulting maximum.
  - `light`: same idea, but solve the subproblem only on `l'` and lectures that overlap `l'`.
  - The `light` mode is safe but weaker: it may leave extra halls in `H(l')`, yet it cannot remove a hall that is needed by a globally feasible solution.
  - The reduction is applied iteratively until a fixed point is reached, so later subproblems benefit from earlier compatibility shrinkage.
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

## Compatibility Preprocessing

The optional compatibility preprocessor uses OR-Tools CP-SAT on the hard constraints only:
- each lecture must be assigned to exactly one currently compatible hall;
- overlapping lectures cannot use the same hall;
- the walking objective is ignored.

For a target lecture `l'`, the preprocessing objective is to maximize the capacity of the hall assigned to `l'`. Any hall in `H(l')` whose capacity is strictly larger than that maximum can be removed safely before solving `MIPQ`, `MIP`, `CP`, or `ROOT`.

The implementation provides two scopes:
- `full`: solve the subproblem on all lectures.
- `light`: solve it only on `l'` and lectures that overlap `l'`.

In both scopes, the preprocessing is run to a fixed point: after one full pass over the lectures, the reduced compatibility sets are fed back into the same subproblems and the process repeats until no `H(l)` shrinks any further.

If preprocessing empties some `H(l)`, the script declares the instance infeasible before calling the main solvers.

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
`v1.0.1`](https://github.com/tal69/lecture-halls/releases/tag/v1.0.1). Its
immutable Zenodo version and any later versions are grouped under concept DOI
[`10.5281/zenodo.21294644`](https://doi.org/10.5281/zenodo.21294644). Citation
metadata are provided in [`CITATION.cff`](CITATION.cff), which GitHub can render
as APA or BibTeX.

The original software and documentation are released under the [MIT
License](LICENSE). Third-party input datasets retain their own rights and are
not covered by the MIT License; see the [third-party data and reconstruction
notes](THIRD_PARTY_DATA.md).
