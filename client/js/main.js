let myConnectionId = null;
let myRoomId = null;
let myPlayerName = localStorage.getItem("pokdeng_name") || "";
let userId = localStorage.getItem("pokdeng_user_id");
let sessionToken = localStorage.getItem("pokdeng_session");
let serverAddress = localStorage.getItem("pokdeng_server") || "";
let latestPlayers = [];
let latestState = null;
let lastMyStatus = null;
let peekedCards = [false, false];
let selectedStake = 1000;
let selectedMaxPlayers = 5;
const DEFAULT_TUTORIAL_STEPS = [
  {title:"1. เลือกโหมด", text:"Practice ใช้ฝึกเล่นโดยไม่กระทบ Ranking ส่วน Ranked ใช้ Virtual Coin และบันทึกสถิติการแข่งขัน"},
  {title:"2. เข้าห้อง", text:"สร้างห้องหรือเข้าห้องที่เปิดอยู่ ห้องจะแสดงจำนวนผู้เล่น โหมด และเจ้ามือที่เลือกไว้"},
  {title:"3. วางเดิมพัน", text:"เมื่อเริ่มรอบ คุณจะมีเวลาวางเดิมพัน ระบบจะแจกไพ่เมื่อผู้เล่นที่พร้อมวางเดิมพันครบ"},
  {title:"4. จั่วหรืออยู่", text:"หลังได้รับไพ่ 2 ใบ ถ้าไม่ป๊อก คุณเลือก จั่วใบที่ 3 เพื่อเพิ่มไพ่ หรือ อยู่ เพื่อหยุด"},
  {title:"5. เจ้้ามือตัดสินใจ", text:"เมื่อผู้เล่นทุกคนตัดสินใจแล้ว AI Dealer จะเลือก DRAW หรือ STAND ตาม strategy ที่กำหนด"},
  {title:"6. เปิดไพ่และคิดผล", text:"Server เป็นผู้คำนวณแต้ม ป๊อก เด้ง ผลแพ้ชนะ และเหรียญ จากนั้นเริ่มรอบถัดไป"},
  {title:"7. Fair Dealing", text:"Server ส่ง commitment ของสำรับก่อนเล่น และเปิดข้อมูลสำหรับตรวจสอบย้อนหลังหลังจบรอบ"},
  {title:"8. เล่นเมื่อไรก็ได้", text:"ปิด Tutorial ได้เลย แล้วกดปุ่ม ? ใน Lobby หรือหน้าเกมเพื่อกลับมาอ่านอีกครั้ง"}
];
let tutorialSteps = [...DEFAULT_TUTORIAL_STEPS];
let tutorialPage = 0;
let leaderboardTab = "human";
let leaderboardPeriod = "all";
let reconnecting = false;
let leavingRoom = false;

function makeId() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

if (!userId) {
  userId = makeId();
  localStorage.setItem("pokdeng_user_id", userId);
}

window.addEventListener("DOMContentLoaded", () => {
  const nameInput = document.getElementById("player-name-input");
  const addressInput = document.getElementById("server-address-input");
  nameInput.value = myPlayerName;
  addressInput.value = serverAddress;
  addressInput.placeholder = window.location.hostname || addressInput.placeholder;

  setupStakePresets(); setupBetSlider(); setupModeControls(); setupDealerOptions(); setupTutorial(); setupLeaderboard();

  document.getElementById("connect-btn").addEventListener("click", () => connectFromForm());
  document.getElementById("show-create-room-btn").addEventListener("click", () => UI.showEl(document.getElementById("create-room-form")));
  document.getElementById("close-create-room-btn").addEventListener("click", () => UI.hideEl(document.getElementById("create-room-form")));
  document.getElementById("create-room-btn").addEventListener("click", createRoom);
  document.getElementById("daily-coin-btn").addEventListener("click", () => GameSocket.send("claim_daily", { player_name: myPlayerName }));
  document.getElementById("start-round-btn").addEventListener("click", () => sendAction("start_round", {}));
  document.getElementById("place-bet-btn").addEventListener("click", () => {
    const amount = parseInt(document.getElementById("bet-slider").value, 10);
    if (amount > 0) sendAction("place_bet", { amount });
  });
  document.getElementById("draw-btn").addEventListener("click", () => sendAction("player_draw", {}));
  document.getElementById("stay-btn").addEventListener("click", () => sendAction("player_stay", {}));
  document.getElementById("dealer-draw-btn").addEventListener("click", () => sendAction("dealer_draw", {}));
  document.getElementById("dealer-stay-btn").addEventListener("click", () => sendAction("dealer_stay", {}));
  document.getElementById("leave-room-btn").addEventListener("click", leaveRoom);
  document.getElementById("connect-help-btn").addEventListener("click", () => openTutorial(0));
  document.getElementById("game-tutorial-btn").addEventListener("click", () => openTutorial(0));
  document.getElementById("tutorial-btn").addEventListener("click", () => openTutorial(0));
  document.getElementById("leaderboard-btn").addEventListener("click", openLeaderboard);
  document.getElementById("round-result-close").addEventListener("click", closeModals);

  registerSocketHandlers();
});

function connectFromForm() {
  const name = document.getElementById("player-name-input").value.trim();
  const address = document.getElementById("server-address-input").value.trim();
  if (!name) { document.getElementById("connect-error").textContent = "กรุณาใส่ชื่อผู้เล่น"; return; }
  myPlayerName = name; serverAddress = address;
  localStorage.setItem("pokdeng_name", name); localStorage.setItem("pokdeng_server", address);
  document.getElementById("connect-error").textContent = "";
  GameSocket.connect(address, () => { reconnecting = false; }, (wsUrl) => {
    document.getElementById("connect-error").textContent = `เชื่อมต่อไม่ได้: ${wsUrl}`;
  });
}

function setupDealerOptions() {
  const input = document.getElementById("dealer-strategy-input");
  document.querySelectorAll(".dealer-option").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".dealer-option").forEach(b => {
        const active = b === btn;
        b.classList.toggle("is-selected", active);
        b.setAttribute("aria-checked", active ? "true" : "false");
      });
      input.value = btn.dataset.dealer;
    });
  });
}

function leaveRoom() {
  if (!myRoomId) return;
  leavingRoom = true;
  const btn = document.getElementById("leave-room-btn");
  btn.disabled = true;
  btn.textContent = "กำลังออก...";
  sendAction("leave_room", {});
}

function setupModeControls() {
  document.querySelectorAll(".seat-preset").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".seat-preset").forEach(b => b.classList.remove("is-selected"));
    btn.classList.add("is-selected"); selectedMaxPlayers = parseInt(btn.dataset.max, 10);
  }));
}

function setupStakePresets() {
  const custom = document.getElementById("stake-custom-input");
  document.querySelectorAll(".stake-preset-btn").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".stake-preset-btn").forEach(b => b.classList.remove("is-selected"));
    btn.classList.add("is-selected"); selectedStake = parseInt(btn.dataset.stake, 10); custom.value = "";
  }));
  custom.addEventListener("input", () => { if (parseInt(custom.value, 10) > 0) { selectedStake = parseInt(custom.value, 10); document.querySelectorAll(".stake-preset-btn").forEach(b => b.classList.remove("is-selected")); } });
}

function setupBetSlider() {
  const slider = document.getElementById("bet-slider"); const display = document.getElementById("bet-amount-display");
  slider.addEventListener("input", () => updateBetSliderDisplay(slider, display));
  document.querySelectorAll(".bet-quick").forEach(btn => btn.addEventListener("click", () => {
    const me = latestPlayers.find(p => p.connection_id === myConnectionId); if (!me) return;
    slider.value = Math.max(1, Math.floor(me.balance * parseInt(btn.dataset.percent, 10) / 100)); updateBetSliderDisplay(slider, display);
  }));
}
function updateBetSliderDisplay(slider, display) {
  const max = parseInt(slider.max, 10) || 100, value = parseInt(slider.value, 10) || 0;
  slider.style.setProperty("--fill-percent", `${max ? value / max * 100 : 0}%`); display.innerHTML = UI.moneyLabel(value);
}

function createRoom() {
  const roomId = document.getElementById("room-id-input").value.trim();
  const mode = document.querySelector('input[name="game-mode"]:checked').value;
  const dealer = document.getElementById("dealer-strategy-input").value;
  if (!roomId) { UI.showLobbyError("กรุณาใส่ชื่อห้อง"); return; }
  if (mode === "ranked" && Number(document.querySelector("#profile-card .profile-coins")?.dataset.coins || 0) <= 0) {
    UI.showLobbyError("Ranked ต้องมี Virtual Coin ก่อน — กด Daily +100 ได้ทุกวัน"); return;
  }
  UI.showLobbyError("");
  GameSocket.send("create_room", { room_id: roomId, player_name: myPlayerName, user_id: userId, stake: selectedStake, max_players: selectedMaxPlayers, dealer_strategy: dealer, mode });
}

function sendAction(type, data = {}) {
  GameSocket.send(type, { ...data, action_id: makeId(), round_number: latestState?.round_number });
}

function registerSocketHandlers() {
  GameSocket.on("connection_open", () => {
    const storedRoom = localStorage.getItem("pokdeng_room");
    if (sessionToken && storedRoom) {
      GameSocket.send("resume_session", { token: sessionToken });
    } else {
      GameSocket.send("login", { user_id: userId, player_name: myPlayerName });
    }
    document.getElementById("connection-banner").classList.add("hidden");
  });

  GameSocket.on("session", msg => {
    sessionToken = msg.token;
    localStorage.setItem("pokdeng_session", sessionToken);
    UI.renderProfile(msg.profile);
    UI.showScreen("room-list-screen");
    GameSocket.send("get_leaderboards", {period: leaderboardPeriod});
    GameSocket.send("get_tutorial", {});

    // Intentional leave must never resume the old room.
    if (leavingRoom) {
      localStorage.removeItem("pokdeng_room");
      myRoomId = null;
      leavingRoom = false;
    }
  });

  GameSocket.on("profile", msg => UI.renderProfile(msg.data));

  GameSocket.on("room_list", msg => {
    UI.renderRoomList(msg.data, roomId => GameSocket.send("join_room", { room_id: roomId, player_name: myPlayerName, user_id: userId }));
    if (leavingRoom) {
      localStorage.removeItem("pokdeng_room");
      myRoomId = null;
      latestState = null;
      latestPlayers = [];
      document.getElementById("leave-room-btn").disabled = false;
      document.getElementById("leave-room-btn").textContent = "ออกจากห้อง";
      UI.showScreen("room-list-screen");
      UI.showToast("ออกจากห้องแล้ว");
      leavingRoom = false;
    }
  });

  GameSocket.on("room_joined", msg => {
    myConnectionId = msg.connection_id;
    myRoomId = msg.room_id;
    leavingRoom = false;
    localStorage.setItem("pokdeng_room", myRoomId);
    document.getElementById("leave-room-btn").disabled = false;
    document.getElementById("leave-room-btn").textContent = "ออกจากห้อง";
    document.getElementById("room-label").textContent = `ห้อง ${myRoomId}`;
    UI.showScreen("game-screen");
    if (!localStorage.getItem("pokdeng_tutorial_prompt_v2")) {
      GameSocket.send("get_tutorial", {});
    }
  });

  GameSocket.on("left_room", () => {
    localStorage.removeItem("pokdeng_room");
    myRoomId = null;
    latestState = null;
    latestPlayers = [];
    document.getElementById("leave-room-btn").disabled = false;
    document.getElementById("leave-room-btn").textContent = "ออกจากห้อง";
    UI.showScreen("room-list-screen");
    UI.showToast("ออกจากห้องแล้ว");
    leavingRoom = false;
  });

  GameSocket.on("error", msg => {
    UI.showLobbyError(msg.message);
    UI.showToast(msg.message, true);
    if (leavingRoom) {
      leavingRoom = false;
      const btn = document.getElementById("leave-room-btn");
      btn.disabled = false;
      btn.textContent = "ออกจากห้อง";
    }
    if (/Session|ห้องเดิม/.test(msg.message)) {
      localStorage.removeItem("pokdeng_room");
      sessionToken = null;
      localStorage.removeItem("pokdeng_session");
    }
  });

  GameSocket.on("game_state", msg => renderGameState(msg.data));

  GameSocket.on("round_result", msg => {
    UI.renderRevealAtSeats(msg.data, latestPlayers, myConnectionId);
    UI.showRoundSummary(msg.data, myConnectionId);
    GameSocket.send("get_leaderboards", {period: leaderboardPeriod});
  });

  GameSocket.on("leaderboards", msg => UI.renderLeaderboards(msg.data, leaderboardTab));

  GameSocket.on("tutorial", msg => {
    tutorialSteps = msg.data.steps?.length ? msg.data.steps : [...DEFAULT_TUTORIAL_STEPS];
    renderTutorial();
    if (!localStorage.getItem("pokdeng_tutorial_prompt_v2")) {
      openTutorialChoice();
      localStorage.setItem("pokdeng_tutorial_prompt_v2", "1");
    }
  });

  GameSocket.on("connection_lost", () => showConnectionBanner("การเชื่อมต่อหลุด — กำลัง reconnect..."));
}
function renderGameState(state) {
  latestState = state; latestPlayers = state.players || [];
  UI.renderTable(latestPlayers, myConnectionId); UI.renderBetPile(latestPlayers); UI.renderPhase(state);
  const me = latestPlayers.find(p => p.connection_id === myConnectionId);
  if (!me) return;
  const isDealer = !!me.is_dealer;
  document.getElementById("round-label").textContent = `Round ${state.round_number} • ${state.mode === "ranked" ? "🏆 Ranked" : "🎮 Practice"}`;
  document.getElementById("dealer-info").innerHTML = `<b>Dealer:</b> ${UI.escape(state.dealer_strategy)}${state.dealer_reason ? ` <span>• ${UI.escape(state.dealer_reason)}</span>` : ""}`;

  const startBtn = document.getElementById("start-round-btn");
  startBtn.classList.toggle("hidden", !(isDealer && ["waiting", "reveal"].includes(state.state)));

  const betting = document.getElementById("betting-section");
  const showBet = state.state === "betting" && !isDealer && !me.has_bet && me.status !== "out_of_money";
  if (showBet) {
    const slider = document.getElementById("bet-slider"); slider.max = me.balance; slider.step = Math.max(1, Math.floor(me.balance / 20));
    if (!parseInt(slider.value, 10)) slider.value = Math.min(me.balance, Math.max(1, Math.floor(me.balance * .25)));
    document.getElementById("my-balance-label").innerHTML = UI.moneyLabel(me.balance); updateBetSliderDisplay(slider, document.getElementById("bet-amount-display")); UI.showEl(betting);
  } else UI.hideEl(betting);

  if (me.hand) UI.renderOwnHand(document.getElementById("my-hand"), me.hand, peekedCards, { animate: state.state === "dealing" && latestState?.round_number === state.round_number ? "deal" : undefined, onPeeked: i => peekedCards[i] = true });
  const scoreChip = document.getElementById("my-score-chip"); scoreChip.textContent = me.hand ? `แต้ม ${UI.calculateVisibleScore(me.hand)}` : "แต้ม —";
  const statusEl = document.getElementById("my-status"); statusEl.textContent = statusText(state.state, me.status, me.card_count);

  const actions = document.getElementById("action-buttons");
  const canPlayerAct = state.state === "playing" && me.status === "thinking" && !me.is_dealer;
  actions.classList.toggle("hidden", !canPlayerAct);
  document.getElementById("dealer-action-buttons").classList.toggle("hidden", !(state.state === "dealer_decision" && me.is_dealer && state.dealer_strategy === "Human Dealer"));
  document.getElementById("action-explanation").textContent = canPlayerAct ? "คุณเลือกได้ 1 ครั้ง: จั่วใบที่ 3 หรือ อยู่ — หลังเลือกแล้วจะเปลี่ยนกลับไม่ได้" : state.state === "dealer_decision" ? "ผู้เล่นทุกคนตัดสินใจแล้ว ถึงตาเจ้ามือ" : "";
  if (me.status === "pok" && lastMyStatus !== "pok") UI.showPokStamp();
  lastMyStatus = me.status;
}

function statusText(gameState, status, cardCount) {
  if (gameState === "betting") return status === "out_of_money" ? "เหรียญหมด — ข้ามรอบนี้" : "รอวางเดิมพัน...";
  const labels = { waiting: "รอเริ่มรอบใหม่", thinking: `มีไพ่ ${cardCount} ใบ — เลือก จั่วใบที่ 3 หรือ อยู่`, pok: "ป๊อก! รอเปิดไพ่", stay: "คุณเลือกอยู่แล้ว", drawn: "จั่วใบที่ 3 แล้ว — รอผู้เล่นคนอื่น", out_of_money: "เหรียญหมด", disconnected: "การเชื่อมต่อชั่วคราว — รอ reconnect" };
  return labels[status] || status;
}

function setupTutorial() {
  document.querySelectorAll(".modal-close").forEach(btn => btn.addEventListener("click", closeModals));
  document.getElementById("tutorial-prev").addEventListener("click", () => {
    tutorialPage = Math.max(0, tutorialPage - 1);
    renderTutorial();
  });
  document.getElementById("tutorial-next").addEventListener("click", () => {
    if (tutorialPage >= tutorialSteps.length - 1) {
      closeModals();
      return;
    }
    tutorialPage += 1;
    renderTutorial();
  });
  document.getElementById("tutorial-choice-view").addEventListener("click", () => {
    document.getElementById("tutorial-choice-modal").classList.add("hidden");
    document.getElementById("tutorial-modal").classList.remove("hidden");
    tutorialPage = 0;
    renderTutorial();
  });
  document.getElementById("tutorial-choice-skip").addEventListener("click", closeModals);
  document.getElementById("modal-layer").addEventListener("click", e => {
    if (e.target.id === "modal-layer") closeModals();
  });
}

function openTutorial(page = 0) {
  if (!tutorialSteps.length) tutorialSteps = [...DEFAULT_TUTORIAL_STEPS];
  tutorialPage = Math.max(0, Math.min(page, tutorialSteps.length - 1));
  document.getElementById("modal-layer").classList.remove("hidden");
  document.getElementById("tutorial-choice-modal").classList.add("hidden");
  document.getElementById("leaderboard-modal").classList.add("hidden");
  document.getElementById("tutorial-modal").classList.remove("hidden");
  renderTutorial();
}

function openTutorialChoice() {
  document.getElementById("modal-layer").classList.remove("hidden");
  document.getElementById("tutorial-modal").classList.add("hidden");
  document.getElementById("leaderboard-modal").classList.add("hidden");
  document.getElementById("tutorial-choice-modal").classList.remove("hidden");
}

function renderTutorial() {
  const step = tutorialSteps[tutorialPage] || DEFAULT_TUTORIAL_STEPS[0];
  document.getElementById("tutorial-title").textContent = step.title;
  document.getElementById("tutorial-content").innerHTML =
    `<div class="tutorial-step"><div class="tutorial-number">${tutorialPage + 1}</div><p>${UI.escape(step.text)}</p></div>`;
  document.getElementById("tutorial-page").textContent = `${tutorialPage + 1} / ${tutorialSteps.length}`;
  document.getElementById("tutorial-prev").disabled = tutorialPage === 0;
  document.getElementById("tutorial-next").textContent = tutorialPage === tutorialSteps.length - 1 ? "เสร็จแล้ว" : "ถัดไป";
}

function closeModals() {
  document.getElementById("modal-layer").classList.add("hidden");
  document.getElementById("tutorial-choice-modal").classList.add("hidden");
  document.getElementById("tutorial-modal").classList.add("hidden");
  document.getElementById("leaderboard-modal").classList.add("hidden");
  document.getElementById("round-result-modal").classList.add("hidden");
}
function setupLeaderboard() { document.querySelectorAll(".tab-btn").forEach(btn => btn.addEventListener("click", () => { document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("is-active")); btn.classList.add("is-active"); leaderboardTab = btn.dataset.tab; document.getElementById("human-period-tabs").classList.toggle("hidden", leaderboardTab !== "human"); GameSocket.send("get_leaderboards", {period: leaderboardPeriod}); })); document.querySelectorAll(".period-btn").forEach(btn => btn.addEventListener("click", () => { document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("is-active")); btn.classList.add("is-active"); leaderboardPeriod = btn.dataset.period; GameSocket.send("get_leaderboards", {period: leaderboardPeriod}); })); }
function openLeaderboard() { document.getElementById("modal-layer").classList.remove("hidden"); document.getElementById("tutorial-modal").classList.add("hidden"); document.getElementById("leaderboard-modal").classList.remove("hidden"); document.getElementById("human-period-tabs").classList.toggle("hidden", leaderboardTab !== "human"); GameSocket.send("get_leaderboards", {period: leaderboardPeriod}); }
function showConnectionBanner(text) { const el = document.getElementById("connection-banner"); el.textContent = text; el.classList.remove("hidden"); }
