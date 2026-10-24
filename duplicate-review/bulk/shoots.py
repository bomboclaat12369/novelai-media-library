"""Source-conditioned shoot hypotheses built from frozen visual cores.

Scores are ranking heuristics, not probabilities. Tentative additions never become
anchors or increase source priors in the same run. A post may contain any number
of shoots; its observed mixture controls how useful co-occurrence is.
"""
from collections import Counter, defaultdict
import numpy as np


def complete(items, outfit, scene, groups, membership, allowed, merge, candidates, check, update):
    sources=[{k for k,s in item['sources'].items() if s['kind'] in ('forum','instagram')} for item in items]
    kinds={k:s['kind'] for item in items for k,s in item['sources'].items()}
    limited=np.array([item.get('clothing_cue',{}).get('state')=='limited' for item in items])
    by_source=defaultdict(set)
    for i,keys in enumerate(sources):
        for key in keys:by_source[key].add(i)
    notes={};decisions=[];counts={'fragment_merges':0,'unassigned_attached':0,'unassigned_seed_groups':0}
    # These are the only images permitted to contribute source-mixture counts.
    frozen={g:frozenset(ids) for g,ids in groups.items() if len(ids)>=2}
    blocks={g:{g} for g in frozen}
    representatives={}

    def reps(ids):
        ids=tuple(sorted(ids,key=lambda i:items[i]['id']))
        if ids in representatives:return representatives[ids]
        if len(ids)<=24:chosen=list(ids)
        else:
            # Preserve distinct views instead of taking only the first thumbnails.
            features=np.concatenate([outfit[list(ids)],scene[list(ids),0],scene[list(ids),1]],axis=1)/np.sqrt(3)
            chosen_at=[0];nearest=features @ features[0]
            while len(chosen_at)<24:
                nearest[chosen_at]=2
                at=int(np.argmin(nearest));chosen_at.append(at)
                nearest=np.maximum(nearest,features @ features[at])
            chosen=[ids[i] for i in chosen_at]
        representatives[ids]=chosen
        return chosen

    def compare(left,right):
        a=reps(left);b=reps(right)
        o=outfit[a] @ outfit[b].T;f=scene[a,0] @ scene[b,0].T;c=scene[a,1] @ scene[b,1].T
        # Limited clothing reduces appearance's influence continuously; uncertain
        # cues do not veto visible outfit continuity across different backgrounds.
        weight=np.where(limited[a,None]&limited[None,b],.15,
                        np.where(limited[a,None]|limited[None,b],.45,.70))
        visual=np.maximum(weight*o+(1-weight)*(.5*f+.5*c),.25*f+.75*c)
        rows=visual.max(axis=1);cols=visual.max(axis=0)
        views=(np.sort(rows)[-2:].mean()+np.sort(cols)[-2:].mean())/2
        score=float(.65*visual.max()+.35*views)
        ca=Counter(k for i in left for k in sources[i]);cb=Counter(k for i in right for k in sources[i])
        shared=ca.keys()&cb.keys()
        support=sorted(((min(ca[k]/len(left),cb[k]/len(right)),k) for k in shared),reverse=True)
        ranked=sorted((((.10 if kinds[k]=='instagram' else .035)*coverage,coverage,k) for coverage,k in support),reverse=True)
        boost=ranked[0][0] if ranked else 0
        # Repeated download aliases have already been collapsed into source keys.
        boost+=min(.02,sum(coverage*.01 for _,coverage,k in ranked[1:]))
        best=np.unravel_index(int(visual.argmax()),visual.shape)
        return {'score':score,'boost':boost,'shared':bool(shared),'sources':sorted(shared),
                'context':float(max(f.max(),c.max())), 'appearance':float(o.max()),
                'weak':float(visual.max())<.50,
                'best_pair':[items[a[best[0]]]['id'],items[b[best[1]]]['id']]}

    relations={}
    def relation(a,b):
        key=tuple(sorted((a,b)))
        if key not in relations:relations[key]=compare(frozen[a],frozen[b])
        return relations[key]

    original_owner={i:g for g,ids in frozen.items() for i in ids}
    pairs=set()
    for i,j in candidates:
        a=original_owner.get(i);b=original_owner.get(j)
        if a is not None and b is not None and a!=b:pairs.add(tuple(sorted((a,b))))
    proposals=[]
    for at,(a,b) in enumerate(sorted(pairs)):
        if at%128==0:check();update(phase='Connecting photoshoot viewpoints',done=at,total=len(pairs))
        ev=relation(a,b);score=ev['score']+ev['boost']
        if score>=(.82 if ev['shared'] else .89):proposals.append((score,a,b,ev))
        elif ev['shared']:
            decisions.append({'action':'separate','reason':'insufficient combined shoot evidence',
                'score':round(score,4),'visual':round(ev['score'],4),'sources':ev['sources'],
                'left':[items[i]['id'] for i in sorted(frozen[a])],
                'right':[items[i]['id'] for i in sorted(frozen[b])]})
            decisions.sort(key=lambda r:-r['score']);del decisions[160:]
    for score,a,b,ev in sorted(proposals,key=lambda r:(-r[0],r[1],r[2])):
        ga,gb=membership[a],membership[b]
        if ga==gb or not allowed(ga,gb):continue
        # Check original cores, not newly added images. A single intermediary
        # cannot connect two clearly incompatible shoots through transitivity.
        conflicts=[]
        for x in blocks[ga]:
            for y in blocks[gb]:
                other=relation(x,y)
                if other['score']<(.60 if other['shared'] else .66):conflicts.append((x,y))
        if conflicts:
            if len(decisions)<200:decisions.append({'action':'separate','reason':'incompatible original shoot cores',
                'left':[items[i]['id'] for i in sorted(groups[ga])],'right':[items[i]['id'] for i in sorted(groups[gb])]})
            continue
        combined=blocks[ga]|blocks[gb]
        for i in groups[ga]|groups[gb]:notes[i]={'tentative':True,'review_hint':'Check grouping','reason':'Photoshoot fragments joined using representative views and source context.'}
        merge(ga,gb);blocks[ga]=combined;blocks.pop(gb)
        counts['fragment_merges']+=1
        if len(decisions)<200:decisions.append({'action':'merge','reason':'representative views and source context',
            'score':round(score,4),'sources':ev['sources'],'best_pair':ev['best_pair']})

    # Freeze the resulting anchor hypotheses BEFORE assigning any new image.
    anchors={g:frozenset(groups[g]) for g in blocks}
    source_mass={key:Counter() for key in by_source}
    for g,ids in anchors.items():
        for i in ids:
            for key in sources[i]:source_mass[key][g]+=1
    profiles={}
    for key,mass in source_mass.items():
        total=len(by_source[key]);established=sum(mass.values())
        coverage=established/total;focus=sum(sorted(mass.values(),reverse=True)[:3])/total
        profiles[key]={'evaluated_members':total,'anchor_members':established,
            'coverage':round(coverage,4),'top_three_share':round(focus,4),
            'shoots':[{'anchor':items[g]['id'],'members':count} for g,count in sorted(mass.items())]}

    def prior(i,g):
        best=0;chosen=None
        for key in sources[i]:
            count=source_mass[key].get(g,0)
            if count<2:continue
            profile=profiles[key];share=count/profile['evaluated_members']
            # 9/12 gives a larger prior than 2/20. Several established shoots
            # increase the chance of membership in one of them, not all of them.
            boost=.14*share+.06*profile['coverage']*profile['top_three_share']
            if boost>best:best=boost;chosen=key
        return best,chosen

    source_anchors=defaultdict(set)
    for g,ids in anchors.items():
        for i in ids:
            for key in sources[i]:source_anchors[key].add(g)
    nearby=defaultdict(set)
    for i,j in candidates:
        if j in original_owner:nearby[i].add(membership[j])
        if i in original_owner:nearby[j].add(membership[i])
    attachments=[];unresolved={}
    singles=sorted(i for i,ids in groups.items() if len(ids)==1)
    for at,i in enumerate(singles):
        if at%64==0:check();update(phase='Completing shoots from folder context',done=at,total=len(singles))
        possible=nearby[i]|set().union(*(source_anchors[k] for k in sources[i])) if sources[i] else nearby[i]
        choices=[]
        for g in sorted(possible):
            if g not in anchors or not allowed(g,i):continue
            ev=compare({i},anchors[g]);bonus,key=prior(i,g)
            score=ev['score']+ev['boost']+bonus
            threshold=.78 if ev['shared'] else .89
            # A dominant folder cannot override a complete lack of visual support.
            eligible=not ev['weak'] and ev['context']>=.30 and score>=threshold
            choices.append({'anchor':g,'score':score,'eligible':eligible,'visual':ev['score'],
                            'source_bonus':ev['boost'],'mixture_bonus':bonus,'source':key,
                            'best_pair':ev['best_pair'],'sources':ev['sources']})
        choices.sort(key=lambda r:(-r['score'],items[r['anchor']]['id']))
        passing=[r for r in choices if r['eligible']]
        if passing and (len(passing)==1 or passing[0]['score']-passing[1]['score']>=.01):
            winner=passing[0];attachments.append((i,winner))
            notes[i]={'tentative':True,'review_hint':'Check addition','reason':'Likely member based on matching views and the shoots established in this post.',
                'source':winner['source'],'mixture_bonus':round(winner['mixture_bonus'],4),
                'alternatives':[r['anchor'] for r in passing[1:4]]}
        elif choices:
            unresolved[items[i]['id']]={'reason':'competing shoot hypotheses' if passing else 'insufficient visual and source support',
                'candidates':[{**{k:v for k,v in r.items() if k!='anchor'},'anchor':items[r['anchor']]['id']} for r in choices[:5]]}
    # Apply together; neither priors nor matching representatives can snowball.
    for i,winner in attachments:
        g=winner['anchor']
        if i in groups and g in groups and allowed(g,i):merge(g,i);counts['unassigned_attached']+=1

    # Remaining same-source images can establish their own shoot. Use a signed
    # group check on original images rather than plain connected components.
    remaining={i for i,ids in groups.items() if len(ids)==1}
    proposals=[];single_relations={}
    def single_relation(i,j):
        key=tuple(sorted((i,j)))
        if key not in single_relations:single_relations[key]=compare({i},{j})
        return single_relations[key]
    for at,(i,j) in enumerate(sorted(candidates)):
        if at%2000==0:check()
        if i not in remaining or j not in remaining or not (sources[i]&sources[j]):continue
        ev=single_relation(i,j);score=ev['score']+ev['boost']
        if not ev['weak'] and ev['context']>=.30 and score>=.80:proposals.append((score,i,j))
    new_roots=set()
    for _,i,j in sorted(proposals,key=lambda r:(-r[0],r[1],r[2])):
        a,b=membership[i],membership[j]
        if a==b or not allowed(a,b):continue
        if any(single_relation(x,y)['score']<.60 for x in groups[a] for y in groups[b]):continue
        merge(a,b);new_roots.discard(b);new_roots.add(a)
        for member in groups[a]:notes[member]={'tentative':True,'review_hint':'Check grouping','reason':'New shoot proposed from combined visual and shared-post evidence.'}
    counts['unassigned_seed_groups']=len(new_roots)
    final_owner={items[i]['id']:g for g,ids in groups.items() for i in ids}
    decisions=[r for r in decisions if r['action']!='separate' or final_owner[r['left'][0]]!=final_owner[r['right'][0]]]
    unresolved={ident:r for ident,r in unresolved.items() if len(groups[final_owner[ident]])==1}
    update(source_shoots={'profiles':profiles,'decisions':decisions,'unresolved':unresolved,
                         'note':'Counts use evaluated images only. Tentative attachments do not increase source priors.'})
    return notes,counts
