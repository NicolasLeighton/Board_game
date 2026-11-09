# Hex Charge

A chess-like strategy game on a six-sided board, for two players or
against the computer. The board is a hexagon of points joined by lines,
and every piece moves along the six lines through its point.

---

## What it needs

- **Python 3.9 or newer** - [python.org/downloads](https://www.python.org/downloads/).
  On Windows, tick **"Add python.exe to PATH"** in the installer.
- **pygame** and **numpy** (numpy makes the sounds):

  ```
  pip install pygame numpy
  ```

- **The engine**, the computer opponent, which is written in C++. The game
  won't start without it, even for two players.
  - **Windows:** `hexcharge_engine.exe` is already included. Nothing to do.
  - **Mac or Linux, or after changing `engine.cpp`:** build it with any
    C++17 compiler:

    ```
    g++ -O2 -std=c++17 -o hexcharge_engine engine.cpp
    ```

    On Windows that needs MinGW, and the file must be called
    `hexcharge_engine.exe`. See BUILD.md.

## How to run it

1. Download the code: the green **Code** button on GitHub, then
   **Download ZIP**, and extract it. Or `git clone` it.
2. Open a terminal in that folder. On Windows: open the folder, click the
   address bar, type `cmd` and press Enter.
3. Run:

   ```
   python HexCharge.py
   ```

   On Mac and Linux it may be `python3 HexCharge.py`.

If it says the engine is missing, see **What it needs** above.

---

## How to play

### The menu

| Option | |
|---|---|
| Two players | you and a friend take turns on one computer |
| Play against the computer | choose your side and how strong it is |
| Watch the computer play itself | |
| Free board | no turns, no opponent: move any piece anywhere to try ideas or set up a position. Drag a piece off the board to remove it; the panel on the right has every piece to add |

**How strong?** Recruit (easiest), Soldier, Sergeant, Captain, Marshal
(hardest), or **Custom**, where you set how far it looks ahead, how often
it slips, and how aggressive it is. Every level sees a forced checkmate a
few moves away.

**Config** changes the rules and the board: its size, which way it
faces, and the starting position.

### The pieces

White's pieces are red and moves first; Black's are black. Each piece
shows its name in two letters, and the small drawing under it shows how
it moves. Click a piece to see every point it can reach.

| | Piece | Moves |
|---|---|---|
| Ch | Chariot | any distance along a line |
| Kn | Knight | jumps: two points along a line, then one more turned to the side. It jumps over anything in between |
| Gu | Guard | one or two steps. The second step may turn, but the point in between must be empty |
| Cn | Cannon | slides like a Chariot, but to capture it must jump over exactly one piece, of either colour, to reach its target |
| Pw | Pawn | one step along any line |
| Ge | General | one step along any line. Lose him and you lose |

You capture by moving onto an enemy piece. A captured piece is gone for
good, and nothing promotes.

### Winning

Attacking the enemy General is **check**, and a player must always get
their own General out of check.

- **Checkmate:** the General is in check and has no way out. That side loses.
- **Draw:** a player has no legal move but isn't in check (stalemate), or
  the same position comes up for the third time.

### Controls

| | |
|---|---|
| Left click a piece, then a point | move it. You can also drag it there |
| Click while the computer is thinking | queue your next move |
| Right click / right drag | mark a point / draw an arrow |
| **R** | restart |
| **Esc** | back to the menu |
| **C** / **X** | deselect / clear marks and arrows |
| **M** | sound on or off |
| **F11** | full screen |

---

*The rest of this file is the reference for the rules and every setting.
Hex Charge grew out of Salvo, a square-board game with the xiangqi cannon,
and moved its design onto Gliński's hexagonal board.*

## The board

Points on a hexagonal lattice, `BOARD_RADIUS` rings deep — 5 by
default, Gliński's 91 points. Files run a to l, with no j.

`BOARD_ORIENTATION` turns it two ways. The board and every move are the
same either way; what changes is which points are each army's home, and
so the opening and how ranks are counted:

- **`"point"`** (the default): a corner of the hexagon at each army's back,
  as Gliński drew it. Files run straight up the board, and every file
  counts its own ranks from 1 at White's edge, so rank 1 is a shallow V:
  a1 at the left corner, down to f1 at the bottom, back up to l1. The
  opening is `WHITE_SETUP`.
- **`"flat"`**: a flat side at each army's back, so the armies face each
  other across straight rows. The ranks are those rows, counted up from
  White's edge, and the files are the lines slanting up to the right. The
  opening is `WHITE_SETUP_FLAT`.

---

## The pieces

| | piece | moves |
|---|---|---|
| Ch | Chariot | any distance along any of the six lines |
| Kn | Knight | Gliński's knight: two cells straight on, then one turned 60°. Twelve cells, jumping anything in between |
| Gu | Guard | one step along a line, or two. The second step may turn, but the point he passes through must be empty |
| Cn | Cannon | the xiangqi cannon on the six lines: slides freely, but takes only by jumping exactly one piece |
| Pw | Pawn | one point along any of the six lines, moving and taking the same way: the General's move, on a piece that isn't royal |
| Ge | General | one step along any line; the royal piece |

White's army is red and Black's is black.

### How a game ends

- **Checkmate:** the side to move is in check and has no legal move. They lose.
- **Stalemate:** the side to move has no legal move but is *not* in check.
  A draw.
- **Repetition:** the same position, with the same side to move, comes up
  for the third time. A draw. The panel warns you when the position on the
  board has already come up twice.

### The openings

With the point at the back (`WHITE_SETUP`):

```
#  a  b  c  d  e  f  g  h  i  k  l
".  Pw Ch Kn Cn Ge Cn Kn Ch Pw .",     rank 1
".  .  Pw .  Gu Gu Gu .  Pw .  .",     rank 2
".  .  .  Pw .  .  .  Pw .  .  .",     rank 3
".  .  .  .  Pw .  Pw .  .  .  .",     rank 4
".  .  .  .  .  Pw .  .  .  .  .",     rank 5
```

Gliński's wedge: the nine Pawns in his places, the Chariots and Knights
where his were, and the General on f1 with the three Guards around him.

The Cannons sit behind the Guards on purpose. Every Pawn faces an enemy
Pawn up its file, so a Cannon with only its own Pawn in front would take
the enemy Pawn on the first move. With a Guard between them, the Cannon
has two pieces in front and no shot. No first move by either side can
capture, and the only first move that gives the other side one is f5–f6,
which offers an even Pawn trade.

With the flat side at the back (`WHITE_SETUP_FLAT`), one line per row:

```
"Cn .  .  .  .  Cn",                  rank 1 (6 points)
".  Gu Kn Ge Kn Gu .",                rank 2 (7)
".  Ch .  .  .  .  Ch .",             rank 3 (8)
"Pw Pw Pw Pw Pw Pw Pw Pw Pw",         rank 4 (9)
```

A wall of nine Pawns with the pieces behind it, found by trying every
symmetric arrangement and keeping the one where no first move by either
side can capture and no first move by White gives Black a capture. It has
two Guards rather than three: a row of six points has no middle, so a
symmetric army has room for only one odd-numbered piece, the General.

### Reading a tile

The lower half of each tile is a diagram of how the piece moves:

- **arrow** — any distance along that line
- **plain line** — one step along that line
- **dotted ring of twelve** — the Knight's leaps
- **filled dots** — on the Guard, the cells two steps away
- **line, dot, ring** — the Cannon: slide, screen, target
- **ring** — the General

---

## Playing

Four modes from the menu: two players, against the computer, watching
the computer play itself, or **Free board**. Five difficulties from Recruit
to Marshal, plus Custom.

**Free board** has no turns and no opponent. Drag any piece, of either
colour, to any empty point or onto an enemy piece, whether or not it could
move there; clicking a piece still shows where it could legally go. Drag a
piece off the board to remove it. The side panel holds a pool of every
piece for both sides, to click or drag onto empty points. A General can't
be captured, and a side can only have one, so his tile works only while
that side has none. It used to be the `SANDBOX` switch in `config.py`;
now it's chosen for one game, from the menu.

| | |
|---|---|
| Left click | select a piece, then a destination |
| Left drag | pick a piece up and drop it where you let go. `MOVEMENT_TYPE` can limit you to clicking or to dragging |
| Left click or drag while the computer thinks | queue a premove |
| Right click / drag | mark a cell / draw an arrow. Arrows snap to the six lines and the Knight's leaps |
| **C** / **X** | deselect / clear marks and arrows |
| **M** | mute |
| **R** | restart |
| **Esc** or Menu | back to the menu |
| **F11** | fullscreen |

---

## Config, from the menu

**Config** on the menu edits `config.py` without opening it:

- **Settings** shows every switch as an on/off toggle and every number or
  choice with arrows on either side. Changed settings turn gold until you
  save. Changing the board size never gets stuck: both openings (point
  and flat) move onto the new board, centred, and any piece that no longer
  fits on White's half comes off, and the screen says how many. To edit the
  opening on the new board, save first: the opening page draws the board
  the game was started with.
- **Edit opening** shows the board itself. Pick a piece from the tray and
  click points on your half to place it; click it again, use Erase, or
  right-click to clear a point. Black's half shows the copy Black gets, and
  the tray counts each piece. Placing a General where there already is one
  moves him. "Clear the board" empties it altogether.
- **Save & restart** first checks the game would start with the new
  settings: at most one General, an opening that fits the board, and so on.
  An empty opening saves too, for laying one out on a Free board. A game
  started from an opening where White can't move simply says so.
  If something's wrong it says what, and nothing is written. Otherwise it
  writes the values into `config.py`, keeps every comment, and restarts
  the game so the rules and the engine pick them up.

`PIECE_CODES` and `GAME_LOG_FOLDER` are still edited in the file by hand. `config_editor.py` reads and writes the file;
`config_screen.py` draws the screen.

## config.py

| Setting | Does |
|---|---|
| `BOARD_ORIENTATION` | `"point"` or `"flat"`: a corner or a flat side of the board at each army's back. See The board |
| `BOARD_RADIUS` | how many rings of points surround the centre one. 5 is Gliński's 91 points; 4 gives 61, 6 gives 127 |
| `MOVEMENT_TYPE` | `1` click or drag, `2` click only, `3` drag only |
| `WHITE_SETUP` | the opening with the point at the back: one line per rank, one token per file. Lay out your own side only |
| `WHITE_SETUP_FLAT` | the opening with the flat side at the back: one line per row, one token per point, so the lines grow by one each rank |
| `MIRRORED_SETUP` | Black is your setup turned through 180°, or reflected across the middle. With the default setups the two are identical |
| `GENERALS_CANT_TOUCH` | the two Generals may never stand side by side |
| `SHOW_MOVEMENT_HINTS` | the diagrams on the tiles |
| `FREE_ARROWS` | arrows go where you drag them instead of snapping |
| `KNIGHT_ARROW_PATH` | arrows for a Knight's leap bend the way the leap is counted, two cells out along a line and one to the side, so they're easy to tell from line arrows. Only the drawing bends; the Knight still jumps |
| `FLIP_WHEN_BLACK` | turn the board when the side you control is Black |
| `SAVE_GAME_LOGS` | write each game to `logs/` |

---

## board_design.py

How the game looks. The board is drawn as in xiangqi: black lines on white,
with the pieces standing on the points where the lines cross. The lines
are the six directions themselves: every point is joined to its six
neighbours, so the board is a hexagon of triangles and every line on it is
a line a Chariot can travel. A heavier second frame runs just outside the
edge, and small dots mark the centre and the six points two steps from it
(`STAR_POINTS`). The pieces are Salvo's arches. `COLOUR_SCHEME` picks
their palette: `"modern"` (White red, Black black) or `"wooden"` (White
gold, Black brown).

---

## ai_config.py

How the computer plays: the difficulty levels, piece values, and what the
engine is rewarded for. The values are first guesses for the new pieces:
Chariot 500, Cannon 420, Knight 300, Guard 280, Pawn 100.

| Level | Depth | Seconds | Moves looked at per position |
|---|---|---|---|
| Recruit | 2 | 0.2 | 10 |
| Soldier | 4 | 0.6 | 20 |
| Sergeant | 5 | 1.5 | 28 |
| Captain | 6 | 4 | 44 |
| Marshal | 9 | 15 | 64 |

The search stops at whichever comes first, the depth or the seconds.
Without drops a position has a few dozen moves instead of hundreds, so
every level looks further ahead than before. Marshal reaches depth 9 in
the opening in about 12 seconds, and depth 6 or 7 in a busy middlegame.

The engine knows the draws. It is sent every position the game has been
through, so it sees which moves would bring one round for the third time
and scores them as a draw; it scores stalemate as a draw too. Ahead, it
steers clear of both; behind, it will go looking for them.

### The mate finder

The search only sees a mate that falls inside the depth its level allows,
so a weak level would hardly ever find one, and would walk into them. So
every level, Recruit included, also runs a mate finder (`MATE_SEARCH` in
`ai_config.py`). It tries only checking moves for the attacker and every
reply for the defender, which is narrow enough to see mates up to 4 moves
deep in a fraction of a second, whatever the level's own depth and time.

- **Before the search:** if it has a forced mate, it plays it at once,
  even at a level that otherwise makes mistakes on purpose.
- **After the search:** if the move it chose lets you force mate, it plays
  the best move that doesn't. `"defend": False` turns this half off.

It spends at most `"seconds"` (0.4) on each half, so a weak level may take
up to a second longer over a move when there are checks about. The engine
log says when it found a mate or dodged one.

### Custom difficulty

The sixth level on the menu, **Custom**. Clicking it opens a page with
every dial set by hand:

| Dial | What it does |
|---|---|
| Look-ahead | how many moves ahead it may look, time allowing |
| Thinking time | the most it thinks over one move |
| Moves considered | how many moves per position it looks at; fewer overlooks things |
| Following captures | captures it follows past the horizon; at 0 it leaves pieces hanging |
| Mistakes | how often it plays a move that isn't its best |
| Worst slip | how much worse than its best such a move may be (a Pawn is 100) |
| Aggression | 0 to 100, see below |

**Start from** copies one of the five named levels to tweak from there.
**Use these** saves the dials into `ai_config.py` (`CUSTOM_DIFFICULTY`),
so they're kept for next time, and makes Custom the chosen level. Click
Custom again to change them.

**Aggression** is 50 on every named level, which is how the engine has
always played. Above 50 it:

- cares more about the enemy General's safety than its own: squares round
  him it covers, check given, how boxed in he is;
- starts hunting him sooner, at 100 even when material is level;
- counts a draw as a small loss (up to 40, at 100), so it steers away from
  repetitions and stalemates.

Below 50 it does the opposite: it guards its own General first, waits
until it's well ahead before going after his, and is glad of a draw.

---

## Testing

`engine.cpp` restates the rules in another language. After any change to
`config.py`, `Rules.py` or `engine.cpp`:

```
python3 test_engine.py 400
```

It builds random positions on the hex board and checks that both
implementations produce exactly the same legal moves, and that no legal
move leaves the mover's own General in check. Then it checks the endings:
that both find no move in a checkmate and a stalemate, that the rules
call them a loss and a draw, that a repeated position draws the game, and
that the engine scores a third repetition as a draw.

There's no Fairy-Stockfish file: Fairy-Stockfish has no hexagonal boards.
