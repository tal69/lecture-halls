#!/usr/bin/env python3
"""Shared data models for lecture-hall experiments and ITC 2019 conversion."""

from __future__ import annotations

from dataclasses import dataclass


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
    instance_name: str
    instance_family: str
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
    assignment_penalties: dict[int, dict[int, int]]
    active_lectures_by_slot: dict[int, list[int]]
    compatibility_preprocess_mode: str = "none"
    compatibility_entries_before: int = 0
    compatibility_entries_after: int = 0
    compatibility_preprocess_subproblems: int = 0
    compatibility_preprocess_wall_seconds: float = 0.0
    compatibility_preprocess_tightened_lectures: int = 0
    compatibility_preprocess_optimal_subproblems: int = 0
    compatibility_preprocess_nonoptimal_subproblems: int = 0
    assignment_penalty_type: str = "quadratic_wasted_space"
    fixed_input_time_penalty: float = 0.0
    fixed_input_time_weight: int = 0
    fixed_input_weighted_time_penalty: float = 0.0
    fixed_input_time_penalty_allocation: str = "none"
    raw_slot_minutes: float = 0.0
    selected_week_index: int = 0
    week_selection_mode: str = "explicit"
    successor_max_gap_slots: int = 0
    successor_max_gap_minutes: float = 0.0
    successor_gap_inference_mode: str = "exact"


@dataclass(frozen=True)
class CapacityDominanceCut:
    clique_index: int
    day: int
    threshold: int
    eligible_lecture_ids: tuple[int, ...]
    large_hall_ids: tuple[int, ...]
    rhs: int
