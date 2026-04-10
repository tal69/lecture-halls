# Quadratic Lecture Hall Assignment

This repository contains a research-oriented simulation and optimization tool for the **Quadratic Lecture Hall Assignment** problem. The problem involves assigning a set of scheduled lectures to a set of halls with varying capacities over a planning horizon (e.g., a standard 5-day week split into discrete timeslots) while minimizing the distance traveled by students attending back-to-back lectures. 

The tool algorithmically generates random lecture hall assignment instances using various configurations, and benchmarks three different solution formulations against each other:
1. **GUROBI Bilinear MIQP** (Mixed-Integer Quadratic Programming Formulation)
2. **GUROBI Linearized MILP** (Mixed-Integer Linear Programming Formulation)
3. **OR-Tools CP-SAT** (Constraint Programming Formulation)

## Requirements

Ensure you have Python 3.9+ along with the required dependencies:
- `pandas`
- `openpyxl`
- `gurobipy` (A valid Gurobi license is required for the MIQP and MILP solvers)
- `ortools`

You can install the Python packages (excluding the Gurobi license) using:
```bash
pip install pandas openpyxl gurobipy ortools
```

## Usage

The primary script is `lecture_hall_experiment.py`. It generates a random problem instance, dispatches it to all three solvers consecutively, and saves a comprehensive summary of the results locally.

### Basic Example

```bash
python lecture_hall_experiment.py --num-halls 10
```

### Full Configuration

You can fully customize the generated instance and experiment parameters:

```bash
python lecture_hall_experiment.py \
    --num-halls 15 \
    --slots-per-day 12 \
    --density 0.9 \
    --common-prob 0.3 \
    --time-limit 120 \
    --seed 42 \
    --save-json
```

### Command-Line Arguments

- `--num-halls` **(Required)**: Total number of physical halls available.
- `--slots-per-day`: Number of discrete time slots per day. (Default: `12`)
- `--seed`: Seed for the random instance generator to ensure reproducibility. (Default: `0`)
- `--density`: Target lecture-slot utilization — conceptually, the total lecture slots scheduled divided by the total available hall-slots. (Default: `0.9`)
- `--common-prob`: Probability that two subsequent (consecutive) lectures share a group of mutual students. (Default: `0.3`)
- `--time-limit`: The maximum execution runtime limit per individual solver, in seconds. (Default: `60.0`)
- `--output`: Filepath to save the Excel workbook summary. (Default: `"results.xlsx"`)
- `-s, --save-json`: Include this flag to export a robust JSON payload capturing the full problem instance data alongside all solver solutions.
- `-q, --quiet`: If set, the solvers evaluate silently without passing output into the terminal. (By default, solver terminal logs are displayed in real-time).

## Outputs

1. **Excel Workbook (`results.xlsx`)**  
   Contains a high-level summary overview of runtime performance, problem scale, generated statuses, and optimality gaps. Further sheets unpack the core properties of the randomly generated scenario: `halls`, `lectures`, `successors`/transitions, `distances`, `assignments`, and detailed `term_costs` breakdowns.

2. **JSON Export (`results_{timestamp}.json`)** *(Optional using `--save-json`)*  
   An algorithmic-friendly object format storing the raw coordinate mappings, constraints matrices, active schedules, mutual students matrices, and final assigned targets.

3. **Console Summary**  
   After completing all three solves, the script yields a compact table within standard output outlining objective bounds, optimality gaps, solve status, and time spent on solving.
