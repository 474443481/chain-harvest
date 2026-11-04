/* Chain Harvest browser client: polls state, draws the board, sends moves. */
let matchId = null, myToken = null, mySeat = null, state = null;

const $ = (id) => document.getElementById(id);

const CELL_MAX = 92, PAD = 26;
let CELL = 68;
const colors = ["#6cb2ff", "#ffd166", "#8f8", "#ff8f8f"];

/* A blank 6x6 board so the landing page shows the game instead of an empty panel. */
function emptyState() {
  const n = 7, z = () => Array.from({ length: n }, () => Array(n).fill(0));
  return {
    matchId: null, joinCode: "", grid: 6, status: "lobby", turn: 0, turnPlayer: "",
    players: [], scores: [], boxesLeft: 36, moveCount: 0, log: [],
    board: { hEdges: z(), vEdges: z(), boxes: Array.from({ length: 6 }, () => Array(6).fill(null)) },
  };
}

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
  const difficulty = $("level") ? $("level").value : "normal";
  const st = await api("POST", "/api/games", { seats, names: [name], botFill: true, difficulty });
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
  $("log").style.display = "";
  history.replaceState(null, "", "#" + st.joinCode);
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

function fitCanvas(g) {
  // keep the whole board on screen: bounded by the column width and the viewport height
  const availW = Math.min(window.innerWidth - 96, 560);
  const availH = Math.max(280, window.innerHeight - 340);
  const side = Math.min(availW, availH);
  CELL = Math.max(34, Math.min(CELL_MAX, Math.floor((side - PAD * 2) / g)));
  const c = $("board"), need = PAD * 2 + CELL * g;
  if (c.width !== need) { c.width = need; c.height = need; }
  c.style.width = need + "px"; c.style.height = need + "px";
}

function draw() {
  const st = state || emptyState();
  const c = $("board"), ctx = c.getContext("2d");
  const g = st.grid;
  fitCanvas(g);
  ctx.clearRect(0, 0, c.width, c.height);

  // boxes
  for (let y = 0; y < g; y++) for (let x = 0; x < g; x++) {
    const owner = st.board.boxes[y][x];
    if (owner !== null && owner !== undefined) {
      ctx.fillStyle = colors[owner % colors.length] + "44";
      ctx.fillRect(PAD + x * CELL, PAD + y * CELL, CELL, CELL);
      ctx.fillStyle = colors[owner % colors.length];
      ctx.font = Math.round(CELL * 0.3) + "px sans-serif";
      ctx.fillText(String.fromCharCode(65 + owner), PAD + x * CELL + CELL / 2 - 7, PAD + y * CELL + CELL / 2 + 8);
    }
  }
  // faint grid of playable edges
  ctx.lineWidth = 1;
  for (let y = 0; y <= g; y++) for (let x = 0; x <= g; x++) {
    if (x < g && !st.board.hEdges[y][x]) line(ctx, PAD + x * CELL + 6, PAD + y * CELL, PAD + (x + 1) * CELL - 6, PAD + y * CELL, "#233040");
    if (y < g && !st.board.vEdges[y][x]) line(ctx, PAD + x * CELL, PAD + y * CELL + 6, PAD + x * CELL, PAD + (y + 1) * CELL - 6, "#233040");
  }
  // edges
  ctx.lineWidth = 5; ctx.lineCap = "round";
  for (let y = 0; y <= g; y++) for (let x = 0; x <= g; x++) {
    if (st.board.hEdges[y][x]) line(ctx, PAD + x * CELL, PAD + y * CELL, PAD + (x + 1) * CELL, PAD + y * CELL, "#dfe9f3");
    if (st.board.vEdges[y][x]) line(ctx, PAD + x * CELL, PAD + y * CELL, PAD + x * CELL, PAD + (y + 1) * CELL, "#dfe9f3");
  }
  // dots
  ctx.fillStyle = "#9fb3c8";
  for (let y = 0; y <= g; y++) for (let x = 0; x <= g; x++) {
    ctx.beginPath(); ctx.arc(PAD + x * CELL, PAD + y * CELL, 4.5, 0, 7); ctx.fill();
  }
  // my-turn highlight
  if (st.status === "live" && mySeat !== null && st.turn === mySeat) {
    ctx.strokeStyle = colors[mySeat % colors.length];
    ctx.lineWidth = 2;
    ctx.strokeRect(3, 3, c.width - 6, c.height - 6);
  }

  // scores, status, log
  $("scores").innerHTML = st.players.length
    ? st.players.map(p =>
      `<span style="color:${colors[p.seat % colors.length]}">${escapeHtml(p.name)}${p.seat === mySeat ? " (you)" : p.isBot ? " (bot)" : ""}: <b>${p.score}</b></span>`).join("")
      + (st.difficulty === "easy" ? ` <span class="muted">easy bot</span>` : "")
    : `<span class="muted">no match yet — create one above to start playing</span>`;

  $("status").textContent =
    !state ? "" :
    st.status === "lobby" ? "Waiting in lobby… share code " + st.joinCode :
    st.status === "finished" ? "Finished — " + (st.winnerText || "match over") :
    (st.turnPlayer + " to move" + (st.turn === mySeat ? " — YOUR TURN" : ""));

  const last = (st.log || []).slice().reverse();
  $("log").innerHTML = last.length
    ? "<b>last moves</b><br>" + last.map(m =>
      `<span style="color:${colors[(m.seat || 0) % colors.length]}">${escapeHtml(m.player)}</span> ${m.edge.o === "h" ? "horizontal" : "vertical"} (${m.edge.x},${m.edge.y})${m.boxesWon ? " <b>+" + m.boxesWon + " box</b>" : ""}`).join("<br>")
    : "<span class='muted'>move log appears here once play starts</span>";
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
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
  // find nearest free edge within 18px
  let best = null;
  for (let y = 0; y <= g; y++) for (let x = 0; x <= g; x++) {
    const cand = [];
    if (x < g && !state.board.hEdges[y][x]) cand.push({ o: "h", x, y, mx: PAD + x * CELL + CELL / 2, my: PAD + y * CELL });
    if (y < g && !state.board.vEdges[y][x]) cand.push({ o: "v", x, y, mx: PAD + x * CELL, my: PAD + y * CELL + CELL / 2 });
    for (const e of cand) {
      const d = Math.hypot(px - e.mx, py - e.my);
      if (d < 18 && (!best || d < best.d)) best = { ...e, d };
    }
  }
  if (!best) return;
  try {
    state = await api("POST", `/api/games/${matchId}/move`,
      { playerToken: myToken, edge: { o: best.o, x: best.x, y: best.y } });
    draw();
  } catch (e) { /* shown */ }
});

window.addEventListener("resize", () => draw());

async function boot() {
  draw();
  try {
    const list = await api("GET", "/api/games");
    const rows = [];
    for (const g of [...(list.openLobbies || []), ...(list.liveGames || [])].slice(0, 8)) {
      rows.push(`<tr><td>${g.joinCode}</td><td>${g.status}</td><td>${g.players.length}P</td><td><a href="#" onclick="quickJoin('${g.matchId}');return false">join</a></td><td><a href="/api/games/${g.matchId}">state</a></td></tr>`);
    }
    $("lobbyList").innerHTML = rows.length
      ? `<table>${rows.join("")}</table>` : "no public matches right now — create the first one";
  } catch (e) { $("lobbyList").textContent = "lobby unavailable"; }

  const code = (location.hash || "").replace("#", "").toUpperCase();
  if (code) { $("joinCode").value = code; }

  // spectate a live match: /?watch=<matchId>
  const watch = new URLSearchParams(location.search).get("watch");
  if (watch) {
    matchId = watch; myToken = null; mySeat = null;
    $("lobby").style.display = "none";
    loop();
  }
}

async function quickJoin(id) {
  const st = await api("POST", `/api/games/${id}/join`, { name: $("name").value || "human" });
  enter(st);
}

boot();
