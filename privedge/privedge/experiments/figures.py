"""Report figures drawn only from the registered runs (same source as the console's experiment centre).

Usage: python -m privedge.experiments.figures [--out DIR]   (needs matplotlib; see requirements-figures.txt)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ..server.evidence import evidence  # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "competition_entry" / "docs" / "v4" / "figures"
DATASETS = ["meituan_trd", "olist_brazil", "massive_steps"]
EPS = ["0.5", "1.0", "2.0", "4.0"]
RED, AMBER, GREEN, BLUE, GREY = "#d64545", "#e0a100", "#1f9d6b", "#3b6fd8", "#8a8f98"

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"],
    "axes.unicode_minus": False, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    "savefig.dpi": 200, "savefig.bbox": "tight",
})


def _top_legend(fig, ax, title: str) -> None:
    handles, labels = ax.get_legend_handles_labels()
    fig.subplots_adjust(top=0.78)
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.93), ncol=len(labels), frameon=False, fontsize=9)
    fig.suptitle(title, y=1.0)


def _save(fig, out: Path, name: str, sources: list[str]) -> None:
    fig.text(0.01, -0.06, "数据来源：runs/…/" + "；".join(sources), fontsize=7, color=GREY, ha="left", va="top")
    for ext in ("png", "svg"):
        fig.savefig(out / f"{name}.{ext}")
    plt.close(fig)
    print(out / f"{name}.png")


def utility(ev: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    for ax, name in zip(axes, DATASETS):
        u = ev["utility"][name]
        x = [float(e) for e in EPS]
        ax.plot(x, [u["curve"]["nonprivate_source_mean"][e]["recall"] for e in EPS], "--", color=GREY, label="非隐私参照（源平均）")
        ax.plot(x, [u["curve"]["variance_weighted"][e]["recall"] for e in EPS], "s-", color=BLUE, ms=7, mfc="none", label="团队原始方差加权")
        ax.plot(x, [u["curve"]["privedge"][e]["recall"] for e in EPS], "o-", color=GREEN, ms=4, label="PrivEdge（全部防御）")
        ax.set_xscale("log", base=2)
        ax.set_xticks(x, ["0.5", "1", "2", "4"])
        ax.set_title(u["title"])
        ax.set_xlabel("ε")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Recall@10")
    _top_legend(fig, axes[0], "隐私—效用：新区域 Top-10 召回随 ε 变化（UTILITY_V1，m=20，全部源）")
    _save(fig, out, "fig_utility", [ev["utility"][n]["run_id"] for n in DATASETS])


def sensitivity(ev: dict, out: Path) -> None:
    u = ev["utility"]["meituan_trd"]
    x = [float(e) for e in EPS]
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    for m, color in zip(("10", "20", "40"), (RED, BLUE, GREEN)):
        a.plot(x, [u["top_m"][m][e] for e in EPS], "o-", color=color, label=f"m={m}")
    counts = [3, 5, 10]
    for e, color in (("1.0", BLUE), ("2.0", GREEN)):
        b.plot(counts, [u["sources"][s][e] for s in ("3", "5", "all")], "o-", color=color, label=f"ε={float(e):g}")
    a.set_xscale("log", base=2)
    a.set_xticks(x, ["0.5", "1", "2", "4"])
    a.set_xlabel("ε")
    b.set_xticks(counts, ["3", "5", "10（全部）"])
    b.set_xlabel("源区域数量")
    for ax, title in ((a, "发布长度 Top-m（全部源）"), (b, "源区域数量（m=20）")):
        ax.set_title(title)
        ax.grid(alpha=0.3)
        ax.legend(frameon=False, fontsize=8)
    a.set_ylabel("Recall@10（拒答记 0）")
    fig.suptitle("参数敏感性（美团 TRD）", y=1.02)
    _save(fig, out, "fig_sensitivity", [u["run_id"]])


SCEN = [("mga_1src_b0.02", "伪造\n2%"), ("mga_1src_b0.05", "伪造\n5%"), ("mga_1src_b0.10", "伪造\n10%"),
        ("mga_2src_b0.05", "2 源伪造\n5%"), ("compromised_1src", "1 源\n被攻破"), ("compromised_2src", "2 源\n被攻破")]


def security(ev: dict, out: Path, epsilon: float = 1.0) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), sharey=True)
    for ax, name in zip(axes, DATASETS):
        rows = [r for r in ev["security"][name]["rows"] if r["epsilon"] == epsilon]
        get = lambda s, d: next(r["attack_success"] for r in rows if r["scenario"] == s and r["defense"] == d)  # noqa: E731
        idx = range(len(SCEN))
        ax.bar([i - 0.2 for i in idx], [get(s, "D0_none") for s, _ in SCEN], 0.4, color=RED, label="无防御（团队原始方差加权）")
        defended = [get(s, "D3_both") for s, _ in SCEN]
        ax.bar([i + 0.2 for i in idx], defended, 0.4, color=GREEN, label="两层防御")
        for i, v in zip(idx, defended):
            ax.text(i + 0.2, v + 0.015, f"{v:.2f}", ha="center", va="bottom", fontsize=7, color=GREEN)
        ax.set_xticks(list(idx), [lbl for _, lbl in SCEN], fontsize=8)
        ax.set_title(ev["security"][name]["title"])
        ax.set_ylim(0, 1.08)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("攻击成功率")
    _top_legend(fig, axes[0], f"投毒攻防：3 个冷门品类进入新区域 Top-10 的比例（SECURITY_V2，ε={epsilon:g}）")
    _save(fig, out, "fig_security", [ev["security"][n]["run_id"] for n in DATASETS])


HIJACK = [("hijack_1src", "1 源权重劫持"), ("demote_1src", "劫持 + 扣热门"), ("hijack_2src", "2 源权重劫持")]


def hijack(ev: dict, out: Path, epsilon: float = 1.0) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), sharey=True)
    for ax, name in zip(axes, DATASETS):
        rows = [r for r in ev["hijack"][name]["rows"] if r["epsilon"] == epsilon]
        get = lambda s, d: next(r["ndcg"] for r in rows if r["scenario"] == s and r["defense"] == d)  # noqa: E731
        idx = range(len(HIJACK))
        for off, (d, label, color) in zip((-0.27, 0, 0.27), (("D0_none", "无防御", RED), ("D3_both", "截尾 + t=2", AMBER),
                                                             ("D4_capped", "+ 权重封顶 κ=2（主线）", GREEN))):
            ax.bar([i + off for i in idx], [get(s, d) for s, _ in HIJACK], 0.27, color=color, label=label)
        ax.axhline(get("clean", "D3_both"), ls="--", color=GREY, lw=1, label="无攻击水平")
        ax.set_xticks(list(idx), [lbl for _, lbl in HIJACK])
        ax.set_title(ev["hijack"][name]["title"])
        ax.set_ylim(0, 1.05)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("NDCG@10")
    _top_legend(fig, axes[0], f"自适应权重劫持（SECURITY_V4，新种子，ε={epsilon:g}）")
    _save(fig, out, "fig_hijack", [ev["hijack"][n]["run_id"] for n in DATASETS])


def overhead(ev: dict, out: Path) -> None:
    rows = ev["overhead"]["rows"]
    users = sorted({int(r["users"]) for r in rows})
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.4))
    pick = lambda n, d: next(r for r in rows if int(r["users"]) == n and int(r["domain"]) == d)  # noqa: E731
    a.plot(users, [pick(n, 156)["raw_reports_bytes"] for n in users], "o-", color=RED, label="原始 LDP 报告")
    a.plot(users, [pick(n, 156)["release_envelope_bytes"] for n in users], "o-", color=GREEN, label="签名摘要信封")
    a.set_xscale("log")
    a.set_yscale("log")
    a.set_xlabel("每区域用户数")
    a.set_ylabel("字节")
    a.set_title("通信量（156 类）")
    a.legend(frameon=False, fontsize=8)
    for d, color in zip((71, 156, 500), (BLUE, AMBER, RED)):
        b.plot(users, [pick(n, d)["publisher_release_total_ms"] for n in users], "o-", color=color, label=f"{d} 类")
    b.set_xscale("log")
    b.set_yscale("log")
    b.set_xlabel("每区域用户数")
    b.set_ylabel("毫秒")
    b.set_title("发布端耗时（含伪造用户过滤）")
    b.legend(frameon=False, fontsize=8)
    for ax in (a, b):
        ax.grid(alpha=0.3, which="both")
    _save(fig, out, "fig_overhead", [ev["overhead"]["run_id"]])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    ev = json.loads(json.dumps(evidence()))
    for draw in (utility, sensitivity, security, hijack, overhead):
        draw(ev, out)


if __name__ == "__main__":
    main()
