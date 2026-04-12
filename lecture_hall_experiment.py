#!/usr/bin/env python3
"""Generate random single-day lecture-hall assignment instances.

The script can either:
1. solve a generated instance with multiple formulations and write result summaries, or
2. print the generated optimization input and export it as JSON without solving.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
import math
import os
import platform
import random
import socket
import statistics
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from gurobipy import GRB, GurobiError, Model, quicksum
from openpyxl import Workbook, load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from ortools.sat.python import cp_model


# The problem is separable by day, so each generated instance is a single-day instance.
DAYS_PER_WEEK = 1
SUBJECTS = (
    "Mathematics",
    "Physics",
    "ComputerScience",
    "Economics",
    "History",
    "Biology",
    "Chemistry",
    "Psychology",
)
STUDY_YEARS = (1, 2, 3, 4)


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
    subject: str
    study_year: int
    is_compulsory: bool
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
    halls: list[Hall]
    lectures: list[Lecture]
    distances: list[list[int]]
    common_students: dict[tuple[int, int], int]
    compatibility: dict[int, list[int]]
    active_lectures_by_slot: dict[int, list[int]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a random single-day lecture-hall assignment instance, then either "
            "solve it with the selected formulation(s) or print/export the generated input."
        ),
        epilog=(
            "Density is interpreted as total lecture slots divided by total "
            "available hall-slots in the day. This matches the stated default of 0.9."
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
        type=str,
        default="0",
        help="Random seed. Can be a single int, a range (e.g. 1-100), or start-step-end (e.g. 1-3-9). Default: 0.",
    )
    parser.add_argument(
        "--density",
        dest="density",
        type=float,
        default=0.9,
        help="Target lecture-slot utilization. Default: 0.9.",
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
        "--cuts",
        dest="cuts",
        type=int,
        choices=(0, 1),
        default=1,
        help=(
            "Linearized MILP cut mode: 0 = base link constraints only, "
            "1 = strong cut only. Default: 1."
        ),
    )
    parser.add_argument(
        "--model",
        dest="model",
        type=str,
        default=None,
        help=(
            "Optional single model to solve: MIPQ, MIP, CP, or ROOT. "
            "When omitted, the script solves the three original models."
        ),
    )
    parser.add_argument(
        "--instance-only",
        dest="instance_only",
        action="store_true",
        help=(
            "Generate the instance only, print the full optimization input in a "
            "human-readable terminal format, and write machine-readable JSON files. "
            "No solver is run and no Excel workbook is written."
        ),
    )
    parser.add_argument(
        "--output",
        dest="output",
        type=Path,
        default=None,
        help=(
            'Optional output workbook path. Defaults to "results.xlsx". '
            "In --instance-only mode, only the filename stem is used to name the JSON export(s)."
        ),
    )
    parser.add_argument(
        "-s",
        "--save-json",
        dest="save_json",
        action="store_true",
        help=(
            "Also write a JSON file with the full instance and all solver solutions. "
            "This is not needed in --instance-only mode because JSON export is automatic there."
        ),
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
    if args.time_limit <= 0:
        raise SystemExit("--time-limit must be positive.")
    if args.model is not None:
        args.model = args.model.upper()
        if args.model == "MIQP":
            args.model = "MIPQ"
        if args.model not in {"MIPQ", "MIP", "CP", "ROOT"}:
            raise SystemExit("--model must be one of MIPQ, MIP, CP, or ROOT.")
    if args.instance_only and args.model is not None:
        raise SystemExit("--instance-only cannot be combined with --model.")


def ensure_output_path(path: Path | None, seed: Any, num_halls: int) -> Path:
    if path is None:
        return Path("results.xlsx")
    if path.suffix.lower() != ".xlsx":
        return path.with_suffix(".xlsx")
    return path


def parse_seed_range(seed_str: str) -> list[int]:
    parts = str(seed_str).split("-")
    try:
        if len(parts) == 1:
            return [int(parts[0])]
        elif len(parts) == 2:
            return list(range(int(parts[0]), int(parts[1]) + 1))
        elif len(parts) == 3:
            return list(range(int(parts[0]), int(parts[2]) + 1, int(parts[1])))
    except ValueError:
        pass
    raise ValueError(f"Invalid seed format: {seed_str}")


def build_json_path(output_path: Path, run_tag: str) -> Path:
    return output_path.with_name(f"{output_path.stem}_{run_tag}.json")


def build_instance_json_path(output_path: Path, run_tag: str) -> Path:
    return output_path.with_name(f"{output_path.stem}_instance_{run_tag}.json")


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


def balanced_values(values: tuple[Any, ...] | list[Any], count: int, rng: random.Random) -> list[Any]:
    base_values = list(values)
    if count <= 0:
        return []
    full_repeats, remainder = divmod(count, len(base_values))
    result = base_values * full_repeats
    if remainder:
        result.extend(rng.sample(base_values, remainder))
    rng.shuffle(result)
    return result


def balanced_course_type_flags(count: int, rng: random.Random) -> list[bool]:
    if count <= 0:
        return []
    compulsory_count = int(round(0.70 * count))
    if count >= 2:
        compulsory_count = min(count - 1, max(1, compulsory_count))
    else:
        compulsory_count = count
    flags = [True] * compulsory_count + [False] * (count - compulsory_count)
    rng.shuffle(flags)
    return flags


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
            # Ceiling preserves the triangle inequality when converting
            # scaled Euclidean distances to integers.
            distances[i][j] = int(math.ceil(math.dist((hall_i.x, hall_i.y), (hall_j.x, hall_j.y)) * 10))
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


def cohort_slot_is_feasible(
    slot_usage: dict[tuple[str, int, int], tuple[int, int]],
    subject: str,
    study_year: int,
    is_compulsory: bool,
    start_slot: int,
    end_slot: int,
) -> bool:
    for slot in range(start_slot, end_slot):
        compulsory_count, elective_count = slot_usage.get((subject, study_year, slot), (0, 0))
        if is_compulsory:
            if compulsory_count >= 1 or elective_count > 0:
                return False
        else:
            if compulsory_count > 0 or elective_count >= 2:
                return False
    return True


def add_cohort_slot_usage(
    slot_usage: dict[tuple[str, int, int], tuple[int, int]],
    subject: str,
    study_year: int,
    is_compulsory: bool,
    start_slot: int,
    end_slot: int,
) -> None:
    for slot in range(start_slot, end_slot):
        key = (subject, study_year, slot)
        compulsory_count, elective_count = slot_usage.get(key, (0, 0))
        if is_compulsory:
            slot_usage[key] = (compulsory_count + 1, elective_count)
        else:
            slot_usage[key] = (compulsory_count, elective_count + 1)


def assign_balanced_course_attributes(
    lecture_slots: list[dict[str, int]],
    rng: random.Random,
) -> list[tuple[str, int, bool]]:
    num_lectures = len(lecture_slots)
    subject_counts = Counter(balanced_values(SUBJECTS, num_lectures, rng))
    year_counts = Counter(balanced_values(STUDY_YEARS, num_lectures, rng))
    course_type_counts = Counter(balanced_course_type_flags(num_lectures, rng))

    for _ in range(200):
        remaining_subjects = Counter(subject_counts)
        remaining_years = Counter(year_counts)
        remaining_types = Counter(course_type_counts)
        assignments: list[tuple[str, int, bool] | None] = [None] * num_lectures
        slot_usage: dict[tuple[str, int, int], tuple[int, int]] = {}
        order = list(range(num_lectures))
        rng.shuffle(order)
        order.sort(
            key=lambda index: (
                -(lecture_slots[index]["end_slot"] - lecture_slots[index]["start_slot"]),
                lecture_slots[index]["start_slot"],
            )
        )

        success = True
        for index in order:
            lecture_slot = lecture_slots[index]
            start_slot = lecture_slot["start_slot"]
            end_slot = lecture_slot["end_slot"]
            candidates: list[tuple[float, str, int, bool]] = []

            for subject, subject_count in remaining_subjects.items():
                if subject_count <= 0:
                    continue
                for study_year, year_count in remaining_years.items():
                    if year_count <= 0:
                        continue
                    for is_compulsory, type_count in remaining_types.items():
                        if type_count <= 0:
                            continue
                        if not cohort_slot_is_feasible(
                            slot_usage,
                            subject,
                            study_year,
                            is_compulsory,
                            start_slot,
                            end_slot,
                        ):
                            continue

                        score = (
                            4.0 * remaining_subjects[subject]
                            + 3.0 * remaining_years[study_year]
                            + 2.0 * remaining_types[is_compulsory]
                            + rng.random()
                        )
                        candidates.append((score, subject, study_year, is_compulsory))

            if not candidates:
                success = False
                break

            _, subject, study_year, is_compulsory = max(candidates, key=lambda item: item[0])
            assignments[index] = (subject, study_year, is_compulsory)
            remaining_subjects[subject] -= 1
            remaining_years[study_year] -= 1
            remaining_types[is_compulsory] -= 1
            add_cohort_slot_usage(
                slot_usage,
                subject,
                study_year,
                is_compulsory,
                start_slot,
                end_slot,
            )

        if success and all(assignment is not None for assignment in assignments):
            return [assignment for assignment in assignments if assignment is not None]

    raise RuntimeError("Failed to assign balanced lecture attributes under cohort overlap rules.")


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

    lecture_slots: list[dict[str, int]] = []
    for bin_info in bins:
        day = int(bin_info["day"])
        hall_id = int(bin_info["hall_id"])
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
            lecture_slots.append(
                {
                    "hall_id": hall_id,
                    "day": day,
                    "start_slot_in_day": start_slot_in_day,
                    "duration": duration,
                    "start_slot": start_slot,
                    "end_slot": end_slot,
                }
            )
            current += duration + gaps[index + 1]

    attribute_assignments = assign_balanced_course_attributes(lecture_slots, rng)

    lectures: list[Lecture] = []
    for lecture_id, (lecture_slot, assignment) in enumerate(zip(lecture_slots, attribute_assignments, strict=True)):
        subject, study_year, is_compulsory = assignment
        lectures.append(
            Lecture(
                lecture_id=lecture_id,
                name=f"L{lecture_id + 1}",
                subject=subject,
                study_year=study_year,
                is_compulsory=is_compulsory,
                day=lecture_slot["day"],
                start_slot_in_day=lecture_slot["start_slot_in_day"],
                duration=lecture_slot["duration"],
                start_slot=lecture_slot["start_slot"],
                end_slot=lecture_slot["end_slot"],
                students=0,
                hidden_hall=lecture_slot["hall_id"],
            )
        )
    lectures.sort(key=lambda lecture: (lecture.day, lecture.start_slot_in_day, lecture.lecture_id))
    return lectures


def build_successor_map(lectures: list[Lecture]) -> dict[int, list[Lecture]]:
    starts_by_day_slot: dict[tuple[int, int], list[Lecture]] = {}
    ends_by_day_slot: dict[tuple[int, int], list[Lecture]] = {}
    for lecture in lectures:
        starts_by_day_slot.setdefault((lecture.day, lecture.start_slot), []).append(lecture)
        ends_by_day_slot.setdefault((lecture.day, lecture.end_slot), []).append(lecture)

    successor_map: dict[int, list[Lecture]] = {lecture.lecture_id: [] for lecture in lectures}
    for key, next_lectures in starts_by_day_slot.items():
        prev_lectures = ends_by_day_slot.get(key, [])
        if not prev_lectures:
            continue
        for prev_lecture in prev_lectures:
            successor_map[prev_lecture.lecture_id].extend(next_lectures)
    return successor_map


def build_lectures_by_cohort(lectures: list[Lecture]) -> dict[tuple[str, int], list[Lecture]]:
    lectures_by_cohort: dict[tuple[str, int], list[Lecture]] = defaultdict(list)
    for lecture in lectures:
        lectures_by_cohort[(lecture.subject, lecture.study_year)].append(lecture)
    for cohort_lectures in lectures_by_cohort.values():
        cohort_lectures.sort(key=lambda lecture: (lecture.start_slot, lecture.lecture_id))
    return dict(lectures_by_cohort)


def build_lectures_starting_by_slot(lectures: list[Lecture]) -> dict[int, list[Lecture]]:
    starts_by_slot: dict[int, list[Lecture]] = defaultdict(list)
    for lecture in lectures:
        starts_by_slot[lecture.start_slot].append(lecture)
    for slot_lectures in starts_by_slot.values():
        slot_lectures.sort(key=lambda lecture: (lecture.end_slot, lecture.lecture_id))
    return dict(starts_by_slot)


def lecture_remaining_capacity(
    lecture: Lecture,
    attendance: dict[int, int],
    hall_capacities: dict[int, int],
) -> int:
    return hall_capacities[lecture.hidden_hall] - attendance[lecture.lecture_id]


def overlaps_home_cohort_lecture(
    candidate: Lecture,
    home_lectures: list[Lecture],
) -> bool:
    for home_lecture in home_lectures:
        if home_lecture.lecture_id == candidate.lecture_id:
            continue
        if home_lecture.end_slot <= candidate.start_slot:
            continue
        if home_lecture.start_slot >= candidate.end_slot:
            break
        return True
    return False


def choose_weighted_lecture(
    candidates: list[Lecture],
    attendance: dict[int, int],
    hall_capacities: dict[int, int],
    lecture_popularity: dict[int, float],
    rng: random.Random,
    score_multiplier: Callable[[Lecture], float] | None = None,
) -> Lecture | None:
    feasible_candidates: list[Lecture] = []
    weights: list[float] = []
    for lecture in candidates:
        remaining_capacity = lecture_remaining_capacity(lecture, attendance, hall_capacities)
        if remaining_capacity <= 0:
            continue
        weight = lecture_popularity[lecture.lecture_id] * (remaining_capacity ** 1.05)
        if score_multiplier is not None:
            weight *= score_multiplier(lecture)
        if weight <= 0:
            continue
        feasible_candidates.append(lecture)
        weights.append(weight)
    if not feasible_candidates:
        return None
    return rng.choices(feasible_candidates, weights=weights, k=1)[0]


def exploratory_course_weight(student_year: int, lecture: Lecture) -> float:
    year_gap = abs(student_year - lecture.study_year)
    if year_gap == 0:
        base = 0.28
    elif year_gap == 1:
        base = 0.08
    else:
        base = 0.015
    if lecture.is_compulsory:
        base *= 0.55
    return base


def estimate_cohort_sizes(
    lectures: list[Lecture],
    halls: list[Hall],
    rng: random.Random,
) -> dict[tuple[str, int], int]:
    lectures_by_cohort = build_lectures_by_cohort(lectures)
    hall_capacities = {hall.hall_id: hall.capacity for hall in halls}

    compulsory_capacity_floors = [
        min(hall_capacities[lecture.hidden_hall] for lecture in cohort_lectures if lecture.is_compulsory)
        for cohort_lectures in lectures_by_cohort.values()
        if any(lecture.is_compulsory for lecture in cohort_lectures)
    ]

    if compulsory_capacity_floors:
        baseline_size = max(
            12,
            int(round(statistics.median(compulsory_capacity_floors) * rng.uniform(0.90, 0.96))),
        )
    else:
        baseline_size = max(
            12,
            int(round(statistics.median(hall.capacity for hall in halls) * rng.uniform(0.65, 0.80))),
        )

    cohort_sizes: dict[tuple[str, int], int] = {}
    for cohort, cohort_lectures in lectures_by_cohort.items():
        compulsory_caps = [
            hall_capacities[lecture.hidden_hall]
            for lecture in cohort_lectures
            if lecture.is_compulsory
        ]
        elective_caps = [
            hall_capacities[lecture.hidden_hall]
            for lecture in cohort_lectures
            if not lecture.is_compulsory
        ]

        if compulsory_caps:
            upper_bound = max(8, int(math.floor(0.98 * min(compulsory_caps))))
            target_reference = 0.55 * baseline_size + 0.45 * upper_bound
            target = max(8, int(round(target_reference * rng.uniform(0.97, 1.03))))
            cohort_sizes[cohort] = min(upper_bound, target)
        elif elective_caps:
            upper_bound = max(8, int(math.floor(0.92 * max(elective_caps))))
            target_reference = 0.45 * baseline_size + 0.35 * upper_bound
            target = max(8, int(round(target_reference * rng.uniform(0.90, 1.08))))
            cohort_sizes[cohort] = min(upper_bound, target)
        else:
            cohort_sizes[cohort] = max(8, int(round(0.60 * baseline_size)))

    return cohort_sizes


def simulate_student_journeys(
    lectures: list[Lecture],
    halls: list[Hall],
    slots_per_day: int,
    rng: random.Random,
) -> tuple[list[Lecture], dict[tuple[int, int], int]]:
    lectures_by_cohort = build_lectures_by_cohort(lectures)
    starts_by_slot = build_lectures_starting_by_slot(lectures)
    successor_map = build_successor_map(lectures)
    hall_capacities = {hall.hall_id: hall.capacity for hall in halls}
    cohort_sizes = estimate_cohort_sizes(lectures, halls, rng)
    attendance = {lecture.lecture_id: 0 for lecture in lectures}
    common_students: dict[tuple[int, int], int] = {}
    lecture_popularity = {
        lecture.lecture_id: (
            rng.uniform(0.98, 1.03)
            if lecture.is_compulsory
            else rng.uniform(0.85, 1.20)
        )
        for lecture in lectures
    }

    students = [
        (subject, study_year)
        for (subject, study_year), cohort_size in cohort_sizes.items()
        for _ in range(cohort_size)
    ]
    rng.shuffle(students)

    for student_subject, student_year in students:
        home_lectures = lectures_by_cohort.get((student_subject, student_year), [])
        compulsory_attendance_rate = min(0.998, max(0.95, rng.gauss(0.988, 0.006)))
        elective_attendance_rate = min(0.94, max(0.58, rng.gauss(0.79, 0.08)))
        previous_year_rate = min(0.16, max(0.01, rng.gauss(0.06, 0.02)))
        other_topic_rate = min(0.03, max(0.0, rng.gauss(0.008, 0.004)))

        attended_lectures: list[Lecture] = []
        slot = 0
        while slot < slots_per_day:
            starting_lectures = starts_by_slot.get(slot, [])
            if not starting_lectures:
                slot += 1
                continue

            available_lectures = [
                lecture
                for lecture in starting_lectures
                if lecture_remaining_capacity(lecture, attendance, hall_capacities) > 0
            ]
            if not available_lectures:
                slot += 1
                continue

            home_compulsory = [
                lecture
                for lecture in available_lectures
                if lecture.subject == student_subject
                and lecture.study_year == student_year
                and lecture.is_compulsory
            ]
            if home_compulsory:
                chosen_lecture = home_compulsory[0]
                if rng.random() < compulsory_attendance_rate:
                    attendance[chosen_lecture.lecture_id] += 1
                    attended_lectures.append(chosen_lecture)
                    slot = chosen_lecture.end_slot
                else:
                    slot += 1
                continue

            home_electives = [
                lecture
                for lecture in available_lectures
                if lecture.subject == student_subject
                and lecture.study_year == student_year
                and not lecture.is_compulsory
            ]
            if home_electives:
                if rng.random() < elective_attendance_rate:
                    chosen_lecture = choose_weighted_lecture(
                        candidates=home_electives,
                        attendance=attendance,
                        hall_capacities=hall_capacities,
                        lecture_popularity=lecture_popularity,
                        rng=rng,
                    )
                    if chosen_lecture is not None:
                        attendance[chosen_lecture.lecture_id] += 1
                        attended_lectures.append(chosen_lecture)
                        slot = chosen_lecture.end_slot
                        continue
                slot += 1
                continue

            previous_year_candidates = [
                lecture
                for lecture in available_lectures
                if lecture.subject == student_subject
                and lecture.study_year == student_year - 1
                and not lecture.is_compulsory
                and not overlaps_home_cohort_lecture(lecture, home_lectures)
            ]
            if previous_year_candidates and rng.random() < previous_year_rate:
                chosen_lecture = choose_weighted_lecture(
                    candidates=previous_year_candidates,
                    attendance=attendance,
                    hall_capacities=hall_capacities,
                    lecture_popularity=lecture_popularity,
                    rng=rng,
                )
                if chosen_lecture is not None:
                    attendance[chosen_lecture.lecture_id] += 1
                    attended_lectures.append(chosen_lecture)
                    slot = chosen_lecture.end_slot
                    continue

            other_topic_candidates = [
                lecture
                for lecture in available_lectures
                if lecture.subject != student_subject
                and not lecture.is_compulsory
                and not overlaps_home_cohort_lecture(lecture, home_lectures)
            ]
            if other_topic_candidates and rng.random() < other_topic_rate:
                chosen_lecture = choose_weighted_lecture(
                    candidates=other_topic_candidates,
                    attendance=attendance,
                    hall_capacities=hall_capacities,
                    lecture_popularity=lecture_popularity,
                    rng=rng,
                    score_multiplier=lambda lecture: exploratory_course_weight(student_year, lecture),
                )
                if chosen_lecture is not None:
                    attendance[chosen_lecture.lecture_id] += 1
                    attended_lectures.append(chosen_lecture)
                    slot = chosen_lecture.end_slot
                    continue

            slot += 1

        for current_lecture, next_lecture in zip(attended_lectures, attended_lectures[1:], strict=False):
            if current_lecture.day == next_lecture.day and current_lecture.end_slot == next_lecture.start_slot:
                common_students[(current_lecture.lecture_id, next_lecture.lecture_id)] = (
                    common_students.get((current_lecture.lecture_id, next_lecture.lecture_id), 0) + 1
                )

    updated_lectures = [
        replace(lecture, students=attendance[lecture.lecture_id])
        for lecture in lectures
    ]

    if not common_students:
        weighted_pairs = [
            (
                prev_lecture.lecture_id,
                next_lecture.lecture_id,
                (
                    max(1, attendance[prev_lecture.lecture_id] + attendance[next_lecture.lecture_id])
                ),
            )
            for prev_lecture in lectures
            for next_lecture in successor_map.get(prev_lecture.lecture_id, [])
        ]
        weighted_pairs = [pair for pair in weighted_pairs if pair[2] > 0]
        if weighted_pairs:
            lecture_id_1, lecture_id_2, _ = rng.choices(
                weighted_pairs,
                weights=[pair[2] for pair in weighted_pairs],
                k=1,
            )[0]
            common_students[(lecture_id_1, lecture_id_2)] = 1

    return updated_lectures, common_students


def build_instance(
    num_halls: int,
    slots_per_day: int,
    seed: int,
    density: float,
) -> Instance:
    rng = random.Random(seed)
    halls = generate_halls(num_halls, rng)
    distances = generate_distances(halls)
    lectures = generate_lectures(halls, slots_per_day, density, rng)
    lectures, common_students = simulate_student_journeys(
        lectures=lectures,
        halls=halls,
        slots_per_day=slots_per_day,
        rng=rng,
    )
    compatibility = {
        lecture.lecture_id: [hall.hall_id for hall in halls if hall.capacity >= lecture.students]
        for lecture in lectures
    }
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
        halls=halls,
        lectures=lectures,
        distances=distances,
        common_students=common_students,
        compatibility=compatibility,
        active_lectures_by_slot=active_lectures_by_slot,
    )


def count_decomposition_connected_components(instance: Instance) -> int:
    adjacency: dict[int, set[int]] = {
        lecture.lecture_id: set() for lecture in instance.lectures
    }

    # Successor arcs induce objective coupling.
    for lecture_id_1, lecture_id_2 in instance.common_students:
        adjacency[lecture_id_1].add(lecture_id_2)
        adjacency[lecture_id_2].add(lecture_id_1)

    # Overlap edges induce room-competition coupling.
    for active_lectures in instance.active_lectures_by_slot.values():
        if len(active_lectures) <= 1:
            continue
        for index, lecture_id_1 in enumerate(active_lectures):
            for lecture_id_2 in active_lectures[index + 1 :]:
                adjacency[lecture_id_1].add(lecture_id_2)
                adjacency[lecture_id_2].add(lecture_id_1)

    visited: set[int] = set()
    component_count = 0
    for lecture in instance.lectures:
        lecture_id = lecture.lecture_id
        if lecture_id in visited:
            continue

        component_count += 1
        stack = [lecture_id]
        visited.add(lecture_id)
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)

    return component_count


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
                "subject": lecture.subject,
                "study_year": lecture.study_year,
                "course_type": "compulsory" if lecture.is_compulsory else "elective",
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


def build_gurobi_linearized_model(
    instance: Instance,
    cuts: int,
    time_limit: float | None,
    verbose: bool,
    threads: int | None = None,
) -> tuple[Model, dict[tuple[int, int], Any], dict[tuple[int, int], Any], int]:
    thread_limit = gurobi_thread_limit() if threads is None else threads
    model = Model("lecture_hall_linearized")
    model.Params.OutputFlag = 1 if verbose else 0
    if time_limit is not None:
        model.Params.TimeLimit = time_limit
    model.Params.Threads = thread_limit
    model.Params.NumericFocus = 2
    model.Params.ScaleFlag = 2
    model.Params.ObjScale = -0.5

    x: dict[tuple[int, int], Any] = {}
    z: dict[tuple[int, int], Any] = {}

    for lecture in instance.lectures:
        for hall_id in instance.compatibility[lecture.lecture_id]:
            x[(lecture.lecture_id, hall_id)] = model.addVar(
                vtype=GRB.BINARY,
                name=f"x_{lecture.lecture_id}_{hall_id}",
            )

    for lecture_id_1, lecture_id_2 in instance.common_students:
        z[(lecture_id_1, lecture_id_2)] = model.addVar(
            lb=0.0,
            vtype=GRB.CONTINUOUS,
            name=f"z_{lecture_id_1}_{lecture_id_2}",
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

    if cuts == 0:
        for lecture_id_1, lecture_id_2 in instance.common_students:
            for hall_id_1 in instance.compatibility[lecture_id_1]:
                for hall_id_2 in instance.compatibility[lecture_id_2]:
                    model.addConstr(
                        z[(lecture_id_1, lecture_id_2)]
                        >= instance.distances[hall_id_1][hall_id_2]
                        * (x[(lecture_id_1, hall_id_1)] + x[(lecture_id_2, hall_id_2)] - 1),
                        name=f"link_{lecture_id_1}_{lecture_id_2}_{hall_id_1}_{hall_id_2}",
                    )

    if cuts == 1:
        for lecture_id_1, lecture_id_2 in instance.common_students:
            halls_1 = instance.compatibility[lecture_id_1]
            halls_2 = instance.compatibility[lecture_id_2]

            for hall_id_1 in halls_1:
                for hall_id_2 in halls_2:
                    threshold_distance = instance.distances[hall_id_1][hall_id_2]
                    farther_halls = [
                        hall_id
                        for hall_id in halls_2
                        if instance.distances[hall_id_1][hall_id] >= threshold_distance
                    ]
                    model.addConstr(
                        z[(lecture_id_1, lecture_id_2)]
                        >= threshold_distance
                        * (
                            x[(lecture_id_1, hall_id_1)]
                            - 1
                            + quicksum(x[(lecture_id_2, hall_id)] for hall_id in farther_halls)
                        ),
                        name=f"strong_{lecture_id_1}_{lecture_id_2}_{hall_id_1}_{hall_id_2}",
                    )

    # Keep the pair weights in the objective to improve matrix scaling.
    objective_terms = [
        common_count * z[(lecture_id_1, lecture_id_2)]
        for (lecture_id_1, lecture_id_2), common_count in instance.common_students.items()
    ]
    model.setObjective(quicksum(objective_terms), GRB.MINIMIZE)
    return model, x, z, thread_limit


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

        if model.Status == GRB.INTERRUPTED:
            raise KeyboardInterrupt("Solver interrupted by user")

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


def solve_gurobi_linearized(
    instance: Instance,
    time_limit: float,
    cuts: int = 1,
    verbose: bool = True,
) -> dict[str, Any]:
    wall_start = time.perf_counter()
    try:
        model, x, _, thread_limit = build_gurobi_linearized_model(
            instance=instance,
            cuts=cuts,
            time_limit=time_limit,
            verbose=verbose,
        )
        model.optimize()

        if model.Status == GRB.INTERRUPTED:
            raise KeyboardInterrupt("Solver interrupted by user")

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
            "cuts_mode": cuts,
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
            "cuts_mode": cuts,
            "error": str(error),
            "solution": None,
        }


def solve_gurobi_linearized_root(
    instance: Instance,
    time_limit: float,
    cuts: int = 1,
    verbose: bool = True,
) -> dict[str, Any]:
    wall_start = time.perf_counter()
    try:
        model, _, _, thread_limit = build_gurobi_linearized_model(
            instance=instance,
            cuts=cuts,
            time_limit=time_limit,
            verbose=verbose,
        )
        model._root_bound = None
        model._terminated_after_root = False

        def callback(cb_model: Model, where: int) -> None:
            if where != GRB.Callback.MIP:
                return

            node_count = cb_model.cbGet(GRB.Callback.MIP_NODCNT)
            obj_bound = cb_model.cbGet(GRB.Callback.MIP_OBJBND)
            if node_count == 0:
                if cb_model._root_bound is None or obj_bound > cb_model._root_bound:
                    cb_model._root_bound = obj_bound
            elif not cb_model._terminated_after_root:
                cb_model._terminated_after_root = True
                cb_model.terminate()

        model.optimize(callback)

        wall_seconds = time.perf_counter() - wall_start
        root_bound = safe_float(model._root_bound)
        if root_bound is None:
            root_bound = safe_float(model.ObjBound)

        if model._terminated_after_root:
            status = "ROOT_LIMIT"
        else:
            status = status_name_from_gurobi(model.Status)

        return {
            "solver_family": "GUROBI",
            "formulation": "linearized_root",
            "status": status,
            "objective_value": None,
            "lower_bound": root_bound,
            "wall_clock_seconds": wall_seconds,
            "solver_runtime_seconds": safe_float(model.Runtime),
            "mip_gap": None,
            "threads": thread_limit,
            "cuts_mode": cuts,
            "error": None,
            "solution": None,
        }
    except GurobiError as error:
        return {
            "solver_family": "GUROBI",
            "formulation": "linearized_root",
            "status": "ERROR",
            "objective_value": None,
            "lower_bound": None,
            "wall_clock_seconds": time.perf_counter() - wall_start,
            "solver_runtime_seconds": None,
            "mip_gap": None,
            "threads": gurobi_thread_limit(),
            "cuts_mode": cuts,
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
    solver.parameters.catch_sigint_signal = False
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
    cuts_mode: int,
) -> list[dict[str, Any]]:
    total_lecture_length = sum(lecture.duration for lecture in instance.lectures)
    sizes = [lecture.students for lecture in instance.lectures]
    capacities = [hall.capacity for hall in instance.halls]
    common_values = list(instance.common_students.values())
    decomposition_connected_components = count_decomposition_connected_components(instance)
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

    valid_lower_bounds = [
        float(result["lower_bound"])
        for result in results
        if result.get("lower_bound") is not None and math.isfinite(float(result["lower_bound"]))
    ]
    best_global_lower_bound = max(valid_lower_bounds) if valid_lower_bounds else None

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

        global_gap = None
        if obj is not None and best_global_lower_bound is not None:
            if obj != 0:
                global_gap = max(0.0, float(obj - best_global_lower_bound) / abs(float(obj)))
            else:
                global_gap = 0.0 if float(best_global_lower_bound) >= 0 else float("inf")

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
                "time_limit_seconds": time_limit,
                "linearized_cuts": cuts_mode,
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
                "decomposition_connected_components": decomposition_connected_components,
                "avg_common_students": (
                    sum(common_values) / len(common_values) if common_values else 0.0
                ),
                "total_common_students_weight": sum(common_values),
                "solver_family": result["solver_family"],
                "formulation": result["formulation"],
                "status": result["status"],
                "objective_value": result["objective_value"],
                "lower_bound": result["lower_bound"],
                "best_global_lower_bound": best_global_lower_bound,
                "wall_clock_seconds": result["wall_clock_seconds"],
                "solver_runtime_seconds": result["solver_runtime_seconds"],
                "mip_gap": result["mip_gap"],
                "optimality_gap": gap,
                "global opt gap": global_gap,
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
                "subject": lecture.subject,
                "study_year": lecture.study_year,
                "course_type": "compulsory" if lecture.is_compulsory else "elective",
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
    cuts_mode: int,
) -> dict[str, Any]:
    return {
        "experiment": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": sys.version,
            "time_limit_seconds": time_limit,
            "linearized_cuts": cuts_mode,
        },
        "instance": instance_to_json_dict(instance),
        "results_summary": summary_rows,
        "solutions": results,
    }


def build_instance_json_payload(
    instance: Instance,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    return {
        "export_type": "instance_only",
        "generation": {
            "generated_at": generated_at.isoformat(),
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "command_line": sys.argv,
        },
        "instance": instance_to_json_dict(instance),
    }


def write_excel(
    output_path: Path,
    summary_rows: list[dict[str, Any]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summary_rows)

    if output_path.exists():
        workbook = load_workbook(output_path)
    else:
        workbook = Workbook()
        default_sheet = workbook.active
        if default_sheet and sheet_is_empty(default_sheet):
            workbook.remove(default_sheet)

    append_summary_sheet(workbook, summary_df)
    workbook.save(output_path)


def write_json(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def render_text_table(
    headers: list[str],
    rows: list[list[Any]],
    right_align_columns: set[int] | None = None,
) -> str:
    right_align_columns = right_align_columns or set()
    string_rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in string_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def format_row(row: list[str]) -> str:
        formatted_cells = []
        for index, cell in enumerate(row):
            if index in right_align_columns:
                formatted_cells.append(cell.rjust(widths[index]))
            else:
                formatted_cells.append(cell.ljust(widths[index]))
        return "  ".join(formatted_cells)

    lines = [format_row(headers), format_row(["-" * width for width in widths])]
    lines.extend(format_row(row) for row in string_rows)
    return "\n".join(lines)


def print_instance_console_view(instance: Instance, json_path: Path) -> None:
    hall_map = {hall.hall_id: hall for hall in instance.halls}
    lecture_map = {lecture.lecture_id: lecture for lecture in instance.lectures}
    total_common_students = sum(instance.common_students.values())
    candidate_successors = sum(
        1
        for lecture in instance.lectures
        for follower in instance.lectures
        if lecture.day == follower.day and lecture.end_slot == follower.start_slot
    )
    min_compatibility = min(len(halls) for halls in instance.compatibility.values()) if instance.compatibility else 0
    max_distance = max(max(row) for row in instance.distances) if instance.distances else 0

    print("=" * 88)
    print(f"Generated instance input | seed={instance.seed}")
    print("=" * 88)
    print(
        "Overview: "
        f"halls={instance.num_halls}, lectures={len(instance.lectures)}, "
        f"slots/day={instance.slots_per_day}, density={instance.density_actual:.3f} "
        f"(target {instance.density_target:.3f})"
    )
    print(
        "Structure: "
        f"successor pairs={len(instance.common_students)}/{candidate_successors}, "
        f"total common students={total_common_students}, "
        f"min compatible halls per lecture={min_compatibility}, max distance={max_distance}"
    )
    print(f"JSON written to: {json_path}")
    print("")

    hall_rows = [
        [
            hall.hall_id,
            hall.name,
            hall.capacity,
            f"{hall.x:.3f}",
            f"{hall.y:.3f}",
        ]
        for hall in instance.halls
    ]
    print("Halls")
    print(
        render_text_table(
            headers=["id", "name", "capacity", "x", "y"],
            rows=hall_rows,
            right_align_columns={0, 2, 3, 4},
        )
    )
    print("")

    lecture_rows = []
    for lecture in instance.lectures:
        slot_end_in_day = lecture.start_slot_in_day + lecture.duration - 1
        compatible_halls = ",".join(
            hall_map[hall_id].name for hall_id in instance.compatibility[lecture.lecture_id]
        )
        lecture_rows.append(
            [
                lecture.lecture_id,
                lecture.name,
                lecture.subject,
                f"Y{lecture.study_year}",
                "compulsory" if lecture.is_compulsory else "elective",
                lecture.day + 1,
                f"{lecture.start_slot_in_day}-{slot_end_in_day}",
                lecture.duration,
                lecture.students,
                compatible_halls,
            ]
        )
    print("Lectures")
    print(
        render_text_table(
            headers=["id", "name", "subject", "year", "type", "day", "slots", "dur", "students", "compatible"],
            rows=lecture_rows,
            right_align_columns={0, 5, 7, 8},
        )
    )
    print("")

    print("Successor pairs")
    if instance.common_students:
        successor_rows = [
            [
                lecture_id_1,
                lecture_map[lecture_id_1].name,
                lecture_id_2,
                lecture_map[lecture_id_2].name,
                common_count,
            ]
            for (lecture_id_1, lecture_id_2), common_count in sorted(instance.common_students.items())
        ]
        print(
            render_text_table(
                headers=["from", "from_name", "to", "to_name", "common_students"],
                rows=successor_rows,
                right_align_columns={0, 2, 4},
            )
        )
    else:
        print("(none)")
    print("")

    distance_rows = []
    hall_headers = ["from/to"] + [hall.name for hall in instance.halls]
    for hall in instance.halls:
        distance_rows.append([hall.name] + instance.distances[hall.hall_id])
    print("Distance matrix")
    print(
        render_text_table(
            headers=hall_headers,
            rows=distance_rows,
            right_align_columns=set(range(1, len(hall_headers))),
        )
    )


def print_console_summary(output_path: Path, summary_rows: list[dict[str, Any]]) -> None:
    print(f"Results written to: {output_path}")
    print("")
    for row in summary_rows:
        gap_str = str(row['optimality_gap']) if row['optimality_gap'] is None else f"{row['optimality_gap']:.2%}"
        global_gap_str = (
            str(row['global opt gap'])
            if row['global opt gap'] is None
            else f"{row['global opt gap']:.2%}"
        )
        print(
            f"{row['solver_family']:>8} | {row['formulation']:<16} | "
            f"status={row['status']:<12} | obj={row['objective_value']} | "
            f"lb={row['lower_bound']} | gap={gap_str} | global={global_gap_str} | "
            f"wall={row['wall_clock_seconds']:.3f}s"
        )


def main() -> None:
    args = parse_args()
    try:
        seeds = parse_seed_range(args.seed)
    except ValueError as e:
        raise SystemExit(str(e))
        
    output_path = ensure_output_path(args.output, args.seed, args.num_halls)

    started_at = dt.datetime.now().astimezone()
    base_run_tag = started_at.strftime("%Y%m%d_%H%M%S")
    
    all_summary_rows = []

    for index, seed in enumerate(seeds):
        run_tag = f"{base_run_tag}_seed{seed}"
        instance = build_instance(
            num_halls=args.num_halls,
            slots_per_day=args.slots_per_day,
            seed=seed,
            density=args.density,
        )

        if args.instance_only:
            generated_at = dt.datetime.now().astimezone()
            json_path = build_instance_json_path(output_path, run_tag)
            payload = build_instance_json_payload(instance=instance, generated_at=generated_at)
            write_json(json_path, payload)
            if index > 0:
                print("")
            print_instance_console_view(instance, json_path)
            continue

        if args.model is None:
            results = [
                solve_gurobi_quadratic(instance, args.time_limit, verbose=not args.quiet),
                solve_gurobi_linearized(
                    instance,
                    args.time_limit,
                    cuts=args.cuts,
                    verbose=not args.quiet,
                ),
                solve_cp_sat(instance, args.time_limit, verbose=not args.quiet),
            ]
        elif args.model == "MIPQ":
            results = [
                solve_gurobi_quadratic(instance, args.time_limit, verbose=not args.quiet),
            ]
        elif args.model == "MIP":
            results = [
                solve_gurobi_linearized(
                    instance,
                    args.time_limit,
                    cuts=args.cuts,
                    verbose=not args.quiet,
                ),
            ]
        elif args.model == "CP":
            results = [
                solve_cp_sat(instance, args.time_limit, verbose=not args.quiet),
            ]
        else:
            results = [
                solve_gurobi_linearized_root(
                    instance,
                    args.time_limit,
                    cuts=args.cuts,
                    verbose=not args.quiet,
                ),
            ]

        finished_at = dt.datetime.now().astimezone()
        summary_rows = build_summary_rows(
            instance=instance,
            results=results,
            started_at=started_at,
            finished_at=finished_at,
            time_limit=args.time_limit,
            cuts_mode=args.cuts,
        )
        all_summary_rows.extend(summary_rows)
        write_excel(output_path, summary_rows)
        
        if args.save_json:
            json_path = build_json_path(output_path, run_tag)
            payload = build_json_payload(
                instance=instance,
                results=results,
                summary_rows=summary_rows,
                started_at=started_at,
                finished_at=finished_at,
                time_limit=args.time_limit,
                cuts_mode=args.cuts,
            )
            write_json(json_path, payload)
            print(f"JSON written to: {json_path}")

    if not args.instance_only:
        print_console_summary(output_path, all_summary_rows)


if __name__ == "__main__":
    main()
