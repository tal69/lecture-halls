#!/usr/bin/env python3
"""Regenerate Section 4.2 bar-chart figures with colors + hatching for dual readability."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

os.makedirs('figures', exist_ok=True)

# ──────────────────────────────────────────────────────────
# Figure 1: Optimal solve counts and median solver runtimes
# Data from Table 2 (tab:results-overview)
# ──────────────────────────────────────────────────────────

sources = ['ITC 2019', 'Lancaster']
formulations = ['MIQP', 'MIP', 'CP']

optimal_counts = {
    'MIQP': [17, 10],
    'MIP':  [23, 10],
    'CP':   [16, 10],
}
total_instances = [25, 10]

median_times = {
    'MIQP': [0.71, 27.92],
    'MIP':  [0.08,  0.60],
    'CP':   [45.03, 45.83],
}

colors = ['#f4a582', '#92c5de', '#a6d96a']
hatches = ['///', '...', 'xxx']

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))

x = np.arange(len(sources))
width = 0.25

for i, form in enumerate(formulations):
    ax1.bar(
        x + i * width - width, optimal_counts[form], width,
        label=form, color=colors[i], hatch=hatches[i],
        edgecolor='black', linewidth=0.8,
    )

ax1.set_ylabel('Optimal solves', fontsize=11)
ax1.set_xticks(x)
ax1.set_xticklabels(sources, fontsize=11)
ax1.legend(fontsize=10)
ax1.set_ylim(0, 28)
for j, tot in enumerate(total_instances):
    ax1.axhline(y=tot, xmin=(j * 0.5) + 0.05, xmax=(j * 0.5) + 0.45,
                color='black', linestyle='--', linewidth=0.7, alpha=0.5)

for i, form in enumerate(formulations):
    ax2.bar(
        x + i * width - width, median_times[form], width,
        label=form, color=colors[i], hatch=hatches[i],
        edgecolor='black', linewidth=0.8,
    )

ax2.set_ylabel('Median solver time (s)', fontsize=11)
ax2.set_yscale('log')
ax2.set_xticks(x)
ax2.set_xticklabels(sources, fontsize=11)
ax2.legend(fontsize=10)

fig.tight_layout()
fig.savefig('figures/section42_runtime_summary.pdf')
print("Figure 1 saved: figures/section42_runtime_summary.pdf")
plt.close(fig)


# ──────────────────────────────────────────────────────────
# Figure 3: Root shortfalls and root solver times
# Data from Table 3 (tab:root-gap)
# ──────────────────────────────────────────────────────────

models = ['Weak', 'Strong']
colors_root = ['#f4a582', '#92c5de']
hatches_root = ['///', '...']

shortfalls = {
    'Weak':   [5.76, 20.67],
    'Strong': [0.09,  0.01],
}

root_times = {
    'Weak':   [1.95, 55.25],
    'Strong': [0.09,  0.62],
}

fig2, (ax3, ax4) = plt.subplots(1, 2, figsize=(10, 4.2))

width2 = 0.3
for i, model in enumerate(models):
    ax3.bar(
        x + i * width2 - width2 / 2, shortfalls[model], width2,
        label=model, color=colors_root[i], hatch=hatches_root[i],
        edgecolor='black', linewidth=0.8,
    )

ax3.set_ylabel('Mean root shortfall (%)', fontsize=11)
ax3.set_xticks(x)
ax3.set_xticklabels(sources, fontsize=11)
ax3.legend(fontsize=10)

for i, model in enumerate(models):
    ax4.bar(
        x + i * width2 - width2 / 2, root_times[model], width2,
        label=model, color=colors_root[i], hatch=hatches_root[i],
        edgecolor='black', linewidth=0.8,
    )

ax4.set_ylabel('Median root solver time (s)', fontsize=11)
ax4.set_yscale('log')
ax4.set_xticks(x)
ax4.set_xticklabels(sources, fontsize=11)
ax4.legend(fontsize=10)

fig2.tight_layout()
fig2.savefig('figures/section42_root_summary.pdf')
print("Figure 3 saved: figures/section42_root_summary.pdf")
plt.close(fig2)
