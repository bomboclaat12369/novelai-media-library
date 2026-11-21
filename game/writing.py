"""Optional offline event and group-stage packs. Selection never draws from the game clock or economy."""
from collections import defaultdict
import hashlib
import os
from pathlib import Path
import re
import uuid

from . import stage_labels

LIMIT=64*1024*1024
ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}')
TOKEN=re.compile(r'\{([a-z_]+)\}')
EVENT_TOKENS={
    'anal_extra':'worker payout energy_cost','creampie_extra':'worker payout energy_cost',
    'extension':'worker payout energy_cost extra_seconds','second_round':'worker payout energy_cost extra_seconds',
    'third_round':'worker payout energy_cost extra_seconds','lounge_round':'payout energy_cost',
    'promotion':'cash_cost reputation_gain promotion_nights','hospitality':'cash_cost energy_restore',
    'team_meal':'cash_cost energy_restore','regular_perk':'cash_cost loyalty_gain',
    'second_worker':'worker partner payout','second_client':'worker payout'}
GROUP_SLOTS={'second_worker','second_client'}


def text_tokens(text, allowed):
    if not isinstance(text,str) or not 0<len(text.strip())<=4096:
        raise ValueError('Each event needs a title and body up to 4096 characters.')
    stripped=TOKEN.sub('',text)
    used=set(TOKEN.findall(text))
    if '{' in stripped or '}' in stripped or not used<=allowed:
        raise ValueError('A line contains an unsupported placeholder.')
    return used


def group_row(row):
    if not isinstance(row,dict) or set(row)!={'id','slot','when','text'} or row['slot'] not in stage_labels.CONDITIONS:
        raise ValueError('Expected a group stage with id, slot, when and text.')
    when=row['when']; text=row['text']
    if not isinstance(when,dict): raise ValueError('Each group stage needs participant conditions.')
    lineup=when.get('lineup'); workers=when.get('workers'); clients=when.get('clients')
    if not ((lineup=='two_workers_one_client' and workers in ('both','original','joining') and clients=='original') or
            (lineup=='one_worker_two_clients' and workers=='original' and clients in ('original','joining','both'))):
        raise ValueError('Unknown group lineup or participant combination.')
    extra=set(when)-{'lineup','workers','clients'}
    if not extra<=stage_labels.CONDITIONS[row['slot']] or any(not stage_labels.valid_fact(k,when[k]) for k in extra):
        raise ValueError('Unsupported group activity, outcome or stage condition.')
    if when.get('stage_index',1)>when.get('stage_count',when.get('stage_index',1)):
        raise ValueError('The stage index exceeds the stage count.')
    valid=isinstance(text,str) and stage_labels.valid_text(text.replace('{partner}','partner'))
    if not valid or text.count('{partner}')>int(workers=='both'):
        raise ValueError('A group label needs one {worker}. Only a two-worker action may also name {partner}.')


def parse(raw):
    if len(raw)>LIMIT: raise ValueError('Writing packs may contain up to 64 MiB.')
    data=stage_labels.read_json(raw)
    group=isinstance(data,list)
    if group:
        key='group-stages'; rows=data
    else:
        if (not isinstance(data,dict) or set(data)!={'format','schema_version','context_version','pack_id','entries'}
            or data['format']!='after-hours-writing-pack' or type(data['schema_version']) is not int or data['schema_version']!=1
            or type(data['context_version']) is not int or data['context_version'] not in (2,3)
            or not isinstance(data['pack_id'],str) or not ID.fullmatch(data['pack_id'])):
            raise ValueError('Choose an event writing pack (schema 1, context 2 or 3) or the group-stage JSON array.')
        key='events-'+data['pack_id']; rows=data['entries']
    if not isinstance(rows,list) or not 1<=len(rows)<=100000: raise ValueError('A pack needs 1–100,000 entries.')
    ids=set()
    for row in rows:
        if group: group_row(row)
        else:
            if (not isinstance(row,dict) or set(row)!={'id','slot','when','title','text','dialogue'}
                or row['when']!={} or row['dialogue']!=[] or not isinstance(row['slot'],str) or not row['slot'].startswith('event.')):
                raise ValueError('Invalid event record.')
            kind=row['slot'][6:]
            if kind not in EVENT_TOKENS or (kind in GROUP_SLOTS)!=(data['context_version']==3):
                raise ValueError('Unknown event in this writing context.')
            allowed=set(EVENT_TOKENS[kind].split())
            row['tokens']=text_tokens(row['title'],allowed)|text_tokens(row['text'],allowed)
        ident=row['id']
        if not isinstance(ident,str) or not ID.fullmatch(ident) or ident in ids: raise ValueError('Use a unique, supported ID per entry.')
        ids.add(ident)
    return key,rows,hashlib.sha256(raw).hexdigest()


class Shelf:
    def __init__(self, folder):
        self.folder=Path(folder)/'writing-packs'
        self.stamp=None;self.rows={};self.summary={};self.errors=[]

    def sync(self):
        paths=sorted(self.folder.glob('*.json'))
        stamp=tuple((p,p.stat().st_mtime_ns,p.stat().st_size) for p in paths)
        if stamp==self.stamp: return
        rows=defaultdict(list);summary={};errors=[];used=set()
        for path,_,size in stamp:
            try:
                if size>LIMIT: raise ValueError('Pack exceeds 64 MiB.')
                key,entries,digest=parse(path.read_bytes())
                ids={r['id'] for r in entries}
                if ids & used: raise ValueError('Variation IDs overlap another pack.')
                for r in entries: rows[r['slot']].append((r,digest))
                summary[key]=len(entries);used.update(ids)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                errors.append(str(exc))
        self.rows=rows;self.summary=summary;self.errors=errors;self.stamp=stamp

    def install(self, raw):
        key,entries,_=parse(raw)
        self.folder.mkdir(exist_ok=True)
        path=self.folder/(hashlib.sha256(key.encode()).hexdigest()+'.json')
        ids={r['id'] for r in entries}
        for other in self.folder.glob('*.json'):
            if other!=path:
                try: _,existing,_=parse(other.read_bytes())
                except (OSError,ValueError,KeyError,TypeError): continue
                if any(r['id'] in ids for r in existing): raise ValueError('An entry ID is already used in another pack.')
        temp=self.folder/('.'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('wb') as f: f.write(raw);f.flush();os.fsync(f.fileno())
            os.replace(temp,path)
        finally: temp.unlink(missing_ok=True)
        self.stamp=None;self.sync()

    def stage(self, slot, facts, rng, recent):
        if 'lineup' not in facts: return None
        matches=[(r,d) for r,d in self.rows.get(slot,[])
                 if all(type(facts.get(k)) is type(v) and facts[k]==v for k,v in r['when'].items())]
        if not matches: return None
        fresh=[item for item in matches if item[0]['id'] not in recent]
        row,digest=rng.choice(sorted(fresh or matches,key=lambda p:p[0]['id']))
        return {'id':row['id'],'text':row['text'],'pack':digest}

    def event(self, decision, catalog, rng):
        from .management import DECISIONS
        kind=decision['kind']; rule=DECISIONS[kind]; people=catalog['people']
        values={'payout':rule.get('revenue'),'energy_cost':rule.get('energy'),'cash_cost':rule.get('cost'),
                'energy_restore':rule.get('restore_energy'),'loyalty_gain':rule.get('loyalty'),
                'extra_seconds':round(decision.get('extra_time',0)),'reputation_gain':2,'promotion_nights':3,
                'worker':people.get(decision.get('worker'),{}).get('name'),'partner':people.get(decision.get('partner'),{}).get('name')}
        rows=[r for r,_ in self.rows.get('event.'+kind,[]) if all(values.get(k) is not None for k in r['tokens'])]
        if not rows: return
        row=rng.choice(sorted(rows,key=lambda r:r['id']))
        def fill(text): return TOKEN.sub(lambda m:str(values[m[1]]),text)
        decision['copy']={'title':fill(row['title']),'detail':fill(row['text']),'id':row['id']}
