#!/usr/bin/env python3
"""Synthetic lecture-hall instance generator."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
import math
import os
import platform
import random
import statistics
from typing import Any, Callable

from ortools.sat.python import cp_model

from lecture_hall_instance_builder import build_instance_from_components
from lecture_hall_models import Hall, Instance, Lecture


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
            candidates = [bin_info for bin_info in bins if bin_info["remaining"] >= duration]
            if not candidates:
                success = False
                break
            best_slack = min(bin_info["remaining"] - duration for bin_info in candidates)
            shortlist = [
                bin_info for bin_info in candidates if bin_info["remaining"] - duration <= best_slack + 1
            ]
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


def build_lecture_slot_coverage(lecture_slots: list[dict[str, int]]) -> dict[int, list[int]]:
    slot_coverage: dict[int, list[int]] = defaultdict(list)
    for lecture_index, lecture_slot in enumerate(lecture_slots):
        for slot in range(lecture_slot["start_slot"], lecture_slot["end_slot"]):
            slot_coverage[slot].append(lecture_index)
    return dict(slot_coverage)


def assign_course_type_flags_exact(
    lecture_slots: list[dict[str, int]],
    slot_coverage: dict[int, list[int]],
    compulsory_count: int,
    rng: random.Random,
) -> list[bool] | None:
    if compulsory_count < 0 or compulsory_count > len(lecture_slots):
        return None

    num_cohorts = len(SUBJECTS) * len(STUDY_YEARS)
    model = cp_model.CpModel()
    compulsory_vars = [model.NewBoolVar(f"compulsory_l{lecture_index}") for lecture_index in range(len(lecture_slots))]
    model.Add(sum(compulsory_vars) == compulsory_count)

    for lecture_indices in slot_coverage.values():
        max_compulsory_lectures = 2 * num_cohorts - len(lecture_indices)
        if max_compulsory_lectures < 0:
            return None
        model.Add(sum(compulsory_vars[lecture_index] for lecture_index in lecture_indices) <= max_compulsory_lectures)

    weighted_cost_terms = []
    for lecture_index, lecture_slot in enumerate(lecture_slots):
        duration = lecture_slot["end_slot"] - lecture_slot["start_slot"]
        congestion = sum(
            len(slot_coverage[slot])
            for slot in range(lecture_slot["start_slot"], lecture_slot["end_slot"])
        )
        tie_breaker = rng.randint(0, 9)
        weighted_cost_terms.append((1000 * duration + 10 * congestion + tie_breaker) * compulsory_vars[lecture_index])
    model.Minimize(sum(weighted_cost_terms))

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = gurobi_thread_limit()
    solver.parameters.random_seed = rng.randint(1, 2_000_000_000)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    return [solver.BooleanValue(var) for var in compulsory_vars]


def assign_subject_year_pairs_exact(
    lecture_slots: list[dict[str, int]],
    slot_coverage: dict[int, list[int]],
    compulsory_flags: list[bool],
    subject_counts: Counter[str],
    year_counts: Counter[int],
    rng: random.Random,
) -> list[tuple[str, int]] | None:
    model = cp_model.CpModel()
    assignment_vars: dict[tuple[int, str, int], cp_model.IntVar] = {}
    subject_vars: dict[str, list[cp_model.IntVar]] = {subject: [] for subject in SUBJECTS}
    year_vars: dict[int, list[cp_model.IntVar]] = {study_year: [] for study_year in STUDY_YEARS}

    lecture_order = sorted(
        range(len(lecture_slots)),
        key=lambda lecture_index: (
            -sum(
                len(slot_coverage[slot])
                for slot in range(
                    lecture_slots[lecture_index]["start_slot"],
                    lecture_slots[lecture_index]["end_slot"],
                )
            ),
            -(lecture_slots[lecture_index]["end_slot"] - lecture_slots[lecture_index]["start_slot"]),
            lecture_slots[lecture_index]["start_slot"],
        ),
    )
    ordered_decision_vars: list[cp_model.IntVar] = []

    for lecture_index in range(len(lecture_slots)):
        lecture_choice_vars: list[cp_model.IntVar] = []
        shuffled_subjects = list(SUBJECTS)
        shuffled_years = list(STUDY_YEARS)
        rng.shuffle(shuffled_subjects)
        rng.shuffle(shuffled_years)
        for subject in shuffled_subjects:
            for study_year in shuffled_years:
                var = model.NewBoolVar(f"cohort_l{lecture_index}_{subject}_{study_year}")
                assignment_vars[(lecture_index, subject, study_year)] = var
                lecture_choice_vars.append(var)
                subject_vars[subject].append(var)
                year_vars[study_year].append(var)
        model.AddExactlyOne(lecture_choice_vars)

    for lecture_index in lecture_order:
        for subject in SUBJECTS:
            for study_year in STUDY_YEARS:
                ordered_decision_vars.append(assignment_vars[(lecture_index, subject, study_year)])
    model.AddDecisionStrategy(
        ordered_decision_vars,
        cp_model.CHOOSE_FIRST,
        cp_model.SELECT_MAX_VALUE,
    )

    for subject in SUBJECTS:
        model.Add(sum(subject_vars[subject]) == subject_counts.get(subject, 0))
    for study_year in STUDY_YEARS:
        model.Add(sum(year_vars[study_year]) == year_counts.get(study_year, 0))

    for lecture_indices in slot_coverage.values():
        for subject in SUBJECTS:
            for study_year in STUDY_YEARS:
                model.Add(
                    sum(
                        (2 if compulsory_flags[lecture_index] else 1)
                        * assignment_vars[(lecture_index, subject, study_year)]
                        for lecture_index in lecture_indices
                    )
                    <= 2
                )

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = gurobi_thread_limit()
    solver.parameters.random_seed = rng.randint(1, 2_000_000_000)
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    assignments: list[tuple[str, int]] = []
    for lecture_index in range(len(lecture_slots)):
        selected_assignment: tuple[str, int] | None = None
        for subject in SUBJECTS:
            for study_year in STUDY_YEARS:
                if solver.BooleanValue(assignment_vars[(lecture_index, subject, study_year)]):
                    selected_assignment = (subject, study_year)
                    break
            if selected_assignment is not None:
                break
        if selected_assignment is None:
            return None
        assignments.append(selected_assignment)

    return assignments


def assign_balanced_course_attributes_exact(
    lecture_slots: list[dict[str, int]],
    subject_counts: Counter[str],
    year_counts: Counter[int],
    course_type_counts: Counter[bool],
    rng: random.Random,
) -> list[tuple[str, int, bool]] | None:
    if not lecture_slots:
        return []

    target_compulsory_count = course_type_counts.get(True, 0)
    slot_coverage = build_lecture_slot_coverage(lecture_slots)

    for compulsory_count in range(target_compulsory_count, -1, -1):
        compulsory_flags = assign_course_type_flags_exact(
            lecture_slots=lecture_slots,
            slot_coverage=slot_coverage,
            compulsory_count=compulsory_count,
            rng=rng,
        )
        if compulsory_flags is None:
            continue

        subject_year_assignments = assign_subject_year_pairs_exact(
            lecture_slots=lecture_slots,
            slot_coverage=slot_coverage,
            compulsory_flags=compulsory_flags,
            subject_counts=subject_counts,
            year_counts=year_counts,
            rng=rng,
        )
        if subject_year_assignments is None:
            continue

        return [
            (subject, study_year, compulsory_flags[lecture_index])
            for lecture_index, (subject, study_year) in enumerate(subject_year_assignments)
        ]

    return None


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

    exact_assignments = assign_balanced_course_attributes_exact(
        lecture_slots=lecture_slots,
        subject_counts=subject_counts,
        year_counts=year_counts,
        course_type_counts=course_type_counts,
        rng=rng,
    )
    if exact_assignments is not None:
        return exact_assignments

    raise RuntimeError("Failed to assign balanced lecture attributes under cohort overlap rules.")


def max_simultaneous_lectures_under_cohort_rules() -> int:
    return 2 * len(SUBJECTS) * len(STUDY_YEARS)


def build_lecture_slots_from_bins(
    bins: list[dict[str, Any]],
    slots_per_day: int,
    rng: random.Random,
) -> list[dict[str, int]]:
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
    return lecture_slots


def max_slot_coverage(lecture_slots: list[dict[str, int]]) -> int:
    slot_coverage = build_lecture_slot_coverage(lecture_slots)
    return max((len(lecture_indices) for lecture_indices in slot_coverage.values()), default=0)


def generate_lectures(
    halls: list[Hall],
    slots_per_day: int,
    density: float,
    rng: random.Random,
) -> list[Lecture]:
    total_capacity = len(halls) * DAYS_PER_WEEK * slots_per_day
    target_busy_slots = max(2, min(total_capacity, int(round(density * total_capacity))))
    max_simultaneous_lectures = max_simultaneous_lectures_under_cohort_rules()
    max_busy_slots_under_cohort_rules = max_simultaneous_lectures * DAYS_PER_WEEK * slots_per_day
    if target_busy_slots > max_busy_slots_under_cohort_rules:
        max_density = max_busy_slots_under_cohort_rules / total_capacity if total_capacity else 0.0
        raise ValueError(
            "Requested density "
            f"{density:.3f} with {len(halls)} halls implies {target_busy_slots} lecture-slots, "
            "but the current cohort overlap rules with "
            f"{len(SUBJECTS) * len(STUDY_YEARS)} subject-year cohorts allow at most "
            f"{max_busy_slots_under_cohort_rules} lecture-slots in total "
            f"({max_simultaneous_lectures} simultaneous lectures per slot, "
            f"maximum feasible density {max_density:.3f}). "
            "Reduce the density or increase the number of cohorts."
        )
    durations = duration_list_for_total(target_busy_slots, rng)
    best_max_coverage = 0
    last_assignment_error: RuntimeError | None = None
    for _ in range(100):
        bins = assign_durations_to_bins(durations, len(halls), DAYS_PER_WEEK, slots_per_day, rng)
        lecture_slots = build_lecture_slots_from_bins(bins, slots_per_day, rng)
        current_max_coverage = max_slot_coverage(lecture_slots)
        best_max_coverage = max(best_max_coverage, current_max_coverage)
        if current_max_coverage > max_simultaneous_lectures:
            continue
        try:
            attribute_assignments = assign_balanced_course_attributes(lecture_slots, rng)
            break
        except RuntimeError as error:
            last_assignment_error = error
    else:
        if last_assignment_error is not None:
            raise RuntimeError(
                "Failed to assign balanced lecture attributes after 100 lecture-layout attempts "
                "that respected the cohort concurrency bound. "
                f"The current cohort system supports at most {max_simultaneous_lectures} "
                "simultaneous lectures per slot."
            ) from last_assignment_error
        raise RuntimeError(
            "Failed to generate a lecture layout compatible with the cohort overlap rules after "
            f"100 attempts. The densest attempted layout required {best_max_coverage} simultaneous "
            f"lectures, while the current cohort system supports at most "
            f"{max_simultaneous_lectures}."
        )

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


def tighten_attendance_to_hidden_halls(
    lectures: list[Lecture],
    halls: list[Hall],
    attendance: dict[int, int],
    rng: random.Random,
) -> dict[int, int]:
    hall_capacity_by_id = {hall.hall_id: hall.capacity for hall in halls}
    distinct_capacities = sorted({hall.capacity for hall in halls})
    previous_capacity_by_capacity: dict[int, int] = {}
    previous_capacity = 0
    for capacity in distinct_capacities:
        previous_capacity_by_capacity[capacity] = previous_capacity
        previous_capacity = capacity

    tightened_attendance: dict[int, int] = {}
    for lecture in lectures:
        hidden_capacity = hall_capacity_by_id[lecture.hidden_hall]
        previous_capacity = previous_capacity_by_capacity[hidden_capacity]
        if lecture.is_compulsory:
            occupancy_floor, occupancy_ceiling = 0.92, 0.98
        else:
            occupancy_floor, occupancy_ceiling = 0.86, 0.95

        occupancy_target = int(math.floor(hidden_capacity * rng.uniform(occupancy_floor, occupancy_ceiling)))
        if previous_capacity > 0:
            rank_target = previous_capacity + 1
        else:
            rank_target = max(8, int(math.floor(0.82 * hidden_capacity)))

        tightened_attendance[lecture.lecture_id] = min(
            hidden_capacity,
            max(attendance[lecture.lecture_id], occupancy_target, rank_target),
        )

    return tightened_attendance


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

    tightened_attendance = tighten_attendance_to_hidden_halls(
        lectures=lectures,
        halls=halls,
        attendance=attendance,
        rng=rng,
    )
    updated_lectures = [
        replace(lecture, students=tightened_attendance[lecture.lecture_id])
        for lecture in lectures
    ]

    if not common_students:
        weighted_pairs = [
            (
                prev_lecture.lecture_id,
                next_lecture.lecture_id,
                max(1, attendance[prev_lecture.lecture_id] + attendance[next_lecture.lecture_id]),
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


def build_synthetic_instance(
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
    return build_instance_from_components(
        seed=seed,
        instance_name=f"synthetic_seed_{seed}",
        instance_family="synthetic",
        halls=halls,
        lectures=lectures,
        distances=distances,
        common_students=common_students,
        compatibility=compatibility,
        slots_per_day=slots_per_day,
        days_per_week=DAYS_PER_WEEK,
        density_target=density,
    )
