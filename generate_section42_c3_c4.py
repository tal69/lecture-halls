"""Generate the C3 violin figure.

For each of the 35 instances and each of the three formulations (MIQP, MIP,
CP), take the BEST solution found across the eight cut/preprocess settings
and compute its gap against the best-known lower bound
$LB^\\star$ = \\max over every run for that instance. Then draw one violin per
formulation showing the distribution of those 35 best-per-instance values.

Outputs:
  figures/section42_gap_dispersion.pdf
"""

import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
ITC_XLSX = os.path.join(BASE, "Numerical experiment results", "full_factorial_300s.xlsx")
LAN_XLSX = os.path.join(
    BASE, "Numerical experiment results", "lancs_yr23_full_factorial_300s.xlsx"
)
RELAX_XLSX = os.path.join(BASE, "Numerical experiment results", "relaxations_factorial_300s.xlsx")
OUT_VIOLIN = os.path.join(BASE, "figures", "section42_gap_dispersion.pdf")

FORMULATION_ORDER = ["quadratic_miqp", "linearized_milp", "cp_sat"]
FORMULATION_LABEL = {
    "quadratic_miqp": "MIQP",
    "linearized_milp": "MIP",
    "cp_sat": "CP",
}
FORMULATION_COLOR = {
    "quadratic_miqp": "tab:red",
    "linearized_milp": "tab:blue",
    "cp_sat": "tab:green",
}


def load_exact() -> pd.DataFrame:
    a = pd.read_excel(ITC_XLSX)
    b = pd.read_excel(LAN_XLSX)
    return pd.concat([a, b], ignore_index=True)


def load_all_for_lb() -> pd.DataFrame:
    """Load every run that contributes to LB* (exact runs + root-relaxation
    runs). Each instance's LB* is the max lower bound observed anywhere."""
    frames = [pd.read_excel(ITC_XLSX), pd.read_excel(LAN_XLSX)]
    if os.path.exists(RELAX_XLSX):
        frames.append(pd.read_excel(RELAX_XLSX))
    return pd.concat(frames, ignore_index=True)


def compute_best_per_instance(exact: pd.DataFrame, all_runs: pd.DataFrame) -> pd.DataFrame:
    """For each (instance, formulation) pick the smallest objective across the
    eight cut/preprocess settings, then compute bk% against instance-level
    LB* taken over every run (exact + root)."""

    # Instance-level LB*
    lb_cols = [c for c in ("best_global_lower_bound", "lower_bound") if c in all_runs.columns]
    # Prefer `best_global_lower_bound` where available, otherwise fall back to
    # `lower_bound`.
    all_runs["_lb"] = all_runs["best_global_lower_bound"].fillna(all_runs["lower_bound"])
    lb_star = (
        all_runs.groupby("instance_name")["_lb"].max().reset_index().rename(columns={"_lb": "LB_star"})
    )

    # Best objective per (instance, formulation) across the 8 settings
    e = exact.dropna(subset=["objective_value"]).copy()
    best = (
        e.groupby(["instance_name", "instance_family", "formulation"])["objective_value"].min().reset_index()
        .rename(columns={"objective_value": "best_obj"})
    )
    best = best.merge(lb_star, on="instance_name", how="left")
    best["bk_pct"] = 100.0 * (best["best_obj"] - best["LB_star"]) / best["LB_star"]
    # Guard against any negative floating-point residuals
    best["bk_pct"] = best["bk_pct"].clip(lower=0.0)
    return best


def violin_plot(best: pd.DataFrame, path: str) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 4.0))

    positions = np.arange(1, len(FORMULATION_ORDER) + 1)
    data = []
    for f in FORMULATION_ORDER:
        sub = best[best["formulation"] == f].sort_values("instance_name")
        vals = sub["bk_pct"].values
        data.append(vals)

    parts = ax.violinplot(
        dataset=data,
        positions=positions,
        widths=0.78,
        showmedians=False,
        showextrema=False,
    )
    for i, body in enumerate(parts["bodies"]):
        body.set_facecolor(FORMULATION_COLOR[FORMULATION_ORDER[i]])
        body.set_edgecolor("black")
        body.set_alpha(0.30)
        body.set_linewidth(0.6)

    # IQR bar, 5-95 whisker, median marker
    for i, f in enumerate(FORMULATION_ORDER):
        vals = data[i]
        q25, q50, q75 = np.percentile(vals, [25, 50, 75])
        p05, p95 = np.percentile(vals, [5, 95])
        x = positions[i]
        ax.plot([x, x], [p05, p95], color="black", linewidth=0.9, zorder=3)
        ax.plot([x, x], [q25, q75], color="black", linewidth=3.0, zorder=4)
        ax.plot([x], [q50], marker="o", color="white",
                markeredgecolor="black", markersize=4.5, zorder=6)

    # Individual points. ITC = filled circle, Lancaster = open square.
    rng = np.random.default_rng(seed=0)
    for i, f in enumerate(FORMULATION_ORDER):
        sub = best[best["formulation"] == f]
        for _, row in sub.iterrows():
            family = row["instance_family"]
            y = row["bk_pct"]
            x = positions[i] + rng.uniform(-0.10, 0.10)
            if family == "itc2019":
                ax.plot(
                    x, y, marker="o", markersize=4.5,
                    markerfacecolor=FORMULATION_COLOR[f],
                    markeredgecolor="black", markeredgewidth=0.4,
                    linestyle="None", zorder=5,
                )
            else:
                ax.plot(
                    x, y, marker="s", markersize=4.2,
                    markerfacecolor="white",
                    markeredgecolor=FORMULATION_COLOR[f], markeredgewidth=1.0,
                    linestyle="None", zorder=5,
                )

    # Max annotation
    for i, f in enumerate(FORMULATION_ORDER):
        m = float(np.max(data[i]))
        ax.annotate(
            f"max {m:.2f}%",
            xy=(positions[i], m),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            color=FORMULATION_COLOR[f],
        )

    ax.set_xticks(positions)
    ax.set_xticklabels([FORMULATION_LABEL[f] for f in FORMULATION_ORDER])
    ax.set_ylabel(r"Best-known gap of the best solution found (\%)")
    ax.set_yscale("symlog", linthresh=0.05)
    ax.set_ylim(-0.02, 80)
    ax.set_yticks([0, 0.05, 0.5, 5, 50])
    ax.set_yticklabels(["0", "0.05", "0.5", "5", "50"])
    ax.grid(True, axis="y", which="both", linestyle=":", linewidth=0.4, alpha=0.6)

    # Legend for the two markers
    from matplotlib.lines import Line2D

    legend_handles = [
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor="0.5", markeredgecolor="black",
               markersize=6, label="ITC 2019 (25)"),
        Line2D([0], [0], marker="s", color="w",
               markerfacecolor="white", markeredgecolor="0.25",
               markeredgewidth=1.2, markersize=6, label="Lancaster (10)"),
    ]
    ax.legend(handles=legend_handles, loc="upper left", frameon=True, fontsize=9)

    plt.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {path}")


def report_stats(best: pd.DataFrame) -> None:
    print("\nBest-per-instance bk% (across 8 settings, per formulation):")
    rows = []
    for f in FORMULATION_ORDER:
        v = best[best["formulation"] == f]["bk_pct"].values
        rows.append({
            "formulation": FORMULATION_LABEL[f],
            "n": len(v),
            "mean": float(np.mean(v)),
            "sd": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0,
            "median": float(np.median(v)),
            "q25": float(np.percentile(v, 25)),
            "q75": float(np.percentile(v, 75)),
            "max": float(np.max(v)),
            "nonzero": int((v > 1e-6).sum()),
        })
    out = pd.DataFrame(rows)
    print(out.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main():
    exact = load_exact()
    all_runs = load_all_for_lb()
    best = compute_best_per_instance(exact, all_runs)
    violin_plot(best, OUT_VIOLIN)
    report_stats(best)


if __name__ == "__main__":
    main()
