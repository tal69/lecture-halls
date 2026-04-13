# Quadratic Lecture Hall Assignment

This repository contains a simulation and optimization tool for the lecture hall quadratic assignment problem. The script generates a **single-day** lecture-to-hall assignment instance and solves it with alternative exact formulations while minimizing the walking burden induced by consecutive lectures that share students.

The current workflow includes:
- a random single-day instance generator,
- a student-journey simulation that determines lecture sizes and the realized successor set \(A'\),
- three main solver backends:
  - GUROBI bilinear `MIPQ`,
  - GUROBI linearized `MIP`,
  - OR-Tools `CP`,
- and a `ROOT` mode for reporting the root-node bound of the linearized GUROBI model.

The script also supports an `--instance-only` path that skips solving, prints the generated optimization input in a readable terminal layout, and saves the same instance in JSON.

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

## Instance Generation

The generator now builds a **single-day** instance because the weekly problem is separable by day.

Lectures:
- have duration `2` to `4` slots,
- are distributed across halls to match the requested density,
- are assigned balanced `subject` and `study_year` labels,
- are classified as roughly `70%` compulsory and `30%` elective,
- satisfy the timetable rule that for any fixed `(subject, year)` cohort and time slot there is either:
  - at most one compulsory lecture, or
  - at most two elective lectures,
  - but not both.

Students:
- are generated around active `(subject, study_year)` cohorts rather than as independent first-course draws,
- receive cohort sizes that are anchored to the compulsory offerings of their own cohort,
- attend almost all compulsory lectures of their own topic and year,
- are frequently distributed among their own parallel elective lectures,
- may occasionally take a previous-year lecture in their own topic,
- and only very rarely take lectures from other topics.

Lecture sizes are not sampled directly. They are the realized attendance counts produced by the cohort-based day-schedule simulation.
After the student-journey simulation, each lecture size is tightened toward the capacity of its hidden feasible hall so that the room-capacity constraints remain globally feasible but materially more restrictive.

## Usage

The main entry point is:

```bash
python lecture_hall_experiment.py --num-halls 10
```

Example with more options:

```bash
python lecture_hall_experiment.py \
    --num-halls 12 \
    --slots-per-day 12 \
    --density 0.9 \
    --time-limit 120 \
    --seed 1-10 \
    --cuts 1 \
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

## Command-Line Arguments

- `--num-halls` **(required)**: number of halls.
- `--slots-per-day`: number of discrete slots in the day. Default: `12`.
- `--seed`: one seed, a closed range such as `1-100`, or a start-step-end pattern such as `1-3-10`. Default: `0`.
- `--density`: target lecture-slot utilization, interpreted as total lecture slots divided by total available hall-slots in the day. Default: `0.9`.
- `--time-limit`: per-solver time limit in seconds. Default: `60`.
- `--cuts {0,1,2,3}`: cut mode for the linearized GUROBI model.
  - `0`: base compact linking constraints only.
  - `1`: strong compact linking constraints only.
  - `2`: strong compact linking constraints plus the symmetric strong family.
  - `3`: one-sided extended strong cuts that enlarge the original strong family on the `l1` side.
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
- `--cuts 0` uses the rescaled distance variable form from the paper.
- `--cuts 1`, `--cuts 2`, and `--cuts 3` use the equivalent weighted pair-cost substitution for computational reasons.

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
- lower bound,
- best global lower bound across solved methods for that instance,
- optimality gap and global optimality gap,
- runtime information,
- selected linearized cut mode.

### JSON export

If `--save-json` is enabled, the script also writes a timestamped JSON file that contains:
- the full generated instance,
- compatibility-preprocessing metadata,
- detailed lecture and hall data,
- realized successor pairs and common-student counts,
- solver summaries,
- and full solution details for any solver that produced an assignment.

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
