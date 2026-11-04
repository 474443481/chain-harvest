#!/usr/bin/env python3
"""sample_bot.py - a minimal agent client for Chain Harvest.

Shows everything an AI agent needs: create/join a match, read state, submit moves.
Uses only the standard library.

    # play a full solo match against the built-in bot
    python3 sample_bot.py --base http://localhost:8080 --name my-agent

    # join someone else's match by code
    python3 sample_bot.py --base http://localhost:8080 --name my-agent --code 305932
"""
import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request

GRID = 6


def call(base, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200]}


def free_edges(state):
    """All unset edges as (o, x, y). h: 7 rows x 6 cols, v: 6 rows x 7 cols."""
    out = []
    for y in range(GRID + 1):
        for x in range(GRID):
            if not state["hEdges"][y][x]:
                out.append(("h", x, y))
    for y in range(GRID):
        for x in range(GRID + 1):
            if not state["vEdges"][y][x]:
                out.append(("v", x, y))
    return out


def box_sides(state, cx, cy):
    return (state["hEdges"][cy][cx] + state["hEdges"][cy + 1][cx]
            + state["vEdges"][cy][cx] + state["vEdges"][cy][cx + 1])


def pick_move(state):
    """Tiny heuristic: complete a box, else avoid handing one over, else random."""
    edges = free_edges(state)
    boxes = state["board"]["boxes"]
    for o, x, y in edges:
        probe = json.loads(json.dumps(state))
        probe["hEdges" if o == "h" else "vEdges"][y][x] = 1
        cells = [(x, y - 1), (x, y)] if o == "h" else [(x - 1, y), (x, y)]
        for cx, cy in cells:
            if 0 <= cx < GRID and 0 <= cy < GRID and boxes[cy][cx] is None:
                if box_sides(probe, cx, cy) == 4:
                    return o, x, y
    safe = []
    for o, x, y in edges:
        probe = json.loads(json.dumps(state))
        probe["hEdges" if o == "h" else "vEdges"][y][x] = 1
        if not any(0 <= cx < GRID and 0 <= cy < GRID and boxes[cy][cx] is None
                   and box_sides(probe, cx, cy) == 3
                   for cx in range(GRID + 1) for cy in range(GRID + 1)):
            safe.append((o, x, y))
    return random.choice(safe or edges)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--name", default="sample-bot")
    ap.add_argument("--code", help="join an existing match by its 6-char join code")
    ap.add_argument("--seats", type=int, default=2)
    ap.add_argument("--poll", type=float, default=0.6, help="seconds between polls")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    if args.code:
        st, lobby = call(base, "GET", "/api/games")
        match = next((g for g in lobby.get("openLobbies", [])
                      if g.get("joinCode", "").upper() == args.code.upper()), None)
        if not match:
            print("no open match with code", args.code)
            return 1
        st, state = call(base, "POST", "/api/games/%s/join" % match["matchId"], {"name": args.name})
        if st != 200:
            print("join failed", st, state)
            return 1
        match_id, token = match["matchId"], state["yourToken"]
    else:
        st, state = call(base, "POST", "/api/games",
                         {"seats": args.seats, "names": [args.name], "botFill": True})
        if st != 200:
            print("create failed", st, state)
            return 1
        match_id, token = state["matchId"], state["yourToken"]
        print("match %s (%s)" % (match_id, state.get("joinCode")))

    seat = state["yourSeat"]
    while state["status"] != "finished":
        if state["turn"] != seat:
            time.sleep(args.poll)
            st, state = call(base, "GET", "/api/games/%s" % match_id)
            continue
        o, x, y = pick_move(state)
        st, state = call(base, "POST", "/api/games/%s/move" % match_id,
                         {"playerToken": token, "edge": {"o": o, "x": x, "y": y}})
        if st != 200:
            print("move rejected", st, state)
            return 1
        print("played %s %d %d -> scores %s" % (o, x, y, state["scores"]))

    st, replay = call(base, "GET", "/api/games/%s/replay" % match_id)
    print("finished. scores=%s winner=%s moves=%d"
          % (state["scores"], replay.get("winner"), len(replay.get("moves") or [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
