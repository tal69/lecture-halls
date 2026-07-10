"""Verify the cross-course share of the shared-enrollment weight.

Supports the claim in the Introduction (comparison with Antunes-Batista et
al., 2026) that successor pairs whose lectures belong to different courses
carry the bulk of the total shared-enrollment weight c_{l1,l2} on the 35
benchmark days: 75--100 percent, 91 percent on average (verified 2026-07-04).

Usage: python verify_cross_course_share.py
"""

import xml.etree.ElementTree as ET
from collections import defaultdict

from prepare_itc2019_inputs import load_itc2019_day_instances
from prepare_lancs_yr23_greedy_terms import (
    build_sameclass_components,
    load_lancs_yr23_term_instances,
)

ITC_SOURCES = [
    "muni-pdf-spr16c",
    "muni-pdfx-fal17",
    "agh-fal17",
    "pu-d9-fal19",
    "pu-proj-fal19",
]

shares = []

for source in ITC_SOURCES:
    for inst in load_itc2019_day_instances(source):
        # For ITC instances the course id is encoded in Lecture.subject.
        subject = {l.lecture_id: l.subject for l in inst.lectures}
        total = sum(inst.common_students.values())
        cross = sum(
            w
            for (l1, l2), w in inst.common_students.items()
            if subject[l1] != subject[l2]
        )
        shares.append((inst.instance_name, cross / total))
        print(f"{inst.instance_name}: share={cross / total:.3f}")

# Lancaster: recover course identity through the SameClass merged components.
root = ET.parse("ITC2019/lancs-yr23.xml").getroot()
_, class_to_component, _, _ = build_sameclass_components(root)

class_to_course = {}
for course in root.find("courses").findall("course"):
    for cls in course.iter("class"):
        class_to_course[cls.get("id")] = course.get("id")

component_courses = defaultdict(set)
for cls, comp in class_to_component.items():
    component_courses[comp].add(class_to_course.get(cls, "?"))

for inst in load_lancs_yr23_term_instances("ITC2019/lancs-yr23.xml"):
    lecture_component = {
        l.lecture_id: l.name.replace("merged_component_", "") for l in inst.lectures
    }

    def course_of(lecture_id: int) -> str:
        courses = component_courses.get(lecture_component[lecture_id], set())
        if len(courses) == 1:
            return next(iter(courses))
        # A handful of merged components span several courses; treat each as
        # its own label so pairs involving them count as cross-course unless
        # both lectures are the same component.
        return f"multi_{lecture_component[lecture_id]}"

    total = sum(inst.common_students.values())
    cross = sum(
        w
        for (l1, l2), w in inst.common_students.items()
        if course_of(l1) != course_of(l2)
    )
    shares.append((inst.instance_name, cross / total))
    print(f"{inst.instance_name}: share={cross / total:.3f}")

values = [s for _, s in shares]
print(f"\nInstances: {len(values)}")
print(f"Min share:  {min(values):.3f}")
print(f"Max share:  {max(values):.3f}")
print(f"Mean share: {sum(values) / len(values):.3f}")
