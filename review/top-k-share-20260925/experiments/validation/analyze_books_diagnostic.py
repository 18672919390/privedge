"""Render the fixed Books diagnostic into an auditable Markdown report."""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/amazon_books_diagnostic'


def main():
    summary = json.loads((OUT/'summary.json').read_text(encoding='utf8'))
    paired = json.loads((OUT/'paired.json').read_text(encoding='utf8'))
    manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    payload = json.loads(Path(manifest['cache']).read_text(encoding='utf8'))
    def row(case, release='OLH', method='average', context='uniform'):
        return next(r for r in summary if (r['case'], r['release'], r['method'], r['context']) ==
                    (case, release, method, context))
    def fmt(r, metric):
        return f"{r[metric]:.3f} ± {r[metric+'_std']:.3f}"
    lines = ['# Books 类别域失败定位实验（2026-09-17）', '',
        '## 结论与下一步', '',
        '本轮 Books 类别域适合作为多源迁移的真实数据诊断场景，但尚不能作为所提融合方法稳定优于 average 的证据。',
        '基准类别 Oracle 候选覆盖 100%，ID Oracle 为 46%；聚合解决了大部分具体 ID 的头部候选断裂。',
        '基准 OLH 覆盖仅 26%；固定 ε=2、m=20，源用户增至 5,000/10,000 时覆盖为 54%/80%。',
        '固定 n=1,000，ε=4 时覆盖为 64%，而仅增大发布量至 50 时覆盖为 34%。主要瓶颈是当前样本/隐私条件下的候选发现；这不是对所有设置的理论结论。',
        'n=10,000 时 average Recall=72%，最近单源为 54%，显示多源信号有用。目录 censor-aware 同为 72%。',
        '目录 censor-aware 相对 average 的各配置 Recall 均值差为 −2 到 +4 个百分点，不能据此声称稳定优越或统计显著。',
        '建议保留该数据集，先把大域 LDP 候选发现与融合误差作为两个研究问题。提高 ε 会削弱隐私保证，不能仅因效果好而选 ε=4。',
        '如果研究范围限于既有发布摘要，优先研究可验证的先验可靠性、先验失配时回退，以及方法适用条件；不要用目标热度构造先验。',
        '若转向分层或改进源端候选发布，需要明确扩展研究范围并重新核算通信及隐私。下一阶段冻结设计后在未使用的年份划分或独立数据集确认，不再把 2013 当留出集。',
        '当前只有一个两源年份划分、五个重复种子，不能外推为所有真实业务，也没有测试已知未来信息不存在的在线部署。', '',
        '## 协议与信息边界', '',
        '- 固定 2011、2012 为源服务器，2013 为目标；k=10；所有配置共用 5 个种子。',
        '- 目标真值固定为全部 51,864 条保留事件，仅用于离线评估；不输入任何融合算法。',
        '- 源事件按年份独立随机排列取前 n 条，样本规模对照采用嵌套样本；发布量对照复用同一份 OLH 估计。',
        '- 全部年份中每用户仅保留一个 SHA-256 选择的合格正向事件（评分 4–5），再按年份分服务器。',
        '- 类别域由可用元数据定义，不按目标评论热度筛选；按标题精确连接，冲突标题排除。',
        '- 元数据类别列表排序后以固定标题哈希选一个类别；目录先验按映射后的标题数构建。',
        '- 当前元数据快照的历史公开性未证实；全时段用户选择也是回顾性离线队列，不是历史上线回放。',
        '- 无噪声 ORACLE 使用源样本真实频率，仅用于诊断；候选覆盖是对应候选集的 Recall 硬上限。',
        '- 2013 已用于探索；本轮不是独立留出确认，也没有根据结果筛选类别或调融合超参数。',
        '- OLH 使用 '+manifest['hash_backend']+'；每个源用户只生成一次 ε-LDP 报告。多个配置是替代实验，不能当作同时发布而忽略隐私组合。',
        '', '## 单因素结果', '',
        '以下为五个种子的均值 ± 样本标准差；不是置信区间。', '',
        '| 配置 (n, ε, m) | 类别 Oracle 覆盖 | ID Oracle 覆盖 | OLH 覆盖 | average Recall | 目录 censor Recall | average NDCG |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for case, n, epsilon, ratio in manifest['cases']:
        a, o, c = row(case), row(case, 'ORACLE'), row(case, method='censor_aware', context='catalog')
        lines.append(f'| {case} ({n}, {epsilon}, {ratio*10}) | {fmt(o, "candidate_recall_upper_bound")} | '
                     f'{fmt(o, "book_oracle_coverage")} | {fmt(a, "candidate_recall_upper_bound")} | '
                     f'{fmt(a, "recall")} | {fmt(c, "recall")} | {fmt(a, "ndcg")} |')
    lines += ['', '## 候选以外的质量与迁移', '',
              '| 配置 | 类别 Oracle 遗漏质量 | ID Oracle 遗漏质量 | OLH 遗漏质量 | 源目标平均 TV |',
              '|---|---:|---:|---:|---:|']
    for case, *_ in manifest['cases']:
        a, o = row(case), row(case, 'ORACLE')
        lines.append(f'| {case} | {o["candidate_miss_mass"]:.3f} | {o["book_oracle_miss_mass"]:.3f} | '
                     f'{a["candidate_miss_mass"]:.3f} | {a["source_target_tv_mean"]:.3f} |')
    lines += ['', '## 与 average 的配对差值', '',
              '各方法使用同一份源发布。latest_source 仅使用最近源，其输出仍按多源公共候选集合评估覆盖。',
              '两源条件下 trimmed 的 trim=0，等价于无修剪基线，不能视为鲁棒性证据。', '',
              '| 配置 | 方法/先验 | ΔRecall | Recall 胜/平/负 | ΔNDCG |',
              '|---|---|---:|---|---:|']
    for p in paired:
        lines.append(f'| {p["case"]} | {p["method"]}/{p["context"]} | {p["recall_delta"]:+.3f} | '
                     f'{p["recall_wins_ties_losses"]} | {p["ndcg_delta"]:+.4f} |')
    target = np.bincount(payload['events']['2013'], minlength=len(payload['labels']))
    ids = np.argsort(-target, kind='stable')[:10]
    lines += ['', '## 完整目标分布（仅评估）', '', '| 类别 | 用户事件数 | 比例 |', '|---|---:|---:|']
    for i in ids:
        lines.append(f'| {payload["labels"][i]} | {target[i]} | {target[i]/target.sum():.3%} |')
    lines += ['', '头部集中意味着较高 NDCG 不一定对应较高 Top-10 Recall，两者必须同时报告。', '',
              '## 数据审计', '', '```json', json.dumps(payload['audit'], indent=2), '```', '',
              '仅代表能匹配元数据、用户 ID 非空且满足正向评分条件的用户事件，不能外推为全部 Books 用户。', '',
              '## 复现', '', '在 top-k 目录运行：', '', '```powershell',
              '.runtime/python/python.exe experiments/validation/amazon_books_diagnostic.py',
              '.runtime/python/python.exe experiments/validation/analyze_books_diagnostic.py', '```', '',
              '原始分种子结果、manifest.json、summary.json、paired.json 位于 outputs/amazon_books_diagnostic。',
              '本轮固定完整目标并更新了配对抽样流，因此不能与旧三种子抽样目标结果直接作增益比较。']
    (ROOT/'docs/BOOKS_DIAGNOSTIC_20260917.md').write_text('\n'.join(lines)+'\n', encoding='utf8')
    print('Wrote docs/BOOKS_DIAGNOSTIC_20260917.md')


if __name__ == '__main__':
    main()
