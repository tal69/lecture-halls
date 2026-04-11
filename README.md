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
- are generated with balanced `subject` and `study_year` profiles,
- choose their first lecture using an earlier-slot preference,
- continue through the day based on their own profile, not on the previous course,
- prefer compulsory courses over electives,
- strongly prefer same-topic and same-year lectures, with very weak probability of large year jumps.

Lecture sizes are not sampled directly. Each lecture receives a target attendance based on its hidden hall capacity, and the final class size is the realized attendance count from the student-journey simulation.

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
    --save-json
```

## Command-Line Arguments

- `--num-halls` **(required)**: number of halls.
- `--slots-per-day`: number of discrete slots in the day. Default: `12`.
- `--seed`: one seed, a closed range such as `1-100`, or a start-step-end pattern such as `1-3-10`. Default: `0`.
- `--density`: target lecture-slot utilization, interpreted as total lecture slots divided by total available hall-slots in the day. Default: `0.9`.
- `--time-limit`: per-solver time limit in seconds. Default: `60`.
- `--cuts {0,1}`: cut mode for the linearized GUROBI model.
  - `0`: base compact linking constraints only.
  - `1`: strong compact linking constraints only.
- `--model`: optional single model to solve.
  - `MIPQ`: bilinear GUROBI formulation.
  - `MIP`: compact linearized GUROBI formulation.
  - `CP`: OR-Tools CP-SAT formulation.
  - `ROOT`: root-node bound of the linearized GUROBI formulation.
  - If omitted, the script solves `MIPQ`, `MIP`, and `CP`.
- `--output`: Excel output path. Default: `results.xlsx`.
- `-s`, `--save-json`: also write a JSON file with the full instance and all solutions.
- `-q`, `--quiet`: suppress solver logs.

## Linearized GUROBI Model

The current `MIP` model uses the **compact** linearization from the paper:
- binary assignment variables `x_(l,h)`,
- one nonnegative continuous variable `y_(l1,l2)` per successor pair.

It does **not** use the older four-index linearization with variables `y_(l1,l2,h1,h2)`.

## Outputs

### Excel workbook

The Excel file contains a single `summary` sheet. Repeated runs append new rows rather than overwriting prior results. The summary includes:
- experiment timestamps,
- seed and instance demographics,
- density and size statistics,
- realized successor-set statistics,
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
- detailed lecture and hall data,
- realized successor pairs and common-student counts,
- solver summaries,
- and full solution details for any solver that produced an assignment.

### Console output

After each run, the script prints a compact summary line with:
- solver family,
- formulation,
- status,
- objective value,
- lower bound,
- gaps,
- wall-clock time.
