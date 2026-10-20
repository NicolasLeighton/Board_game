"""
Ui.py - everything HEX CHARGE puts on screen and everything it reads back.

    Theme       colours
    Layout      every measurement, derived from the window size
    Fonts       type sizes, derived from the layout
    text tools  fitting and wrapping, so nothing ever overlaps
    artwork     the vector pieces
    SoundManager  effects synthesised at runtime, no audio files
    Menu        opening screen
    GameView    draws a GameState and turns clicks into calls on it

Nothing here has a fixed size. The window can be dragged to any shape or
thrown into fullscreen, and the board, panel, pieces and type all resize
with it - see Layout, which is the single place any of that is decided.

The rules live in Rules.py and know nothing about any of this. A
GameView holds a GameState and asks it questions; it never edits the
position itself.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

try:
    import numpy as np
except ImportError:          # pragma: no cover - sound just degrades quietly
    np = None

from config import (BOARD_FLIP_DELAY_MS, FLIP_WHEN_BLACK, FREE_ARROWS,
                    KNIGHT_ARROW_PATH, MOVEMENT_TYPE, SANDBOX,
                    SHOW_MOVEMENT_HINTS)

if MOVEMENT_TYPE not in (1, 2, 3):
    raise ValueError(f"MOVEMENT_TYPE in config.py must be 1 (click or drag), "
                     f"2 (click only) or 3 (drag only), not {MOVEMENT_TYPE!r}.")
# Whether a click on a destination moves the selected piece there, and
# whether a piece can be picked up and dragged.
CLICK_MOVES = MOVEMENT_TYPE in (1, 2)
DRAG_MOVES = MOVEMENT_TYPE in (1, 3)
# Everything about how the board and pieces LOOK comes from board_design.
# This file decides what to draw and when; that one decides what it looks
# like. clear_piece_cache is imported here so that HexCharge.py can still reach
# it as Ui.clear_piece_cache when the window is resized.
from board_design import (
    BOARD_MARGIN, CAPTURE, CAPTURE_RADIUS, CAPTURE_RING_GROWTH, CAPTURE_RING_START,
    CHECK_RED, COORD_TEXT, DOT, HIGHLIGHT_RADIUS, HIGHLIGHT_WIDTH, HOVER,
    LABEL_OFFSET, LABEL_SIZE, LAST_MOVE, MARK_EDGE, MARK_FILL, MARK_RADIUS,
    MATE_SUPPORT, PREMOVE, SELECTED,
    clear_piece_cache, draw_arrow, draw_board_lines, draw_board_surface,
    draw_piece_outline, draw_ring, facing, label_colour, lattice_xy, piece_surface,
)
from Rules import (
    BOARD_RADIUS,
    BOARD_SIZE,
    FILE_LETTERS,
    FLAT,
    PIECE_CODES,
    ROYAL,
    HEX_DIRS,
    KNIGHT_LEAPS,
    GameState,
    Piece,
    legal_moves,
    mating_pieces,
    on_board,
    rank_of,
)

# ======================================================================
# Theme
# ======================================================================
# A light wooden board in a neutral dark case. The board is the brightest
# thing on screen, so the PIECES have to be darker than it - the reverse
# of the all-wood scheme, where they were paler than the surface.


BG = (24, 24, 29)
PANEL = (33, 33, 40)
PANEL_LINE = (58, 58, 68)
STAND_BG = (44, 40, 36)
STAND_EDGE = (84, 74, 60)

TEXT = (238, 238, 240)
MUTED = (156, 156, 166)
DIM = (112, 112, 122)
GOLD = (206, 176, 84)
GOOD = (140, 206, 140)
BAD = (212, 132, 132)





# Row striping in the move log, a touch above the panel.
ROW_STRIPE = (41, 41, 49)

MOVE_ANIMATION_MS = 220
MIN_WINDOW = (880, 600)


def clamp(value, low, high):
    return max(low, min(high, value))


# ======================================================================
# Layout
# ======================================================================

SQRT3 = math.sqrt(3.0)


class Layout:
    """
    Every measurement in the game, worked out from the window size.

    The board is a hexagon of flat-topped hexagons. One number sets its
    size: `hex_size`, a cell's centre-to-corner radius. Neighbouring
    cells sit 1.5 radii apart across and sqrt(3) radii apart up a file, so
    the whole board is (3R + 2) radii wide and (2R + 1) * sqrt(3) tall.
    Solving both against the window and taking the smaller answer keeps it
    fully visible whatever shape the window is dragged into.

    `cell_w` and `cell_h` are the box a piece is drawn in - centred on its
    cell and as tall as the cell is from flat side to flat side - so every
    piece, highlight and font that was sized from a square cell still is.
    """

    CELL_RATIO = 11 / 10       # piece tiles are taller than they are wide
    GUTTER_RATIO = 0.62        # coordinate margin, in cell radii

    def __init__(self, win_w: int, win_h: int) -> None:
        self.win_w = max(MIN_WINDOW[0], int(win_w))
        self.win_h = max(MIN_WINDOW[1], int(win_h))

        self.pad = clamp(round(self.win_h * 0.020), 10, 22)
        self.top_bar = clamp(round(self.win_h * 0.072), 44, 76)
        self.panel_w = int(clamp(self.win_w * 0.30, 286, 430))

        avail_w = self.win_w - self.panel_w - self.pad * 2
        avail_h = self.win_h - self.top_bar - self.pad * 2

        # The board's extent in point radii: the long way is (3R + 2), the
        # short way (2R + 1) * sqrt(3). Which is across and which is up
        # depends on which way it is turned.
        long_span = 3 * BOARD_RADIUS + 2
        short_span = BOARD_SIZE * SQRT3
        across, down = (short_span, long_span) if FLAT else (long_span, short_span)
        span_w = across + 2 * self.GUTTER_RATIO
        span_h = down + 2 * self.GUTTER_RATIO
        self.hex_size = max(12.0, min(avail_w / span_w, avail_h / span_h))
        s = self.hex_size

        self.cell_h = max(22, int(SQRT3 * s))
        self.cell_w = max(20, round(self.cell_h / self.CELL_RATIO))
        self.gutter = max(14, round(s * self.GUTTER_RATIO))

        self.board_w = int(round(across * s))
        self.board_h = int(round(down * s))

        # Centre the board inside the space left of the panel.
        left_space = self.win_w - self.panel_w
        self.board_x = max(self.gutter, (left_space - self.board_w) // 2)
        self.board_y = self.top_bar + max(
            self.gutter, (self.win_h - self.top_bar - self.board_h) // 2
        )
        self.centre_x = self.board_x + self.board_w / 2.0
        self.centre_y = self.board_y + self.board_h / 2.0

        self.panel_x = self.win_w - self.panel_w

        # Set by the view each frame; see GameView.board_flipped.
        self.flipped = False

    @property
    def size(self) -> Tuple[int, int]:
        return self.win_w, self.win_h

    def view_cell(self, row: int, col: int) -> Tuple[int, int]:
        """
        Board cell -> the cell it is DRAWN in, and back again.

        Turning the board is a half turn, so this is its own inverse: the
        same function converts a board cell to a screen cell and a screen
        cell back to a board cell. Every conversion in the UI goes through
        here, which is why the coordinate labels, the planning arrows and
        the animation all turn together without any of them knowing the
        board can turn at all.
        """
        if self.flipped:
            return BOARD_SIZE - 1 - row, BOARD_SIZE - 1 - col
        return row, col

    def board_rect(self) -> pygame.Rect:
        return pygame.Rect(self.board_x, self.board_y, self.board_w, self.board_h)

    def view_centre(self, vrow: int, vcol: int) -> Tuple[float, float]:
        """Screen centre of the cell DRAWN at (vrow, vcol), unrounded."""
        x, y = lattice_xy(vrow - BOARD_RADIUS, vcol - BOARD_RADIUS)
        return self.centre_x + x * self.hex_size, self.centre_y + y * self.hex_size

    def square_center(self, row: int, col: int) -> Tuple[int, int]:
        x, y = self.view_centre(*self.view_cell(row, col))
        return int(round(x)), int(round(y))

    def square_rect(self, row: int, col: int) -> pygame.Rect:
        """The box a piece on this cell is drawn in."""
        cx, cy = self.square_center(row, col)
        return pygame.Rect(cx - self.cell_w // 2, cy - self.cell_h // 2,
                           self.cell_w, self.cell_h)

    def cell_corners(self, row: int, col: int, grow: float = 0.0) -> List[Tuple[float, float]]:
        """The six corners of a cell's hexagon, `grow` pixels further out."""
        cx, cy = self.view_centre(*self.view_cell(row, col))
        radius = self.hex_size + grow
        turn = 30 if FLAT else 0
        return [(cx + radius * math.cos(math.radians(60 * k + turn)),
                 cy + radius * math.sin(math.radians(60 * k + turn))) for k in range(6)]

    def square_at(self, pos) -> Optional[Tuple[int, int]]:
        """The board cell under a screen point, or None off the board."""
        # Undo lattice_xy: solve for the fractional (row, col) step.
        x = (pos[0] - self.centre_x) / self.hex_size
        y = (pos[1] - self.centre_y) / self.hex_size
        (ax, ay), (bx, by) = lattice_xy(1, 0), lattice_xy(0, 1)
        det = ax * by - bx * ay
        r = (x * by - bx * y) / det
        q = (ax * y - x * ay) / det
        # Round in cube coordinates, fixing whichever axis rounded worst.
        x, z = q, r
        y = -x - z
        rx, ry, rz = round(x), round(y), round(z)
        dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
        if dx > dy and dx > dz:
            rx = -ry - rz
        elif dy <= dz:
            rz = -rx - ry
        vrow, vcol = int(rz) + BOARD_RADIUS, int(rx) + BOARD_RADIUS
        if not on_board(vrow, vcol):
            return None
        return self.view_cell(vrow, vcol)

    def font_sizes(self) -> Dict[str, int]:
        c = self.cell_w
        return {
            "title": int(clamp(round(c * 0.92), 24, 58)),
            "big": int(clamp(round(c * 0.40), 15, 30)),
            "normal": int(clamp(round(c * 0.30), 13, 22)),
            "small": int(clamp(round(c * 0.245), 11, 17)),
        }


class Fonts:
    """Type scaled to the layout, rebuilt whenever the window changes."""

    def __init__(self, layout: Layout) -> None:
        sizes = layout.font_sizes()
        self.title = pygame.font.SysFont("georgia", sizes["title"], bold=True)
        self.big = pygame.font.SysFont("georgia", sizes["big"], bold=True)
        self.normal = pygame.font.SysFont("segoeui", sizes["normal"])
        self.small = pygame.font.SysFont("segoeui", sizes["small"])
        self.line = self.small.get_linesize() + 3


# ======================================================================
# Text that never overlaps
# ======================================================================
# Every string drawn in this game goes through one of these. Text was the
# main thing that looked untidy before: long messages ran under the
# panel, help lines ran into what was below them. Fitting and
# wrapping against a real width, and refusing to draw what doesn't fit,
# is what stops that happening at any window size.


def fit_text(font, text: str, max_w: int) -> str:
    """Shortens with an ellipsis until it fits inside `max_w`."""
    if font.size(text)[0] <= max_w:
        return text
    ellipsis = "..."
    trimmed = text
    while trimmed and font.size(trimmed + ellipsis)[0] > max_w:
        trimmed = trimmed[:-1]
    return (trimmed.rstrip() + ellipsis) if trimmed else ""


def blit_text(surface, font, text: str, colour, x: int, y: int, max_w: int) -> int:
    """Draws one clipped line and returns the y below it."""
    img = font.render(fit_text(font, text, max_w), True, colour)
    surface.blit(img, (x, y))
    return y + font.get_linesize()


class SoundManager:
    """
    Generates every sound effect on the fly as short synthesized tones,
    so the game needs no external audio files. If the environment has
    no audio device or numpy isn't installed, every method here just
    becomes a silent no-op instead of crashing the game - sound is a
    nice-to-have, never a requirement to play.
    """

    SAMPLE_RATE = 44100

    def __init__(self) -> None:
        self.enabled = True
        self.available = False
        self.channels = 1
        self.sounds: Dict[str, "pygame.mixer.Sound"] = {}
        if np is None:
            return
        try:
            # pygame.init() (called earlier in Game.__init__) may already have
            # auto-initialized the mixer - typically in stereo - before we get
            # here. Reset it so our own frequency/channel request actually
            # takes effect, rather than silently keeping whatever came before.
            if pygame.mixer.get_init() is not None:
                pygame.mixer.quit()
            pygame.mixer.init(frequency=self.SAMPLE_RATE, size=-16, channels=1)
            init_info = pygame.mixer.get_init()
            self.channels = init_info[2] if init_info else 1
            self.available = True
        except Exception:
            self.available = False
            return
        self._build_sounds()

    def _finalize(self, wave: "np.ndarray") -> "pygame.mixer.Sound":
        """
        Converts a finished 1-D waveform (already windowed/scaled to
        [-1, 1]) into a Sound, duplicating it across channels if the
        mixer turned out to be stereo instead of mono.
        """
        samples = np.int16(wave * 32767)
        if self.channels == 2:
            samples = np.column_stack([samples, samples])
        return pygame.sndarray.make_sound(samples)

    # ------------------------------------------------------------------
    # Wood, not electronics
    #
    # A struck piece of wood is three things at once: an instant contact
    # click, a short burst of broadband noise as the two faces meet, and
    # a handful of resonant modes that die away fast. None of them is a
    # pure tone, and none of them fades IN - an attack that ramps up is
    # the single thing that makes a synthesised sound feel electronic.
    #
    # The mode ratios below (1, 2.76, 5.40, 8.93) are those of a free bar
    # rather than a string: inharmonic, so the ear hears a knock with a
    # pitch rather than a note. Higher modes are given faster decay,
    # which is what makes a small block sound small.
    # ------------------------------------------------------------------

    BAR_MODES = (1.0, 2.76, 5.40, 8.93)

    def _knock(self, pitch: float, duration_ms: int, volume: float = 0.35,
               noise: float = 0.55, damping: float = 34.0,
               brightness: float = 1.0, dull: int = 0) -> "np.ndarray":
        """One piece meeting another. Returns a raw waveform.

        `damping` is how fast it dies - low for a big resonant board,
        high for a small dry block. `noise` is how much of the sound is
        the contact itself rather than the ringing afterwards; a dull
        thud is nearly all noise, a bright tap nearly none. `dull`
        smooths the finished waveform, taking the top off the way a soft
        or muffled surface does.
        """
        n = max(1, int(self.SAMPLE_RATE * duration_ms / 1000))
        t = np.arange(n) / self.SAMPLE_RATE

        wave = np.zeros(n)
        for index, ratio in enumerate(self.BAR_MODES):
            # Higher modes are quieter and die sooner - that is most of
            # what separates a woodblock from a bell.
            decay = np.exp(-t * damping * (1.0 + 1.1 * index))
            weight = brightness ** index / (index + 1) ** 1.3
            # Cosine, not sine: a struck object is displaced instantly, so
            # every mode starts at full amplitude. Starting from zero
            # phase makes each mode ramp up over its first quarter cycle,
            # and that ramp is audible as a soft, synthetic attack.
            wave += weight * np.cos(2 * np.pi * pitch * ratio * t) * decay

        # The contact transient: a very short noise burst, smoothed so it
        # reads as a knock rather than a hiss.
        rng = np.random.default_rng(int(pitch) * 7919 + duration_ms)
        # ~4ms of it. Any shorter and the knock loses the sound of two
        # surfaces actually meeting; any longer and it turns into a hiss.
        burst = rng.standard_normal(n) * np.exp(-t * 260.0)
        kernel = np.exp(-np.arange(24) / 6.0)
        burst = np.convolve(burst, kernel / kernel.sum(), mode="same")
        wave += noise * burst

        if dull:
            # A rolling average is a crude low-pass, but a crude low-pass
            # is exactly what a soft surface is: the high modes go first.
            smooth = np.ones(dull) / dull
            wave = np.convolve(wave, smooth, mode="same")

        peak = float(np.max(np.abs(wave))) or 1.0
        wave = wave / peak

        # No fade IN - the attack has to be instant. Only the tail is
        # eased, and only enough to stop the buffer end clicking.
        tail = min(n, max(1, int(self.SAMPLE_RATE * 0.006)))
        wave[-tail:] *= np.linspace(1.0, 0.0, tail)
        return wave * volume

    def _sequence(self, knocks: Sequence[Tuple], *,
                  pitch: float, duration_ms: int, volume: float,
                  **kwargs) -> "np.ndarray":
        """Several knocks laid over one timeline.

        Each entry is (delay in ms, relative loudness) and may carry a
        third value to give that knock its own pitch. Used for the double
        tap of a capture - one piece lifted, another set down - and for
        the three falling raps of a mate.
        """
        span = int(max(entry[0] for entry in knocks) + duration_ms) + 20
        n = int(self.SAMPLE_RATE * span / 1000)
        out = np.zeros(n)
        for delay, loudness, *rest in knocks:
            note_pitch = rest[0] if rest else pitch
            piece = self._knock(note_pitch, duration_ms, volume * loudness, **kwargs)
            at = int(self.SAMPLE_RATE * delay / 1000)
            out[at:at + len(piece)] += piece[:max(0, n - at)]
        peak = float(np.max(np.abs(out))) or 1.0
        return out / peak * volume

    def _build_sounds(self) -> None:
        # Picking a piece up: the small dry tick of a fingernail on wood.
        self.sounds["select"] = self._finalize(
            self._knock(1180, 45, 0.16, noise=0.75, damping=70, brightness=0.7))

        # Setting your own piece down - the sound the game is built on.
        self.sounds["own_move"] = self._finalize(
            self._knock(520, 110, 0.34, noise=0.55, damping=32))

        # Theirs, from the far side of the board: same knock, darker and
        # a shade softer, as though it were further away.
        self.sounds["enemy_move"] = self._finalize(
            self._knock(380, 120, 0.30, noise=0.5, damping=28, brightness=0.8))

        # A capture is two pieces: the one lifted away, then yours coming
        # down hard on the square it left.
        self.sounds["capture"] = self._finalize(self._sequence(
            [(0, 0.55, 620), (32, 1.0, 430)],
            pitch=520, duration_ms=130, volume=0.40, damping=30,
            noise=0.4, brightness=0.6, dull=6))

        # Check is a rap on the board - two quick knuckles, high and hard.
        self.sounds["check"] = self._finalize(self._sequence(
            [(0, 1.0), (70, 0.9)],
            pitch=700, duration_ms=90, volume=0.34, damping=45,
            noise=0.4, brightness=0.6, dull=6))

        # Mate: three falling raps, the last one on the whole board rather
        # than a piece - low, slow to die, and final.
        self.sounds["mate"] = self._finalize(self._sequence(
            [(0, 0.8, 520), (150, 0.85, 400), (320, 1.0, 190)],
            pitch=520, duration_ms=520, volume=0.42, damping=9,
            noise=0.3, brightness=0.6, dull=6))

        # An illegal move gets no pitch at all: a dead thud, the sound of
        # a piece stopped against the rim.
        self.sounds["illegal"] = self._finalize(
            self._knock(150, 70, 0.26, noise=1.4, damping=90,
                        brightness=0.3, dull=26))

    def play(self, name: str) -> None:
        if not self.enabled or not self.available:
            return
        sound = self.sounds.get(name)
        if sound is not None:
            try:
                sound.play()
            except Exception:
                pass





# ======================================================================
# Menu
# ======================================================================

class Menu:
    """Opening screen. Returns a config dict describing the game wanted:
    who controls Black, and how hard the computer should think."""

    def __init__(self, layout: Layout, fonts: Fonts) -> None:
        self.layout = layout
        self.fonts = fonts
        self.mode = "ai"
        self.difficulty = 0
        self.side = "W"          # "W", "B" or "random"
        self.buttons: Dict[str, pygame.Rect] = {}

    def resize(self, layout: Layout, fonts: Fonts) -> None:
        self.layout, self.fonts = layout, fonts

    SIDES = (("W", "Play White - you move first"),
             ("B", "Play Black - the computer opens"),
             ("random", "Randomise"))

    def stack(self, screen, difficulties, cx, top, width, button_h, gap) -> int:
        """Lays the option stack out from `top` and returns the y below the
        Start button.

        Pass screen=None to measure without drawing. That is the point of
        this being one routine: the height the menu reserves comes from
        the same code that positions the buttons, so the two cannot drift.
        A separate height formula is what let the Start button be clamped
        back on top of the last difficulty - and a click then landed on
        both, so every game began at the last level in the table whatever
        you had chosen.
        """
        y = self._heading(screen, "Who is playing?", cx, top)
        y = self._option(screen, "human", "Two players - you control both sides",
                         cx, y, width, button_h, self.mode == "human") + gap
        y = self._option(screen, "ai", "Play against the computer",
                         cx, y, width, button_h, self.mode == "ai") + gap
        y = self._option(screen, "watch", "Watch the computer play itself",
                         cx, y, width, button_h, self.mode == "watch") + gap * 2

        if self.mode == "ai":
            # Nobody has a side when the computer plays itself.
            y = self._heading(screen, "Your side", cx, y)
            for code, text in self.SIDES:
                y = self._option(screen, f"side{code}", text, cx, y, width,
                                 button_h, self.side == code) + gap
            y += gap

        if self.mode in ("ai", "watch"):
            y = self._heading(screen, "How strong?", cx, y)
            for index, (name, blurb) in enumerate(difficulties):
                y = self._option(screen, f"diff{index}", name, cx, y, width,
                                 button_h, self.difficulty == index, blurb) + gap
            y += gap

        start = pygame.Rect(cx - width // 4, y + gap, width // 2, button_h)
        if screen is not None:
            pygame.draw.rect(screen, GOLD, start, border_radius=10)
            label = self.fonts.big.render("Start", True, (24, 22, 18))
            screen.blit(label, label.get_rect(center=start.center))
        self.buttons["start"] = start

        # Config: the settings in config.py, and the opening, edited here.
        settings = pygame.Rect(cx - width // 6, start.bottom + gap * 2, width // 3,
                               int(button_h * 0.8))
        if screen is not None:
            pygame.draw.rect(screen, STAND_BG, settings, border_radius=9)
            pygame.draw.rect(screen, STAND_EDGE, settings, 1, border_radius=9)
            label = self.fonts.normal.render("Config", True, TEXT)
            screen.blit(label, label.get_rect(center=settings.center))
        self.buttons["config"] = settings
        return settings.bottom

    def draw(self, screen, difficulties: Sequence[Tuple[str, str]]) -> None:
        L, F = self.layout, self.fonts
        screen.fill(BG)
        cx = L.win_w // 2
        width = int(clamp(L.win_w * 0.46, 320, 520))

        button_h = int(clamp(L.win_h * 0.052, 34, 50))
        gap = int(clamp(L.win_h * 0.010, 6, 12))
        top = max(int(L.win_h * 0.16), 0)
        floor = L.win_h - L.pad

        # Measured with the real layout code, shrinking until it fits.
        self.buttons = {}
        while self.stack(None, difficulties, cx, top, width, button_h, gap) > floor:
            if button_h > 20:
                button_h -= 1
            elif gap > 3:
                gap -= 1
            else:
                break
        # If even the smallest rows will not fit - a window below the
        # supported minimum - give up the space above the title rather
        # than let the Start button fall off the bottom.
        bottom = self.stack(None, difficulties, cx, top, width, button_h, gap)
        if bottom > floor:
            top = max(L.pad, top - (bottom - floor))

        title = F.title.render("HEX CHARGE", True, GOLD)
        screen.blit(title, title.get_rect(center=(cx, top - int(L.win_h * 0.10))))
        tag = F.small.render(
            "Screens to jump, ground to hold, and everything you take fights for you.",
            True, MUTED)
        if tag.get_width() < L.win_w - 2 * L.pad:
            screen.blit(tag, tag.get_rect(center=(cx, top - int(L.win_h * 0.055))))

        self.buttons = {}
        self.stack(screen, difficulties, cx, top, width, button_h, gap)

        hint = F.small.render("F11 fullscreen    Esc quits", True, DIM)
        screen.blit(hint, hint.get_rect(center=(cx, L.win_h - L.pad // 2 - hint.get_height() // 2)))

    def _heading(self, screen, text: str, cx: int, y: int) -> int:
        """Draws a heading and returns the y below it. `screen` may be
        None, which lays the row out without drawing - see stack()."""
        img = self.fonts.normal.render(text, True, TEXT)
        if screen is not None:
            screen.blit(img, img.get_rect(midtop=(cx, y)))
        return y + img.get_height() + 8

    def _option(self, screen, key: str, text: str, cx: int, y: int,
                width: int, height: int, selected: bool, blurb: str = "") -> int:
        """Draws one option and returns the y below it. `screen` may be
        None to lay the row out without drawing it."""
        rect = pygame.Rect(cx - width // 2, y, width, height)
        F = self.fonts
        if screen is not None:
            pygame.draw.rect(screen, STAND_BG if not selected else (56, 62, 78),
                             rect, border_radius=9)
            pygame.draw.rect(screen, SELECTED if selected else STAND_EDGE,
                             rect, 3 if selected else 1, border_radius=9)
            inner = width - 24
            if blurb:
                name = F.normal.render(fit_text(F.normal, text, inner), True,
                                       TEXT if selected else MUTED)
                note = F.small.render(fit_text(F.small, blurb, inner), True,
                                      MUTED if selected else DIM)
                total = name.get_height() + note.get_height()
                ny = rect.y + (height - total) // 2
                screen.blit(name, (rect.x + 12, ny))
                screen.blit(note, note.get_rect(right=rect.right - 12,
                                                top=ny + name.get_height() - note.get_height()))
            else:
                img = F.normal.render(fit_text(F.normal, text, inner), True,
                                      TEXT if selected else MUTED)
                screen.blit(img, img.get_rect(center=rect.center))
        self.buttons[key] = rect
        return rect.bottom

    def handle_click(self, pos) -> Optional[Dict]:
        # Start is tested first and on its own. If two buttons ever overlap
        # again, the worst that happens is a wasted click - not a game that
        # silently begins on a setting you never chose.
        start = self.buttons.get("start")
        if start is not None and start.collidepoint(pos):
            return {"mode": self.mode, "difficulty": self.difficulty,
                    "side": self.side}
        settings = self.buttons.get("config")
        if settings is not None and settings.collidepoint(pos):
            return {"mode": "config"}

        for key, rect in self.buttons.items():
            if key in ("start", "config") or not rect.collidepoint(pos):
                continue
            if key in ("human", "ai", "watch"):
                self.mode = key
            elif key.startswith("side"):
                self.side = key[4:]
            elif key.startswith("diff"):
                self.difficulty = int(key[4:])
            elif key == "start":
                return {"mode": self.mode, "difficulty": self.difficulty,
                        "side": self.side}
        return None



# ======================================================================
# Board view
# ======================================================================

class GameView:
    """
    Draws a GameState and turns mouse input into actions on it.

    Everything the player is part-way through - the current selection,
    planning arrows, the in-flight animation - lives here, not in the
    rules. `human_sides` is which colours accept input: both in a
    two-player game, White only against the computer.
    """

    def __init__(self, layout: Layout, fonts: Fonts, state: GameState,
                 human_sides=("W",)) -> None:
        self.layout = layout
        self.fonts = fonts
        self.state = state
        self.human_sides = tuple(human_sides)
        self.sound = SoundManager()

        # A move queued while the other side is thinking. Kept as the same
        # action dictionary the engine returns, so playing it later goes
        # through exactly the code that plays any other action.
        self.premove: Optional[Dict] = None
        # A piece picked up with the mouse: the point it came from, where
        # the press began, where the pointer is now, and whether it has
        # moved far enough to count as a drag.
        self.drag: Optional[Dict] = None
        self.premove_from: Optional[Tuple[int, int]] = None
        self.selected_square: Optional[Tuple[int, int]] = None
        self.legal_targets: List[Tuple[int, int]] = []
        # The sandbox's pool: one tile per piece for each side, to put new
        # pieces on the board. The tile picked, as (owner, name), and
        # where each tile is drawn this frame.
        self.pool_pick: Optional[Tuple[str, str]] = None
        self.pool_tiles: Dict[Tuple[str, str], pygame.Rect] = {}

        self.animation: Optional[Dict] = None
        # How far the move log is scrolled back, counted in turns. Zero
        # means pinned to the newest move, which is where it stays unless
        # you deliberately scroll up - so a live game keeps following
        # itself, and a game you're reading back doesn't jump.
        self.log_scroll = 0
        self.log_rect: Optional[pygame.Rect] = None
        # Worked out once when the game ends; see mate_highlight.
        self._mate_marks: Optional[Dict[str, set]] = None
        # Which side the board is currently drawn for. It follows whoever
        # is to move, but LATE - see update_orientation.
        self.shown_side = self.viewer
        self.flip_at: Optional[int] = None
        # Set by the main loop while the computer is searching, so the
        # wait reads as "thinking" rather than "frozen".
        self.thinking = False
        self.marks: set = set()
        self.arrows: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []
        self.arrow_start: Optional[Tuple[int, int]] = None

    def resize(self, layout: Layout, fonts: Fonts) -> None:
        self.layout, self.fonts = layout, fonts
        clear_piece_cache()

    # --- whose input counts --------------------------------------------

    def controls(self, owner: str) -> bool:
        return owner in self.human_sides

    @property
    def viewer(self) -> str:
        """Whose side of the board is nearest you. With two players that's
        whoever is to move."""
        if not self.human_sides:
            # The computer against itself: there is nobody to turn the
            # board for, so it simply stays the right way up.
            return "W"
        if len(self.human_sides) > 1:
            return self.state.turn
        return self.human_sides[0]

    # --- geometry passthrough -------------------------------------------

    def square_from_mouse(self, pos):
        return self.layout.square_at(pos)

    def square_rect(self, row, col):
        return self.layout.square_rect(row, col)

    def square_center(self, row, col):
        return self.layout.square_center(row, col)

    # --- reacting to an action ------------------------------------------

    def on_event(self, event: Optional[Dict]) -> None:
        """Turns a rules event into animation and sound."""
        if not event:
            return
        src, dst = event.get("src"), event.get("dst")
        if src and dst and src != dst:
            piece = self.state.board.at(*dst)
            if piece is not None:
                self.animation = {
                    "piece": piece, "src": src, "dst": dst,
                    "start": pygame.time.get_ticks(),
                    "duration": MOVE_ANIMATION_MS,
                    "captured": event.get("captured", False),
                }
        move_cue = "own_move" if self.controls(event.get("mover", "")) else "enemy_move"
        cues = [move_cue]
        if event.get("captured"):
            cues.append("capture")
        if event.get("gameover"):
            cues.append("mate")
        elif event.get("check"):
            cues.append("check")
        for cue in cues:
            self.sound.play(cue)

    def update_animation(self) -> None:
        now = pygame.time.get_ticks()
        if self.animation is None:
            return
        if now - self.animation["start"] >= self.animation["duration"]:
            self.animation = None

    # --- selection -------------------------------------------------------

    def clear_selection(self) -> None:
        self.selected_square = None
        self.legal_targets = []
        self.pool_pick = None

    def clear_annotations(self) -> None:
        self.marks.clear()
        self.arrows.clear()
        self.arrow_start = None

    def select_own_piece(self, row: int, col: int, piece: Piece) -> None:
        """Selects a piece and lights up everywhere it may legally go."""
        self.selected_square = (row, col)
        self.legal_targets = legal_moves(self.state.board, row, col, piece)
        self.state.message = f"{piece.name} selected."
        self.sound.play("select")

    # --- clicks ----------------------------------------------------------

    def may_premove(self) -> bool:
        """Whether a move can be queued right now.

        Only when you control exactly one side and it is the other's turn
        - which means playing the computer. In a hotseat game it is always
        somebody's turn, and when the computer plays itself nobody is
        clicking at all.
        """
        return (len(self.human_sides) == 1
                and self.state.phase == "battle"
                and self.state.turn not in self.human_sides)

    def clear_premove(self) -> None:
        self.premove = None
        self.premove_from = None

    def take_up_pending_selection(self) -> None:
        """Your turn has come with a premove only half made - a piece picked
        but no destination given. It becomes an ordinary selection, showing
        that piece's moves in the position as it now is, so the move can be
        finished at once. If the opponent's move took the piece, the
        selection is simply dropped."""
        square = self.premove_from
        if square is None:
            return
        self.clear_premove()
        self.legal_targets = []
        piece = self.state.board.at(*square)
        if piece is not None and piece.owner == self.state.turn:
            self.selected_square = square
            self.legal_targets = legal_moves(self.state.board, *square, piece)

    def premove_squares(self) -> List[Tuple[int, int]]:
        """The points to light up: where it starts and where it ends."""
        if self.premove is None:
            return [self.premove_from] if self.premove_from else []
        return [self.premove["src"], self.premove["dst"]]

    def handle_click(self, pos) -> None:
        self.clear_annotations()
        moving = self.animation is not None and not self.animation.get("landed")
        if moving or self.state.phase == "gameover":
            return
        if SANDBOX:
            self.sandbox_click(pos)
            return
        if not self.controls(self.state.turn):
            if self.may_premove():
                self.premove_click(pos)
            return
        self.battle_click(pos)

    def sandbox_click(self, pos) -> None:
        """Clicks in a sandbox. Any piece of either colour can be selected,
        and shows where it could legally go; clicking one of those points
        moves it there. Dragging is what ignores the rules.

        With a pool tile picked, clicking an empty point puts a new piece
        there - and the tile stays picked, so you can lay out several."""
        square = self.square_from_mouse(pos)
        if square is None:
            self.clear_selection()
            return
        piece = self.state.board.at(*square)
        if self.pool_pick is not None and piece is None:
            if CLICK_MOVES:
                self.place_from_pool(self.pool_pick, square)
            return
        self.pool_pick = None
        if self.selected_square == square:
            return                                  # picked up to drag
        if self.selected_square is not None and square in self.legal_targets and CLICK_MOVES:
            event = self.state.sandbox_move(self.selected_square, square)
            self.clear_selection()
            self.on_event(event)
            return
        self.clear_selection()
        if piece is not None:
            self.select_own_piece(*square, piece)

    def premove_click(self, pos, by_drag: bool = False) -> None:
        """Queues a move for the moment it becomes your turn.

        Nothing is checked against the rules here - it cannot be, because
        the position will have changed by the time it is played. The
        board simply remembers what you asked for and tries it later; if
        the opponent's move made it impossible, it is quietly dropped.
        """
        mine = self.human_sides[0]
        square = self.square_from_mouse(pos)
        if square is None:
            self.clear_premove()
            return
        row, col = square

        if self.premove_from is None:
            piece = self.state.board.at(row, col)
            if piece is not None and piece.owner == mine:
                self.premove_from = square
                # Shown as a guide only. They are this position's moves,
                # and the position is about to change.
                self.legal_targets = legal_moves(self.state.board, row, col, piece)
                self.sound.play("select")
            else:
                self.clear_premove()
            return

        if square == self.premove_from:
            self.clear_premove()             # clicking it again cancels
            self.legal_targets = []
            return
        if not (CLICK_MOVES or by_drag):
            self.clear_premove()
            self.legal_targets = []
            return
        self.premove = {"type": "move", "src": self.premove_from, "dst": square}
        self.premove_from = None
        self.legal_targets = []
        self.state.message = "Move queued."
        self.sound.play("select")

    # --- dragging -----------------------------------------------------------
    # A press does exactly what a click always did - select a piece, or
    # play the move if one was already selected - and also picks the
    # selected piece up. Move the mouse a few pixels and it follows the
    # pointer; let go and it lands where you let go, if that is legal, or
    # goes back where it was if not. Click-to-move works as before.

    DRAG_THRESHOLD = 6           # pixels the pointer must travel to count

    def pool_tile_at(self, pos) -> Optional[Tuple[str, str]]:
        """The pool tile under the pointer, in a sandbox."""
        for slot, rect in self.pool_tiles.items():
            if rect.collidepoint(pos):
                return slot
        return None

    def place_from_pool(self, slot: Tuple[str, str], square) -> None:
        event = self.state.sandbox_place(slot[0], slot[1], *square)
        if event is None:
            # An occupied point, or a second General for one side.
            self.sound.play("illegal")
            return
        self.on_event(event)

    def left_press(self, pos) -> None:
        slot = self.pool_tile_at(pos) if SANDBOX else None
        if slot is not None:
            # A pool tile: picked, and picked up to drag. Pressing the one
            # already picked and letting go puts it down again.
            was_picked = self.pool_pick == slot
            self.clear_selection()
            self.pool_pick = slot
            self.sound.play("select")
            self.drag = {"pool": slot, "from": None, "start": pos, "pos": pos,
                         "active": False, "deselect": was_picked}
            return
        was_selected = self.selected_square or self.premove_from
        self.handle_click(pos)
        self.drag = None
        square = self.square_from_mouse(pos)
        held = self.selected_square or self.premove_from
        if square is not None and square == held:
            self.drag = {"from": square, "start": pos, "pos": pos,
                         "active": False, "deselect": was_selected == square}

    def drag_motion(self, pos) -> None:
        if self.drag is None:
            return
        self.drag["pos"] = pos
        sx, sy = self.drag["start"]
        if DRAG_MOVES and math.hypot(pos[0] - sx, pos[1] - sy) >= self.DRAG_THRESHOLD:
            self.drag["active"] = True

    def left_release(self, pos) -> None:
        drag, self.drag = self.drag, None
        if drag is None:
            return
        if not drag["active"]:
            # A plain click. Clicking a piece that was already selected
            # puts it down again; anything else stays as the click left it.
            if drag["deselect"]:
                self.clear_selection()
                self.clear_premove()
                self.pool_pick = None
            return
        if SANDBOX:
            self.sandbox_drop(drag, pos)
        elif self.controls(self.state.turn) and self.state.phase != "gameover":
            self.drop_dragged(drag, pos)
        elif self.may_premove():
            self.drop_premove(drag, pos)

    def drop_dragged(self, drag, pos) -> None:
        """Plays the dragged piece where it was let go, if it may go there."""
        square = self.square_from_mouse(pos)
        src = drag["from"]
        if self.selected_square != src or square is None or square == src:
            return                               # put back where it was
        if square in self.legal_targets:
            event = self.state.execute_move(src, square)
            self.clear_selection()
            self.on_event(event)
            self.land_in_place()
            return
        self.state.message = "Illegal move."
        self.sound.play("illegal")

    def sandbox_drop(self, drag, pos) -> None:
        """Puts the dragged piece wherever it was let go, legal or not. A
        piece from the pool lands as a new piece; a piece from the board
        dropped off the board is taken off it altogether."""
        square = self.square_from_mouse(pos)
        if drag.get("pool"):
            if square is not None:
                self.place_from_pool(drag["pool"], square)
                self.land_in_place()
            return
        if square is None:
            event = self.state.sandbox_remove(drag["from"])
            self.clear_selection()
            self.on_event(event)
            return
        if square == drag["from"]:
            return
        event = self.state.sandbox_move(drag["from"], square)
        if event is None:
            # Onto one of its own side, or onto a General.
            self.sound.play("illegal")
            return
        self.clear_selection()
        self.on_event(event)
        self.land_in_place()

    def drop_premove(self, drag, pos) -> None:
        """Queues the dragged piece's move, as a click would."""
        square = self.square_from_mouse(pos)
        if square is None or square == drag["from"]:
            return
        self.premove_click(pos, by_drag=True)

    def land_in_place(self) -> None:
        """A dragged piece is already where it was put down, so it does not
        slide there again. Only the capture ring, if any, still plays."""
        if self.animation is not None:
            self.animation["src"] = self.animation["dst"]
            # Nothing is travelling, so nothing to wait for: the board takes
            # the next press straight away instead of locking until the
            # capture ring has faded.
            self.animation["landed"] = True

    def draw_drag(self, screen) -> None:
        """The piece under the pointer, drawn last so it is above
        everything, with the point it would land on outlined."""
        drag = self.drag
        if drag is None or not drag["active"]:
            return
        L = self.layout
        if drag.get("pool"):
            piece = Piece(*drag["pool"])
        else:
            piece = self.state.board.at(*drag["from"])
        if piece is None:
            return
        over = self.square_from_mouse(drag["pos"])
        if over is not None and (over in self.legal_targets
                                 or (SANDBOX and self.state.board.at(*over) is None)):
            self.highlight(screen, over, SELECTED, HIGHLIGHT_WIDTH)
        elif over is None and SANDBOX and not drag.get("pool"):
            # Off the board: let go here and it is gone.
            x, y = drag["pos"]
            draw_ring(screen, CAPTURE, (x, y), L.cell_w * 0.62, HIGHLIGHT_WIDTH)
        x, y = drag["pos"]
        self.draw_piece(screen, piece, x - L.cell_w // 2, y - L.cell_h // 2)

    def battle_click(self, pos) -> None:
        owner = self.state.turn
        square = self.square_from_mouse(pos)
        if square is None:
            self.clear_selection()
            return
        row, col = square
        piece = self.state.board.at(row, col)

        if self.selected_square is None:
            if piece is None or piece.owner != owner:
                self.state.message = "Select one of your pieces."
                return
            self.select_own_piece(row, col, piece)
            return

        src = self.selected_square
        if self.state.board.at(*src) is None:
            self.clear_selection()
            return
        if (row, col) == src:
            # Pressing the selected piece again picks it up to drag; a
            # press and release without moving puts it down unselected -
            # see left_release.
            return
        if piece is not None and piece.owner == owner and (row, col) != src:
            self.select_own_piece(row, col, piece)
            return
        if not CLICK_MOVES:
            self.clear_selection()                   # drag-only: drag it there
            return
        if (row, col) not in self.legal_targets:
            self.state.message = "Illegal move."
            self.sound.play("illegal")
            return
        event = self.state.execute_move(src, (row, col))
        self.clear_selection()
        self.on_event(event)

    # --- planning overlay -------------------------------------------------

    def menu_button_rect(self) -> pygame.Rect:
        """Where the Menu button is.

        Worked out from the layout rather than remembered from the last
        frame, so a click on the very first frame - before anything has
        been drawn - still lands on it.
        """
        L, F = self.layout, self.fonts
        width = F.small.size("Menu")[0] + L.pad * 2
        rect = pygame.Rect(0, 8, width, L.top_bar - 16)
        rect.right = L.win_w - L.pad
        return rect

    def hit_menu_button(self, pos) -> bool:
        return self.menu_button_rect().collidepoint(pos)

    def scroll_log(self, amount: int, pos=None) -> None:
        """Scrolls the move log by `amount` turns, positive for older.

        Ignored unless the pointer is over the log, so the wheel doesn't
        move it while you're looking at the board.
        """
        if pos is not None and (self.log_rect is None or not self.log_rect.collidepoint(pos)):
            return
        self.log_scroll = max(0, min(self.log_scroll + amount, self._log_max_scroll()))

    def _log_max_scroll(self) -> int:
        if not self.log_rect:
            return 0
        line_h = self.fonts.small.get_linesize() + 4
        room = max(1, self.log_rect.height // line_h)
        return max(0, len(self.move_pairs()) - room)

    def toggle_mark(self, square) -> None:
        self.marks.symmetric_difference_update({square})

    def toggle_arrow(self, start, end) -> None:
        arrow = (start, end)
        if arrow in self.arrows:
            self.arrows.remove(arrow)
        else:
            self.arrows.append(arrow)

    # The eight directions an arrow can be straightened onto, and the
    # leap shapes that are left alone instead.
    _SNAP_DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (-1, 1), (1, -1), (1, 1))

    def snap_arrow(self, start, pos):
        """Where an arrow dragged to `pos` should actually point.

        With FREE_ARROWS off, the drag is straightened onto the nearest of
        the six lines, measured by the cells' true positions so a line
        that crosses files comes out at its real 60 degrees. A Knight's
        leap is left exactly as dragged - it is a real move, and on no
        line, so straightening it would make it undrawable.
        """
        end = self.square_from_mouse(pos)
        if FREE_ARROWS or end is None or start is None or end == start:
            return end

        dr, dc = end[0] - start[0], end[1] - start[1]
        if (dr, dc) in KNIGHT_LEAPS:
            return end

        # The offset as it lies on an unturned board, in cell radii.
        x, y = lattice_xy(dr, dc)
        best, unit = None, None
        for ur, uc in HEX_DIRS:
            ux, uy = lattice_xy(ur, uc)
            along = (x * ux + y * uy) / 3.0             # each step is sqrt(3) long
            if best is None or along > best:
                best, unit = along, (ur, uc)
        steps = max(1, int(round(best)))
        # Shorten the ray until it lands on the board.
        for length in range(steps, 0, -1):
            cell = (start[0] + unit[0] * length, start[1] + unit[1] * length)
            if on_board(*cell):
                return cell
        return None

    def arrow_path(self, start, end):
        """The cells an arrow runs through.

        Usually just the two ends. An arrow on a Knight's leap bends the
        way the leap is counted - two cells straight out along a line,
        then one turned 60 degrees - so it can't be mistaken for an arrow
        along a line. Only the drawing bends: the Knight still jumps, and
        nothing on the way can stop him. KNIGHT_ARROW_PATH turns it off.
        """
        dr, dc = end[0] - start[0], end[1] - start[1]
        if not KNIGHT_ARROW_PATH or (dr, dc) not in KNIGHT_LEAPS:
            return [start, end]
        for ar, ac in HEX_DIRS:
            br, bc = dr - 2 * ar, dc - 2 * ac
            if (br, bc) in HEX_DIRS:             # every leap splits exactly one way
                return [start, (start[0] + 2 * ar, start[1] + 2 * ac), end]
        return [start, end]

    def right_press(self, pos) -> None:
        self.arrow_start = self.square_from_mouse(pos)

    def right_release(self, pos) -> None:
        end = self.snap_arrow(self.arrow_start, pos)
        if self.arrow_start is not None and end is not None:
            if end == self.arrow_start:
                self.toggle_mark(end)
            else:
                self.toggle_arrow(self.arrow_start, end)
        self.arrow_start = None

    # --- drawing -----------------------------------------------------------

    def mate_highlight(self) -> Dict[str, set]:
        """The pieces that finished the game, ready to be drawn.

        Computed once when the game ends and then cached - it walks every
        enemy piece against every escape square, which is far too much to
        repeat sixty times a second for a board that is no longer moving.
        """
        if self.state.phase != "gameover":
            return {"checkers": set(), "support": set()}
        if self._mate_marks is None:
            winner = self.state.winner
            loser = "B" if winner == "White" else "W" if winner == "Black" else None
            marks = {"checkers": set(), "support": set()}
            if loser is not None:
                if self.state.board.royal_pos(loser) is not None:
                    marks = mating_pieces(self.state.board, loser)
                elif self.state.last_move is not None:
                    # The General was taken outright; the piece standing on
                    # his square is the whole story.
                    marks["checkers"] = {self.state.last_move[1]}
            self._mate_marks = marks
        return self._mate_marks

    def board_flipped(self) -> bool:
        """True when the board is currently drawn for Black.

        This follows `shown_side`, not `viewer`, so the board keeps its
        old orientation for a moment after the turn changes. See
        update_orientation for why.
        """
        return FLIP_WHEN_BLACK and self.shown_side == "B"

    def update_orientation(self) -> None:
        """Turns the board once the move has been seen, not the instant
        the turn changed.

        The order matters: the piece finishes moving, the board holds
        still long enough to read what happened, and only then turns.
        Flipping straight away pulled the board out from under the piece
        mid-thought. The wait is BOARD_FLIP_DELAY_MS and never starts
        while an animation is still running.
        """
        if not FLIP_WHEN_BLACK or self.shown_side == self.viewer:
            self.flip_at = None
            return
        if self.animation is not None:
            self.flip_at = None          # the piece is still travelling
            return
        now = pygame.time.get_ticks()
        if self.flip_at is None:
            self.flip_at = now + max(0, BOARD_FLIP_DELAY_MS)
        if now >= self.flip_at:
            self.shown_side = self.viewer
            self.flip_at = None

    def draw(self, screen) -> None:
        # Decided here, once, so every piece of drawing this frame agrees
        # about which way round the board is.
        self.update_orientation()
        self.layout.flipped = self.board_flipped()
        screen.fill(BG)
        self.draw_top_bar(screen)
        self.draw_board(screen)
        self.draw_panel(screen)
        # A piece in your hand goes over everything.
        self.draw_drag(screen)

    def draw_top_bar(self, screen) -> None:
        L, F = self.layout, self.fonts
        pygame.draw.rect(screen, PANEL, (0, 0, L.win_w, L.top_bar))
        pygame.draw.line(screen, PANEL_LINE, (0, L.top_bar - 1), (L.win_w, L.top_bar - 1))

        title = F.big.render("HEX CHARGE", True, GOLD)
        screen.blit(title, title.get_rect(midleft=(L.pad, L.top_bar // 2)))

        # "Menu" sits at the right end of the bar. Drawn before the status
        # message so the message can be clipped to whatever is left, rather
        # than sliding underneath it.
        label = F.small.render("Menu", True, TEXT)
        button = self.menu_button_rect()
        hovered = button.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(screen, STAND_BG if hovered else PANEL, button, border_radius=6)
        pygame.draw.rect(screen, GOLD if hovered else PANEL_LINE, button, 1, border_radius=6)
        screen.blit(label, label.get_rect(center=button.center))

        # The message gets whatever room is left after the title, and is
        # clipped to it. Previously it just kept drawing and slid under
        # the panel.
        msg_x = L.pad + title.get_width() + L.pad * 2
        msg_w = button.left - L.pad - msg_x
        if msg_w > 60:
            if self.thinking:
                # A slow ellipsis, so it's obvious the game is alive and
                # working rather than hung.
                dots = "." * (1 + int(pygame.time.get_ticks() / 400) % 3)
                text = f"{self.state.player_name()} is thinking{dots}"
                colour = MUTED
            else:
                text = self.state.message
                colour = GOLD if self.state.phase == "gameover" else TEXT
            img = F.normal.render(fit_text(F.normal, text, msg_w), True, colour)
            screen.blit(img, img.get_rect(midleft=(msg_x, L.top_bar // 2)))

    def draw_tile_label(self, screen, name: str, owner: str, rect,
                        flip: bool = False) -> None:
        """Writes a piece's code onto a tile."""
        font = self.fonts.big if rect.width >= self.layout.cell_w * 0.8 else self.fonts.normal
        colour = label_colour(owner)
        code = Piece("W", name).label()
        img = font.render(code, True, colour)
        if LABEL_SIZE != 1.0:
            # Sized as a fraction of the normal lettering - board_design
            # decides, since it depends on how much room the tile leaves.
            img = pygame.transform.smoothscale(
                img, (max(1, int(img.get_width() * LABEL_SIZE)),
                      max(1, int(img.get_height() * LABEL_SIZE))))
        if flip:
            # Turned with the tile, the way an opponent's shogi piece
            # faces away from you. Orientation is what marks ownership,
            # so the writing should agree with the wood it sits on.
            img = pygame.transform.rotate(img, 180)
        screen.blit(img, img.get_rect(center=rect.center))

    def draw_piece(self, screen, piece: Piece, x, y) -> None:
        """Tile first, then its code on top. The tile is cached art and
        faces its owner; the text is drawn fresh and always upright, so a
        Black piece is still readable from White's side."""
        L = self.layout
        flip = facing(piece.owner, L.flipped)
        screen.blit(piece_surface(piece, L.cell_w, L.cell_h, flip), (int(x), int(y)))
        # The marks are baked into the tile and rotate with it, so for
        # Black they sit in the upper half. Put the label in the other
        # half rather than on top of them - and never rotate the text.
        rect = pygame.Rect(int(x), int(y), L.cell_w, L.cell_h)
        if SHOW_MOVEMENT_HINTS:
            shift = int(L.cell_h * LABEL_OFFSET) * (1 if flip else -1)
            rect = rect.move(0, shift)
        self.draw_tile_label(screen, piece.name, piece.owner, rect, flip=flip)

    def draw_board(self, screen) -> None:
        L = self.layout
        hovered = None
        if (self.animation is None and self.state.phase == "battle"
                and self.controls(self.state.turn)):
            hovered = self.square_from_mouse(pygame.mouse.get_pos())

        draw_board_surface(screen, L)

        draw_board_lines(screen, L)

        self.draw_coordinates(screen)

        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                if not on_board(row, col):
                    continue
                rect = L.square_rect(row, col)
                cx, cy = L.square_center(row, col)
                if self.state.last_move and (row, col) in self.state.last_move:
                    self.highlight(screen, (row, col), LAST_MOVE, HIGHLIGHT_WIDTH)
                if hovered == (row, col):
                    here = self.state.board.at(row, col)
                    if here is not None and here.owner == self.state.turn:
                        self.highlight(screen, (row, col), HOVER, 2)
                if self.selected_square == (row, col):
                    self.highlight(screen, (row, col), SELECTED, HIGHLIGHT_WIDTH)

                dot = max(5, L.cell_w // 7)
                if (row, col) in self.legal_targets:
                    if self.state.board.at(row, col) is None:
                        pygame.draw.circle(screen, DOT, (cx, cy), dot)
                    else:
                        self.highlight(screen, (row, col), CAPTURE, 4, radius=CAPTURE_RADIUS)

                piece = self.state.board.at(row, col)
                # The piece in flight is drawn by draw_animation, so don't
                # also draw it sitting on its destination.
                skip = (self.animation is not None
                        and self.animation["dst"] == (row, col))
                # Nor the piece being dragged: it is under the pointer.
                if (self.drag is not None and self.drag["active"]
                        and self.drag["from"] == (row, col)):
                    skip = True
                if piece is not None and not skip:
                    self.draw_piece(screen, piece, rect.x, rect.y)

        for check in self.state.check_squares():
            self.highlight(screen, check, CHECK_RED, HIGHLIGHT_WIDTH)

        self.draw_annotations(screen)
        self.draw_animation(screen)
        self.draw_premove(screen)
        # The rings sit on top of the pieces they are ringing...
        self.draw_mate_marks(screen)
        # ...and arrows on top of everything.
        self.draw_arrows(screen)

    def highlight(self, screen, square, colour, width: int, fill=None,
                  radius: float = HIGHLIGHT_RADIUS) -> None:
        """Marks one point. With a piece on it, an outline of that piece -
        its own shape, a little larger, facing the way it faces. On an
        empty point, a circle."""
        L = self.layout
        piece = self.state.board.at(*square)
        if piece is not None:
            draw_piece_outline(screen, colour, piece, L.square_rect(*square),
                               facing(piece.owner, L.flipped), width, fill)
        else:
            draw_ring(screen, colour, L.square_center(*square),
                      L.cell_w * radius, width, fill)

    def draw_premove(self, screen) -> None:
        """Outlines the move waiting to be played.

        Drawn in its own colour rather than the selection blue, so a
        queued move is never mistaken for one that has been made.
        """
        squares = self.premove_squares()
        if not squares:
            return
        for square in squares:
            self.highlight(screen, square, PREMOVE, HIGHLIGHT_WIDTH)

    def draw_mate_marks(self, screen) -> None:
        """Rings the pieces that sealed the General in.

        Two colours, because the two jobs are different and worth telling
        apart when you are working out how you lost: red for the pieces
        actually giving check, gold for the ones holding the escape
        squares shut - including any defending a checker the General
        would otherwise have taken.
        """
        marks = self.mate_highlight()
        if not marks["checkers"] and not marks["support"]:
            return
        for group, colour in (("support", MATE_SUPPORT), ("checkers", CHECK_RED)):
            for square in marks[group]:
                self.highlight(screen, square, colour, HIGHLIGHT_WIDTH)

    def draw_coordinates(self, screen) -> None:
        """Glinski's labels, outside the board's edge: the file letter by
        the point at White's end of every file, and the rank numbers down
        the left-hand side - the straight side for the lower ranks, the
        slanting one above it for the rest.

        Each label is pushed straight out from the edge its point sits on,
        found from which of the point's neighbours are missing, so it
        always clears the board whatever the board's size and whichever
        way up it is drawn. Worked out from the points as DRAWN, so the
        labels turn with the board."""
        L, F = self.layout, self.fonts
        s = L.hex_size
        out = s * (BOARD_MARGIN + 0.42)              # past the paper's edge
        # Screen angle (y down) of each neighbour, by (row, col) step.
        angle_of = {d: round(math.degrees(math.atan2(lattice_xy(*d)[1], lattice_xy(*d)[0]))) % 360
                    for d in HEX_DIRS}
        if FLAT:
            # Ranks are rows; files slant, and are labelled where they meet
            # White's side of the board. That side's slanting edge leans
            # left normally and right when turned, so the ranks go on the
            # other side - their left ends normally, their right when
            # turned - and the two sets of labels never meet.
            below = tuple(a for a in angle_of.values() if 0 < a < 180)
            above = tuple(a for a in angle_of.values() if 180 < a < 360)
            left = tuple(a for a in angle_of.values() if 90 < a < 270)
            right = tuple(a for a in angle_of.values() if a < 90 or a > 270)
            file_side = above if L.flipped else below
            rank_side = right if L.flipped else left
        elif L.flipped:
            file_side, rank_side = (270, 210, 330), (150, 210, 90)
        else:
            file_side, rank_side = (90, 150, 30), (150, 210, 270)

        def place(text, vrow, vcol, side) -> bool:
            missing = [a for (dr, dc), a in angle_of.items()
                       if a in side and not on_board(vrow + dr, vcol + dc)]
            if not missing:
                return False
            # Average the directions as vectors, then push out - further
            # at a corner, where the paper reaches out to a point.
            ax = sum(math.cos(math.radians(a)) for a in missing)
            ay = sum(math.sin(math.radians(a)) for a in missing)
            length = math.hypot(ax, ay) or 1.0
            reach = out / math.cos(math.radians(30)) if len(missing) == 3 else out
            x, y = L.view_centre(vrow, vcol)
            img = F.small.render(text, True, COORD_TEXT)
            screen.blit(img, img.get_rect(center=(round(x + reach * ax / length),
                                                  round(y + reach * ay / length))))
            return True

        for vcol in range(BOARD_SIZE):
            rows = [r for r in range(BOARD_SIZE) if on_board(r, vcol)]
            edge = min(rows) if L.flipped else max(rows)
            place(FILE_LETTERS[L.view_cell(edge, vcol)[1]], edge, vcol, file_side)

        labelled = set()
        # The left-hand file first, so its ranks are labelled down it; the
        # slanting edge then takes the ranks it doesn't have.
        for vcol in range(BOARD_SIZE):
            for vrow in range(BOARD_SIZE):
                if not on_board(vrow, vcol):
                    continue
                if FLAT and on_board(vrow, vcol + (1 if L.flipped else -1)):
                    continue                 # only the end of a row
                rank = rank_of(*L.view_cell(vrow, vcol))
                if rank not in labelled and place(str(rank), vrow, vcol, rank_side):
                    labelled.add(rank)

    def draw_annotations(self, screen) -> None:
        """The marked SQUARES only. Arrows are drawn separately and last -
        see draw_arrows."""
        if not self.marks:
            return
        for square in self.marks:
            self.highlight(screen, square, MARK_EDGE, HIGHLIGHT_WIDTH,
                           fill=MARK_FILL, radius=MARK_RADIUS)

    def draw_arrows(self, screen) -> None:
        """Drawn after every square highlight, so an arrow is never buried
        under one. An arrow is something you put there on purpose; the
        highlights are the board telling you about itself."""
        L = self.layout
        live = list(self.arrows)
        if self.arrow_start is not None:
            # Snap the preview too, so what you see while dragging is what
            # you get when you let go.
            hover = self.snap_arrow(self.arrow_start, pygame.mouse.get_pos())
            if hover is not None and hover != self.arrow_start:
                live.append((self.arrow_start, hover))
        if not live:
            return
        overlay = pygame.Surface((L.board_w, L.board_h), pygame.SRCALPHA)
        for start, end in live:
            points = []
            for row, col in self.arrow_path(start, end):
                x, y = L.square_center(row, col)
                points.append((x - L.board_x, y - L.board_y))
            self._draw_arrow(overlay, points)
        screen.blit(overlay, (L.board_x, L.board_y))

    def _draw_arrow(self, surface, points) -> None:
        """Paints an arrow along a path - the look is board_design's."""
        draw_arrow(surface, points, self.layout.cell_w)

    def draw_animation(self, screen) -> None:
        anim = self.animation
        if anim is None:
            return
        L = self.layout
        elapsed = pygame.time.get_ticks() - anim["start"]
        t = max(0.0, min(1.0, elapsed / anim["duration"]))

        eased = t * t * (3 - 2 * t)
        sx, sy = L.square_center(*anim["src"])
        dx, dy = L.square_center(*anim["dst"])
        cx = sx + (dx - sx) * eased
        cy = sy + (dy - sy) * eased
        self.draw_piece(screen, anim["piece"], cx - L.cell_w // 2, cy - L.cell_h // 2)

        # A ring spreading out from the square where a piece was taken.
        if anim.get("captured"):
            fade = max(0.0, 1.0 - t)
            radius = int(L.cell_w * CAPTURE_RING_START + L.cell_w * CAPTURE_RING_GROWTH * t)
            ring = pygame.Surface((L.cell_w, L.cell_h), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*CAPTURE, int(180 * fade)),
                               (L.cell_w // 2, L.cell_h // 2), radius, 4)
            screen.blit(ring, (dx - L.cell_w // 2, dy - L.cell_h // 2))

    def draw_material_graph(self, screen, x: int, top: int, width: int, height: int) -> int:
        """
        The material swing over the whole game, filled above the midline
        when White leads and below when Black does.
        """
        F = self.fonts
        blit_text(screen, F.small, "Material swing", MUTED, x, top, width)
        top += F.small.get_linesize() + 2
        plot = pygame.Rect(x, top, width, height)
        pygame.draw.rect(screen, BG, plot)

        values = [0] + [entry["material"] for entry in self.state.history]
        span = max(400, max(abs(v) for v in values))
        mid = plot.y + plot.height // 2

        def point(index, value):
            span_x = max(1, len(values) - 1)
            px = plot.x + round(index * (plot.width - 1) / span_x)
            py = mid - round((value / span) * (plot.height / 2 - 2))
            return px, py

        line = [point(i, v) for i, v in enumerate(values)]
        if len(line) > 1:
            # Two filled areas rather than one, so "who is ahead" is a
            # colour and not something you have to read off an axis.
            for colour, above in ((GOOD, True), (BAD, False)):
                shape = [(px, min(py, mid) if above else max(py, mid)) for px, py in line]
                poly = [(line[0][0], mid)] + shape + [(line[-1][0], mid)]
                surface = pygame.Surface((plot.width, plot.height), pygame.SRCALPHA)
                pygame.draw.polygon(surface, (*colour, 70),
                                    [(px - plot.x, py - plot.y) for px, py in poly])
                screen.blit(surface, plot.topleft)
            pygame.draw.lines(screen, TEXT, False, line, 2)
        pygame.draw.line(screen, DIM, (plot.x, mid), (plot.right, mid), 1)
        return plot.bottom + self.layout.pad

    def move_pairs(self) -> List[Tuple[int, Optional[Dict], Optional[Dict]]]:
        """The record grouped into numbered turns, White then Black."""
        pairs: List[Tuple[int, Optional[Dict], Optional[Dict]]] = []
        for entry in self.state.history:
            if pairs and entry["mover"] == "B" and pairs[-1][2] is None:
                number, white, _ = pairs[-1]
                pairs[-1] = (number, white, entry)
            else:
                pairs.append((len(pairs) + 1,
                              entry if entry["mover"] == "W" else None,
                              entry if entry["mover"] == "B" else None))
        return pairs

    def draw_move_log(self, screen, x: int, top: int, width: int, bottom: int) -> None:
        """
        The game so far. Newest at the bottom, and it follows the game
        unless you have scrolled back - see scroll_log.
        """
        F = self.fonts
        header = "Moves" if self.log_scroll == 0 else f"Moves  (back {self.log_scroll})"
        blit_text(screen, F.small, header, GOLD if self.log_scroll else MUTED, x, top, width)
        top += F.small.get_linesize() + 2

        line_h = F.small.get_linesize() + 4
        room = max(0, (bottom - top) // line_h)
        self.log_rect = pygame.Rect(x, top, width, max(0, room * line_h))
        if room == 0:
            return

        pairs = self.move_pairs()
        self.log_scroll = max(0, min(self.log_scroll, max(0, len(pairs) - room)))
        end = len(pairs) - self.log_scroll
        window = pairs[max(0, end - room):end]

        column = width // 2
        last = self.state.history[-1] if self.state.history else None
        for index, (number, white, black) in enumerate(window):
            y = top + index * line_h
            if index % 2 == 0:
                pygame.draw.rect(screen, ROW_STRIPE, (x - 4, y - 1, width + 8, line_h))
            blit_text(screen, F.small, f"{number}", DIM, x, y, 26)
            for entry, offset in ((white, 26), (black, 26 + column)):
                if entry is None:
                    continue
                colour = CHECK_RED if entry["check"] else TEXT
                if entry is last:
                    colour = GOLD
                blit_text(screen, F.small, entry["text"], colour,
                          x + offset, y, column - 8)

        # A thumb down the right edge, so it's obvious there is more above.
        if len(pairs) > room:
            track = self.log_rect
            span = max(1, len(pairs))
            height = max(12, int(track.height * room / span))
            shown_top = max(0, end - room)
            offset = int(track.height * shown_top / span)
            pygame.draw.rect(screen, PANEL_LINE,
                             (track.right - 3, track.y, 3, track.height))
            pygame.draw.rect(screen, DIM,
                             (track.right - 3, track.y + offset, 3, height))

    def draw_pool(self, screen, x: int, top: int, width: int) -> int:
        """The sandbox's pool: every piece, for each side, to put on the
        board - click a tile then empty points, or drag a tile onto one. A
        side's General tile works only while that side has no General."""
        F = self.fonts
        y = blit_text(screen, F.small, "Pool - click or drag onto an empty point",
                      MUTED, x, top, width)
        y = blit_text(screen, F.small, "Drag a piece off the board to remove it",
                      DIM, x, y, width)
        y += 4
        names = list(PIECE_CODES.values())
        gap = 6
        tile_w = max(18, (width - (len(names) - 1) * gap) // len(names))
        tile_h = round(tile_w * Layout.CELL_RATIO)
        for owner in ("W", "B"):
            for i, name in enumerate(names):
                rect = pygame.Rect(x + i * (tile_w + gap), y, tile_w, tile_h)
                usable = name != ROYAL or self.state.board.royal_pos(owner) is None
                screen.blit(piece_surface(Piece(owner, name), tile_w, tile_h, False), rect.topleft)
                self.draw_tile_label(screen, name, owner,
                                     rect.move(0, -int(tile_h * LABEL_OFFSET)) if SHOW_MOVEMENT_HINTS else rect)
                if not usable:
                    shade = pygame.Surface(rect.size, pygame.SRCALPHA)
                    shade.fill((0, 0, 0, 140))
                    screen.blit(shade, rect.topleft)
                    continue
                if self.pool_pick == (owner, name):
                    pygame.draw.rect(screen, SELECTED, rect.inflate(6, 6), 3, border_radius=6)
                self.pool_tiles[(owner, name)] = rect
            y += tile_h + gap
        return y + 4

    def draw_panel(self, screen) -> None:
        L, F = self.layout, self.fonts
        pygame.draw.rect(screen, PANEL, (L.panel_x, 0, L.panel_w, L.win_h))
        pygame.draw.line(screen, PANEL_LINE, (L.panel_x, 0), (L.panel_x, L.win_h))

        text_w = L.panel_w - L.pad * 2
        x = L.panel_x + L.pad
        y = L.top_bar + L.pad

        if self.state.phase == "gameover":
            result = "Draw" if self.state.winner is None else f"{self.state.winner} wins"
            img = F.big.render(fit_text(F.big, result, text_w), True, GOLD)
            screen.blit(img, (x, y))
            y += img.get_height() + 4
            y = blit_text(screen, F.small, self.state.message, MUTED, x, y, text_w)
        else:
            turn = "Sandbox" if SANDBOX else f"{self.state.player_name()} to move"
            img = F.big.render(fit_text(F.big, turn, text_w), True,
                               MUTED if self.thinking else TEXT)
            screen.blit(img, (x, y))
            y += img.get_height() + 2
            # A position that has come up before is one more visit from a
            # draw - worth knowing before you play into it a third time.
            seen = self.state.repetitions()
            if seen >= 2:
                y = blit_text(screen, F.small,
                              "This position has come up twice - a third time draws",
                              GOLD, x, y, text_w)

        if self.state.phase == "battle":
            diff = self.state.material_diff()
            if diff > 0:
                label, colour = f"Material  White +{diff}", GOOD
            elif diff < 0:
                label, colour = f"Material  Black +{-diff}", BAD
            else:
                label, colour = "Material  even", MUTED
            y = blit_text(screen, F.small, label, colour, x, y, text_w)
        y += L.pad

        pygame.draw.line(screen, PANEL_LINE, (x, y), (x + text_w, y))
        y += L.pad

        self.pool_tiles = {}
        if SANDBOX:
            y = self.draw_pool(screen, x, y, text_w)
            pygame.draw.line(screen, PANEL_LINE, (x, y), (x + text_w, y))
            y += L.pad

        # The graph gets a fixed slice; the log takes the rest and simply
        # shows fewer moves when the window is short.
        keys = "R restart   Esc menu   C clear   M mute   F11 full"
        keys_top = L.win_h - L.pad - F.small.get_linesize()
        room = keys_top - y
        graph_h = int(clamp(room * 0.28, 44, 120))
        if room > graph_h + F.small.get_linesize() * 4:
            y = self.draw_material_graph(screen, x, y, text_w, graph_h)
        if room > F.small.get_linesize() * 3:
            self.draw_move_log(screen, x, y, text_w, keys_top - 4)
        blit_text(screen, F.small, keys, DIM, x, keys_top, text_w)
