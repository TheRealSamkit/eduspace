"""
Survey analysis for the EduSpace project (Stage 1-2: Empathise + Define evidence).

Usage:
    python survey_analysis.py responses.csv [output_folder]

Input: the Google Forms CSV export (with header row). Column ORDER is what matters:
    Timestamp, [Consent], Year, Branch, Sources, Minutes, Fail-frequency,
    5 pain-point grid rows, Satisfaction, Frustration, Shared-before,
    Credit-motivation, Copyright-worry, Would-use, Device, Open-1, Open-2

Output: statistics printed to the terminal + PNG charts + results.txt in the output folder.
Everything is computed from the CSV; nothing is typed in by hand.

Requires: pandas, numpy, scipy, statsmodels, matplotlib
"""
import sys
import io
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from statsmodels.stats.proportion import proportion_confint

warnings.filterwarnings("ignore")

# Colours match the app palette (petrol primary, brass accent, neutral grays)
PETROL, BRASS, GRAY = "#1F6B7D", "#A47D1E", "#A3A3A3"
ALPHA = 0.05
SEED = 42

NAMES = ["ts", "consent", "year", "branch", "sources", "mins", "fail",
         "p_spread", "p_find", "p_outdated", "p_reliable", "p_buried",
         "sat", "frus", "shared", "incent", "copyright", "use", "device",
         "open_frus", "open_feat"]

PAIN_LABELS = {
    "p_spread": "Material spread across too many places",
    "p_find": "Hard to find notes by subject and semester",
    "p_outdated": "Material outdated or incomplete",
    "p_reliable": "Hard to judge whether material is reliable",
    "p_buried": "Files buried in chats or need re-sending",
}


def load(path):
    """Read the Google Forms CSV and give columns short names."""
    raw = pd.read_csv(path)
    # The Consent column only exists if the form had a consent checkbox item.
    if len(raw.columns) == 20:
        names = [n for n in NAMES if n != "consent"]
    else:
        names = NAMES
    raw.columns = names
    df = raw.copy()
    # Likert answers arrive as "4 Agree" / "3 - Sometimes": keep the leading digit.
    for c in ["fail", "p_spread", "p_find", "p_outdated", "p_reliable", "p_buried"]:
        df[c] = df[c].astype(str).str.extract(r"(\d)")[0].astype(float)
    for c in ["mins", "sat", "frus", "incent", "copyright", "use"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def describe(x):
    """Mean, median, SD, IQR, min, max for one column."""
    x = x.dropna()
    q1, q3 = np.percentile(x, [25, 75])
    return dict(n=len(x), mean=x.mean(), median=np.median(x), sd=x.std(ddof=1),
                q1=q1, q3=q3, min=x.min(), max=x.max())


def t_ci(x, level=0.95):
    """t-based confidence interval for a mean."""
    x = x.dropna()
    h = stats.sem(x) * stats.t.ppf((1 + level) / 2, len(x) - 1)
    return x.mean() - h, x.mean() + h


def boot_median_ci(x, n=10000):
    """Bootstrap 95% CI for the median (used for skewed 'minutes')."""
    rng = np.random.default_rng(SEED)
    x = x.dropna().values
    med = [np.median(rng.choice(x, len(x))) for _ in range(n)]
    return tuple(np.percentile(med, [2.5, 97.5]))


def prop(k, n):
    """Proportion with exact Clopper-Pearson 95% CI."""
    lo, hi = proportion_confint(k, n, alpha=ALPHA, method="beta")
    return k / n, lo, hi


def wilcoxon_vs(x, mid, alternative):
    """One-sample Wilcoxon signed-rank test of x against the neutral midpoint."""
    d = x - mid
    d = d[d != 0]
    return stats.wilcoxon(d, alternative=alternative)


def main(csv_path, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()

    def P(*a):
        print(*a)
        print(*a, file=buf)

    df = load(csv_path)
    n = len(df)
    P(f"=== SAMPLE ===\nn = {n} responses")
    P("Year:", df.year.value_counts().to_dict())
    P("Branch:", df.branch.value_counts().to_dict())
    P("Device:", df.device.value_counts().to_dict())
    P("Shared notes before:", df.shared.value_counts().to_dict())

    # ---- Sources (multi-select) ----
    cnt = Counter()
    for s in df.sources.dropna():
        for item in [t.strip() for t in s.split(",") if t.strip()]:
            cnt[item] += 1
    P("\nSources (count of respondents, multi-select):", cnt.most_common())

    # ---- Descriptives ----
    P("\n=== DESCRIPTIVE STATISTICS ===")
    for c, label in [("mins", "Minutes to find material"), ("fail", "Fail frequency (1-5)"),
                     ("sat", "Satisfaction (1-5)"), ("frus", "Frustration (1-5)"),
                     ("incent", "Credits motivate sharing (1-5)"),
                     ("copyright", "Copyright worry (1-5)"), ("use", "Would use platform (1-5)")]:
        d = describe(df[c])
        P(f"{label}: mean={d['mean']:.2f}, median={d['median']:.1f}, SD={d['sd']:.2f}, "
          f"IQR={d['q1']:.1f}-{d['q3']:.1f}, range={d['min']:.0f}-{d['max']:.0f}, "
          f"mode={df[c].mode().tolist()}")

    # ---- Confidence intervals ----
    P("\n=== 95% CONFIDENCE INTERVALS ===")
    for c, label in [("sat", "Satisfaction mean"), ("frus", "Frustration mean"), ("use", "Would-use mean")]:
        lo, hi = t_ci(df[c])
        P(f"{label}: {df[c].mean():.2f} (95% CI {lo:.2f} to {hi:.2f})")
    lo, hi = boot_median_ci(df.mins)
    P(f"Minutes median: {df.mins.median():.1f} (bootstrap 95% CI {lo:.1f} to {hi:.1f})")
    P(f"Minutes mean:   {df.mins.mean():.1f} (skewed by outlier of {df.mins.max():.0f} min; prefer the median)")
    out_ok = df.mins[df.mins < df.mins.max()]
    P(f"Minutes mean without the single highest value: {out_ok.mean():.1f}, median {out_ok.median():.1f}")

    # ---- Assumption checks ----
    P("\n=== NORMALITY (Shapiro-Wilk) ===")
    for c in ["sat", "frus", "mins"]:
        s = stats.shapiro(df[c])
        P(f"{c}: W={s.statistic:.3f}, p={s.pvalue:.4f} -> "
          f"{'NOT normal, use non-parametric tests' if s.pvalue < ALPHA else 'no evidence against normality'}")

    # ---- Pre-planned baseline hypothesis test ----
    P("\n=== PRE-PLANNED BASELINE TEST (satisfaction vs neutral = 3) ===")
    P("H0: median satisfaction = 3   H1: median satisfaction < 3   alpha = 0.05")
    w = wilcoxon_vs(df.sat, 3, "less")
    P(f"Wilcoxon signed-rank (one-sided, less): W={w.statistic:.1f}, p={w.pvalue:.4f}")
    w2 = wilcoxon_vs(df.sat, 3, "two-sided")
    P(f"Two-sided check: W={w2.statistic:.1f}, p={w2.pvalue:.4f}")
    P("Satisfaction distribution:", df.sat.value_counts().sort_index().to_dict())
    pct_dis = (df.sat <= 2).mean() * 100
    pct_sat = (df.sat >= 4).mean() * 100
    P(f"Dissatisfied (1-2): {pct_dis:.0f}%   Satisfied (4-5): {pct_sat:.0f}%")
    P("RESULT:", "H0 rejected" if w.pvalue < ALPHA else
      "FAIL TO REJECT H0. There is no evidence that overall satisfaction is below neutral.")

    # ---- Exploratory tests (label as exploratory in the report) ----
    P("\n=== EXPLORATORY TESTS (not pre-planned: report as exploratory) ===")
    wf = wilcoxon_vs(df.frus, 3, "greater")
    P(f"Frustration above neutral? Wilcoxon (one-sided): W={wf.statistic:.1f}, p={wf.pvalue:.4f}")
    wu = wilcoxon_vs(df.use, 3, "greater")
    P(f"Would-use above neutral? Wilcoxon (one-sided): W={wu.statistic:.1f}, p={wu.pvalue:.4f}")
    P("Note: several tests were run, so treat borderline p-values (0.01-0.05) with caution.")

    # ---- Correlations ----
    P("\n=== SPEARMAN CORRELATIONS ===")
    pc = list(PAIN_LABELS)
    df["pain_mean"] = df[pc].mean(axis=1)
    pairs = [("mins", "frus", "Minutes vs frustration"),
             ("mins", "sat", "Minutes vs satisfaction"),
             ("fail", "frus", "Fail frequency vs frustration"),
             ("pain_mean", "frus", "Mean pain-point score vs frustration"),
             ("incent", "use", "Credit motivation vs would-use")]
    for a, b, label in pairs:
        r = stats.spearmanr(df[a], df[b])
        strength = "weak" if abs(r.statistic) < 0.3 else "moderate" if abs(r.statistic) < 0.6 else "strong"
        P(f"{label}: rho={r.statistic:.2f}, p={r.pvalue:.4f} ({strength}, "
          f"{'significant' if r.pvalue < ALPHA else 'not significant'})")
    P("Correlation is not causation, and small samples give wide uncertainty.")

    # ---- Pain-point ranking ----
    P("\n=== PAIN-POINT RANKING (agree = 4 or 5) ===")
    rows = []
    for c in pc:
        k = int((df[c] >= 4).sum())
        p, lo, hi = prop(k, n)
        rows.append((PAIN_LABELS[c], k, p, lo, hi, df[c].mean()))
    rows.sort(key=lambda r: (-r[1], -r[5]))
    for lab, k, p, lo, hi, m in rows:
        P(f"{lab}: {k}/{n} = {p*100:.0f}% (95% CI {lo*100:.0f}-{hi*100:.0f}%), mean severity {m:.2f}")

    # ---- Willingness ----
    P("\n=== STATED WILLINGNESS (agree = 4 or 5) ===")
    wil = []
    for c, label in [("use", "Would use such a platform"),
                     ("incent", "More willing to share if earning credits"),
                     ("copyright", "Worry about uploading copyrighted material")]:
        k = int((df[c] >= 4).sum())
        p, lo, hi = prop(k, n)
        neutral = int((df[c] == 3).sum())
        P(f"{label}: {k}/{n} = {p*100:.0f}% (95% CI {lo*100:.0f}-{hi*100:.0f}%); neutral = {neutral}")
        wil.append((label, k, p, lo, hi))
    k_f = int((df.frus >= 4).sum())
    p_f, lo_f, hi_f = prop(k_f, n)
    P(f"Frustration rated 4-5: {k_f}/{n} = {p_f*100:.0f}% (95% CI {lo_f*100:.0f}-{hi_f*100:.0f}%)")

    # ---- Open-ended answers ----
    P("\n=== OPEN-ENDED: biggest frustration ===")
    for t in df.open_frus.dropna():
        P(" -", str(t).strip())
    P("\n=== OPEN-ENDED: feature requests ===")
    for t in df.open_feat.dropna():
        P(" -", str(t).strip().replace("\n", " "))

    # ---- Charts ----
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})

    # 1. Pain points with CI
    fig, ax = plt.subplots(figsize=(9, 4.2))
    labs = [r[0] for r in rows][::-1]
    pct = [r[2] * 100 for r in rows][::-1]
    err = [[(r[2] - r[3]) * 100 for r in rows][::-1], [(r[4] - r[2]) * 100 for r in rows][::-1]]
    ax.barh(labs, pct, xerr=err, color=PETROL, capsize=4, ecolor=GRAY)
    for i, v in enumerate(pct):
        ax.text(2, i, f"{v:.0f}%", va="center", color="white", fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_xlabel(f"% who agree or strongly agree (n = {n}, bars = 95% CI)")
    ax.set_title("What makes finding study material difficult?", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(out / "chart_pain_points.png", dpi=200); plt.close(fig)

    # 2. Minutes: histogram + box plot
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.8), gridspec_kw={"width_ratios": [2, 1]})
    a1.hist(df.mins, bins=[0, 5, 10, 15, 20, 30, 45, 60, 90, 270], color=PETROL, edgecolor="white")
    a1.axvline(df.mins.median(), color=BRASS, ls="--", lw=2)
    a1.text(df.mins.median() + 3, a1.get_ylim()[1] * 0.9, f"median {df.mins.median():.0f} min", color=BRASS)
    a1.set_xlabel("Minutes to find reliable material for one topic"); a1.set_ylabel("Respondents")
    a1.set_title("Time to find material", loc="left", fontweight="bold")
    bp = a2.boxplot(df.mins, vert=True, patch_artist=True, widths=0.5)
    bp["boxes"][0].set(facecolor="#D9EEF2", edgecolor=PETROL)
    bp["medians"][0].set(color=BRASS, lw=2)
    a2.set_xticks([]); a2.set_ylabel("Minutes")
    fig.tight_layout(); fig.savefig(out / "chart_minutes.png", dpi=200); plt.close(fig)

    # 3. Satisfaction and frustration distributions
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    for ax, c, title, col in [(axes[0], "sat", "Satisfaction with current methods", PETROL),
                              (axes[1], "frus", "Frustration with finding material", BRASS)]:
        counts = df[c].value_counts().reindex(range(1, 6), fill_value=0)
        ax.bar(counts.index, counts.values, color=col)
        for x, v in zip(counts.index, counts.values):
            ax.text(x, v + 0.2, str(v), ha="center")
        ax.axvline(3, color=GRAY, ls=":")
        ax.set_xticks(range(1, 6)); ax.set_xlabel("1 = lowest, 5 = highest")
        ax.set_title(title, loc="left", fontweight="bold", fontsize=11)
    axes[0].set_ylabel("Respondents")
    fig.tight_layout(); fig.savefig(out / "chart_sat_frus.png", dpi=200); plt.close(fig)

    # 4. Scatter minutes vs frustration
    r = stats.spearmanr(df.mins, df.frus)
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    jitter = np.random.default_rng(SEED).uniform(-0.12, 0.12, n)
    ax.scatter(df.mins, df.frus + jitter, color=PETROL, alpha=0.8)
    ax.set_xlabel("Minutes to find material"); ax.set_ylabel("Frustration (1-5)")
    ax.set_title(f"Longer searches, more frustration (Spearman rho = {r.statistic:.2f}, p = {r.pvalue:.3f})",
                 loc="left", fontweight="bold", fontsize=10)
    fig.tight_layout(); fig.savefig(out / "chart_correlation.png", dpi=200); plt.close(fig)

    # 5. Sources
    top = cnt.most_common(7)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.barh([t[0] for t in top][::-1], [t[1] for t in top][::-1], color=PETROL)
    for i, v in enumerate([t[1] for t in top][::-1]):
        ax.text(v + 0.2, i, str(v), va="center")
    ax.set_xlabel(f"Respondents (n = {n}, multiple answers allowed)")
    ax.set_title("Where students find study material today", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(out / "chart_sources.png", dpi=200); plt.close(fig)

    # 6. Willingness with CI
    fig, ax = plt.subplots(figsize=(8, 3.2))
    wl = [w_[0] for w_ in wil][::-1]
    wp = [w_[2] * 100 for w_ in wil][::-1]
    we = [[(w_[2] - w_[3]) * 100 for w_ in wil][::-1], [(w_[4] - w_[2]) * 100 for w_ in wil][::-1]]
    ax.barh(wl, wp, xerr=we, color=[GRAY, BRASS, PETROL], capsize=4, ecolor="#525252")
    for i, v in enumerate(wp):
        ax.text(2, i, f"{v:.0f}%", va="center", color="white", fontweight="bold")
    ax.set_xlim(0, 100); ax.set_xlabel(f"% who agree or strongly agree (n = {n}, bars = 95% CI)")
    ax.set_title("Stated willingness (not actual behaviour)", loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(out / "chart_willingness.png", dpi=200); plt.close(fig)

    (out / "results.txt").write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nSaved 6 charts and results.txt to {out.resolve()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python survey_analysis.py responses.csv [output_folder]")
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "survey_output")