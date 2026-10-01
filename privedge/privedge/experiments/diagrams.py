"""Architecture and release-protocol diagrams for the report (matplotlib only, no external tools).

Usage: python -m privedge.experiments.diagrams [--out DIR]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from .figures import OUT  # noqa: E402  (also applies the shared font settings)

INK, SOFT, ACCENT, OK, WARN, BAD = "#1f2937", "#eef2ff", "#4f46e5", "#1f9d6b", "#e0a100", "#d64545"


def _box(ax, x, y, w, h, title, lines=(), face=SOFT, edge=ACCENT):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=face, ec=edge, lw=1.3))
    ax.text(x + w / 2, y + h - 0.16, title, ha="center", va="top", fontsize=10.5, weight="bold", color=INK)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.48 - i * 0.26, line, ha="center", va="top", fontsize=8, color=INK)


def _arrow(ax, a, b, text="", color=INK, style="-|>", rad=0.0, dy=0.1):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, color=color, lw=1.2,
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + dy, text, ha="center", va="bottom", fontsize=7.5, color=color)


def architecture(out: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 6.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    for i, y in enumerate((4.6, 3.1, 1.6)):
        _box(ax, 0.2, y, 1.9, 1.15, f"用户终端 ×N", ["本地 OLH 扰动", "原始品类不出设备"])
        _box(ax, 2.8, y, 2.4, 1.15, f"区域发布者 S{i + 1}" if i < 2 else "区域发布者 Sn",
             ["频率估计 + 伪造用户过滤", "只发布 Top-m 摘要"])
        _arrow(ax, (2.1, y + 0.57), (2.8, y + 0.57), "LDP 报告")
    ax.text(1.15, 1.3, "…", ha="center", fontsize=14, color=INK)
    _box(ax, 5.9, 3.55, 2.3, 1.9, "签名信封与账本", ["Ed25519 签名（含窗口号）", "(主体, 角色) 密钥注册表",
                                              "哈希链账本：登记前验签", "按窗口顺序组合记账"], face="#fff7e6", edge=WARN)
    for y in (4.6, 3.1, 1.6):
        _arrow(ax, (5.2, y + 0.57), (5.9, 4.5), "", color=WARN)
    _box(ax, 5.9, 0.6, 2.3, 2.3, "攻击者", ["伪造用户（MGA）", "被攻破发布者：注入 /", "谎报方差 / 负频率 / 多摘要",
                                         "网络：篡改 / 重放 / 冒充", "第三方：代扣预算"], face="#fdecec", edge=BAD)
    _box(ax, 8.9, 3.3, 2.1, 2.4, "目标网关", ["验签 + 角色", "窗口 / 域 / 格式", "账本值核对", "同源多摘要拒收",
                                         "→ 拒收并给原因码"], face="#ecfdf5", edge=OK)
    _arrow(ax, (8.2, 4.5), (8.9, 4.5), "", color=WARN)
    _box(ax, 8.9, 0.6, 2.1, 2.3, "鲁棒融合", ["留一共识截尾（下限 0）", "支持规则 t=2（定理 1）", "权重封顶 κ=2（定理 2）",
                                         "方差加权 Top-10"], face="#ecfdf5", edge=OK)
    _arrow(ax, (9.95, 3.3), (9.95, 2.9), "", color=OK)
    _box(ax, 11.4, 3.3, 1.5, 2.4, "三态决策", ["正常", "降级", "拒答", "+ 原因码", "+ 审计记录"])
    _arrow(ax, (11.0, 2.7), (11.4, 3.6), "", color=OK)
    _box(ax, 11.4, 0.6, 1.5, 2.3, "控制台", ["REST + WebSocket", "5 个视图", "离线评估器", "（唯一可读真值）"],
         face="#f3f4f6", edge="#6b7280")
    _arrow(ax, (12.15, 3.3), (12.15, 2.9), "", color="#6b7280")
    for y in (1.2, 2.2):
        _arrow(ax, (8.2, y), (8.9, y), "", color=BAD, style="-|>")
    _arrow(ax, (7.05, 2.9), (7.05, 3.55), "", color=BAD)
    ax.text(6.5, 6.0, "PrivEdge 系统总体框架", ha="center", fontsize=13, weight="bold", color=INK)
    for ext in ("png", "svg"):
        fig.savefig(out / f"fig_architecture.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(out / "fig_architecture.png")


def protocol(out: Path) -> None:
    actors = ["用户终端", "区域发布者 S", "密钥注册表", "账本", "目标网关 T", "审计方"]
    xs = [0.8 + i * 2.1 for i in range(len(actors))]
    steps = [
        (0, 1, "1. OLH(x_u; ε) 报告", INK),
        (1, 1, "2. 估计 + 伪造用户过滤 → Top-m (i, f_i, Var_i)", INK),
        (1, 3, "3. env = Sign_sk(S, window, domain, ε, n, items)", WARN),
        (3, 2, "4. 查 (S, 角色=source) 公钥并验签", WARN),
        (3, 3, "5. spent(S, window) + ε ≤ ε_max？追加哈希链条目", WARN),
        (1, 4, "6. 发送 env", INK),
        (4, 2, "7. 验签 + 角色；窗口 ∈ 当前窗口；域哈希", OK),
        (4, 3, "8. 核对账本中 record_id 的摘要值", OK),
        (4, 4, "9. 同源多摘要 → 全部拒收；格式检查", OK),
        (4, 4, "10. 截尾(下限 0) + 支持 t=2 + 权重封顶 → Top-10 + 三态", OK),
        (5, 3, "11. verify_chain()：任何改动定位到首个断点", ACCENT),
    ]
    height = 1.2 + 0.62 * len(steps)
    fig, ax = plt.subplots(figsize=(13, height * 0.72))
    ax.set_xlim(0, xs[-1] + 0.9)
    ax.set_ylim(0, height)
    ax.axis("off")
    for x, name in zip(xs, actors):
        ax.add_patch(FancyBboxPatch((x - 0.75, height - 0.75), 1.5, 0.5, boxstyle="round,pad=0.02", fc=SOFT, ec=ACCENT))
        ax.text(x, height - 0.5, name, ha="center", va="center", fontsize=10, weight="bold", color=INK)
        ax.plot([x, x], [0.2, height - 0.75], color="#9ca3af", lw=0.8, ls="--")
    for k, (a, b, text, color) in enumerate(steps):
        y = height - 1.25 - k * 0.62
        if a == b:
            ax.add_patch(FancyArrowPatch((xs[a], y + 0.1), (xs[a], y - 0.2), connectionstyle="arc3,rad=-1.4",
                                         arrowstyle="-|>", mutation_scale=10, color=color, lw=1.1))
            ax.text(xs[a] + 0.3, y - 0.05, text, ha="left", va="center", fontsize=8, color=color)
        else:
            _arrow(ax, (xs[a], y), (xs[b], y), text, color=color, dy=0.04)
    ax.text((xs[0] + xs[-1]) / 2, height + 0.15, "签名摘要发布与准入协议（每个窗口）", ha="center", fontsize=13,
            weight="bold", color=INK)
    for ext in ("png", "svg"):
        fig.savefig(out / f"fig_protocol.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(out / "fig_protocol.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    architecture(out)
    protocol(out)


if __name__ == "__main__":
    main()
