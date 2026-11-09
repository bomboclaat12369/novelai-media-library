"""Disk-backed game transactions and durable history, isolated from library files."""
from __future__ import annotations
import copy
from contextlib import contextmanager, closing
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from . import engine


class Conflict(engine.RuleError):
    pass


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class GameStore:
    def __init__(self,path,catalog):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.last_tick=None
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS save(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,digest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL NOT NULL,body TEXT NOT NULL);''')
            old=db.execute("SELECT value FROM meta WHERE key='catalog'").fetchone()
            if old:
                saved=json.loads(old[0])
                if saved['source_id']!=catalog['source_id']:
                    raise engine.RuleError('This save belongs to a different catalog. Select its original source.')
                for ident,card in saved['cards'].items():
                    card['available']=False;card['image']=None;card['original']=None
                    if ident in catalog['cards']:
                        current=catalog['cards'][ident]
                        card.update({k:current[k] for k in ('available','image','original','name','categories')})
                        card['source_categories']=current.get('source_categories',[])
                for ident,card in catalog['cards'].items(): saved['cards'].setdefault(ident,card)
                saved['people'].update(catalog['people'])
                catalog=saved
            self.catalog=catalog
            db.execute("INSERT OR REPLACE INTO meta VALUES ('catalog',?)",(encode(catalog),))
            row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
            if row:
                state=json.loads(row[1])
                if state.get('schema')!=1: raise engine.RuleError('This save needs a supported migration; it was not replaced.')
                if state['phase']=='night':
                    state['night']['paused']=True
                    db.execute('UPDATE save SET revision=?,body=? WHERE id=1',(row[0]+1,encode(state)))

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
            row=db.execute('SELECT revision,body FROM save WHERE id=1').fetchone()
            return {'revision':row[0],'state':json.loads(row[1])} if row else {'revision':0,'state':None}

    def apply(self,action,body,request_id,expected_revision):
        if not isinstance(request_id,str) or not 8<=len(request_id)<=100:
            raise engine.RuleError('A valid request ID is required.')
        if type(expected_revision) is not int: raise Conflict('Refresh the current game state before trying again.')
        digest=hashlib.sha256(encode([action,body]).encode()).hexdigest()
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
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
                delta=0 if self.last_tick is None else min(10,max(0,now-self.last_tick))
                speed=state['night']['speed'] if state['phase']=='night' else 1
                state=engine.command(state,self.catalog,'advance',{'seconds':delta*speed})
            else:
                if action=='advance': raise engine.RuleError('The server owns the game clock.')
                state=engine.command(state,self.catalog,action,body)
            events=state.pop('journal',[]);state['journal']=[]
            db.execute('INSERT OR REPLACE INTO save VALUES (1,?,?)',(revision+1,encode(state)))
            db.execute('INSERT INTO requests VALUES (?,?)',(request_id,digest))
            db.executemany('INSERT INTO events(at,body) VALUES (?,?)',[(time.time(),encode(e)) for e in events])
            db.commit()
            if action in ('new','start','tick','pause','speed','finish'):
                self.last_tick=time.monotonic()
            result={'revision':revision+1,'state':state}
        if action in ('new','pack','upgrade','hire','finish') or any(e['kind']=='night_settled' for e in events):
            self.backup()
        return result

    def backup(self):
        with self.lock,self.connect() as source,closing(sqlite3.connect(str(self.path)+'.backup')) as target:
            source.backup(target)

    def export(self):
        result=self.read()
        public=copy.deepcopy(self.catalog)
        for c in public['cards'].values(): c.pop('image',None);c.pop('original',None)
        with self.connect() as db:
            events=[json.loads(r[0]) for r in db.execute('SELECT body FROM events ORDER BY id')]
        return {'format':'novelai-game-prototype','schema':1,'catalog':public,'save':result,'history':events}
