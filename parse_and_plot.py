import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

tex_file = "main.tex"
with open(tex_file, 'r') as f:
    lines = f.readlines()

data = []
in_itc = False
in_lan = False

for line in lines:
    if r"\begin{tabular}{@{}lrr rrr rrr rrr@{}}" in line:
        pass 
    if "agh w4d1" in line:
        in_itc = True
    if "lancs t1 w13d1" in line:
        in_lan = True

    if in_itc or in_lan:
        if line.strip() == r"\hline":
            if in_itc: in_itc = False
            if in_lan: in_lan = False
            continue

        parts = line.split('&')
        if len(parts) >= 12:
            def parse_time(s):
                s = s.replace(r'\\', '').replace('\n', '').strip()
                s = s.replace('$', '').replace('^', '').replace(r'\dagger', '').replace(r'\ddagger', '').replace(r'\ast', '')
                try:
                    return float(s)
                except ValueError:
                    return 300.0

            def parse_gap(s):
                s = s.strip()
                try:
                    return float(s)
                except ValueError:
                    return 100.0

            mipq_gap = parse_gap(parts[4])
            mipq_t = parse_time(parts[5])
            if mipq_gap > 1e-4: mipq_t = np.inf
            
            mip_gap = parse_gap(parts[7])
            mip_t = parse_time(parts[8])
            if mip_gap > 1e-4: mip_t = np.inf
            
            cp_gap = parse_gap(parts[10])
            cp_t = parse_time(parts[11])
            if cp_gap > 1e-4: cp_t = np.inf
            
            data.append((mipq_t, mip_t, cp_t))

# Convert to numpy
all_times = np.array(data).T # shape is (3, 35)

num_problems = all_times.shape[1]

# min_times over solvers
min_times = np.min(all_times, axis=0)

# ratios
ratios = np.zeros_like(all_times)
for i in range(3):
    for p in range(num_problems):
        if all_times[i, p] == np.inf:
            ratios[i, p] = np.inf
        else:
            ratios[i, p] = all_times[i, p] / max(min_times[p], 0.001)

def compute_profile(r, taus):
    return np.array([np.sum(r <= tau) / len(r) for tau in taus])

taus = np.logspace(0, 3, 1000)
prof_mipq = compute_profile(ratios[0], taus)
prof_mip = compute_profile(ratios[1], taus)
prof_cp = compute_profile(ratios[2], taus)

plt.figure(figsize=(6, 4.5))

plt.step(taus, prof_mip, label='MIP', linestyle='-', linewidth=2, color='#1f77b4', where='post')
plt.step(taus, prof_mipq, label='MIQP', linestyle='--', linewidth=2, color='#ff7f0e', where='post')
plt.step(taus, prof_cp, label='CP', linestyle='-.', linewidth=2, color='#2ca02c', where='post')

plt.xscale('log')
plt.xlim(1, 1000)
plt.ylim(0, 1.05)
plt.xlabel(r'Performance ratio $\tau$', fontsize=12)
plt.ylabel(r'Fraction of instances solved to optimality', fontsize=12)
plt.legend(loc='lower right', fontsize=11)
plt.grid(True, which="both", ls="--", alpha=0.5)
plt.tight_layout()

os.makedirs('figures', exist_ok=True)
plt.savefig('figures/section42_performance_profile.pdf')
print("Profile plotted and saved to figures/section42_performance_profile.pdf")
