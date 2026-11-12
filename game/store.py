"""Disk-backed game transactions and durable history, isolated from library files."""
from __future__ import annotations
import copy
from contextlib import contextmanager, closing
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from . import engine, evolution, migrations, stage_labels


class Conflict(engine.RuleError):
    pass


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def merge_catalog(previous, current, owned):
    """Keep career balance and acquired sequences. Only the live reader supplies artwork."""
    if not isinstance(previous.get('cards'), dict) or not isinstance(previous.get('people'), dict):
        raise engine.RuleError('The saved catalog is invalid.')
    cards = dict(current['cards'])
    for ident, old in previous['cards'].items():
        if not isinstance(old, dict):
            raise engine.RuleError('The saved card is invalid.')
        live = current['cards'].get(ident)
        card = dict(live or old)
        if not live:
            card.update(available=False, image=None, original=None)
        for key in ('rarity', 'specialty', 'rarity_schema'):
            if key in old:
                card[key] = old[key]
        if card.get('source') in evolution.SET_CARDS:
            keys = evolution.form_keys(old.get('forms'), card['source'])
            if ident in owned and not keys:
                raise engine.RuleError('The saved Set card has an invalid photo selection.')
            if ident in owned or not live:
                verified = {f['key']: f for f in (live or {}).get('forms', [])}
                card['forms'] = [verified.get(key, {'key': key}) for key in keys]
                if not all(f.get('original') for f in card['forms']):
                    card['available'] = False
        else:
            card.pop('forms', None)
        cards[ident] = card
    # A newly eligible Duo inherits this career's frozen ordinary photo rarities.
    for ident in current['cards'].keys() - previous['cards'].keys():
        card = cards[ident]
        if card.get('source') == 'duo':
            cards[ident] = {**card, 'rarity': evolution.duo_rarity(card['forms'], cards)}
    return {**current, 'cards': cards, 'people': {**previous['people'], **current['people']}}


class GameStore:
    def __init__(self,path,catalog):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.last_tick=None
        self.label_path=self.path.parent/'stage-labels.json'
        self.label_stamp=None;self.label_pack=stage_labels.bundled();self.label_error=None
        self.sync_labels()
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS save(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL NOT NULL,body TEXT NOT NULL);''')
            row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
            state=migrations.migrate(json.loads(row[1])) if row else None
            if row and json.loads(row[1]).get('schema') != migrations.SCHEMA:
                before=self.path.with_name(self.path.name+'.before-schema-2')
                if not before.exists():
                    with closing(sqlite3.connect(before)) as target: db.backup(target)
            old=db.execute("SELECT value FROM meta WHERE key='catalog'").fetchone()
            self.source_catalog=catalog
            if old:
                saved=json.loads(old[0])
                if saved['source_id']!=catalog['source_id']:
                    raise engine.RuleError('This save belongs to a different catalog. Select its original source.')
                catalog=merge_catalog(saved,catalog,state['owned'] if state else {})
            self.catalog=catalog
            db.execute("INSERT OR REPLACE INTO meta VALUES ('catalog',?)",(encode(catalog),))
            self.catalog_stamp=uuid.uuid4().hex
            db.execute("INSERT OR REPLACE INTO meta VALUES ('catalog_stamp',?)",(self.catalog_stamp,))
            if row:
                migrations.validate(state,catalog)
                events=state.pop('journal',[]);state['journal']=[]
                db.executemany('INSERT INTO events(at,body) VALUES (?,?)',[(time.time(),encode(e)) for e in events])
                if encode(state)!=row[1]:
                    db.execute('UPDATE save SET revision=?,body=? WHERE id=1',(row[0]+1,encode(state)))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('clock_tick',?)",(str(time.monotonic()),))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        try:
            db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.lock,self.connect() as db:
            self.sync_labels()
            self.sync_catalog(db)
            row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
            return {'revision':row[0],'state':json.loads(row[1])} if row else {'revision':0,'state':None}

    def sync_labels(self):
        try:
            info=self.label_path.stat()
            stamp=(info.st_mtime_ns,info.st_size)
            if stamp==self.label_stamp: return
            if info.st_size>stage_labels.MAX_BYTES: raise ValueError('The custom label pack exceeds 32 MB.')
            pack=stage_labels.LabelPack(self.label_path.read_bytes())
            self.label_pack=pack;self.label_stamp=stamp;self.label_error=None
        except FileNotFoundError:
            self.label_pack=stage_labels.bundled();self.label_stamp=None;self.label_error=None
        except (OSError,ValueError) as exc:
            # A broken optional text file cannot prevent playing/recovering a save.
            self.label_pack=stage_labels.bundled();self.label_error=str(exc)
            if isinstance(exc,ValueError): self.label_stamp=stamp

    def label_info(self):
        with self.lock:
            self.sync_labels()
            return {**self.label_pack.summary,'custom':self.label_stamp is not None and not self.label_error,
                    'error':self.label_error}

    def import_labels(self, raw):
        pack=stage_labels.load_upload(raw)
        with self.lock:
            temp=self.label_path.with_name(f'.stage-labels-{uuid.uuid4().hex}.tmp')
            try:
                with temp.open('wb') as target:
                    target.write(pack.raw);target.flush();os.fsync(target.fileno())
                os.replace(temp,self.label_path)
            finally:
                temp.unlink(missing_ok=True)
            self.label_stamp=None;self.sync_labels()
        return self.label_info()

    def sync_catalog(self,db):
        stamp=db.execute("SELECT value FROM meta WHERE key='catalog_stamp'").fetchone()
        if stamp and stamp[0]!=self.catalog_stamp:
            self.catalog=json.loads(db.execute("SELECT value FROM meta WHERE key='catalog'").fetchone()[0])
            self.catalog_stamp=stamp[0]

    def apply(self,action,body,request_id,expected_revision):
        if not isinstance(request_id,str) or not 8<=len(request_id)<=100:
            raise engine.RuleError('A valid request ID is required.')
        if type(expected_revision) is not int: raise Conflict('Refresh the current game state before trying again.')
        digest=hashlib.sha256(encode([action,body]).encode()).hexdigest()
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sync_labels()
            self.sync_catalog(db)
            duplicate=db.execute('SELECT digest FROM requests WHERE id=?',(request_id,)).fetchone()
            row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
            revision,state=(row[0],json.loads(row[1])) if row else (0,None)
            if duplicate:
                if duplicate[0]!=digest: raise Conflict('A request ID was reused for a different action.')
                return {'revision':revision,'state':state,'replayed':True}
            if revision!=expected_revision: raise Conflict('The game changed in another window. Your view has been refreshed.')
            if action=='new':
                if state: raise engine.RuleError('A save already exists. It has not been overwritten.')
                state=engine.new_game(self.catalog,body.get('selected'),body.get('seed',int(time.time())))
                engine.record(state,'game_created',selected=body.get('selected'))
            elif not state:
                raise engine.RuleError('Choose your starting team first.')
            elif action=='tick':
                now=time.monotonic()
                clock=db.execute("SELECT value FROM meta WHERE key='clock_tick'").fetchone()
                delta=0 if not clock else max(0,now-float(clock[0]))
                speed=state['night']['speed'] if state['phase']=='night' else 1
                state=engine.command(state,self.catalog,'advance',{'seconds':delta*speed,'stop_at_decision':True},labels=self.label_pack)
            else:
                if action=='advance': raise engine.RuleError('The server owns the game clock.')
                state=engine.command(state,self.catalog,action,body,labels=self.label_pack)
            events=state.pop('journal',[]);state['journal']=[]
            db.execute('INSERT OR REPLACE INTO save VALUES (1,?,?)',(revision+1,encode(state)))
            db.execute('INSERT INTO requests VALUES (?,?)',(request_id,digest))
            db.executemany('INSERT INTO events(at,body) VALUES (?,?)',[(time.time(),encode(e)) for e in events])
            if action in ('new','start','tick','pause','speed','finish','decision'):
                db.execute("INSERT OR REPLACE INTO meta VALUES ('clock_tick',?)",(str(time.monotonic()),))
            db.commit()
            if action in ('new','start','tick','pause','speed','finish','decision'):
                self.last_tick=time.monotonic()
            result={'revision':revision+1,'state':state}
        if action in ('new','pack','upgrade','hire','finish','schedule','department') or any(e['kind']=='night_settled' for e in events):
            self.backup()
        return result

    def backup(self):
        with self.lock,self.connect() as source,closing(sqlite3.connect(str(self.path)+'.backup')) as target:
            source.backup(target)
        folder=self.path.parent/(self.path.name+'.backups');folder.mkdir(exist_ok=True)
        revision=self.read()['revision']
        snapshot=folder/f'{revision:010d}.sqlite3'
        if not snapshot.exists():
            with self.lock,self.connect() as source,closing(sqlite3.connect(snapshot)) as target: source.backup(target)
        snapshots=sorted(folder.glob('*.sqlite3'))
        for old in snapshots[:-12]: old.unlink()

    def backups(self):
        folder=self.path.parent/(self.path.name+'.backups')
        return [{'id':p.name,'bytes':p.stat().st_size} for p in sorted(folder.glob('*.sqlite3'),reverse=True)]

    def refresh_catalog(self,catalog,expected_revision):
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.sync_catalog(db)
            row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
            revision=row[0] if row else 0
            if revision!=expected_revision: raise Conflict('The game changed. Refresh before importing catalog additions.')
            if catalog['source_id']!=self.catalog['source_id']: raise engine.RuleError('The library identity changed; existing progress was preserved.')
            added=len(catalog['cards'].keys() - self.catalog['cards'].keys())
            merged=merge_catalog(self.catalog,catalog,json.loads(row[1])['owned'] if row else {})
            db.execute("UPDATE meta SET value=? WHERE key='catalog'",(encode(merged),))
            if row: db.execute('UPDATE save SET revision=? WHERE id=1',(revision+1,))
            db.execute('INSERT INTO events(at,body) VALUES (?,?)',(time.time(),encode({'kind':'catalog_refreshed','added':added})))
            stamp=uuid.uuid4().hex
            db.execute("INSERT OR REPLACE INTO meta VALUES ('catalog_stamp',?)",(stamp,))
            db.commit()
            self.catalog=merged;self.catalog_stamp=stamp;self.source_catalog=catalog
        return added

    def restore(self,payload=None,backup=None):
        """Restore to a new sibling save. The current save is never overwritten."""
        if backup is not None:
            allowed={b['id'] for b in self.backups()}
            if backup not in allowed: raise engine.RuleError('Choose one of the listed backups.')
            path=self.path.parent/(self.path.name+'.backups')/backup
            with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)) as db:
                row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
                cat=json.loads(db.execute("SELECT value FROM meta WHERE key='catalog'").fetchone()[0])
                events=[json.loads(r[0]) for r in db.execute('SELECT body FROM events ORDER BY id')]
            payload={'format':'after-hours-game','schema':2,'catalog':cat,'save':{'revision':row[0],'state':json.loads(row[1])},'history':events}
        if not isinstance(payload,dict) or payload.get('format') not in ('novelai-game-prototype','after-hours-game'):
            raise engine.RuleError('Select an After Hours JSON save export.')
        try:
            if payload['catalog']['source_id']!=self.catalog['source_id']: raise engine.RuleError('This export belongs to another library.')
            state=migrations.migrate(payload['save']['state'])
            cat=merge_catalog(payload['catalog'],self.source_catalog,state['owned'])
            migrations.validate(state,cat)
            if state.get('night'): state['night']['paused']=True
            history=payload.get('history',[])
            if not isinstance(history,list) or len(history)>2000000 or any(not isinstance(e,dict) for e in history): raise ValueError()
            history=history+state.pop('journal',[]);state['journal']=[]
        except (KeyError,TypeError,ValueError) as exc:
            if isinstance(exc,engine.RuleError): raise
            raise engine.RuleError('Invalid recovery export. The current save is unchanged.') from None
        self.backup()
        path=self.path.with_name(f'{self.path.stem}-restored-{uuid.uuid4().hex[:10]}.sqlite3')
        restored=GameStore(path,cat)
        restored.source_catalog=self.source_catalog
        with restored.connect() as db:
            db.execute('INSERT INTO save VALUES (1,1,?)',(encode(state),))
            db.executemany('INSERT INTO events(at,body) VALUES (?,?)',[(time.time(),encode(e)) for e in history])
            db.execute('INSERT INTO events(at,body) VALUES (?,?)',(time.time(),encode({'kind':'save_restored','to_new_file':True})))
        restored.backup()
        return restored

    def export(self):
        with self.lock,self.connect() as db:
            db.execute('BEGIN')
            self.sync_catalog(db)
            row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
            result={'revision':row[0],'state':json.loads(row[1])} if row else {'revision':0,'state':None}
            public=copy.deepcopy(self.catalog)
            for ident,c in public['cards'].items():
                c.pop('image',None);c.pop('original',None)
                if 'forms' in c:
                    forms=c.pop('forms')
                    if row and ident in result['state']['owned']:
                        c['forms']=[{'key':key} for key in evolution.form_keys(forms,c['source'])]
            events=[json.loads(r[0]) for r in db.execute('SELECT body FROM events ORDER BY id')]
        return {'format':'after-hours-game','schema':migrations.SCHEMA,'catalog':public,'save':result,'history':events}
