#!/usr/bin/env python3
"""Reproduce the revised-paper numerical tables from archived workbooks.

The revised manuscript uses only the 1800-second workbooks for its reported
numerical evidence.  The exact-method tables use only MIQP/MIP rows with
compatibility preprocessing disabled.  CP-SAT and light compatibility
preprocessing were exploratory tests retained in the replication files but
left out of the revised paper after they were empirically dominated.

The exploratory preprocessing summary uses end-to-end wall time.  For each run
this is the workbook's wall_clock_seconds value, which times model construction
plus the solver call, plus compatibility_preprocess_wall_seconds.

Outputs are written as CSV files when --output-dir is provided; otherwise the
same tables are printed to stdout.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent
RESULT_DIR = BASE / "Numerical experiment results"
ITC_1800 = RESULT_DIR / "full_factorial_1800s.xlsx"
LANCS_1800 = RESULT_DIR / "lancs_yr23_full_factorial_1800s.xlsx"
ROOT_1800 = RESULT_DIR / "relaxations_factorial_1800s.xlsx"

PAPER_FORMULATIONS = ("quadratic_miqp", "linearized_milp")
PAPER_PREPROCESS_MODE = "none"
FORMULATION_LABEL = {
    "quadratic_miqp": "MIQP",
    "linearized_milp": "MIP",
    "cp_sat": "CP",
    "linearized_root": "ROOT",
}
SOURCE_LABEL = {
    "itc2019": "ITC 2019",
    "lancs_yr23": "Lancaster",
}
OBJECTIVE_TOL = 1e-4


def load_workbook(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_excel(path, sheet_name="summary")


def numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in (
        "objective_value",
        "lower_bound",
        "wall_clock_seconds",
        "compatibility_preprocess_wall_seconds",
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    df["total_wall_seconds"] = (
        df["wall_clock_seconds"].fillna(0.0)
        + df["compatibility_preprocess_wall_seconds"].fillna(0.0)
    )
    df["table_time_seconds"] = df["total_wall_seconds"]
    return df


def load_exact_1800() -> pd.DataFrame:
    exact = pd.concat(
        [load_workbook(ITC_1800), load_workbook(LANCS_1800)],
        ignore_index=True,
    )
    exact = numeric_columns(exact)
    exact["source_label"] = exact["instance_family"].map(SOURCE_LABEL)
    return exact


def paper_exact(exact: pd.DataFrame) -> pd.DataFrame:
    """Return the MIQP/MIP rows used by the revised paper."""
    return exact[
        exact["formulation"].isin(PAPER_FORMULATIONS)
        & (exact["compatibility_preprocess_mode"] == PAPER_PREPROCESS_MODE)
    ].copy()


def method_code(row: pd.Series) -> str:
    formulation = FORMULATION_LABEL[row["formulation"]]
    biclique = "B" if bool(row["biclique_enabled"]) else "noB"
    cardinality = "D" if bool(row["cardinality_enabled"]) else "noD"
    return f"{formulation}-{biclique}-{cardinality}"


def short_instance_name(name: str) -> str:
    replacements = {
        "pu-proj-fal19_week": "pu-proj w",
        "pu-d9-fal19_week": "pu-d9 w",
        "agh-fal17_week": "agh w",
        "muni-pdfx-fal17_week": "muni-pdfx w",
        "muni-pdf-spr16c_week": "muni-pdf w",
        "lancs-yr23_term1_week": "lancs t1 w",
        "lancs-yr23_term2_week": "lancs t2 w",
    }
    out = name
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out.replace("_day", "d")


def overview_table(exact: pd.DataFrame) -> pd.DataFrame:
    paper = paper_exact(exact)
    best_obj = paper.groupby("instance_name")["objective_value"].min()
    rows: list[dict[str, object]] = []
    for (family, formulation), group in paper.groupby(["instance_family", "formulation"]):
        by_instance = group.groupby("instance_name")
        optimal = int(by_instance["status"].apply(lambda s: (s == "OPTIMAL").any()).sum())
        form_best = by_instance["objective_value"].min()
        best_incumbent = int(
            sum(
                np.isclose(value, best_obj.loc[instance], rtol=0, atol=OBJECTIVE_TOL)
                for instance, value in form_best.items()
            )
        )
        proof_times = []
        for _, inst_group in by_instance:
            solved = inst_group[inst_group["status"] == "OPTIMAL"]
            if not solved.empty:
                proof_times.append(float(solved["table_time_seconds"].min()))
        rows.append(
            {
                "Source": SOURCE_LABEL[family],
                "Formulation": FORMULATION_LABEL[formulation],
                "Instances": int(by_instance.ngroups),
                "Optimal": optimal,
                "Best incumbent": best_incumbent,
                "Median proof time (s)": round(float(np.median(proof_times)), 2),
            }
        )
    order = {"ITC 2019": 0, "Lancaster": 1, "MIQP": 0, "MIP": 1}
    out = pd.DataFrame(rows)
    out["_source_order"] = out["Source"].map(order)
    out["_form_order"] = out["Formulation"].map(order)
    return out.sort_values(["_source_order", "_form_order"]).drop(columns=["_source_order", "_form_order"])


def best_methods_table(exact: pd.DataFrame) -> pd.DataFrame:
    paper = paper_exact(exact)
    paper["method"] = paper.apply(method_code, axis=1)
    best_obj = paper.groupby("instance_name")["objective_value"].min()
    rows: list[dict[str, object]] = []
    instance_order = (
        paper[["instance_name", "num_lectures", "instance_family"]]
        .drop_duplicates()
        .assign(short=lambda d: d["instance_name"].map(short_instance_name))
        .assign(source_order=lambda d: d["instance_family"].map({"itc2019": 0, "lancs_yr23": 1}))
        .sort_values(["source_order", "short"])
    )
    for _, inst in instance_order.iterrows():
        name = inst["instance_name"]
        opt = float(best_obj.loc[name])
        candidates = paper[
            (paper["instance_name"] == name)
            & (paper["status"] == "OPTIMAL")
            & np.isclose(paper["objective_value"], opt, rtol=0, atol=OBJECTIVE_TOL)
        ].sort_values(["table_time_seconds", "method"])
        first = candidates.iloc[0]
        second = candidates.iloc[1] if len(candidates) > 1 else None
        third = candidates.iloc[2] if len(candidates) > 2 else None
        rows.append(
            {
                "Instance": short_instance_name(name),
                "|L|": int(inst["num_lectures"]),
                "UB": int(round(opt)),
                "Fastest method": first["method"],
                "Time (s)": round(float(first["table_time_seconds"]), 2),
                "Second method": second["method"] if second is not None else "-",
                "Second time (s)": round(float(second["table_time_seconds"]), 2)
                if second is not None
                else "-",
                "Third method": third["method"] if third is not None else "-",
                "Third time (s)": round(float(third["table_time_seconds"]), 2)
                if third is not None
                else "-",
            }
        )
    return pd.DataFrame(rows)


def method_summary_table(exact: pd.DataFrame) -> pd.DataFrame:
    paper = paper_exact(exact)
    paper["method"] = paper.apply(method_code, axis=1)
    best_obj = paper.groupby("instance_name")["objective_value"].min()
    paper["found_optimum"] = paper.apply(
        lambda row: row["status"] == "OPTIMAL"
        or (
            pd.notna(row["objective_value"])
            and np.isclose(
                row["objective_value"],
                best_obj.loc[row["instance_name"]],
                rtol=0,
                atol=OBJECTIVE_TOL,
            )
        ),
        axis=1,
    )
    fastest = (
        paper[paper["found_optimum"]]
        .groupby("instance_name")["table_time_seconds"]
        .min()
        .rename("fastest_optimum_time")
    )
    paper = paper.join(fastest, on="instance_name")
    paper["fastest_optimum"] = paper["found_optimum"] & np.isclose(
        paper["table_time_seconds"],
        paper["fastest_optimum_time"],
        rtol=0,
        atol=1e-7,
    )
    rows = []
    for method, group in paper.groupby("method", sort=True):
        rows.append(
            {
                "Method": method,
                "Found optimum": int(group["found_optimum"].sum()),
                "Proved optimality": int((group["status"] == "OPTIMAL").sum()),
                "Fastest optimum": int(group["fastest_optimum"].sum()),
                "Mean time (s)": round(float(group["table_time_seconds"].mean()), 2),
            }
        )
    combinations = (
        {
            "formulation": formulation,
            "biclique_enabled": biclique,
            "cardinality_enabled": cardinality,
        }
        for formulation in PAPER_FORMULATIONS
        for biclique in (False, True)
        for cardinality in (False, True)
    )
    order = {method_code(combination): index for index, combination in enumerate(combinations)}
    out = pd.DataFrame(rows)
    out["_order"] = out["Method"].map(order)
    return out.sort_values("_order").drop(columns="_order")


def root_diagnostics_table(exact: pd.DataFrame) -> pd.DataFrame:
    root = numeric_columns(load_workbook(ROOT_1800))
    root = root[root["compatibility_preprocess_mode"] == PAPER_PREPROCESS_MODE].copy()
    opt = (
        paper_exact(exact)
        .groupby("instance_name")["objective_value"]
        .min()
        .rename("optimum")
    )
    root = root.join(opt, on="instance_name")
    root["root_gap_pct"] = 100.0 * (root["optimum"] - root["lower_bound"]) / root["optimum"]
    root["root_gap_pct"] = root["root_gap_pct"].clip(lower=0.0)
    rows = []
    for biclique, group in root.groupby("biclique_enabled"):
        rows.append(
            {
                "Biclique": bool(biclique),
                "Rows": len(group),
                "Optimal root solves": int((group["status"] == "OPTIMAL").sum()),
                "Root-limit solves": int((group["status"] == "ROOT_LIMIT").sum()),
                "Time-limit solves": int((group["status"] == "TIME_LIMIT").sum()),
                "Mean root gap (%)": round(float(group["root_gap_pct"].mean()), 2),
                "Median root gap (%)": round(float(group["root_gap_pct"].median()), 2),
                "Max root gap (%)": round(float(group["root_gap_pct"].max()), 2),
            }
        )
    return pd.DataFrame(rows)


def preprocessing_attempt_summary(exact: pd.DataFrame) -> pd.DataFrame:
    """Summarize the archived light-preprocessing rows excluded from the paper."""
    methods = exact[exact["formulation"].isin(PAPER_FORMULATIONS)].copy()
    light = methods[methods["compatibility_preprocess_mode"] == "light"].copy()
    if light.empty:
        return pd.DataFrame()

    fastest = methods.groupby("instance_name")["table_time_seconds"].min()
    light_fastest = light.groupby("instance_name")["table_time_seconds"].min()
    fastest_instances = sum(
        np.isclose(value, fastest.loc[instance], rtol=0, atol=1e-7)
        for instance, value in light_fastest.items()
    )
    return pd.DataFrame(
        [
            {
                "Rows": len(light),
                "Instances": light["instance_name"].nunique(),
                "Fastest end-to-end instances": int(fastest_instances),
                "Mean setup time (s)": round(
                    float(light["compatibility_preprocess_wall_seconds"].mean()), 2
                ),
                "Median setup time (s)": round(
                    float(light["compatibility_preprocess_wall_seconds"].median()), 2
                ),
                "Max setup time (s)": round(
                    float(light["compatibility_preprocess_wall_seconds"].max()), 2
                ),
            }
        ]
    )


def cp_attempt_summary(exact: pd.DataFrame) -> pd.DataFrame:
    cp = exact[exact["formulation"] == "cp_sat"].copy()
    if cp.empty:
        return pd.DataFrame()
    paper = paper_exact(exact)
    best_obj = paper.groupby("instance_name")["objective_value"].min()
    cp_best = cp.groupby("instance_name")["objective_value"].min()
    rows = [
        {
            "Rows": len(cp),
            "Instances": cp["instance_name"].nunique(),
            "Proved optimality": int(cp.groupby("instance_name")["status"].apply(lambda s: (s == "OPTIMAL").any()).sum()),
            "Matched paper optimum": int(
                sum(
                    pd.notna(value)
                    and np.isclose(value, best_obj.loc[instance], rtol=0, atol=OBJECTIVE_TOL)
                    for instance, value in cp_best.items()
                )
            ),
            "Strictly better than paper optimum": int(
                sum(
                    pd.notna(value) and value < best_obj.loc[instance] - OBJECTIVE_TOL
                    for instance, value in cp_best.items()
                )
            ),
        }
    ]
    return pd.DataFrame(rows)


def write_or_print(name: str, table: pd.DataFrame, output_dir: Path | None) -> None:
    if output_dir is None:
        print(f"\n## {name}")
        print(table.to_string(index=False))
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.csv"
    table.to_csv(path, index=False)
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory for CSV outputs. If omitted, print tables to stdout.",
    )
    args = parser.parse_args()

    exact = load_exact_1800()
    write_or_print("results_overview", overview_table(exact), args.output_dir)
    write_or_print("best_methods", best_methods_table(exact), args.output_dir)
    write_or_print("method_summary", method_summary_table(exact), args.output_dir)
    write_or_print("root_diagnostics", root_diagnostics_table(exact), args.output_dir)
    write_or_print(
        "preprocessing_attempt_summary",
        preprocessing_attempt_summary(exact),
        args.output_dir,
    )
    write_or_print("cp_attempt_summary", cp_attempt_summary(exact), args.output_dir)


if __name__ == "__main__":
    main()
