# Hex Charge

Charge on a hexagonal board. The board is a hexagon of hexagons, as in
Gliński's hex chess, and every piece moves along the six **orthogonal**
lines: up and down its file, and the four lines that cross to the
neighbouring files. There is no diagonal movement anywhere.

A captured piece is gone for good, and nothing promotes. Play against a
compiled C++ opponent or a second person.

Built from Salvo, so it shares Salvo's controls, menu, pieces, engine and
tooling.

---

## Running it

```
g++ -O2 -std=c++17 -o hexcharge_engine engine.cpp
python3 HexCharge.py
```

Needs Python 3.9+, pygame, numpy (for sound) and any C++17 compiler. On
Windows the binary is `hexcharge_engine.exe`; see BUILD.md.

---

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

Three modes from the menu: two players, against the computer, or watching
the computer play itself. Five difficulties from Recruit to Marshal.

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
  save. Changing the board size keeps your opening centred on the new board.
- **Edit opening** shows the board itself. Pick a piece from the tray and
  click points on your half to place it; click it again, use Erase, or
  right-click to clear a point. Black's half shows the copy Black gets, and
  the tray counts each piece.
- **Save & restart** first checks the game would start with the new
  settings: exactly one General, an opening that fits the board, and so on.
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
| `SANDBOX` | display mode: no turns and no opponent. Drag any piece anywhere, or off the board to remove it; the panel holds a pool of every piece for both sides, to click or drag onto empty points. A side can only have one General, so his tile works only while that side has none |
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
