// engine.cpp - the Hex Charge opponent.
//
// Searches deeper as time allows (iterative deepening with principal-
// variation search, killer moves, a history table and late-move
// reductions), keeps a table of positions it has already searched, and
// answers "is this point attacked?" backwards - looking outward from the
// point for something that could reach it, and stopping at the first.
//
// The rules are the ones in Rules.py, restated: a captured piece is gone,
// nothing promotes. The side with no legal move loses if in check and
// draws if not, and a position met for the third time is a draw - the
// game sends the keys of every position so far, so the search knows which
// moves would repeat one.
//
// Aggression (0-100, 50 the old engine's own taste) tilts its judgement
// towards attack or towards safety: how much it cares about the enemy
// General's safety against its own, how early it starts hunting him, and
// what a draw is worth to it - an aggressive engine counts a draw as a
// small loss and steers away from one, a cautious one is glad of it.
//
// It also measures itself: every search reports how deep it got, how many
// positions it looked at and how fast - in the "info" line, and in an
// engine log if one is set up (ENGINE_LOG in ai_config.py).
// engine_report.py summarises that log.
//
// Build:  g++ -O2 -std=c++17 -o hexcharge_engine engine.cpp

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

namespace {

// ---------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------

enum PieceType : int8_t {
    NONE = 0, GENERAL, CHARIOT, KNIGHT, GUARD, PAWN, CANNON, TYPE_COUNT
};

const char* kTypeName[TYPE_COUNT] = {
    "-", "General", "Chariot", "Knight", "Guard", "Pawn", "Cannon"
};

PieceType typeFromName(const std::string& name) {
    for (int t = 1; t < TYPE_COUNT; ++t)
        if (name == kTypeName[t]) return static_cast<PieceType>(t);
    return NONE;
}

struct Cell {
    int8_t type = NONE;
    int8_t owner = 0;        // 0 = White, 1 = Black
    bool empty() const { return type == NONE; }
};

constexpr int MAXN = 15;                 // largest array side: radius 7
constexpr int MAXSQ = MAXN * MAXN;
constexpr int MAX_PLY = 128;
constexpr int MAX_MOVES = 1024;          // per position
constexpr double WIN_SCORE = 1e6;
constexpr double INF_SCORE = WIN_SCORE * 4;

// ---------------------------------------------------------------------
// Everything the Python side tells us
// ---------------------------------------------------------------------

struct Config {
    int size = 9;
    bool generalsCantTouch = false;

    double pawnAdvance = 0.0;
    int pawnHome = 2;
    double shelter = 0.0;
    double exposure = 0.0;
    double activity[TYPE_COUNT] = {};
    std::array<double, TYPE_COUNT> value{};

    // The finer weights - ENGINE_WEIGHTS in ai_config.py.
    double mobility = 0.7, check = 45.0;
    double huntRamp = 400.0, huntEscape = 26.0, huntDistance = 6.0;
    double repetition = 55.0;
    double aggression = 50.0;            // 0 cautious, 50 neutral, 100 reckless

    // The mate finder, at every level - MATE_SEARCH in ai_config.py.
    int mateMoves = 4;                   // looks for mates up to this many moves
    double mateSeconds = 0.4;            // and spends at most this long, each way
    bool mateDefend = true;              // also checks its own move doesn't allow one

    // The difficulty dials.
    int branching = 64, qply = 8;
    double noise = 0.0, window = 250.0;
    bool lmr = true;                     // late-move reductions

    // Measuring.
    std::string logPath;
    std::string level = "?";
};

Config cfg;
int NN = 9;

int RAD = 4;                             // board radius: NN = 2 * RAD + 1

// The board is a hexagon of hexagons stored in axial coordinates in a
// square array: col is the file, row runs down it. Only cells within RAD
// of the centre are on the board.
// The side this engine is playing, set at the start of every search, so
// aggression can tilt the judgement towards that side's attack.
int engineSide = 0;

// How much a General's safety counts, by whose General it is. Neutral at
// aggression 50: both 1. More aggressive, the enemy's counts for more
// (attacking him) and its own for less; less aggressive, the other way.
inline double safetyWeight(int owner) {
    const double a = cfg.aggression / 50.0;                 // 0 .. 2
    return owner == engineSide ? 1.5 - 0.5 * a : a;
}
// A draw, as the side to move sees it: a small loss for an aggressive
// engine, a small gain for a cautious one, nothing at 50.
inline double drawScore(int side) {
    const double contempt = (cfg.aggression - 50.0) * 0.8;  // -40 .. +40
    return side == engineSide ? -contempt : contempt;
}

inline int idx(int r, int c) { return r * NN + c; }
inline bool inside(int r, int c) {
    return r >= 0 && r < NN && c >= 0 && c < NN && std::abs(r + c - 2 * RAD) <= RAD;
}
inline int hexDist(int a, int b) {
    const int dr = a / NN - b / NN, dc = a % NN - b % NN;
    return (std::abs(dr) + std::abs(dc) + std::abs(dr + dc)) / 2;
}
// White's rank of a cell, counted up its own file as Glinski counts.
// With the flat side at the back the ranks are simply the rows.
bool flatBoard = false;
inline int rankOf(int r, int c) {
    return flatBoard ? NN - r : std::min(NN - 1, NN - 1 + RAD - c) - r + 1;
}
inline int rankFor(int side, int sq) {
    const int r = sq / NN, c = sq % NN;
    return side == 0 ? rankOf(r, c) : rankOf(NN - 1 - r, NN - 1 - c);
}

double pieceValue(const Cell& c) { return cfg.value[c.type]; }

// The six orthogonal directions - up and down the file, and the four that
// cross to the neighbouring files. There are no diagonals.
const int kHexR[6] = {-1, 1, -1, 0, 0, 1};
const int kHexC[6] = {0, 0, 1, 1, -1, -1};
// Glinski's knight: the twelve nearest cells on none of his lines.
const int kKnightR[12] = {-3, -3, -2, -2, -1, -1, 1, 1, 2, 2, 3, 3};
const int kKnightC[12] = {1, 2, -1, 3, -2, 3, -3, 2, -3, 1, -2, -1};
// The Guard's second step: the twelve cells two away, and the one or two
// neighbours he may pass through to reach each.
struct Walk { int dr, dc, via; int vr[2], vc[2]; };
Walk kWalk[12];
void setupWalks() {
    int n = 0;
    for (int a = 0; a < 6; ++a)
        for (int b = 0; b < 6; ++b) {
            int er = kHexR[a] + kHexR[b], ec = kHexC[a] + kHexC[b];
            if ((std::abs(er) + std::abs(ec) + std::abs(er + ec)) / 2 != 2) continue;
            int k = 0;
            while (k < n && !(kWalk[k].dr == er && kWalk[k].dc == ec)) ++k;
            if (k == n) { kWalk[n] = Walk{er, ec, 0, {0, 0}, {0, 0}}; ++n; }
            Walk& w = kWalk[k];
            bool have = false;
            for (int v = 0; v < w.via; ++v) have |= (w.vr[v] == kHexR[a] && w.vc[v] == kHexC[a]);
            if (!have) { w.vr[w.via] = kHexR[a]; w.vc[w.via] = kHexC[a]; ++w.via; }
        }
}

std::string squareName(int sq) {
    static const char* kFiles = "abcdefghiklmnopq";          // no j
    std::string s(1, kFiles[sq % NN]);
    return s + std::to_string(rankOf(sq / NN, sq % NN));
}

// ---------------------------------------------------------------------
// Keys for positions (Zobrist)
// ---------------------------------------------------------------------

uint64_t zobCell[MAXSQ][TYPE_COUNT][2];
uint64_t zobSide;

void setupZobrist() {
    std::mt19937_64 rng(0x5a1f0e7c2d3b4a59ULL);
    for (auto& a : zobCell) for (auto& b : a) for (auto& d : b) d = rng();
    zobSide = rng();
}

inline uint64_t cellKey(int sq, const Cell& c) {
    return c.empty() ? 0 : zobCell[sq][c.type][c.owner];
}

// ---------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------

struct Board {
    Cell cell[MAXSQ];
    int royal[2];
    uint64_t key;                        // the pieces; side added on use

    void clear() {
        for (auto& c : cell) c = Cell{};
        royal[0] = royal[1] = -1;
        key = 0;
    }
    void recompute() {
        key = 0;
        royal[0] = royal[1] = -1;
        for (int sq = 0; sq < NN * NN; ++sq) {
            key ^= cellKey(sq, cell[sq]);
            if (cell[sq].type == GENERAL) royal[cell[sq].owner] = sq;
        }
    }
    void put(int sq, const Cell& c) {
        key ^= cellKey(sq, cell[sq]);
        cell[sq] = c;
        key ^= cellKey(sq, c);
    }
};

inline uint64_t hashOf(const Board& b, int side) { return b.key ^ (side ? zobSide : 0); }

// ---------------------------------------------------------------------
// Moves
// ---------------------------------------------------------------------

struct Move {
    int16_t from = -1;
    int16_t to = -1;
    double order = 0.0;                  // move-ordering score, not identity
};

inline bool sameMove(const Move& a, const Move& b) {
    return a.from == b.from && a.to == b.to;
}

struct Undo {
    Cell mover, victim;
    int royal0 = -1, royal1 = -1;
    uint64_t key = 0;
};

void makeMove(Board& b, const Move& m, int side, Undo& u) {
    u.key = b.key;
    u.royal0 = b.royal[0];
    u.royal1 = b.royal[1];
    const Cell mover = b.cell[m.from];
    const Cell victim = b.cell[m.to];
    u.mover = mover;
    u.victim = victim;
    if (victim.type == GENERAL) b.royal[victim.owner] = -1;
    b.put(m.from, Cell{});
    b.put(m.to, mover);
    if (mover.type == GENERAL) b.royal[side] = m.to;
}

void unmakeMove(Board& b, const Move& m, int side, const Undo& u) {
    (void)side;
    b.cell[m.from] = u.mover;
    b.cell[m.to] = u.victim;
    b.key = u.key;
    b.royal[0] = u.royal0;
    b.royal[1] = u.royal1;
}

// ---------------------------------------------------------------------
// Movement, written once and used two ways
//
// Each generator calls emit(square) for every square it reaches, so the
// same code serves both to COUNT moves (for the evaluation) and to LIST
// them (for the search) without allocating anything. Like Rules.py, where
// a piece can MOVE and where it can CAPTURE are separate questions for the
// cannons: baseGen answers the first, threatGen the second.
// ---------------------------------------------------------------------

template <class F>
void slideGen(const Board& b, int r, int c, int o, const int* dr, const int* dc,
              int dirs, int limit, bool quiet, F&& emit) {
    for (int d = 0; d < dirs; ++d)
        for (int step = 1; step <= limit; ++step) {
            int nr = r + dr[d] * step, nc = c + dc[d] * step;
            if (!inside(nr, nc)) break;
            const Cell& t = b.cell[idx(nr, nc)];
            if (t.empty()) { emit(idx(nr, nc)); continue; }
            if (!quiet && t.owner != o) emit(idx(nr, nc));
            break;
        }
}

template <class F>
void leapGen(const Board& b, int r, int c, int o, const int* dr, const int* dc, int n, F&& emit) {
    for (int d = 0; d < n; ++d) {
        int nr = r + dr[d], nc = c + dc[d];
        if (!inside(nr, nc)) continue;
        const Cell& t = b.cell[idx(nr, nc)];
        if (t.empty() || t.owner != o) emit(idx(nr, nc));
    }
}

// The Guard's second step: two cells away, through an empty neighbour.
template <class F>
void walkGen(const Board& b, int r, int c, int o, F&& emit) {
    for (const Walk& w : kWalk) {
        int nr = r + w.dr, nc = c + w.dc;
        if (!inside(nr, nc)) continue;
        bool open = false;
        for (int v = 0; v < w.via && !open; ++v) {
            int pr = r + w.vr[v], pc = c + w.vc[v];
            open = inside(pr, pc) && b.cell[idx(pr, pc)].empty();
        }
        if (!open) continue;
        const Cell& t = b.cell[idx(nr, nc)];
        if (t.empty() || t.owner != o) emit(idx(nr, nc));
    }
}

// Where a cannon may MOVE: slide over empty squares, or take the first
// piece beyond exactly one screen.
template <class F>
void cannonGen(const Board& b, int r, int c, int o, const int* dr, const int* dc, F&& emit) {
    for (int d = 0; d < 6; ++d) {
        int step = 1;
        for (;; ++step) {
            int nr = r + dr[d] * step, nc = c + dc[d] * step;
            if (!inside(nr, nc)) break;
            if (!b.cell[idx(nr, nc)].empty()) break;
            emit(idx(nr, nc));
        }
        int sr = r + dr[d] * step, sc = c + dc[d] * step;
        if (!inside(sr, sc)) continue;              // no screen on this line
        for (++step;; ++step) {
            int tr = r + dr[d] * step, tc = c + dc[d] * step;
            if (!inside(tr, tc)) break;
            const Cell& t = b.cell[idx(tr, tc)];
            if (t.empty()) continue;
            if (t.owner != o) emit(idx(tr, tc));
            break;
        }
    }
}

// What a cannon THREATENS: everything past exactly one screen, up to and
// including the next piece.
template <class F>
void hopGen(const Board& b, int r, int c, int o, const int* dr, const int* dc, F&& emit) {
    for (int d = 0; d < 6; ++d) {
        int step = 1;
        for (;; ++step) {
            int nr = r + dr[d] * step, nc = c + dc[d] * step;
            if (!inside(nr, nc)) break;
            if (!b.cell[idx(nr, nc)].empty()) {          // the screen
                for (++step;; ++step) {
                    int tr = r + dr[d] * step, tc = c + dc[d] * step;
                    if (!inside(tr, tc)) break;
                    const Cell& t = b.cell[idx(tr, tc)];
                    if (t.empty()) { emit(idx(tr, tc)); continue; }
                    if (t.owner != o) emit(idx(tr, tc));
                    break;
                }
                break;
            }
        }
    }
}

template <class F>
void baseGen(const Board& b, int sq, F&& emit) {
    const Cell& p = b.cell[sq];
    const int r = sq / NN, c = sq % NN, o = p.owner;
    switch (p.type) {
        case GENERAL: slideGen(b, r, c, o, kHexR, kHexC, 6, 1, false, emit); break;
        case CHARIOT: slideGen(b, r, c, o, kHexR, kHexC, 6, NN - 1, false, emit); break;
        case KNIGHT:  leapGen(b, r, c, o, kKnightR, kKnightC, 12, emit); break;
        case GUARD:
            slideGen(b, r, c, o, kHexR, kHexC, 6, 1, false, emit);
            walkGen(b, r, c, o, emit);
            break;
        case PAWN:    slideGen(b, r, c, o, kHexR, kHexC, 6, 1, false, emit); break;
        case CANNON:  cannonGen(b, r, c, o, kHexR, kHexC, emit); break;
        default: break;
    }
}

// Where a piece could CAPTURE - not the same as where it moves for the
// Cannon, which covers only what lies past a screen.
template <class F>
void threatGen(const Board& b, int sq, F&& emit) {
    const Cell& p = b.cell[sq];
    const int r = sq / NN, c = sq % NN, o = p.owner;
    if (p.type == CANNON) hopGen(b, r, c, o, kHexR, kHexC, emit);
    else baseGen(b, sq, emit);
}

// ---------------------------------------------------------------------
// Is this square attacked? - asked backwards
//
// Does `side`'s army (its General aside) attack `sq`? Instead of listing
// what every piece attacks, look outward FROM the square for something
// that could reach it, and stop at the first. This is the heart of the
// rewrite: the old engine spent four fifths of its time on this question.
// ---------------------------------------------------------------------

bool attackedBy(const Board& b, int sq, int side) {
    const int r = sq / NN, c = sq % NN;

    // Lines: the first piece may be a Chariot; a Cannon further on, with
    // that first piece as its screen.
    for (int d = 0; d < 6; ++d) {
        const int dr = kHexR[d], dc = kHexC[d];
        int rr = r + dr, cc = c + dc;
        while (inside(rr, cc) && b.cell[idx(rr, cc)].empty()) { rr += dr; cc += dc; }
        if (!inside(rr, cc)) continue;
        const Cell& p = b.cell[idx(rr, cc)];
        if (p.owner == side && p.type == CHARIOT) return true;
        rr += dr; cc += dc;
        while (inside(rr, cc) && b.cell[idx(rr, cc)].empty()) { rr += dr; cc += dc; }
        if (!inside(rr, cc)) continue;
        const Cell& q = b.cell[idx(rr, cc)];
        if (q.owner == side && q.type == CANNON) return true;
    }

    // Next door: a Guard or a Pawn.
    for (int d = 0; d < 6; ++d) {
        int nr = r + kHexR[d], nc = c + kHexC[d];
        if (!inside(nr, nc)) continue;
        const Cell& p = b.cell[idx(nr, nc)];
        if ((p.type == GUARD || p.type == PAWN) && p.owner == side) return true;
    }

    // Two away: a Guard walking in through an empty cell. The walk is
    // symmetric, so the cells he passes are the same seen from here.
    for (const Walk& w : kWalk) {
        int gr = r + w.dr, gc = c + w.dc;
        if (!inside(gr, gc)) continue;
        const Cell& p = b.cell[idx(gr, gc)];
        if (p.type != GUARD || p.owner != side) continue;
        for (int v = 0; v < w.via; ++v) {
            int pr = r + w.vr[v], pc = c + w.vc[v];
            if (inside(pr, pc) && b.cell[idx(pr, pc)].empty()) return true;
        }
    }

    // Leaps: a Knight whose leap lands here.
    for (int d = 0; d < 12; ++d) {
        int kr = r - kKnightR[d], kc = c - kKnightC[d];
        if (!inside(kr, kc)) continue;
        const Cell& p = b.cell[idx(kr, kc)];
        if (p.owner == side && p.type == KNIGHT) return true;
    }

    return false;
}

bool royalInCheck(const Board& b, int side) {
    const int seat = b.royal[side];
    if (seat < 0) return false;
    const int enemy = side ^ 1;
    if (attackedBy(b, seat, enemy)) return true;
    const int other = b.royal[enemy];
    if (other < 0 || hexDist(seat, other) > 1) return false;
    if (cfg.generalsCantTouch) return true;
    // Generals may stand side by side only if his own army guards him.
    return !attackedBy(b, seat, side);
}

// ---------------------------------------------------------------------
// Legal actions
// ---------------------------------------------------------------------

int generateActions(Board& b, int side, Move* out, int maxOut) {
    int n = 0;
    int targets[MAXSQ];
    for (int sq = 0; sq < NN * NN; ++sq) {
        const Cell& p = b.cell[sq];
        if (p.empty() || p.owner != side) continue;
        bool seen[MAXSQ] = {};
        int nt = 0;
        baseGen(b, sq, [&](int to) { if (!seen[to]) { seen[to] = true; targets[nt++] = to; } });
        for (int k = 0; k < nt && n < maxOut; ++k) {
            Move m; m.from = static_cast<int16_t>(sq); m.to = static_cast<int16_t>(targets[k]);
            Undo u;
            makeMove(b, m, side, u);
            bool ok = !royalInCheck(b, side);
            unmakeMove(b, m, side, u);
            if (ok) out[n++] = m;
        }
    }
    return n;
}

// ---------------------------------------------------------------------
// Evaluation - the same terms and weights as the old engine
// ---------------------------------------------------------------------

double pawnProgress(const Board& b, int sq, int side) {
    int col = sq % NN;
    int forward = rankFor(side, sq) - 1;
    int advanced = std::max(0, std::min(4, forward - cfg.pawnHome));
    if (advanced == 0) return 0.0;
    int seat = b.royal[side];
    if (seat >= 0 && std::abs(col - seat % NN) <= 1) return 0.0;
    return advanced * cfg.pawnAdvance;
}

double generalSafety(const Board& b, int side) {
    const int seat = b.royal[side];
    if (seat < 0) return 0.0;
    const int enemy = side ^ 1;
    const int r = seat / NN, c = seat % NN;
    double score = 0.0;
    for (int d = 0; d < 6; ++d) {
        int nr = r + kHexR[d], nc = c + kHexC[d];
        if (!inside(nr, nc)) continue;
        int s = idx(nr, nc);
        const Cell& x = b.cell[s];
        if (!x.empty() && x.owner == side) score += cfg.shelter;
        // A side never "covers" a square holding its own piece.
        bool enemyCovers = !(!x.empty() && x.owner == enemy) && attackedBy(b, s, enemy);
        if (enemyCovers) score -= cfg.exposure;
    }
    return score;
}

double evaluate(const Board& b, int side) {
    const int enemy = side ^ 1;
    const int enemySeat = b.royal[enemy];
    double ownValue = 0, enemyValue = 0, style = 0;
    int ownMoves = 0, enemyMoves = 0;
    long distTotal = 0;
    int distCount = 0;
    for (int sq = 0; sq < NN * NN; ++sq) {
        const Cell& p = b.cell[sq];
        if (p.empty()) continue;
        int count = 0;
        baseGen(b, sq, [&](int) { ++count; });
        double seen = count * cfg.activity[p.type];
        double pawn = (p.type == PAWN) ? pawnProgress(b, sq, p.owner) : 0.0;
        style += (p.owner == side ? 1.0 : -1.0) * (seen + pawn);
        if (p.owner == side) {
            ownValue += pieceValue(p);
            ownMoves += count;
            if (enemySeat >= 0 && p.type != GENERAL) { distTotal += hexDist(sq, enemySeat); ++distCount; }
        } else {
            enemyValue += pieceValue(p);
            enemyMoves += count;
        }
    }
    double material = ownValue - enemyValue;
    double positional = (ownMoves - enemyMoves) * cfg.mobility + style;
    if (cfg.shelter != 0.0 || cfg.exposure != 0.0)
        positional += generalSafety(b, side) * safetyWeight(side)
                    - generalSafety(b, enemy) * safetyWeight(enemy);
    if (royalInCheck(b, side)) positional -= cfg.check * safetyWeight(side);
    if (royalInCheck(b, enemy)) positional += cfg.check * safetyWeight(enemy);

    // Ahead: hunt the enemy General - box him in, close in on him. An
    // aggressive engine starts the hunt sooner: at aggression 100 when
    // level, at 0 only once well ahead.
    const double head = (side == engineSide ? 1.0 : -1.0)
                      * (cfg.aggression - 50.0) / 50.0 * cfg.huntRamp * 0.5;
    if (material + head > 0 && enemySeat >= 0) {
        double hunt = std::min(1.0, (material + head) / cfg.huntRamp) * safetyWeight(enemy);
        const int ownSeat = b.royal[side];
        int safe = 0;
        const int er = enemySeat / NN, ec = enemySeat % NN;
        for (int d = 0; d < 6; ++d) {
            int nr = er + kHexR[d], nc = ec + kHexC[d];
            if (!inside(nr, nc)) continue;
            int s = idx(nr, nc);
            const Cell& x = b.cell[s];
            if (!x.empty() && x.owner == enemy) continue;          // not an escape
            bool ours = !x.empty() && x.owner == side;
            bool covered = !ours && (attackedBy(b, s, side)
                                     || (ownSeat >= 0 && hexDist(s, ownSeat) == 1));
            if (!covered) ++safe;
        }
        positional -= safe * cfg.huntEscape * hunt;
        if (distCount)
            positional -= (static_cast<double>(distTotal) / distCount) * cfg.huntDistance * hunt;
    }
    return material + positional;
}

// ---------------------------------------------------------------------
// Searched positions
// ---------------------------------------------------------------------

enum : uint8_t { EXACT = 0, LOWER = 1, UPPER = 2 };

struct TTEntry {
    uint64_t key = 0;
    double score = 0.0;
    int16_t depth = -1;
    uint8_t bound = EXACT;
    uint8_t age = 0;
    Move move;
    bool hasMove = false;
};

std::vector<TTEntry> table;
size_t tableMask = 0;
uint8_t tableAge = 0;

void resetTable() {
    table.assign(size_t(1) << 20, TTEntry{});
    tableMask = table.size() - 1;
    tableAge = 0;
}

// ---------------------------------------------------------------------
// Measuring
// ---------------------------------------------------------------------

using Clock = std::chrono::steady_clock;

struct Stats {
    long long nodes = 0, qnodes = 0;
    long long ttProbes = 0, ttHits = 0, ttCuts = 0;
    long long cutoffs = 0, firstCutoffs = 0;
    long long reductions = 0, researches = 0;
    int seldepth = 0;
};

struct Iteration {
    int depth;
    double seconds, score;
    long long nodes;                     // positions searched in this iteration
    Move best;
};

Stats st;
bool stopFlag = false;
Clock::time_point started, deadline;

inline void tick() {
    if (((st.nodes + st.qnodes) & 1023) == 0 && Clock::now() > deadline) stopFlag = true;
}

// ---------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------

Board board;
int sideToMove = 0;
// Whether each side had a General when the search began. A General gone
// from the board mid-search has been taken; one that was never there - an
// opening laid out without him - is simply absent, and nothing is won.
bool hadRoyal[2] = {true, true};

// Repetition. gameKeys holds the key of every position the game has been
// through, sent by the game before each search; pathKeys the positions
// along the line being searched, by ply. A position that has already
// been met twice - in the game, along the line, or between them - would
// be met for the third time: a draw.
std::vector<uint64_t> gameKeys;
uint64_t pathKeys[MAX_PLY + 1];

int timesSeen(uint64_t key, int ply) {
    int n = 0;
    for (uint64_t k : gameKeys) n += (k == key);
    for (int p = 0; p < ply; ++p) n += (pathKeys[p] == key);
    return n;
}

Move moveStack[MAX_PLY][MAX_MOVES];
Move killers[MAX_PLY][2];
int history[MAXSQ][MAXSQ];

// The old engine's ordering, plus the transposition move first, killer
// moves and the history table for quiet moves.
void orderMoves(const Board& b, int side, Move* mv, int n, const Move* ttMove, int ply) {
    const int enemy = side ^ 1;
    for (int i = 0; i < n; ++i) {
        Move& m = mv[i];
        if (ttMove && sameMove(m, *ttMove)) { m.order = 1e15; continue; }
        const Cell& mover = b.cell[m.from];
        const Cell& victim = b.cell[m.to];
        double score = 0.0;
        if (!victim.empty()) {
            if (victim.type == GENERAL) score += WIN_SCORE;
            score += pieceValue(victim) * 10 - pieceValue(mover);
        } else {
            if (attackedBy(b, m.to, enemy)) score -= cfg.value[mover.type] * 0.3;
            if (ply < MAX_PLY) {
                if (sameMove(m, killers[ply][0])) score += 150.0;
                else if (sameMove(m, killers[ply][1])) score += 100.0;
            }
            const double h = history[m.from][m.to];
            score += 50.0 * h / (h + 1000.0);
        }
        m.order = score;
    }
    std::sort(mv, mv + n, [](const Move& a, const Move& b2) { return a.order > b2.order; });
}

// The difficulty's branching limit: the best `branching` moves by the
// ordering, the rest never looked at.
int selectBranch(Move*, int n) { return std::min(n, cfg.branching); }

double quiescence(Board& b, int side, double alpha, double beta, int qply, int ply) {
    ++st.qnodes;
    if (ply > st.seldepth) st.seldepth = ply;
    tick();
    if (stopFlag) return 0.0;
    if (b.royal[side ^ 1] < 0 && hadRoyal[side ^ 1]) return WIN_SCORE;
    if (b.royal[side] < 0 && hadRoyal[side]) return -WIN_SCORE;
    double standPat = evaluate(b, side);
    if (standPat >= beta) return beta;
    if (standPat > alpha) alpha = standPat;
    if (qply >= cfg.qply) return alpha;

    Move caps[256];
    int n = 0;
    for (int sq = 0; sq < NN * NN; ++sq) {
        const Cell& p = b.cell[sq];
        if (p.empty() || p.owner != side) continue;
        bool seen[MAXSQ] = {};
        baseGen(b, sq, [&](int to) {
            if (seen[to] || n >= 256) return;
            seen[to] = true;
            const Cell& v = b.cell[to];
            if (v.empty() || v.owner == side) return;
            Move m; m.from = static_cast<int16_t>(sq); m.to = static_cast<int16_t>(to);
            m.order = pieceValue(v) * 10 - pieceValue(p);
            caps[n++] = m;
        });
    }
    std::sort(caps, caps + n, [](const Move& a, const Move& b2) { return a.order > b2.order; });
    const int enemy = side ^ 1;
    for (int i = 0; i < n; ++i) {
        Undo u;
        makeMove(b, caps[i], side, u);
        if (royalInCheck(b, side)) { unmakeMove(b, caps[i], side, u); continue; }
        double score = -quiescence(b, enemy, -beta, -alpha, qply + 1, ply + 1);
        unmakeMove(b, caps[i], side, u);
        if (stopFlag) return 0.0;
        if (score >= beta) return beta;
        if (score > alpha) alpha = score;
    }
    return alpha;
}

constexpr double NULL_WINDOW = 1e-4;

double negamax(Board& b, int side, int depth, double alpha, double beta, int ply) {
    ++st.nodes;
    if (ply > st.seldepth) st.seldepth = ply;
    tick();
    if (stopFlag) return 0.0;
    if (b.royal[side ^ 1] < 0 && hadRoyal[side ^ 1]) return WIN_SCORE + depth;
    if (b.royal[side] < 0 && hadRoyal[side]) return -WIN_SCORE - depth;

    const uint64_t key = hashOf(b, side);
    if (timesSeen(key, ply) >= 2) return drawScore(side); // third time: a draw
    pathKeys[ply] = key;
    TTEntry& slot = table[key & tableMask];
    Move ttMove;
    bool haveTT = false;
    ++st.ttProbes;
    if (slot.key == key) {
        ++st.ttHits;
        if (slot.depth >= depth) {
            if (slot.bound == EXACT) { ++st.ttCuts; return slot.score; }
            if (slot.bound == LOWER && slot.score > alpha) alpha = slot.score;
            else if (slot.bound == UPPER && slot.score < beta) beta = slot.score;
            if (alpha >= beta) { ++st.ttCuts; return slot.score; }
        }
        if (slot.hasMove) { ttMove = slot.move; haveTT = true; }
    }
    if (depth <= 0) return quiescence(b, side, alpha, beta, 0, ply);
    if (ply >= MAX_PLY - 1) return evaluate(b, side);

    Move* mv = moveStack[ply];
    int n = generateActions(b, side, mv, MAX_MOVES);
    const bool inCheck = royalInCheck(b, side);
    if (n == 0) return inCheck ? -WIN_SCORE - depth : drawScore(side);   // mated, or stalemate
    orderMoves(b, side, mv, n, haveTT ? &ttMove : nullptr, ply);
    n = selectBranch(mv, n);

    const int enemy = side ^ 1;
    const double alphaOrig = alpha;
    Move best = mv[0];
    for (int i = 0; i < n; ++i) {
        const Move m = mv[i];
        Undo u;
        makeMove(b, m, side, u);
        const bool quiet = u.victim.empty();
        double score;
        if (i == 0) {
            score = -negamax(b, enemy, depth - 1, -beta, -alpha, ply + 1);
        } else {
            // Late, quiet moves are searched a ply shallower first; if one
            // turns out better than expected it is searched again in full.
            int reduce = 0;
            if (cfg.lmr && depth >= 3 && i >= 3 && quiet && !inCheck
                && !sameMove(m, killers[ply][0]) && !sameMove(m, killers[ply][1])
                && !royalInCheck(b, enemy)) {
                reduce = 1;
                ++st.reductions;
            }
            score = -negamax(b, enemy, depth - 1 - reduce, -alpha - NULL_WINDOW, -alpha, ply + 1);
            if (score > alpha && reduce) {
                ++st.researches;
                score = -negamax(b, enemy, depth - 1, -alpha - NULL_WINDOW, -alpha, ply + 1);
            }
            if (score > alpha && score < beta) {
                ++st.researches;
                score = -negamax(b, enemy, depth - 1, -beta, -alpha, ply + 1);
            }
        }
        unmakeMove(b, m, side, u);
        if (stopFlag) return 0.0;
        if (score > alpha) { alpha = score; best = m; }
        if (alpha >= beta) {
            ++st.cutoffs;
            if (i == 0) ++st.firstCutoffs;
            if (quiet) {
                if (!sameMove(m, killers[ply][0])) { killers[ply][1] = killers[ply][0]; killers[ply][0] = m; }
                int& h = history[m.from][m.to];
                h = std::min(h + depth * depth, 1 << 24);
            }
            break;
        }
    }
    if (slot.key == key || slot.age != tableAge || depth >= slot.depth) {
        slot.key = key;
        slot.score = alpha;
        slot.depth = static_cast<int16_t>(depth);
        slot.bound = (alpha <= alphaOrig) ? UPPER : (alpha >= beta) ? LOWER : EXACT;
        slot.age = tableAge;
        slot.move = best;
        slot.hasMove = true;
    }
    return alpha;
}

struct SearchResult {
    Move best;
    bool found = false;
    int depthReached = 0;
    double score = 0.0;
    int rootActions = 0, rootSearched = 0;
    bool stoppedByClock = false;
    std::vector<Iteration> iterations;
    int mateIn = 0;                      // a forced mate the mate finder found, in moves
    int dodged = 0;                      // moves set aside for walking into a mate
};

// ---------------------------------------------------------------------
// The mate finder
// ---------------------------------------------------------------------
// The main search only sees a mate inside the depth the difficulty allows,
// so a weak level would hardly ever find one - and walk into them. This
// runs alongside it at EVERY level, with its own small time budget
// (MATE_SEARCH in ai_config.py): it tries only checking moves for the
// attacker, and every reply for the defender, which is narrow enough to
// see mates several moves deep in a fraction of a second.
//
// It is used both ways round. Before the search: is there a forced mate
// for us? Then play it. After the search, on the move chosen: does it let
// the enemy force mate? Then choose another.

long long mateNodes = 0, mateNodeLimit = 4000000;
bool mateStop = false;
Clock::time_point mateDeadline;

inline bool mateTick() {
    if ((++mateNodes & 511) == 0 && Clock::now() > mateDeadline) mateStop = true;
    if (mateNodes > mateNodeLimit) mateStop = true;
    return mateStop;
}

bool defenderLost(Board& b, int d, int movesLeft);

// Can `a`, to move, force mate within `movesLeft` of its own moves, giving
// check every time? The mating move is written to `found` at the top.
bool attackerMates(Board& b, int a, int movesLeft, Move* found) {
    if (mateTick()) return false;
    Move mv[MAX_MOVES];
    const int n = generateActions(b, a, mv, MAX_MOVES);
    const int d = a ^ 1;
    for (int i = 0; i < n; ++i) {
        Undo u;
        makeMove(b, mv[i], a, u);
        bool win = false;
        if (b.royal[d] >= 0 && royalInCheck(b, d)) win = defenderLost(b, d, movesLeft);
        unmakeMove(b, mv[i], a, u);
        if (mateStop) return false;
        if (win) { if (found) *found = mv[i]; return true; }
    }
    return false;
}

// `d` is in check and to move: is every reply still lost?
bool defenderLost(Board& b, int d, int movesLeft) {
    if (mateTick()) return false;
    Move mv[MAX_MOVES];
    const int n = generateActions(b, d, mv, MAX_MOVES);
    if (n == 0) return true;                       // checkmate
    if (movesLeft <= 1) return false;
    for (int i = 0; i < n; ++i) {
        Undo u;
        makeMove(b, mv[i], d, u);
        const bool lost = attackerMates(b, d ^ 1, movesLeft - 1, nullptr);
        unmakeMove(b, mv[i], d, u);
        if (mateStop || !lost) return false;
    }
    return true;
}

// The shortest forced mate for `a`, up to `maxMoves`, within `seconds`:
// its length in moves, or 0 if none was found in time.
int findMate(Board& b, int a, int maxMoves, double seconds, Move* found) {
    if (maxMoves <= 0 || b.royal[a ^ 1] < 0 || b.royal[a] < 0) return 0;
    mateNodes = 0;
    mateStop = false;
    mateDeadline = Clock::now() + std::chrono::microseconds(static_cast<long long>(seconds * 1e6));
    for (int k = 1; k <= maxMoves; ++k) {
        if (attackerMates(b, a, k, found)) return k;
        if (mateStop) break;
    }
    return 0;
}


SearchResult search(Board& b, int side, int maxDepth, double seconds) {
    SearchResult result;
    st = Stats{};
    stopFlag = false;
    started = Clock::now();
    deadline = started + std::chrono::milliseconds(static_cast<long long>(seconds * 1000));
    ++tableAge;
    engineSide = side;
    for (auto& k : killers) k[0] = k[1] = Move{};
    for (auto& row : history) for (int& h : row) h /= 8;   // keep a little from last move

    static Move roots[MAX_MOVES];
    pathKeys[0] = hashOf(b, side);
    int n = generateActions(b, side, roots, MAX_MOVES);
    result.rootActions = n;
    if (n == 0) return result;
    orderMoves(b, side, roots, n, nullptr, 0);
    n = selectBranch(roots, n);
    result.rootSearched = n;
    result.best = roots[0];
    result.found = true;

    const int enemy = side ^ 1;

    // A forced mate the main search might be too shallow to see: play it.
    {
        Move mate;
        const int k = findMate(b, side, cfg.mateMoves, cfg.mateSeconds, &mate);
        if (k > 0) {
            result.best = mate;
            result.score = WIN_SCORE - (2 * k - 1);
            result.depthReached = 2 * k - 1;
            result.mateIn = k;
            return result;
        }
    }

    std::vector<std::pair<double, Move>> lastScores;
    std::vector<double> rootScore(n, -INF_SCORE);
    long long nodesBefore = 0;

    for (int depth = 1; depth <= maxDepth; ++depth) {
        // Best move from the last iteration first, then by last scores.
        if (depth > 1) {
            std::vector<int> order(n);
            for (int i = 0; i < n; ++i) order[i] = i;
            std::stable_sort(order.begin(), order.end(), [&](int x, int y) {
                bool xb = sameMove(roots[x], result.best), yb = sameMove(roots[y], result.best);
                if (xb != yb) return xb;
                return rootScore[x] > rootScore[y];
            });
            std::vector<Move> moves(n);
            std::vector<double> scores(n);
            for (int i = 0; i < n; ++i) { moves[i] = roots[order[i]]; scores[i] = rootScore[order[i]]; }
            for (int i = 0; i < n; ++i) { roots[i] = moves[i]; rootScore[i] = scores[i]; }
        }
        double alpha = -INF_SCORE, bestScore = -INF_SCORE;
        Move bestThisDepth = roots[0];
        std::vector<std::pair<double, Move>> scored;
        bool complete = true;
        const bool exactForAll = cfg.noise > 0.0;    // weighted choice needs every score
        for (int i = 0; i < n; ++i) {
            Undo u;
            makeMove(b, roots[i], side, u);
            // Back to a position the game has already seen: allowed, and
            // scored as a draw on the third time, but charged a little
            // even before then so the engine doesn't shuffle.
            const bool repeat = timesSeen(hashOf(b, side ^ 1), 0) > 0;
            double score;
            if (i == 0 || exactForAll || repeat) {
                score = -negamax(b, enemy, depth - 1, -INF_SCORE, INF_SCORE, 1);
            } else {
                score = -negamax(b, enemy, depth - 1, -alpha - NULL_WINDOW, -alpha, 1);
                if (score > alpha && !stopFlag) {
                    ++st.researches;
                    score = -negamax(b, enemy, depth - 1, -INF_SCORE, -alpha, 1);
                }
            }
            unmakeMove(b, roots[i], side, u);
            if (stopFlag) { complete = false; break; }
            if (repeat) score -= cfg.repetition;
            rootScore[i] = score;
            scored.push_back({score, roots[i]});
            if (score > bestScore) { bestScore = score; bestThisDepth = roots[i]; }
            if (score > alpha) alpha = score;
        }
        if (!complete) { result.stoppedByClock = true; break; }
        result.best = bestThisDepth;
        result.score = bestScore;
        result.depthReached = depth;
        lastScores = scored;
        long long total = st.nodes + st.qnodes;
        double elapsed = std::chrono::duration<double>(Clock::now() - started).count();
        result.iterations.push_back(Iteration{depth, elapsed, bestScore, total - nodesBefore, bestThisDepth});
        nodesBefore = total;
        if (std::abs(bestScore) >= WIN_SCORE / 2) break;    // a forced result: deeper adds nothing
    }

    // Weaker levels sometimes play a near-best move on purpose.
    if (cfg.noise > 0.0 && lastScores.size() > 1) {
        double best = -INF_SCORE;
        for (auto& sc : lastScores) best = std::max(best, sc.first);
        std::vector<std::pair<double, Move>> pool;
        double total = 0.0;
        for (auto& sc : lastScores) {
            if (sc.first < best - cfg.window) continue;
            total += std::exp((sc.first - best) / cfg.noise);
            pool.push_back({total, sc.second});
        }
        if (!pool.empty()) {
            static std::mt19937_64 rng(std::random_device{}());
            double roll = std::uniform_real_distribution<double>(0.0, total)(rng);
            for (auto& pc : pool) if (roll <= pc.first) { result.best = pc.second; break; }
        }
    }

    // Does the move chosen let the enemy force a mate the search was too
    // shallow to see? Then take the best-scored move that doesn't.
    if (cfg.mateDefend && cfg.mateMoves > 0 && b.royal[side] >= 0 && b.royal[enemy] >= 0) {
        std::vector<std::pair<double, Move>> order = lastScores;
        std::stable_sort(order.begin(), order.end(),
                         [](const std::pair<double, Move>& x, const std::pair<double, Move>& y) {
                             return x.first > y.first; });
        std::vector<Move> candidates{result.best};
        for (auto& sc : order) if (!sameMove(sc.second, result.best)) candidates.push_back(sc.second);
        const auto until = Clock::now() + std::chrono::microseconds(static_cast<long long>(cfg.mateSeconds * 1e6));
        const int depthCheck = std::max(1, cfg.mateMoves - 1);
        for (size_t i = 0; i < candidates.size() && i < 12 && Clock::now() < until; ++i) {
            Undo u;
            makeMove(b, candidates[i], side, u);
            Move reply;
            const double left = std::chrono::duration<double>(until - Clock::now()).count();
            const int k = findMate(b, enemy, depthCheck, std::max(0.01, left), &reply);
            unmakeMove(b, candidates[i], side, u);
            if (k == 0) {
                if (i > 0) { result.best = candidates[i]; result.dodged = static_cast<int>(i); }
                break;
            }
        }
    }
    return result;
}

// ---------------------------------------------------------------------
// The engine log
// ---------------------------------------------------------------------

std::string moveName(const Move& m) {
    return squareName(m.from) + "-" + squareName(m.to);
}

std::string fmt(const char* f, double v) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), f, v);
    return buf;
}

std::string withCommas(long long v) {
    std::string s = std::to_string(v), out;
    int k = 0;
    for (auto it = s.rbegin(); it != s.rend(); ++it) {
        if (k && k % 3 == 0 && *it != '-') out.push_back(',');
        out.push_back(*it);
        ++k;
    }
    return std::string(out.rbegin(), out.rend());
}

void writeLog(const SearchResult& r, int side, int askedDepth, double budget, int gamePly, double used) {
    if (cfg.logPath.empty()) return;
    const long long total = st.nodes + st.qnodes;
    const double nps = used > 0 ? total / used : 0.0;
    const double ttHit = st.ttProbes ? 100.0 * st.ttHits / st.ttProbes : 0.0;
    const double ttCut = st.ttProbes ? 100.0 * st.ttCuts / st.ttProbes : 0.0;
    const double first = st.cutoffs ? 100.0 * st.firstCutoffs / st.cutoffs : 0.0;
    const double quiesc = total ? 100.0 * st.qnodes / total : 0.0;
    double ebf = 0.0;
    if (r.iterations.size() >= 2) {
        const auto& a = r.iterations[r.iterations.size() - 2];
        const auto& b2 = r.iterations.back();
        if (a.nodes > 0) ebf = static_cast<double>(b2.nodes) / a.nodes;
    }
    char when[32];
    std::time_t now = std::time(nullptr);
    std::strftime(when, sizeof(when), "%Y-%m-%d %H:%M:%S", std::localtime(&now));
    const char* who = side == 0 ? "White" : "Black";
    std::string reason = r.depthReached >= askedDepth ? "reached the depth asked"
                       : r.stoppedByClock ? "stopped by the clock" : "stopped early (forced result)";

    std::ostringstream o;
    o << "[" << when << "] " << cfg.level << "  " << who << " to move  game ply " << gamePly << "\n";
    o << "  asked      depth " << askedDepth << " within " << fmt("%.2f", budget) << " s\n";
    o << "  reached    depth " << r.depthReached << " (deepest line " << st.seldepth << " plies, captures included)"
      << " in " << fmt("%.2f", used) << " s - " << reason << "\n";
    o << "  positions  " << withCommas(total) << " (" << fmt("%.0f", quiesc) << "% in the capture search), "
      << withCommas(static_cast<long long>(nps)) << " per second\n";
    o << "  table      " << fmt("%.1f", ttHit) << "% of lookups found, " << fmt("%.1f", ttCut)
      << "% answered outright\n";
    o << "  ordering   " << withCommas(st.cutoffs) << " cutoffs, " << fmt("%.1f", first)
      << "% by the first move tried\n";
    o << "  reductions " << withCommas(st.reductions) << " late moves searched shallower, "
      << withCommas(st.researches) << " searched again\n";
    o << "  branching  " << (ebf > 0 ? fmt("%.2f", ebf) : std::string("-"))
      << " (how many times longer each extra ply took)\n";
    o << "  root       " << r.rootActions << " legal actions, " << r.rootSearched << " searched\n";
    if (r.mateIn) o << "  mate       the mate finder found mate in " << r.mateIn << " - played at once\n";
    if (r.dodged) o << "  mate       the move first chosen let the enemy force mate; took choice " << r.dodged + 1 << " instead\n";
    o << "  chose      " << (r.found ? moveName(r.best) : std::string("none"))
      << "  score " << fmt("%+.1f", r.score) << "\n";
    for (const auto& it : r.iterations)
        o << "    depth " << it.depth << "  " << fmt("%7.3f", it.seconds) << " s  "
          << withCommas(it.nodes) << " positions  score " << fmt("%+.1f", it.score)
          << "  best " << moveName(it.best) << "\n";
    o << "summary level=" << cfg.level << " side=" << (side ? "B" : "W") << " ply=" << gamePly
      << " asked_depth=" << askedDepth << " budget=" << fmt("%.3f", budget)
      << " depth=" << r.depthReached << " seldepth=" << st.seldepth
      << " time=" << fmt("%.3f", used) << " nodes=" << total << " qnodes=" << st.qnodes
      << " nps=" << fmt("%.0f", nps) << " tt_hit=" << fmt("%.1f", ttHit)
      << " tt_cut=" << fmt("%.1f", ttCut) << " first_cut=" << fmt("%.1f", first)
      << " ebf=" << fmt("%.2f", ebf) << " root_actions=" << r.rootActions
      << " root_searched=" << r.rootSearched << " score=" << fmt("%.1f", r.score)
      << " stopped=" << (r.stoppedByClock ? 1 : 0) << "\n\n";

    std::string text = o.str();
    if (FILE* f = std::fopen(cfg.logPath.c_str(), "a")) {
        std::fwrite(text.data(), 1, text.size(), f);       // one write per search
        std::fclose(f);
    }
}

// ---------------------------------------------------------------------
// Protocol - unchanged from the old engine
// ---------------------------------------------------------------------

std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> parts;
    std::istringstream in(line);
    std::string word;
    while (in >> word) parts.push_back(word);
    return parts;
}

double numberAfter(const std::string& token, const std::string& key, double fallback) {
    if (token.rfind(key + "=", 0) != 0) return fallback;
    return std::stod(token.substr(key.size() + 1));
}

void printAction(const std::string& tag, const Move& m) {
    std::cout << tag << " move " << m.from << " " << m.to << "\n";
}

void handleSetup(const std::vector<std::string>& parts) {
    for (size_t i = 1; i < parts.size(); ++i) {
        const std::string& t = parts[i];
        auto eq = t.find('=');
        if (eq == std::string::npos) continue;
        std::string key = t.substr(0, eq), val = t.substr(eq + 1);
        if (key == "size") cfg.size = std::min(std::max(std::stoi(val), 3), MAXN);
        else if (key == "canttouch") cfg.generalsCantTouch = val != "0";
        else if (key == "flat") flatBoard = val != "0";
        else if (key == "style_pawn_advance") cfg.pawnAdvance = std::stod(val);
        else if (key == "style_pawn_home") cfg.pawnHome = std::stoi(val);
        else if (key == "style_general_shelter") cfg.shelter = std::stod(val);
        else if (key == "style_general_exposure") cfg.exposure = std::stod(val);
        else if (key == "weight_mobility") cfg.mobility = std::stod(val);
        else if (key == "weight_check") cfg.check = std::stod(val);
        else if (key == "weight_hunt_ramp") cfg.huntRamp = std::stod(val);
        else if (key == "weight_hunt_escape") cfg.huntEscape = std::stod(val);
        else if (key == "weight_hunt_distance") cfg.huntDistance = std::stod(val);
        else if (key == "weight_repetition") cfg.repetition = std::stod(val);
        else if (key == "mate_moves") cfg.mateMoves = std::max(0, std::min(8, std::stoi(val)));
        else if (key == "mate_seconds") cfg.mateSeconds = std::max(0.0, std::stod(val));
        else if (key == "mate_defend") cfg.mateDefend = val != "0" && val != "False";
        else if (key == "aggression") cfg.aggression = std::max(0.0, std::min(100.0, std::stod(val)));
        else if (key.rfind("activity_", 0) == 0) {
            PieceType t2 = typeFromName(key.substr(9));
            if (t2 != NONE) cfg.activity[t2] = std::stod(val);
        }
        else if (key == "branching") cfg.branching = std::stoi(val);
        else if (key == "qply") cfg.qply = std::stoi(val);
        else if (key == "noise") cfg.noise = std::stod(val);
        else if (key == "window") cfg.window = std::stod(val);
        else if (key == "lmr") cfg.lmr = val != "0";
        else if (key == "log") cfg.logPath = val;
        else if (key == "level") cfg.level = val;
        else {
            PieceType t2 = typeFromName(key);
            if (t2 != NONE) cfg.value[t2] = std::stod(val);
        }
    }
    NN = cfg.size | 1;
    RAD = NN / 2;
    board.clear();
    resetTable();
    std::memset(history, 0, sizeof(history));
    std::cout << "ok\n";
}

// position <cell> <cell> ... | <W or B>
// One token per point of the storage array, row by row: "." for empty,
// otherwise w or b and the piece's name ("wPawn").
void handlePosition(const std::string& line) {
    std::vector<std::string> fields;
    std::string chunk;
    std::istringstream in(line.substr(line.find(' ') + 1));
    while (std::getline(in, chunk, '|')) fields.push_back(chunk);
    if (fields.size() < 2) { std::cout << "error position\n"; return; }
    board.clear();
    auto cells = split(fields[0]);
    for (size_t i = 0; i < cells.size() && static_cast<int>(i) < NN * NN; ++i) {
        const std::string& token = cells[i];
        if (token == ".") continue;
        Cell c;
        c.owner = (token[0] == 'w') ? 0 : 1;
        PieceType t = typeFromName(token.substr(1));
        c.type = static_cast<int8_t>(t);
        board.cell[i] = c;
    }
    board.recompute();
    hadRoyal[0] = board.royal[0] >= 0;
    hadRoyal[1] = board.royal[1] >= 0;
    auto turn = split(fields[1]);
    sideToMove = (!turn.empty() && turn[0] == "B") ? 1 : 0;
    std::cout << "ok\n";
}

}  // namespace

int main() {
    std::ios::sync_with_stdio(false);
    cfg.value.fill(0);
    setupZobrist();
    setupWalks();
    resetTable();
    board.clear();
    std::string line;
    while (std::getline(std::cin, line)) {
        auto parts = split(line);
        if (parts.empty()) continue;
        const std::string& cmd = parts[0];
        if (cmd == "quit") break;
        if (cmd == "ping") { std::cout << "pong\n" << std::flush; continue; }
        if (cmd == "setup") { handleSetup(parts); std::cout << std::flush; continue; }
        if (cmd == "position") { handlePosition(line); std::cout << std::flush; continue; }
        if (cmd == "history") {
            // The key of every position the game has been through.
            gameKeys.clear();
            for (size_t i = 1; i < parts.size(); ++i) gameKeys.push_back(std::stoull(parts[i]));
            std::cout << "ok\n" << std::flush;
            continue;
        }
        if (cmd == "moves") {
            // Every legal move - what the differential test compares
            // against Rules.py.
            static Move all[MAX_MOVES];
            int n = generateActions(board, sideToMove, all, MAX_MOVES);
            for (int i = 0; i < n; ++i) printAction("action", all[i]);
            std::cout << "end\n" << std::flush;
            continue;
        }
        if (cmd == "key") {
            std::cout << "key " << hashOf(board, sideToMove) << "\n" << std::flush;
            continue;
        }
        if (cmd == "eval") {
            std::cout << "eval " << evaluate(board, sideToMove) << "\n" << std::flush;
            continue;
        }
        if (cmd == "go") {
            int depth = 6, gamePly = -1;
            double seconds = 5.0;
            for (size_t i = 1; i < parts.size(); ++i) {
                depth = static_cast<int>(numberAfter(parts[i], "depth", depth));
                seconds = numberAfter(parts[i], "seconds", seconds);
                gamePly = static_cast<int>(numberAfter(parts[i], "ply", gamePly));
            }
            SearchResult r = search(board, sideToMove, depth, seconds);
            double used = std::chrono::duration<double>(Clock::now() - started).count();
            long long total = st.nodes + st.qnodes;
            if (!r.found) std::cout << "bestmove none\n";
            else printAction("bestmove", r.best);
            std::cout << "info depth " << r.depthReached << " score " << r.score
                      << " nodes " << total << " seldepth " << st.seldepth
                      << " time " << fmt("%.3f", used)
                      << " nps " << fmt("%.0f", used > 0 ? total / used : 0.0)
                      << " mate " << r.mateIn << " dodged " << r.dodged << "\n" << std::flush;
            writeLog(r, sideToMove, depth, seconds, gamePly, used);
            continue;
        }
        std::cout << "error unknown " << cmd << "\n" << std::flush;
    }
    return 0;
}
