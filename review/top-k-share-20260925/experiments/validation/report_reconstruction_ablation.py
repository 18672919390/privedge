"""Render reconstruction ablations and seed-level paired comparisons."""
import csv
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/two_stage_reconstruction_ablation'


def main():
    syn = json.loads((OUT/'synthetic_summary.json').read_text(encoding='utf8'))
    books = json.loads((OUT/'books_summary.json').read_text(encoding='utf8'))
    rows = list(csv.DictReader((OUT/'synthetic_results.csv').open(encoding='utf8')))
    grouped = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[(r['context_concentration'],r['stage'],r['variant'])][r['seed']].append(float(r['recall']))
    paired = []
    comparisons=[('full_shift_002','full_shift_0'),('full_shift_0','candidate_tail'),
                 ('candidate_tail','candidate_tail_reported_only'),('direct','candidate_tail'),
                 ('direct','full_shift_0')]
    for concentration in ['25','75','250']:
        for stage in ['equal','target_mix','target_mix_full_metric']:
            for baseline,variant in comparisons:
                a=grouped[(concentration,stage,baseline)]; b=grouped[(concentration,stage,variant)]
                delta=np.array([np.mean(b[s])-np.mean(a[s]) for s in sorted(a)])
                rng=np.random.default_rng(718)
                ci=np.quantile(delta[rng.integers(len(delta),size=(5000,len(delta)))].mean(axis=1),[.025,.975])
                paired.append(dict(context=int(concentration),stage=stage,baseline=baseline,variant=variant,
                    seed_count=len(delta),delta=float(delta.mean()),ci95=ci.tolist(),
                    note='Exploratory bootstrap, seed means over two targets; not multiplicity corrected'))
    (OUT/'seed_paired.json').write_text(json.dumps(paired,indent=2),encoding='utf8')
    lines=['# 源重建错配消融结果', '',
           '这是在已经查看过的种子上的探索性排查，不是新的独立确认。模拟 20 个种子，两个目标、三档上下文；Books 两档样本量各五个种子。', '',
           '## 修改与控制', '',
           '- full_shift_002：上一版均匀参考、0.02 迁移容差。',
           '- full_shift_0：仅移除迁移容差；发布点仍按相对逆方差加权。',
           '- candidate_tail：候选并集加一个尾部总质量；不为尾部伪造观测。',
           '- reported_only：移除未发布候选损失，其余权重保持不变。',
           '- 第二阶段同时运行旧完整域距离和候选加尾部距离，两者使用相同 ridge=0.1。',
           '- 压缩不仅减少变量，也改变先验惩罚：原全域尾部均匀时二次损失为 (t-N/d)^2/N，新实现为 (t-N/d)^2。因此不能把效果单独归因于降维。',
           '- 所有参数都是建模选择，阈值软上界不是 LDP 置信界，更不是精确选择似然。', '',
           '## 模拟目标 Recall', '',
           '| 方法 | 等权 | 弱/旧距离 | 中/旧距离 | 强/旧距离 | 弱/压缩距离 | 中/压缩距离 | 强/压缩距离 |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    variants=list(dict.fromkeys(r['variant'] for r in syn))
    def get(v,c,s):return next(r for r in syn if r['variant']==v and r['context_concentration']==c and r['stage']==s)
    for v in variants:
        values=[get(v,25,'equal')['recall']]+[get(v,c,s)['recall'] for s in ['target_mix_full_metric','target_mix'] for c in [25,75,250]]
        lines.append('| '+v+' | '+' | '.join(f'{x:.4f}' for x in values)+' |')
    lines+=['','## 源重建误差（只用隐藏源做离线评估）','','| 方法 | 候选 L1 | 全域 L1 | 源 Top-10 Recall |','|---|---:|---:|---:|']
    for v in variants:
        r=get(v,25,'equal')
        lines.append(f"| {v} | {r['source_candidate_l1']:.4f} | {r['source_full_l1']:.4f} | {r['source_topk_recall']:.4f} |")
    lines+=['','direct 的误差使用原始零填充摘要，未归一化；上一轮的零填充 L1 使用归一化向量，不能跨表直接比较。','','## Books 等权融合','','| 用户数 | 方法 | Recall ± SD | NDCG |','|---:|---|---:|---:|']
    for r in books:
        lines.append(f"| {r['users']} | {r['variant']} | {r['recall']:.3f} ± {r['recall_std']:.3f} | {r['ndcg']:.4f} |")
    lines+=['','## 解释与下一步','',
        '移除迁移容差改善了模拟源频率误差；源重建自身不应默认保留目标迁移容差。候选加尾部进一步减小候选 L1，但没有建立最终 Top-k 优势。',
        '未发布软上界开关结果相同，说明该区间损失在这组数据上没有带来有效排序信息；不能把它描述为已经纠正了 Top-m 选择偏差。',
        '频率拟合改善不等于最终排序改善。源混合权重会受到质量分配和距离尺度影响；第二阶段的 ridge 即使数值固定，其相对作用也可能变化。',
        '建议暂保留直接摘要目标加权作为强基线，不将此重建升级为正式主方法。下一次若继续重建，应先验证选择机制的统计模型或尾部正则的作用，避免继续无目的调参。',
        'Books 当前目录不含可验证的年份目标特征，只评估第一阶段。任何模型仍受相同候选覆盖上限约束。','',
        '## 复现','', '```powershell',
        '.runtime/python/python.exe experiments/validation/two_stage_reconstruction_ablation.py',
        '.runtime/python/python.exe experiments/validation/report_reconstruction_ablation.py','```','',
        '原始逐种子结果、汇总、代码 SHA256 与配对结果位于 outputs/two_stage_reconstruction_ablation。seed_paired.json 先在种子内平均两个目标，再计算探索性 bootstrap 区间；没有把两个目标当成独立种子。']
    (ROOT/'docs/RECONSTRUCTION_ABLATION_RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('Wrote docs/RECONSTRUCTION_ABLATION_RESULTS.md')


if __name__=='__main__':main()
