#!/usr/bin/env python3
"""Compare cold-start matchmaking against a local Git revision, using no user data.

python tools/benchmark-ranking-start.py --baseline-ref 08d45f2 --entries 120 --votes 150
Both versions use the same synthetic preferences and independent seeded noise.
Pairwise agreement excludes true-rating gaps <= 50 (ambiguous near-neighbors).
This measures comparisons to placement, not a promise about real collections.
"""
import argparse
import hashlib
import json
import random
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'runtime-src/companion-runtime.pyw'


def simulate(source, label, entries, truth, args):
    namespace = {'__name__':'ranking_benchmark', '__file__':str(ROOT / SOURCE)}
    exec(compile(source, str(ROOT / SOURCE), 'exec'), namespace)
    battle = object.__new__(namespace['BattleRankings'])
    battle.rng = random.Random(args.seed + 100)
    board = {'ratings':{}, 'history_priors':{}, 'history':[], 'recent':[], 'votes':0,
             'session':{'mode':'rank', 'minimum':1, 'similar':False, 'category':'', 'limit':0, 'done':0}}
    if hasattr(battle, '_starting_preferences'):
        battle._starting_preferences(board, entries, 'images')
    noise = random.Random(args.seed + 200)
    milestones, snapshots = {}, []
    started = time.perf_counter()
    for count in range(1, args.votes + 1):
        pair = battle._pair(board, entries)
        left, right = pair['left'], pair['right']
        difference = truth[left] - truth[right] + noise.gauss(0, args.noise)
        outcome = 'left' if difference > 25 else 'right' if difference < -25 else 'tie'
        before = battle._apply_comparison(board, pair, outcome)
        board['history'].append({'type':'vote', 'id':str(count), 'left':left, 'right':right,
                                 'outcome':outcome, 'before':before})
        board['recent'] = (board['recent'] + [[left, right]])[-32:]
        battle._fit_history(board)
        placed = [row for row in battle._ranked_rows(board, entries) if not row['provisional']]
        for target in sorted({1, 5, 8, 10, 20, 40, 60, 100, args.entries}):
            if len(placed) >= target:
                milestones.setdefault(str(target), count)
        if count in {25, 50, 100, 150, args.votes}:
            pairs = [(x, y) for at, x in enumerate(placed) for y in placed[at+1:]
                     if abs(truth[x['id']] - truth[y['id']]) > 50]
            correct = sum((x['rating']-y['rating']) * (truth[x['id']]-truth[y['id']]) > 0 for x,y in pairs)
            snapshots.append({'votes':count, 'placed':len(placed), 'seen':len(board['ratings']),
                              'pairwise_agreement':round(correct/len(pairs), 4) if pairs else None})
    return {'model':label, 'first_placed_at':milestones, 'snapshots':snapshots,
            'seconds':round(time.perf_counter()-started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--entries', type=int, default=120)
    parser.add_argument('--votes', type=int, default=150)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--noise', type=float, default=65)
    parser.add_argument('--favorites', choices=['helpful','none','all','wrong'], default='helpful')
    args = parser.parse_args()
    if not 5 <= args.entries <= 2000 or not 1 <= args.votes <= 10000 or not 0 <= args.noise <= 1000:
        parser.error('Fixture size/noise outside supported bounds')
    original = subprocess.check_output(['git','show',args.baseline_ref+':'+SOURCE], cwd=ROOT)
    current = (ROOT / SOURCE).read_bytes()
    rng = random.Random(args.seed)
    truth = {str(i):rng.gauss(1200, 230) for i in range(args.entries)}
    entries = {i:{'id':i, 'name':i, 'images':[i], 'count':1,
        'favorite':(value>1340 and rng.random()<.65) if args.favorites=='helpful' else
                    True if args.favorites=='all' else
                    (value<1050 and rng.random()<.65) if args.favorites=='wrong' else False}
        for i,value in truth.items()}
    result = {'schema':1, 'baseline_ref':args.baseline_ref,
              'current_runtime_sha256':hashlib.sha256(current).hexdigest(),
              'entries':args.entries, 'votes':args.votes, 'seed':args.seed, 'noise_sd':args.noise,
              'favorites':args.favorites, 'favorite_count':sum(e['favorite'] for e in entries.values()),
              'agreement_minimum_true_gap':50,
              'results':[simulate(original, 'previous', entries, truth, args),
                         simulate(current, 'fast_start', entries, truth, args)]}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
