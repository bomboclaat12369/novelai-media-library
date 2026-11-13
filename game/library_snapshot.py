"""Read-only use of the companion's exact ranking/presentation policy.

Never construct LibraryStore or BattleRankings: their constructors can migrate
source files. Only the pure snapshot methods below are called, without sync,
vote, arrival consumption, history fitting, or persistence.
"""
from functools import lru_cache
import json
import uuid
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace
from .evolution import selected_ids


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
    result, duos, duo_boards = {}, {}, {}
    media = {item['id']: item for item in data['media']}
    pairs = {}
    for group in data.get('sets', []):
        if (not isinstance(group, dict) or group.get('kind', 'set') != 'set' or group.get('in_purgatory')
                or not isinstance(group.get('id'), str) or not group['id'] or group.get('character_id') not in people):
            continue
        sides = selected_ids(group, 'duo', media)
        if sides:
            pairs.setdefault(group['character_id'], []).append((group['id'], sides))
    for owner in people:
        board=battles.get('boards',{}).get(owner+':images',{'ratings':{}})
        entries=ranking._entries(owner,'images')
        if owner in pairs:
            peers = set(entries)
            pair_rows = {}
            for set_id, sides in pairs[owner]:
                # Image Battles identifies the photo pair independently of its display order.
                pair_id = 'duo:' + uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(sorted(sides))).hex
                if pair_id not in pair_rows:
                    if pair_id in board['ratings']:
                        score = ranking._score(board, pair_id)
                    else:
                        # A saved Duo can be previewed before Battles has persisted its first rating.
                        scores = []
                        for mid in sorted(sides):
                            side = ranking._score(board, mid)
                            if mid not in board['ratings']:
                                side.update(board.get('history_priors', {}).get(mid, {}))
                            scores.append(side)
                        score = max(scores, key=lambda side: (side['rating'], side['played'], -side['rd']))
                    peers.difference_update(sides)
                    pair_rows[pair_id] = overall_row(ranking, score)
                duos['duo:' + set_id] = pair_rows[pair_id]
            contenders = [overall_row(ranking, ranking._score(board, mid)) for mid in peers]
            contenders.extend(pair_rows.values())
            duo_boards[owner] = [row for row in contenders if not row['provisional']]
        entries={i:e for i,e in entries.items() if not e.get('flagged_for_removal')}
        ranked=ranking._ranked_rows(board,entries)
        ranking._card_metadata(board,ranked,owner,'images')
        result.update({row['id']:row for row in ranked})
    return result, duos, duo_boards


def overall_row(ranking, score):
    status = ranking._quality(score)
    return {'rating': score['rating'], 'played': score['played'], 'rating_status': status,
            'provisional': status in ('Unrated', 'Provisional')}
