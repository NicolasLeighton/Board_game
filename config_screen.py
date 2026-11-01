"""
config_screen.py - the Config screen, opened from the menu.

Two pages:

  Settings  every switch and number in config.py as a row you click -
            on/off pills, and arrows either side of a number or a choice.
  Opening   the board itself. Pick a piece from the tray and click the
            cells on your half to lay out your army; Black's half shows
            the copy he gets.

Nothing is written until Save. Save checks that the game would actually
start with the new settings, writes them into config.py - keeping its
comments and layout - and restarts the game so every part of it, the
engine included, picks them up. config_editor.py does the reading and
writing; this file only draws and clicks.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional, Tuple

import pygame

import config_editor as E
import Rules as R
import Ui
from board_design import draw_ring, piece_surface
from Ui import (BAD, BG, DIM, GOLD, GOOD, MUTED, PANEL, PANEL_LINE, SELECTED,
                STAND_BG, STAND_EDGE, TEXT, clamp, fit_text)

CHANGED = GOLD                  # a setting you've changed but not saved
HALF_SHADE = (20, 14, 8, 120)   # over Black's half on the Opening page


# ======================================================================
# Turning the opening into points and back
# ======================================================================
# The opening being edited is the one for the way the board is turned now:
# WHITE_SETUP with the point at the back, WHITE_SETUP_FLAT with the flat
# side - Rules.SETUP_NAME says which.

def editable(row: int, col: int) -> bool:
    """A point on White's half: nearer his edge than Black's. A point on
    the middle line belongs to neither."""
    return (R.on_board(row, col)
            and R.rank_for("W", row, col) < R.rank_for("B", row, col))


def cells_from_setup(lines: List[str]) -> Dict[Tuple[int, int], str]:
    """White's pieces by point. Anything that wouldn't fit the board is
    dropped - the page shows what the board can hold."""
    codes = R.PIECE_CODES
    out = {}
    for offset, line in enumerate(lines):
        for (row, col), token in zip(R.rank_cells(offset + 1), line.split()):
            if token in codes and editable(row, col):
                out[(row, col)] = codes[token]
    return out


def setup_from_cells(cells: Dict[Tuple[int, int], str]) -> List[str]:
    """Opening lines for these pieces: as many ranks as the furthest piece
    needs, one token per point of each rank."""
    code_of = {name: code for code, name in R.PIECE_CODES.items()}
    ranks = max((R.rank_of(r, c) for r, c in cells), default=1)
    lines = []
    for rank in range(1, ranks + 1):
        tokens = [code_of[cells[p]] if p in cells else "." for p in R.rank_cells(rank)]
        lines.append(" ".join(tokens))
    return lines


# ======================================================================
# The screen
# ======================================================================

class ConfigScreen:

    def __init__(self, layout: "Ui.Layout", fonts: "Ui.Fonts") -> None:
        self.layout, self.fonts = layout, fonts
        self.saved = E.load()
        self.values = copy.deepcopy(self.saved)
        self.page = "settings"
        self.message = ""
        self.message_bad = False
        self.buttons: Dict[str, pygame.Rect] = {}
        self.brush: Optional[str] = "Pawn"      # None is the eraser
        self.cells = cells_from_setup(self.values[R.SETUP_NAME])

    def resize(self, layout, fonts) -> None:
        self.layout, self.fonts = layout, fonts

    def changes(self) -> Dict:
        return {k: v for k, v in self.values.items() if v != self.saved[k]}

    def say(self, text: str, bad: bool = False) -> None:
        self.message, self.message_bad = text, bad

    # --- drawing helpers -------------------------------------------------

    def button(self, screen, key, rect, text, primary=False, enabled=True) -> None:
        F = self.fonts
        fill = GOLD if primary and enabled else STAND_BG
        pygame.draw.rect(screen, fill, rect, border_radius=9)
        pygame.draw.rect(screen, GOLD if primary else STAND_EDGE, rect, 1, border_radius=9)
        ink = (24, 22, 18) if primary and enabled else (TEXT if enabled else DIM)
        img = F.normal.render(fit_text(F.normal, text, rect.width - 12), True, ink)
        screen.blit(img, img.get_rect(center=rect.center))
        if enabled:
            self.buttons[key] = rect

    def draw_message(self, screen, y) -> None:
        if not self.message:
            return
        F = self.fonts
        img = F.normal.render(fit_text(F.normal, self.message, self.layout.win_w - 40),
                              True, BAD if self.message_bad else GOOD)
        screen.blit(img, img.get_rect(center=(self.layout.win_w // 2, y)))

    def draw(self, screen) -> None:
        self.buttons = {}
        screen.fill(BG)
        if self.page == "settings":
            self.draw_settings(screen)
        else:
            self.draw_opening(screen)

    # --- the Settings page -----------------------------------------------

    def columns(self) -> List[List[Dict]]:
        """The settings split into two columns at a group boundary, as
        evenly as the groups allow."""
        groups: List[List[Dict]] = []
        for entry in E.SETTINGS:
            if "group" in entry:
                groups.append([entry])
            else:
                groups[-1].append(entry)
        total = sum(len(g) for g in groups)
        left, count = [], 0
        while groups and count + len(groups[0]) / 2 <= total / 2:
            count += len(groups[0])
            left += groups.pop(0)
        return [left, [e for g in groups for e in g]]

    def draw_settings(self, screen) -> None:
        L, F = self.layout, self.fonts
        pad = max(16, L.pad)
        title = F.title.render("Config", True, GOLD)
        screen.blit(title, (pad, pad))
        note = F.small.render("Changes are saved into config.py and the game restarts.",
                              True, MUTED)
        screen.blit(note, (pad, pad + title.get_height()))

        top = pad + title.get_height() + note.get_height() + 14
        bottom_bar = int(clamp(L.win_h * 0.07, 40, 56))
        bottom = L.win_h - pad - bottom_bar - 30
        cols = self.columns()
        col_gap = pad * 2
        col_w = (L.win_w - 2 * pad - col_gap) // 2
        rows = max(len(c) for c in cols)
        row_h = int(clamp((bottom - top) / rows, 28, 60))

        for index, column in enumerate(cols):
            x = pad + index * (col_w + col_gap)
            y = top
            for entry in column:
                if "group" in entry:
                    img = F.big.render(entry["group"], True, TEXT)
                    screen.blit(img, (x, y + row_h - img.get_height() - 4))
                    pygame.draw.line(screen, PANEL_LINE, (x, y + row_h - 2), (x + col_w, y + row_h - 2))
                else:
                    self.draw_row(screen, entry, pygame.Rect(x, y, col_w, row_h))
                y += row_h

        y = L.win_h - pad - bottom_bar
        self.draw_message(screen, y - 18)
        w = int(clamp(L.win_w * 0.17, 130, 210))
        gap = 12
        changed = bool(self.changes())
        left = pygame.Rect(pad, y, w, bottom_bar)
        self.button(screen, "opening", left, "Edit opening")
        self.button(screen, "back", pygame.Rect(L.win_w - pad - 3 * w - 2 * gap, y, w, bottom_bar),
                    "Leave unsaved" if changed else "Back")
        self.button(screen, "defaults", pygame.Rect(L.win_w - pad - 2 * w - gap, y, w, bottom_bar),
                    "Undo changes", enabled=changed)
        self.button(screen, "save", pygame.Rect(L.win_w - pad - w, y, w, bottom_bar),
                    "Save & restart", primary=True, enabled=changed)

    def draw_row(self, screen, entry: Dict, rect: pygame.Rect) -> None:
        F = self.fonts
        key = entry["key"]
        value = self.values[key]
        changed = value != self.saved[key]

        # The control, right-aligned.
        ch = int(clamp(rect.height * 0.62, 22, 34))
        cy = rect.centery
        if entry["kind"] == "bool":
            pill = pygame.Rect(0, 0, int(ch * 2.4), ch)
            pill.midright = (rect.right, cy)
            pygame.draw.rect(screen, (70, 120, 84) if value else STAND_BG, pill, border_radius=ch // 2)
            pygame.draw.rect(screen, GOOD if value else STAND_EDGE, pill, 1, border_radius=ch // 2)
            knob = ch // 2 - 3
            kx = pill.right - ch // 2 if value else pill.left + ch // 2
            pygame.draw.circle(screen, TEXT if value else MUTED, (kx, cy), knob)
            word = F.small.render("On" if value else "Off", True, TEXT if value else DIM)
            wx = pill.left + ch // 2 + 2 if value else pill.right - ch // 2 - word.get_width() - 2
            screen.blit(word, (wx, cy - word.get_height() // 2))
            self.buttons[f"row:{key}"] = pill
            control_left = pill.left
        else:
            if entry["kind"] == "int":
                text = entry["show"](value) if "show" in entry else str(value)
            else:
                text = dict(entry["options"]).get(value, str(value))
            box_w = int(clamp(rect.width * 0.36, 120, 210))
            box = pygame.Rect(0, 0, box_w, ch)
            box.midright = (rect.right, cy)
            pygame.draw.rect(screen, STAND_BG, box, border_radius=7)
            pygame.draw.rect(screen, STAND_EDGE, box, 1, border_radius=7)
            arrow = ch
            less = pygame.Rect(box.left, box.top, arrow, ch)
            more = pygame.Rect(box.right - arrow, box.top, arrow, ch)
            for r, glyph, k in ((less, "<", "dec"), (more, ">", "inc")):
                img = F.normal.render(glyph, True, GOLD)
                screen.blit(img, img.get_rect(center=r.center))
                self.buttons[f"{k}:{key}"] = r
            img = F.normal.render(fit_text(F.normal, text, box_w - 2 * arrow - 4), True, TEXT)
            screen.blit(img, img.get_rect(center=box.center))
            control_left = box.left

        # The label and its one-line explanation.
        room = control_left - rect.left - 14
        label = F.normal.render(fit_text(F.normal, entry["label"], room), True,
                                CHANGED if changed else TEXT)
        help_img = F.small.render(fit_text(F.small, entry.get("help", ""), room), True, DIM)
        total = label.get_height() + (help_img.get_height() if rect.height >= 40 else 0)
        y = rect.centery - total // 2
        screen.blit(label, (rect.left + (12 if changed else 0), y))
        if changed:
            pygame.draw.circle(screen, CHANGED, (rect.left + 4, y + label.get_height() // 2), 3)
        if rect.height >= 40:
            screen.blit(help_img, (rect.left + (12 if changed else 0), y + label.get_height()))

    def step(self, key: str, direction: int) -> None:
        entry = next(e for e in E.SETTINGS if e.get("key") == key)
        value = self.values[key]
        if entry["kind"] == "bool":
            new = not value
        elif entry["kind"] == "int":
            new = int(clamp(value + direction * entry.get("step", 1), entry["lo"], entry["hi"]))
        else:
            options = [v for v, _ in entry["options"]]
            index = options.index(value) if value in options else 0
            new = options[(index + direction) % len(options)]
        if new == value:
            return
        if key == "BOARD_RADIUS":
            # Both openings - one for each way the board can be turned -
            # follow it onto the new board. Whatever no longer fits on
            # White's half is taken off rather than blocking the change.
            openings, lost = E.resize_openings(self.values, new)
            self.values.update(openings)
            self.values[key] = new
            self.say(f"{lost} piece{'s' if lost != 1 else ''} didn't fit on the smaller "
                     "board and came off - check the opening." if lost else "")
            return
        self.values[key] = new
        self.say("")

    # --- the Opening page ------------------------------------------------

    def open_opening(self) -> None:
        if (self.values["BOARD_RADIUS"] != R.BOARD_RADIUS
                or (self.values["BOARD_ORIENTATION"] == "flat") != R.FLAT):
            self.say("The board has changed - save first, then lay out the "
                     "opening on the new board.", bad=True)
            return
        self.cells = cells_from_setup(self.values[R.SETUP_NAME])
        self.page = "opening"
        self.say("Pick a piece, then click the points on your half. Right-click clears a point.")

    def preview_state(self) -> "R.GameState":
        """A position holding the opening as it stands, Black included."""
        state = R.GameState()
        state.board = R.Board()
        mirrored = self.values["MIRRORED_SETUP"]
        for (row, col), name in self.cells.items():
            state.board.set(row, col, R.Piece("W", name))
            br, bc = R.black_cell(row, col, mirrored)
            if R.on_board(br, bc):
                state.board.set(br, bc, R.Piece("B", name))
        state.message = ""
        return state

    def draw_opening(self, screen) -> None:
        L, F = self.layout, self.fonts
        L.flipped = False
        view = Ui.GameView(L, F, self.preview_state(), human_sides=())
        view.draw_board(screen)

        # Black's half is his copy: shaded, and not clickable.
        shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        # Shaded triangle by triangle of the lattice, so the edge of the
        # shading runs along the board's own lines.
        for row in range(R.BOARD_SIZE):
            for col in range(R.BOARD_SIZE):
                for d1, d2 in (((0, 1), (1, 0)), ((-1, 1), (0, 1))):
                    tri = [(row, col), (row + d1[0], col + d1[1]), (row + d2[0], col + d2[1])]
                    if all(R.on_board(*p) and not editable(*p) for p in tri):
                        pygame.draw.polygon(shade, HALF_SHADE, [L.square_center(*p) for p in tri])
        screen.blit(shade, (0, 0))
        hover = L.square_at(pygame.mouse.get_pos())
        if hover is not None and editable(*hover):
            draw_ring(screen, SELECTED, L.square_center(*hover), L.cell_w * 0.47, 2)

        # The top bar.
        pygame.draw.rect(screen, (30, 30, 36), pygame.Rect(0, 0, L.win_w, L.top_bar))
        title = F.big.render("Opening", True, GOLD)
        screen.blit(title, (L.pad, (L.top_bar - title.get_height()) // 2))
        if self.message:
            room = L.panel_x - L.pad * 3 - title.get_width()
            img = F.small.render(fit_text(F.small, self.message, room), True,
                                 BAD if self.message_bad else MUTED)
            screen.blit(img, (L.pad * 2 + title.get_width(), (L.top_bar - img.get_height()) // 2))

        # The tray.
        panel = pygame.Rect(L.panel_x, 0, L.panel_w, L.win_h)
        pygame.draw.rect(screen, PANEL, panel)
        pygame.draw.line(screen, PANEL_LINE, panel.topleft, panel.bottomleft)
        x0, y = L.panel_x + L.pad, L.top_bar + L.pad
        head = F.normal.render("Pieces", True, TEXT)
        screen.blit(head, (x0, y))
        y += head.get_height() + 8
        names = list(R.PIECE_CODES.values()) + [None]
        cols = 3
        gap = 10
        tw = (L.panel_w - 2 * L.pad - (cols - 1) * gap) // cols
        th = int(tw * 1.25)
        counts: Dict[str, int] = {}
        for name in self.cells.values():
            counts[name] = counts.get(name, 0) + 1
        for i, name in enumerate(names):
            rect = pygame.Rect(x0 + (i % cols) * (tw + gap), y + (i // cols) * (th + gap), tw, th)
            chosen = self.brush == name
            pygame.draw.rect(screen, (56, 62, 78) if chosen else STAND_BG, rect, border_radius=8)
            pygame.draw.rect(screen, SELECTED if chosen else STAND_EDGE, rect,
                             3 if chosen else 1, border_radius=8)
            caption_h = F.small.get_height()
            art = pygame.Rect(rect.x + 6, rect.y + 4, rect.width - 12, rect.height - caption_h - 10)
            if name is None:
                pygame.draw.line(screen, BAD, (art.centerx - 12, art.centery - 12),
                                 (art.centerx + 12, art.centery + 12), 3)
                pygame.draw.line(screen, BAD, (art.centerx + 12, art.centery - 12),
                                 (art.centerx - 12, art.centery + 12), 3)
                caption = "Erase"
            else:
                pw = min(art.width, int(art.height / 1.1))
                ph = int(pw * 1.1)
                px, py = art.centerx - pw // 2, art.centery - ph // 2
                screen.blit(piece_surface(R.Piece("W", name), pw, ph, False), (px, py))
                view.draw_tile_label(screen, name, "W",
                                     pygame.Rect(px, py - int(ph * 0.12), pw, ph))
                caption = f"{name} {counts.get(name, 0)}"
            cap = F.small.render(fit_text(F.small, caption, tw - 4), True, TEXT if chosen else MUTED)
            screen.blit(cap, cap.get_rect(midbottom=(rect.centerx, rect.bottom - 4)))
            self.buttons[f"brush:{name}"] = rect
        y += ((len(names) + cols - 1) // cols) * (th + gap) + 6

        total = sum(counts.values())
        status = f"{total} piece{'' if total == 1 else 's'} each"
        if total and not counts.get(R.ROYAL):
            status += f" - no {R.ROYAL} yet"
        img = F.small.render(fit_text(F.small, status, L.panel_w - 2 * L.pad), True, MUTED)
        screen.blit(img, (x0, y))

        bh = int(clamp(L.win_h * 0.06, 36, 50))
        bw = L.panel_w - 2 * L.pad
        by = L.win_h - L.pad - bh
        self.button(screen, "done", pygame.Rect(x0, by, bw, bh), "Done", primary=True)
        self.button(screen, "revert", pygame.Rect(x0, by - bh - 10, bw, bh), "Back to saved opening")
        self.button(screen, "clear", pygame.Rect(x0, by - 2 * (bh + 10), bw, bh), "Clear the board")

    def paint(self, cell, erase: bool) -> None:
        if cell is None or not editable(*cell):
            return
        if erase or self.brush is None or self.cells.get(cell) == self.brush:
            self.cells.pop(cell, None)
        else:
            if self.brush == R.ROYAL:
                # Only one General: placing him again moves him.
                for other in [p for p, n in self.cells.items() if n == R.ROYAL]:
                    del self.cells[other]
            self.cells[cell] = self.brush
        self.values[R.SETUP_NAME] = setup_from_cells(self.cells)

    # --- input -----------------------------------------------------------

    def handle_click(self, pos, button: int = 1) -> Optional[str]:
        """Returns "back" to leave, "restart" after a save, else None."""
        if self.page == "opening" and button == 3:
            self.paint(self.layout.square_at(pos), erase=True)
            return None
        if button != 1:
            return None
        for key, rect in list(self.buttons.items()):
            if not rect.collidepoint(pos):
                continue
            kind, _, name = key.partition(":")
            if kind == "row":
                self.step(name, 1)
            elif kind == "inc":
                self.step(name, 1)
            elif kind == "dec":
                self.step(name, -1)
            elif kind == "brush":
                self.brush = None if name == "None" else name
            elif key == "opening":
                self.open_opening()
            elif key == "done":
                self.page = "settings"
                changed = self.values[R.SETUP_NAME] != self.saved[R.SETUP_NAME]
                self.say("Opening changed - Save & restart to play it." if changed else "")
            elif key == "revert":
                self.values[R.SETUP_NAME] = copy.deepcopy(self.saved[R.SETUP_NAME])
                self.cells = cells_from_setup(self.values[R.SETUP_NAME])
            elif key == "clear":
                self.cells = {}
                self.values[R.SETUP_NAME] = setup_from_cells(self.cells)
            elif key == "defaults":
                self.values = copy.deepcopy(self.saved)
                self.cells = cells_from_setup(self.values[R.SETUP_NAME])
                self.say("")
            elif key == "back":
                return "back"
            elif key == "save":
                problem = E.save(self.changes())
                if problem:
                    self.say(f"Not saved: {problem}", bad=True)
                    return None
                return "restart"
            return None
        if self.page == "opening":
            self.paint(self.layout.square_at(pos), erase=False)
        return None
