"""Regenerate figures/section42_performance_profile.pdf.

X-axis is now the certified optimality gap in percent (0%-130%), so the plot
is an empirical CDF of per-instance certified gaps rather than a
reparameterized performance profile. Data source: the representative block of
the full factorial (light preprocessing, cardinality OFF, biclique ON --
except for MIQP on ITC which uses the weaker pairwise distance model).
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
ITC_XLSX = os.path.join(BASE, "Numerical experiment results", "full_factorial_300s.xlsx")
LAN_XLSX = os.path.join(BASE, "Numerical experiment results", "lancs_yr23_full_factorial_300s.xlsx")
OUT = os.path.join(BASE, "figures", "section42_performance_profile.pdf")

FORMULATION_ORDER = ["quadratic_miqp", "linearized_milp", "cp_sat"]
FORMULATION_LABEL = {
    "quadratic_miqp": "MIQP",
    "linearized_milp": "MIP",
    "cp_sat": "CP",
}
STYLE = {
    "quadratic_miqp": dict(color="#d6604d", linestyle="--", linewidth=2),
    "linearized_milp": dict(color="#4393c3", linestyle="-", linewidth=2),
    "cp_sat": dict(color="#5aae61", linestyle="-.", linewidth=2),
}


def representative_mask(row) -> bool:
    """Representative block: light preprocess, cardinality off, biclique on
    except for MIQP on ITC where the weaker pairwise model wins."""
    if row["compatibility_preprocess_mode"] != "light":
        return False
    if row["cardinality_enabled"]:
        return False
    if row["formulation"] == "quadratic_miqp" and row["instance_family"] == "itc2019":
        return row["biclique_enabled"] == False  # noqa: E712
    return row["biclique_enabled"] == True  # noqa: E712


def main() -> None:
    df = pd.concat([pd.read_excel(ITC_XLSX), pd.read_excel(LAN_XLSX)], ignore_index=True)
    rep = df[df.apply(representative_mask, axis=1)].copy()

    # Use the conservative gap convention gap = (UB - LB)/LB (in percent), to
    # match Table~\ref{tab:results-overview}.
    rep = rep.copy()
    rep["cons_gap_pct"] = 100.0 * (rep["objective_value"] - rep["lower_bound"]) / rep["lower_bound"]

    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    for f in FORMULATION_ORDER:
        gaps = rep[rep["formulation"] == f]["cons_gap_pct"].dropna().values
        gaps = np.sort(gaps)
        n_total = int((rep["formulation"] == f).sum())
        n_nan = int(rep[rep["formulation"] == f]["cons_gap_pct"].isna().sum())
        # ECDF with right-continuous steps, capped at (n_total-n_nan)/n_total
        x = np.concatenate(([0.0], gaps))
        y = np.concatenate(([0.0], np.arange(1, len(gaps) + 1) / n_total))
        label = FORMULATION_LABEL[f]
        if n_nan:
            label += f" ({n_nan} run without incumbent)" if n_nan == 1 else f" ({n_nan} runs without incumbent)"
        ax.step(x, y, where="post", label=label, **STYLE[f])

    ax.set_xlim(0, 130)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(r"Certified optimality gap (\%)", fontsize=12)
    ax.set_ylabel(r"Fraction of instances", fontsize=12)
    ax.legend(loc="lower right", fontsize=10, frameon=True)
    ax.grid(True, which="both", ls=":", alpha=0.5)
    plt.tight_layout()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    plt.savefig(OUT)
    plt.close(fig)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
