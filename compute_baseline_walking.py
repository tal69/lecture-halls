#!/usr/bin/env python3
"""Value-of-optimization baseline for the lecture-hall assignment paper.

For every one of the 35 daily benchmark instances this script evaluates the
model-implied student walking burden of the *status-quo* hall assignment, that is,
the hall each lecture actually used in the source data (the published ITC 2019
competition room assignment and the real Lancaster 2023 institutional room
assignment, stored as ``Lecture.hidden_hall``).  It contrasts that value with
the smallest walking component observed among archived 1800-second MIQP/MIP
runs without compatibility preprocessing that attain the best full-objective
value for the instance.  It also reports the largest observed walking component
among those runs.

The script verifies that the status-quo assignment is feasible for the complete
hard model: every recorded hall is compatible, no hall hosts overlapping
lectures, and every hard SameRoom and SameAttendees constraint is satisfied.
It also checks that the rebuilt instances match the archived workbooks before
using their solution records.

Run:  python compute_baseline_walking.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from prepare_itc2019_inputs import load_itc2019_day_instances
from prepare_lancs_yr23_greedy_terms import load_lancs_yr23_term_instances

BASE = Path(__file__).resolve().parent
RESULT_DIR = BASE / "Numerical experiment results"
ITC_1800 = RESULT_DIR / "full_factorial_1800s.xlsx"
LANCS_1800 = RESULT_DIR / "lancs_yr23_full_factorial_1800s.xlsx"
SOURCE_DIR = BASE / "ITC2019"
SOLUTION_DIR = SOURCE_DIR / "solution"
LANCS_XML = SOURCE_DIR / "lancs-yr23.xml"
ITC_SOURCES = [
    "muni-pdf-spr16c",
    "muni-pdfx-fal17",
    "agh-fal17",
    "pu-d9-fal19",
    "pu-proj-fal19",
]
PAPER_FORMULATIONS = ("quadratic_miqp", "linearized_milp")
PAPER_PREPROCESS_MODE = "none"
OBJ_TOL = 1e-4
EXPECTED_INSTANCE_COUNT = 35
SIGNATURE_COLUMNS = (
    "num_halls",
    "num_lectures",
    "total_common_students_weight",
    "hard_same_room_pairs",
    "hard_same_attendees_pairs",
)


def short_name(name: str) -> str:
    reps = {
        "pu-proj-fal19_week": "pu-proj w",
        "pu-d9-fal19_week": "pu-d9 w",
        "agh-fal17_week": "agh w",
        "muni-pdfx-fal17_week": "muni-pdfx w",
        "muni-pdf-spr16c_week": "muni-pdf w",
        "lancs-yr23_term1_week": "lancs t1 w",
        "lancs-yr23_term2_week": "lancs t2 w",
    }
    out = name
    for old, new in reps.items():
        out = out.replace(old, new)
    return out.replace("_day", "d")


def per_pair_distance_floor(inst) -> int:
    """Sum over active successor pairs of c * min compatible hall-to-hall distance.

    This is a valid lower bound on the walking cost of any feasible assignment:
    each pair independently attains at least its minimum compatible distance.
    Pairs whose two lectures share a compatible hall have a floor of zero (both
    can occupy the same hall), which is exploited as an O(1) short-circuit.
    """
    d = inst.distances
    comp = inst.compatibility
    floor = 0
    for (l1, l2), c in inst.common_students.items():
        s1 = comp[l1]
        s2 = comp[l2]
        if set(s1) & set(s2):  # co-locatable: min distance is d[h][h] = 0
            continue
        m = min(d[h1][h2] for h1 in s1 for h2 in s2)
        floor += c * m
    return int(floor)


def status_quo_walking(inst) -> dict:
    """Walking distance and feasibility of the hidden-hall (status-quo) assignment."""
    hidden = {l.lecture_id: l.hidden_hall for l in inst.lectures}
    lecture_map = {l.lecture_id: l for l in inst.lectures}
    d = inst.distances
    walking = 0
    for (l1, l2), c in inst.common_students.items():
        walking += c * d[hidden[l1]][hidden[l2]]
    # feasibility: compatibility
    incompatible = sum(
        1 for l in inst.lectures if hidden[l.lecture_id] not in inst.compatibility[l.lecture_id]
    )
    # feasibility: non-overlap (no two lectures in the same hall overlap in time)
    by_hall: dict[int, list] = {}
    for l in inst.lectures:
        by_hall.setdefault(hidden[l.lecture_id], []).append((l.start_slot, l.end_slot))
    overlap_pairs = 0
    for _, ivs in by_hall.items():
        ivs.sort()
        for left_index, (_, end_1) in enumerate(ivs):
            for start_2, _ in ivs[left_index + 1:]:
                if start_2 >= end_1:
                    break
                overlap_pairs += 1

    hard_same_room_violations = sum(
        hidden[pair.lecture_id_1] != hidden[pair.lecture_id_2]
        for pair in inst.hard_same_room_pairs
    )
    hard_same_attendees_violations = 0
    for pair in inst.hard_same_attendees_pairs:
        lecture_1 = lecture_map[pair.lecture_id_1]
        lecture_2 = lecture_map[pair.lecture_id_2]
        hall_1 = hidden[pair.lecture_id_1]
        hall_2 = hidden[pair.lecture_id_2]
        if lecture_1.end_slot <= lecture_2.start_slot:
            violated = d[hall_1][hall_2] > lecture_2.start_slot - lecture_1.end_slot
        elif lecture_2.end_slot <= lecture_1.start_slot:
            violated = d[hall_2][hall_1] > lecture_1.start_slot - lecture_2.end_slot
        else:
            violated = True
        hard_same_attendees_violations += int(violated)

    return {
        "instance_name": inst.instance_name,
        "family": inst.instance_family,
        "num_halls": inst.num_halls,
        "num_lectures": len(inst.lectures),
        "sum_c": int(sum(inst.common_students.values())),
        "hard_same_room_pairs": len(inst.hard_same_room_pairs),
        "hard_same_attendees_pairs": len(inst.hard_same_attendees_pairs),
        "walk_status_quo": int(walking),
        "walk_floor": per_pair_distance_floor(inst),
        "hidden_incompatible": int(incompatible),
        "hidden_overlap_pairs": int(overlap_pairs),
        "hidden_hard_same_room_violations": int(hard_same_room_violations),
        "hidden_hard_same_attendees_violations": int(hard_same_attendees_violations),
    }


def build_all_instances() -> pd.DataFrame:
    rows = []
    for source in ITC_SOURCES:
        instance_path = SOURCE_DIR / f"{source}.xml"
        solution_path = SOLUTION_DIR / f"{source}.xml"
        for inst in load_itc2019_day_instances(
            str(instance_path),
            solution=solution_path,
        ):
            rows.append(status_quo_walking(inst))
    for inst in load_lancs_yr23_term_instances(LANCS_XML):
        rows.append(status_quo_walking(inst))
    return pd.DataFrame(rows)


def optimal_walking() -> pd.DataFrame:
    itc = pd.read_excel(ITC_1800, sheet_name="summary")
    lan = pd.read_excel(LANCS_1800, sheet_name="summary")
    ex = pd.concat([itc, lan], ignore_index=True)
    paper = ex[
        ex.formulation.isin(PAPER_FORMULATIONS)
        & ex.compatibility_preprocess_mode.eq(PAPER_PREPROCESS_MODE)
    ].copy()
    for col in ("objective_value", "total_student_walking_distance"):
        paper[col] = pd.to_numeric(paper[col], errors="coerce")
    rows = []
    for name, g in paper.groupby("instance_name"):
        proven = g[g.status == "OPTIMAL"]
        if proven.empty:
            raise ValueError(f"No MIQP/MIP run proves optimality for {name}.")
        if proven[["objective_value", "total_student_walking_distance"]].isna().any().any():
            raise ValueError(f"Missing objective component in an optimal run for {name}.")

        row = {"instance_name": name}
        for column in SIGNATURE_COLUMNS:
            numeric_values = pd.to_numeric(g[column], errors="coerce")
            values = numeric_values.dropna().unique()
            if numeric_values.isna().any() or len(values) != 1:
                raise ValueError(
                    f"Workbook signature column {column} is not constant for {name}: {values}."
                )
            row[f"workbook_{column}"] = int(round(float(values[0])))

        best_obj = proven["objective_value"].min()
        finite_objectives = g.dropna(subset=["objective_value"])
        if finite_objectives["objective_value"].min() < best_obj - OBJ_TOL:
            raise ValueError(
                f"An uncertified run has an objective below the certified optimum for {name}."
            )
        best = g[np.isclose(g["objective_value"], best_obj, rtol=0, atol=OBJ_TOL)]
        if best["total_student_walking_distance"].isna().any():
            raise ValueError(f"Missing walking component in a best-objective run for {name}.")
        row.update(
            {
                "opt_objective": float(best_obj),
                "walk_opt": float(best["total_student_walking_distance"].min()),
                "walk_opt_max": float(best["total_student_walking_distance"].max()),
                "best_objective_runs": len(best),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def merge_and_validate(sq: pd.DataFrame, opt: pd.DataFrame) -> pd.DataFrame:
    """Join rebuilt inputs to workbook results and enforce the paper's data contract."""
    if len(sq) != EXPECTED_INSTANCE_COUNT or sq["instance_name"].nunique() != EXPECTED_INSTANCE_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_INSTANCE_COUNT} unique rebuilt instances; got "
            f"{len(sq)} rows and {sq['instance_name'].nunique()} names."
        )
    if len(opt) != EXPECTED_INSTANCE_COUNT or opt["instance_name"].nunique() != EXPECTED_INSTANCE_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_INSTANCE_COUNT} unique workbook instances; got "
            f"{len(opt)} rows and {opt['instance_name'].nunique()} names."
        )

    df = sq.merge(opt, on="instance_name", how="outer", validate="one_to_one", indicator=True)
    if not (df["_merge"] == "both").all():
        missing = df.loc[df["_merge"] != "both", ["instance_name", "_merge"]]
        raise ValueError(f"Rebuilt/workbook instance mismatch:\n{missing.to_string(index=False)}")
    df = df.drop(columns="_merge")

    comparisons = {
        "num_halls": "workbook_num_halls",
        "num_lectures": "workbook_num_lectures",
        "sum_c": "workbook_total_common_students_weight",
        "hard_same_room_pairs": "workbook_hard_same_room_pairs",
        "hard_same_attendees_pairs": "workbook_hard_same_attendees_pairs",
    }
    mismatch_mask = pd.Series(False, index=df.index)
    for rebuilt, archived in comparisons.items():
        mismatch_mask |= df[rebuilt] != df[archived]
    if mismatch_mask.any():
        columns = ["instance_name", *comparisons.keys(), *comparisons.values()]
        raise ValueError(
            "Rebuilt instance signatures do not match the workbooks:\n"
            + df.loc[mismatch_mask, columns].to_string(index=False)
        )

    violation_columns = [
        "hidden_incompatible",
        "hidden_overlap_pairs",
        "hidden_hard_same_room_violations",
        "hidden_hard_same_attendees_violations",
    ]
    if df[violation_columns].to_numpy().sum() != 0:
        raise ValueError(
            "The status-quo assignment violates a hard model constraint:\n"
            + df.loc[df[violation_columns].sum(axis=1) > 0, ["instance_name", *violation_columns]].to_string(index=False)
        )
    return df


def main() -> None:
    sq = build_all_instances()
    opt = optimal_walking()
    df = merge_and_validate(sq, opt)
    df["short"] = df["instance_name"].map(short_name)
    df["walk_reduction"] = df["walk_status_quo"] - df["walk_opt"]
    df["reduction_pct"] = 100.0 * df["walk_reduction"] / df["walk_status_quo"].where(df["walk_status_quo"] > 0)
    df["ratio"] = df["walk_status_quo"] / df["walk_opt"].where(df["walk_opt"] > 0)
    df["observed_best_objective_walk_spread_pp"] = (
        100.0 * (df["walk_opt_max"] - df["walk_opt"])
        / df["walk_status_quo"].where(df["walk_status_quo"] > 0)
    )
    df["source"] = df["family"].map({"itc2019": "ITC 2019", "lancs_yr23": "Lancaster"})
    # The per-pair distance floor is a lower bound on any feasible walking; an
    # instance sits "at the floor" when the optimum equals it, so no assignment
    # (including the status quo, when it also equals the floor) can do better.
    df["at_floor"] = np.isclose(df["walk_opt"], df["walk_floor"], rtol=0, atol=0.5)
    src_order = {"itc2019": 0, "lancs_yr23": 1}
    df = df.sort_values(by=["family", "short"], key=lambda s: s.map(src_order) if s.name == "family" else s)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 40)
    print("\n=== Per-instance status-quo vs selected best-objective walking ===")
    print(df[["short", "source", "num_lectures", "sum_c", "walk_floor", "walk_status_quo",
              "walk_opt", "reduction_pct", "ratio", "at_floor", "hidden_incompatible",
              "hidden_overlap_pairs", "hidden_hard_same_room_violations",
              "hidden_hard_same_attendees_violations", "walk_opt_max",
              "observed_best_objective_walk_spread_pp"]].to_string(index=False))

    print("\n=== Input and feasibility checks ===")
    print(f"rebuilt/workbook signatures matched: {len(df)} of {EXPECTED_INSTANCE_COUNT}")
    print("total hidden-incompatible lectures:", int(df["hidden_incompatible"].sum()))
    print("total hidden-hall overlap pairs:", int(df["hidden_overlap_pairs"].sum()))
    print("hard SameRoom pairs/violations:",
          int(df["hard_same_room_pairs"].sum()),
          int(df["hidden_hard_same_room_violations"].sum()))
    print("hard SameAttendees pairs/violations:",
          int(df["hard_same_attendees_pairs"].sum()),
          int(df["hidden_hard_same_attendees_violations"].sum()))
    print("instances with observed walking variation among best-objective runs:",
          int((df["walk_opt"] != df["walk_opt_max"]).sum()))
    print("maximum observed reduction spread (percentage points):",
          f"{df['observed_best_objective_walk_spread_pp'].max():.3f}")
    print("instances where walk_opt > walk_status_quo:",
          int((df["walk_opt"] > df["walk_status_quo"]).sum()))

    print("\n=== Per-pair distance floor (explains the zero-reduction days) ===")
    at = df[df["at_floor"]]
    print(f"instances at the per-pair floor (selected walking == floor): {len(at)} of {len(df)}")
    print("  ", ", ".join(f"{r.short} (floor={int(r.walk_floor)}=opt, sq={int(r.walk_status_quo)})"
                          for r in at.itertuples()))
    zero = df[df["reduction_pct"].fillna(0) == 0]
    print("zero-reduction instances (status quo already walking-optimal):",
          ", ".join(zero["short"].tolist()))
    print("  all zero-reduction instances are at the floor:",
          bool(zero["at_floor"].all()))

    # Aggregates
    for label, sub in [("ITC 2019", df[df.family == "itc2019"]),
                       ("Lancaster", df[df.family == "lancs_yr23"]),
                       ("All 35", df)]:
        tot_sq = sub["walk_status_quo"].sum()
        tot_opt = sub["walk_opt"].sum()
        print(f"\n[{label}] instances={len(sub)}  "
              f"sum status-quo walking={tot_sq:.0f}  sum selected walking={tot_opt:.0f}  "
              f"pooled reduction={100*(tot_sq-tot_opt)/tot_sq:.1f}%  "
              f"mean per-instance reduction={sub['reduction_pct'].mean():.1f}%  "
              f"median={sub['reduction_pct'].median():.1f}%  "
              f"min={sub['reduction_pct'].min():.1f}%  max={sub['reduction_pct'].max():.1f}%  "
              f"mean ratio={sub['ratio'].mean():.2f}x  "
              f"max observed tie spread={sub['observed_best_objective_walk_spread_pp'].max():.3f} pp")

    out = df[["short", "source", "num_lectures", "walk_floor", "walk_status_quo", "walk_opt",
              "walk_opt_max", "walk_reduction", "reduction_pct", "ratio", "at_floor",
              "observed_best_objective_walk_spread_pp"]].copy()
    out.columns = ["instance", "source", "num_lectures", "walking_floor", "walking_status_quo",
                   "walking_optimized_min_observed", "walking_optimized_max_observed",
                   "walking_reduction", "reduction_pct", "ratio", "at_floor",
                   "observed_best_objective_walk_spread_pp"]
    output_path = BASE / "tmp" / "baseline_value_of_optimization.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"\nWrote {output_path.relative_to(BASE)}")


if __name__ == "__main__":
    main()
