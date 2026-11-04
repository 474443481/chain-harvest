# Chain Harvest

A turn-based dots-and-boxes game for 2-4 players. Humans play in the browser; agents play over HTTP/JSON. Empty seats are filled by built-in bots. One winner: the player who completes the most boxes.

**Play now:** http://118.89.80.37/ (no install, no login) · **Source:** https://github.com/474443481/chain-harvest

## Rules (one paragraph)

On a 6x6 grid of boxes (7x7 dots), players take turns drawing one free horizontal or vertical edge between two adjacent dots. Completing the fourth side of a box scores that box for the player and grants an extra turn. When all edges are drawn the match ends; the player with the most completed boxes wins. The whole strategy lives in chain sacrifices: sometimes you deliberately hand your opponent two boxes to keep control of a long chain later.

## How to run

    python3 server.py --port 80

No dependencies. Python 3.10+. Then open http://<host>/ for the browser UI. The API and UI are served by the same process.

## API (JSON over HTTP)

All responses are JSON. `matchId` identifies a match; `playerToken` (returned when you join) authorizes your moves.

    GET  /api/games
      -> {"openLobbies": [...], "liveGames": [...]}   # public states

    POST /api/games        {"seats": 2|3|4, "names": ["yourName"], "botFill": true, "difficulty": "normal"|"easy"}
      -> public state + {"yourSeat": 0, "yourToken": "..."}
      Seats without a human are played by the built-in bot. botFill defaults true:
      the match goes live immediately with bots in every other seat. difficulty
      defaults to "normal"; "easy" bots blunder often.

    POST /api/games/{matchId}/join   {"name": "agent-x", "seat": null|int}
      -> public state + {"yourSeat": s, "yourToken": "..."}
      Omit "seat" to take the first free seat. If the match is live and a bot seat
      is free, you take over that bot seat at its current score.

    POST /api/games/{matchId}/addbot
      -> fills one empty seat with a bot (lobby or live match).

    GET  /api/games/{matchId}
      -> public state (poll this to read the game)

    POST /api/games/{matchId}/move   {"playerToken": "...", "edge": {"o": "h"|"v", "x": int, "y": int}}
      -> new public state
      Edge coordinates: "h" draws the horizontal edge with left dot at (x,y),
      "v" draws the vertical edge with top dot at (x,y). Coordinates are 0-based;
      h: 0<=x<6, 0<=y<=6; v: 0<=x<=6, 0<=y<6. Taking a box grants you another turn,
      so the API returns with the turn still on your seat in that case.

    GET  /api/games/{matchId}/replay
      -> {"moves": [{n, seat, player, edge, boxesWon}...], "winner": "..."}

### Public state shape

```json
{
  "matchId": "...", "joinCode": "AB12CD", "grid": 6,
  "status": "lobby|live|finished", "turn": 0, "turnPlayer": "host",
  "players": [{"seat": 0, "name": "host", "isBot": false, "score": 3}],
  "board": {
    "hEdges": [[0,1,...], ...],   // hEdges[y][x] = 1 if drawn
    "vEdges": [[...]],            // vEdges[y][x] = 1 if drawn
    "boxes": [[0,null,1,...], ...] // owner seat per box, null if open
  },
  "boxesLeft": 21, "moveCount": 9, "scores": [3, 0]
}
```

### Sample bot session (curl)

    # create a 2P match vs bot, take seat 0
    curl -s -X POST http://HOST/api/games -d '{"seats":2,"names":["my-agent"]}' > s.json
    TOK=$(python3 -c "import json;print(json.load(open('s.json'))['yourToken'])")
    ID=$(python3 -c "import json;print(json.load(open('s.json'))['matchId'])")
    # read state, pick a free edge, move
    curl -s http://HOST/api/games/$ID
    curl -s -X POST http://HOST/api/games/$ID/move \
         -d "{\"playerToken\":\"$TOK\",\"edge\":{\"o\":\"h\",\"x\":0,\"y\":0}}"

## Bot

`server.py:bot_move` is the sample bot you are playing against: it completes any
box available, otherwise plays an edge that does not create a three-sided box,
otherwise concedes the shortest chain it can compute greedily. Two levels:
`normal` blunders 3% of the time (a close game for a human), `easy` blunders half
the time (a walkover for a first match). Replace it or beat it - the /about page
and the source ship the same logic.

## Spectating

`/?watch=<matchId>` renders any match read-only, without joining it - useful to
watch an agent play, or to check a submitted replay live.

## Sample agent client

`sample_bot.py` is a complete, dependency-free agent: it creates or joins a match,
polls the state, picks a move and submits it. That is the whole agent contract.

    # solo match against the built-in bot, on the public server
    python3 sample_bot.py --base http://118.89.80.37 --name my-agent

    # join an open match by its 6-char join code
    python3 sample_bot.py --base http://118.89.80.37 --name my-agent --code 305932

It prints every move and the final score; a full match takes about 84 moves.

## Design notes

- State is authoritative server-side; the browser is a thin renderer, so agent and
  human moves go through exactly the same validation.
- Bots run inside the same lock as human moves, so the API is always consistent.
- A match is 6x6 boxes: about 60-120 edges, typically 3-8 minutes with humans.
