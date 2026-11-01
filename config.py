"""
config.py - the rules of HEX CHARGE.

Charge on a hexagonal board: a hexagon of hexagons, as in Glinski's hex
chess, with six pieces that all move along the six ORTHOGONAL lines -
there is no diagonal movement anywhere. A captured piece is gone for good,
and nothing promotes.

The game is won by checkmate. It is drawn by stalemate - the side to move
has no legal move but is not in check - or when the same position comes
round for the third time.

Every value below is sent to the C++ engine at startup, so this file is
the only place the rules are defined. Two other files hold the rest:
board_design.py decides how the game LOOKS, and ai_config.py decides how
the computer PLAYS.
"""

# ======================================================================
# Board
# ======================================================================
# Which way the board is turned.
#
#   "point" - a corner of the hexagon at each army's back, as Glinski drew
#             it: the files run straight up the board and the armies face
#             each other point to point. Uses WHITE_SETUP.
#   "flat"  - a flat side of the hexagon at each army's back, so the armies
#             face each other across straight rows. Uses WHITE_SETUP_FLAT.
#
# The board and every move are the same either way; what changes is which
# points are each army's home, and so the opening.
BOARD_ORIENTATION = 'point'

# How many rings of cells surround the centre one. 5 is Glinski's board:
# 91 cells, files a-l (there is no j), the middle file eleven cells long.
# 4 gives 61 cells, 6 gives 127. The setup below must fit: one token per
# file on every rank, so 2 * BOARD_RADIUS + 1 tokens per line.
BOARD_RADIUS = 5


# ======================================================================
# Sandbox
# ======================================================================
# For showing the game rather than playing it. With this on there are no
# turns and no opponent: drag any piece, of either colour, to any empty
# point or onto an enemy piece, whether or not it could move there.
# Clicking a piece still shows where it could legally go. Drag a piece off
# the board to remove it; the side panel holds a pool of every piece for
# both sides, to click or drag onto empty points. A General can't be
# captured, and a side can only have one.
SANDBOX = False


# ======================================================================
# Rule switches
# ======================================================================

# The General is the royal piece - lose him and you lose. True is the
# chess rule: the two Generals may never stand next to each other.
GENERALS_CANT_TOUCH = True

# Draw each piece's movement on the lower half of its tile.
SHOW_MOVEMENT_HINTS = True

# How you move pieces with the left mouse button.
#
#   1 - click or drag, whichever you like
#   2 - click only: click a piece, then click where it goes
#   3 - drag only: pick a piece up and let go where it goes. A click still
#       selects a piece and shows where it can move.
MOVEMENT_TYPE = 3

# Right-click arrows snap to the six lines and the Knight's leaps unless
# this is True.
FREE_ARROWS = False

# Right-click arrows for a Knight's leap bend the way the leap is counted:
# two cells straight out along a line, then one to the side. It is only a
# drawing - the Knight still jumps - but it tells his arrows apart from
# arrows along a line at a glance. False draws them straight.
KNIGHT_ARROW_PATH = True


# ======================================================================
# The pieces
# ======================================================================
# Two-letter codes are what you write in the setup below. Every piece
# moves only along the six orthogonal lines - straight up and down its
# file, and the four lines that cross to the neighbouring files.
#
#   Ch  Chariot    any distance along any of the six lines.
#   Kn  Knight     Glinski's knight: two cells straight on and one turned
#                  60 degrees - twelve cells, jumping anything between.
#   Gu  Guard      one step, or two: the second step may turn, but the
#                  cell he passes through must be empty.
#   Cn  Cannon     the xiangqi cannon on the six lines: slides freely,
#                  but captures only by jumping exactly one piece.
#   Pw  Pawn       one step in any of the six directions, moving and
#                  capturing the same way - the General's move, on a piece
#                  that isn't royal.
#   Ge  General    one step in any of the six directions; the royal piece.

PIECE_CODES = {
    "Ch": "Chariot",
    "Kn": "Knight",
    "Gu": "Guard",
    "Cn": "Cannon",
    "Pw": "Pawn",
    "Ge": "General",
}


# ======================================================================
# The opening position
# ======================================================================
# You lay out YOUR OWN side only; Black gets the same army - see
# MIRRORED_SETUP. One line per rank, the first line rank 1.
#
# WHITE_SETUP is the opening with the point at the back (BOARD_ORIENTATION
# = "point"): one token per file a b c d e f g h i k l. Ranks are counted
# as Glinski counts them: every file starts at 1 on
# White's edge, so rank 1 is a shallow V - a1 at the left corner, down to
# f1 at the bottom, back up to l1. Rank 2 is the V just inside it, and so
# on. Glinski's own army stands in a wedge: nine pieces across rank 1,
# then 3, 3, 2 and 1 narrowing up the middle file.

WHITE_SETUP = [
    #  a  b  c  d  e  f  g  h  i  k  l
    ".  Ch Kn Cn Gu Ge Gu Cn Kn Ch .",
    ".  Pw .  .  .  .  .  .  .  Pw .",
    ".  .  .  Pw .  .  .  Pw .  .  .",
    ".  .  .  .  .  Pw .  .  .  .  .",
]

# The opening with the flat side at the back (BOARD_ORIENTATION = "flat").
# Here the ranks are the board's straight rows, so each line lists that
# row's points left to right: with radius 5, rank 1 has 6 points, rank 2
# has 7, and so on, one more each rank up to the middle.
#
# A wall of nine Pawns, and behind it the pieces, each placed so a Cannon
# never has just one piece in front of it: no first move captures, and
# no first move by White hands Black a capture.
WHITE_SETUP_FLAT = [
    ".  .  .  .  .  .",
    ".  .  .  .  .  .  .",
    ".  .  .  .  .  .  .  .",
    ".  .  .  .  Ge .  .  .  .",
]

# How Black's army is laid out from yours.
#
# False - ROTATED. Black is your setup turned through 180 degrees.
# True  - MIRRORED: reflected across the middle of the board, so matching
#         pieces face each other straight across it.
#
# With a setup that reads the same from either end, the two are identical.
MIRRORED_SETUP = False



# ======================================================================
# Records
# ======================================================================

FLIP_WHEN_BLACK = False
BOARD_FLIP_DELAY_MS = 1000
SAVE_GAME_LOGS = True
GAME_LOG_FOLDER = "logs"
