/* Chain Harvest browser client: polls state, draws the board, sends moves. */
let matchId = null, myToken = null, mySeat = null, state = null;

const $ = (id) => document.getElementById(id);

async function api(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { $("err").textContent = j.error || ("HTTP " + r.status); throw new Error(j.error); }
  $("err").textContent = "";
  return j;
}

async function createGame() {
  const name = $("name").value || "human";
  const seats = parseInt($("seats").value, 10);
  const st = await api("POST", "/api/games", { seats, names: [name], botFill: true });
  enter(st);
}

async function joinByCode() {
  const code = ($("joinCode").value || "").trim().toUpperCase();
  const list = await api("GET", "/api/games");
  const all = [...(list.openLobbies || []), ...(list.liveGames || [])];
  const g = all.find((x) => x.joinCode === code);
  if (!g) { $("err").textContent = "no open match with that code"; return; }
  const st = await api("POST", `/api/games/${g.matchId}/join`, { name: $("name").value || "human" });
  enter(st);
}

function enter(st) {
  matchId = st.matchId; myToken = st.yourToken; mySeat = st.yourSeat;
  state = st;
  $("lobby").style.display = "none";
  draw(); loop();
}

async function loop() {
  if (!matchId) return;
  try {
    state = await api("GET", `/api/games/${matchId}`);
    draw();
  } catch (e) { /* transient */ }
  setTimeout(loop, state && state.status === "finished" ? 3000 : 1200);
}

const CELL = 68, PAD = 26;
const colors = ["#6cb2ff", "#ffd166", "#8f8", "#ff8f8f"];

function draw() {
  if (!state) return;
  const c = $("board"), ctx = c.getContext("2d");
  const g = state.grid;
  const need = PAD * 2 + CELL * g;
  if (need !== c.width) { c.width = need; c.height = need; }
  ctx.clearRect(0, 0, c.width, c.height);

  // boxes
  for (let y = 0; y < g; y++) for (let x = 0; x < g; x++) {
    const owner = state.board.boxes[y][x];
    if (owner !== null && owner !== undefined) {
      ctx.fillStyle = colors[owner % colors.length] + "55";
      ctx.fillRect(PAD + x * CELL, PAD + y * CELL, CELL, CELL);
      ctx.fillStyle = colors[owner % colors.length];
      ctx.font = "20px sans-serif";
      ctx.fillText(String.fromCharCode(65 + owner), PAD + x * CELL + CELL / 2 - 6, PAD + y * CELL + CELL / 2 + 7);
    }
  }
  // edges
  ctx.lineWidth = 4; ctx.lineCap = "round";
  for (let y = 0; y <= g; y++) for (let x = 0; x <= g; x++) {
    if (state.board.hEdges[y][x]) line(ctx, PAD + x * CELL, PAD + y * CELL, PAD + (x + 1) * CELL, PAD + y * CELL, "#dfe9f3");
    if (state.board.vEdges[y][x]) line(ctx, PAD + x * CELL, PAD + y * CELL, PAD + x * CELL, PAD + (y + 1) * CELL, "#dfe9f3");
  }
  // dots
  ctx.fillStyle = "#9fb3c8";
  for (let y = 0; y <= g; y++) for (let x = 0; x <= g; x++) {
    ctx.beginPath(); ctx.arc(PAD + x * CELL, PAD + y * CELL, 4, 0, 7); ctx.fill();
  }
  // my turn highlight
  if (state.status === "live" && mySeat !== null && state.turn === mySeat) {
    ctx.strokeStyle = colors[mySeat % colors.length];
    ctx.lineWidth = 2;
    ctx.strokeRect(4, 4, c.width - 8, c.height - 8);
  }
  // scores + status
  $("scores").innerHTML = state.players.map(p =>
    `<span style="color:${colors[p.seat % colors.length]}">${p.name}${p.seat === mySeat ? " (you)" : ""}: <b>${p.score}</b></span>`).join("");
  $("status").textContent =
    state.status === "lobby" ? "Waiting in lobby… share code " + state.joinCode :
    state.status === "finished" ? "Finished — " + (state.winnerText || "") :
    (state.turnPlayer + " to move" + (state.turn === mySeat ? " — YOUR TURN" : ""));
  const rep = state.moveCount ? `${state.moveCount} moves · box left: ${state.boxesLeft}` : "";
  $("hint").textContent = rep + " · your seat: " + (mySeat === null ? "spectator" : mySeat);
}

function line(ctx, x1, y1, x2, y2, color) {
  ctx.strokeStyle = color;
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
}

$("board").addEventListener("click", async (ev) => {
  if (!state || state.status !== "live") return;
  if (mySeat === null || state.turn !== mySeat) return;
  const r = $("board").getBoundingClientRect();
  const px = ev.clientX - r.left, py = ev.clientY - r.top;
  const g = state.grid;
  // find nearest edge within 16px
  let best = null;
  for (let y = 0; y <= g; y++) for (let x = 0; x <= g; x++) {
    const cand = [];
    if (x < g) cand.push({ o: "h", x, y, mx: PAD + x * CELL + CELL / 2, my: PAD + y * CELL });
    if (y < g) cand.push({ o: "v", x, y, mx: PAD + x * CELL, my: PAD + y * CELL + CELL / 2 });
    for (const e of cand) {
      const d = Math.hypot(px - e.mx, py - e.my);
      if (d < 16 && (!best || d < best.d)) best = { ...e, d };
    }
  }
  if (!best) return;
  try {
    state = await api("POST", `/api/games/${matchId}/move`,
      { playerToken: myToken, edge: { o: best.o, x: best.x, y: best.y } });
    draw();
  } catch (e) { /* shown */ }
});

async function boot() {
  try {
    const list = await api("GET", "/api/games");
    const rows = [];
    for (const g of [...(list.openLobbies || []), ...(list.liveGames || [])].slice(0, 8)) {
      rows.push(`<tr><td>${g.joinCode}</td><td>${g.status}</td><td>${g.players.length}P</td><td><a href="#" onclick="quickJoin('${g.matchId}');return false">join</a></td><td><a href="/api/games/${g.matchId}">state</a></td></tr>`);
    }
    $("lobbyList").innerHTML = rows.length
      ? `<table>${rows.join("")}</table>` : "no public matches yet — create one";
  } catch (e) { $("lobbyList").textContent = "lobby unavailable"; }
}

async function quickJoin(id) {
  const st = await api("POST", `/api/games/${id}/join`, { name: $("name").value || "human" });
  enter(st);
}

boot();
