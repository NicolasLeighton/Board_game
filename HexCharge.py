"""
HEX CHARGE - run this file to play.

    python HexCharge.py

The game is split across four modules:

    Rules.py    how the game is played: board, pieces, movement,
                and the GameState that tracks a match.
                Imports no pygame - this is the file to edit when you
                want to tune the game.
    AiCpp.py    drives the compiled C++ opponent (see BUILD.md).
    Ui.py       everything drawn and clicked: artwork, sound, the menu
                and the board view.
    HexCharge.py this file: opens the window, runs the menu, then runs
                the match loop.

Controls
    left click      select and move, or drag a piece where it goes
    right click     mark a square; drag between squares to draw an arrow
    C               clear selection          X   clear your marks
    M               mute sound               R   new game
    F11             fullscreen               Esc quit

The window can be resized freely; the board, pieces and text all scale
with it.
"""

from __future__ import annotations

import datetime
import os
import random
import subprocess
import sys
import threading
import traceback
from typing import Optional

import pygame

import AiCpp
import Ui
import config
import config_screen
from Rules import GameState, legal_moves


class BackgroundOpponent:
    """
    Runs the AI on a worker thread so the window never stops responding.

    The search can take seconds, and calling it straight from the frame
    loop froze everything - no redraw, no arrows, not even a window drag.
    Here the main thread only ever does two cheap things: hand the worker
    a private snapshot of the position, and later collect the answer.

    Two details make it safe:

      * The worker is given a SNAPSHOT, not the live GameState, so there
        is nothing shared to race over. The answer is applied back on the
        main thread, which is the only thread that ever edits the game.
      * Every job carries a generation number. Restarting or quitting
        bumps it, so an answer that arrives from an abandoned game is
        recognised as stale and dropped instead of being played onto a
        position it was never computed for.
    """

    def __init__(self, ai) -> None:
        self.ai = ai
        self._thread: Optional[threading.Thread] = None
        self._result = None
        self._lock = threading.Lock()
        self._generation = 0

    @property
    def owner(self) -> str:
        return self.ai.owner

    @property
    def thinking(self) -> bool:
        with self._lock:
            pending = self._result is not None
        return not pending and self._thread is not None and self._thread.is_alive()

    def start(self, state) -> None:
        """Begins thinking about `state`. Does nothing if already busy or
        if an answer is sitting there waiting to be collected."""
        with self._lock:
            if self._result is not None:
                return
        if self._thread is not None and self._thread.is_alive():
            return

        snapshot = state.snapshot()
        generation = self._generation

        def work():
            try:
                payload = ("move", self.ai.choose_move(snapshot))
            except Exception:
                payload = ("error", traceback.format_exc())
            with self._lock:
                if generation == self._generation:
                    self._result = payload

        self._thread = threading.Thread(target=work, daemon=True,
                                        name=f"charge-ai-{self.owner}")
        self._thread.start()

    def take(self):
        """Collects a finished answer, or None if it isn't ready."""
        with self._lock:
            result, self._result = self._result, None
        if result is not None:
            self._thread = None
        return result

    def abandon(self) -> None:
        """Forgets the current job. The thread is left to finish and exit
        on its own - it's a daemon, and its answer will be discarded."""
        with self._lock:
            self._generation += 1
            self._result = None
        self._thread = None

    def shutdown(self) -> None:
        """Stops the engine process. Called when a match ends, so a long
        session doesn't leave a trail of engines running."""
        closer = getattr(self.ai, "close", None)
        if closer is not None:
            closer()


class Window:
    """
    Owns the display surface and the sizes derived from it.

    The window is resizable and can go fullscreen, so the layout and the
    fonts are not constants - they are rebuilt from the current surface
    every time it changes shape. Anything that draws asks the Window for
    the current layout rather than caching one.
    """

    def __init__(self, size=(1024, 780)) -> None:
        self.windowed_size = size
        self.fullscreen = False
        self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.rebuild()

    def rebuild(self) -> None:
        width, height = self.surface.get_size()
        self.layout = Ui.Layout(width, height)
        self.fonts = Ui.Fonts(self.layout)
        Ui.clear_piece_cache()

    def resized(self, width: int, height: int) -> None:
        width = max(Ui.MIN_WINDOW[0], width)
        height = max(Ui.MIN_WINDOW[1], height)
        if not self.fullscreen:
            self.windowed_size = (width, height)
        self.surface = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        self.rebuild()

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.surface = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.surface = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.rebuild()


def difficulty_menu_entries():
    blurbs = ["glances one move ahead and often picks a worse one",
              "sees your reply, but still misjudges",
              "steady - punishes a loose piece",
              "looks several moves ahead",
              "everything it has, and it will take its time"]
    return [(level[0], blurbs[i] if i < len(blurbs) else f"depth {level[1]}")
            for i, level in enumerate(AiCpp.DIFFICULTIES)]


def run_menu(window: "Window", clock):
    """Shows the opening screen until a game is started. Returns the chosen
    config, or None if the player quit."""
    menu = Ui.Menu(window.layout, window.fonts)
    menu.difficulty = AiCpp.DEFAULT_DIFFICULTY
    options = difficulty_menu_entries()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                if event.key == pygame.K_F11:
                    window.toggle_fullscreen()
                    menu.resize(window.layout, window.fonts)
            if event.type == pygame.VIDEORESIZE:
                window.resized(event.w, event.h)
                menu.resize(window.layout, window.fonts)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                chosen = menu.handle_click(event.pos)
                if chosen is not None and chosen["mode"] == "config":
                    if run_config(window, clock) == "restart":
                        restart()
                    menu.resize(window.layout, window.fonts)
                elif chosen is not None:
                    return chosen
        menu.draw(window.surface, options)
        pygame.display.flip()
        clock.tick(60)


def run_config(window: "Window", clock) -> Optional[str]:
    """The Config screen, until it is left. Returns "restart" after a
    save, "back" otherwise - and None if the window was closed."""
    screen = config_screen.ConfigScreen(window.layout, window.fonts)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if screen.page == "opening":
                        screen.page = "settings"
                    else:
                        return "back"
                if event.key == pygame.K_F11:
                    window.toggle_fullscreen()
                    screen.resize(window.layout, window.fonts)
            if event.type == pygame.VIDEORESIZE:
                window.resized(event.w, event.h)
                screen.resize(window.layout, window.fonts)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                result = screen.handle_click(event.pos, event.button)
                if result is not None:
                    return result
        screen.draw(window.surface)
        pygame.display.flip()
        clock.tick(60)


def restart() -> None:
    """Starts the game afresh, so every module - and the engine - reads
    the config.py that was just saved. A new process rather than
    re-importing, because the rules are read once, at import, all over
    the code."""
    pygame.quit()
    subprocess.Popen([sys.executable, os.path.abspath(__file__)] + sys.argv[1:],
                     cwd=os.path.dirname(os.path.abspath(__file__)))
    sys.exit(0)


def build_match(window: "Window", setup):
    """Sets up a fresh GameState, a view, and whichever sides the computer
    is playing - returned as {owner: player}, which is empty for a game
    between two people and holds both sides when the computer plays
    itself."""
    state = GameState()

    if config.SANDBOX:
        # Display mode: no opponent and no turns, whatever the menu said.
        state.message = "Sandbox - move anything anywhere."
        view = Ui.GameView(window.layout, window.fonts, state, human_sides=("W", "B"))
        return state, view, {}

    if setup["mode"] == "human":
        # One person drives both armies, so the view accepts input for both.
        view = Ui.GameView(window.layout, window.fonts, state, human_sides=("W", "B"))
        return state, view, {}

    if setup["mode"] == "watch":
        # Nobody is playing, so the view takes no input at all. Both sides
        # get their own engine: one process cannot be asked for two
        # positions at once.
        view = Ui.GameView(window.layout, window.fonts, state, human_sides=())
        return state, view, {owner: AiCpp.make_ai(owner, setup["difficulty"])
                             for owner in ("W", "B")}

    side = setup.get("side", "W")
    if side == "random":
        side = random.choice(["W", "B"])
    view = Ui.GameView(window.layout, window.fonts, state, human_sides=(side,))
    computer = "W" if side == "B" else "B"
    return state, view, {computer: AiCpp.make_ai(computer, setup["difficulty"])}


def fallback_action(state):
    """Any legal action, used if the engine hands back something the
    position no longer allows. Better a plain move than a crash.

    Built from Rules.py rather than from any search, so it stays correct
    without this file needing an opponent of its own.
    """
    for row, col, piece in state.board.pieces(state.turn):
        moves = legal_moves(state.board, row, col, piece)
        if moves:
            return {"type": "move", "src": (row, col), "dst": moves[0]}
    return None


def apply_ai_action(state, view, action) -> None:
    """Plays the AI's chosen action on the main thread."""
    owner = state.turn
    event = None
    if action is not None:
        # execute_move does NOT check legality - it simply moves the piece.
        # So the rules get the final say here, every time. The engine holds
        # its own copy of the rules, and if the two ever disagree this is
        # the only thing standing between that and a piece moving in a way
        # the game does not allow.
        src_square, dst_square = action["src"], action["dst"]
        mover = state.board.at(*src_square)
        allowed = (mover is not None and mover.owner == owner
                   and dst_square in legal_moves(state.board, *src_square, mover))
        if allowed:
            event = state.execute_move(src_square, dst_square)
        else:
            what = mover.name if mover is not None else "nothing"
            print(f"[Hex Charge] the engine proposed an illegal move: {what} "
                  f"{state.square_notation(*src_square)}-"
                  f"{state.square_notation(*dst_square)} - refused.")
            print("[Hex Charge] the usual cause is a stale binary. Rebuild it:")
            print("[Hex Charge]   g++ -O2 -std=c++17 -o hexcharge_engine engine.cpp")
            print("[Hex Charge] then check the two agree: python3 test_engine.py 200")

    if event is None:
        # No move, or one the rules rejected. The game already ends itself
        # when a side has no legal move, so this shouldn't happen - but
        # never wedge the game on it.
        spare = fallback_action(state)
        if spare is not None:
            apply_ai_action(state, view, spare)
        return
    view.on_event(event)


def play_premove(state, view) -> None:
    """Plays the move queued while the computer was thinking, if it is
    still legal.

    A premove is a guess about a position that did not exist yet, so most
    of the work here is deciding it can no longer be played: the piece
    moved or was taken, the square is occupied now, the move would leave
    the General in check. In any of those cases it is dropped without
    fuss - announcing it would be noise, since the player can see their
    move did not happen.
    """
    if view.animation is not None:
        return
    if state.phase != "battle" or not view.controls(state.turn):
        return
    if view.premove is None:
        # Perhaps a piece was picked with nowhere chosen for it yet: that
        # turns into an ordinary selection now that it is your move.
        view.take_up_pending_selection()
        return

    action, owner = view.premove, state.turn
    view.clear_premove()

    src, dst = action["src"], action["dst"]
    mover = state.board.at(*src)
    if mover is None or mover.owner != owner:
        return
    if dst not in legal_moves(state.board, *src, mover):
        return
    view.on_event(state.execute_move(src, dst))


def ai_progress(state, view, opponents) -> None:
    """
    Nudges the computer's turn along without ever blocking the frame.

    Thinking STARTS as soon as it's the computer's turn, including while
    the previous move is still animating - that hides a good chunk of the
    wait behind the animation. The answer is only applied once the board
    has settled.
    """
    if state.phase == "gameover":
        return
    opponent = opponents.get(state.turn)
    if opponent is None:
        return

    opponent.start(state)

    if view.animation is not None:
        return                      # think now, play once the board is still

    result = opponent.take()
    if result is None:
        return

    kind, payload = result
    if kind == "error":
        # Surface it instead of freezing, and keep the game playable.
        print("The AI raised an exception:\n" + payload, file=sys.stderr)
        state.message = "The computer hit an error - playing a fallback move."
        apply_ai_action(state, view, fallback_action(state))
        return

    apply_ai_action(state, view, payload)


def write_game_log(state) -> Optional[str]:
    """
    Saves the finished game as a plain text file: the rules it was played
    under, every move, and the material after each one.

    Deliberately dull and greppable rather than a replay format - the
    point is that when something strange happens you can read the game
    back and find the move where it went wrong.
    """
    if not getattr(config, "SAVE_GAME_LOGS", False) or not state.history:
        return None
    # An unfinished game is still worth keeping - it just says so.
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          getattr(config, "GAME_LOG_FOLDER", "logs"))
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(folder, f"hexcharge-{stamp}.txt")

    lines = ["HEX CHARGE game log",
             f"saved {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
             "",
             "rules",
             f"  board                 hexagon, radius {config.BOARD_RADIUS}",
             f"  generals cant touch   {config.GENERALS_CANT_TOUCH}",
             "",
             "moves                              material (+ is White)",
             ""]
    turn = 0
    for index in range(0, len(state.history), 2):
        turn += 1
        white = state.history[index]
        black = state.history[index + 1] if index + 1 < len(state.history) else None
        left = f"{turn:3d}. {white['text']:<14s}"
        right = f"{black['text']:<14s}" if black else " " * 14
        after = (black or white)["material"]
        flags = "".join(("+" if e and e["check"] else " ") for e in (white, black))
        lines.append(f"{left} {right}  {after:+6d}  {flags}")

    lines += ["", f"result: {state.message.strip()}"]
    if state.winner:
        lines.append(f"winner: {state.winner}")
    elif state.phase == "gameover":
        lines.append("winner: none - a draw")
    else:
        lines.append("winner: none - game left unfinished")
    lines.append(f"turns:  {len(state.history)}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


# What play() hands back when a match ends.
AGAIN = "again"     # R - straight into another game with the same setup
MENU = "menu"       # the Menu button, or Esc - back to the opening screen
QUIT = "quit"       # the window was closed


def play(window: "Window", clock, config) -> str:
    """Runs one match. Returns AGAIN, MENU or QUIT."""
    state, view, players = build_match(window, config)
    opponents = {owner: BackgroundOpponent(ai) for owner, ai in players.items()}
    saved = {"done": False}

    def finish(result: str) -> str:
        """Leaves the match: stop the AI thinking and keep the record.

        The log is written on the way out as well as at checkmate, because
        the games worth troubleshooting are usually the ones you abandon
        BECAUSE something looked wrong - and those never reach an ending.
        """
        for thinker in opponents.values():
            thinker.abandon()
            thinker.shutdown()
        if not saved["done"]:
            saved["done"] = True
            path = write_game_log(state)
            if path:
                print(f"game log written to {path}")
        return result

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return finish(QUIT)
            if event.type == pygame.KEYDOWN:
                # Esc backs out one level - to the menu, not out of the
                # program. Esc again from the menu quits.
                if event.key == pygame.K_ESCAPE:
                    return finish(MENU)
                if event.key == pygame.K_r:
                    return finish(AGAIN)
                if event.key == pygame.K_c:
                    view.clear_selection()
                if event.key == pygame.K_x:
                    view.clear_annotations()
                if event.key == pygame.K_m:
                    view.sound.enabled = not view.sound.enabled
                if event.key == pygame.K_F11:
                    window.toggle_fullscreen()
                    view.resize(window.layout, window.fonts)
            if event.type == pygame.VIDEORESIZE:
                window.resized(event.w, event.h)
                view.resize(window.layout, window.fonts)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                view.left_press(event.pos)
            if event.type == pygame.MOUSEMOTION:
                view.drag_motion(event.pos)
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                view.left_release(event.pos)
            if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                    and view.hit_menu_button(event.pos)):
                return finish(MENU)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                view.scroll_log(1 if event.button == 4 else -1, event.pos)
            if event.type == getattr(pygame, "MOUSEWHEEL", -1):
                view.scroll_log(getattr(event, "y", 0), pygame.mouse.get_pos())
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                view.right_press(event.pos)
            if event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                view.right_release(event.pos)

        view.update_animation()
        play_premove(state, view)
        ai_progress(state, view, opponents)
        view.thinking = any(t.thinking for t in opponents.values())

        # Save the record the moment the game ends, once. Waiting until
        # the player quits would lose the log of anyone who just closes
        # the window on a finished game.
        if state.phase == "gameover" and not saved["done"]:
            saved["done"] = True
            path = write_game_log(state)
            if path:
                print(f"game log written to {path}")

        view.draw(window.surface)
        pygame.display.flip()
        clock.tick(60)


def main() -> None:
    # The AI thread is pure Python, so it holds the interpreter lock while
    # it searches. Shortening the switch interval lets the drawing thread
    # in far more often, which is the difference between a smooth window
    # and a stuttering one while the computer thinks.
    sys.setswitchinterval(0.001)

    try:
        AiCpp.require_engine()
    except AiCpp.EngineError as problem:
        print(f"Hex Charge cannot start: {problem}")
        sys.exit(1)

    pygame.init()
    pygame.display.set_caption("Hex Charge")
    window = Window()
    clock = pygame.time.Clock()

    while True:
        setup = run_menu(window, clock)
        if setup is None:
            break
        outcome = AGAIN
        while outcome == AGAIN:          # R keeps the same setup
            outcome = play(window, clock, setup)
        if outcome == QUIT:
            break
        # MENU falls through and shows the opening screen again.

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
