"""
board_design.py - how HEX CHARGE LOOKS.

Everything about the appearance of the board and the pieces lives here:
colours, the board and its lines, every highlight, the
shape of a tile, its palettes and sizes, and the diagram of how each
piece moves. To restyle the game, this is the only file to touch.

What the game DOES is elsewhere. config.py holds the rules, Rules.py
plays them, and Ui.py runs the window - menus, clicks, timing, sound - and
asks this file whenever it needs to draw something. Nothing in here
changes how a piece moves; it only changes how that is shown.

One setting in config.py still affects drawing, because it is a rule
before it is a picture: SHOW_MOVEMENT_HINTS turns the diagrams on and off.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

from config import SHOW_MOVEMENT_HINTS
from Rules import BOARD_SIZE, FLAT, GUARD_WALKS, HEX_DIRS, KNIGHT_LEAPS, Piece, on_board


def lattice_xy(dr: float, dc: float) -> Tuple[float, float]:
    """Where a (row, col) step lands on screen, in point radii: one step
    along a line is sqrt(3) long.

    This is the one place the board's turn is decided. With the point at
    each army's back (Glinski's way) the files are vertical; with the flat
    side at the back the array's rows - lines too - are horizontal. Every
    other piece of geometry, from where a point is drawn to which way a
    tile's diagram points, comes from here."""
    if FLAT:
        return math.sqrt(3.0) * (dc + dr / 2.0), 1.5 * dr
    return 1.5 * dc, math.sqrt(3.0) * (dr + dc / 2.0)


# ======================================================================
# The colours
# ======================================================================
# Each piece is an arch - a semicircle over a rectangle - whose rounded
# end points at the enemy, and the two armies are told apart by colour as
# well. The board is the same white xiangqi board either way; the scheme
# picks the PIECES:
#
#   "modern"  White's army red, Black's black, both with light ink
#   "wooden"  White's army gold, Black's brown, both with dark ink

COLOUR_SCHEME = "modern"


# ======================================================================
# The board
# ======================================================================
# Drawn as in xiangqi: a white board with black lines, and the pieces
# standing on the POINTS where the lines cross rather than inside cells.
# The lines are the six orthogonal directions themselves - every point is
# joined to its six neighbours - so the board is a lattice of triangles
# filling a hexagon, and each line on it is a line a Chariot can travel.
# Round the outside, a heavier second frame a little way out, as on a
# xiangqi board.

BOARD_COLOUR = (247, 245, 240)

BOARD_EDGE = (34, 34, 34)

GRID_LINE = (40, 40, 40)

COORD_TEXT = (150, 136, 116)

GRID_WIDTH = 1          # the lattice lines, in pixels
FRAME_WIDTH = 2         # the outer frame
FRAME_GAP = 0.16        # how far out the frame stands, in cell radii
BOARD_MARGIN = 0.95     # white paper beyond the outer points, in cell radii

# The centre point and the six around it, marked with small dots the way
# a xiangqi board marks its cannon and soldier points.
STAR_POINTS = True


def _cells():
    return [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if on_board(r, c)]


def _outline(L, push: float):
    """The board's six corner points, pushed `push` pixels outward from
    each side of the hexagon they make."""
    R = BOARD_SIZE // 2
    corners = [(0, R), (0, 2 * R), (R, 2 * R), (2 * R, R), (2 * R, 0), (R, 0)]
    cx, cy = L.centre_x, L.centre_y
    apothem = 1.5 * R * L.hex_size            # centre to the middle of a side
    grow = (apothem + push) / apothem
    out = []
    for row, col in corners:
        x, y = L.square_center(row, col)
        out.append((cx + (x - cx) * grow, cy + (y - cy) * grow))
    return out


def draw_board_surface(screen, layout) -> None:
    """The white board and its edge - everything under the lines."""
    paper = _outline(layout, layout.hex_size * BOARD_MARGIN)
    pygame.draw.polygon(screen, BOARD_COLOUR, paper)
    pygame.draw.polygon(screen, BOARD_EDGE, paper, 2)


def draw_board_lines(screen, L) -> None:
    """The lattice: a line from every point to each of its neighbours,
    drawn after the board and any zone tint and before the pieces. The
    lines meet at exactly the screen points Ui.Layout.square_center gives
    the pieces, so a piece can never sit a pixel off its point."""
    for row, col in _cells():
        a = L.square_center(row, col)
        # Three directions each, so every line is drawn once.
        for dr, dc in ((1, 0), (0, 1), (-1, 1)):
            if on_board(row + dr, col + dc):
                b = L.square_center(row + dr, col + dc)
                if GRID_WIDTH > 1:
                    pygame.draw.line(screen, GRID_LINE, a, b, GRID_WIDTH)
                else:
                    pygame.draw.aaline(screen, GRID_LINE, a, b)

    # The heavier frame just outside the outer lines.
    frame = _outline(L, max(3.0, L.hex_size * FRAME_GAP))
    pygame.draw.polygon(screen, GRID_LINE, frame, FRAME_WIDTH)

    if STAR_POINTS:
        R = BOARD_SIZE // 2
        radius = max(2, int(L.hex_size * 0.07))
        for dr, dc in [(0, 0), (-1, 0), (1, 0), (-1, 1), (0, 1), (0, -1), (1, -1)]:
            cell = (R + 2 * dr, R + 2 * dc) if (dr, dc) != (0, 0) else (R, R)
            if on_board(*cell):
                pygame.draw.circle(screen, GRID_LINE, L.square_center(*cell), radius)


# ======================================================================
# Highlights
# ======================================================================
# Everything the board draws ON TOP of the squares to tell you something:
# selection, legal moves, the last move, check, your own marks and arrows.

SELECTED = (78, 138, 220)

DOT = (70, 178, 106)

CAPTURE = (200, 82, 82)

LAST_MOVE = (176, 186, 96)

HOVER = (232, 226, 196)

PREMOVE = (128, 106, 178)     # a queued move, waiting for your turn

# Every outline drawn around a square uses this, whatever it means. They
# used to differ - the selection and last move at 4, the check ring
# pulsing between 3 and 5, the premove and mate rings scaled off the cell
# size - and the board read as though some highlights mattered more than
# others when they are simply different things.
HIGHLIGHT_WIDTH = 3

CHECK_RED = (218, 62, 62)

# Highlights are rings around the crossing a piece stands on, not squares.
# Sizes are fractions of a square's width. Every ring has to clear the
# largest piece, or the piece hides it - so a capture target gets the same
# size as the rest, told apart by its colour and thicker line.
HIGHLIGHT_RADIUS = 0.47
CAPTURE_RADIUS = 0.47
MARK_RADIUS = 0.40            # your own marked points, filled

# A point with a piece on it is highlighted with an outline of the piece
# itself rather than a circle: the arch's own shape, OUTLINE_GAP of a
# square larger all round, so it follows the piece's size and which way
# it faces.
OUTLINE_GAP = 0.035


MARK_FILL = (232, 124, 44, 96)

MARK_EDGE = (232, 124, 44)

ARROW_COLOR = (232, 124, 44, 190)

# The ring around each piece holding a mated General's escape squares
# shut. The pieces giving check are ringed in CHECK_RED.
MATE_SUPPORT = (206, 176, 84)

# The ring that bursts on a square when a piece is captured, as fractions
# of a square's width: where it starts, and how much it grows.
CAPTURE_RING_START = 0.34
CAPTURE_RING_GROWTH = 0.28

# Your right-click arrows. The shaft is a square's width divided by the
# divisor (never thinner than 4 pixels); the head is ARROW_HEAD of a
# square long, but never more than ARROW_HEAD_MAX of the whole arrow, and
# its wings spread ARROW_WING of the head's length.
ARROW_WIDTH_DIVISOR = 9
ARROW_HEAD = 0.36
ARROW_HEAD_MAX = 0.42
ARROW_WING = 0.55

# How many times larger an arrow is drawn before being scaled down, which
# is what smooths its round ends and diagonal edges. 1 turns it off.
ARROW_SUPERSAMPLE = 3


def _band(surface, colour, a, b, half: float) -> None:
    """A straight stroke of exactly `half` either side of the line a-b.

    Drawn as a rectangle turned to lie along the line, because pygame's
    own thick line is built from horizontal or vertical pixel runs: at 45
    degrees a line of width 9 is only about 9 / sqrt(2) = 6.4 pixels
    across, which is why diagonal arrows used to look thinner.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 0.5:
        return
    nx, ny = -dy / length * half, dx / length * half
    pygame.draw.polygon(surface, colour, [
        (a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny),
        (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)])


_RING_CACHE: Dict[tuple, "pygame.Surface"] = {}


def draw_ring(surface, colour, centre, radius: float, width: int, fill=None) -> None:
    """A highlight around one crossing: a ring of `width` pixels, and an
    optional fill inside it (colours may carry alpha).

    Drawn ARROW_SUPERSAMPLE times larger and scaled down, as the arrows
    are, because a plain pygame circle is visibly jagged at this size. The
    result is cached - the board asks for the same few rings every frame.
    """
    r = max(2, int(round(radius)))
    key = (tuple(colour), r, width, tuple(fill) if fill else None)
    image = _RING_CACHE.get(key)
    if image is None:
        k = ARROW_SUPERSAMPLE
        size = 2 * r + 4
        big = pygame.Surface((size * k, size * k), pygame.SRCALPHA)
        big.fill((*colour[:3], 0))
        mid = (size * k // 2, size * k // 2)
        if fill:
            pygame.draw.circle(big, fill, mid, r * k)
        pygame.draw.circle(big, colour, mid, r * k, max(1, width * k))
        image = pygame.transform.smoothscale(big, (size, size))
        if len(_RING_CACHE) > 128:
            _RING_CACHE.clear()
        _RING_CACHE[key] = image
    surface.blit(image, image.get_rect(center=(int(centre[0]), int(centre[1]))))


_OUTLINE_CACHE: Dict[tuple, "pygame.Surface"] = {}


def draw_piece_outline(surface, colour, piece: "Piece", rect, flip: bool,
                       width: int, fill=None) -> None:
    """A highlight in the shape of the piece on this point: its arch, grown
    by OUTLINE_GAP of a square, `width` pixels thick, with an optional
    fill inside (colours may carry alpha).

    Uses exactly the scale and centre render_piece does, so the outline
    sits evenly around the piece whatever its size. Drawn as a band - the
    grown shape filled, the slightly smaller one cut out of it - because
    pygame's own thick polygon outline leaves notches on a curve. Smoothed
    and cached like the rings and arrows.
    """
    cw, ch = rect.width, rect.height
    key = (tuple(colour), tuple(fill) if fill else None, size_of(piece.name),
           bool(flip), cw, ch, width)
    image = _OUTLINE_CACHE.get(key)
    pad = max(4, int(cw * 0.2))
    if image is None:
        k = ARROW_SUPERSAMPLE
        big = pygame.Surface(((cw + 2 * pad) * k, (ch + 2 * pad) * k), pygame.SRCALPHA)
        big.fill((*colour[:3], 0))
        scale = min(cw * TILE_FILL / ART_W, ch * TILE_FILL / ART_H) * size_of(piece.name)
        centre = ((pad + cw / 2.0) * k, (pad + ch / 2.0) * k)
        half_width = 38.0 * scale                     # the arch's radius, in pixels
        mid = (0.0, 2.0)                              # the arch's middle, in tile units

        def grown(by_pixels: float):
            factor = 1.0 + by_pixels / half_width
            points = [(mid[0] + (x - mid[0]) * factor, mid[1] + (y - mid[1]) * factor)
                      for x, y in TILE_SHAPE]
            return [_art_point(p, (0.0, 0.0), 1.0, centre, scale * k, flip) for p in points]

        gap = cw * OUTLINE_GAP
        pygame.draw.polygon(big, colour, grown(gap + width))
        # Writing straight into the pixels, not blending: this is the cut.
        pygame.draw.polygon(big, fill if fill else (*colour[:3], 0), grown(gap))
        image = pygame.transform.smoothscale(big, (cw + 2 * pad, ch + 2 * pad))
        if len(_OUTLINE_CACHE) > 256:
            _OUTLINE_CACHE.clear()
        _OUTLINE_CACHE[key] = image
    surface.blit(image, (rect.x - pad, rect.y - pad))


_ARROW_CACHE: Dict[tuple, tuple] = {}


def draw_arrow(surface, points, cell_w: int) -> None:
    """A right-click arrow along a path of pixel points: a shaft of even
    thickness in every direction, rounded where it starts and at every
    bend, and a head on the last segment.

    Drawn ARROW_SUPERSAMPLE times larger and scaled down smoothly, as the
    pieces are. Without that, a round end a few pixels across comes out
    as a near-square block, and every diagonal edge as a staircase.
    """
    if len(points) < 2:
        return
    k = ARROW_SUPERSAMPLE
    key = (tuple((round(x, 1), round(y, 1)) for x, y in points), cell_w, ARROW_COLOR)
    cached = _ARROW_CACHE.get(key)
    if cached is not None:
        image, corner = cached
        surface.blit(image, corner)
        return
    half = max(4, cell_w // ARROW_WIDTH_DIVISOR) / 2.0
    (sx, sy), (ex, ey) = points[-2], points[-1]
    dx, dy = ex - sx, ey - sy
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    head = min(cell_w * ARROW_HEAD, length * ARROW_HEAD_MAX)
    wing = head * ARROW_WING

    # Work on a small canvas around the arrow only, not the whole board.
    margin = int(max(half, wing)) + 3
    left = int(min(p[0] for p in points)) - margin
    top = int(min(p[1] for p in points)) - margin
    width = int(max(p[0] for p in points)) + margin - left
    height = int(max(p[1] for p in points)) + margin - top
    canvas = pygame.Surface((width * k, height * k), pygame.SRCALPHA)
    # Transparent ORANGE, not transparent black. Scaling down blends each
    # edge pixel with its empty neighbours, and if those were black the
    # soft edge would pick up a grey fringe.
    canvas.fill((*ARROW_COLOR[:3], 0))
    big = lambda p: ((p[0] - left) * k, (p[1] - top) * k)

    def round_cap(point) -> None:
        cx, cy = big(point)
        pygame.draw.circle(canvas, ARROW_COLOR, (round(cx), round(cy)), round(half * k))

    # Every segment but the last, each joined to the next by a round cap
    # so a bent Knight arrow turns its corner smoothly.
    round_cap(points[0])
    for a, b in zip(points, points[1:-1]):
        _band(canvas, ARROW_COLOR, big(a), big(b), half * k)
        round_cap(b)

    bx, by = ex - ux * head, ey - uy * head
    _band(canvas, ARROW_COLOR, big((sx, sy)), big((bx, by)), half * k)
    pygame.draw.polygon(canvas, ARROW_COLOR, [
        big((ex, ey)),
        big((bx - uy * wing, by + ux * wing)),
        big((bx + uy * wing, by - ux * wing)),
    ])
    image = pygame.transform.smoothscale(canvas, (width, height))
    # An arrow that is not moving looks the same next frame, so keep it.
    # Only the one being dragged is drawn afresh each time.
    if len(_ARROW_CACHE) > 64:
        _ARROW_CACHE.clear()
    _ARROW_CACHE[key] = (image, (left, top))
    surface.blit(image, (left, top))


# ======================================================================
# The pieces
# ======================================================================

# How big each piece is drawn, as a multiple of the normal tile - rank at
# a glance, five per cent a step.
PIECE_SIZES = {
    "Pawn": 1.00,
    "Guard": 1.05,
    "Knight": 1.05,
    "Cannon": 1.05,
    "Chariot": 1.10,
    "General": 1.15,
}


# Hex Charge draws no emblems: every piece carries its two-letter code, so
# adding a piece costs no artwork at all. Whose it is shows twice over -
# in its colour, and in which way its rounded end points.
#
# The wooden scheme's colours; the modern scheme replaces them in its own
# section below. Each army has a body, an edge and an ink for its code.
WHITE_BODY = (238, 206, 118)
WHITE_EDGE = (134, 96, 34)
WHITE_LABEL = (152, 44, 20)
BLACK_BODY = (226, 192, 140)
BLACK_EDGE = (110, 76, 40)
BLACK_LABEL = (52, 35, 18)

# How far the two-letter code is pushed away from the movement diagram,
# as a fraction of a square's height. Only applies when the diagrams are
# shown; without them the code sits in the middle of the piece. It sits
# low because the arch narrows to a curve at the top, and letters placed
# any higher would clip it.
LABEL_OFFSET = 0.12

# How large the code is drawn, as a fraction of the normal lettering.
LABEL_SIZE = 0.8

# Movement marks engraved on the lower half of each tile.
MARK = (60, 42, 24)

def _arch(radius: float, top: float, bottom: float, steps: int = 32):
    """A semicircle on top of a rectangle, in tile units, as a polygon. The
    rounded end is the front of the piece - it points at the enemy."""
    centre_y = top + radius
    points = []
    for k in range(steps + 1):
        angle = math.pi * k / steps                 # left, over the top, to right
        points.append((-radius * math.cos(angle), centre_y - radius * math.sin(angle)))
    points += [(radius, bottom), (-radius, bottom)]
    return points


# The shape of a piece: a semicircle of radius 38 on top of a rectangle,
# in tile units. The code lives in the round half, the movement diagram in
# the square half.
TILE_SHAPE = _arch(radius=38.0, top=-40.0, bottom=44.0)
ART_W, ART_H = 80.0, 92.0

# How much of its square a normal-sized piece fills - small enough that
# the lines show between the pieces and each reads as standing on its
# crossing.
TILE_FILL = 0.76

# The cannon diagram, in tile units out from the diagram's centre: where
# the filled dot (the screen) sits, where the hollow circle (the target)
# sits, and the radius of both.
CANNON_SCREEN_AT = 12.5
CANNON_TARGET_AT = 19.5
CANNON_DOT = 2.8


# HEX CHARGE draws no emblems. Every piece is the same arch with its
# two-letter code on it, which is fast to read, impossible to confuse,
# and costs nothing to add a piece to - a new piece needs no artwork at
# all, just an entry in config.PIECE_CODES.
#
# The tile still turns around for the other player, so orientation is
# what tells you whose piece it is. The text is drawn upright by
# draw_piece() rather than baked into the tile, so it stays readable from
# your side of the board whichever way the tile is facing.

# ======================================================================
# Movement marks
# ======================================================================
# The lower half of every tile carries a diagram of how the piece moves,
# in the same art units as the tile itself (a radius of about 20 around
# a centre at (0, 20)). The notation is five symbols and nothing else:
#
#   arrow            unlimited range along that line
#   plain line       a single step along that line
#   small circles    a Knight's leap - twelve, two in each gap between
#                    the lines, so they never crowd an arrow
#   filled dots      on the Guard, the cells two steps away, reached
#                    through an empty cell between
#   line, dot, ring  a cannon: it slides along the line, must shoot over
#                    a piece (the filled dot), and takes beyond it (the
#                    hollow circle)
#   ring             the General
#
# Marks are baked into the cached tile, so they rotate with it - which is
# what makes a Pawn's forward mark point the right way for each player
# without any extra work. The text label is drawn separately and stays
# upright; see GameView.draw_piece.

MARK_CENTRE = (0.0, 20.0)


# ======================================================================
# The colour schemes
# ======================================================================
# COLOUR_SCHEME at the top picks one.

if COLOUR_SCHEME == "modern":
    # White's army red, Black's black, with light ink that reads on both.
    WHITE_BODY = (178, 30, 30)
    WHITE_EDGE = (112, 16, 16)
    WHITE_LABEL = (255, 234, 190)
    BLACK_BODY = (30, 30, 32)
    BLACK_EDGE = (105, 105, 108)
    BLACK_LABEL = (244, 240, 230)
    MARK = (226, 222, 214)
# "wooden" uses the colours set further up, where each is first defined:
# White gold, Black brown, dark ink.


# The six lines as they lie on a tile, forward first: straight up and
# down, and the four that cross to the next files at 60 degrees.
def _unit(dr: int, dc: int) -> Tuple[float, float]:
    x, y = lattice_xy(dr, dc)
    length = math.hypot(x, y)
    return x / length, y / length


# The six lines as they lie on a tile, whichever way the board is turned.
_HEX = [_unit(dr, dc) for dr, dc in HEX_DIRS]
_LEAP_DOT = 2.4        # radius of one knight mark
_WALK_DOT = 2.5        # radius of one Guard mark


def _rays(dirs, r1, r2, kind, colour):
    """One mark per direction, from radius r1 out to r2."""
    return [(kind, (dx * r1, dy * r1), (dx * r2, dy * r2), colour)
            for dx, dy in dirs]


def _leap_dots(distance: float, colour):
    """Twelve small circles, one toward each of the Knight's cells - two
    flanking the middle of every gap between the lines, so they read as
    their own ring and never land on an arrow."""
    return [("ring", (dx * distance, dy * distance), _LEAP_DOT, colour)
            for dx, dy in (_unit(dr, dc) for dr, dc in KNIGHT_LEAPS)]


def _walk_marks(colour):
    """The Guard: a step along each line, and a filled dot on every cell
    two away - six straight on, six in the gaps between. The dots sit at
    their true relative distances, so the gap ones are a little nearer."""
    marks = _rays(_HEX, 4, 10, "line", colour)
    for (dr, dc), _ in GUARD_WALKS:
        x, y = lattice_xy(dr, dc)
        scale = 17.0 / (2 * math.sqrt(3.0))       # a straight two-step lands at 17
        marks.append(("disc", (x * scale, y * scale), _WALK_DOT, colour))
    return marks


def _cannon_marks(dirs, colour):
    """How a cannon moves and takes, per direction: a line for the free
    slide, ending on a FILLED dot - the screen it must shoot over - and,
    just past it and not joined to it, a HOLLOW circle: the cell it takes
    on beyond the screen. Read outwards it is the shot itself: travel,
    the piece in the way, the target."""
    marks = []
    for dx, dy in dirs:
        screen_at, target_at = CANNON_SCREEN_AT, CANNON_TARGET_AT
        dot = CANNON_DOT
        marks.append(("line", (dx * 4.0, dy * 4.0),
                      (dx * (screen_at - dot), dy * (screen_at - dot)), colour))
        marks.append(("disc", (dx * screen_at, dy * screen_at), dot, colour))
        marks.append(("ring", (dx * target_at, dy * target_at), dot, colour))
    return marks


def _pawn_marks(colour):
    """The Pawn: a short step along each of the six lines."""
    return _rays(_HEX, 4, 13, "line", colour)


def movement_marks(name: str) -> List[Tuple]:
    """The diagram on the lower half of one piece's tile."""
    if name == "Chariot":
        return _rays(_HEX, 5, 19, "arrow", MARK)
    if name == "Knight":
        return _leap_dots(13.0, MARK)
    if name == "Guard":
        return _walk_marks(MARK)
    if name == "Cannon":
        return _cannon_marks(_HEX, MARK)
    if name == "Pawn":
        return _pawn_marks(MARK)
    if name == "General":
        # A ring: the royal piece, stepping every which way.
        return [("ring", (0, 0), 14.0, MARK)]
    return []


def _draw_marks(surface, name, centre, scale, flip) -> None:
    if not SHOW_MOVEMENT_HINTS:
        return
    origin = MARK_CENTRE
    for mark in movement_marks(name):
        kind, a, b, colour = mark
        if kind in ("ring", "disc"):
            # A hollow ring, or a filled disc.
            spot = _art_point((a[0], a[1]), origin, 1.0, centre, scale, flip)
            pygame.draw.circle(surface, colour, (round(spot[0]), round(spot[1])),
                               max(2, int(b * scale)),
                               0 if kind == "disc" else max(1, int(round(1.5 * scale))))
            continue
        start = _art_point(a, origin, 1.0, centre, scale, flip)
        end = _art_point(b, origin, 1.0, centre, scale, flip)
        width = max(1, int(round((1.8 if kind == "bar" else 1.4) * scale)))
        if kind == "dash":
            _dashed_line(surface, colour, start, end, width, 2.6 * scale)
        else:
            pygame.draw.line(surface, colour, start, end, width)
        if kind == "arrow":
            _arrow_head(surface, colour, start, end, scale)


def _dashed_line(surface, colour, start, end, width, dash) -> None:
    """pygame has no dashed line, so walk the segment in steps."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    step = max(2.0, dash)
    travelled = 0.0
    while travelled < length:
        run = min(step, length - travelled)
        a = (start[0] + ux * travelled, start[1] + uy * travelled)
        b = (start[0] + ux * (travelled + run), start[1] + uy * (travelled + run))
        pygame.draw.line(surface, colour, a, b, width)
        travelled += step * 2


def _arrow_head(surface, colour, start, end, scale) -> None:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    size = 3.4 * scale
    base = (end[0] - ux * size, end[1] - uy * size)
    wing = size * 0.62
    pygame.draw.polygon(surface, colour, [
        end,
        (base[0] - uy * wing, base[1] + ux * wing),
        (base[0] + uy * wing, base[1] - ux * wing),
    ])


PIECE_SUPERSAMPLE = 3
_PIECE_CACHE: Dict[Tuple, "pygame.Surface"] = {}

def _art_point(point, offset, sub_scale, centre, scale, flip):
    """Art units -> pixels. `centre` is the (x, y) middle of the target
    cell, which is no longer square. `flip` is the 180 degree turn that
    makes a tile face the other player; rotating by pi is just negating
    both axes."""
    x = offset[0] + point[0] * sub_scale
    y = offset[1] + point[1] * sub_scale
    if flip:
        x, y = -x, -y
    return (centre[0] + x * scale, centre[1] + y * scale)


def render_piece(piece: "Piece", width: int, height: int, flip: bool) -> "pygame.Surface":
    """Draws one blank tile, facing its owner.

    Rendered at PIECE_SUPERSAMPLE times final size and smoothscaled down,
    which is what gives the sloped shoulders a clean edge - pygame's
    polygon fill has no antialiasing of its own. The piece's code is
    written on top later by the view.

    `flip` is the finished orientation on screen, not simply "is it
    Black". A piece faces its owner's opponent, and turning the whole
    board turns that too - so the two cancel out and a Black piece on a
    turned board points up the screen, exactly as a White one does on an
    unturned one.
    """
    ss = PIECE_SUPERSAMPLE
    bw = max(1, int(width * ss))
    bh = max(1, int(height * ss))
    surface = pygame.Surface((bw, bh), pygame.SRCALPHA)
    scale = min(bw * TILE_FILL / ART_W, bh * TILE_FILL / ART_H) * size_of(piece.name)
    centre = (bw / 2.0, bh / 2.0)

    white = piece.owner == "W"
    fill = WHITE_BODY if white else BLACK_BODY
    edge = WHITE_EDGE if white else BLACK_EDGE
    outline = [_art_point(p, (0.0, 0.0), 1.0, centre, scale, flip) for p in TILE_SHAPE]
    pygame.draw.polygon(surface, fill, outline)
    pygame.draw.polygon(surface, edge, outline, max(1, int(round(2 * scale))))
    if SHOW_MOVEMENT_HINTS:
        _draw_marks(surface, piece.name, centre, scale, flip)
    return pygame.transform.smoothscale(surface, (int(width), int(height)))


def clear_piece_cache() -> None:
    """Dropped whenever the window resizes - tiles are re-rendered at the
    new cell size and keeping every old size around would leak."""
    _PIECE_CACHE.clear()


def label_colour(owner: str):
    """The ink for a piece's two-letter code."""
    return WHITE_LABEL if owner == "W" else BLACK_LABEL


def size_of(name: str) -> float:
    """How large the tile is drawn, relative to a Pawn. Rank is legible
    without reading anything: five per cent a step."""
    return PIECE_SIZES.get(name, 1.0)


def facing(owner: str, board_flipped: bool) -> bool:
    """Which way a tile points on screen. Owner and board turn cancel."""
    return (owner == "B") != board_flipped


def piece_surface(piece: "Piece", width: int, height: int,
                  flip: bool = False) -> "pygame.Surface":
    """Cached tile art. Keyed on everything that changes the drawing -
    orientation included, since a turned board draws the same piece the
    other way up."""
    w, h = int(width), int(height)
    key = (piece.name, piece.owner, bool(flip), w, h)
    surface = _PIECE_CACHE.get(key)
    if surface is None:
        surface = render_piece(piece, w, h, bool(flip))
        _PIECE_CACHE[key] = surface
    return surface

