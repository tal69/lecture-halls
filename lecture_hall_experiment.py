#!/usr/bin/env python3
"""Generate and solve random lecture-hall assignment instances.

The script builds one random instance, solves it with three formulations:
1. GUROBI bilinear MIQP
2. GUROBI linearized MILP
3. OR-Tools CP-SAT

It then writes an Excel workbook with solver results and the generated data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import platform
import random
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from gurobipy import GRB, GurobiError, Model, quicksum
from openpyxl import Workbook, load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from ortools.sat.python import cp_model


DAYS_PER_WEEK = 5


@dataclass(frozen=True)
class Hall:
    hall_id: int
    name: str
    capacity: int
    x: float
    y: float


@dataclass(frozen=True)
class Lecture:
    lecture_id: int
    name: str
    day: int
    start_slot_in_day: int
    duration: int
    start_slot: int
    end_slot: int
    students: int
    hidden_hall: int


@dataclass(frozen=True)
class Instance:
    seed: int
    num_halls: int
    slots_per_day: int
    days_per_week: int
    density_target: float
    density_actual: float
    common_prob: float
    halls: list[Hall]
    lectures: list[Lecture]
    distances: list[list[int]]
    common_students: dict[tuple[int, int], int]
    compatibility: dict[int, list[int]]
    active_lectures_by_slot: dict[int, list[int]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a random lecture-hall assignment instance, solve it with "
            "Gurobi and OR-Tools, and write an Excel experiment summary."
        ),
        epilog=(
            "Density is interpreted as total lecture slots divided by total "
            "available hall-slots. This matches the stated default of 0.9."
        ),
    )
    parser.add_argument(
        "--num-halls",
        "--num_halls",
        dest="num_halls",
        type=int,
        required=True,
        help="Number of halls in the instance.",
    )
    parser.add_argument(
        "--slots-per-day",
        "--slots_per_day",
        dest="slots_per_day",
        type=int,
        default=12,
        help="Number of discrete slots per day. Default: 12.",
    )
    parser.add_argument(
        "--seed",
        dest="seed",
        type=int,
        default=0,
        help="Random seed. Default: 0.",
    )
    parser.add_argument(
        "--density",
        dest="density",
        type=float,
        default=0.9,
        help="Target lecture-slot utilization. Default: 0.9.",
    )
    parser.add_argument(
        "--common-prob",
        "--common_prob",
        dest="common_prob",
        type=float,
        default=0.3,
        help="Probability that two consecutive lectures share students. Default: 0.3.",
    )
    parser.add_argument(
        "--time-limit",
        "--time_limit",
        dest="time_limit",
        type=float,
        default=60.0,
        help="Per-solver time limit in seconds. Default: 60.",
    )
    parser.add_argument(
        "--output",
        dest="output",
        type=Path,
        default=None,
        help='Optional output workbook path. Defaults to "results.xlsx".',
    )
    parser.add_argument(
        "-s",
        "--save-json",
        dest="save_json",
        action="store_true",
        help="Also write a JSON file with the full instance and all solver solutions.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Disable solver terminal output while running.",
    )
    args = parser.parse_args()
    validate_args(args)
    return args


def validate_args(args: argparse.Namespace) -> None:
    if args.num_halls <= 0:
        raise SystemExit("--num-halls must be positive.")
    if args.slots_per_day < 4:
        raise SystemExit("--slots-per-day must be at least 4 because lectures last 2-4 slots.")
    if not 0 < args.density <= 1:
        raise SystemExit("--density must be in (0, 1].")
    if not 0 <= args.common_prob <= 1:
        raise SystemExit("--common-prob must be in [0, 1].")
    if args.time_limit <= 0:
        raise SystemExit("--time-limit must be positive.")


def ensure_output_path(path: Path | None, seed: int, num_halls: int) -> Path:
    if path is None:
        return Path("results.xlsx")
    if path.suffix.lower() != ".xlsx":
        return path.with_suffix(".xlsx")
    return path


def build_json_path(output_path: Path, run_tag: str) -> Path:
    return output_path.with_name(f"{output_path.stem}_{run_tag}.json")


def gurobi_thread_limit() -> int:
    cpu_count = os.cpu_count() or 1
    system = platform.system()
    if system == "Darwin":
        return min(cpu_count, 8)
    if system == "Linux":
        return min(cpu_count, 12)
    return min(cpu_count, 8)


def random_partition(total: int, parts: int, rng: random.Random) -> list[int]:
    if parts <= 0:
        raise ValueError("parts must be positive")
    if parts == 1:
        return [total]
    remaining = total
    values: list[int] = []
    for _ in range(parts - 1):
        value = rng.randint(0, remaining)
        values.append(value)
        remaining -= value
    values.append(remaining)
    rng.shuffle(values)
    return values


def duration_list_for_total(total_busy_slots: int, rng: random.Random) -> list[int]:
    durations: list[int] = []
    remaining = total_busy_slots
    while remaining > 0:
        candidates = [
            duration
            for duration in (2, 3, 4)
            if remaining - duration == 0 or remaining - duration >= 2
        ]
        if not candidates:
            raise ValueError(f"Cannot decompose {total_busy_slots} into durations 2-4.")
        duration = rng.choice(candidates)
        durations.append(duration)
        remaining -= duration
    rng.shuffle(durations)
    return durations


def generate_halls(num_halls: int, rng: random.Random) -> list[Hall]:
    halls: list[Hall] = []
    raw_capacities = [rng.randint(40, 220) for _ in range(num_halls)]
    raw_capacities.sort()
    for hall_id, capacity in enumerate(raw_capacities):
        halls.append(
            Hall(
                hall_id=hall_id,
                name=f"H{hall_id + 1}",
                capacity=capacity,
                x=round(rng.uniform(0, 100), 3),
                y=round(rng.uniform(0, 100), 3),
            )
        )
    return halls


def generate_distances(halls: list[Hall]) -> list[list[int]]:
    num_halls = len(halls)
    distances = [[0 for _ in range(num_halls)] for _ in range(num_halls)]
    for i, hall_i in enumerate(halls):
        for j, hall_j in enumerate(halls):
            if i == j:
                continue
            distances[i][j] = int(round(math.dist((hall_i.x, hall_i.y), (hall_j.x, hall_j.y)) * 10))
    return distances


def assign_durations_to_bins(
    durations: list[int],
    num_halls: int,
    days_per_week: int,
    slots_per_day: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    for _ in range(100):
        bins = [
            {
                "hall_id": hall_id,
                "day": day,
                "remaining": slots_per_day,
                "durations": [],
            }
            for hall_id in range(num_halls)
            for day in range(days_per_week)
        ]
        rng.shuffle(bins)
        success = True
        for duration in sorted(durations, reverse=True):
            candidates = [b for b in bins if b["remaining"] >= duration]
            if not candidates:
                success = False
                break
            best_slack = min(b["remaining"] - duration for b in candidates)
            shortlist = [b for b in candidates if b["remaining"] - duration <= best_slack + 1]
            chosen = rng.choice(shortlist)
            chosen["durations"].append(duration)
            chosen["remaining"] -= duration
        if success:
            return bins
    raise RuntimeError("Failed to pack lecture durations into hall/day bins.")


def generate_lectures(
    halls: list[Hall],
    slots_per_day: int,
    density: float,
    rng: random.Random,
) -> list[Lecture]:
    total_capacity = len(halls) * DAYS_PER_WEEK * slots_per_day
    target_busy_slots = max(2, min(total_capacity, int(round(density * total_capacity))))
    durations = duration_list_for_total(target_busy_slots, rng)
    bins = assign_durations_to_bins(durations, len(halls), DAYS_PER_WEEK, slots_per_day, rng)

    lectures: list[Lecture] = []
    lecture_id = 0
    for bin_info in bins:
        day = int(bin_info["day"])
        hall_id = int(bin_info["hall_id"])
        hall = halls[hall_id]
        day_durations = list(bin_info["durations"])
        if not day_durations:
            continue
        rng.shuffle(day_durations)
        used_slots = sum(day_durations)
        gaps = random_partition(slots_per_day - used_slots, len(day_durations) + 1, rng)
        current = gaps[0]
        for index, duration in enumerate(day_durations):
            start_slot_in_day = current
            start_slot = day * slots_per_day + start_slot_in_day
            end_slot = start_slot + duration
            lower = max(10, int(math.ceil(0.45 * hall.capacity)))
            students = rng.randint(lower, hall.capacity)
            lectures.append(
                Lecture(
                    lecture_id=lecture_id,
                    name=f"L{lecture_id + 1}",
                    day=day,
                    start_slot_in_day=start_slot_in_day,
                    duration=duration,
                    start_slot=start_slot,
                    end_slot=end_slot,
                    students=students,
                    hidden_hall=hall_id,
                )
            )
            lecture_id += 1
            current += duration + gaps[index + 1]
    lectures.sort(key=lambda lecture: (lecture.day, lecture.start_slot_in_day, lecture.lecture_id))
    return lectures


def generate_common_students(
    lectures: list[Lecture],
    common_prob: float,
    rng: random.Random,
) -> dict[tuple[int, int], int]:
    starts_by_day_slot: dict[tuple[int, int], list[Lecture]] = {}
    ends_by_day_slot: dict[tuple[int, int], list[Lecture]] = {}
    for lecture in lectures:
        starts_by_day_slot.setdefault((lecture.day, lecture.start_slot), []).append(lecture)
        ends_by_day_slot.setdefault((lecture.day, lecture.end_slot), []).append(lecture)

    all_candidate_pairs: list[tuple[int, int]] = []
    common_students: dict[tuple[int, int], int] = {}
    for key, next_lectures in starts_by_day_slot.items():
        prev_lectures = ends_by_day_slot.get(key, [])
        if not prev_lectures:
            continue

        selected_edges: set[tuple[int, int]] = set()
        for prev_lecture in prev_lectures:
            for next_lecture in next_lectures:
                pair = (prev_lecture.lecture_id, next_lecture.lecture_id)
                all_candidate_pairs.append(pair)
                if rng.random() <= common_prob:
                    selected_edges.add(pair)

        if not selected_edges:
            continue

        remaining_in = {lecture.lecture_id: lecture.students for lecture in next_lectures}
        prev_order = list(prev_lectures)
        rng.shuffle(prev_order)

        for prev_lecture in prev_order:
            eligible_successors = [
                lecture
                for lecture in next_lectures
                if (prev_lecture.lecture_id, lecture.lecture_id) in selected_edges
                and remaining_in[lecture.lecture_id] > 0
            ]
            if not eligible_successors:
                continue

            max_out = min(
                prev_lecture.students,
                sum(remaining_in[lecture.lecture_id] for lecture in eligible_successors),
            )
            if max_out <= 0:
                continue

            max_target = min(max_out, max(1, int(math.ceil(0.6 * prev_lecture.students))))
            target_out = rng.randint(1, max_target)
            rng.shuffle(eligible_successors)

            guaranteed_successors = eligible_successors[: min(len(eligible_successors), target_out)]
            for successor in guaranteed_successors:
                common_students[(prev_lecture.lecture_id, successor.lecture_id)] = (
                    common_students.get((prev_lecture.lecture_id, successor.lecture_id), 0) + 1
                )
                remaining_in[successor.lecture_id] -= 1

            remaining_out = target_out - len(guaranteed_successors)
            while remaining_out > 0:
                available_successors = [
                    lecture for lecture in eligible_successors if remaining_in[lecture.lecture_id] > 0
                ]
                if not available_successors:
                    break
                successor = rng.choices(
                    available_successors,
                    weights=[remaining_in[lecture.lecture_id] for lecture in available_successors],
                    k=1,
                )[0]
                common_students[(prev_lecture.lecture_id, successor.lecture_id)] = (
                    common_students.get((prev_lecture.lecture_id, successor.lecture_id), 0) + 1
                )
                remaining_in[successor.lecture_id] -= 1
                remaining_out -= 1

    if not common_students and all_candidate_pairs and common_prob > 0:
        lecture_map = {lecture.lecture_id: lecture for lecture in lectures}
        lecture_id_1, lecture_id_2 = rng.choice(all_candidate_pairs)
        max_shared = min(lecture_map[lecture_id_1].students, lecture_map[lecture_id_2].students)
        common_students[(lecture_id_1, lecture_id_2)] = max(1, min(max_shared, int(round(0.2 * max_shared))))
    return common_students


def build_instance(
    num_halls: int,
    slots_per_day: int,
    seed: int,
    density: float,
    common_prob: float,
) -> Instance:
    rng = random.Random(seed)
    halls = generate_halls(num_halls, rng)
    distances = generate_distances(halls)
    lectures = generate_lectures(halls, slots_per_day, density, rng)
    compatibility = {
        lecture.lecture_id: [hall.hall_id for hall in halls if hall.capacity >= lecture.students]
        for lecture in lectures
    }
    common_students = generate_common_students(lectures, common_prob, rng)
    horizon = DAYS_PER_WEEK * slots_per_day
    active_lectures_by_slot = {
        slot: [
            lecture.lecture_id
            for lecture in lectures
            if lecture.start_slot <= slot < lecture.end_slot
        ]
        for slot in range(horizon)
    }
    total_lecture_length = sum(lecture.duration for lecture in lectures)
    total_capacity = num_halls * DAYS_PER_WEEK * slots_per_day
    density_actual = total_lecture_length / total_capacity
    return Instance(
        seed=seed,
        num_halls=num_halls,
        slots_per_day=slots_per_day,
        days_per_week=DAYS_PER_WEEK,
        density_target=density,
        density_actual=density_actual,
        common_prob=common_prob,
        halls=halls,
        lectures=lectures,
        distances=distances,
        common_students=common_students,
        compatibility=compatibility,
        active_lectures_by_slot=active_lectures_by_slot,
    )


def safe_float(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(value):
        return value
    return None


def status_name_from_gurobi(status_code: int) -> str:
    mapping = {
        GRB.LOADED: "LOADED",
        GRB.OPTIMAL: "OPTIMAL",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.UNBOUNDED: "UNBOUNDED",
        GRB.CUTOFF: "CUTOFF",
        GRB.ITERATION_LIMIT: "ITERATION_LIMIT",
        GRB.NODE_LIMIT: "NODE_LIMIT",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.SOLUTION_LIMIT: "SOLUTION_LIMIT",
        GRB.INTERRUPTED: "INTERRUPTED",
        GRB.NUMERIC: "NUMERIC",
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
        GRB.USER_OBJ_LIMIT: "USER_OBJ_LIMIT",
    }
    return mapping.get(status_code, f"STATUS_{status_code}")


def assignment_details_from_map(
    instance: Instance,
    assignment_by_lecture: dict[int, int] | None,
) -> dict[str, Any] | None:
    if assignment_by_lecture is None:
        return None

    hall_map = {hall.hall_id: hall for hall in instance.halls}
    lecture_map = {lecture.lecture_id: lecture for lecture in instance.lectures}
    assignments = []
    objective_terms = []
    recomputed_objective = 0

    for lecture in instance.lectures:
        hall_id = assignment_by_lecture[lecture.lecture_id]
        hall = hall_map[hall_id]
        assignments.append(
            {
                "lecture_id": lecture.lecture_id,
                "lecture_name": lecture.name,
                "day": lecture.day,
                "start_slot": lecture.start_slot,
                "end_slot": lecture.end_slot,
                "students": lecture.students,
                "assigned_hall_id": hall_id,
                "assigned_hall_name": hall.name,
                "assigned_hall_capacity": hall.capacity,
            }
        )

    for (lecture_id_1, lecture_id_2), common_count in sorted(instance.common_students.items()):
        hall_id_1 = assignment_by_lecture[lecture_id_1]
        hall_id_2 = assignment_by_lecture[lecture_id_2]
        distance = instance.distances[hall_id_1][hall_id_2]
        contribution = common_count * distance
        recomputed_objective += contribution
        objective_terms.append(
            {
                "from_lecture_id": lecture_id_1,
                "from_lecture_name": lecture_map[lecture_id_1].name,
                "to_lecture_id": lecture_id_2,
                "to_lecture_name": lecture_map[lecture_id_2].name,
                "common_students": common_count,
                "from_hall_id": hall_id_1,
                "to_hall_id": hall_id_2,
                "distance": distance,
                "contribution": contribution,
            }
        )

    return {
        "assignment_by_lecture": assignment_by_lecture,
        "assignments": assignments,
        "objective_terms": objective_terms,
        "recomputed_objective": recomputed_objective,
    }


def solve_gurobi_quadratic(instance: Instance, time_limit: float, verbose: bool = True) -> dict[str, Any]:
    wall_start = time.perf_counter()
    thread_limit = gurobi_thread_limit()
    try:
        model = Model("lecture_hall_quadratic")
        model.Params.OutputFlag = 1 if verbose else 0
        model.Params.TimeLimit = time_limit
        model.Params.Threads = thread_limit
        model.Params.NonConvex = 2

        x: dict[tuple[int, int], Any] = {}
        for lecture in instance.lectures:
            for hall_id in instance.compatibility[lecture.lecture_id]:
                x[(lecture.lecture_id, hall_id)] = model.addVar(
                    vtype=GRB.BINARY,
                    name=f"x_{lecture.lecture_id}_{hall_id}",
                )

        model.update()

        for lecture in instance.lectures:
            model.addConstr(
                quicksum(
                    x[(lecture.lecture_id, hall_id)]
                    for hall_id in instance.compatibility[lecture.lecture_id]
                )
                == 1,
                name=f"assign_{lecture.lecture_id}",
            )

        for slot, active_lectures in instance.active_lectures_by_slot.items():
            if len(active_lectures) <= 1:
                continue
            for hall in instance.halls:
                vars_for_slot = [
                    x[(lecture_id, hall.hall_id)]
                    for lecture_id in active_lectures
                    if (lecture_id, hall.hall_id) in x
                ]
                if len(vars_for_slot) > 1:
                    model.addConstr(
                        quicksum(vars_for_slot) <= 1,
                        name=f"overlap_h{hall.hall_id}_t{slot}",
                    )

        objective_terms = []
        for (lecture_id_1, lecture_id_2), common_count in instance.common_students.items():
            for hall_id_1 in instance.compatibility[lecture_id_1]:
                for hall_id_2 in instance.compatibility[lecture_id_2]:
                    distance = instance.distances[hall_id_1][hall_id_2]
                    objective_terms.append(
                        common_count
                        * distance
                        * x[(lecture_id_1, hall_id_1)]
                        * x[(lecture_id_2, hall_id_2)]
                    )
        model.setObjective(quicksum(objective_terms), GRB.MINIMIZE)
        model.optimize()

        wall_seconds = time.perf_counter() - wall_start
        assignment_by_lecture = None
        if model.SolCount > 0:
            assignment_by_lecture = {}
            for lecture in instance.lectures:
                assigned_hall = next(
                    hall_id
                    for hall_id in instance.compatibility[lecture.lecture_id]
                    if x[(lecture.lecture_id, hall_id)].X > 0.5
                )
                assignment_by_lecture[lecture.lecture_id] = assigned_hall
        return {
            "solver_family": "GUROBI",
            "formulation": "quadratic_miqp",
            "status": status_name_from_gurobi(model.Status),
            "objective_value": safe_float(model.ObjVal) if model.SolCount > 0 else None,
            "lower_bound": safe_float(model.ObjBound),
            "wall_clock_seconds": wall_seconds,
            "solver_runtime_seconds": safe_float(model.Runtime),
            "mip_gap": safe_float(model.MIPGap) if model.SolCount > 0 else None,
            "threads": thread_limit,
            "error": None,
            "solution": assignment_details_from_map(instance, assignment_by_lecture),
        }
    except GurobiError as error:
        return {
            "solver_family": "GUROBI",
            "formulation": "quadratic_miqp",
            "status": "ERROR",
            "objective_value": None,
            "lower_bound": None,
            "wall_clock_seconds": time.perf_counter() - wall_start,
            "solver_runtime_seconds": None,
            "mip_gap": None,
            "threads": thread_limit,
            "error": str(error),
            "solution": None,
        }


def solve_gurobi_linearized(instance: Instance, time_limit: float, verbose: bool = True) -> dict[str, Any]:
    wall_start = time.perf_counter()
    thread_limit = gurobi_thread_limit()
    try:
        model = Model("lecture_hall_linearized")
        model.Params.OutputFlag = 1 if verbose else 0
        model.Params.TimeLimit = time_limit
        model.Params.Threads = thread_limit

        x: dict[tuple[int, int], Any] = {}
        y: dict[tuple[int, int, int, int], Any] = {}

        for lecture in instance.lectures:
            for hall_id in instance.compatibility[lecture.lecture_id]:
                x[(lecture.lecture_id, hall_id)] = model.addVar(
                    vtype=GRB.BINARY,
                    name=f"x_{lecture.lecture_id}_{hall_id}",
                )

        for (lecture_id_1, lecture_id_2) in instance.common_students:
            for hall_id_1 in instance.compatibility[lecture_id_1]:
                for hall_id_2 in instance.compatibility[lecture_id_2]:
                    y[(lecture_id_1, lecture_id_2, hall_id_1, hall_id_2)] = model.addVar(
                        vtype=GRB.BINARY,
                        name=f"y_{lecture_id_1}_{lecture_id_2}_{hall_id_1}_{hall_id_2}",
                    )

        model.update()

        for lecture in instance.lectures:
            model.addConstr(
                quicksum(
                    x[(lecture.lecture_id, hall_id)]
                    for hall_id in instance.compatibility[lecture.lecture_id]
                )
                == 1,
                name=f"assign_{lecture.lecture_id}",
            )

        for slot, active_lectures in instance.active_lectures_by_slot.items():
            if len(active_lectures) <= 1:
                continue
            for hall in instance.halls:
                vars_for_slot = [
                    x[(lecture_id, hall.hall_id)]
                    for lecture_id in active_lectures
                    if (lecture_id, hall.hall_id) in x
                ]
                if len(vars_for_slot) > 1:
                    model.addConstr(
                        quicksum(vars_for_slot) <= 1,
                        name=f"overlap_h{hall.hall_id}_t{slot}",
                    )

        for (lecture_id_1, lecture_id_2), _ in instance.common_students.items():
            for hall_id_1 in instance.compatibility[lecture_id_1]:
                for hall_id_2 in instance.compatibility[lecture_id_2]:
                    model.addConstr(
                        y[(lecture_id_1, lecture_id_2, hall_id_1, hall_id_2)]
                        >= x[(lecture_id_1, hall_id_1)] + x[(lecture_id_2, hall_id_2)] - 1,
                        name=f"link_{lecture_id_1}_{lecture_id_2}_{hall_id_1}_{hall_id_2}",
                    )

        objective_terms = []
        for (lecture_id_1, lecture_id_2), common_count in instance.common_students.items():
            for hall_id_1 in instance.compatibility[lecture_id_1]:
                for hall_id_2 in instance.compatibility[lecture_id_2]:
                    distance = instance.distances[hall_id_1][hall_id_2]
                    objective_terms.append(
                        common_count
                        * distance
                        * y[(lecture_id_1, lecture_id_2, hall_id_1, hall_id_2)]
                    )
        model.setObjective(quicksum(objective_terms), GRB.MINIMIZE)
        model.optimize()

        wall_seconds = time.perf_counter() - wall_start
        assignment_by_lecture = None
        if model.SolCount > 0:
            assignment_by_lecture = {}
            for lecture in instance.lectures:
                assigned_hall = next(
                    hall_id
                    for hall_id in instance.compatibility[lecture.lecture_id]
                    if x[(lecture.lecture_id, hall_id)].X > 0.5
                )
                assignment_by_lecture[lecture.lecture_id] = assigned_hall
        return {
            "solver_family": "GUROBI",
            "formulation": "linearized_milp",
            "status": status_name_from_gurobi(model.Status),
            "objective_value": safe_float(model.ObjVal) if model.SolCount > 0 else None,
            "lower_bound": safe_float(model.ObjBound),
            "wall_clock_seconds": wall_seconds,
            "solver_runtime_seconds": safe_float(model.Runtime),
            "mip_gap": safe_float(model.MIPGap) if model.SolCount > 0 else None,
            "threads": thread_limit,
            "error": None,
            "solution": assignment_details_from_map(instance, assignment_by_lecture),
        }
    except GurobiError as error:
        return {
            "solver_family": "GUROBI",
            "formulation": "linearized_milp",
            "status": "ERROR",
            "objective_value": None,
            "lower_bound": None,
            "wall_clock_seconds": time.perf_counter() - wall_start,
            "solver_runtime_seconds": None,
            "mip_gap": None,
            "threads": thread_limit,
            "error": str(error),
            "solution": None,
        }


def solve_cp_sat(instance: Instance, time_limit: float, verbose: bool = True) -> dict[str, Any]:
    wall_start = time.perf_counter()
    model = cp_model.CpModel()

    hall_assignment: dict[int, cp_model.IntVar] = {}
    for lecture in instance.lectures:
        domain = cp_model.Domain.FromValues(instance.compatibility[lecture.lecture_id])
        hall_assignment[lecture.lecture_id] = model.NewIntVarFromDomain(
            domain,
            f"a_{lecture.lecture_id}",
        )

    for active_lectures in instance.active_lectures_by_slot.values():
        if len(active_lectures) > 1:
            model.AddAllDifferent([hall_assignment[lecture_id] for lecture_id in active_lectures])

    objective_terms: list[Any] = []
    for (lecture_id_1, lecture_id_2), common_count in instance.common_students.items():
        feasible_distances = sorted(
            {
                instance.distances[hall_id_1][hall_id_2]
                for hall_id_1 in instance.compatibility[lecture_id_1]
                for hall_id_2 in instance.compatibility[lecture_id_2]
            }
        )
        distance_var = model.NewIntVar(
            feasible_distances[0],
            feasible_distances[-1],
            f"z_{lecture_id_1}_{lecture_id_2}",
        )
        tuples = [
            (hall_id_1, hall_id_2, instance.distances[hall_id_1][hall_id_2])
            for hall_id_1 in instance.compatibility[lecture_id_1]
            for hall_id_2 in instance.compatibility[lecture_id_2]
        ]
        model.AddAllowedAssignments(
            [hall_assignment[lecture_id_1], hall_assignment[lecture_id_2], distance_var],
            tuples,
        )
        objective_terms.append(common_count * distance_var)

    model.Minimize(sum(objective_terms) if objective_terms else 0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.log_search_progress = verbose
    status = solver.Solve(model)
    wall_seconds = time.perf_counter() - wall_start

    if status == cp_model.OPTIMAL:
        status_name = "OPTIMAL"
    elif status == cp_model.FEASIBLE:
        status_name = "FEASIBLE"
    elif status == cp_model.INFEASIBLE:
        status_name = "INFEASIBLE"
    elif status == cp_model.MODEL_INVALID:
        status_name = "MODEL_INVALID"
    else:
        status_name = "UNKNOWN"

    objective_value = None
    lower_bound = safe_float(solver.BestObjectiveBound())
    assignment_by_lecture = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        objective_value = safe_float(solver.ObjectiveValue())
        assignment_by_lecture = {
            lecture.lecture_id: solver.Value(hall_assignment[lecture.lecture_id])
            for lecture in instance.lectures
        }

    return {
        "solver_family": "OR_TOOLS",
        "formulation": "cp_sat",
        "status": status_name,
        "objective_value": objective_value,
        "lower_bound": lower_bound,
        "wall_clock_seconds": wall_seconds,
        "solver_runtime_seconds": safe_float(solver.WallTime()),
        "mip_gap": None,
        "threads": None,
        "error": None,
        "solution": assignment_details_from_map(instance, assignment_by_lecture),
    }


def build_summary_rows(
    instance: Instance,
    results: list[dict[str, Any]],
    started_at: dt.datetime,
    finished_at: dt.datetime,
    time_limit: float,
) -> list[dict[str, Any]]:
    total_lecture_length = sum(lecture.duration for lecture in instance.lectures)
    sizes = [lecture.students for lecture in instance.lectures]
    capacities = [hall.capacity for hall in instance.halls]
    common_values = list(instance.common_students.values())
    candidate_successors = sum(
        1
        for lecture in instance.lectures
        for follower in instance.lectures
        if lecture.day == follower.day and lecture.end_slot == follower.start_slot
    )

    try:
        script_path = Path(__file__)
        script_name = script_path.name
        script_last_modified = dt.datetime.fromtimestamp(script_path.stat().st_mtime).astimezone().isoformat()
    except Exception:
        script_name = "unknown"
        script_last_modified = "unknown"

    rows = []
    for result in results:
        obj = result.get("objective_value")
        lb = result.get("lower_bound")
        gap = result.get("mip_gap")
        if gap is None and obj is not None and lb is not None:
            if obj != 0:
                gap = max(0.0, float(obj - lb) / abs(float(obj)))
            else:
                gap = 0.0 if float(lb) >= 0 else float("inf")
        

        rows.append(
            {
                "experiment_started_at": started_at.isoformat(),
                "experiment_finished_at": finished_at.isoformat(),
                "script_name": script_name,
                "script_last_modified": script_last_modified,
                "host": socket.gethostname(),
                "platform": platform.platform(),
                "python_version": sys.version.split()[0],
                "seed": instance.seed,
                "num_halls": instance.num_halls,
                "days_per_week": instance.days_per_week,
                "slots_per_day": instance.slots_per_day,
                "time_horizon_slots": instance.days_per_week * instance.slots_per_day,
                "density_target": instance.density_target,
                "density_actual": instance.density_actual,
                "common_prob": instance.common_prob,
                "time_limit_seconds": time_limit,
                "num_lectures": len(instance.lectures),
                "total_lecture_length": total_lecture_length,
                "avg_lecture_length": total_lecture_length / len(instance.lectures),
                "min_lecture_length": min(lecture.duration for lecture in instance.lectures),
                "max_lecture_length": max(lecture.duration for lecture in instance.lectures),
                "min_class_size": min(sizes),
                "avg_class_size": sum(sizes) / len(sizes),
                "max_class_size": max(sizes),
                "min_hall_capacity": min(capacities),
                "avg_hall_capacity": sum(capacities) / len(capacities),
                "max_hall_capacity": max(capacities),
                "candidate_successor_pairs": candidate_successors,
                "successor_pairs_with_common_students": len(instance.common_students),
                "avg_common_students": (
                    sum(common_values) / len(common_values) if common_values else 0.0
                ),
                "total_common_students_weight": sum(common_values),
                "solver_family": result["solver_family"],
                "formulation": result["formulation"],
                "status": result["status"],
                "objective_value": result["objective_value"],
                "lower_bound": result["lower_bound"],
                "wall_clock_seconds": result["wall_clock_seconds"],
                "solver_runtime_seconds": result["solver_runtime_seconds"],
                "mip_gap": result["mip_gap"],
                "optimality_gap": gap,
                "threads": result["threads"],
                "error": result["error"],
            }
        )
    return rows


def excel_cell_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def sheet_is_empty(worksheet: Any) -> bool:
    return worksheet.max_row == 1 and worksheet.max_column == 1 and worksheet["A1"].value is None


def normalized_row(values: list[Any]) -> list[Any]:
    trimmed = list(values)
    while trimmed and trimmed[-1] is None:
        trimmed.pop()
    return trimmed


def last_header_row(worksheet: Any, first_header_cell: str) -> list[Any] | None:
    if sheet_is_empty(worksheet):
        return None
    for row_idx in range(worksheet.max_row, 0, -1):
        row_values = [
            worksheet.cell(row=row_idx, column=column_idx).value
            for column_idx in range(1, worksheet.max_column + 1)
        ]
        row_values = normalized_row(row_values)
        if row_values and row_values[0] == first_header_cell:
            return row_values
    return None


def unique_sheet_name(workbook: Workbook, base_name: str) -> str:
    candidate = base_name[:31]
    if candidate not in workbook.sheetnames:
        return candidate
    suffix_index = 1
    while True:
        suffix = f"_{suffix_index}"
        candidate = f"{base_name[:31 - len(suffix)]}{suffix}"
        if candidate not in workbook.sheetnames:
            return candidate
        suffix_index += 1


def write_row(worksheet: Any, row_index: int, values: list[Any]) -> None:
    for column_index, value in enumerate(values, start=1):
        worksheet.cell(row=row_index, column=column_index, value=excel_cell_value(value))


def append_dataframe_to_sheet(workbook: Workbook, sheet_name: str, dataframe: pd.DataFrame) -> None:
    worksheet = workbook.create_sheet(title=unique_sheet_name(workbook, sheet_name))
    row_index = 1
    for row in dataframe_to_rows(dataframe, index=False, header=True):
        write_row(worksheet, row_index, list(row))
        row_index += 1


def append_summary_sheet(workbook: Workbook, summary_df: pd.DataFrame) -> None:
    worksheet = workbook["summary"] if "summary" in workbook.sheetnames else workbook.create_sheet("summary")
    header = list(summary_df.columns)
    prior_header = last_header_row(worksheet, str(header[0])) if header else None
    row_index = 1 if sheet_is_empty(worksheet) else worksheet.max_row + 1
    if prior_header != header:
        write_row(worksheet, row_index, header)
        row_index += 1
    for row in summary_df.itertuples(index=False, name=None):
        write_row(worksheet, row_index, list(row))
        row_index += 1


def instance_to_json_dict(instance: Instance) -> dict[str, Any]:
    return {
        "seed": instance.seed,
        "num_halls": instance.num_halls,
        "slots_per_day": instance.slots_per_day,
        "days_per_week": instance.days_per_week,
        "density_target": instance.density_target,
        "density_actual": instance.density_actual,
        "common_prob": instance.common_prob,
        "halls": [
            {
                "hall_id": hall.hall_id,
                "hall_name": hall.name,
                "capacity": hall.capacity,
                "x": hall.x,
                "y": hall.y,
            }
            for hall in instance.halls
        ],
        "lectures": [
            {
                "lecture_id": lecture.lecture_id,
                "lecture_name": lecture.name,
                "day": lecture.day,
                "start_slot_in_day": lecture.start_slot_in_day,
                "duration": lecture.duration,
                "start_slot": lecture.start_slot,
                "end_slot": lecture.end_slot,
                "students": lecture.students,
                "compatible_halls": instance.compatibility[lecture.lecture_id],
            }
            for lecture in instance.lectures
        ],
        "successor_pairs": [
            {
                "from_lecture_id": lecture_id_1,
                "to_lecture_id": lecture_id_2,
                "common_students": common_count,
            }
            for (lecture_id_1, lecture_id_2), common_count in sorted(instance.common_students.items())
        ],
        "distances": instance.distances,
        "active_lectures_by_slot": [
            {"slot": slot, "lecture_ids": lecture_ids}
            for slot, lecture_ids in sorted(instance.active_lectures_by_slot.items())
            if lecture_ids
        ],
    }


def build_json_payload(
    instance: Instance,
    results: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    started_at: dt.datetime,
    finished_at: dt.datetime,
    time_limit: float,
) -> dict[str, Any]:
    return {
        "experiment": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": sys.version,
            "time_limit_seconds": time_limit,
        },
        "instance": instance_to_json_dict(instance),
        "results_summary": summary_rows,
        "solutions": results,
    }


def write_excel(
    output_path: Path,
    instance: Instance,
    results: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    run_tag: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    halls_df = pd.DataFrame(
        [
            {
                "hall_id": hall.hall_id,
                "hall_name": hall.name,
                "capacity": hall.capacity,
                "x": hall.x,
                "y": hall.y,
            }
            for hall in instance.halls
        ]
    )
    lectures_df = pd.DataFrame(
        [
            {
                "lecture_id": lecture.lecture_id,
                "lecture_name": lecture.name,
                "day": lecture.day,
                "start_slot_in_day": lecture.start_slot_in_day,
                "duration": lecture.duration,
                "start_slot": lecture.start_slot,
                "end_slot": lecture.end_slot,
                "students": lecture.students,
                "hidden_hall_id": lecture.hidden_hall,
                "compatible_halls": ",".join(map(str, instance.compatibility[lecture.lecture_id])),
            }
            for lecture in instance.lectures
        ]
    )
    transitions_df = pd.DataFrame(
        [
            {
                "from_lecture_id": lecture_id_1,
                "to_lecture_id": lecture_id_2,
                "common_students": common_count,
            }
            for (lecture_id_1, lecture_id_2), common_count in sorted(instance.common_students.items())
        ]
    )
    distance_df = pd.DataFrame(instance.distances)
    distance_df.index.name = "from_hall_id"
    distance_df.columns = [f"to_{hall.hall_id}" for hall in instance.halls]
    summary_df = pd.DataFrame(summary_rows)
    assignments_df = pd.DataFrame(
        [
            {
                "solver_family": result["solver_family"],
                "formulation": result["formulation"],
                **assignment_row,
            }
            for result in results
            for assignment_row in (result.get("solution") or {}).get("assignments", [])
        ]
    )
    objective_terms_df = pd.DataFrame(
        [
            {
                "solver_family": result["solver_family"],
                "formulation": result["formulation"],
                **term_row,
            }
            for result in results
            for term_row in (result.get("solution") or {}).get("objective_terms", [])
        ]
    )

    if output_path.exists():
        workbook = load_workbook(output_path)
    else:
        workbook = Workbook()
        default_sheet = workbook.active
        if default_sheet and sheet_is_empty(default_sheet):
            workbook.remove(default_sheet)

    append_summary_sheet(workbook, summary_df)
    append_dataframe_to_sheet(workbook, f"halls_{run_tag}", halls_df)
    append_dataframe_to_sheet(workbook, f"lectures_{run_tag}", lectures_df)
    append_dataframe_to_sheet(workbook, f"successors_{run_tag}", transitions_df)
    append_dataframe_to_sheet(workbook, f"distances_{run_tag}", distance_df.reset_index())
    if not assignments_df.empty:
        append_dataframe_to_sheet(workbook, f"assignments_{run_tag}", assignments_df)
    if not objective_terms_df.empty:
        append_dataframe_to_sheet(workbook, f"term_costs_{run_tag}", objective_terms_df)
    workbook.save(output_path)


def write_json(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def print_console_summary(output_path: Path, summary_rows: list[dict[str, Any]]) -> None:
    print(f"Results written to: {output_path}")
    print("")
    for row in summary_rows:
        gap_str = str(row['optimality_gap']) if row['optimality_gap'] is None else f"{row['optimality_gap']:.2%}"
        print(
            f"{row['solver_family']:>8} | {row['formulation']:<16} | "
            f"status={row['status']:<12} | obj={row['objective_value']} | "
            f"lb={row['lower_bound']} | gap={gap_str} | wall={row['wall_clock_seconds']:.3f}s"
        )


def main() -> None:
    args = parse_args()
    output_path = ensure_output_path(args.output, args.seed, args.num_halls)

    started_at = dt.datetime.now().astimezone()
    run_tag = started_at.strftime("%Y%m%d_%H%M%S")
    instance = build_instance(
        num_halls=args.num_halls,
        slots_per_day=args.slots_per_day,
        seed=args.seed,
        density=args.density,
        common_prob=args.common_prob,
    )

    results = [
        solve_gurobi_quadratic(instance, args.time_limit, verbose=not args.quiet),
        solve_gurobi_linearized(instance, args.time_limit, verbose=not args.quiet),
        solve_cp_sat(instance, args.time_limit, verbose=not args.quiet),
    ]

    finished_at = dt.datetime.now().astimezone()
    summary_rows = build_summary_rows(
        instance=instance,
        results=results,
        started_at=started_at,
        finished_at=finished_at,
        time_limit=args.time_limit,
    )
    write_excel(output_path, instance, results, summary_rows, run_tag)
    if args.save_json:
        json_path = build_json_path(output_path, run_tag)
        payload = build_json_payload(
            instance=instance,
            results=results,
            summary_rows=summary_rows,
            started_at=started_at,
            finished_at=finished_at,
            time_limit=args.time_limit,
        )
        write_json(json_path, payload)
        print(f"JSON written to: {json_path}")
    print_console_summary(output_path, summary_rows)


if __name__ == "__main__":
    main()
