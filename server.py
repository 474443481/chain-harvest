#!/usr/bin/env python3
"""Chain Harvest — turn-based dots-and-boxes for 2-4 humans and agents.

One process serves the browser UI, the JSON API, and the bots.
Stdlib only. Run: python3 server.py [--port 80]
"""
import json
import os
import random
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GRID = 6  # 6x6 boxes -> 7x7 dots
HERE = os.path.dirname(os.path.abspath(__file__))

GAMES = {}
LOCK = threading.Lock()


def new_board():
    return {
        "h": [[False] * (GRID + 1) for _ in range(GRID + 1)],  # h[y][x]: edge from (x,y) to (x+1,y)
        "v": [[False] * (GRID + 1) for _ in range(GRID + 1)],  # v[y][x]: edge from (x,y) to (x,y+1)
        "boxes": [[None] * GRID for _ in range(GRID)],          # owner seat index or None
    }


class Game:
    def __init__(self, seats, names, bot_fill=True):
        self.id = uuid.uuid4().hex[:12]
        self.join_code = uuid.uuid4().hex[:6].upper()
        self.seats = seats
        self.names = list(names) + [None] * (seats - len(names))
        self.tokens = {}   # seat -> player token (humans only)
        self.board = new_board()
        self.turn = 0
        self.scores = [0] * seats
        self.moves = []    # move log entries
        self.status = "lobby"
        self.created = time.time()
        self.bot_fill = bot_fill
        self.difficulty = "normal"
        self.pending = 0   # extra turns earned by scoring

    def seat_name(self, i):
        if self.names[i]:
            return self.names[i]
        # an unnamed seat is a bot once the match is live, an open seat while it waits
        return f"bot-{i}" if self.status != "lobby" else f"open-{i}"

    def public_state(self):
        return {
            "matchId": self.id,
            "joinCode": self.join_code,
            "game": "Chain Harvest (dots-and-boxes)",
            "grid": GRID,
            "status": self.status,
            "difficulty": getattr(self, "difficulty", "normal"),
            "turn": self.turn,
            "turnPlayer": self.seat_name(self.turn),
            "players": [
                {"seat": i, "name": self.seat_name(i), "isBot": self.tokens.get(i) is None and self.status != "lobby",
                 "score": self.scores[i]}
                for i in range(self.seats)
            ],
            "scores": self.scores,
            "board": {
                "hEdges": [[1 if c else 0 for c in row] for row in self.board["h"]],
                "vEdges": [[1 if c else 0 for c in row] for row in self.board["v"]],
                "boxes": self.board["boxes"],
            },
            "boxesLeft": sum(1 for row in self.board["boxes"] for c in row if c is None),
            "moveCount": len(self.moves),
            "winnerText": self.winner_text() if self.game_over() else None,
            "log": [{"n": m["n"], "seat": m["seat"], "player": m["player"], "edge": m["edge"], "boxesWon": m["boxesWon"]}
                    for m in self.moves[-6:]],
            "hEdges": [[1 if c else 0 for c in row] for row in self.board["h"]],
            "vEdges": [[1 if c else 0 for c in row] for row in self.board["v"]],
        }

    def edge_free(self, o, x, y):
        if o == "h":
            return 0 <= x < GRID and 0 <= y <= GRID and not self.board["h"][y][x]
        return 0 <= x <= GRID and 0 <= y < GRID and not self.board["v"][y][x]

    def apply_edge(self, o, x, y, seat):
        if o == "h":
            self.board["h"][y][x] = True
        else:
            self.board["v"][y][x] = True
        gained = 0
        if o == "h":
            cells = [(x, y - 1), (x, y)]
        else:
            cells = [(x - 1, y), (x, y)]
        for cx, cy in cells:
            if 0 <= cx < GRID and 0 <= cy < GRID and self.board["boxes"][cy][cx] is None:
                if self.box_sides(cx, cy) == 4:
                    self.board["boxes"][cy][cx] = seat
                    gained += 1
        self.scores[seat] += gained
        self.moves.append({"n": len(self.moves) + 1, "seat": seat,
                           "player": self.names[seat] or f"bot-{seat}",
                           "edge": {"o": o, "x": x, "y": y}, "boxesWon": gained})
        return gained

    def box_sides(self, cx, cy):
        b = self.board
        return (int(b["h"][cy][cx]) + int(b["h"][cy + 1][cx])
                + int(b["v"][cy][cx]) + int(b["v"][cy][cx + 1]))

    def legal_moves(self):
        out = []
        for y in range(GRID + 1):
            for x in range(GRID + 1):
                if self.edge_free("h", x, y):
                    out.append(("h", x, y))
                if self.edge_free("v", x, y):
                    out.append(("v", x, y))
        return out

    def game_over(self):
        return not self.legal_moves()

    def winner_text(self):
        best = max(self.scores)
        seats = [i for i, s in enumerate(self.scores) if s == best]
        names = [self.names[i] or f"bot-{i}" for i in seats]
        return "Tie: " + ", ".join(names) if len(seats) > 1 else f"{names[0]} wins {best} boxes"


# ---------------- bot ----------------

def chain_boxes(g, start, seen):
    """Collect connected boxes with 3 sides (consumable now) or track chains loosely."""
    return []


def bot_move(g, seat):
    moves = g.legal_moves()
    if not moves:
        return None
    # easy bots blunder on purpose, normal bots now and then, so matches stay winnable
    level = getattr(g, "difficulty", "normal")
    if level == "easy" and random.random() < 0.5:
        return random.choice(moves)
    if level == "normal" and random.random() < 0.03:
        return random.choice(moves)
    # 1) take any box
    for o, x, y in moves:
        probe = clone(g)
        probe.apply_edge(o, x, y, seat)
        if probe.scores[seat] > g.scores[seat]:
            return (o, x, y)
    # 2) safe move: does not hand a box (no box reaches 3 sides)
    safe = []
    for o, x, y in moves:
        probe = clone(g)
        probe.apply_edge(o, x, y, seat)
        if not any(probe.box_sides(cx, cy) == 3
                   for cy in range(GRID) for cx in range(GRID)
                   if probe.board["boxes"][cy][cx] is None):
            safe.append((o, x, y))
    if safe:
        return random.choice(safe)
    # 3) all moves concede; concede the smallest chain (count boxes reachable)
    def concede_size(o, x, y):
        probe = clone(g)
        probe.apply_edge(o, x, y, seat)
        # count boxes the opponent could take in a greedy sweep
        taken = 0
        while True:
            for mo, mx, my in probe.legal_moves():
                p2 = clone(probe)
                p2.apply_edge(mo, mx, my, (seat + 1) % probe.seats)
                if p2.scores[(seat + 1) % probe.seats] > probe.scores[(seat + 1) % probe.seats]:
                    probe = p2
                    taken += p2.moves[-1]["boxesWon"]
                    break
            else:
                break
        return taken
    moves.sort(key=lambda m: concede_size(*m))
    return moves[0]


def clone(g):
    ng = Game.__new__(Game)
    ng.id, ng.join_code, ng.seats = g.id, g.join_code, g.seats
    ng.names, ng.tokens = g.names, g.tokens
    ng.board = {"h": [row[:] for row in g.board["h"]],
                "v": [row[:] for row in g.board["v"]],
                "boxes": [row[:] for row in g.board["boxes"]]}
    ng.turn, ng.scores = g.turn, g.scores[:]
    ng.moves, ng.status = [], g.status
    ng.created, ng.bot_fill, ng.pending = g.created, g.bot_fill, g.pending
    ng.difficulty = getattr(g, "difficulty", "normal")
    return ng


def run_bots(g):
    """While it is a bot seat's turn (or a scoring extra turn of a bot), play."""
    guard = 0
    while not g.game_over() and g.tokens.get(g.turn) is None and g.status == "live":
        if guard > 500:
            break
        guard += 1
        mv = bot_move(g, g.turn)
        if mv is None:
            break
        gained = g.apply_edge(*mv, g.turn)
        if gained == 0:
            g.turn = (g.turn + 1) % g.seats
        # scoring extra turn: bot keeps playing (loop continues)
    if g.game_over() and g.status == "live":
        g.status = "finished"


# ---------------- HTTP ----------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/" or path == "/index.html":
            return self._file("index.html", "text/html; charset=utf-8")
        if path == "/game.js":
            return self._file("game.js", "application/javascript")
        if path == "/about":
            return self._file("README.md", "text/plain; charset=utf-8")
        if path == "/source.zip":
            return self._file("source.zip", "application/zip")
        if path == "/api/games":
            with LOCK:
                lobby = [g.public_state() for g in GAMES.values() if g.status == "lobby"]
                live = [g.public_state() for g in GAMES.values() if g.status == "live"]
            return self._json(200, {"openLobbies": lobby, "liveGames": live})
        if path.startswith("/api/games/"):
            rest = path[len("/api/games/"):]
            parts = rest.split("/")
            gid = parts[0]
            with LOCK:
                g = GAMES.get(gid)
                if not g:
                    return self._json(404, {"error": "no such match"})
                if len(parts) == 1:
                    return self._json(200, g.public_state())
                if parts[1] == "replay":
                    return self._json(200, {"matchId": g.id, "winner": g.winner_text() if g.game_over() else None,
                                            "moves": g.moves})
        return self._json(404, {"error": "not found"})

    def _file(self, name, ctype):
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            return self._json(404, {"error": "missing " + name})
        with open(p, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        path = self.path.split("?")[0]

        if path == "/api/games":
            seats = int(body.get("seats") or 2)
            seats = min(max(seats, 2), 4)
            names = [str(x)[:20] for x in (body.get("names") or [])][:seats]
            with LOCK:
                want_bots = body.get("botFill")
                want_bots = True if want_bots is None else bool(want_bots)
                g = Game(seats, names or ["host"], bot_fill=want_bots)
                g.difficulty = "easy" if str(body.get("difficulty") or "").lower() == "easy" else "normal"
                if names:
                    tok = uuid.uuid4().hex
                    g.tokens[0] = tok
                GAMES[g.id] = g
                if len(names) >= seats or (g.bot_fill and len(names) >= 1):
                    g.status = "live"
                    run_bots(g)
                st = g.public_state()
                st["yourSeat"] = 0 if names else None
                st["yourToken"] = g.tokens.get(0)
            return self._json(200, st)

        if path.startswith("/api/games/") and path.endswith("/join"):
            gid = path.split("/")[3]
            name = str(body.get("name") or "player")[:20]
            with LOCK:
                g = GAMES.get(gid)
                if not g:
                    return self._json(404, {"error": "no such match"})
                if g.status == "finished":
                    return self._json(409, {"error": "match finished"})
                seat = body.get("seat")
                free = [i for i in range(g.seats) if g.tokens.get(i) is None and (g.names[i] is None or g.names[i].startswith("open-"))]
                if seat is not None:
                    seat = int(seat)
                    if seat not in free:
                        return self._json(409, {"error": "seat taken"})
                else:
                    if not free:
                        return self._json(409, {"error": "match full; seats taken by bots or players"})
                    seat = free[0]
                g.names[seat] = name
                tok = uuid.uuid4().hex
                g.tokens[seat] = tok
                humans = sum(1 for i in range(g.seats) if g.tokens.get(i))
                if humans >= 1 and (g.bot_fill or humans == g.seats):
                    g.status = "live"
                    run_bots(g)
                st = g.public_state()
                st["yourSeat"] = seat
                st["yourToken"] = tok
            return self._json(200, st)

        if path.startswith("/api/games/") and path.endswith("/addbot"):
            gid = path.split("/")[3]
            with LOCK:
                g = GAMES.get(gid)
                if not g:
                    return self._json(404, {"error": "no such match"})
                filled = [i for i in range(g.seats) if g.names[i] is not None]
                if len(filled) >= g.seats:
                    return self._json(409, {"error": "no empty seat"})
                seat = next(i for i in range(g.seats) if g.names[i] is None)
                g.names[seat] = f"bot-{seat}"
            return self._json(200, g.public_state())

        if path.startswith("/api/games/") and path.endswith("/move"):
            gid = path.split("/")[3]
            tok = body.get("playerToken")
            seat = body.get("seat")
            edge = body.get("edge") or {}
            o, x, y = edge.get("o"), edge.get("x"), edge.get("y")
            with LOCK:
                g = GAMES.get(gid)
                if not g:
                    return self._json(404, {"error": "no such match"})
                if g.status != "live":
                    return self._json(409, {"error": f"match is {g.status}; join first"})
                if tok:
                    match = [i for i, t in g.tokens.items() if t == tok]
                    if not match:
                        return self._json(403, {"error": "bad playerToken"})
                    seat = match[0]
                if seat is None:
                    return self._json(400, {"error": "need playerToken or seat"})
                seat = int(seat)
                if seat != g.turn:
                    return self._json(409, {"error": f"not your turn; turn={g.turn}"})
                if not g.edge_free(o, x, y):
                    return self._json(409, {"error": "edge taken or out of range"})
                gained = g.apply_edge(o, x, y, seat)
                if gained == 0:
                    g.turn = (g.turn + 1) % g.seats
                run_bots(g)
            return self._json(200, g.public_state())

        return self._json(404, {"error": "not found"})


def main():
    port = 80
    for i, a in enumerate(os.sys.argv):
        if a == "--port":
            port = int(os.sys.argv[i + 1])
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Chain Harvest serving on :{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
