"""Combined-evidence seeds, source-aware reconciliation and set recovery.

Engineering thresholds, not probabilities. An appearance score only suffices on
its own when BOTH images have positive clothing cues. Folder co-occurrence never
suffices. All source cohesion is measured within this evaluation's image cohort.
"""
from collections import defaultdict
import math
import numpy as np

RECIPE = 'bulk-evaluation-3'


def propose(items, outfit, scene, update=lambda **kw: None, check=lambda: None):
    n=len(items)
    if n<2:return [],list(range(n)),[]
    clothing=[i.get('clothing_cue',{}).get('state')=='present' for i in items]
    limited=[i.get('clothing_cue',{}).get('state')=='limited' for i in items]
    by_source=defaultdict(list)
    for i,item in enumerate(items):
        for key,source in item['sources'].items():
            if source['kind'] in ('forum','instagram'):by_source[key].append(i)
    # A compilation post is not strengthened just because it contains a real pair.
    # Require broad scene agreement, including the less typical sampled members.
    profiles={};source_components={}
    for key,ids in sorted(by_source.items()):
        check()
        sample=sorted(ids,key=lambda i:items[i]['id'])
        if len(sample)>200:sample=[sample[j] for j in np.linspace(0,len(sample)-1,64,dtype=int)]
        a=scene[sample,0] @ scene[sample,0].T
        b=scene[sample,1] @ scene[sample,1].T
        supported=(a>=.62)&(b>=.80);np.fill_diagonal(supported,False)
        rates=supported.sum(axis=1)/max(1,len(sample)-1)
        density=float(rates.mean())
        coherent=len(sample)>=3 and density>=.70 and float(rates.min())>=.50
        components={};sizes=[]
        if coherent:
            components={i:0 for i in sample};sizes=[len(sample)]
        elif len(sample)>=3:
            # Find coherent subsets INSIDE a mixed post. Dense cross-support is
            # required; connected components alone would join shoots via bridges.
            parts={i:{i} for i in range(len(sample))};owner=list(range(len(sample)))
            pairs=sorted(((float(.3*a[i,j]+.7*b[i,j]),i,j) for i,j in zip(*np.where(np.triu(supported,1)))),reverse=True)
            for step,(_,i,j) in enumerate(pairs):
                if step%256==0:check()
                left,right=owner[i],owner[j]
                if left==right:continue
                joined=parts[left]|parts[right];indices=sorted(joined)
                block=supported[np.ix_(indices,indices)]
                fractions=block.sum(axis=1)/(len(indices)-1)
                if fractions.mean()<.70 or fractions.min()<.50:continue
                moved=parts.pop(right);parts[left]|=moved
                for member in moved:owner[member]=left
            for members in parts.values():
                if len(members)<3:continue
                label=len(sizes);sizes.append(len(members))
                for member in members:components[sample[member]]=label
        source_components[key]=components
        profiles[key]={'coherent':coherent,'density':round(density,4),'sample':len(sample),'total':len(ids),
                       'coherent_subgroups':sizes}

    update(source_profiles=profiles)
    candidates=set();capped=[key for key,ids in by_source.items() if len(ids)>200]
    # Keep N x N matrices out of memory. Source expansion complements NN retrieval.
    for start in range(0,n,128):
        check();stop=min(n,start+128)
        for matrix,right,k in ((outfit[start:stop],outfit,32),(scene[start:stop,0],scene[:,0],24),(scene[start:stop,1],scene[:,1],24)):
            scores=matrix @ right.T;width=min(k+1,n)
            neighbors=np.argpartition(scores,n-width,axis=1)[:,-width:]
            for offset,ids in enumerate(neighbors):
                i=start+offset
                for j in ids:
                    if i!=j:candidates.add((min(i,int(j)),max(i,int(j))))
        update(phase='Finding outfit and setting candidates',done=stop,total=n)
    for ids in by_source.values():
        if len(ids)<=200:
            for at,i in enumerate(ids):
                for j in ids[at+1:]:candidates.add((min(i,j),max(i,j)))
    cache={}

    def evidence(i,j):
        key=(min(i,j),max(i,j))
        if key in cache:return cache[key]
        o=float(outfit[i] @ outfit[j]);full=float(scene[i,0] @ scene[j,0]);outer=float(scene[i,1] @ scene[j,1])
        shared=items[i]['sources'].keys() & items[j]['sources'].keys() & profiles.keys()
        coherent=any(i in source_components[s] and source_components[s].get(i)==source_components[s].get(j) for s in shared)
        # Bare skin/face/pose similarity cannot bypass the scene checks.
        garment=clothing[i] and clothing[j]
        outfit_ok=garment and o>=.86
        contradictory=garment and o<.76
        scene_ok=(full>=.86 and outer>=.84) if shared else (full>=.91 and outer>=.89)
        # Distinctive background can survive major full-frame/pose changes. This
        # relaxed branch needs broad source consistency, not any shared folder.
        source_scene=coherent and ((full>=.72 and outer>=.86) or (full>=.84 and outer>=.82))
        # Uncertain clothing is not evidence that the outfit is absent. Combine
        # appearance and scene agreement without requiring a coherent-post label
        # first (that label itself can fragment close-ups and full-body views).
        appearance_context=(not (limited[i] or limited[j]) and
            ((bool(shared) and o>=.84 and full>=.62 and outer>=.74) or
             (o>=.88 and full>=.74 and outer>=.82)))
        strong=outfit_ok or ((scene_ok or source_scene or appearance_context) and not contradictory)
        # Softer evidence can support a group-level merge, never seed a pair alone.
        source_support=bool(shared) and full>=.60 and outer>=.79
        soft=strong or (not contradictory and
            ((coherent and full>=.64 and outer>=.84) or source_support or
             (bool(shared) and not (limited[i] or limited[j]) and o>=.82 and full>=.58 and outer>=.72)))
        context_score=.30*full+.70*outer
        strength=max(o if outfit_ok else 0,context_score if not contradictory else 0)
        method='outfit' if outfit_ok else ('outfit + setting + post' if appearance_context and shared else
            'outfit + setting' if appearance_context else 'setting + consistent post' if source_scene else 'setting + post' if shared else 'setting')
        value={'strong':strong,'soft':soft,'score':strength,'outfit':o,'full':full,'outer':outer,
               'method':method,'shared':bool(shared),'coherent':coherent,
               'contradictory':contradictory,'reason':('strong evidence' if strong else 'group support only' if soft else
                   'conflicting outfit evidence' if contradictory else 'insufficient combined visual evidence')}
        if key in candidates:cache[key]=value
        return value

    links=[];soft_links=[];adjacency=defaultdict(list)
    for step,(i,j) in enumerate(sorted(candidates)):
        if step%2000==0:check();update(phase='Checking clothing, setting and source support',done=step,total=len(candidates))
        e=evidence(i,j)
        if e['soft']:
            soft_links.append((e['score'],i,j));adjacency[i].append((e['score'],j));adjacency[j].append((e['score'],i))
        if e['strong']:links.append((e['score'],i,j))
    links.sort(reverse=True);soft_links.sort(reverse=True)
    groups={i:{i} for i in range(n)};membership=list(range(n))
    labels={i:set(items[i].get('existing_sets',[])) for i in range(n)}

    def allowed(a,b):
        return len(groups[a])+len(groups[b])<=120 and not (labels[a] and labels[b] and labels[a]!=labels[b])

    def merge(a,b):
        members=groups.pop(b);groups[a]|=members;labels[a]|=labels.pop(b)
        for member in members:membership[member]=a

    # First build reliable cores, retaining the anti-bridge safeguard.
    for step,(_,i,j) in enumerate(links):
        if step%1000==0:check();update(phase='Building reliable set cores',done=step,total=len(links))
        a,b=membership[i],membership[j]
        if a==b or not allowed(a,b):continue
        good=True
        for left,right in ((groups[a],groups[b]),(groups[b],groups[a])):
            for member in left:
                count=sum(evidence(member,other)['strong'] for other in right)
                if count<min(2,len(right)) or count/len(right)<.4:good=False;break
            if not good:break
        if good:merge(a,b)

    reconciled=0;recovered=0;new_cores=0
    # Three mutually supporting remaining images can establish a new shoot even
    # when none passes a strong pair threshold. Shared post alone never suffices;
    # every edge needs visual support and all three need ONE common source.
    singleton_ids={i for i,ids in groups.items() if len(ids)==1}
    triangles={}
    for step,i in enumerate(sorted(singleton_ids)):
        check()
        if step%64==0:update(phase='Finding sets among unassigned images',done=step,total=len(singleton_ids))
        neighbors=[j for _,j in sorted(adjacency[i],reverse=True) if j in singleton_ids and j>i][:32]
        local_triangles=[]
        for at,j in enumerate(neighbors):
            for k in neighbors[at+1:]:
                triple=tuple(sorted((i,j,k)))
                common=items[i]['sources'].keys() & items[j]['sources'].keys() & items[k]['sources'].keys() & profiles.keys()
                if not common:continue
                edges=[evidence(i,j),evidence(i,k),evidence(j,k)]
                if all(e['soft'] for e in edges):local_triangles.append((sum(e['score'] for e in edges)/3,triple))
        # Bounded proposal memory for full-library runs, not O(N * 32 squared).
        for score,triple in sorted(local_triangles,reverse=True)[:8]:triangles[triple]=score
    for ids,_ in sorted(triangles.items(),key=lambda row:(-row[1],row[0])):
        a,b,c=ids
        if any(i not in groups or len(groups[i])!=1 for i in ids):continue
        combined_labels=labels[a]|labels[b]|labels[c]
        if any(labels[i] and labels[i]!=combined_labels for i in ids):continue
        merge(a,b);merge(a,c);new_cores+=1

    merge_rejections={}
    # Bounded reconciliation rounds. Require support across multiple members
    # on BOTH sides, so a single similar-looking bridge cannot join two shoots.
    for round_number in range(8):
        choices={}
        for score,i,j in soft_links:
            a,b=membership[i],membership[j]
            if a!=b and len(groups[a])>=2 and len(groups[b])>=2:
                key=(min(a,b),max(a,b));choices[key]=max(score,choices.get(key,0))
        changed=False
        for at,((a,b),_) in enumerate(sorted(choices.items(),key=lambda x:(-x[1],x[0]))):
            if at%100==0:check();update(phase='Reuniting supported set fragments',done=at,total=len(choices))
            if a not in groups or b not in groups or not allowed(a,b):continue
            ga,gb=sorted(groups[a]),sorted(groups[b])
            edges=[[evidence(i,j) for j in gb] for i in ga]
            soft=np.array([[e['soft'] for e in row] for row in edges])
            strong=np.array([[e['strong'] for e in row] for row in edges])
            # Shared origin must cover most of each fragment, not one alias.
            origin=np.array([[e['shared'] for e in row] for row in edges])
            source_supported=origin.any(axis=1).mean()>=.6 and origin.any(axis=0).mean()>=.6
            required=.6 if source_supported else .8
            connected=soft if source_supported else strong
            def rejected(reason):
                # Bounded details, kept outside the UI; no image vectors exported.
                key=(a,b)
                if key in merge_rejections or len(merge_rejections)<200:
                    merge_rejections[key]={'left':[items[i]['id'] for i in ga],
                        'right':[items[i]['id'] for i in gb],'reason':reason,
                        'strong_edges':int(strong.sum()),'support_edges':int(connected.sum()),
                        'shared_source':bool(source_supported)}
            if connected.any(axis=1).sum()<2 or connected.any(axis=0).sum()<2:
                rejected('fewer than two supported members on each side');continue
            if connected.any(axis=1).mean()<required or connected.any(axis=0).mean()<required:
                rejected('insufficient member coverage');continue
            # Multiple independent source-backed visual links can substitute for
            # strong edges. One bridge still cannot unite unrelated shoots.
            if source_supported:
                if connected.mean()<.5:
                    rejected('sparse cross-group support');continue
            elif strong.sum()<max(3,math.ceil(.25*len(ga)*len(gb))):
                rejected('insufficient strong evidence without shared source');continue
            # Compare whole-group context too; outfit-only merges still need
            # pervasive positive clothing evidence and direct outfit agreement.
            fa=scene[ga,0].mean(axis=0);fb=scene[gb,0].mean(axis=0)
            oa=scene[ga,1].mean(axis=0);ob=scene[gb,1].mean(axis=0)
            cosine=lambda x,y:float(x@y/max(1e-8,np.linalg.norm(x)*np.linalg.norm(y)))
            scene_agreement=cosine(fa,fb)>=(.64 if source_supported else .72) and cosine(oa,ob)>=(.80 if source_supported else .86)
            garment_agreement=all(clothing[i] for i in ga+gb) and np.mean([[e['outfit']>=.86 for e in row] for row in edges])>=.6
            if not scene_agreement and not garment_agreement:
                rejected('group setting and outfit agreement insufficient');continue
            merge(a,b);reconciled+=1;changed=True
        if not changed:break

    # Evaluate unassigned images against established cores simultaneously. Newly
    # attached images cannot act as bridges for additional attachments in this pass.
    attachments=[];attachment_rejections={}
    for at,i in enumerate(sorted(g for g,ids in groups.items() if len(ids)==1)):
        if at%64==0:check();update(phase='Checking unassigned images against set cores',done=at,total=n)
        possible={membership[j] for _,j in adjacency[i] if len(groups[membership[j]])>=2}
        matches=[]
        for group in sorted(possible):
            edges=sorted((evidence(i,j) for j in groups[group]),key=lambda e:-e['score'])
            supporting=[e for e in edges if e['soft']]
            reason=None
            if not allowed(group,i):reason='conflicting existing sets or group size limit'
            elif len(supporting)<2:reason='fewer than two supporting members'
            elif not any(e['strong'] for e in supporting) and sum(e['shared'] for e in supporting)<2:reason='weak support without shared source'
            elif len(supporting)/len(edges)<.4:reason='insufficient group coverage'
            if reason:
                attachment_rejections.setdefault(i,[]).append({'group':[items[j]['id'] for j in sorted(groups[group])],
                    'reason':reason,'support':len(supporting),'score':round(edges[0]['score'],4)})
                attachment_rejections[i].sort(key=lambda r:-r['score']);del attachment_rejections[i][5:]
                continue
            score=sum(e['score'] for e in supporting[:2])/2
            matches.append((score,group))
        matches.sort(reverse=True)
        if matches and (len(matches)==1 or matches[0][0]-matches[1][0]>=.025):attachments.append((matches[0][0],i,matches[0][1]))
        elif matches:attachment_rejections[i]=[{'group':[items[j]['id'] for j in sorted(groups[g])],
            'reason':'competing groups within score margin','score':round(score,4)} for score,g in matches[:5]]
    for _,i,group in sorted(attachments,reverse=True):
        if i in groups and group in groups and allowed(group,i):merge(group,i);recovered+=1
    update(grouping_changes={'fragment_merges':reconciled,'unassigned_attached':recovered,'unassigned_seed_groups':new_cores})

    result=[];singles=[]
    for ids in groups.values():
        check()
        if not any(not items[i].get('reference') for i in ids):continue
        if len(ids)<2:singles.extend(ids);continue
        rows=[]
        for i in sorted(ids):
            inside=sorted((evidence(i,j) for j in ids if j!=i),key=lambda e:(not e['soft'],-e['score']))
            rivals=sorted(((v,j) for v,j in adjacency[i] if j not in ids),reverse=True)
            best=inside[0];margin=best['score']-(rivals[0][0] if rivals else 0)
            support=sum(e['soft'] for e in inside)
            rows.append({'index':i,'support':support,'method':best['method'],
                **{k:round(best[k],4) for k in ('score','outfit','full','outer')},
                'ambiguous':margin<.025 or support/max(1,len(inside))<.5,
                'alternatives':[j for _,j in rivals[:3]]})
        result.append({'members':rows,'priority':'inspect' if any(r['ambiguous'] for r in rows) else 'review',
            'existing_sets':sorted(set().union(*(set(items[i].get('existing_sets',[])) for i in ids)))})
    result.sort(key=lambda g:(g['priority']=='inspect',-len(g['members'])))
    # Include rejected candidates too: previous exports only recorded matches
    # which already passed, making missed sets impossible to diagnose directly.
    nearest=defaultdict(list)
    singleton_set=set(singles)
    for step,(i,j) in enumerate(sorted(candidates)):
        if step%2000==0:check()
        if i not in singleton_set and j not in singleton_set:continue
        e=evidence(i,j)
        for left,right in ((i,j),(j,i)):
            if left not in singleton_set:continue
            row={'image':items[right]['id'],**{k:e[k] for k in ('strong','soft','shared','coherent','reason')},
                 **{k:round(e[k],4) for k in ('outfit','full','outer','score')}}
            nearest[left].append(row)
            nearest[left].sort(key=lambda r:(-max(r['score'],r['outfit']),r['image']))
            del nearest[left][5:]
    update(match_diagnostics={'recipe':RECIPE,
        'unassigned_candidates':{items[i]['id']:nearest[i] for i in singles},
        'unassigned_group_rejections':{items[i]['id']:attachment_rejections.get(i,[]) for i in singles},
        'fragment_rejections':[r for (a,b),r in merge_rejections.items() if membership[a]!=membership[b]]})
    return result,singles,capped
