# Quadratic Lecture Hall Assignment

This repository contains data acquisition, instance-preparation, and exact optimization code for the lecture hall quadratic assignment problem. The main workflow is to transform realistic weekly timetabling and registration data into **single-day** lecture-to-hall assignment instances and then solve them with alternative exact formulations.

The realistic-data pipeline currently supports:
- the ITC 2019 university course timetabling benchmark XML files,
- the Lancaster 2023 institutional timetable and anonymized registration data,
- preservation of the original hall set, capacities, and hall-to-hall distances,
- reconstruction of student-flow successor pairs from timetable and registration records,
- import or propagation of hall-assignment penalties,
- and propagation of the additional side constraints discussed in Section 3.5, in particular hard and soft `SameRoom` and `SameAttendees`.

The optimization models minimize:
- the walking burden induced by consecutive lectures that share students,
- linear hall-assignment penalties,
- and, when present in the source data, penalties for soft `SameRoom` and soft `SameAttendees` violations.

The current workflow includes:
- realistic-data preparation for ITC 2019, including peak-week selection, weekday extraction, short-break inference, student-flow construction, hall-penalty import, and side-constraint extraction,
- realistic-data preparation for Lancaster 2023, including `SameClass` contraction, peak-week selection by term, registration repair, and side-constraint projection,
- optional capacity-dominance constraints and compatibility preprocessing,
- three main solver backends:
  - GUROBI bilinear `MIPQ`,
  - GUROBI linearized `MIP`,
  - OR-Tools `CP`,
- a `ROOT` mode for reporting the root-node bound of the linearized GUROBI model,
- and a synthetic single-day instance generator for controlled experiments and stress tests.

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

## Real-World Data Preparation

### ITC 2019

The script natively supports loading real-world XML instances from the International Timetabling Competition (ITC 2019).
- **Week and Day Selection**: It selects the most loaded teaching week automatically if not specified, and by default retains only weekdays `0-4`.
- **Student-Flow Inference**: It maps lecture-student records to construct consecutive successor pairs using a short-break threshold that can be inferred from the timetable or provided manually.
- **Capacity Fix**: It automatically handles anomalies where the published ITC solution places a lecture in a hall smaller than the recorded class size by reducing the student count only for those anomalies.
- **Penalties and Side Constraints**: It imports the original hall-assignment penalties together with the hard and soft `SameRoom` and `SameAttendees` constraints defined in the XML data.

### Lancaster 2023

The repository also supports a Lancaster-specific data-transformation path for `lancs-yr23.xml`.
- It merges `SameClass` components into representative activities before any day-level instance is created.
- It identifies the two main teaching terms and selects the peak-load week of each term.
- It keeps weekdays `0-4` by default and discards weekend activity unless a specific source day is requested.
- It greedily repairs student registrations subject to the merged weekly timetable and hidden-hall capacities.
- It propagates the relevant side constraints from the weekly XML data to the resulting day-level hall-assignment instances exposed to `lecture_hall_experiment.py`.

## Synthetic Instance Generation

The synthetic generator is retained for controlled experiments and stress testing. It also builds a **single-day** instance because the weekly problem is separable by day.

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

The main entry point is `lecture_hall_experiment.py`. The paper workflow primarily uses the real-world data-preparation modes shown below. If `--source` is omitted, the script falls back to synthetic generation.

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

Example with more options for synthetic generation:

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
- `run_full_factorial_all.sh`: Runs the exact solvers (`MIPQ`, `MIP`, `CP`) with all eight combinations of biclique strengthening, capacity-dominance constraints, and compatibility preprocessing on the 5 largest ITC 2019 instances (5 daily instances of the quadratic hall assignment problem for each, so 25 instances in total).
- `run_full_factorial_lancs.sh`: Runs the same exact solver sweep over the 10 individual weekdays extracted from the Lancaster `lancs_yr23` instance (10 daily instances - 5 from the weekdays of the most loaded week in the first and second terms).
- `run_relaxations_factorial.sh`: Evaluates only the `ROOT` node linear relaxation bound across all 6 instances (5 ITC 2019 + Lancaster) to benchmark the gap-closing impact of the different biclique and preprocessing combinations.

Each script accepts the running time per instance as a parameter.


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
  - `CP`: OR-Tools CP-SAT formulation.
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
- With `--biclique`, `MIP` uses the same anchor-based biclique construction as Section 3.4, and the implementation folds the common-student weight into the pair variable for scaling.
- With `--biclique`, `MIPQ` keeps the walking objective bilinear and adds the corresponding quadratic biclique inequalities directly in the assignment variables.

It does **not** use the older four-index linearization with variables `y_(l1,l2,h1,h2)`.

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
- runtime information (including detailed wall-clock timings for model construction phrases),
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
