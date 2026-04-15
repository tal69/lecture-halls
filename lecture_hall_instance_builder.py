#!/usr/bin/env python3
"""Shared helpers to assemble lecture-hall instances from raw components."""

from __future__ import annotations

import hashlib
import math

from lecture_hall_models import Hall, Instance, Lecture


FREE_WASTE_RATIO = 0.10


def stable_seed_from_text(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2_000_000_000


def min_students_without_waste_penalty(hall_capacity: int) -> int:
    return math.ceil((1.0 - FREE_WASTE_RATIO) * hall_capacity)


def wasted_space_penalty(students: int, hall_capacity: int) -> int:
    penalty_trigger_threshold = min_students_without_waste_penalty(hall_capacity)
    excess_empty_seats = max(0, penalty_trigger_threshold - students)
    return excess_empty_seats * excess_empty_seats


def build_assignment_penalties(
    lectures: list[Lecture],
    halls: list[Hall],
    compatibility: dict[int, list[int]],
) -> dict[int, dict[int, int]]:
    hall_capacity_by_id = {hall.hall_id: hall.capacity for hall in halls}
    return {
        lecture.lecture_id: {
            hall_id: wasted_space_penalty(lecture.students, hall_capacity_by_id[hall_id])
            for hall_id in compatibility[lecture.lecture_id]
        }
        for lecture in lectures
    }


def build_active_lectures_by_slot(
    lectures: list[Lecture],
    days_per_week: int,
    slots_per_day: int,
) -> dict[int, list[int]]:
    horizon = days_per_week * slots_per_day
    return {
        slot: [
            lecture.lecture_id
            for lecture in lectures
            if lecture.start_slot <= slot < lecture.end_slot
        ]
        for slot in range(horizon)
    }


def build_instance_from_components(
    *,
    seed: int,
    instance_name: str,
    instance_family: str,
    halls: list[Hall],
    lectures: list[Lecture],
    distances: list[list[int]],
    common_students: dict[tuple[int, int], int],
    compatibility: dict[int, list[int]],
    slots_per_day: int,
    days_per_week: int,
    density_target: float | None = None,
) -> Instance:
    assignment_penalties = build_assignment_penalties(lectures, halls, compatibility)
    active_lectures_by_slot = build_active_lectures_by_slot(lectures, days_per_week, slots_per_day)
    total_lecture_length = sum(lecture.duration for lecture in lectures)
    total_capacity = len(halls) * days_per_week * slots_per_day
    density_actual = total_lecture_length / total_capacity if total_capacity else 0.0
    compatibility_entries = sum(len(hall_ids) for hall_ids in compatibility.values())
    return Instance(
        seed=seed,
        instance_name=instance_name,
        instance_family=instance_family,
        num_halls=len(halls),
        slots_per_day=slots_per_day,
        days_per_week=days_per_week,
        density_target=density_actual if density_target is None else density_target,
        density_actual=density_actual,
        halls=halls,
        lectures=lectures,
        distances=distances,
        common_students=common_students,
        compatibility=compatibility,
        assignment_penalties=assignment_penalties,
        active_lectures_by_slot=active_lectures_by_slot,
        compatibility_preprocess_mode="none",
        compatibility_entries_before=compatibility_entries,
        compatibility_entries_after=compatibility_entries,
        compatibility_preprocess_subproblems=0,
        compatibility_preprocess_wall_seconds=0.0,
        compatibility_preprocess_tightened_lectures=0,
        compatibility_preprocess_optimal_subproblems=0,
        compatibility_preprocess_nonoptimal_subproblems=0,
    )
