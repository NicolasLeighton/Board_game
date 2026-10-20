"""
test_engine.py - proves the C++ engine agrees with Rules.py.

The C++ engine restates the rules in a second language, and a second copy
of a rule is the most reliable way to introduce a bug. This script is the
thing that keeps that honest: it builds thousands of random positions,
asks BOTH implementations for the complete list of legal moves, and fails
loudly on the first disagreement.

Then it checks the endings, which the move lists alone can't show: that
both treat a side with no move as mated when in check and stalemated
when not, and that a position coming round for the third time is a draw.

Run it after any change to Rules.py or engine.cpp:

    python3 test_engine.py
"""

import random
import subprocess
import sys

import AiCpp
import Rules as R

ENGINE = "./hexcharge_engine"


# ----------------------------------------------------------------------
# Talking to the engine
# ----------------------------------------------------------------------

class Engine:
    def __init__(self, path=ENGINE):
        self.proc = subprocess.Popen(
            [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)
        # The game's own setup message, from AiCpp.setup_line - the test
        # must check exactly the game that is played, so it never builds
        # its own copy.
        self.send(AiCpp.setup_line())
        assert self.read() == "ok"

    def send(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def read(self):
        return self.proc.stdout.readline().strip()

    def set_position(self, state):
        n = R.BOARD_SIZE
        tokens = ["."] * (n * n)
        for row, col, piece in state.board.pieces():
            tokens[row * n + col] = ("w" if piece.owner == "W" else "b") + piece.name
        self.send(f"position {' '.join(tokens)} | {state.turn}")
        assert self.read() == "ok"

    def moves(self):
        self.send("moves")
        out = set()
        while True:
            line = self.read()
            if line in ("end", ""):
                return out
            parts = line.split()
            out.add((int(parts[2]), int(parts[3])))

    def key(self):
        self.send("key")
        return int(self.read().split()[1])

    def go(self, depth=3, seconds=2.0):
        self.send(f"go depth={depth} seconds={seconds}")
        best, info = self.read(), self.read()
        parts = best.split()
        score = float(info.split()[4])
        move = (int(parts[2]), int(parts[3])) if parts[1] == "move" else None
        return move, score

    def close(self):
        try:
            self.send("quit")
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


# ----------------------------------------------------------------------
# Ground truth from the Python rules
# ----------------------------------------------------------------------

def python_moves(state):
    """Every legal move, straight from Rules.py."""
    n = R.BOARD_SIZE
    out = set()
    for row, col, piece in state.board.pieces(state.turn):
        for dr, dc in R.legal_moves(state.board, row, col, piece):
            out.add((row * n + col, dr * n + dc))
    return out


def self_check_violations(state):
    """Every move the rules call legal that would leave the mover's own
    General in check - which, by definition, no legal move may do.

    This is the one check here that does not depend on either
    implementation being right. Comparing Rules.py with the engine only
    finds places where they DISAGREE; a mistake both share passes that
    comparison untouched.
    """
    owner = state.turn
    bad = []
    for row, col, piece in state.board.pieces(owner):
        for dst in R.legal_moves(state.board, row, col, piece):
            trial = state.board.clone()
            R.apply_move(trial, (row, col), dst)
            if R.royal_in_check(trial, owner):
                bad.append(((row, col), dst))
    return bad


NAMES = [n for n in R.PIECE_NAMES if n != R.ROYAL]


def random_position(rng, density):
    """Two Generals and some pieces, scattered."""
    state = R.GameState()
    state.board = R.Board()
    n = R.BOARD_SIZE
    points = rng.sample([(r, c) for r in range(n) for c in range(n) if R.on_board(r, c)],
                        density + 2)
    state.board.set(*points[0], R.Piece("W", R.ROYAL))
    state.board.set(*points[1], R.Piece("B", R.ROYAL))
    for i, point in enumerate(points[2:]):
        state.board.set(*point, R.Piece("W" if i % 2 else "B", rng.choice(NAMES)))
    state.turn = rng.choice(["W", "B"])
    return state


def describe(state):
    lines = []
    for row in range(R.BOARD_SIZE):
        cells = []
        for col in range(R.BOARD_SIZE):
            piece = state.board.at(row, col)
            if not R.on_board(row, col):
                cells.append(" ")
            else:
                cells.append("." if piece is None else piece.owner.lower() + piece.label())
        lines.append(" ".join(f"{c:>3s}" for c in cells))
    lines.append(f"turn {state.turn}")
    return "\n".join(lines)


def show(move):
    n = R.BOARD_SIZE
    name = lambda sq: R.square_name(sq // n, sq % n)
    return f"{name(move[0])}-{name(move[1])}"


# ----------------------------------------------------------------------
# The endings
# ----------------------------------------------------------------------

def place(spec, turn):
    """A position from {"f1": "wGeneral", ...}."""
    state = R.GameState()
    state.board = R.Board()
    for where, token in spec.items():
        col = R.FILE_LETTERS.index(where[0])
        row, _ = R.cell_at(col, int(where[1:]))
        state.board.set(row, col, R.Piece(token[0].upper(), token[1:]))
    state.turn = turn
    state.seen = {state.position_key(): 1}
    return state


def find_ending(rng, want_check):
    """A position where the side to move has no legal move - checkmate if
    `want_check`, stalemate if not.

    Checkmates turn up quickly among random positions. A stalemate almost
    never does, so that one is built: Black's General alone at the top
    point of the board, White's General two below him and a Chariot up
    each neighbouring file - every point he could step to covered, the one
    he stands on not. It is built from the board's own size, so it works
    whatever BOARD_RADIUS is."""
    if not want_check:
        mid = R.BOARD_RADIUS
        state = R.GameState()
        state.board = R.Board()
        state.board.set(0, mid, R.Piece("B", R.ROYAL))
        state.board.set(2, mid, R.Piece("W", R.ROYAL))
        for col in (mid - 1, mid + 1):
            bottom = max(r for r in range(R.BOARD_SIZE) if R.on_board(r, col))
            state.board.set(bottom, col, R.Piece("W", "Chariot"))
        state.turn = "B"
        return state
    for _ in range(20000):
        state = random_position(rng, rng.choice([4, 6, 8, 10]))
        if (not state.any_legal_moves(state.turn)
                and R.royal_in_check(state.board, state.turn)):
            return state
    return None


def check_endings(engine, rng):
    for want_check, label in ((True, "checkmate"), (False, "stalemate")):
        state = find_ending(rng, want_check)
        if state is None:
            print(f"  (no random {label} found to test - skipped)")
            continue
        engine.set_position(state)
        if engine.moves():
            print(f"\nthe engine finds a move in this {label}:\n{describe(state)}")
            sys.exit(1)
        # The rules' verdict, as a game would reach it: hand the turn over
        # to the side with no move.
        stuck = state.turn
        state.turn = R.other_owner(stuck)
        state._end_turn()
        expected = state.player_name(R.other_owner(stuck)) if want_check else None
        assert state.phase == "gameover" and state.winner == expected, state.message
        print(f"  {label}: \"{state.message}\" - ok")

    # Repetition, in the rules: a Knight out and back twice brings the
    # opening round for the third time, and the game is drawn.
    game = R.GameState()

    def a_knight_move(owner):
        for r, c, piece in game.board.pieces(owner):
            if piece.name == "Knight":
                moves = R.legal_moves(game.board, r, c, piece)
                if moves:
                    return (r, c), moves[0]
    white, black = a_knight_move("W"), a_knight_move("B")
    for _ in range(2):
        for src, dst in (white, black, (white[1], white[0]), (black[1], black[0])):
            game.execute_move(src, dst)
    assert game.phase == "gameover" and game.winner is None, game.message
    print(f"  repetition, rules: \"{game.message}\" - ok")

    # Repetition, in the engine. White is a Chariot up, which it scores as
    # winning. Then it is told that every position White could move to
    # has already happened twice: every move would now be a draw, and the
    # score has to fall to about nothing.
    state = place({"f1": "wGeneral", "f11": "bGeneral", "a1": "wChariot"}, "W")
    engine.set_position(state)
    engine.send("history")
    engine.read()
    _, ahead = engine.go(depth=3)
    keys = []
    for src, dst in [((s // R.BOARD_SIZE, s % R.BOARD_SIZE), (d // R.BOARD_SIZE, d % R.BOARD_SIZE))
                     for s, d in python_moves(state)]:
        after = state.snapshot()
        R.apply_move(after.board, src, dst)
        after.turn = "B"
        engine.set_position(after)
        keys += [str(engine.key())] * 2
    engine.send("history " + " ".join(keys))
    engine.read()
    engine.set_position(state)
    _, repeated = engine.go(depth=3)
    engine.send("history")
    engine.read()
    assert ahead > 300 and abs(repeated) < 100, (ahead, repeated)
    print(f"  repetition, engine: a Chariot up scores {ahead:.0f}; "
          f"with every move a third repetition, {repeated:.0f} - ok")


# ----------------------------------------------------------------------

def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    engine = Engine()
    rng = random.Random(20261017)
    moves_checked = 0

    try:
        opening = R.GameState()
        engine.set_position(opening)
        mine, theirs = python_moves(opening), engine.moves()
        assert mine == theirs, "the opening position already disagrees"
        print(f"opening position: {len(mine)} legal moves, both agree")

        for _ in range(rounds):
            state = random_position(rng, rng.choice([2, 4, 6, 10, 16, 24, 32]))
            engine.set_position(state)
            mine, theirs = python_moves(state), engine.moves()
            wrong = self_check_violations(state)
            if wrong:
                print("\nA LEGAL MOVE LEAVES ITS OWN GENERAL IN CHECK:\n")
                print(describe(state))
                print("\n ", wrong[:8])
                sys.exit(1)
            moves_checked += len(mine)
            if mine != theirs:
                print("\nDISAGREEMENT on this position:\n")
                print(describe(state))
                only_python = sorted(show(m) for m in mine - theirs)
                only_cpp = sorted(show(m) for m in theirs - mine)
                if only_python:
                    print("\n  Rules.py allows, engine does not:", only_python[:12])
                if only_cpp:
                    print("\n  engine allows, Rules.py does not:", only_cpp[:12])
                sys.exit(1)
        print(f"{rounds} random positions, {moves_checked} legal moves: identical")
        print("and no legal move leaves its own General in check")

        print("endings:")
        check_endings(engine, rng)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
