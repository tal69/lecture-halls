"""Generate appendix scatter plot: best-known gap (bk%) vs number of lectures |L|.

Reads the precomputed /tmp/bkgaps.txt file (columns: instance, |L|, |P|,
bk_MIQP, bk_MIP, bk_CP) and produces
figures/section_appendix_bkgap_scatter.pdf with three series on a symlog y-axis.
"""

import os

import matplotlib.pyplot as plt
import numpy as np

SRC = "/tmp/bkgaps.txt"
OUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "figures",
    "section_appendix_bkgap_scatter.pdf",
)


def load_data(path: str):
    Ls, bk_miqp, bk_mip, bk_cp = [], [], [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            L = int(parts[1])
            Ls.append(L)
            bk_miqp.append(float(parts[3]))
            bk_mip.append(float(parts[4]))
            bk_cp.append(float(parts[5]))
    return (
        np.array(Ls, dtype=float),
        np.array(bk_miqp),
        np.array(bk_mip),
        np.array(bk_cp),
    )


def main():
    L, g_miqp, g_mip, g_cp = load_data(SRC)

    # Jitter MIQP and MIP slightly so their coincident points (usually 0%) are
    # distinguishable from CP points drawn at the same location.
    rng = np.random.default_rng(seed=0)
    jitter_mip = rng.uniform(-0.015, 0.015, size=len(L))
    jitter_miqp = rng.uniform(-0.015, 0.015, size=len(L))

    fig, ax = plt.subplots(figsize=(6.6, 4.1))

    ax.scatter(
        L,
        g_cp,
        s=50,
        marker="^",
        facecolors="none",
        edgecolors="tab:green",
        linewidths=1.3,
        label="CP",
        zorder=3,
    )
    ax.scatter(
        L,
        np.maximum(g_mip + jitter_mip, 0.0),
        s=36,
        marker="s",
        facecolors="none",
        edgecolors="tab:blue",
        linewidths=1.3,
        label="MIP",
        zorder=4,
    )
    ax.scatter(
        L,
        np.maximum(g_miqp + jitter_miqp, 0.0),
        s=28,
        marker="o",
        facecolors="none",
        edgecolors="tab:red",
        linewidths=1.3,
        label="MIQP",
        zorder=5,
    )

    ax.set_yscale("symlog", linthresh=0.05)
    ax.set_ylim(-0.02, 80)
    ax.set_yticks([0, 0.05, 0.5, 5, 50])
    ax.set_yticklabels(["0", "0.05", "0.5", "5", "50"])
    ax.set_xlabel(r"Number of lectures $|L|$")
    ax.set_ylabel(r"Best-known gap (\%)")
    ax.grid(True, which="both", linestyle=":", linewidth=0.4, alpha=0.6)
    ax.legend(loc="upper left", frameon=True, fontsize=9)

    plt.tight_layout()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    plt.savefig(OUT, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
