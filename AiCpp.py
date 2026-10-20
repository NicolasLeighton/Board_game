"""
AiCpp.py - drives the C++ engine from the Python game.

The engine is a separate program (engine.cpp, built to ./hexcharge_engine)
that we talk to over a pipe.

    ai = AiCpp.make_ai("B", difficulty_index)
    action = ai.choose_move(state)

Build the engine first:

    g++ -O2 -std=c++17 -o hexcharge_engine engine.cpp

This build has no Python opponent to fall back on: if the engine will
not start, the game says so plainly and stops. That is deliberate -
silently substituting a different, weaker opponent would be a worse
outcome than a clear error.

Everything is sent to the engine at startup - the rules from config.py,
how to play from ai_config.py - so nothing about the game is compiled
into it.
"""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Dict, Optional, Tuple

import ai_config
import config
import Rules as R

# The difficulty table lives in ai_config.py; these names are kept here
# because the menu reads them as AiCpp.DIFFICULTIES.
DIFFICULTIES = ai_config.DIFFICULTIES
DEFAULT_DIFFICULTY = ai_config.DEFAULT_DIFFICULTY

ENGINE_NAME = "hexcharge_engine.exe" if os.name == "nt" else "hexcharge_engine"
ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ENGINE_NAME)



def setup_line(tuning: Optional[Dict] = None) -> str:
    """The one message that tells the engine everything: the rules from
    config.py, and how to play from ai_config.py. Nothing about the game
    is compiled into the engine, so changing either file changes it.

    test_engine.py uses this same function. It used to build its own copy
    of the message, which meant every new setting had to be added in two
    places - and forgetting one would have left the test quietly checking
    a slightly different game from the one being played.
    """
    bits = [
        "setup",
        f"size={R.BOARD_SIZE}",
        f"canttouch={int(config.GENERALS_CANT_TOUCH)}",
        f"flat={int(R.FLAT)}",
    ]
    # What the pieces are worth.
    for name, value in ai_config.PIECE_VALUES.items():
        bits.append(f"{name}={value}")
    # What it is rewarded for.
    for key, value in ai_config.ENGINE_STYLE.items():
        bits.append(f"style_{key}={value}")
    # The rank Pawns start on, read off the setup rather than assumed.
    pawn_ranks = [i for i, line in enumerate(R.SETUP) if "Pw" in line.split()]
    bits.append(f"style_pawn_home={max(pawn_ranks) if pawn_ranks else 2}")
    for name, value in ai_config.PIECE_ACTIVITY.items():
        bits.append(f"activity_{name}={value}")
    # The finer weights.
    for key, value in ai_config.ENGINE_WEIGHTS.items():
        bits.append(f"weight_{key}={value}")
    # Whatever makes this difficulty what it is.
    for key, value in (tuning or {}).items():
        bits.append(f"{key}={value}")
    # Where to report each search - see ENGINE_LOG in ai_config.py. Paths
    # with spaces cannot travel in this message, so those go unlogged.
    if getattr(ai_config, "ENGINE_LOG", False) and tuning:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            ai_config.ENGINE_LOG_FILE)
        if " " not in path:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                bits.append(f"log={path}")
            except OSError:
                pass
    return " ".join(bits)


class EngineError(RuntimeError):
    pass


def inspect_engine(path: str = ENGINE_PATH) -> Optional[str]:
    """
    Looks at the file and says what is wrong with it, or None if it looks
    runnable here.

    Worth doing before trying to launch it, because the operating system's
    own complaint is unhelpful. Windows answers a Linux binary with
    "WinError 216: this version of %1 is not compatible with the version
    of Windows you are running", which sounds like an architecture problem
    and is really "that is not a Windows program at all".

    The first bytes of a binary say which system it was built for:
    Windows programs start with "MZ", Linux ones with 0x7F E L F, macOS
    with a Mach-O magic number.
    """
    if not os.path.exists(path):
        return (f"the engine is not built.\n"
                f"  expected: {path}\n"
                f"  build it: g++ -O2 -std=c++17 -o {ENGINE_NAME} engine.cpp")
    try:
        with open(path, "rb") as handle:
            head = handle.read(4)
    except OSError as problem:
        return f"cannot read {path}: {problem}"

    if len(head) < 4:
        return f"{path} is empty or truncated - rebuild it."

    windows = head[:2] == b"MZ"
    linux = head[:4] == b"\x7fELF"
    macos = head[:4] in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe",
                         b"\xca\xfe\xba\xbe")

    if os.name == "nt" and not windows:
        built_for = ("Linux" if linux else "macOS" if macos else "something else")
        return (f"{os.path.basename(path)} is not a Windows program - it was "
                f"built for {built_for}.\n"
                f"  A binary cannot be moved between systems; it has to be\n"
                f"  compiled on the machine that will run it. Delete this file\n"
                f"  and build it here:\n"
                f"    g++ -O2 -std=c++17 -o {ENGINE_NAME} engine.cpp\n"
                f"  On Windows the usual way to get g++ is MSYS2 (msys2.org),\n"
                f"  then 'pacman -S mingw-w64-ucrt-x86_64-gcc'.")
    if os.name != "nt" and windows:
        return (f"{os.path.basename(path)} is a Windows program, but this is "
                f"not Windows.\n"
                f"  Rebuild it here: g++ -O2 -std=c++17 -o {ENGINE_NAME} engine.cpp")
    return None


class Engine:
    """One engine process. Not safe to call from two threads at once, so
    every request holds a lock - the background thinker only ever makes
    one request at a time anyway."""

    def __init__(self, path: str = ENGINE_PATH, tuning: Optional[Dict] = None) -> None:
        self.tuning = tuning or {}
        problem = inspect_engine(path)
        if problem is not None:
            raise EngineError(problem)
        try:
            self.proc = subprocess.Popen(
                [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                text=True, bufsize=1)
        except OSError as failure:
            # The file looked right but the system still refused it.
            raise EngineError(
                f"could not start {os.path.basename(path)}: {failure}\n"
                f"  Rebuild it: g++ -O2 -std=c++17 -o {ENGINE_NAME} engine.cpp")
        self.lock = threading.Lock()
        self.keys: Dict = {}             # position -> the engine's key for it
        self._setup()

    # --- plumbing ------------------------------------------------------

    def _write(self, line: str) -> None:
        if self.proc.poll() is not None:
            raise EngineError("engine has exited")
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _read(self) -> str:
        line = self.proc.stdout.readline()
        if not line:
            raise EngineError("engine closed the pipe")
        return line.strip()

    def _setup(self) -> None:
        """Hand the engine the whole game - see setup_line."""
        with self.lock:
            self._write(setup_line(self.tuning))
            if self._read() != "ok":
                raise EngineError("engine rejected the setup")

    # --- the game ------------------------------------------------------

    def _send_cells(self, cells, turn: str) -> None:
        """Puts a position on the engine's board: `cells` is every piece
        as (row, col, owner, name)."""
        size = R.BOARD_SIZE
        tokens = ["."] * (size * size)
        for row, col, owner, name in cells:
            tokens[row * size + col] = ("w" if owner == "W" else "b") + name
        self._write(f"position {' '.join(tokens)} | {turn}")
        if self._read() != "ok":
            raise EngineError("engine rejected the position")

    def _key_of(self, position) -> int:
        """The engine's key for a position, as GameState.position_key
        gives it - asked once per position, then remembered."""
        if position not in self.keys:
            cells, turn = position
            self._send_cells(cells, turn)
            self._write("key")
            self.keys[position] = int(self._read().split()[1])
        return self.keys[position]

    def _send_history(self, state) -> None:
        """Every position the game has been through, so the search knows
        which moves would bring one round for the third time. The current
        position is counted once fewer: the search counts it itself."""
        here = state.position_key()
        keys = []
        for position, count in state.seen.items():
            if position == here:
                count -= 1
            keys += [str(self._key_of(position))] * max(0, count)
        self._write("history " + " ".join(keys))
        self._read()

    def best_action(self, state, depth: int, seconds: float) -> Tuple[Optional[Dict], str]:
        size = R.BOARD_SIZE
        with self.lock:
            self._send_history(state)
            cells, turn = state.position_key()
            self._send_cells(cells, turn)
            self._write(f"go depth={depth} seconds={seconds} ply={len(state.history)}")
            best = self._read()
            info = self._read()

        parts = best.split()
        if len(parts) < 4 or parts[1] != "move":
            return None, info
        src, dst = int(parts[2]), int(parts[3])
        return ({"type": "move",
                 "src": (src // size, src % size),
                 "dst": (dst // size, dst % size)}, info)

    def close(self) -> None:
        """Stops the engine, without waiting for a search in flight.

        Asking politely means writing "quit" down the pipe, and that needs
        the lock - which the thinking thread holds for the WHOLE of its
        search. Waiting for it froze the main thread for as long as the
        engine had left to think: nearly twelve seconds at the top
        difficulty, during which the window stopped redrawing and looked
        to the operating system like a hung program.

        So: try for the lock briefly, and if a search has it, kill the
        process instead. It is a child we are discarding and there is
        nothing in it worth saving.
        """
        got_lock = self.lock.acquire(timeout=0.2)
        try:
            if got_lock:
                try:
                    self._write("quit")
                except Exception:
                    pass
        finally:
            if got_lock:
                self.lock.release()
        try:
            self.proc.wait(timeout=1 if got_lock else 0)
        except Exception:
            pass
        if self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass


class CppPlayer:
    """The computer opponent: one engine process, at one difficulty."""

    def __init__(self, owner: str, lookahead: int, time_budget: float,
                 engine: Optional[Engine] = None,
                 tuning: Optional[Dict] = None) -> None:
        self.owner = owner
        self.lookahead = lookahead
        self.time_budget = time_budget
        self.engine = engine or Engine(tuning=tuning)
        self.last_info = ""

    def choose_move(self, state) -> Optional[Dict]:
        action, info = self.engine.best_action(state, self.lookahead, self.time_budget)
        self.last_info = info
        return action

    def close(self) -> None:
        self.engine.close()


def available() -> bool:
    """True only if the engine is present AND looks runnable on this
    system - a binary from another machine does not count."""
    return inspect_engine() is None


def make_ai(owner: str, difficulty_index: int) -> "CppPlayer":
    """Builds the opponent. Raises EngineError if the engine won't run."""
    level = DIFFICULTIES[max(0, min(difficulty_index, len(DIFFICULTIES) - 1))]
    _name, depth, budget, branching, qply, noise, window = level
    tuning = {"branching": branching, "qply": qply,
              "noise": noise, "window": window, "level": _name}
    return CppPlayer(owner, depth, budget, tuning=tuning)


def require_engine() -> None:
    """Checked once at startup, so a bad build is a clear message on the
    way in rather than a traceback out of subprocess."""
    problem = inspect_engine()
    if problem is not None:
        raise EngineError(problem)
    probe = Engine()                 # proves it starts and accepts the rules
    probe.close()
