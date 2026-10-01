"""Paired descriptive comparisons for the two-stage exploratory runs."""
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def paired(records, keys, method, baseline):
    grouped = defaultdict(dict)
    for row in records:
        grouped[tuple(row[k] for k in keys)][row['method']] = row
    deltas = []
    for group in grouped.values():
        if method in group and baseline in group:
            deltas.append(float(group[method]['recall'])-float(group[baseline]['recall']))
    values=np.asarray(deltas)
    return dict(method=method,baseline=baseline,units=len(values),recall_delta=float(values.mean()),
                recall_delta_std=float(values.std(ddof=1)),
                wins_ties_losses=[int((values>1e-12).sum()),int((abs(values)<=1e-12).sum()),int((values < -1e-12).sum())])


def main():
    synthetic=list(csv.DictReader((ROOT/'outputs/two_stage_synthetic/results.csv').open(encoding='utf8')))
    books=list(csv.DictReader((ROOT/'outputs/two_stage_books/results.csv').open(encoding='utf8')))
    comparisons=[('reconstructed_equal','direct_equal'),('direct_target_mix','direct_equal'),
                 ('reconstructed_target_mix','direct_target_mix'),('direct_target_mix','context_only'),
                 ('reconstructed_target_mix','context_only'),
                 ('reconstructed_target_mix','reconstructed_swapped_context')]
    synthetic_report=[]
    for concentration in ['25','75','250']:
        scoped=[r for r in synthetic if r['context_concentration']==concentration]
        # Each target is a paired observation; dependence within seeds remains explicit.
        for method,baseline in comparisons:
            synthetic_report.append(dict(context_concentration=int(concentration),
                **paired(scoped,['seed','target'],method,baseline)))
    books_report=[]
    for case in ['users_1000','users_10000']:
        scoped=[r for r in books if r['case']==case]
        books_report.append(dict(case=case,**paired(scoped,['seed'],'reconstructed_average','direct_average')))
    report={'status':'Exploratory descriptive paired differences; target pairs within a seed are not independent.',
            'synthetic':synthetic_report,'books':books_report}
    (ROOT/'outputs/two_stage_synthetic/paired.json').write_text(json.dumps(report['synthetic'],indent=2),encoding='utf8')
    (ROOT/'outputs/two_stage_books/paired.json').write_text(json.dumps(report['books'],indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
