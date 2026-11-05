#!/usr/bin/env python3
"""Repeatable synthetic performance probe; never opens the user's library.

python tools/benchmark-workflows.py --entries 1000 --votes 8000 --repeat 3
Use --compare-reference to verify the previous iterative uncertainty calculation.
"""
import argparse,copy,json,random,runpy,statistics,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--entries',type=int,default=1000);p.add_argument('--votes',type=int,default=8000);p.add_argument('--repeat',type=int,default=3);p.add_argument('--compare-reference',action='store_true');a=p.parse_args()
    if not 2<=a.entries<=10000 or not 1<=a.repeat<=20 or not 0<=a.votes<=100000:raise SystemExit('Fixture size outside allowed bounds')
    runtime=runpy.run_path(str(ROOT/'runtime-src/companion-runtime.pyw'))
    board={'ratings':{str(i):{'rating':1200.,'rd':350.,'played':1,'wins':0,'losses':0,'ties':0} for i in range(a.entries)},'history_priors':{},'history':[]}
    rng=random.Random(214)
    for i in range(a.votes):
        left,right=rng.sample(range(a.entries),2);board['history'].append({'type':'vote','id':str(i),'left':str(left),'right':str(right),'outcome':('left','right','tie')[i%3]})
    with tempfile.TemporaryDirectory(prefix='nai-benchmark-') as folder:
        store=runtime['LibraryStore'](Path(folder));times=[]
        for _ in range(a.repeat):
            sample=copy.deepcopy(board);start=time.perf_counter();store.battles._fit_history(sample);times.append(time.perf_counter()-start)
        result={'schema':1,'entries':a.entries,'votes':a.votes,'seed':214,'seconds':times,'median_seconds':statistics.median(times),'pure_python_fallback_available':True}
        if a.compare_reference:
            reference=copy.deepcopy(board);start=time.perf_counter()
            with patch.object(store.battles,'_inverse_diagonal',return_value=None):store.battles._fit_history(reference)
            result['reference_seconds']=time.perf_counter()-start
            result['maximum_rating_difference']=max(abs(v['rating']-reference['ratings'][k]['rating']) for k,v in sample['ratings'].items())
            result['maximum_uncertainty_difference']=max(abs(v['rd']-reference['ratings'][k]['rd']) for k,v in sample['ratings'].items())
            if result['maximum_rating_difference']>1e-6 or result['maximum_uncertainty_difference']>1e-5:raise SystemExit('Ranking equivalence failed: '+json.dumps(result))
        print(json.dumps(result,indent=2))
if __name__=='__main__':main()
