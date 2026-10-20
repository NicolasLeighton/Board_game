"""
Rules.py - how HEX CHARGE is played.

Everything you would want to change lives in config.py; this file reads
it and implements the game. Two properties worth preserving:

  1. It imports NO pygame. The rules run and can be tested without a
     window ever opening.
  2. Nothing here knows about pixels or clicks. Rows and columns in,
     rows and columns out.

THE BOARD. A hexagon of hexagons, flat-topped, as in Glinski's hex chess.
Cells are stored in axial coordinates in an ordinary square array: `col`
is the file (left to right) and `row` runs down each file, so the six
neighbours of a cell are fixed offsets, exactly as on a square board. Only
the cells within BOARD_RADIUS of the centre are on the board; the corners
of the array are simply never "inside". Everything that walks a line or
takes a step therefore works unchanged - it just has six directions now
instead of eight, and no diagonals at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import config
import ai_config

BOARD_RADIUS = config.BOARD_RADIUS
if not 2 <= BOARD_RADIUS <= 7:
    raise ValueError("BOARD_RADIUS must be between 2 and 7.")
BOARD_SIZE = 2 * BOARD_RADIUS + 1          # side of the storage array
FILES = BOARD_SIZE                          # files across the board

# The material graph is drawn with the engine's own values, from
# ai_config.py, so the two always agree about who is ahead.
PIECE_VALUES = ai_config.PIECE_VALUES
PIECE_CODES = config.PIECE_CODES

ROYAL = "General"
PIECE_NAMES = list(PIECE_CODES.values())
GENERALS_CANT_TOUCH = config.GENERALS_CANT_TOUCH

# A position seen this many times, with the same side to move, is a draw.
REPETITION_LIMIT = 3

# Which way the board is turned - see BOARD_ORIENTATION in config.py.
# "point": a corner of the hexagon at each army's back, as Glinski drew
# it. "flat": a flat side at each army's back. The board and every move are
# the same either way; what changes is which points are each army's home,
# so the opening, and the way ranks are counted.
FLAT = getattr(config, "BOARD_ORIENTATION", "point") == "flat"
SETUP_NAME = "WHITE_SETUP_FLAT" if FLAT else "WHITE_SETUP"
SETUP = getattr(config, SETUP_NAME)

# Glinski's files: a to l, skipping j.
FILE_LETTERS = "abcdefghiklmnopq"[:FILES]


def on_board(row: int, col: int) -> bool:
    """Is this array cell one of the hexagon's cells?"""
    q, r = col - BOARD_RADIUS, row - BOARD_RADIUS
    return (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE
            and abs(q + r) <= BOARD_RADIUS)


# The six orthogonal directions, as (row, col) steps: straight up and down
# a file, and the four that cross to the next file - up-right, down-right,
# up-left, down-left. A hex cell has no diagonal neighbours.
HEX_DIRS = [(-1, 0), (1, 0), (-1, 1), (0, 1), (0, -1), (1, -1)]
ALL_DIRS = HEX_DIRS


def hex_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """Steps between two cells."""
    dr, dc = a[0] - b[0], a[1] - b[1]
    return (abs(dr) + abs(dc) + abs(dr + dc)) // 2


def _knight_leaps() -> List[Tuple[int, int]]:
    """Glinski's knight: two steps straight on, then one turned 60 degrees -
    the twelve nearest cells that share no line with him. In cube
    coordinates, every arrangement of (1, 2, -3) and its negative."""
    from itertools import permutations
    out = set()
    for sign in (1, -1):
        for x, y, z in permutations((sign, 2 * sign, -3 * sign)):
            out.add((z, x))                 # (row, col) = (cube z, cube x)
    return sorted(out)


def _guard_walks() -> List[Tuple[Tuple[int, int], List[Tuple[int, int]]]]:
    """The Guard's second step, as (offset, cells he may pass through).

    Two orthogonal steps reach the twelve cells two away. The six straight
    on have one way through; the six between two lines have two, and
    either will do."""
    walks: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    for a in HEX_DIRS:
        for b in HEX_DIRS:
            end = (a[0] + b[0], a[1] + b[1])
            if hex_distance(end, (0, 0)) == 2:
                walks.setdefault(end, [])
                if a not in walks[end]:
                    walks[end].append(a)
    return sorted((end, sorted(via)) for end, via in walks.items())


KNIGHT_LEAPS = _knight_leaps()
GUARD_WALKS = _guard_walks()

# How each piece moves, as data.
#
#   slides         walk outward until blocked; may capture what stops them
#   steps          one cell; may capture
#   leaps          jump straight to the cell, over anything
#   walks          two steps, through an EMPTY cell between
#   cannons        the xiangqi cannon: slide freely, capture only over a screen
PIECE_MOVES: Dict[str, Dict] = {
    "General":   {"steps": HEX_DIRS},
    "Chariot":   {"slides": HEX_DIRS},
    "Knight":    {"leaps": KNIGHT_LEAPS},
    "Guard":     {"steps": HEX_DIRS, "walks": GUARD_WALKS},
    # One point along any of the six lines, moving and taking the same
    # way - the General's move, on a piece that isn't royal.
    "Pawn":      {"steps": HEX_DIRS},
    "Cannon":    {"cannons": HEX_DIRS},
}


def move_spec(piece: "Piece") -> Dict:
    """How this piece moves."""
    return PIECE_MOVES[piece.name]


# ======================================================================
# Files and ranks
# ======================================================================
# Files are lettered a-l (no j); a file is one of the board's lines.
#
# With the point at each army's back, this is Glinski's notation: files
# run straight up the board, and every file counts its own ranks from 1 at
# White's edge, so rank 1 is not a straight line but a shallow V - a1 ...
# f1 runs down to the bottom corner and f1 ... l1 back up.
#
# With the flat side at the back, the ranks are the board's straight rows,
# counted up from White's edge, and the files are the lines slanting up
# to the right across them.
#
# Black's ranks are the same, counted from his edge.

def _file_bottom(col: int) -> int:
    """The row of a file's lowest cell."""
    return min(BOARD_SIZE - 1, BOARD_SIZE - 1 + BOARD_RADIUS - col)


def file_length(col: int) -> int:
    return BOARD_SIZE - abs(col - BOARD_RADIUS)


def rank_of(row: int, col: int) -> int:
    """White's rank of a point: 1 at his edge of the board."""
    if FLAT:
        return BOARD_SIZE - row
    return _file_bottom(col) - row + 1


def rank_for(owner: str, row: int, col: int) -> int:
    """How far up the board this cell is, counted from `owner`'s edge."""
    if owner == "W":
        return rank_of(row, col)
    return rank_of(BOARD_SIZE - 1 - row, BOARD_SIZE - 1 - col)


def cell_at(col: int, rank: int) -> Tuple[int, int]:
    """(row, col) of White's rank `rank` on file `col`."""
    if FLAT:
        return BOARD_SIZE - rank, col
    return _file_bottom(col) - rank + 1, col


def rank_cells(rank: int) -> List[Tuple[int, int]]:
    """The points of White's rank `rank`, left to right - one token each in
    a setup line. With the point at the back every rank has one token per
    file, some of them off the board on the short outer files; with the
    flat side at the back a rank is a row, and only its points count."""
    if FLAT:
        row = BOARD_SIZE - rank
        return [(row, c) for c in range(FILES) if on_board(row, c)]
    return [cell_at(c, rank) for c in range(FILES)]


def black_cell(row: int, col: int, mirrored: bool) -> Tuple[int, int]:
    """Where Black's copy of White's piece on (row, col) stands: the board
    turned through 180 degrees, or - mirrored - reflected across the middle
    so each piece faces its twin."""
    if not mirrored:
        return BOARD_SIZE - 1 - row, BOARD_SIZE - 1 - col
    if FLAT:
        # Reflected across the middle row, which keeps every point's
        # left-right place on the screen.
        return BOARD_SIZE - 1 - row, col + row - BOARD_RADIUS
    # Same file, counted down from Black's edge.
    top = _file_bottom(col) - file_length(col) + 1
    return top + rank_of(row, col) - 1, col


def other_owner(owner: str) -> str:
    return "W" if owner == "B" else "B"


# ======================================================================
# Reading the opening position
# ======================================================================

def parse_setup() -> List[Tuple[int, int, str, str]]:
    """
    Turns the opening in config.py - WHITE_SETUP, or WHITE_SETUP_FLAT with
    the flat side at the back - into (row, col, owner, name) placements for
    BOTH sides. You write only your own army, one line per rank, one token
    per point of the rank; Black is the same position turned through 180
    degrees - or, with MIRRORED_SETUP, reflected.

    Complains specifically about a malformed setup - this is the part
    people edit by hand, and a silent misread would be baffling.
    """
    name_of = SETUP_NAME
    placements: List[Tuple[int, int, str, str]] = []
    for offset, line in enumerate(SETUP):
        rank = offset + 1
        if rank > BOARD_SIZE:
            raise ValueError(f"{name_of} has more ranks than the board has.")
        tokens = line.split()
        points = rank_cells(rank)
        if len(tokens) != len(points):
            raise ValueError(
                f"{name_of} rank {rank} has {len(tokens)} points, expected "
                f"{len(points)}: {line!r}"
            )
        for (row, col), token in zip(points, tokens):
            if token == ".":
                continue
            if token not in PIECE_CODES:
                raise ValueError(
                    f"{name_of} rank {rank} has unknown piece {token!r}. "
                    f"Known codes: {', '.join(sorted(PIECE_CODES))}."
                )
            name = PIECE_CODES[token]
            placements.append((row, col, "W", name))
            placements.append((*black_cell(row, col, config.MIRRORED_SETUP), "B", name))

    taken: Dict[Tuple[int, int], str] = {}
    for row, col, owner, name in placements:
        where = f"{FILE_LETTERS[col]}{rank_of(row, col)}"
        if not on_board(row, col):
            raise ValueError(f"{name_of} puts a {name} off the board, on {where}.")
        if (row, col) in taken:
            raise ValueError(
                f"{name_of} puts White's and Black's armies both on {where}: "
                "keep each army to its own half of the board."
            )
        taken[(row, col)] = owner

    royals = sum(1 for _, _, o, n in placements if o == "W" and n == ROYAL)
    if royals != 1:
        raise ValueError(f"{name_of} has {royals} {ROYAL}s; it needs exactly one.")
    return placements


# ======================================================================
# Pieces and board
# ======================================================================

@dataclass
class Piece:
    owner: str          # "W" or "B"
    name: str

    def label(self) -> str:
        for code, name in PIECE_CODES.items():
            if name == self.name:
                return code
        return self.name[:2]


class Board:
    def __init__(self) -> None:
        self.grid: List[List[Optional[Piece]]] = [
            [None] * BOARD_SIZE for _ in range(BOARD_SIZE)
        ]

    def inside(self, row: int, col: int) -> bool:
        return on_board(row, col)

    def at(self, row: int, col: int) -> Optional[Piece]:
        if not self.inside(row, col):
            return None
        return self.grid[row][col]

    def set(self, row: int, col: int, piece: Optional[Piece]) -> None:
        self.grid[row][col] = piece

    def pieces(self, owner: Optional[str] = None) -> Iterable[Tuple[int, int, Piece]]:
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = self.grid[row][col]
                if piece is not None and (owner is None or piece.owner == owner):
                    yield row, col, piece

    def royal_pos(self, owner: str) -> Optional[Tuple[int, int]]:
        for row, col, piece in self.pieces(owner):
            if piece.name == ROYAL:
                return row, col
        return None

    def clone(self) -> "Board":
        copy = Board()
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                piece = self.grid[row][col]
                if piece is not None:
                    copy.grid[row][col] = Piece(piece.owner, piece.name)
        return copy


# ======================================================================
# Movement
# ======================================================================

def _slide_moves(board: Board, row: int, col: int, piece: Piece,
                 dirs, limit: int) -> List[Tuple[int, int]]:
    """Walk outward up to `limit` steps, stopping at the first occupied
    point - which may be taken if it is an enemy."""
    out = []
    for dr, dc in dirs:
        for step in range(1, limit + 1):
            nr, nc = row + dr * step, col + dc * step
            if not board.inside(nr, nc):
                break
            target = board.at(nr, nc)
            if target is None:
                out.append((nr, nc))
                continue
            if target.owner != piece.owner:
                out.append((nr, nc))
            break
    return out






def _hop_moves(board: Board, row: int, col: int, piece: Piece, dirs) -> List[Tuple[int, int]]:
    """
    Everything a cannon COVERS along its lines: every square past the
    first piece (the screen), up to and including the next piece.

    This is not where a cannon can move - it slides freely before the
    screen, and can only land beyond it by capturing. It is where it could
    CAPTURE if something stood there, which is the question check
    detection asks. Getting the two confused is a real bug: a General may
    not step onto an empty square past a screen, because the cannon would
    take him there, even though the cannon could not move to it now.
    """
    out = []
    for dr, dc in dirs:
        step = 1
        while True:                       # look for the screen
            nr, nc = row + dr * step, col + dc * step
            if not board.inside(nr, nc):
                break
            if board.at(nr, nc) is not None:
                step += 1
                while True:               # then run on past it
                    tr, tc = row + dr * step, col + dc * step
                    if not board.inside(tr, tc):
                        break
                    beyond = board.at(tr, tc)
                    if beyond is None:
                        out.append((tr, tc))
                        step += 1
                        continue
                    if beyond.owner != piece.owner:
                        out.append((tr, tc))
                    break
                break
            step += 1
    return out


def _cannon_moves(board: Board, row: int, col: int, piece: Piece, dirs) -> List[Tuple[int, int]]:
    """
    The xiangqi cannon, on the six lines.

    It slides along the line freely so long as it isn't capturing - so on
    an open board it moves exactly like a Chariot. To TAKE something it
    needs a screen: exactly one piece between it and its target, of
    either colour, with clear squares on both sides of that screen.

    That split personality is what makes it awkward to face. The same
    piece is a quiet developer down an empty file and a sniper down a
    crowded one, and blocking its line doesn't shut it off - it arms it.
    """
    out = []
    for dr, dc in dirs:
        step = 1
        while True:                        # quiet travel, no captures
            nr, nc = row + dr * step, col + dc * step
            if not board.inside(nr, nc):
                break
            if board.at(nr, nc) is not None:
                break                      # this is the screen
            out.append((nr, nc))
            step += 1
        nr, nc = row + dr * step, col + dc * step
        if not board.inside(nr, nc):
            continue                       # ran off the board, no screen
        step += 1
        while True:                        # look past the screen for prey
            tr, tc = row + dr * step, col + dc * step
            if not board.inside(tr, tc):
                break
            target = board.at(tr, tc)
            if target is None:
                step += 1
                continue
            if target.owner != piece.owner:
                out.append((tr, tc))
            break
    return out


def _walk_moves(board: Board, row: int, col: int, piece: Piece,
                walks) -> List[Tuple[int, int]]:
    """The Guard's two-step move: to a cell two away, through an EMPTY
    neighbour on the way. Where two neighbours lead there, either will do."""
    out = []
    for (dr, dc), vias in walks:
        target = (row + dr, col + dc)
        if not board.inside(*target):
            continue
        if not any(board.inside(row + vr, col + vc) and board.at(row + vr, col + vc) is None
                   for vr, vc in vias):
            continue
        occupant = board.at(*target)
        if occupant is None or occupant.owner != piece.owner:
            out.append(target)
    return out


def square_name(row: int, col: int) -> str:
    return f"{FILE_LETTERS[col]}{rank_of(row, col)}"


def _base_moves(board: Board, row: int, col: int, piece: Piece) -> List[Tuple[int, int]]:
    """Everything the piece does except the General's optional second step."""
    spec = move_spec(piece)
    moves: List[Tuple[int, int]] = []
    if "slides" in spec:
        moves += _slide_moves(board, row, col, piece, spec["slides"], BOARD_SIZE - 1)
    if "steps" in spec:
        moves += _slide_moves(board, row, col, piece, spec["steps"], 1)
    if "leaps" in spec:
        for dr, dc in spec["leaps"]:
            nr, nc = row + dr, col + dc
            if board.inside(nr, nc):
                target = board.at(nr, nc)
                if target is None or target.owner != piece.owner:
                    moves.append((nr, nc))
    if "walks" in spec:
        moves += _walk_moves(board, row, col, piece, spec["walks"])
    if "cannons" in spec:
        moves += _cannon_moves(board, row, col, piece, spec["cannons"])
    return moves


def generate_moves(board: Board, row: int, col: int, piece: Piece) -> List[Tuple[int, int]]:
    """Everywhere this piece may legally end its turn, ignoring whether
    doing so exposes its own General (use legal_moves for that)."""
    moves = _base_moves(board, row, col, piece)
    seen = set()
    unique = []
    for move in moves:
        if move not in seen:
            seen.add(move)
            unique.append(move)
    return unique


def _threat_of(board: Board, row: int, col: int, piece: Piece) -> List[Tuple[int, int]]:
    """
    Where this piece could CAPTURE, which is not always where it can move.

    The Cannon is why. It slides freely along an empty line but cannot
    take anything there; it covers only what lies beyond a screen.
    """
    spec = move_spec(piece)
    threats: List[Tuple[int, int]] = []
    if "slides" in spec:
        threats += _slide_moves(board, row, col, piece, spec["slides"], BOARD_SIZE - 1)
    if "steps" in spec:
        threats += _slide_moves(board, row, col, piece, spec["steps"], 1)
    if "leaps" in spec:
        for dr, dc in spec["leaps"]:
            nr, nc = row + dr, col + dc
            if board.inside(nr, nc):
                target = board.at(nr, nc)
                if target is None or target.owner != piece.owner:
                    threats.append((nr, nc))
    if "walks" in spec:
        threats += _walk_moves(board, row, col, piece, spec["walks"])
    if "cannons" in spec:
        threats += _hop_moves(board, row, col, piece, spec["cannons"])
    return threats


def _army_covers(board: Board, row: int, col: int, owner: str) -> bool:
    """Does any NON-royal piece of `owner` cover this square? Stops at the
    first one that does - the whole-set version below is only built when
    something genuinely needs the entire map."""
    for r, c, piece in board.pieces(owner):
        if piece.name == ROYAL:
            continue
        if (row, col) in _threat_of(board, r, c, piece):
            return True
    return False


def _army_threats(board: Board, owner: str) -> set:
    """Every square this side's NON-royal pieces cover.

    Kept separate from the General because the General's threat depends on
    what the enemy army covers, and the enemy army's threat doesn't depend
    on anything - so splitting them is what lets the two Generals be
    resolved without infinite recursion.
    """
    hits = set()
    for r, c, piece in board.pieces(owner):
        if piece.name != ROYAL:
            hits.update(_threat_of(board, r, c, piece))
    return hits


def _general_reach(board: Board, row: int, col: int, general: Piece) -> set:
    """The squares beside this General that he could step to."""
    reach = set()
    for dr, dc in ALL_DIRS:
        square = (row + dr, col + dc)
        if board.inside(*square):
            occupant = board.at(*square)
            if occupant is None or occupant.owner != general.owner:
                reach.add(square)
    return reach


def attacked(board: Board, row: int, col: int, by_owner: str) -> bool:
    """Is this square covered by `by_owner`?

    Answered piece by piece with an early exit rather than by building the
    whole threat map, because this runs inside the AI's search and the map
    is expensive. The General is only consulted when it is close enough to
    matter, which it almost never is.
    """
    if _army_covers(board, row, col, by_owner):
        return True
    seat = board.royal_pos(by_owner)
    if seat is None:
        return False
    if hex_distance(seat, (row, col)) > 1:
        return False
    return (row, col) in _general_reach(board, seat[0], seat[1], board.at(*seat))


def _guarded_by_army(board: Board, row: int, col: int, owner: str) -> bool:
    """Would this side recapture on the square with something OTHER than
    its General?

    Tested by standing an enemy dummy there, because a piece never lists a
    square held by its own side as a move. The General is excluded on
    purpose: when the question is "can the enemy General take mine here",
    my own General is the victim, not a defender.
    """
    occupant = board.grid[row][col]
    board.grid[row][col] = Piece(other_owner(owner), "Pawn")
    try:
        for r, c, piece in board.pieces(owner):
            if piece.name == ROYAL or (r, c) == (row, col):
                continue
            if (row, col) in _threat_of(board, r, c, piece):
                return True
        return False
    finally:
        board.grid[row][col] = occupant


def royal_in_check(board: Board, owner: str) -> bool:
    """
    Is this side's General attacked?

    The enemy army is simple - if anything covers the square, it's check.
    The enemy GENERAL is the interesting case, and it is where Charge
    parts company with chess.

    Chess forbids two kings from ever touching, which is really a
    shorthand: a king may not move to a square the other king covers.
    Charge asks the honest question instead - could that General ACTUALLY
    capture here? It could not, if the square is guarded by one of our
    other pieces, because taking would walk it onto a defended square.

    So two Generals may stand shoulder to shoulder in Charge, provided
    the one that moved in is protected. That turns a defended approach
    into a real mating weapon rather than an illegal move.
    """
    seat = board.royal_pos(owner)
    if seat is None:
        return False
    enemy = other_owner(owner)
    if _army_covers(board, seat[0], seat[1], enemy):
        return True

    enemy_seat = board.royal_pos(enemy)
    if enemy_seat is None:
        return False
    if GENERALS_CANT_TOUCH:
        # The chess rule: never mind whether he could actually be taken,
        # the Generals simply may not be neighbours.
        if hex_distance(enemy_seat, seat) <= 1:
            return True
    # Two Generals can only bear on each other when they touch.
    if hex_distance(enemy_seat, seat) > 1:
        return False
    return not _guarded_by_army(board, seat[0], seat[1], owner)


def captures_of(board: Board, src: Tuple[int, int], dst: Tuple[int, int],
                piece: Piece) -> List[Tuple[int, int]]:
    """Which squares a move takes pieces from. At most one here; the list
    exists so Ai.py can share code with variants that capture several."""
    victim = board.at(*dst)
    if victim is None or victim.owner == piece.owner:
        return []
    return [dst]


def apply_move(board: Board, src: Tuple[int, int], dst: Tuple[int, int]) -> None:
    """Moves a piece, clearing anything it captures on the way. No rule
    checking and no bookkeeping."""
    piece = board.at(*src)
    if piece is None:
        return
    for square in captures_of(board, src, dst, piece):
        board.set(square[0], square[1], None)
    board.set(src[0], src[1], None)
    board.set(dst[0], dst[1], piece)


def legal_moves(board: Board, row: int, col: int, piece: Piece) -> List[Tuple[int, int]]:
    """Moves that don't leave your own General in check."""
    legal = []
    for dst in generate_moves(board, row, col, piece):
        trial = board.clone()
        apply_move(trial, (row, col), dst)
        if not royal_in_check(trial, piece.owner):
            legal.append(dst)
    return legal


def _screen_between(board: Board, cannon: Tuple[int, int],
                    target: Tuple[int, int]) -> Optional[Tuple[int, int]]:
    """The square a cannon shoots over to reach `target`, or None."""
    dr0, dc0 = target[0] - cannon[0], target[1] - cannon[1]
    if not (dr0 == 0 or dc0 == 0 or dr0 == -dc0):
        return None                      # not on one of his six lines
    dr = (dr0 > 0) - (dr0 < 0)
    dc = (dc0 > 0) - (dc0 < 0)
    r, c = cannon[0] + dr, cannon[1] + dc
    while (r, c) != target and board.inside(r, c):
        if board.at(r, c) is not None:
            return (r, c)
        r, c = r + dr, c + dc
    return None


def mating_pieces(board: Board, loser: str) -> Dict[str, set]:
    """
    Which enemy pieces are responsible for the mate, split into the ones
    giving check and the ones holding the net shut.

    The question is answered exactly, by trying it: for every square the
    General could step to, he is actually PUT there - capturing whatever
    stands on it - and every enemy piece that would then attack him is
    named. That one rule covers all three ways a piece holds the net:

      * it covers an empty square beside him, so he cannot step there;
      * it defends one of its own pieces beside him, so he cannot capture
        his way out - with him standing on that square, the defender is
        simply attacking him;
      * and with cannons, it may be the SCREEN a Cannon shoots
        over. The screen covers nothing itself, but take it away and the
        cannon has no shot, so when it is one of the winner's own pieces
        it is named too.

    This replaced a quicker version that judged each square with its
    ordinary move lists. A piece's moves never include a square its own
    side occupies, so every defender went unnamed - 11 of 13 missing
    pieces across 15 real checkmates - and no screen was ever named.
    """
    found = {"checkers": set(), "support": set()}
    seat = board.royal_pos(loser)
    enemy = other_owner(loser)
    if seat is None:
        return found

    def attackers(position: Board, target, into: set) -> None:
        for r, c, piece in position.pieces(enemy):
            if target not in _threat_of(position, r, c, piece):
                continue
            into.add((r, c))
            if "cannons" in move_spec(piece):
                screen = _screen_between(position, (r, c), target)
                if screen is not None and position.at(*screen).owner == enemy:
                    found["support"].add(screen)

    # Giving check, with him where he stands.
    attackers(board, seat, found["checkers"])

    # Every square he might step to, with him actually standing on it.
    for dr, dc in ALL_DIRS:
        square = (seat[0] + dr, seat[1] + dc)
        if not board.inside(*square):
            continue
        occupant = board.at(*square)
        if occupant is not None and occupant.owner == loser:
            continue                     # his own man is in the way
        trial = board.clone()
        general = trial.at(*seat)
        trial.set(seat[0], seat[1], None)
        trial.set(square[0], square[1], general)
        attackers(trial, square, found["support"])

    found["support"] -= found["checkers"]
    return found


def value_of(piece: Piece) -> int:
    return PIECE_VALUES[piece.name]


# ======================================================================
# Game state
# ======================================================================

class GameState:
    """The whole game as data. Knows nothing about windows or clicks.

    Every action that consumes a turn returns an EVENT describing what
    happened, so a UI can decide what to animate and what to play a
    sound for without the rules caring.

    The game ends three ways:
      * checkmate - the side to move is in check with no legal move, and
        loses;
      * stalemate - the side to move has no legal move but is NOT in
        check: a draw;
      * repetition - the same position, with the same side to move, comes
        round for the third time: a draw.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.board = Board()
        for row, col, owner, name in parse_setup():
            self.board.set(row, col, Piece(owner, name))

        self.turn = "W"
        self.phase = "battle"
        self.winner: Optional[str] = None      # None at the end means a draw
        self.message = "White to move."
        self.last_move: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
        # The game record: one entry per turn, for the move log and the
        # material graph.
        self.history: List[Dict] = []
        # How often each position has been seen, for the repetition draw.
        self.seen: Dict[Tuple, int] = {self.position_key(): 1}
        self.version = 0

    def position_key(self) -> Tuple:
        """Everything that makes two positions the same: every piece on
        its cell, and whose move it is."""
        cells = tuple((r, c, p.owner, p.name) for r, c, p in self.board.pieces())
        return cells, self.turn

    def repetitions(self) -> int:
        """How many times the position on the board has now been seen."""
        return self.seen.get(self.position_key(), 0)

    def snapshot(self) -> "GameState":
        """A detached copy, so the AI can think on a worker thread without
        sharing mutable state with the drawing thread."""
        clone = GameState.__new__(GameState)
        clone.board = self.board.clone()
        clone.turn = self.turn
        clone.phase = self.phase
        clone.winner = self.winner
        clone.message = self.message
        clone.last_move = self.last_move
        clone.version = self.version
        clone.seen = dict(self.seen)
        # The AI never needs the record and copying a growing list into
        # every search would be waste, so a snapshot starts blank.
        clone.history = []
        return clone

    def _record(self, text: str, mover: str, check: bool) -> None:
        self.history.append({
            "text": text,
            "mover": mover,
            "check": check,
            "material": self.material_diff(),
        })

    # --- naming ---------------------------------------------------------

    def player_name(self, owner: Optional[str] = None) -> str:
        owner = self.turn if owner is None else owner
        return "White" if owner == "W" else "Black"

    def square_notation(self, row: int, col: int) -> str:
        return square_name(row, col)

    # --- what can happen this turn ----------------------------------------

    def any_legal_moves(self, owner: str) -> bool:
        for row, col, piece in self.board.pieces(owner):
            if legal_moves(self.board, row, col, piece):
                return True
        return False

    def check_squares(self) -> List[Tuple[int, int]]:
        """Every General in check. Normally only the side to move can be,
        but in a sandbox, where anything goes, both can at once."""
        if self.phase != "battle":
            return []
        sides = ("W", "B") if config.SANDBOX else (self.turn,)
        found = []
        for side in sides:
            royal = self.board.royal_pos(side)
            if royal is not None and royal_in_check(self.board, side):
                found.append(royal)
        return found

    def check_square(self) -> Optional[Tuple[int, int]]:
        if self.phase != "battle":
            return None
        royal = self.board.royal_pos(self.turn)
        if royal is None:
            return None
        return royal if royal_in_check(self.board, self.turn) else None

    def material_diff(self) -> int:
        """White's material minus Black's - the Generals left out, since
        neither side can be without one in a game."""
        def side_total(owner: str) -> int:
            return sum(value_of(p) for _, _, p in self.board.pieces(owner)
                       if p.name != ROYAL)
        return side_total("W") - side_total("B")

    # --- taking a turn -----------------------------------------------------

    def _end_turn(self) -> Dict:
        self.version += 1
        self.turn = other_owner(self.turn)
        in_check = royal_in_check(self.board, self.turn)
        self.message = (f"{self.player_name()} is in check."
                        if in_check else f"{self.player_name()} to move.")
        key = self.position_key()
        self.seen[key] = self.seen.get(key, 0) + 1
        if self.phase == "battle" and not self.any_legal_moves(self.turn):
            self.phase = "gameover"
            if in_check:
                self.winner = self.player_name(other_owner(self.turn))
                self.message = f"Checkmate - {self.winner} wins."
            else:
                self.winner = None
                self.message = (f"Stalemate - {self.player_name()} has no legal move "
                                "but is not in check. A draw.")
        elif self.phase == "battle" and self.seen[key] >= REPETITION_LIMIT:
            self.phase = "gameover"
            self.winner = None
            self.message = "Draw - the same position has come up three times."
        return {"check": in_check, "gameover": self.phase == "gameover"}

    def execute_move(self, src: Tuple[int, int], dst: Tuple[int, int]) -> Optional[Dict]:
        mover_piece = self.board.at(*src)
        if mover_piece is None:
            return None
        mover = mover_piece.owner
        victim = self.board.at(*dst)
        captured = victim is not None and victim.owner != mover

        event = {"kind": "move", "src": src, "dst": dst, "mover": mover,
                 "captured": captured, "check": False, "gameover": False}
        record = (f"{mover_piece.label()} {self.square_notation(*src)}"
                  f"{'x' if captured else '-'}{self.square_notation(*dst)}")

        apply_move(self.board, src, dst)
        if captured and victim.name == ROYAL:
            # Only possible in a sandbox: legal play never leaves a
            # General where he can be taken.
            self.phase = "gameover"
            self.winner = self.player_name(mover)
            self.message = f"{self.winner} wins by taking the General."
            self.version += 1
            event["gameover"] = True
        else:
            event.update(self._end_turn())

        self.last_move = (src, dst)
        self._record(record, mover, event.get("check", False))
        return event

    # --- the sandbox --------------------------------------------------------
    # SANDBOX in config.py: no turns, and pieces go wherever they are put.
    # Nothing here asks whose turn it is or whether the move is legal, and
    # the turn never changes - but capturing works as in a game, and every
    # change still goes in the move log.

    def sandbox_move(self, src: Tuple[int, int], dst: Tuple[int, int]) -> Optional[Dict]:
        """Puts a piece on any empty point, or onto an enemy piece, taking
        it. Refused onto its own side's piece, or onto a General."""
        piece = self.board.at(*src)
        victim = self.board.at(*dst)
        if piece is None or src == dst:
            return None
        if victim is not None and (victim.owner == piece.owner or victim.name == ROYAL):
            return None
        mover = piece.owner
        captured = victim is not None
        event = {"kind": "move", "src": src, "dst": dst, "mover": mover,
                 "captured": captured, "gameover": False}
        record = (f"{piece.label()} {self.square_notation(*src)}"
                  f"{'x' if captured else '-'}{self.square_notation(*dst)}")
        apply_move(self.board, src, dst)
        return self._sandbox_done(event, record, mover, (src, dst))

    def sandbox_place(self, owner: str, name: str, row: int, col: int) -> Optional[Dict]:
        """Puts a new piece from the pool on an empty point. A side may
        have only one General, so his tile places one only when that side
        has none."""
        if not on_board(row, col) or self.board.at(row, col) is not None:
            return None
        if name == ROYAL and self.board.royal_pos(owner) is not None:
            return None
        piece = Piece(owner, name)
        self.board.set(row, col, piece)
        event = {"kind": "place", "mover": owner, "captured": False, "gameover": False}
        record = f"{piece.label()} +{self.square_notation(row, col)}"
        return self._sandbox_done(event, record, owner, ((row, col), (row, col)))

    def sandbox_remove(self, src: Tuple[int, int]) -> Optional[Dict]:
        """Takes a piece off the board altogether - dragged off its edge."""
        piece = self.board.at(*src)
        if piece is None:
            return None
        self.board.set(src[0], src[1], None)
        event = {"kind": "remove", "mover": piece.owner, "captured": False, "gameover": False}
        record = f"{piece.label()} {self.square_notation(*src)} off"
        return self._sandbox_done(event, record, piece.owner, self.last_move)

    def _sandbox_done(self, event: Dict, record: str, mover: str, last) -> Dict:
        enemy = other_owner(mover)
        event["check"] = royal_in_check(self.board, enemy)
        self.version += 1
        self.last_move = last
        self.message = (f"{self.player_name(enemy)} is in check." if event["check"]
                        else "Sandbox - move anything anywhere.")
        self._record(record, mover, event["check"])
        return event
