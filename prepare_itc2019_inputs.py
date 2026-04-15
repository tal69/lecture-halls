#!/usr/bin/env python3
"""Load ITC 2019 instance data into the in-memory lecture-hall format."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

from lecture_hall_instance_builder import build_instance_from_components, stable_seed_from_text
from lecture_hall_models import Hall, Instance, Lecture


DEFAULT_INSTANCE_DIR = Path("ITC2019")
DEFAULT_SOLUTION_DIR = DEFAULT_INSTANCE_DIR / "solution"


def resolve_instance_path(instance_arg: str) -> Path:
    candidate = Path(instance_arg)
    if candidate.exists():
        return candidate
    if candidate.suffix == ".xml":
        default_path = DEFAULT_INSTANCE_DIR / candidate.name
    else:
        default_path = DEFAULT_INSTANCE_DIR / f"{candidate.name}.xml"
    if default_path.exists():
        return default_path
    raise ValueError(f"Could not find instance XML for '{instance_arg}'.")


def resolve_solution_path(instance_path: Path, explicit_solution: Path | None) -> Path:
    if explicit_solution is not None:
        if not explicit_solution.exists():
            raise ValueError(f"Solution XML does not exist: {explicit_solution}")
        return explicit_solution
    solution_path = DEFAULT_SOLUTION_DIR / instance_path.name
    if solution_path.exists():
        return solution_path
    raise ValueError(f"Could not find matching solution XML: {solution_path}")


def parse_xml(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def build_halls_and_distances(instance_root: ET.Element) -> tuple[list[Hall], dict[str, int], list[list[int]]]:
    rooms_element = instance_root.find("rooms")
    if rooms_element is None:
        raise ValueError("Instance XML has no <rooms> section.")

    halls: list[Hall] = []
    room_id_to_hall_id: dict[str, int] = {}
    for hall_id, room_element in enumerate(rooms_element.findall("room")):
        source_room_id = room_element.get("id")
        if source_room_id is None:
            raise ValueError("Encountered a room without an id.")
        room_id_to_hall_id[source_room_id] = hall_id
        halls.append(
            Hall(
                hall_id=hall_id,
                name=f"R{source_room_id}",
                capacity=int(room_element.get("capacity", "0")),
                x=0.0,
                y=0.0,
            )
        )

    num_halls = len(halls)
    distances = [[0 for _ in range(num_halls)] for _ in range(num_halls)]
    for room_element in rooms_element.findall("room"):
        source_room_id = room_element.get("id")
        if source_room_id is None:
            continue
        hall_id = room_id_to_hall_id[source_room_id]
        for travel_element in room_element.findall("travel"):
            other_room_id = travel_element.get("room")
            if other_room_id is None or other_room_id not in room_id_to_hall_id:
                raise ValueError(
                    f"Travel entry from room {source_room_id} references unknown room {other_room_id}."
                )
            other_hall_id = room_id_to_hall_id[other_room_id]
            value = int(travel_element.get("value", "0"))
            distances[hall_id][other_hall_id] = value

    for hall_id in range(num_halls):
        for other_hall_id in range(num_halls):
            if hall_id == other_hall_id:
                continue
            left = distances[hall_id][other_hall_id]
            right = distances[other_hall_id][hall_id]
            if left and right and left != right:
                raise ValueError(
                    f"Asymmetric travel times between halls {hall_id} and {other_hall_id}: {left} vs {right}."
                )
            if not left and right:
                distances[hall_id][other_hall_id] = right
            elif left and not right:
                distances[other_hall_id][hall_id] = left

    return halls, room_id_to_hall_id, distances


def build_class_catalog(instance_root: ET.Element, room_id_to_hall_id: dict[str, int]) -> dict[str, dict[str, object]]:
    courses_element = instance_root.find("courses")
    if courses_element is None:
        raise ValueError("Instance XML has no <courses> section.")

    class_catalog: dict[str, dict[str, object]] = {}
    for course_element in courses_element.findall("course"):
        course_id = course_element.get("id", "")
        for config_element in course_element.findall("config"):
            config_id = config_element.get("id", "")
            for subpart_element in config_element.findall("subpart"):
                subpart_id = subpart_element.get("id", "")
                for class_element in subpart_element.findall("class"):
                    class_id = class_element.get("id")
                    if class_id is None:
                        raise ValueError("Encountered a class without an id.")

                    room_options: list[int] = []
                    for room_element in class_element.findall("room"):
                        source_room_id = room_element.get("id")
                        if source_room_id is None:
                            raise ValueError(f"Class {class_id} has a room option without an id.")
                        if source_room_id not in room_id_to_hall_id:
                            raise ValueError(
                                f"Class {class_id} references unknown room id {source_room_id}."
                            )
                        room_options.append(room_id_to_hall_id[source_room_id])

                    time_lengths_by_key: dict[tuple[str, str, str], set[int]] = defaultdict(set)
                    for time_element in class_element.findall("time"):
                        key = (
                            time_element.get("days", ""),
                            time_element.get("start", ""),
                            time_element.get("weeks", ""),
                        )
                        time_lengths_by_key[key].add(int(time_element.get("length", "0")))

                    class_catalog[class_id] = {
                        "course_id": course_id,
                        "config_id": config_id,
                        "subpart_id": subpart_id,
                        "parent_class_id": class_element.get("parent"),
                        "limit": int(class_element.get("limit", "0")),
                        "room_options": sorted(room_options),
                        "time_lengths_by_key": {
                            key: sorted(lengths) for key, lengths in time_lengths_by_key.items()
                        },
                    }
    return class_catalog


def get_unique_duration(class_id: str, class_info: dict[str, object], solution_class: ET.Element) -> int:
    key = (
        solution_class.get("days", ""),
        solution_class.get("start", ""),
        solution_class.get("weeks", ""),
    )
    matching_lengths = class_info["time_lengths_by_key"].get(key)  # type: ignore[index]
    if not matching_lengths:
        raise ValueError(f"Could not match solution timing for class {class_id} with key {key!r}.")
    if len(matching_lengths) != 1:
        raise ValueError(
            f"Class {class_id} has multiple lengths for the chosen timing {key!r}: {matching_lengths}."
        )
    return matching_lengths[0]


def build_daily_lecture_records(
    solution_root: ET.Element,
    class_catalog: dict[str, dict[str, object]],
    room_id_to_hall_id: dict[str, int],
    week_index: int,
) -> dict[int, list[dict[str, object]]]:
    daily_records: dict[int, list[dict[str, object]]] = defaultdict(list)

    for solution_class in solution_root.findall("class"):
        class_id = solution_class.get("id")
        if class_id is None:
            raise ValueError("Encountered a solution class without an id.")
        if class_id not in class_catalog:
            raise ValueError(f"Solution contains class id {class_id} that does not appear in the instance.")

        class_info = class_catalog[class_id]
        room_options = class_info["room_options"]  # type: ignore[assignment]
        if not room_options:
            continue

        weeks = solution_class.get("weeks", "")
        if week_index < 0 or week_index >= len(weeks) or weeks[week_index] != "1":
            continue

        room_id = solution_class.get("room")
        if room_id is None:
            raise ValueError(f"Room-requiring class {class_id} has no room in the solution.")
        if room_id not in room_id_to_hall_id:
            raise ValueError(f"Solution assigns class {class_id} to unknown room id {room_id}.")
        hidden_hall = room_id_to_hall_id[room_id]
        if hidden_hall not in room_options:
            raise ValueError(
                f"Solution assigns class {class_id} to room {room_id}, which is not in the original compatibility set."
            )

        duration = get_unique_duration(class_id, class_info, solution_class)
        start_slot = int(solution_class.get("start", "0"))
        student_ids = sorted(int(student.get("id", "0")) for student in solution_class.findall("student"))
        days = solution_class.get("days", "")

        for day_index, is_active in enumerate(days):
            if is_active != "1":
                continue
            daily_records[day_index].append(
                {
                    "source_class_id": class_id,
                    "course_id": class_info["course_id"],
                    "config_id": class_info["config_id"],
                    "subpart_id": class_info["subpart_id"],
                    "parent_class_id": class_info["parent_class_id"],
                    "limit": class_info["limit"],
                    "day_index": day_index,
                    "start_slot_in_day": start_slot,
                    "duration": duration,
                    "start_slot": start_slot,
                    "end_slot": start_slot + duration,
                    "students": len(student_ids),
                    "student_ids": tuple(student_ids),
                    "hidden_hall": hidden_hall,
                    "compatibility": tuple(room_options),
                }
            )

    return dict(daily_records)


def build_day_lectures(day_records: list[dict[str, object]]) -> tuple[list[Lecture], dict[int, list[int]], dict[int, tuple[int, ...]]]:
    sorted_records = sorted(
        day_records,
        key=lambda record: (
            int(record["start_slot"]),
            int(record["end_slot"]),
            str(record["source_class_id"]),
        ),
    )

    lectures: list[Lecture] = []
    compatibility: dict[int, list[int]] = {}
    lecture_students: dict[int, tuple[int, ...]] = {}
    for lecture_id, record in enumerate(sorted_records):
        lectures.append(
            Lecture(
                lecture_id=lecture_id,
                name=(
                    f"course_{record['course_id']}_config_{record['config_id']}"
                    f"_subpart_{record['subpart_id']}_class_{record['source_class_id']}"
                ),
                subject=f"ITC_C{record['course_id']}",
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
        lecture_students[lecture_id] = record["student_ids"]  # type: ignore[assignment]

    return lectures, compatibility, lecture_students


def build_common_students(lectures: list[Lecture], lecture_students: dict[int, tuple[int, ...]]) -> dict[tuple[int, int], int]:
    student_lectures: dict[int, list[Lecture]] = defaultdict(list)
    for lecture in lectures:
        for student_id in lecture_students[lecture.lecture_id]:
            student_lectures[student_id].append(lecture)

    common_students: dict[tuple[int, int], int] = {}
    for attended_lectures in student_lectures.values():
        attended_lectures.sort(key=lambda lecture: (lecture.start_slot, lecture.end_slot, lecture.lecture_id))
        for lecture_1, lecture_2 in zip(attended_lectures, attended_lectures[1:], strict=False):
            if lecture_1.end_slot == lecture_2.start_slot:
                key = (lecture_1.lecture_id, lecture_2.lecture_id)
                common_students[key] = common_students.get(key, 0) + 1
    return common_students


def load_itc2019_day_instances(
    instance: str,
    *,
    solution: Path | None = None,
    week_index: int = 0,
    source_day: int | None = None,
) -> list[Instance]:
    instance_path = resolve_instance_path(instance)
    solution_path = resolve_solution_path(instance_path, solution)
    instance_root = parse_xml(instance_path)
    solution_root = parse_xml(solution_path)

    slots_per_day = int(instance_root.get("slotsPerDay", "0"))
    nr_weeks = int(instance_root.get("nrWeeks", "0"))
    if week_index < 0 or week_index >= nr_weeks:
        raise ValueError(f"week_index={week_index} is outside the instance horizon 0..{nr_weeks - 1}.")

    halls, room_id_to_hall_id, distances = build_halls_and_distances(instance_root)
    class_catalog = build_class_catalog(instance_root, room_id_to_hall_id)
    daily_records = build_daily_lecture_records(
        solution_root=solution_root,
        class_catalog=class_catalog,
        room_id_to_hall_id=room_id_to_hall_id,
        week_index=week_index,
    )

    if source_day is not None:
        selected_items = [(source_day, daily_records.get(source_day, []))]
    else:
        selected_items = sorted(daily_records.items())

    instances: list[Instance] = []
    for day_index, day_records in selected_items:
        if not day_records:
            continue
        lectures, compatibility, lecture_students = build_day_lectures(day_records)
        common_students = build_common_students(lectures, lecture_students)
        instance_name = f"{instance_path.stem}_week{week_index + 1}_day{day_index + 1}"
        instances.append(
            build_instance_from_components(
                seed=stable_seed_from_text(instance_name),
                instance_name=instance_name,
                instance_family="itc2019",
                halls=halls,
                lectures=lectures,
                distances=distances,
                common_students=common_students,
                compatibility=compatibility,
                slots_per_day=slots_per_day,
                days_per_week=1,
                density_target=None,
            )
        )

    return instances


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect how an ITC 2019 instance is split into daily lecture-hall instances."
    )
    parser.add_argument("instance", help="Instance stem or XML path.")
    parser.add_argument("--solution", dest="solution", type=Path, default=None, help="Optional solution XML path.")
    parser.add_argument("--week-index", dest="week_index", type=int, default=0, help="0-based week index.")
    parser.add_argument("--day", dest="source_day", type=int, default=None, help="Optional 0-based day index.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    instances = load_itc2019_day_instances(
        args.instance,
        solution=args.solution,
        week_index=args.week_index,
        source_day=args.source_day,
    )
    if not instances:
        print("No active room-requiring day instances found.")
        return
    for instance in instances:
        print(
            f"{instance.instance_name}: halls={instance.num_halls}, lectures={len(instance.lectures)}, "
            f"successor_pairs={len(instance.common_students)}, density={instance.density_actual:.3f}"
        )


if __name__ == "__main__":
    main()
