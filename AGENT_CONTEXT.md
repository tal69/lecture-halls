# AGENT_CONTEXT

## Project goal

Maintain the lecture hall quadratic assignment codebase: generate seeded single-day instances, solve them with exact formulations, and keep the implementation, README, and paper context aligned.

## Main files

- Code: [lecture_hall_experiment.py](/Users/talraviv/Library/CloudStorage/Dropbox/research/Quadraic%20Lecture%20Hall%20Assignment/lecture_hall_experiment.py)
- ITC Loader: [prepare_itc2019_inputs.py](/Users/talraviv/Library/CloudStorage/Dropbox/research/Quadraic%20Lecture%20Hall%20Assignment/prepare_itc2019_inputs.py)
- Batch Script: [run_full_factorial_all.sh](/Users/talraviv/Library/CloudStorage/Dropbox/research/Quadraic%20Lecture%20Hall%20Assignment/run_full_factorial_all.sh)
- Docs: [README.md](/Users/talraviv/Library/CloudStorage/Dropbox/research/Quadraic%20Lecture%20Hall%20Assignment/README.md)
- Paper draft: [main.tex](/Users/talraviv/Library/CloudStorage/Dropbox/research/Quadraic%20Lecture%20Hall%20Assignment/main.tex)

## Current solver scope

The script generates synthetic or loads single-day instances only (`DAYS_PER_WEEK = 1`) with:
- `MIPQ`: Gurobi bilinear MIQP
- `MIP`: Gurobi compact linearized MILP
- `CP`: OR-Tools CP-SAT
- `ROOT`: root-node bound of the linearized MILP

Common features across formulations:
- hard assignment constraints
- hard overlap constraints
- walking cost over successor pairs with common students
- compatibility preprocessing modes `none`, `full`, and `light`

## Current objective

The objective now has two parts:

1. Walking cost:
- for each successor pair `(l1, l2)`, cost is
  `common_students(l1, l2) * distance(h1, h2)`

2. Assignment penalty:
- For synthetic problems, each compatible lecture-hall pair `(l, h)` gets a linear penalty based on wasted hall space:
  - no penalty while `s >= ceil(0.9 * u)`
  - otherwise `max(0, ceil(0.9 * u) - s)^2`
- For ITC 2019 instances, the penalty directly uses the `room-penalty` provided in the raw XML data.

Implementation details:
- constant: `FREE_WASTE_RATIO = 0.10`
- helper functions:
  - `min_students_without_waste_penalty(...)`
  - `wasted_space_penalty(...)`
  - `build_assignment_penalties(...)`
- stored in the instance as
  `assignment_penalties: dict[int, dict[int, int]]`

All three solver families optimize the same combined objective.

## Current instance data

Each `Instance` now includes:
- halls
- lectures
- distances
- `common_students`
- `compatibility`
- `assignment_penalties`
- active lectures by slot
- compatibility-preprocessing metadata

JSON exports now also include:
- assignment-penalty rule metadata
- per-lecture compatible-hall penalties

Solution JSON/details now include:
- per-assignment penalty information
- walking objective terms
- assignment-penalty terms
- recomputed walking objective
- recomputed assignment penalty
- recomputed total objective

## Important recent code changes

### 1. Generator fallback fix

Dense instances that previously failed in balanced lecture-attribute generation now fall back to an exact CP-SAT construction after the randomized greedy path fails.

Determinism rule:
- if the original greedy generator already succeeded for a seed/parameter tuple, the instance is unchanged
- only previously failing cases can differ

### 2. Wasted-space penalty added

The objective was extended with a bad room-matching penalty based solely on wasted space:
- free up to `10%` empty seats
- quadratic beyond that threshold

This penalty is now implemented in:
- MIQP objective
- MILP objective
- CP-SAT objective
- solution reconstruction and JSON reporting
- instance JSON export

### 3. ITC 2019 Integration
- Added `prepare_itc2019_inputs.py` to extract single-day instances from ITC 2019 dataset
- `lecture_hall_experiment.py` handles diverse assignment penalties (`quadratic_wasted_space` or `itc2019_room_penalty`)
- Factored out logic to `lecture_hall_instance_builder.py` alongside updated data models.
- Provided `run_full_factorial_all.sh` for batch testing real-world instances.

## Verification completed in this session

- `python -m py_compile lecture_hall_experiment.py` passed
- smoke solve:
  - `python lecture_hall_experiment.py --num-halls 6 --density 0.4 --seed 1 --time-limit 5 --quiet --save-json --output /tmp/lecture_penalty_smoke.xlsx`
  - all three formulations solved optimally
- penalty-generation probe:
  - `build_instance(10, 12, 1, 0.2)` produced positive assignment penalties

## Git guidance

Background sync scripts (`auto_sync.sh` and `stop_sync.sh`) may be present. Do not delete them.
There may be unrelated paper edits in:
- `main.tex`
- `main.pdf`
- `refs.bib`

Do not assume those should be committed with code changes unless explicitly requested.
