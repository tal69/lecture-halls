#!/usr/bin/env python3
"""Prepare merged zero-penalty term-week schedules for lancs-yr23.xml."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd

from lecture_hall_instance_builder import build_instance_from_components, stable_seed_from_text
from lecture_hall_models import Hall, Instance, Lecture
from prepare_itc2019_inputs import (
    apply_capacity_fix,
    build_common_students,
    build_halls_and_distances,
    infer_short_break_slots,
)


DEFAULT_INSTANCE_PATH = Path("ITC2019/lancs-yr23.xml")
DEFAULT_OUTPUT_PATH = Path("Numerical experiment results/lancs_yr23_greedy_terms.xlsx")


@dataclass(frozen=True)
class MergedComponent:
    component_id: str
    member_class_ids: tuple[str, ...]
    days: str
    days_mask: int
    weeks: str
    weeks_mask: int
    start: int
    length: int
    end: int
    room_id: str | None
    room_penalties_by_room_id: dict[str, int]


@dataclass(frozen=True)
class CourseConfig:
    course_id: str
    config_id: str
    component_ids: tuple[str, ...]


@dataclass(frozen=True)
class WeeklyCourseOption:
    course_id: str
    config_id: str
    active_component_ids: tuple[str, ...]


@dataclass(frozen=True)
class TermWeek:
    term_index: int
    block_start_week: int
    block_end_week: int
    block_peak_active_room_components: int
    selected_week_index: int
    selected_week_active_room_components: int


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def add(self, item: str) -> None:
        self.parent[item] = item
        self.rank[item] = 0

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge SameClass components in lancs-yr23.xml, validate the zero-penalty timetable, "
            "and greedily repair student registrations for the first substantial week of each term."
        )
    )
    parser.add_argument(
        "--instance",
        type=Path,
        default=DEFAULT_INSTANCE_PATH,
        help=f"XML input path. Defaults to {DEFAULT_INSTANCE_PATH}.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Excel workbook output path. Defaults to {DEFAULT_OUTPUT_PATH}.",
    )
    parser.add_argument(
        "--term-peak-ratio",
        type=float,
        default=0.5,
        help="Minimum block peak, as a fraction of the global peak, to qualify as a main teaching term.",
    )
    parser.add_argument(
        "--substantial-week-ratio",
        type=float,
        default=0.5,
        help="Within a term block, choose the first week whose activity reaches this fraction of the block peak.",
    )
    return parser.parse_args()


def parse_xml(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def bitmask(bits: str) -> int:
    mask = 0
    for index, value in enumerate(bits):
        if value == "1":
            mask |= 1 << index
    return mask


def dedupe_preserve_order(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def build_sameclass_components(
    root: ET.Element,
) -> tuple[dict[str, MergedComponent], dict[str, str], int, Counter[int]]:
    union_find = UnionFind()
    class_elements: dict[str, ET.Element] = {}
    for class_element in root.findall(".//course//class"):
        class_id = class_element.get("id")
        if class_id is None:
            raise ValueError("Encountered a class without an id.")
        union_find.add(class_id)
        class_elements[class_id] = class_element

    sameclass_constraint_count = 0
    for distribution in root.find("distributions").findall("distribution"):
        if distribution.get("type") != "SameClass":
            continue
        sameclass_constraint_count += 1
        members = [member.get("id") for member in distribution.findall("class")]
        member_ids = [member_id for member_id in members if member_id is not None]
        if not member_ids:
            continue
        anchor = member_ids[0]
        for member_id in member_ids[1:]:
            union_find.union(anchor, member_id)

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for class_id in class_elements:
        members_by_root[union_find.find(class_id)].append(class_id)

    components: dict[str, MergedComponent] = {}
    class_to_component: dict[str, str] = {}
    component_sizes: Counter[int] = Counter()
    for root_id, member_ids in members_by_root.items():
        ordered_member_ids = tuple(sorted(member_ids, key=int))
        zero_times = []
        zero_rooms = []
        room_penalty_maps: list[dict[str, int]] = []
        for member_id in ordered_member_ids:
            class_element = class_elements[member_id]
            zero_time_candidates = [time for time in class_element.findall("time") if int(time.get("penalty", "0")) == 0]
            if len(zero_time_candidates) != 1:
                raise ValueError(
                    f"Class {member_id} does not have exactly one zero-penalty time: {len(zero_time_candidates)}."
                )
            zero_times.append(zero_time_candidates[0])
            zero_room_candidates = [room for room in class_element.findall("room") if int(room.get("penalty", "0")) == 0]
            zero_rooms.append(zero_room_candidates[0].get("id") if zero_room_candidates else None)
            room_penalty_maps.append(
                {
                    room.get("id"): int(room.get("penalty", "0"))
                    for room in class_element.findall("room")
                    if room.get("id") is not None
                }
            )

        first_time = zero_times[0]
        first_time_key = (
            first_time.get("days", ""),
            first_time.get("weeks", ""),
            int(first_time.get("start", "0")),
            int(first_time.get("length", "0")),
        )
        for member_id, time_element in zip(ordered_member_ids, zero_times, strict=False):
            time_key = (
                time_element.get("days", ""),
                time_element.get("weeks", ""),
                int(time_element.get("start", "0")),
                int(time_element.get("length", "0")),
            )
            if time_key != first_time_key:
                raise ValueError(
                    f"SameClass component rooted at {root_id} has inconsistent zero-penalty times "
                    f"between member {ordered_member_ids[0]} and member {member_id}."
                )

        nonnull_rooms = {room_id for room_id in zero_rooms if room_id is not None}
        if len(nonnull_rooms) > 1:
            raise ValueError(
                f"SameClass component rooted at {root_id} has inconsistent zero-penalty rooms: {sorted(nonnull_rooms)}."
            )

        common_room_ids = set(room_penalty_maps[0]) if room_penalty_maps else set()
        for room_penalty_map in room_penalty_maps[1:]:
            common_room_ids &= set(room_penalty_map)
        common_room_penalties: dict[str, int] = {}
        for room_id in sorted(common_room_ids, key=int):
            penalties = {room_penalty_map[room_id] for room_penalty_map in room_penalty_maps}
            if len(penalties) != 1:
                raise ValueError(
                    f"SameClass component rooted at {root_id} has inconsistent penalties for room {room_id}: "
                    f"{sorted(penalties)}."
                )
            common_room_penalties[room_id] = penalties.pop()
        if nonnull_rooms and next(iter(nonnull_rooms)) not in common_room_penalties:
            raise ValueError(
                f"SameClass component rooted at {root_id} has zero-penalty room {next(iter(nonnull_rooms))} "
                "outside the common room-option intersection."
            )

        days, weeks, start, length = first_time_key
        component = MergedComponent(
            component_id=root_id,
            member_class_ids=ordered_member_ids,
            days=days,
            days_mask=bitmask(days),
            weeks=weeks,
            weeks_mask=bitmask(weeks),
            start=start,
            length=length,
            end=start + length,
            room_id=next(iter(nonnull_rooms)) if nonnull_rooms else None,
            room_penalties_by_room_id=common_room_penalties,
        )
        components[root_id] = component
        for member_id in ordered_member_ids:
            class_to_component[member_id] = root_id
        component_sizes[len(ordered_member_ids)] += 1

    return components, class_to_component, sameclass_constraint_count, component_sizes


def build_course_configs(root: ET.Element, class_to_component: dict[str, str]) -> dict[str, list[CourseConfig]]:
    course_configs: dict[str, list[CourseConfig]] = defaultdict(list)
    for course_element in root.find("courses").findall("course"):
        course_id = course_element.get("id")
        if course_id is None:
            raise ValueError("Encountered a course without an id.")
        for config_element in course_element.findall("config"):
            config_id = config_element.get("id")
            if config_id is None:
                raise ValueError(f"Course {course_id} contains a config without an id.")
            component_ids: list[str] = []
            for subpart_element in config_element.findall("subpart"):
                subpart_classes = subpart_element.findall("class")
                if len(subpart_classes) != 1:
                    raise ValueError(
                        f"Course {course_id} config {config_id} has subpart {subpart_element.get('id')} "
                        f"with {len(subpart_classes)} classes; this script expects one class per subpart."
                    )
                class_id = subpart_classes[0].get("id")
                if class_id is None:
                    raise ValueError(f"Course {course_id} config {config_id} contains a class without an id.")
                component_ids.append(class_to_component[class_id])
            course_configs[course_id].append(
                CourseConfig(
                    course_id=course_id,
                    config_id=config_id,
                    component_ids=dedupe_preserve_order(component_ids),
                )
            )
    return course_configs


def build_student_requests(root: ET.Element) -> list[tuple[str, tuple[str, ...]]]:
    student_requests: list[tuple[str, tuple[str, ...]]] = []
    for student_element in root.find("students").findall("student"):
        student_id = student_element.get("id")
        if student_id is None:
            raise ValueError("Encountered a student without an id.")
        course_ids = [course.get("id") for course in student_element.findall("course")]
        cleaned_course_ids = [course_id for course_id in course_ids if course_id is not None]
        student_requests.append((student_id, dedupe_preserve_order(cleaned_course_ids)))
    return student_requests


def build_travel_map(root: ET.Element) -> dict[tuple[str, str], int]:
    travel_map: dict[tuple[str, str], int] = {}
    for room_element in root.find("rooms").findall("room"):
        room_id = room_element.get("id")
        if room_id is None:
            raise ValueError("Encountered a room without an id.")
        for travel_element in room_element.findall("travel"):
            other_room_id = travel_element.get("room")
            if other_room_id is None:
                raise ValueError(f"Room {room_id} has a travel entry without a destination room.")
            value = int(travel_element.get("value", "0"))
            travel_map[(room_id, other_room_id)] = value
            travel_map[(other_room_id, room_id)] = value
    return travel_map


def active_room_components_by_week(components: dict[str, MergedComponent], nr_weeks: int) -> list[int]:
    counts = [0] * nr_weeks
    for component in components.values():
        if component.room_id is None:
            continue
        for week_index, is_active in enumerate(component.weeks[:nr_weeks]):
            if is_active == "1":
                counts[week_index] += 1
    return counts


def identify_term_weeks(
    weekly_room_activity: list[int],
    *,
    term_peak_ratio: float,
    substantial_week_ratio: float,
) -> list[TermWeek]:
    if not weekly_room_activity:
        raise ValueError("No weekly activity found.")

    blocks: list[tuple[int, int, list[int]]] = []
    start_index: int | None = None
    for week_index, count in enumerate(weekly_room_activity):
        if count > 0 and start_index is None:
            start_index = week_index
        elif count == 0 and start_index is not None:
            blocks.append((start_index, week_index - 1, weekly_room_activity[start_index:week_index]))
            start_index = None
    if start_index is not None:
        blocks.append((start_index, len(weekly_room_activity) - 1, weekly_room_activity[start_index:]))

    if not blocks:
        raise ValueError("Could not find any positive-activity teaching blocks.")

    global_peak = max(weekly_room_activity)
    main_blocks = [block for block in blocks if max(block[2]) >= term_peak_ratio * global_peak]
    if len(main_blocks) < 2:
        main_blocks = sorted(blocks, key=lambda block: max(block[2]), reverse=True)[:2]
    main_blocks = sorted(main_blocks[:2], key=lambda block: block[0])

    term_weeks: list[TermWeek] = []
    for term_index, (block_start, block_end, block_counts) in enumerate(main_blocks, start=1):
        block_peak = max(block_counts)
        threshold = substantial_week_ratio * block_peak
        selected_week_index = next(
            block_start + offset
            for offset, count in enumerate(block_counts)
            if count >= threshold
        )
        term_weeks.append(
            TermWeek(
                term_index=term_index,
                block_start_week=block_start,
                block_end_week=block_end,
                block_peak_active_room_components=block_peak,
                selected_week_index=selected_week_index,
                selected_week_active_room_components=weekly_room_activity[selected_week_index],
            )
        )
    return term_weeks


def components_overlap(component_a: MergedComponent, component_b: MergedComponent) -> bool:
    return (
        component_a.component_id != component_b.component_id
        and (component_a.days_mask & component_b.days_mask) != 0
        and component_a.start < component_b.end
        and component_b.start < component_a.end
    )


def validate_merged_zero_penalty_timetable(
    root: ET.Element,
    components: dict[str, MergedComponent],
    class_to_component: dict[str, str],
    travel_map: dict[tuple[str, str], int],
) -> None:
    room_usage: dict[str, list[MergedComponent]] = defaultdict(list)
    for component in components.values():
        if component.room_id is not None:
            room_usage[component.room_id].append(component)

    for room_id, room_components in room_usage.items():
        for left_index, left_component in enumerate(room_components):
            for right_component in room_components[left_index + 1:]:
                if (
                    (left_component.weeks_mask & right_component.weeks_mask) != 0
                    and components_overlap(left_component, right_component)
                ):
                    raise ValueError(
                        f"Merged zero-penalty timetable still has a room conflict in room {room_id} between "
                        f"components {left_component.component_id} and {right_component.component_id}."
                    )

    hard_sameattendees_violations = 0
    for distribution in root.find("distributions").findall("distribution"):
        if distribution.get("type") != "SameAttendees" or distribution.get("required") != "true":
            continue
        member_components = dedupe_preserve_order(
            [class_to_component[class_element.get("id")] for class_element in distribution.findall("class") if class_element.get("id") is not None]
        )
        for left_index, left_component_id in enumerate(member_components):
            left_component = components[left_component_id]
            for right_component_id in member_components[left_index + 1:]:
                right_component = components[right_component_id]
                travel_left = 0 if left_component.room_id is None or right_component.room_id is None else travel_map.get((left_component.room_id, right_component.room_id), 0)
                travel_right = 0 if left_component.room_id is None or right_component.room_id is None else travel_map.get((right_component.room_id, left_component.room_id), 0)
                no_common_day = (left_component.days_mask & right_component.days_mask) == 0
                no_common_week = (left_component.weeks_mask & right_component.weeks_mask) == 0
                if no_common_day or no_common_week:
                    continue
                if left_component.end + travel_left <= right_component.start:
                    continue
                if right_component.end + travel_right <= left_component.start:
                    continue
                hard_sameattendees_violations += 1

    if hard_sameattendees_violations:
        raise ValueError(
            f"Merged zero-penalty timetable violates {hard_sameattendees_violations} hard SameAttendees pairs."
        )


def build_weekly_course_options(
    course_configs: dict[str, list[CourseConfig]],
    active_component_ids: set[str],
) -> dict[str, list[WeeklyCourseOption]]:
    weekly_options: dict[str, list[WeeklyCourseOption]] = {}
    for course_id, configs in course_configs.items():
        option_by_signature: dict[tuple[str, ...], WeeklyCourseOption] = {}
        for config in configs:
            active_ids = tuple(component_id for component_id in config.component_ids if component_id in active_component_ids)
            option_by_signature.setdefault(
                active_ids,
                WeeklyCourseOption(
                    course_id=course_id,
                    config_id=config.config_id,
                    active_component_ids=active_ids,
                ),
            )
        weekly_options[course_id] = list(option_by_signature.values())
    return weekly_options


def option_fits_schedule(
    option: WeeklyCourseOption,
    scheduled_component_ids: set[str],
    components: dict[str, MergedComponent],
) -> bool:
    for component_id in option.active_component_ids:
        component = components[component_id]
        for scheduled_component_id in scheduled_component_ids:
            scheduled_component = components[scheduled_component_id]
            if components_overlap(component, scheduled_component):
                return False
    return True


def option_fits_capacity(
    option: WeeklyCourseOption,
    *,
    scheduled_component_ids: set[str],
    used_capacity_by_component: Counter[str],
    capacity_by_component: dict[str, int | None],
) -> bool:
    for component_id in option.active_component_ids:
        if component_id in scheduled_component_ids:
            continue
        component_capacity = capacity_by_component.get(component_id)
        if component_capacity is None:
            continue
        if used_capacity_by_component[component_id] >= component_capacity:
            return False
    return True


def option_is_self_consistent(option: WeeklyCourseOption, components: dict[str, MergedComponent]) -> bool:
    component_ids = option.active_component_ids
    for left_index, left_component_id in enumerate(component_ids):
        left_component = components[left_component_id]
        for right_component_id in component_ids[left_index + 1:]:
            if components_overlap(left_component, components[right_component_id]):
                return False
    return True


def greedy_assign_term_week(
    term_week: TermWeek,
    student_requests: list[tuple[str, tuple[str, ...]]],
    course_configs: dict[str, list[CourseConfig]],
    components: dict[str, MergedComponent],
    capacity_by_component: dict[str, int | None],
) -> tuple[dict[str, dict[str, WeeklyCourseOption]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    active_component_ids = {
        component_id
        for component_id, component in components.items()
        if term_week.selected_week_index < len(component.weeks)
        and component.weeks[term_week.selected_week_index] == "1"
    }
    weekly_options = build_weekly_course_options(course_configs, active_component_ids)
    weekly_options = {
        course_id: [
            option
            for option in course_options
            if option_is_self_consistent(option, components)
        ]
        for course_id, course_options in weekly_options.items()
    }

    assignments_by_student: dict[str, dict[str, WeeklyCourseOption]] = {}
    removed_pairs: list[dict[str, object]] = []
    student_summary_rows: list[dict[str, object]] = []
    assignment_counter: Counter[tuple[str, str]] = Counter()
    active_assignment_counter: Counter[tuple[str, str]] = Counter()
    used_capacity_by_component: Counter[str] = Counter()

    total_requested_pairs = 0
    total_active_requested_pairs = 0
    total_removed_pairs = 0
    total_assigned_pairs = 0
    total_assigned_active_pairs = 0

    for student_id, requested_courses in student_requests:
        requested_course_ids = list(requested_courses)
        total_requested_pairs += len(requested_course_ids)

        assigned_course_options: dict[str, WeeklyCourseOption] = {}
        scheduled_component_ids: set[str] = set()
        remaining_courses = requested_course_ids.copy()

        course_has_active_weekly_meeting = {
            course_id: any(option.active_component_ids for option in weekly_options.get(course_id, []))
            for course_id in requested_course_ids
        }
        total_active_requested_pairs += sum(course_has_active_weekly_meeting.values())

        while remaining_courses:
            candidate_rows = []
            for course_id in remaining_courses:
                options = weekly_options.get(course_id, [])
                feasible_options = [
                    option
                    for option in options
                    if option_fits_schedule(option, scheduled_component_ids, components)
                    and option_fits_capacity(
                        option,
                        scheduled_component_ids=scheduled_component_ids,
                        used_capacity_by_component=used_capacity_by_component,
                        capacity_by_component=capacity_by_component,
                    )
                ]
                max_active_components = max((len(option.active_component_ids) for option in options), default=0)
                candidate_rows.append((len(feasible_options), -max_active_components, course_id, feasible_options))

            candidate_rows.sort()
            _, _, course_id, feasible_options = candidate_rows[0]
            remaining_courses.remove(course_id)

            if not feasible_options:
                total_removed_pairs += 1
                removed_pairs.append(
                    {
                        "term_index": term_week.term_index,
                        "selected_week_number": term_week.selected_week_index + 1,
                        "student_id": student_id,
                        "course_id": course_id,
                        "had_active_weekly_meeting": course_has_active_weekly_meeting[course_id],
                        "weekly_option_count": len(weekly_options.get(course_id, [])),
                    }
                )
                continue

            chosen_option = min(
                feasible_options,
                key=lambda option: (-len(option.active_component_ids), option.config_id),
            )
            assigned_course_options[course_id] = chosen_option
            new_component_ids = [component_id for component_id in chosen_option.active_component_ids if component_id not in scheduled_component_ids]
            scheduled_component_ids.update(chosen_option.active_component_ids)
            for component_id in new_component_ids:
                component_capacity = capacity_by_component.get(component_id)
                if component_capacity is not None:
                    used_capacity_by_component[component_id] += 1
            total_assigned_pairs += 1
            assignment_counter[(course_id, chosen_option.config_id)] += 1
            if chosen_option.active_component_ids:
                total_assigned_active_pairs += 1
                active_assignment_counter[(course_id, chosen_option.config_id)] += 1

        student_summary_rows.append(
            {
                "term_index": term_week.term_index,
                "selected_week_number": term_week.selected_week_index + 1,
                "student_id": student_id,
                "requested_courses": len(requested_course_ids),
                "requested_courses_with_active_weekly_meeting": sum(course_has_active_weekly_meeting.values()),
                "assigned_courses": len(assigned_course_options),
                "assigned_courses_with_active_weekly_meeting": sum(
                    1 for option in assigned_course_options.values() if option.active_component_ids
                ),
                "removed_courses": len(requested_course_ids) - len(assigned_course_options),
            }
        )
        assignments_by_student[student_id] = assigned_course_options

    course_assignment_rows: list[dict[str, object]] = []
    for course_id in sorted(course_configs, key=int):
        seen_configs: set[str] = set()
        for option in weekly_options.get(course_id, []):
            if option.config_id in seen_configs:
                continue
            seen_configs.add(option.config_id)
            course_assignment_rows.append(
                {
                    "term_index": term_week.term_index,
                    "selected_week_number": term_week.selected_week_index + 1,
                    "course_id": course_id,
                    "config_id": option.config_id,
                    "active_component_count": len(option.active_component_ids),
                    "active_component_ids": ",".join(option.active_component_ids),
                    "assigned_students": assignment_counter[(course_id, option.config_id)],
                    "assigned_students_with_active_weekly_meeting": active_assignment_counter[(course_id, option.config_id)],
                }
            )

    summary_row = {
        "term_index": term_week.term_index,
        "block_start_week": term_week.block_start_week + 1,
        "block_end_week": term_week.block_end_week + 1,
        "selected_week_number": term_week.selected_week_index + 1,
        "block_peak_active_room_components": term_week.block_peak_active_room_components,
        "selected_week_active_room_components": term_week.selected_week_active_room_components,
        "active_components_in_selected_week": len(active_component_ids),
        "students": len(student_requests),
        "student_course_pairs_total": total_requested_pairs,
        "student_course_pairs_with_active_weekly_meeting": total_active_requested_pairs,
        "assigned_student_course_pairs": total_assigned_pairs,
        "assigned_student_course_pairs_with_active_weekly_meeting": total_assigned_active_pairs,
        "removed_student_course_pairs": total_removed_pairs,
        "removed_share_of_total_pairs": total_removed_pairs / total_requested_pairs if total_requested_pairs else 0.0,
        "removed_share_of_active_pairs": (
            total_removed_pairs / total_active_requested_pairs if total_active_requested_pairs else 0.0
        ),
        "students_with_removed_pairs": sum(row["removed_courses"] > 0 for row in student_summary_rows),
        "distinct_removed_courses": len({row["course_id"] for row in removed_pairs}),
        "capacity_constrained_components_in_week": sum(
            component_id in active_component_ids and capacity_by_component.get(component_id) is not None
            for component_id in components
        ),
    }
    return assignments_by_student, removed_pairs, student_summary_rows, course_assignment_rows, summary_row


def validate_student_assignments(
    assignments_by_student: dict[str, dict[str, WeeklyCourseOption]],
    components: dict[str, MergedComponent],
    capacity_by_component: dict[str, int | None] | None = None,
) -> None:
    attendance_counter: Counter[str] = Counter()
    for student_id, course_assignments in assignments_by_student.items():
        scheduled_component_ids = set()
        for option in course_assignments.values():
            for component_id in option.active_component_ids:
                component = components[component_id]
                for scheduled_component_id in scheduled_component_ids:
                    if components_overlap(component, components[scheduled_component_id]):
                        raise ValueError(
                            f"Greedy assignment left an overlap for student {student_id} between "
                            f"components {component_id} and {scheduled_component_id}."
                        )
                scheduled_component_ids.add(component_id)
        for component_id in scheduled_component_ids:
            attendance_counter[component_id] += 1
    if capacity_by_component is None:
        return
    for component_id, used_capacity in attendance_counter.items():
        component_capacity = capacity_by_component.get(component_id)
        if component_capacity is not None and used_capacity > component_capacity:
            raise ValueError(
                f"Greedy assignment exceeded capacity on component {component_id}: "
                f"{used_capacity} > {component_capacity}."
            )


def resolve_lancs_instance_path(instance_arg: str | Path | None) -> Path:
    if instance_arg is None:
        return DEFAULT_INSTANCE_PATH
    candidate = Path(instance_arg)
    if candidate.exists():
        return candidate
    if candidate.suffix == ".xml":
        default_path = DEFAULT_INSTANCE_PATH.parent / candidate.name
    else:
        default_path = DEFAULT_INSTANCE_PATH.parent / f"{candidate.name}.xml"
    if default_path.exists():
        return default_path
    raise ValueError(f"Could not find Lancaster XML for '{instance_arg}'.")


def build_term_capacity_by_component(
    term_week: TermWeek,
    components: dict[str, MergedComponent],
    halls_by_room_id: dict[str, Hall],
) -> dict[str, int | None]:
    capacity_by_component: dict[str, int | None] = {}
    for component_id, component in components.items():
        if (
            term_week.selected_week_index >= len(component.weeks)
            or component.weeks[term_week.selected_week_index] != "1"
            or component.room_id is None
        ):
            capacity_by_component[component_id] = None
            continue
        capacity_by_component[component_id] = halls_by_room_id[component.room_id].capacity
    return capacity_by_component


def build_component_attendees(
    assignments_by_student: dict[str, dict[str, WeeklyCourseOption]],
) -> dict[str, tuple[int, ...]]:
    attendees_by_component: dict[str, set[int]] = defaultdict(set)
    for student_id, course_assignments in assignments_by_student.items():
        student_component_ids: set[str] = set()
        for option in course_assignments.values():
            student_component_ids.update(option.active_component_ids)
        student_id_int = int(student_id)
        for component_id in student_component_ids:
            attendees_by_component[component_id].add(student_id_int)
    return {
        component_id: tuple(sorted(student_ids))
        for component_id, student_ids in attendees_by_component.items()
    }


def build_term_daily_records(
    term_week: TermWeek,
    *,
    components: dict[str, MergedComponent],
    component_attendees: dict[str, tuple[int, ...]],
    room_id_to_hall_id: dict[str, int],
    source_day: int | None,
) -> dict[int, list[dict[str, object]]]:
    daily_records: dict[int, list[dict[str, object]]] = defaultdict(list)
    for component_id, component in components.items():
        if (
            term_week.selected_week_index >= len(component.weeks)
            or component.weeks[term_week.selected_week_index] != "1"
            or component.room_id is None
        ):
            continue
        student_ids = component_attendees.get(component_id, ())
        hall_id = room_id_to_hall_id[component.room_id]
        assignment_penalties = {
            room_id_to_hall_id[room_id]: penalty
            for room_id, penalty in component.room_penalties_by_room_id.items()
            if room_id in room_id_to_hall_id
        }
        compatibility = tuple(sorted(assignment_penalties))
        if hall_id not in assignment_penalties:
            raise ValueError(
                f"Merged component {component_id} has hidden room {component.room_id} outside its common compatibility set."
            )
        for day_index, is_active in enumerate(component.days):
            if is_active != "1":
                continue
            if source_day is not None and day_index != source_day:
                continue
            daily_records[day_index].append(
                {
                    "source_component_id": component_id,
                    "day_index": day_index,
                    "start_slot_in_day": component.start,
                    "duration": component.length,
                    "start_slot": component.start,
                    "end_slot": component.end,
                    "students": len(student_ids),
                    "student_ids": student_ids,
                    "hidden_hall": hall_id,
                    "compatibility": compatibility,
                    "assignment_penalties": assignment_penalties,
                }
            )
    return dict(daily_records)


def build_day_lectures_from_merged_records(
    day_records: list[dict[str, object]],
) -> tuple[list[Lecture], dict[int, list[int]], dict[int, dict[int, int]], dict[int, tuple[int, ...]]]:
    sorted_records = sorted(
        day_records,
        key=lambda record: (
            int(record["start_slot"]),
            int(record["end_slot"]),
            str(record["source_component_id"]),
        ),
    )

    lectures: list[Lecture] = []
    compatibility: dict[int, list[int]] = {}
    assignment_penalties: dict[int, dict[int, int]] = {}
    lecture_students: dict[int, tuple[int, ...]] = {}
    for lecture_id, record in enumerate(sorted_records):
        source_component_id = str(record["source_component_id"])
        lectures.append(
            Lecture(
                lecture_id=lecture_id,
                name=f"merged_component_{source_component_id}",
                subject="LANCS_MERGED",
                study_year=1,
                is_compulsory=True,
                day=0,
                start_slot_in_day=int(record["start_slot_in_day"]),
                duration=int(record["duration"]),
                start_slot=int(record["start_slot"]),
                end_slot=int(record["end_slot"]),
                students=int(record["students"]),
                hidden_hall=int(record["hidden_hall"]),
            )
        )
        compatibility[lecture_id] = list(record["compatibility"])  # type: ignore[arg-type]
        assignment_penalties[lecture_id] = dict(record["assignment_penalties"])  # type: ignore[arg-type]
        lecture_students[lecture_id] = tuple(record["student_ids"])  # type: ignore[arg-type]

    return lectures, compatibility, assignment_penalties, lecture_students


def load_lancs_yr23_term_instances(
    instance: str | Path | None = None,
    *,
    source_day: int | None = None,
    short_break_slots: int | None = None,
    capacity_fix: bool = True,
    term_peak_ratio: float = 0.5,
    substantial_week_ratio: float = 0.5,
) -> list[Instance]:
    instance_path = resolve_lancs_instance_path(instance)
    root = parse_xml(instance_path)

    halls, room_id_to_hall_id, distances = build_halls_and_distances(root)
    halls_by_room_id = {room_id: halls[hall_id] for room_id, hall_id in room_id_to_hall_id.items()}
    components, class_to_component, _, _ = build_sameclass_components(root)
    course_configs = build_course_configs(root, class_to_component)
    student_requests = build_student_requests(root)
    travel_map = build_travel_map(root)
    validate_merged_zero_penalty_timetable(root, components, class_to_component, travel_map)

    nr_weeks = int(root.get("nrWeeks", "0"))
    slots_per_day = int(root.get("slotsPerDay", "0"))
    raw_slot_minutes = 1440.0 / slots_per_day if slots_per_day else 0.0
    optimization_element = root.find("optimization")
    time_weight = int(optimization_element.get("time", "0")) if optimization_element is not None else 0

    term_weeks = identify_term_weeks(
        active_room_components_by_week(components, nr_weeks),
        term_peak_ratio=term_peak_ratio,
        substantial_week_ratio=substantial_week_ratio,
    )
    if len(term_weeks) != 2:
        raise ValueError(f"Expected to identify two main teaching terms, found {len(term_weeks)}.")

    instances: list[Instance] = []
    for term_week in term_weeks:
        capacity_by_component = build_term_capacity_by_component(term_week, components, halls_by_room_id)
        assignments_by_student, _, _, _, _ = greedy_assign_term_week(
            term_week,
            student_requests,
            course_configs,
            components,
            capacity_by_component,
        )
        validate_student_assignments(assignments_by_student, components, capacity_by_component)
        component_attendees = build_component_attendees(assignments_by_student)
        daily_records = build_term_daily_records(
            term_week,
            components=components,
            component_attendees=component_attendees,
            room_id_to_hall_id=room_id_to_hall_id,
            source_day=source_day,
        )
        if short_break_slots is None:
            selected_short_break_slots, successor_gap_inference_mode = infer_short_break_slots(
                daily_records,
                raw_slot_minutes,
            )
        else:
            if short_break_slots < 0:
                raise ValueError("short_break_slots must be nonnegative.")
            selected_short_break_slots = short_break_slots
            successor_gap_inference_mode = "explicit"

        for day_index, day_records in sorted(daily_records.items()):
            if not day_records:
                continue
            lectures, compatibility, assignment_penalties, lecture_students = build_day_lectures_from_merged_records(day_records)
            adjusted_student_counts = None
            capacity_fix_changed_lectures = 0
            if capacity_fix:
                (
                    adjusted_lectures,
                    adjusted_compatibility,
                    adjusted_assignment_penalties,
                    adjusted_student_counts,
                    capacity_fix_changed_lectures,
                ) = apply_capacity_fix(
                    lectures,
                    halls,
                    compatibility,
                    assignment_penalties,
                )
            else:
                adjusted_lectures = lectures
                adjusted_compatibility = compatibility
                adjusted_assignment_penalties = assignment_penalties

            common_students = build_common_students(
                lectures,
                lecture_students,
                max_gap_slots=selected_short_break_slots,
                adjusted_student_counts=adjusted_student_counts,
            )
            instance_name = (
                f"{instance_path.stem}_term{term_week.term_index}_week{term_week.selected_week_index + 1}"
                f"_day{day_index + 1}"
            )
            instances.append(
                build_instance_from_components(
                    seed=stable_seed_from_text(instance_name),
                    instance_name=instance_name,
                    instance_family="lancs_yr23",
                    halls=halls,
                    lectures=adjusted_lectures,
                    distances=distances,
                    common_students=common_students,
                    compatibility=adjusted_compatibility,
                    slots_per_day=slots_per_day,
                    days_per_week=1,
                    density_target=None,
                    assignment_penalties=adjusted_assignment_penalties,
                    assignment_penalty_type="itc2019_room_penalty",
                    fixed_input_time_penalty=0.0,
                    fixed_input_time_weight=time_weight,
                    fixed_input_time_penalty_allocation="merged_zero_penalty_weekly_schedule",
                    raw_slot_minutes=raw_slot_minutes,
                    selected_week_index=term_week.selected_week_index,
                    week_selection_mode=f"lancs_term{term_week.term_index}_auto_first_substantial",
                    successor_max_gap_slots=selected_short_break_slots,
                    successor_max_gap_minutes=selected_short_break_slots * raw_slot_minutes,
                    successor_gap_inference_mode=successor_gap_inference_mode,
                    capacity_fix_applied=capacity_fix,
                    capacity_fix_changed_lectures=capacity_fix_changed_lectures,
                    capacity_fix_mode="greedy_capacity_and_hidden_hall_fix" if capacity_fix else "disabled",
                )
            )

    return instances


def write_workbook(
    output_path: Path,
    *,
    summary_rows: list[dict[str, object]],
    removed_pair_rows: list[dict[str, object]],
    student_summary_rows: list[dict[str, object]],
    course_assignment_rows: list[dict[str, object]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="summary", index=False)
        pd.DataFrame(removed_pair_rows).to_excel(writer, sheet_name="removed_pairs", index=False)
        pd.DataFrame(student_summary_rows).to_excel(writer, sheet_name="student_summary", index=False)
        pd.DataFrame(course_assignment_rows).to_excel(writer, sheet_name="course_assignments", index=False)


def main() -> None:
    args = parse_args()
    root = parse_xml(args.instance)
    halls, room_id_to_hall_id, _ = build_halls_and_distances(root)
    halls_by_room_id = {room_id: halls[hall_id] for room_id, hall_id in room_id_to_hall_id.items()}

    components, class_to_component, sameclass_constraint_count, component_sizes = build_sameclass_components(root)
    course_configs = build_course_configs(root, class_to_component)
    student_requests = build_student_requests(root)
    travel_map = build_travel_map(root)
    validate_merged_zero_penalty_timetable(root, components, class_to_component, travel_map)

    nr_weeks = int(root.get("nrWeeks", "0"))
    weekly_room_activity = active_room_components_by_week(components, nr_weeks)
    term_weeks = identify_term_weeks(
        weekly_room_activity,
        term_peak_ratio=args.term_peak_ratio,
        substantial_week_ratio=args.substantial_week_ratio,
    )
    if len(term_weeks) != 2:
        raise ValueError(f"Expected to identify two main teaching terms, found {len(term_weeks)}.")

    summary_rows: list[dict[str, object]] = []
    removed_pair_rows: list[dict[str, object]] = []
    student_summary_rows: list[dict[str, object]] = []
    course_assignment_rows: list[dict[str, object]] = []

    merged_class_count = sum(len(component.member_class_ids) for component in components.values())
    for term_week in term_weeks:
        capacity_by_component = build_term_capacity_by_component(term_week, components, halls_by_room_id)
        assignments_by_student, term_removed_pairs, term_student_rows, term_course_rows, term_summary = greedy_assign_term_week(
            term_week,
            student_requests,
            course_configs,
            components,
            capacity_by_component,
        )
        validate_student_assignments(assignments_by_student, components, capacity_by_component)
        term_summary.update(
            {
                "sameclass_constraints": sameclass_constraint_count,
                "original_classes": merged_class_count,
                "merged_components": len(components),
                "classes_eliminated_by_merge": merged_class_count - len(components),
                "largest_component_size": max(component_sizes),
            }
        )
        summary_rows.append(term_summary)
        removed_pair_rows.extend(term_removed_pairs)
        student_summary_rows.extend(term_student_rows)
        course_assignment_rows.extend(term_course_rows)

    write_workbook(
        args.output,
        summary_rows=summary_rows,
        removed_pair_rows=removed_pair_rows,
        student_summary_rows=student_summary_rows,
        course_assignment_rows=course_assignment_rows,
    )

    print(f"Merged components: {len(components)} from {merged_class_count} original classes.")
    for summary_row in summary_rows:
        print(
            f"term {summary_row['term_index']}: week {summary_row['selected_week_number']}, "
            f"removed {summary_row['removed_student_course_pairs']} student-course pairs "
            f"out of {summary_row['student_course_pairs_total']}"
        )
    print(f"Workbook written to: {args.output}")


if __name__ == "__main__":
    main()
