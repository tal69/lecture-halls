# Quadratic Lecture Hall Assignment

This repository contains a simulation and optimization tool for the lecture hall quadratic assignment problem. The script generates a **single-day** lecture-to-hall assignment instance and solves it with alternative exact formulations while minimizing:
- the walking burden induced by consecutive lectures that share students, and
- a linear assignment penalty for excessive wasted space in the chosen hall.

The current workflow includes:
- a random single-day instance generator,
- a student-journey simulation that determines lecture sizes and the realized successor set \(A'\),
- an optional family of capacity-dominance cardinality constraints derived from maximal overlap cliques,
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
- are first assigned by a randomized greedy balancing heuristic,
- and, if that heuristic fails on a dense instance, are completed by an exact CP-SAT fallback that preserves the balanced subject/year totals and enforces the cohort-overlap rule,
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

## Assignment Penalty

The objective now includes a per-assignment penalty that discourages placing a lecture in a hall that is much larger than needed.

For a lecture with `students = s` assigned to a hall with `capacity = u`:
- the penalty is `0` as long as at least `90%` of the hall is filled, equivalently while `s >= ceil(0.9 * u)`;
- otherwise the penalty is quadratic in the excess empty seats beyond that threshold:

```text
penalty(s, u) = max(0, ceil(0.9 * u) - s)^2
```

Examples for a hall of capacity `100`:
- class size `90` to `100`: penalty `0`
- class size `89`: penalty `1`
- class size `80`: penalty `100`

This penalty is generated automatically for every compatible lecture-hall pair and added to the objective in all solver backends (`MIPQ`, `MIP`, and `CP`).

Determinism note:
- if the original greedy attribute-assignment path succeeds for a given seed, the generated instance is unchanged by the fallback patch;
- the new CP-SAT fallback only affects seeds and parameter combinations for which the old generator would previously have failed with a runtime error.

## Complexity

The paper now includes an NP-hardness proof for the lecture-hall assignment problem via a reduction from the classical quadratic assignment problem. The reduction already applies to a restricted single-day case with two consecutive time blocks, identical hall capacities, and full lecture-hall compatibility.

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
  - The synthetic generator also enforces the cohort-overlap rules used to create student flows. With the current `8 x 4 = 32` subject-year cohorts, at most `64` lectures can run simultaneously, so very high densities become infeasible once `num_halls > 64`.
- `--time-limit`: per-solver time limit in seconds. Default: `60`.
- `--cuts {0,1,2,3}`: pair-distance cut mode.
  - `0`: base compact linking constraints only.
  - `1`: strong compact linking constraints only.
  - `2`: strong compact linking constraints plus the symmetric strong family.
  - `3`: one-sided extended strong cuts that enlarge the original strong family on the `l1` side.
  - In the `CP` model, mode `3` also activates a redundant propagation layer analogous to the extended strong cut; modes `0`-`2` do not change the CP formulation.
- `--cardinality`: enable the capacity-dominance cardinality constraints derived from maximal overlap cliques and hall-capacity thresholds.
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
  - The reduction is now applied iteratively until a fixed point is reached, so later subproblems benefit from earlier compatibility shrinkage.
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
- the two objective components:
  - total student walking distance,
  - matching penalty,
- lower bound,
- best global lower bound across solved methods for that instance,
- optimality gap and global optimality gap,
- runtime information,
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
