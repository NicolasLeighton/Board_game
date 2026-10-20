"""
engine_report.py - what the engine log says, in averages.

Reads the engine log (ENGINE_LOG_FILE in ai_config.py, or a file named on
the command line) and prints, for each difficulty, how deep the engine
searched and how efficiently:

    python3 engine_report.py
    python3 engine_report.py logs/engine_log.txt

Every search in the log ends with a "summary" line of key=value pairs;
that is all this reads, so the human-readable part above each one can
change freely.
"""

import os
import sys
from collections import defaultdict

import ai_config


def read(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("summary "):
                continue
            row = {}
            for part in line.split()[1:]:
                key, _, value = part.partition("=")
                try:
                    row[key] = float(value)
                except ValueError:
                    row[key] = value
            rows.append(row)
    return rows


def average(rows, key):
    values = [r[key] for r in rows if isinstance(r.get(key), float) and r[key] > 0]
    return sum(values) / len(values) if values else 0.0


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, ai_config.ENGINE_LOG_FILE)
    if not os.path.exists(path):
        print(f"No engine log at {path} yet - play a game with ENGINE_LOG on.")
        return
    rows = read(path)
    if not rows:
        print(f"{path} has no searches in it yet.")
        return
    order = [d[0] for d in ai_config.DIFFICULTIES]
    by_level = defaultdict(list)
    for r in rows:
        by_level[r.get("level", "?")].append(r)
    levels = sorted(by_level, key=lambda name: order.index(name) if name in order else len(order))

    print(f"{len(rows)} searches in {path}\n")
    header = (f"{'level':10s} {'searches':>8s} {'depth':>6s} {'max':>4s} {'deepest':>8s} "
              f"{'k pos/s':>8s} {'time':>6s} {'budget':>7s} {'clock':>6s} {'branch':>7s} "
              f"{'table':>6s} {'1st cut':>8s}")
    print(header)
    print("-" * len(header))
    for name in levels:
        rs = by_level[name]
        clock = 100.0 * sum(1 for r in rs if r.get("stopped") == 1.0) / len(rs)
        print(f"{name:10s} {len(rs):8d} {average(rs, 'depth'):6.1f} {max(r['depth'] for r in rs):4.0f} "
              f"{average(rs, 'seldepth'):8.1f} {average(rs, 'nps') / 1000:8.0f} "
              f"{average(rs, 'time'):5.2f}s {average(rs, 'budget'):6.2f}s {clock:5.0f}% "
              f"{average(rs, 'ebf'):7.2f} {average(rs, 'tt_hit'):5.0f}% {average(rs, 'first_cut'):7.0f}%")
    print("""
depth     the depth fully searched, on average and at most
deepest   the longest line looked at, captures included
k pos/s   thousands of positions searched per second
time      thinking time actually used, against the budget allowed
clock     how often the budget ran out before the depth asked for
branch    how many times longer each extra ply took (lower is better)
table     how often a position had already been searched
1st cut   how often the first move tried was good enough to stop there
          (a measure of move ordering - higher is better)""")


if __name__ == "__main__":
    main()
