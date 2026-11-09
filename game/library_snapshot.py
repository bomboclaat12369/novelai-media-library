"""Read-only use of the companion's exact ranking/presentation policy.

Never construct LibraryStore or BattleRankings: their constructors can migrate
source files. Only the pure snapshot methods below are called, without sync,
vote, arrival consumption, history fitting, or persistence.
"""
from functools import lru_cache
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace


@lru_cache(maxsize=1)
def runtime():
    path=Path(__file__).resolve().parents[1]/'runtime-src'/'companion-runtime.pyw'
    loader=SourceFileLoader('after_hours_readonly_runtime',str(path))
    module=module_from_spec(spec_from_loader(loader.name,loader))
    loader.exec_module(module)
    return module


def rows(data,battles):
    module=runtime()
    people={p['id']:p for p in data['characters']}
    ranking=module.BattleRankings.__new__(module.BattleRankings)
    ranking.store=SimpleNamespace(data=data,character=lambda owner:people[owner],_in_main=module.LibraryStore._in_main)
    result={}
    for owner in people:
        board=battles.get('boards',{}).get(owner+':images',{'ratings':{}})
        entries=ranking._entries(owner,'images')
        entries={i:e for i,e in entries.items() if not e.get('flagged_for_removal')}
        ranked=ranking._ranked_rows(board,entries)
        ranking._card_metadata(board,ranked,owner,'images')
        result.update({row['id']:row for row in ranked})
    return result
