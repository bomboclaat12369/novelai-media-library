"""Reproducible integrated campaigns using the shipped rules and explicit policies."""
import argparse
import copy
import json
from pathlib import Path
import statistics
from . import engine as g, management as m
from .catalog import demo_catalog,read_library


def catalog_for(count):
    cat=demo_catalog();owners=list(cat['people'])[:count]
    cat['people']={p:v for p,v in cat['people'].items() if p in owners}
    cat['cards']={i:c for i,c in cat['cards'].items() if c['owner'] in owners}
    return cat


def campaign(count,seed,nights=120,policy='balanced',keep_state=False,catalog=None,collecting=False):
    cat=catalog or catalog_for(count);s=g.new_game(cat,list(cat['people'])[:2],seed)
    milestones={};early=[];growth=[];purchases=[]
    def do(action,**body):
        nonlocal s
        s=g.command(s,cat,action,body)
    for _ in range(nights):
        reserve=g.recurring_cost(s)*(2 if policy=='conservative' else 1)+100
        if s['cash']<g.recurring_cost(s):do('recovery')
        # A modest opening schedule leaves money for both collecting and growth.
        if s['day']%3==0 and s['cash']>=reserve+100:
            do('pack',pack='standard');do('reveal_done');purchases.append(s['day'])
        if s['pack_vouchers']:
            do('pack',pack='standard',voucher=True);do('reveal_done')
        owners=list(s['people']);slots=s['facilities']['rooms']+s['facilities']['lounge']
        if len(owners)<min(count,4) and s['cash']>=reserve+g.hire_cost(s):
            p=next(p for p in cat['people'] if p not in s['people']);do('hire',owner=p);growth.append({'day':s['day'],'action':'hire'})
        elif slots<min(len(owners),4) and s['cash']>=reserve+g.upgrade_cost(s,'rooms'):
            do('upgrade',kind='rooms');growth.append({'day':s['day'],'action':'room'})
        elif not s['departments']['studio'] and m.unlocks(s)['studio'] and s['cash']>=reserve+m.DEPARTMENTS['studio']['price']:
            do('department',kind='studio');milestones['studio']=s['day']
        elif not s['departments']['resort'] and m.unlocks(s)['resort'] and s['cash']>=reserve+m.DEPARTMENTS['resort']['price']:
            do('department',kind='resort');milestones['resort']=s['day']
        elif s['departments']['resort']:
            if len(s['people'])<count and s['cash']>=reserve+g.hire_cost(s):
                do('hire',owner=next(p for p in cat['people'] if p not in s['people']))
            elif slots<min(len(s['people'])-2,9) and s['facilities']['rooms']<6 and s['cash']>=reserve+g.upgrade_cost(s,'rooms'):
                do('upgrade',kind='rooms')
            elif s['facilities']['recovery']<2 and s['cash']>=reserve+g.upgrade_cost(s,'recovery'):
                do('upgrade',kind='recovery')
            elif s['facilities']['lounge']<3 and len(s['people'])>8 and s['cash']>=reserve+g.upgrade_cost(s,'lounge'):
                do('upgrade',kind='lounge')
            elif len(s['people'])>8:
                dept='studio' if s['departments']['studio']<=s['departments']['resort'] else 'resort'
                cost=m.DEPARTMENTS[dept]['price']*(s['departments'][dept]+1)
                if s['departments'][dept]<min(6,max(1,(len(s['people'])-6)//2)) and s['cash']>=reserve+cost:do('department',kind=dept)
        # Fill department reservations before the club; tired workers rotate.
        for dept in ('studio','resort'):
            capacity=s['departments'][dept]-sum(c['department']==dept for c in m.reservations(s))
            for _ in range(capacity):
                candidates=[p for p,w in s['people'].items() if not m.reservations(s,p) and w['energy']>=55]
                if len(candidates)<=1:break
                owner=max(candidates,key=lambda p:m.skill_bonus(s['people'][p],dept))
                kind=('portrait' if s['totals']['studio_completed']<2 else 'editorial') if dept=='studio' else 'retreat'
                fee=(m.PROJECTS if dept=='studio' else m.STAYS)[kind]['fee']
                if s['cash']>=fee+g.recurring_cost(s):do('schedule',department=dept,owner=owner,kind=kind)
        do('auto')
        if policy=='aggressive':do('price',pricing='premium')
        do('start')
        if policy!='conservative':
            do('advance',seconds=100)
            d=s['night']['decisions'][0]
            if d['kind']=='booking' and any(w['energy']>=10 and m.assignment(s,p) in ('room','lounge') for p,w in s['people'].items()):do('decision',decision=d['id'],choice='accept')
            do('advance',seconds=100)
            if any(w['energy']<45 for w in s['people'].values()):do('decision',decision=s['night']['decisions'][1]['id'],choice='refresh')
        do('finish')
        if s['day']<=15:early.append(s['reports'][-1]['profit'])
        if s['cash']>reserve+800 and s['day']%2==0:
            kind='premium' if s['day']%4 else 'collector'
            if kind=='collector' and all(i in s['owned'] for i in cat['cards']):kind='premium'
            do('pack',pack=kind);do('reveal_done');purchases.append(s['day'])
        if collecting and s['departments']['resort']:
            # Spend up to three quarters of discretionary savings, preserving a
            # payroll reserve. Larger venues can support several openings.
            allowance=max(0,(s['cash']-reserve)*.75)
            while allowance>=600 and s['cash']>=reserve+600:
                kind='collector' if any(i not in s['owned'] for i in cat['cards']) else 'standard'
                do('pack',pack=kind);do('reveal_done');purchases.append(s['day'])
                allowance-=g.PACKS[kind]['price']
        s['journal']=[]
    result={'roster':len(s['people']),'cash':s['cash'],'packs':s['totals']['packs'],'purchased_pack_nights':len(purchases),
        'milestone_days':milestones,'first_growth':growth[0]['day'] if growth else None,
        'early_mean_net':round(statistics.mean(early),2),'late_mean_net':round(statistics.mean(r['profit'] for r in s['reports'][-20:]),2),
        'studio_completed':s['totals']['studio_completed'],'resort_completed':s['totals']['resort_completed'],
        'recovery_breaks':s['totals']['recovery_grants'],'departments':s['departments'],'unique_cards':len(s['owned'])}
    return (result,s,cat) if keep_state else result


def run(seeds,nights,library=None):
    output={'scope':'Synthetic policy comparisons using shipped rules; not human playtesting or guaranteed outcomes.','seeds':seeds,'nights_per_campaign':nights,'campaigns':{}}
    for count in (4,5,12,20):
        for policy in ('balanced','conservative','aggressive'):
            rows=[campaign(count,seed,nights,policy) for seed in range(seeds)]
            output['campaigns'][f'{count}_{policy}']={
                'all_reached_resort':all('resort' in r['milestone_days'] for r in rows),
                'studio_day_range':[min(r['milestone_days'].get('studio',999) for r in rows),max(r['milestone_days'].get('studio',999) for r in rows)],
                'resort_day_range':[min(r['milestone_days'].get('resort',999) for r in rows),max(r['milestone_days'].get('resort',999) for r in rows)],
                'mean_early_net':round(statistics.mean(r['early_mean_net'] for r in rows),2),
                'mean_late_net':round(statistics.mean(r['late_mean_net'] for r in rows),2),
                'mean_packs':round(statistics.mean(r['packs'] for r in rows),1),
                'mean_final_cash':round(statistics.mean(r['cash'] for r in rows),2),
                'recovery_breaks':sum(r['recovery_breaks'] for r in rows),'sample':rows[0]}
    # Opening comparison isolates the two-founder cadence before capital growth.
    profits=[]
    for seed in range(seeds):
        cat=catalog_for(4);s=g.new_game(cat,list(cat['people'])[:2],seed)
        for _ in range(14):
            for action in ('auto','start','finish'):s=g.command(s,cat,action)
            profits.append(s['reports'][-1]['profit']);s['journal']=[]
    output['opening']={'nights':len(profits),'mean_net':round(statistics.mean(profits),2),'median_net':statistics.median(profits),'negative_nights':sum(p<0 for p in profits),'standard_price':100}
    output['continued_collecting']={str(count):[campaign(count,seed,nights,collecting=True) for seed in range(seeds)] for count in (4,20)}
    if library:
        cat=read_library(Path(library));count=len(cat['people'])
        output['real_catalog']={'characters':count,'cards':len(cat['cards']),
            'gallery_sizes':sorted(sum(c['owner']==p for c in cat['cards'].values()) for p in cat['people']),
            'campaigns':[campaign(count,seed,nights,catalog=cat,collecting=True) for seed in range(seeds)]}
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',type=int,default=24);parser.add_argument('--nights',type=int,default=120);parser.add_argument('--output',default='game/full-balance-report.json');parser.add_argument('--library');args=parser.parse_args()
    report=run(args.seeds,args.nights,args.library);Path(args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'opening':report['opening'],'campaigns':{k:{f:v for f,v in r.items() if f!='sample'} for k,r in report['campaigns'].items()}},indent=2))
