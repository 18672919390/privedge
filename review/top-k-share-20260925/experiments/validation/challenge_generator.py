"""Frozen first-pass challenge sweeps for the parameterized generator.

This is an exploratory factor screen. It intentionally uses three seeds; only
factors surviving this screen should enter the 12/20-seed confirmatory runs.
"""
from dataclasses import replace
import csv
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from experiment import ExperimentConfig, run
from simulation import make_problem


def cases(base):
    levels=[]
    for name, values, field in (
        ('sparsity',(4.,24.,96.),'target_concentration'),
        ('latent_shape',(.4,.9,1.6),'latent_exponent'),
        ('source_shape',(.7,1.08,1.6),'source_exponent'),
        ('migration',(0.,.15,.5),'source_mix_min'),
    ):
        levels.extend((name,value,replace(base,**{field:value})) for value in values)
    for condition in ('clean','noisy','misleading','outdated'):
        levels.append(('context',condition,replace(base,context_condition=condition)))
    return levels


def main():
    output=ROOT/'outputs/challenge_generator_v4'; output.mkdir(parents=True,exist_ok=True)
    seeds=(2026091501,2026091502,2026091503)
    base=ExperimentConfig(domain=128,users_per_server=1500,server_count=6,top_k=10,
                          epsilon=2.,rounds=1,mechanisms=('OLH','MIXED'),context_quality=.5)
    rows=[]
    for factor,value,config in cases(base):
        for seed in seeds:
            result=make_problem(config.domain,config.server_count,config.context_quality,
                np.random.default_rng(seed),context_condition=config.context_condition,
                source_condition=config.source_condition,affected_source_fraction=config.affected_source_fraction,
                target_concentration=config.target_concentration,latent_exponent=config.latent_exponent,
                source_exponent=config.source_exponent,source_mix_min=config.source_mix_min,source_mix_max=config.source_mix_max)
            ordered=np.sort(result.target)[::-1]
            gap=float(ordered[config.top_k-1]-ordered[config.top_k])
            entropy=float(-np.sum(result.target*np.log(np.maximum(result.target,1e-300))))
            target_mass=float(ordered[:config.top_k].sum())
            for record in run(replace(config,seed=seed)):
                rows.append({'factor':factor,'level':value,'seed':seed,'target_gap':gap,
                             'target_entropy':entropy,'target_topk_mass':target_mass,**record})
    with (output/'round_results.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(f'Wrote {len(rows)} rows to {output.resolve()}')


if __name__=='__main__': main()
