"""
ai_config.py - how the computer PLAYS Hex Charge.

Everything that shapes the opponent lives here: the difficulty levels,
what it thinks each piece is worth, what it is rewarded for beyond
material, and the finer weights of its judgement. None of it changes a
rule - that is config.py - or how anything looks - that is
board_design.py. AiCpp.py sends all of it to the engine when it starts.

The piece values have a second use: the material graph beside the board
is drawn with them, so the graph and the engine always agree about who
is ahead.

Everything is in centipawns - a Pawn is 100 - unless it says otherwise.
"""


# ======================================================================
# Difficulty
# ======================================================================
# Named difficulties.
#
# Depth alone is a bad dial. Even two plies with a quiescence search never
# hangs a piece and always takes what is hanging, so the weakest setting
# still plays tactically clean - which is exactly what makes it feel
# strong. Four dials move together instead:
#
#   depth / seconds  how far ahead it looks
#   branching        how many moves per position it examines at all. A
#                    narrow search overlooks things, the way a person does
#   qply             plies of capture-only search past the horizon. At 0
#                    it will leave pieces hanging; this is the single
#                    biggest strength lever we have
#   noise            spread, in centipawns, when picking among root moves.
#                    Big noise means it often plays the second or third
#                    best move - mistakes a person recognises
#   window           how far below best a move may be and still be picked.
#                    Keeps even Recruit from throwing its General away
#
# Fields: name, depth, seconds, branching, qply, noise, window
#
# Without drops a position has a few dozen moves instead of hundreds, so
# every level now looks further ahead than it could before. Measured on
# this machine, the strongest settings reach depth 9 in the opening in
# about 12 seconds and depth 6-7 in a busy middlegame in 15; the search
# stops at whichever comes first, the depth or the seconds.
DIFFICULTIES = [
    ("Recruit",  2, 0.20, 10, 0, 400.0,  900.0),
    ("Soldier",  4, 0.60, 20, 2, 150.0,  500.0),
    ("Sergeant", 5, 1.50, 28, 4,  60.0,  300.0),
    ("Captain",  6, 4.00, 44, 6,  20.0,  200.0),
    ("Marshal",  9, 15.0, 64, 8,   0.0,  250.0),
]
DEFAULT_DIFFICULTY = 1


# ======================================================================
# What the pieces are worth
# ======================================================================
PIECE_VALUES = {
    "General": 10000,
    "Chariot": 500,      # six open lines - the strongest piece in the box
    "Cannon": 420,       # strong on a crowded board, weak on an empty one
    "Knight": 300,       # twelve leaps, over anything
    "Guard": 280,        # every cell within two steps, short of range
    "Pawn": 100,
}


# ======================================================================
# What the engine is rewarded for
# ======================================================================
# Material is not everything. These are the things the engine is paid for
# BEYOND the pieces themselves - all in the same units as PIECE_VALUES, so
# a Pawn is 100 and a reward of 10 is a tenth of one.
#
# Every term is scored for both sides and the difference taken, so the
# engine is also paid for stopping YOU doing these things.

ENGINE_STYLE = {
    # Per rank a Pawn has advanced from where it started, up to four. The
    # Pawns on the General's own file and the two beside it earn nothing:
    # they are his roof.
    "pawn_advance": 5,

    # Per piece of his own standing next to the General.
    "general_shelter": 12,

    # Per square next to the General that the enemy covers.
    "general_exposure": 10,
}

# How much each piece is paid per square it can reach - "how much it
# sees". A bishop-like piece stuck behind its own Pawns sees nothing, so
# this is what makes the engine develop it. Pieces not listed earn only
# the engine's small general mobility bonus.
PIECE_ACTIVITY = {
    "Knight": 3,
    "Guard": 2,
    "Cannon": 2,
    "Chariot": 2,
}


# ======================================================================
# The finer weights
# ======================================================================
# The rest of the engine's judgement. These were built into the engine
# until now; the values are the ones it has always used, so changing
# nothing here changes nothing about how it plays.

ENGINE_WEIGHTS = {
    # Per square every piece can move to, whatever the piece. Small on
    # purpose - PIECE_ACTIVITY above is where individual pieces are paid.
    "mobility": 0.7,

    # For giving check, and against being in it.
    "check": 45.0,

    # Once ahead, the engine starts hunting the enemy General instead of
    # banking material forever. The hunt reaches full strength at this
    # much of a lead...
    "hunt_ramp": 400.0,
    # ...then charges for each square the enemy General can still flee to,
    "hunt_escape": 26.0,
    # ...and for how far its own pieces are from him, per square.
    "hunt_distance": 6.0,

    # Charged for going back to a position the game has already been in,
    # so it does not shuffle. A third visit is a draw, which the search
    # sees for itself - this is only the nudge before that.
    "repetition": 55.0,
}


# ======================================================================
# The engine log
# ======================================================================
# With ENGINE_LOG on, the engine writes a report of every search it makes:
# how deep it got and how deep its longest line went, how many positions
# it looked at and how fast, how often its table of searched positions
# answered for it, how well it ordered moves, how much longer each extra
# ply took, and the move it chose at each depth. Searches append to the
# file, games after games; delete it to start afresh.
#
# engine_report.py turns the file into averages per difficulty.

ENGINE_LOG = True

# Where the log goes, relative to the game's folder.
ENGINE_LOG_FILE = "logs/engine_log.txt"

