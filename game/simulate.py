"""Seeded economy and pack-distribution checks using the real prototype rules."""
import argparse
import json
from pathlib import Path
import random
import statistics
from collections import Counter
from . import engine as g
from .catalog import demo_catalog


def configured(catalog,count,rooms,lounge,recovery,seed):
    owners=list(catalog['people'])
    state=g.new_game(catalog,owners[:2],seed)
    state['cash']=100000
    for owner in owners[2:count]: state=g.command(state,catalog,'hire',{'owner':owner})
    state['facilities'].update(rooms=rooms,lounge=lounge,recovery=recovery)
    state['cash']=2000
    return state


def campaign(catalog,seed,nights=120):
    state=g.new_game(catalog,list(catalog['people'])[:2],seed)
    growth=[]
    for _ in range(nights):
        reserve=g.recurring_cost(state)*2+100
        count=len(state['people']);slots=state['facilities']['rooms']+state['facilities']['lounge']
        if state['cash']>reserve:
            if slots<=count and state['facilities']['rooms']<6 and state['cash']>=reserve+g.upgrade_cost(state,'rooms')+g.hire_cost(state):
                state=g.command(state,catalog,'upgrade',{'kind':'rooms'})
                growth.append({'day':state['day'],'action':'room'})
            elif slots<=count and state['facilities']['lounge']<3 and state['cash']>=reserve+g.upgrade_cost(state,'lounge')+g.hire_cost(state):
                state=g.command(state,catalog,'upgrade',{'kind':'lounge'})
                growth.append({'day':state['day'],'action':'lounge'})
            elif (count<slots or (slots==9 and count<12)) and state['cash']>=reserve+g.hire_cost(state):
                owner=next(p for p in catalog['people'] if p not in state['people'])
                state=g.command(state,catalog,'hire',{'owner':owner})
                growth.append({'day':state['day'],'action':'hire'})
            elif state['facilities']['rooms']>=3 and state['facilities']['recovery']<3 and state['cash']>=reserve+g.upgrade_cost(state,'recovery'):
                state=g.command(state,catalog,'upgrade',{'kind':'recovery'})
        state=g.command(state,catalog,'auto')
        state=g.command(state,catalog,'start')
        state=g.command(state,catalog,'finish')
        if state['cash']>=g.recurring_cost(state)*2+100 and state['day']%2==0:
            state=g.command(state,catalog,'pack',{'pack':'standard'})
            state=g.command(state,catalog,'reveal_done')
        if state['cash']<0: state=g.command(state,catalog,'recovery')
    return {'girls':len(state['people']),'cash':state['cash'],'packs':state['totals']['packs'],
            'growth':growth,'recovery_breaks':state['totals']['recovery_grants'],
            'last_20_profit':round(statistics.mean(r['profit'] for r in state['reports'][-20:]),2)}


def run(seeds=40,nights=120):
    cat=demo_catalog();results={}
    scenarios={'opening_two':(2,1,1,0),'established_four':(4,3,1,1),
               'expanded_eight':(8,6,3,2),'expanded_twelve':(12,6,3,2),'expanded_two':(2,6,3,2)}
    for name,(count,rooms,lounge,recovery) in scenarios.items():
        profits=[];losses=0
        for seed in range(seeds):
            s=configured(cat,count,rooms,lounge,recovery,seed)
            for _ in range(nights):
                s=g.command(s,cat,'auto');s=g.command(s,cat,'start');s=g.command(s,cat,'finish')
                if s['day']>15: profits.append(s['reports'][-1]['profit'])
                losses+=s['reports'][-1]['profit']<0
        results[name]={'mean_net_per_night':round(statistics.mean(profits),2),
                       'p10_net':sorted(profits)[int(len(profits)*.1)],'p90_net':sorted(profits)[int(len(profits)*.9)],
                       'negative_nights':losses,'nights':seeds*nights}
    campaigns=[campaign(cat,seed,nights) for seed in range(seeds)]
    rng=random.Random(8462);counts=Counter();pool=list(cat['cards'].values())
    for _ in range(40000): counts[g.draw(pool,rng)['owner']]+=1
    shares={cat['people'][p]['name']:round(v/40000,4) for p,v in counts.items()}
    return {'scope':'Synthetic prototype model, not real-library or human playtesting.',
            'seeds':seeds,'nights_per_scenario':nights,'scenarios':results,
            'campaign':{'mean_girls':statistics.mean(c['girls'] for c in campaigns),
                        'mean_packs':statistics.mean(c['packs'] for c in campaigns),
                        'recovery_breaks':sum(c['recovery_breaks'] for c in campaigns),
                        'mean_final_cash':round(statistics.mean(c['cash'] for c in campaigns),2),
                        'first_growth_days':[c['growth'][0]['day'] if c['growth'] else None for c in campaigns],
                        'sample':campaigns[0]},
            'pack_sampling':{'draws':40000,'catalog_images':len(pool),'characters':len(cat['people']),
                             'images_per_main_girl':120,'images_per_supporting_girl':6,'character_shares':shares}}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='game/balance-report.json');p.add_argument('--seeds',type=int,default=40);p.add_argument('--nights',type=int,default=120)
    a=p.parse_args();report=run(a.seeds,a.nights)
    Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='pack_sampling'},indent=2))
    print('Character odds min/max:',min(report['pack_sampling']['character_shares'].values()),max(report['pack_sampling']['character_shares'].values()))
