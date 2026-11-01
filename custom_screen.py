"""
custom_screen.py - the Custom difficulty page, opened from the menu.

Choosing Custom under "How strong?" opens this page: every dial that makes
a difficulty, and the computer's aggression, each with arrows either side.
"Start from" copies one of the named levels to tweak from there. "Use
these" writes the values into ai_config.py (CUSTOM_DIFFICULTY), keeping
its comments, so they are there next time; nothing needs restarting, the
next game simply uses them.
"""

from __future__ import annotations

import ast
import os
from typing import Dict, List, Optional

import pygame

import ai_config
import AiCpp
import Ui
from Ui import (BAD, BG, DIM, GOLD, GOOD, MUTED, STAND_BG, STAND_EDGE, TEXT,
                clamp, fit_text)

HERE = os.path.dirname(os.path.abspath(__file__))
AI_CONFIG_PATH = os.path.join(HERE, "ai_config.py")


def _seconds(v: float) -> str:
    return f"{v:g} s"


def _aggression(v: float) -> str:
    v = int(v)
    word = ("Very cautious" if v <= 15 else "Cautious" if v <= 35 else
            "Balanced" if v <= 60 else "Aggressive" if v <= 85 else "Reckless")
    return f"{v}  {word}"


# Each dial: its key in CUSTOM_DIFFICULTY, a name, a line of explanation,
# the values the arrows step through, and how a value is written.
DIALS: List[Dict] = [
    {"key": "depth", "label": "Look-ahead",
     "help": "how many moves ahead it may look, time allowing",
     "steps": list(range(1, 21)) + [25, 30, 40, 60],
     "show": lambda v: "as far as time allows" if v >= 40 else f"{int(v)} moves"},
    {"key": "seconds", "label": "Thinking time",
     "help": "the most it thinks over one move",
     "steps": [0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0,
               10.0, 15.0, 20.0, 30.0, 45.0, 60.0],
     "show": _seconds},
    {"key": "branching", "label": "Moves considered",
     "help": "how many moves per position it looks at; fewer overlooks things",
     "steps": [4, 6, 8, 10, 14, 20, 28, 36, 44, 64, 100],
     "show": lambda v: "all of them" if v >= 100 else f"best {int(v)}"},
    {"key": "qply", "label": "Following captures",
     "help": "captures it follows past the horizon; at 0 it leaves pieces hanging",
     "steps": list(range(0, 11)),
     "show": lambda v: "none" if v == 0 else f"{int(v)} deep"},
    {"key": "noise", "label": "Mistakes",
     "help": "how often it plays a move that isn't its best",
     "steps": [0.0, 10.0, 20.0, 30.0, 45.0, 60.0, 100.0, 150.0, 250.0, 400.0],
     "show": lambda v: "never" if v == 0 else
             ("rarely" if v <= 20 else "sometimes" if v <= 60 else
              "often" if v <= 150 else "a lot") + f"  ({int(v)})"},
    {"key": "window", "label": "Worst slip",
     "help": "how much worse than its best a mistake may be - a Pawn is 100",
     "steps": [0.0, 25.0, 50.0, 100.0, 150.0, 200.0, 300.0, 500.0, 900.0],
     "show": lambda v: "none" if v == 0 else f"up to {int(v)}"},
    {"key": "aggression", "label": "Aggression",
     "help": "attack or safety: how it weighs the Generals, and what a draw is worth to it",
     "steps": list(range(0, 101, 10)),
     "show": _aggression},
]


def preset(index: int) -> Dict:
    """A named level's dials, as Custom values. Aggression is left alone."""
    _name, depth, seconds, branching, qply, noise, window = AiCpp.DIFFICULTIES[index]
    return {"depth": depth, "seconds": float(seconds), "branching": branching,
            "qply": qply, "noise": float(noise), "window": float(window)}


def format_custom(values: Dict) -> str:
    order = [d["key"] for d in DIALS]
    lines = ["{"]
    for key in order + [k for k in values if k not in order]:
        lines.append(f"    {key!r}: {values[key]!r},".replace("'", '"'))
    lines.append("}")
    return "\n".join(lines)


def save_custom(values: Dict, path: str = AI_CONFIG_PATH) -> None:
    """Writes CUSTOM_DIFFICULTY into ai_config.py, keeping everything else
    in the file as it is - or adds it at the end if it isn't there."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    literal = format_custom(values)
    node = None
    for item in ast.parse(text).body:
        if (isinstance(item, ast.Assign) and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
                and item.targets[0].id == "CUSTOM_DIFFICULTY"):
            node = item.value
    if node is None:
        text = text.rstrip("\n") + "\n\n\nCUSTOM_DIFFICULTY = " + literal + "\n"
    else:
        lines = text.splitlines(keepends=True)
        start = sum(len(l) for l in lines[:node.lineno - 1]) + len(
            lines[node.lineno - 1].encode("utf-8")[:node.col_offset].decode("utf-8", "ignore"))
        end = sum(len(l) for l in lines[:node.end_lineno - 1]) + len(
            lines[node.end_lineno - 1].encode("utf-8")[:node.end_col_offset].decode("utf-8", "ignore"))
        text = text[:start] + literal + text[end:]
    compile(text, path, "exec")                     # never write a broken file
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    ai_config.CUSTOM_DIFFICULTY = dict(values)      # the next game uses them


class CustomScreen:

    def __init__(self, layout: "Ui.Layout", fonts: "Ui.Fonts") -> None:
        self.layout, self.fonts = layout, fonts
        self.saved = AiCpp.custom_settings()
        self.values = dict(self.saved)
        self.buttons: Dict[str, pygame.Rect] = {}
        self.message, self.message_bad = "", False

    def resize(self, layout, fonts) -> None:
        self.layout, self.fonts = layout, fonts

    # --- drawing ---------------------------------------------------------

    def button(self, screen, key, rect, text, primary=False, chosen=False) -> None:
        F = self.fonts
        fill = GOLD if primary else ((56, 62, 78) if chosen else STAND_BG)
        pygame.draw.rect(screen, fill, rect, border_radius=9)
        pygame.draw.rect(screen, GOLD if primary or chosen else STAND_EDGE, rect, 1, border_radius=9)
        ink = (24, 22, 18) if primary else TEXT
        img = F.normal.render(fit_text(F.normal, text, rect.width - 10), True, ink)
        screen.blit(img, img.get_rect(center=rect.center))
        self.buttons[key] = rect

    def draw(self, screen) -> None:
        L, F = self.layout, self.fonts
        self.buttons = {}
        screen.fill(BG)
        cx = L.win_w // 2
        width = int(clamp(L.win_w * 0.62, 420, 760))
        left = cx - width // 2

        y = int(L.win_h * 0.05)
        title = F.title.render("Custom difficulty", True, GOLD)
        screen.blit(title, title.get_rect(midtop=(cx, y)))
        y += title.get_height() + 6
        note = F.small.render("Set every dial by hand. Changed ones are marked in gold.", True, MUTED)
        screen.blit(note, note.get_rect(midtop=(cx, y)))
        y += note.get_height() + 14

        # Start from a named level.
        label = F.normal.render("Start from", True, TEXT)
        screen.blit(label, (left, y))
        y += label.get_height() + 6
        names = [d[0] for d in AiCpp.DIFFICULTIES]
        gap = 8
        bw = (width - gap * (len(names) - 1)) // len(names)
        bh = int(clamp(L.win_h * 0.045, 30, 42))
        for i, name in enumerate(names):
            same = all(abs(float(self.values[k]) - float(v)) < 1e-9 for k, v in preset(i).items())
            self.button(screen, f"preset:{i}", pygame.Rect(left + i * (bw + gap), y, bw, bh),
                        name, chosen=same)
        y += bh + 16

        # The dials.
        bottom_room = int(clamp(L.win_h * 0.06, 36, 50)) + 40
        row_h = int(clamp((L.win_h - y - bottom_room) / len(DIALS), 34, 62))
        for dial in DIALS:
            self.draw_dial(screen, dial, pygame.Rect(left, y, width, row_h - 6))
            y += row_h

        # Use / Cancel.
        bh = int(clamp(L.win_h * 0.06, 36, 50))
        by = L.win_h - bh - 20
        bw = int(width * 0.3)
        self.button(screen, "cancel", pygame.Rect(cx - bw - 8, by, bw, bh), "Cancel")
        self.button(screen, "use", pygame.Rect(cx + 8, by, bw, bh), "Use these", primary=True)
        if self.message:
            img = F.small.render(fit_text(F.small, self.message, width), True,
                                 BAD if self.message_bad else GOOD)
            screen.blit(img, img.get_rect(midbottom=(cx, by - 6)))

    def draw_dial(self, screen, dial: Dict, rect: pygame.Rect) -> None:
        F = self.fonts
        key = dial["key"]
        value = self.values[key]
        changed = abs(float(value) - float(self.saved.get(key, value))) > 1e-9
        pygame.draw.rect(screen, (34, 32, 30), rect, border_radius=8)

        ch = int(clamp(rect.height * 0.62, 22, 34))
        box_w = int(clamp(rect.width * 0.40, 170, 280))
        box = pygame.Rect(0, 0, box_w, ch)
        box.midright = (rect.right - 10, rect.centery)
        pygame.draw.rect(screen, STAND_BG, box, border_radius=7)
        pygame.draw.rect(screen, STAND_EDGE, box, 1, border_radius=7)
        less = pygame.Rect(box.left, box.top, ch, ch)
        more = pygame.Rect(box.right - ch, box.top, ch, ch)
        steps = dial["steps"]
        index = self.index_of(dial)
        for r, glyph, k, live in ((less, "<", "dec", index > 0), (more, ">", "inc", index < len(steps) - 1)):
            img = F.normal.render(glyph, True, GOLD if live else DIM)
            screen.blit(img, img.get_rect(center=r.center))
            self.buttons[f"{k}:{key}"] = r
        text = dial["show"](value)
        img = F.normal.render(fit_text(F.normal, text, box_w - 2 * ch - 4), True, TEXT)
        screen.blit(img, img.get_rect(center=box.center))

        room = box.left - rect.left - 24
        x = rect.left + 12
        name = F.normal.render(fit_text(F.normal, dial["label"], room), True, GOLD if changed else TEXT)
        help_img = F.small.render(fit_text(F.small, dial["help"], room), True, DIM)
        show_help = rect.height >= 42
        total = name.get_height() + (help_img.get_height() if show_help else 0)
        ty = rect.centery - total // 2
        screen.blit(name, (x, ty))
        if show_help:
            screen.blit(help_img, (x, ty + name.get_height()))

        if key == "aggression":
            # A small bar under the value: cautious on the left, reckless right.
            bar = pygame.Rect(box.left + ch, box.bottom + 3, box_w - 2 * ch, 3)
            if bar.bottom < rect.bottom:
                pygame.draw.rect(screen, STAND_EDGE, bar)
                fill = bar.copy()
                fill.width = int(bar.width * float(value) / 100)
                pygame.draw.rect(screen, BAD if value > 60 else GOLD if value >= 40 else GOOD, fill)

    def index_of(self, dial: Dict) -> int:
        steps = dial["steps"]
        value = float(self.values[dial["key"]])
        return min(range(len(steps)), key=lambda i: abs(float(steps[i]) - value))

    # --- input -----------------------------------------------------------

    def step(self, key: str, direction: int) -> None:
        dial = next(d for d in DIALS if d["key"] == key)
        steps = dial["steps"]
        i = int(clamp(self.index_of(dial) + direction, 0, len(steps) - 1))
        self.values[key] = steps[i]
        self.message = ""

    def handle_click(self, pos) -> Optional[str]:
        """Returns "use" or "cancel" when the page is left."""
        for key, rect in self.buttons.items():
            if not rect.collidepoint(pos):
                continue
            if key == "cancel":
                return "cancel"
            if key == "use":
                try:
                    save_custom(self.values)
                except (OSError, SyntaxError, ValueError) as problem:
                    self.message, self.message_bad = f"Couldn't save: {problem}", True
                    return None
                return "use"
            if key.startswith("preset:"):
                self.values.update(preset(int(key[7:])))
                self.message, self.message_bad = (
                    f"Copied {AiCpp.DIFFICULTIES[int(key[7:])][0]} - aggression kept.", False)
            elif key.startswith("inc:"):
                self.step(key[4:], 1)
            elif key.startswith("dec:"):
                self.step(key[4:], -1)
            return None
        return None


def summary() -> str:
    """One line for the menu: what Custom is set to now."""
    c = AiCpp.custom_settings()
    depth = "any depth" if c["depth"] >= 40 else f"{int(c['depth'])} moves"
    return f"{depth}, {float(c['seconds']):g} s, aggression {int(c['aggression'])} - click to edit"
