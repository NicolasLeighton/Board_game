"""
config_editor.py - reads and rewrites config.py for the in-game Config
screen.

config.py stays the one place the rules live, and stays a file you can
edit by hand: this module changes only the VALUES of the settings it
knows about and leaves every comment, blank line and setting it doesn't
know about exactly as it was. It finds each value with Python's own parser
rather than by pattern-matching text, so a value spread over several
lines - WHITE_SETUP - is replaced whole and nothing else is touched.

Nothing here imports pygame; config_screen.py draws the screen.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.py")


# ======================================================================
# What the Config screen offers
# ======================================================================
# kind:  "bool"   - on or off
#        "int"    - a number between lo and hi, in steps of `step`
#        "choice" - one of `options`, as (value, label) pairs
#
# Settings left out - PIECE_CODES, GAME_LOG_FOLDER - are still in
# config.py for editing by hand. The openings - WHITE_SETUP and
# WHITE_SETUP_FLAT, one for each way the board can be turned - have their
# own page.

SETTINGS: List[Dict] = [
    {"group": "Board"},
    {"key": "BOARD_ORIENTATION", "label": "Board turned", "kind": "choice",
     "options": [("point", "Point to point"), ("flat", "Flat side to flat")],
     "help": "a corner of the board at each army's back, or a flat side"},
    {"key": "BOARD_RADIUS", "label": "Board size", "kind": "int", "lo": 2, "hi": 7,
     "help": "rings around the centre point - 5 is Glinski's 91 points",
     "show": lambda v: f"{v}  ({3 * v * (v + 1) + 1} points)"},
    {"key": "MIRRORED_SETUP", "label": "Black's army", "kind": "choice",
     "options": [(False, "Turned 180°"), (True, "Mirrored")],
     "help": "how Black's pieces are laid out from yours"},

    {"group": "Rules"},
    {"key": "GENERALS_CANT_TOUCH", "label": "Generals can't touch", "kind": "bool",
     "help": "the two Generals may never stand side by side"},
    {"key": "SANDBOX", "label": "Sandbox", "kind": "bool",
     "help": "no turns, no opponent: move anything anywhere"},

    {"group": "Controls"},
    {"key": "MOVEMENT_TYPE", "label": "Moving pieces", "kind": "choice",
     "options": [(1, "Click or drag"), (2, "Click only"), (3, "Drag only")],
     "help": "how the left mouse button moves a piece"},
    {"key": "FREE_ARROWS", "label": "Free arrows", "kind": "bool",
     "help": "off: arrows snap to the lines and the Knight's leaps"},
    {"key": "KNIGHT_ARROW_PATH", "label": "Bent Knight arrows", "kind": "bool",
     "help": "Knight arrows go two out, then one to the side"},
    {"key": "SHOW_MOVEMENT_HINTS", "label": "Movement diagrams", "kind": "bool",
     "help": "how each piece moves, drawn on its tile"},

    {"group": "Display"},
    {"key": "FLIP_WHEN_BLACK", "label": "Turn board for Black", "kind": "bool",
     "help": "show Black at the bottom when you play Black"},
    {"key": "BOARD_FLIP_DELAY_MS", "label": "Turn delay", "kind": "int",
     "lo": 0, "hi": 3000, "step": 250,
     "help": "how long the board waits before turning",
     "show": lambda v: f"{v / 1000:g} s"},
    {"key": "SAVE_GAME_LOGS", "label": "Save game logs", "kind": "bool",
     "help": "write every game to the logs folder"},
]

SETUPS = ("WHITE_SETUP", "WHITE_SETUP_FLAT")
EDITABLE = [s["key"] for s in SETTINGS if "key" in s] + list(SETUPS)


# ======================================================================
# Reading
# ======================================================================

def _assignments(text: str) -> Dict[str, ast.Assign]:
    """Every top-level `NAME = value` in the file, by name."""
    found = {}
    for node in ast.parse(text).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            found[node.targets[0].id] = node
    return found


def load(path: str = CONFIG_PATH) -> Dict:
    """The current value of every setting the screen can edit."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    values = {}
    for name, node in _assignments(text).items():
        if name in EDITABLE:
            values[name] = ast.literal_eval(node.value)
    return values


# ======================================================================
# Writing
# ======================================================================

FILE_LETTERS = "abcdefghiklmnopq"


def format_setup(lines: List[str], letters: bool = True) -> str:
    """An opening written the way config.py lays it out: tokens in aligned
    columns, under a header of file letters when every line is one token
    per file (WHITE_SETUP; the flat opening's rows differ in length)."""
    rows = [line.split() for line in lines]
    files = max((len(r) for r in rows), default=0)
    header = ("    #  " + "  ".join(FILE_LETTERS[:files]) + "\n") if letters else ""
    body = []
    for row in rows:
        cells = "".join(f"{t:<3s}" for t in row).rstrip()
        body.append(f'    "{cells}",')
    return "[\n" + header + "\n".join(body) + "\n]"


def _literal(name: str, value) -> str:
    if name in SETUPS:
        return format_setup(value, letters=name == "WHITE_SETUP")
    return repr(value)


def rewrite(text: str, changes: Dict) -> str:
    """config.py's text with these values replaced, and nothing else.

    Each value is located by the parser and swapped for the new one,
    working from the bottom of the file up so earlier positions stay
    valid. A comment on the same line, after the value, is kept."""
    nodes = _assignments(text)
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def offset(lineno: int, col: int) -> int:
        # ast columns count UTF-8 bytes, not characters.
        line = lines[lineno - 1]
        return starts[lineno - 1] + len(line.encode("utf-8")[:col].decode("utf-8", "ignore"))

    spans = []
    for name, value in changes.items():
        node = nodes.get(name)
        if node is None:
            raise KeyError(f"{name} is not in config.py")
        v = node.value
        spans.append((offset(v.lineno, v.col_offset),
                      offset(v.end_lineno, v.end_col_offset), _literal(name, value)))
    for start, end, new in sorted(spans, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def check(text: str) -> Optional[str]:
    """Would the game start with this config.py? Returns the problem, or
    None if it would.

    Answered by actually trying: the new file is put in a scratch folder
    beside copies of the rules, and a separate Python loads them and sets
    up the opening position. That runs every check Rules.py makes - a
    setup that doesn't fit the board, two Generals, armies overlapping -
    without this screen having to know any of them."""
    folder = tempfile.mkdtemp(prefix="hexcharge-config-")
    try:
        for name in ("Rules.py", "ai_config.py"):
            shutil.copy(os.path.join(HERE, name), folder)
        with open(os.path.join(folder, "config.py"), "w", encoding="utf-8") as handle:
            handle.write(text)
        probe = ("import Rules\n"
                 "Rules.GameState()\n")
        result = subprocess.run([sys.executable, "-c", probe], cwd=folder,
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return None
        lines = [l for l in result.stderr.strip().splitlines() if l.strip()]
        last = lines[-1] if lines else "the rules would not load"
        # "ValueError: WHITE_SETUP has ..." -> just the message.
        return last.split(": ", 1)[1] if ": " in last else last
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def save(changes: Dict, path: str = CONFIG_PATH) -> Optional[str]:
    """Writes the changes to config.py if the game would still start with
    them. Returns the problem instead, leaving the file untouched."""
    if not changes:
        return None
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    new_text = rewrite(text, changes)
    problem = check(new_text)
    if problem is not None:
        return problem
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(new_text)
    return None


# ======================================================================
# Keeping the opening when the board changes size
# ======================================================================

def resize_setup_flat(lines: List[str], old_radius: int,
                      new_radius: int) -> Optional[List[str]]:
    """The flat-side opening on a board of another size. Every row gains or
    loses one point per ring, so it can't stay exactly centred: the new
    point goes at alternate ends, ring by ring, which keeps the army within
    half a point of the middle. None if shrinking would push a piece off
    the board."""
    rows = [line.split() for line in lines]
    radius = old_radius
    while radius != new_radius:
        grow = new_radius > radius
        left = (radius % 2 == 0) == grow           # alternate ends
        for k, tokens in enumerate(rows):
            if grow:
                rows[k] = (["."] + tokens) if left else (tokens + ["."])
                continue
            ends = [0, len(tokens) - 1] if left else [len(tokens) - 1, 0]
            for end in ends:
                if tokens[end] == ".":
                    del tokens[end]
                    break
            else:
                return None
        radius += 1 if grow else -1
    return [" ".join(tokens) for tokens in rows]


def resize_setup(lines: List[str], old_radius: int, new_radius: int) -> Optional[List[str]]:
    """The same opening on a board of another size: one empty file added
    or taken away at each side per ring, so the army stays centred on the
    middle file. None if shrinking would push a piece off the board."""
    out = []
    for line in lines:
        tokens = line.split()
        grow = new_radius - old_radius
        if grow >= 0:
            tokens = ["."] * grow + tokens + ["."] * grow
        else:
            cut = -grow
            if any(t != "." for t in tokens[:cut] + tokens[len(tokens) - cut:]):
                return None
            tokens = tokens[cut:len(tokens) - cut]
        out.append(" ".join(tokens))
    return out
