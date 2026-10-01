"""Write the corrected Yelp category experiment report."""
import csv
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/yelp_categories_v3_six'


def summary(rows):
    groups=defaultdict(list)
    for row in rows: groups[(row['users'],row['release'],row['context'],row['method'])].append(row)
    out=[]
    for key,records in groups.items():
        item=dict(zip(['users','release','context','method'],key))
        for metric in ['recall','ndcg','candidate_recall_upper_bound','candidate_miss_mass','source_target_tv_mean']:
            values=np.asarray([float(r[metric]) for r in records])
            item[metric]=float(values.mean()); item[metric+'_std']=float(values.std(ddof=1))
        out.append(item)
    return out


def get(s, users, release, context, method):
    return next(x for x in s if str(x['users'])==str(users) and x['release']==release
                and x['context']==context and x['method']==method)


def main():
    rows=list(csv.DictReader((OUT/'results.csv').open(encoding='utf8')))
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    s=summary(rows)
    report={'status':'Exploratory corrected Yelp category experiment; all six cities were inspected during development.',
            'rows':len(rows),'summary':s}
    (OUT/'summary_recomputed.json').write_text(json.dumps(s,indent=2),encoding='utf8')
    lines=['# Yelp 类别域目标迁移实验（修正版）', '',
        '## 结论', '',
        '本轮适合继续保留 Yelp，但结果支持的是“类别域可迁移、目录上下文有弱信号、主方法优势依赖样本量”，还不能声称稳定优于 average。',
        '商户 ID 版本没有被纳入本轮：跨城市商户不重叠，那个任务构造会让源候选无法迁移。',
        '本轮只使用类别事件。商户类别按固定 SHA-256 选一个；用户在全部城市、全部年份中只保留一个固定哈希的评分 4–5 事件。',
        '目标真值是全局去重后目标城市的完整事件分布，仅用于离线评价。目录上下文只来自商户元数据，不使用目标评论数量、评分或文本。',
        '均匀上下文下，context-aware 方法显式回退到 average；否则会把均匀向量误当成目标信号而产生任意源排序。',
        '正确目录和交换目录使用完全相同的源发布；交换对照检验上下文是否真的带有目标信息。', '',
        '## 配置', '',
        f"- 城市：{', '.join(manifest['cities'])}；每个城市轮流作为目标，其余五城为源。",
        f"- 用户数：{manifest['users']}；epsilon={manifest['epsilon']}；k={manifest['top_k']}；发布 m=20；五个种子。",
        '- OLH 是可部署发布；ORACLE 使用抽样源的真实频率，只用于分解 LDP/候选损失。',
        '- 目标上下文：uniform、correct_catalog、swapped_catalog。', '',
        '## OLH 结果（均值 ± 五种子/六目标的样本标准差）', '',
        '| 源用户数 | 上下文 | average | context-weighted | censor-aware | robust | 候选覆盖上限 |',
        '|---:|---|---:|---:|---:|---:|---:|']
    for users in manifest['users']:
        for context in ['uniform','correct_catalog','swapped_catalog']:
            a=get(s,users,'OLH',context,'average')
            cw=get(s,users,'OLH',context,'context_weighted')
            ca=get(s,users,'OLH',context,'censor_aware')
            rb=get(s,users,'OLH',context,'robust_context')
            def f(x): return f"{x['recall']:.3f} ± {x['recall_std']:.3f}"
            lines.append(f"| {users} | {context} | {f(a)} | {f(cw)} | {f(ca)} | {f(rb)} | {a['candidate_recall_upper_bound']:.3f} |")
    lines += ['', '## 目录排序基线与无噪声诊断', '',
              '| 源用户数 | 发布 | correct_catalog context-only（候选内） | average | censor-aware | robust | 候选覆盖 |',
              '|---:|---|---:|---:|---:|---:|---:|']
    for users in manifest['users']:
        for release in ['OLH','ORACLE']:
            co=get(s,users,release,'correct_catalog','context_only')
            av=get(s,users,release,'correct_catalog','average')
            ca=get(s,users,release,'correct_catalog','censor_aware')
            rb=get(s,users,release,'correct_catalog','robust_context')
            lines.append(f"| {users} | {release} | {co['recall']:.3f} ± {co['recall_std']:.3f} | "
                         f"{av['recall']:.3f} ± {av['recall_std']:.3f} | {ca['recall']:.3f} ± {ca['recall_std']:.3f} | "
                         f"{rb['recall']:.3f} ± {rb['recall_std']:.3f} | {av['candidate_recall_upper_bound']:.3f} |")
    paired=json.loads((OUT/'paired_context_summary.json').read_text(encoding='utf8'))
    lines += ['', '## 上下文配对差值', '',
              'correct_catalog 与 swapped_catalog 使用同一源发布；差值按目标城市和种子配对后汇总。', '',
              '| 用户数 | 发布 | 方法 | Recall correct−swapped | Recall correct−uniform |',
              '|---:|---|---|---:|---:|']
    for users in manifest['users']:
        for release in ['OLH','ORACLE']:
            for method in ['context_weighted','censor_aware','robust_context','context_only']:
                p=next(x for x in paired if x['users']==users and x['release']==release
                       and x['metric']=='recall' and x['method']==method)
                lines.append(f"| {users} | {release} | {method} | {p['correct_minus_swapped']:+.3f} | {p['correct_minus_uniform']:+.3f} |")
    lines += ['', '## 如何解释', '',
        '- 2,000 用户、OLH：average Recall=0.417，correct_catalog censor-aware=0.457（+4.0 个百分点）；context-weighted=0.430（+1.3 个百分点）。',
        '- 10,000 用户、OLH：average=0.663，correct_catalog censor-aware=0.673（+1.0 个百分点）；context-weighted=0.657（−0.7 个百分点）。',
        '- 2,000 用户的候选覆盖上限为 0.600；10,000 用户为 0.890。低样本时不能把融合排序误判为主要瓶颈。',
        '- 无噪声 ORACLE 的候选覆盖约 0.973–0.977，correct_catalog censor-aware/robust 约 0.747/0.760（2,000）和 0.767/0.783（10,000）。因此 LDP 候选发现确实造成损失，但上下文方法也仍只带来小幅改善。',
        '- correct−swapped 对 OLH censor-aware 为 +0.010（两档均值），context-weighted 为 −0.007；目录的目标特异性信号弱，不能声称强目标识别。context-only 候选内基线更高，说明目录本身在这个协议中是强基线。',
        '- Yelp 类别实验适合继续做真实验证；它不支持“当前 censor-aware 稳定优于 average”的强结论。主方法若要形成贡献，需要解释低样本候选缺失、目录供给与用户行为偏差，并在未开发城市上确认。',
        '- `context_full_domain` 是允许公开上下文扩展候选的诊断，不是候选并集内的可比方法；表格没有把它当作主结果。',
        '- 目录是当前元数据快照，历史上是否已公开未证实；用户事件是“留下正向评论的用户事件”，不能称为城市居民消费偏好。', '',
        '## 复现与输出', '',
        '```powershell',
        '.runtime/python/python.exe experiments/validation/audit_available_data.py',
        '.runtime/python/python.exe experiments/validation/yelp_categories_v3.py --output-dir outputs/yelp_categories_v3_six --cities "Philadelphia | PA" "Tucson | AZ" "Tampa | FL" "Indianapolis | IN" "Nashville | TN" "New Orleans | LA"',
        '.runtime/python/python.exe experiments/validation/report_yelp_categories_v3.py', '```', '',
        '原始逐目标结果、manifest、摘要及上下文配对结果位于 outputs/yelp_categories_v3_six。']
    (ROOT/'docs/YELP_CATEGORIES_V3_RESULTS_20260920.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('Wrote docs/YELP_CATEGORIES_V3_RESULTS_20260920.md')


if __name__=='__main__': main()
