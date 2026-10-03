/*
  ui.js
  -----
  รวมฟังก์ชัน render หน้าจอทั้งหมด (วาดไพ่, สถานะผู้เล่น, ผลลัพธ์)
  ไฟล์นี้ไม่ยุ่งกับ WebSocket เลย รับข้อมูลมาแล้ววาดลง DOM เท่านั้น
*/

const UI = (function () {
  const suitSymbol = {
    Spade: "♠",
    Heart: "♥",
    Diamond: "♦",
    Club: "♣",
  };

  const statusLabel = {
    waiting: "รอเริ่มรอบ",
    thinking: "กำลังคิด...",
    pok: "ป๊อก!",
    stay: "อยู่",
    drawn: "จั่วแล้ว",
    out_of_money: "เงินหมด",
  };

  const DEAL_STAGGER_MS = 120; // ระยะห่างจังหวะแจกไพ่ทีละใบ (ในช่วง 100-150ms ตามสเปก)
  const FLIP_STAGGER_MS = 150; // ระยะห่างจังหวะพลิกไพ่ทีละใบ "ภายในมือเดียวกัน" (ข้ามคนพลิกพร้อมกันหมด)
  const PEEK_DURATION_MS = 1300; // เวลาที่ต้องกดค้างให้แง้มไพ่ตัวเองครบ (ลดเหลือสั้นถ้า reduced-motion)
  const PEEK_DURATION_REDUCED_MS = 200;

  // ---------- helper: โชว์/ซ่อน element แบบ fade ไม่ตัดฉับ ----------
  // display:none แก้ animate ตรงๆไม่ได้ จึงต้องรอให้ animation fade-out เล่นจบก่อน (animationend)
  // ค่อยเพิ่ม .hidden จริง ไม่งั้นเนื้อหาจะหายวับไปทันทีโดยไม่มีจังหวะเฟดเลย

  function showEl(el) {
    if (!el.classList.contains("hidden")) return; // อยู่แล้ว ไม่ต้อง fade ซ้ำ
    el.classList.remove("fx-fade-out");
    el.classList.remove("hidden");
    el.classList.add("fx-fade-in");
    el.addEventListener(
      "animationend",
      () => el.classList.remove("fx-fade-in"),
      { once: true }
    );
  }

  function hideEl(el) {
    if (el.classList.contains("hidden")) return;
    el.classList.remove("fx-fade-in");
    el.classList.add("fx-fade-out");
    el.addEventListener(
      "animationend",
      () => {
        el.classList.add("hidden");
        el.classList.remove("fx-fade-out");
      },
      { once: true }
    );
  }

  function showScreen(screenId) {
    document.querySelectorAll(".screen").forEach((el) => {
      if (el.id === screenId) {
        showEl(el);
      } else if (!el.classList.contains("hidden")) {
        hideEl(el);
      }
    });
  }

  function showLobbyError(text) {
    document.getElementById("lobby-error").textContent = text;
  }

  // แสดงจำนวนเงินพร้อมไอคอนเหรียญมีมิติ (แทนที่การพิมพ์ ฿{amount} ตรงๆทุกจุด)
  function moneyLabel(amount) {
    return `<span class="coin-icon"></span>฿${amount}`;
  }

  // แฮชชื่อ -> สี HSL คงที่ (ชื่อเดียวกันได้สีเดียวกันเสมอทุกที่ที่ปรากฏ ไม่ต้องเก็บ state ที่ไหน)
  function hashNameToHsl(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
      hash = (hash * 31 + name.charCodeAt(i)) % 360;
    }
    return `hsl(${hash}, 55%, 40%)`;
  }

  // ---------- การ์ด ----------
  // opts.flip: true  -> คืนโครงสร้าง flip-shell (หน้า-หลัง) พร้อมเล่น animation พลิก 3 มิติ
  //            false/undefined -> การ์ดธรรมดา (ใช้ตอนโชว์ไพ่ของตัวเอง ซึ่งเห็นหน้าไพ่ทันทีอยู่แล้ว)
  // opts.dealDelayMs: ตั้ง --deal-delay แล้วเล่น deal-in (การ์ดวิ่งเข้าจากกองไพ่)
  // opts.delayMs + opts.isPok: ใช้ตอน flip เท่านั้น (ตั้ง --flip-delay และเลือก easing แบบกระแทกถ้าป๊อก)
  function renderCard(card, opts = {}) {
    const isRed = card.suit === "Heart" || card.suit === "Diamond";
    const label = `${card.rank}${suitSymbol[card.suit] || ""}`;

    if (opts.flip) {
      const shell = document.createElement("div");
      shell.className = "flip-shell";

      const inner = document.createElement("div");
      inner.className = "flip-inner flip-anim" + (opts.isPok ? " is-pok" : "");
      inner.style.setProperty("--flip-delay", `${opts.delayMs || 0}ms`);

      const back = document.createElement("div");
      back.className = "card-face card-back";

      const front = document.createElement("div");
      front.className = "card-face card-front" + (isRed ? " suit-red" : "");
      front.textContent = label;

      inner.appendChild(back);
      inner.appendChild(front);
      shell.appendChild(inner);
      return shell;
    }

    const div = document.createElement("div");
    div.className = "playing-card" + (isRed ? " suit-red" : "");
    if (opts.dealDelayMs !== undefined) {
      div.classList.add("deal-in");
      div.style.setProperty("--deal-delay", `${opts.dealDelayMs}ms`);
    }
    div.textContent = label;
    return div;
  }

  // opts.animate === "deal" -> stagger การ์ดแต่ละใบวิ่งเข้าทีละใบ (ใช้ตอนแจกไพ่รอบใหม่เท่านั้น
  // ไม่ใช่ทุกครั้งที่ broadcast game_state มา ไม่งั้นจะ animate ซ้ำทุกครั้งที่ state อัปเดตเล็กน้อย)
  function renderCardRow(containerEl, cards, opts = {}) {
    containerEl.innerHTML = "";
    containerEl.classList.toggle("is-fan", cards.length === 3);
    cards.forEach((card, i) => {
      const cardOpts = {};
      if (opts.animate === "deal") {
        cardOpts.dealDelayMs = i * DEAL_STAGGER_MS;
      }
      containerEl.appendChild(renderCard(card, cardOpts));
    });
  }

  // ไพ่ปิดหน้า "ของคนอื่น" — ไม่มีวันพลิกจนกว่าจะถึง reveal (ค่าจริงยังไม่ถูกส่งมาด้วยซ้ำ)
  // จึง render แบบ static ล้วนๆ ตามจำนวน card_count ที่ server ส่งมา ไม่ต้องมีโครง 3D เลย
  function renderFaceDownRow(containerEl, count) {
    containerEl.innerHTML = "";
    containerEl.classList.toggle("is-fan", count === 3);
    for (let i = 0; i < count; i++) {
      const el = document.createElement("div");
      el.className = "card-back-static";
      containerEl.appendChild(el);
    }
  }

  // ไพ่ 2 ใบแรกของตัวเอง: เริ่มปิดหน้า ต้องกดค้างเพื่อ "แง้ม" (attachPeekHandlers)
  // ใบที่ 3 ขึ้นไป (ถ้าจั่วเพิ่ม) เห็นหน้าทันทีเหมือนเดิม ไม่ผ่านกลไกนี้
  // peekedCards: array boolean ต่อ index (เก็บ state ไว้ที่ main.js เพราะ DOM ถูกสร้างใหม่ทุก broadcast)
  // opts.animate === "deal" -> เล่น deal-in ตอนแจกไพ่รอบใหม่ (เหมือน renderCardRow)
  // opts.onPeeked(index) -> callback ตอนแง้มครบ (ให้ main.js จำสถานะไว้)
  function renderOwnHand(containerEl, cards, peekedCards, opts = {}) {
    containerEl.innerHTML = "";
    containerEl.classList.toggle("is-fan", cards.length === 3);
    cards.forEach((card, i) => {
      if (i < 2) {
        containerEl.appendChild(renderPeekCard(card, i, !!peekedCards[i], opts));
      } else {
        const cardOpts = {};
        if (opts.animate === "deal") {
          cardOpts.dealDelayMs = i * DEAL_STAGGER_MS;
        }
        containerEl.appendChild(renderCard(card, cardOpts));
      }
    });
  }

  function renderPeekCard(card, index, isPeeked, opts) {
    const isRed = card.suit === "Heart" || card.suit === "Diamond";
    const label = `${card.rank}${suitSymbol[card.suit] || ""}`;

    const shell = document.createElement("div");
    shell.className = "flip-shell";
    if (opts.animate === "deal") {
      shell.classList.add("deal-in");
      shell.style.setProperty("--deal-delay", `${index * DEAL_STAGGER_MS}ms`);
    }

    const inner = document.createElement("div");
    inner.className = "flip-inner";
    inner.style.transform = isPeeked ? "rotateY(180deg)" : "rotateY(0deg)";

    const back = document.createElement("div");
    back.className = "card-face card-back";
    const front = document.createElement("div");
    front.className = "card-face card-front" + (isRed ? " suit-red" : "");
    front.textContent = label;

    inner.appendChild(back);
    inner.appendChild(front);
    shell.appendChild(inner);

    if (!isPeeked) {
      attachPeekHandlers(shell, inner, index, opts.onPeeked);
    }

    return shell;
  }

  // กดค้างเพื่อแง้มไพ่ทีละองศาตามเวลาที่ค้างไว้จริง (ไม่ใช่ animation ตามไทม์ไลน์คงที่)
  // ครบ 180deg = แง้มค้างถาวร (เรียก onPeeked แล้วเลิกฟัง pointer ต่อไป)
  // ปล่อยก่อนครบ = snap ปิดคืนด้วย transition สั้นๆ (.card-peek-snap-back ใน animations.css)
  function attachPeekHandlers(shellEl, innerEl, cardIndex, onPeeked) {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const durationMs = reduceMotion ? PEEK_DURATION_REDUCED_MS : PEEK_DURATION_MS;

    let startTime = null;
    let rafId = null;
    let peeked = false;

    function tick(now) {
      if (startTime === null) startTime = now;
      const angle = Math.min(180, ((now - startTime) / durationMs) * 180);
      innerEl.style.transform = `rotateY(${angle}deg)`;

      if (angle >= 180) {
        peeked = true;
        rafId = null;
        if (onPeeked) onPeeked(cardIndex);
        return;
      }
      rafId = requestAnimationFrame(tick);
    }

    function onPointerDown(e) {
      if (peeked) return;
      e.preventDefault();
      innerEl.classList.remove("card-peek-snap-back");
      startTime = null;
      rafId = requestAnimationFrame(tick);
    }

    function onPointerRelease() {
      if (peeked) return;
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      startTime = null;
      innerEl.classList.add("card-peek-snap-back");
      innerEl.style.transform = "rotateY(0deg)";
      innerEl.addEventListener(
        "transitionend",
        () => innerEl.classList.remove("card-peek-snap-back"),
        { once: true }
      );
    }

    shellEl.addEventListener("pointerdown", onPointerDown);
    shellEl.addEventListener("pointerup", onPointerRelease);
    shellEl.addEventListener("pointercancel", onPointerRelease);
    shellEl.addEventListener("pointerleave", onPointerRelease);
  }

  // ---------- โต๊ะวงกลม ----------
  // หมุน array ให้ตัวเองมาอยู่ตำแหน่งแรกเสมอ (seat-1 = ล่างกึ่งกลาง ตาม CSS .seat-count-N)
  // ที่นั่งที่เหลือกระจายรอบวงตามลำดับเดิม (เจ้ามือ/ผู้เล่นคนอื่นตามที่ server ส่งมา)
  function renderTable(players, myConnectionId) {
    const container = document.getElementById("table-oval");

    const myIndex = players.findIndex((p) => p.connection_id === myConnectionId);
    const ordered =
      myIndex >= 0
        ? players.slice(myIndex).concat(players.slice(0, myIndex))
        : players.slice();

    const seatCount = Math.min(8, Math.max(3, ordered.length));
    container.className = "table-oval seat-count-" + seatCount;

    // ลบแค่ที่นั่งเดิม เก็บ #table-center (กองเงินกลางโต๊ะ) ไว้ ไม่ล้างทั้ง container
    container.querySelectorAll(".seat").forEach((el) => el.remove());

    ordered.forEach((player, i) => {
      const seat = document.createElement("div");
      seat.className = "seat seat-" + (i + 1);
      seat.dataset.connectionId = player.connection_id;
      seat.appendChild(renderPlayerBadge(player, myConnectionId));
      container.appendChild(seat);
    });
  }

  function renderPlayerBadge(player, myConnectionId) {
    const badge = document.createElement("div");
    badge.className =
      "player-badge" +
      (player.is_dealer ? " is-dealer" : "") +
      // is-turn/is-pok คุมกรอบเรืองแสง (ดู @keyframes glow-pulse ใน animations.css)
      (player.status === "thinking" ? " is-turn" : "") +
      (player.status === "pok" ? " is-pok" : "") +
      (player.status === "out_of_money" ? " status-out_of_money" : "");

    const avatar = document.createElement("div");
    avatar.className = "player-avatar";
    avatar.style.background = hashNameToHsl(player.name);
    avatar.textContent = (player.name[0] || "?").toUpperCase();
    badge.appendChild(avatar);

    const nameLine = document.createElement("div");
    let displayName = player.name;
    if (player.connection_id === myConnectionId) displayName += " (คุณ)";
    nameLine.textContent = displayName;
    badge.appendChild(nameLine);

    const balanceLine = document.createElement("div");
    balanceLine.className = "player-balance";
    balanceLine.innerHTML = moneyLabel(player.balance);
    badge.appendChild(balanceLine);

    const statusLine = document.createElement("div");
    statusLine.className = `status-tag status-${player.status}`;
    statusLine.textContent = statusLabel[player.status] || player.status;
    badge.appendChild(statusLine);

    // ไพ่ปิดหน้าของ "คนอื่น" เท่านั้น (ไพ่ตัวเองแสดงแยกใน my-hand-section อยู่แล้ว)
    if (player.connection_id !== myConnectionId && player.card_count > 0) {
      const cardsEl = document.createElement("div");
      cardsEl.className = "card-row";
      renderFaceDownRow(cardsEl, player.card_count);
      badge.appendChild(cardsEl);
    }

    return badge;
  }

  // ---------- กองเงินกลางโต๊ะ ----------
  // centerChips: connection_id -> element ปัจจุบันของ chip นั้นใน #table-center
  // เก็บเป็น closure state เพราะต้องรู้ว่า chip ไหน "มีอยู่แล้ว" (ไม่ slide-in ซ้ำ) ตอน broadcast ถัดไปมา
  const centerChips = {};

  function findSeatEl(connectionId) {
    return document.querySelector(
      `#table-oval .seat[data-connection-id="${connectionId}"]`
    );
  }

  function rectOffset(fromEl, toEl) {
    const fromRect = fromEl.getBoundingClientRect();
    const toRect = toEl.getBoundingClientRect();
    return {
      x: fromRect.left + fromRect.width / 2 - (toRect.left + toRect.width / 2),
      y: fromRect.top + fromRect.height / 2 - (toRect.top + toRect.height / 2),
    };
  }

  // เรียกทุกครั้งที่ broadcast game_state มาระหว่างเฟสเดิมพัน: คนที่วางเดิมพันแล้วได้ chip
  // ก้อนใหม่ไหลเข้ากลางโต๊ะจากตำแหน่งที่นั่งจริงของเขา (คำนวณด้วย getBoundingClientRect)
  function renderBetPile(players) {
    const center = document.getElementById("table-center");
    const activeIds = new Set();

    players.forEach((player) => {
      if (!player.has_bet || player.current_bet <= 0) return;
      activeIds.add(player.connection_id);

      let chip = centerChips[player.connection_id];
      if (!chip) {
        chip = document.createElement("div");
        chip.className = "bet-pile chip-slide-in";

        const seatEl = findSeatEl(player.connection_id);
        if (seatEl) {
          const offset = rectOffset(seatEl, center);
          chip.style.setProperty("--chip-from-x", `${offset.x}px`);
          chip.style.setProperty("--chip-from-y", `${offset.y}px`);
        }

        center.appendChild(chip);
        centerChips[player.connection_id] = chip;
      }
      chip.innerHTML = moneyLabel(player.current_bet);
    });

    // ล้าง chip ของรอบก่อน (คนที่ตอนนี้ has_bet=false แล้ว เช่นเริ่มรอบใหม่)
    Object.keys(centerChips).forEach((connId) => {
      if (!activeIds.has(connId)) {
        centerChips[connId].remove();
        delete centerChips[connId];
      }
    });
  }

  // เรียกตอน round_result มาถึง: ก้อนเงินแต่ละคู่ (เจ้ามือ vs ผู้เล่น) บินไปหาฝั่งที่ชนะคู่นั้น
  function settleBetPiles(summary) {
    const center = document.getElementById("table-center");
    Object.entries(summary.results || {}).forEach(([connId, result]) => {
      const chip = centerChips[connId];
      if (!chip) return;

      const winnerConnId = result.winner === "player" ? connId : summary.dealer.connection_id;
      const targetSeat = findSeatEl(winnerConnId);
      if (targetSeat) {
        const offset = rectOffset(targetSeat, center);
        chip.style.setProperty("--chip-to-x", `${offset.x}px`);
        chip.style.setProperty("--chip-to-y", `${offset.y}px`);
      }

      chip.classList.remove("chip-slide-in");
      chip.classList.add("chip-fly-out");
      chip.addEventListener("animationend", () => chip.remove(), { once: true });
      delete centerChips[connId];
    });
  }

  // index นับใหม่ในแต่ละมือ (ไม่ต่อเนื่องข้ามคน) -> ใบแรกของทุกคนพลิกพร้อมกันที่ delay 0 (sync flip)
  // มี ripple เล็กๆแค่ระหว่าง 2-3 ใบในมือเดียวกันเท่านั้น
  function renderFlipRow(containerEl, cards, isPok) {
    containerEl.innerHTML = "";
    containerEl.classList.toggle("is-fan", cards.length === 3);
    cards.forEach((card, i) => {
      containerEl.appendChild(
        renderCard(card, {
          flip: true,
          isPok,
          delayMs: i * FLIP_STAGGER_MS,
        })
      );
    });
  }

  function findBadgeCardRow(connectionId) {
    const seatEl = findSeatEl(connectionId);
    return seatEl ? seatEl.querySelector(".card-row") : null;
  }

  // แนบ badge ผลแพ้ชนะ + ค่าเปลี่ยนแปลงเงินเดิมพันไว้ที่ element ของ "ที่นั่ง" นั้นเลย
  // (ชนะ = ประกายทอง + shimmer, แพ้ = จาง + dim — ไม่ใช้สีป๊อกเพื่อไม่ให้ปนความหมาย)
  // targetEl ของตัวเอง (.my-hand-section) ไม่ถูกสร้างใหม่ทุกรอบเหมือน seat อื่น จึงต้องล้าง badge ค้างจากรอบก่อนเองก่อน
  function attachResultBadge(targetEl, isWin, bet) {
    targetEl.querySelectorAll(".seat-result-badge, .bet-delta-label").forEach((el) => el.remove());
    targetEl.classList.remove("reveal-win-shimmer", "reveal-lose-dim");

    const badge = document.createElement("div");
    badge.className = "seat-result-badge " + (isWin ? "is-win" : "is-lose");
    badge.textContent = isWin ? "✦" : "×";
    targetEl.appendChild(badge);
    targetEl.classList.add(isWin ? "reveal-win-shimmer" : "reveal-lose-dim");

    const deltaLine = document.createElement("div");
    deltaLine.className = "bet-delta-label " + (isWin ? "is-win" : "is-lose");
    deltaLine.textContent = `${isWin ? "+" : "−"}${bet}`;
    targetEl.appendChild(deltaLine);
  }

  // แทนที่ floating summary เดิม: เปิดไพ่จริงทับ face-down ตรงที่นั่งของแต่ละคน
  // แล้วแนบ badge ผลแพ้ชนะไว้ที่ตำแหน่งนั้นเลย (เจ้ามือเทียบกับผู้เล่นแต่ละคนแยกกัน ไม่มี shared summary)
  function renderRevealAtSeats(summary, players, myConnectionId) {
    const dealer = summary.dealer;
    const dealerResult = getResultForDealer(summary);

    if (dealer.connection_id !== myConnectionId) {
      const dealerCardRow = findBadgeCardRow(dealer.connection_id);
      if (dealerCardRow) {
        renderFlipRow(dealerCardRow, dealer.hand, dealerResult && dealerResult.is_pok);
      }
    }

    players.forEach((player) => {
      if (player.is_dealer) return;
      const result = summary.results[player.connection_id];
      if (!result) return;

      const isWin = result.winner === "player";
      const isMe = player.connection_id === myConnectionId;

      if (!isMe) {
        const cardRow = findBadgeCardRow(player.connection_id);
        if (cardRow) {
          renderFlipRow(cardRow, result.hand || [], result.player && result.player.is_pok);
        }
      }

      const seatEl = findSeatEl(player.connection_id);
      const targetEl = isMe
        ? document.querySelector(".my-hand-section")
        : seatEl && seatEl.querySelector(".player-badge");
      if (targetEl) {
        attachResultBadge(targetEl, isWin, result.bet);
      }
    });

    settleBetPiles(summary);
  }

  // ---------- lobby: รายการห้อง real-time ----------
  function renderRoomList(rooms, onJoin) {
    const container = document.getElementById("room-list");
    container.innerHTML = "";

    if (!rooms || rooms.length === 0) {
      const empty = document.createElement("p");
      empty.className = "room-list-empty";
      empty.textContent = "ยังไม่มีห้องเปิดอยู่ สร้างห้องใหม่เลย!";
      container.appendChild(empty);
      return;
    }

    rooms.forEach((room) => {
      const card = document.createElement("div");
      card.className = "room-card";

      const info = document.createElement("div");
      info.className = "room-card-info";

      const nameEl = document.createElement("div");
      nameEl.className = "room-card-name";
      nameEl.textContent = room.room_id;
      info.appendChild(nameEl);

      const metaEl = document.createElement("div");
      metaEl.className = "room-card-meta";
      metaEl.innerHTML = `${room.player_count}/${room.max_players} · ${moneyLabel(room.stake)}`;
      info.appendChild(metaEl);

      card.appendChild(info);

      const joinBtn = document.createElement("button");
      joinBtn.className = "btn btn-primary";
      joinBtn.textContent = "เข้าร่วม";
      joinBtn.addEventListener("click", () => onJoin(room.room_id));
      card.appendChild(joinBtn);

      container.appendChild(card);
    });
  }

  // สร้างตราปั๊ม "ป๊อก!" ลอยกลางจอชั่วคราว แล้วลบตัวเองทิ้งหลัง animation จบ (ดู @keyframes pok-stamp-anim)
  function showPokStamp() {
    const layer = document.getElementById("fx-layer");
    const stamp = document.createElement("div");
    stamp.className = "pok-stamp";
    stamp.textContent = "ป๊อก!";
    stamp.addEventListener("animationend", () => stamp.remove(), { once: true });
    layer.appendChild(stamp);

    // จอสั่นเบาๆพร้อมกันตอนตราปั๊มลง ให้ความรู้สึก "กระแทก" (เฉพาะฉากเกม ไม่ใช่ทั้ง body)
    const gameScreen = document.getElementById("game-screen");
    gameScreen.classList.add("fx-thump");
    gameScreen.addEventListener(
      "animationend",
      () => gameScreen.classList.remove("fx-thump"),
      { once: true }
    );
  }

  function scoreLabel(handResult) {
    if (!handResult) return "-";
    return handResult.is_pok ? `ป๊อก ${handResult.score}` : `${handResult.score}`;
  }

  function getResultForDealer(summary) {
    // เจ้ามือมีผลลัพธ์เดียวกันไม่ว่าจะเทียบกับผู้เล่นคนไหน (หยิบจากคนแรกที่มี)
    const firstResult = Object.values(summary.results)[0];
    return firstResult ? firstResult.dealer : null;
  }

  return {
    showScreen,
    showLobbyError,
    showEl,
    hideEl,
    moneyLabel,
    renderCardRow,
    renderOwnHand,
    renderFaceDownRow,
    renderTable,
    renderBetPile,
    renderRevealAtSeats,
    renderRoomList,
    showPokStamp,
  };
})();

// ---------- Enhanced UX helpers ----------
UI.escape = function(value) {
  const div = document.createElement("div"); div.textContent = value == null ? "" : String(value); return div.innerHTML;
};
UI.calculateVisibleScore = function(cards) {
  if (!cards || !cards.length) return "—";
  const points = cards.reduce((sum, c) => sum + (c.rank === "A" ? 1 : ["10","J","Q","K"].includes(c.rank) ? 0 : Number(c.rank)), 0);
  return points % 10;
};
UI.showToast = function(text, error = false) {
  let layer = document.getElementById("toast-layer");
  if (!layer) { layer = document.createElement("div"); layer.id = "toast-layer"; document.body.appendChild(layer); }
  const toast = document.createElement("div"); toast.className = `toast ${error ? "toast-error" : ""}`; toast.textContent = text; layer.appendChild(toast); setTimeout(() => toast.remove(), 3200);
};
UI.renderRoomList = function(rooms, onJoin) {
  const container = document.getElementById("room-list"); container.innerHTML = "";
  if (!rooms || !rooms.length) { container.innerHTML = '<div class="empty-state">ยังไม่มีห้องเปิดอยู่ — สร้างห้องแรกของคุณได้เลย</div>'; return; }
  rooms.forEach(room => {
    const card=document.createElement("div"); card.className="room-card";
    const mode=room.mode === "ranked" ? "🏆 Ranked" : "🎮 Practice";
    card.innerHTML=`<div class="room-card-info"><div class="room-card-name">${UI.escape(room.room_id)}</div><div class="room-card-meta">${mode} • ${room.player_count}/${room.max_players} คน • ${UI.escape(room.dealer_strategy)}</div></div>`;
    const btn=document.createElement("button"); btn.className="btn btn-primary"; btn.textContent=room.player_count>=room.max_players?"เต็ม":"เข้าร่วม"; btn.disabled=room.player_count>=room.max_players; btn.addEventListener("click",()=>onJoin(room.room_id)); card.appendChild(btn); container.appendChild(card);
  });
};
UI.renderProfile = function(profile) {
  const el = document.getElementById("profile-card"); if (!el || !profile) return;
  el.innerHTML = `<div class="profile-avatar">${UI.escape((profile.name || "?")[0].toUpperCase())}</div><div class="profile-main"><b>${UI.escape(profile.name)}</b><span>${profile.games} เกม • Win rate ${profile.win_rate}% • Streak ${profile.best_streak}</span></div><div class="profile-coins" data-coins="${profile.coins}">${UI.moneyLabel(profile.coins)}</div>`;
};
let phaseTimerInterval = null;

UI.renderPhase = function(state) {
  const labels = {
    waiting: "รอเริ่มรอบ",
    betting: "วางเดิมพัน",
    dealing: "กำลังแจกไพ่",
    playing: "เลือก จั่ว / อยู่",
    dealer_decision: "เจ้ามือกำลังตัดสินใจ",
    reveal: "เปิดไพ่ + สรุปผล"
  };
  document.getElementById("phase-label").textContent = labels[state.state] || state.state;

  const progress = document.getElementById("phase-progress");
  const timer = document.getElementById("timer-label");
  const phaseBar = document.querySelector(".phase-bar");
  clearInterval(phaseTimerInterval);

  // ความยาวของ phase ที่ server ใช้อยู่ใน room.py
  // betting=45s, playing=30s, human dealer=15s, AI dealer=2s
  const phaseDurations = { betting: 45, playing: 30 };
  const dealerDuration = state.dealer_strategy === "Human Dealer" ? 15 : 2;
  const totalSeconds = state.state === "dealer_decision" ? dealerDuration : phaseDurations[state.state];

  const tick = () => {
    if (!state.phase_deadline || !totalSeconds) {
      timer.textContent = "";
      phaseBar?.classList.remove("timer-warning", "timer-danger");
      progress.style.width = state.state === "waiting" ? "0%" : "100%";
      progress.classList.remove("is-timer");
      return;
    }

    const rawLeft = state.phase_deadline - Date.now() / 1000;
    const left = Math.max(0, Math.ceil(rawLeft));
    const percent = Math.max(0, Math.min(100, (rawLeft / totalSeconds) * 100));

    timer.textContent = left > 0 ? `⏱ ${left}s` : "⏱ หมดเวลา";
    progress.classList.add("is-timer");
    progress.style.width = `${percent}%`;
    phaseBar?.classList.toggle("timer-warning", left <= 10 && left > 3);
    phaseBar?.classList.toggle("timer-danger", left <= 3);
  };

  tick();
  if (state.phase_deadline && totalSeconds) phaseTimerInterval = setInterval(tick, 100);
};
UI.renderLeaderboards = function(data, tab) {
  const el = document.getElementById("leaderboard-content"); const rows = data[tab] || [];
  if (!rows.length) { el.innerHTML = `<div class="empty-state">ยังไม่มีข้อมูล — เล่น Ranked เพื่อสร้างสถิติ</div>`; return; }
  if (tab === "human") {
    el.innerHTML = `<div class="table-scroll"><table class="leader-table"><thead><tr><th>#</th><th>ผู้เล่น</th><th>Coins</th><th>Win%</th><th>Games</th><th>Streak</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${i+1}</td><td><b>${UI.escape(r.name)}</b></td><td>${r.coins}</td><td>${r.win_rate}%</td><td>${r.games}</td><td>${r.best_streak}</td></tr>`).join("")}</tbody></table></div>`;
  } else {
    el.innerHTML = `<div class="table-scroll"><table class="leader-table"><thead><tr><th>#</th><th>Strategy</th><th>Win%</th><th>Loss%</th><th>Games</th><th>Avg P/L</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td>${i+1}</td><td><b>${UI.escape(r.dealer_name)}</b></td><td>${r.win_rate}%</td><td>${r.loss_rate}%</td><td>${r.total_games}</td><td>${r.average_profit}</td></tr>`).join("")}</tbody></table></div>`;
  }
};
UI.showRoundSummary = function(summary, myId) {
  const playerResult = summary.results?.[myId];
  const isDealer = summary.dealer?.connection_id === myId;

  // ผู้เล่นจะมี result ของตัวเอง ส่วนเจ้ามือไม่มี entry โดยตรง
  // จึงรวมกำไร/ขาดทุนจากทุกโต๊ะเพื่อแสดงผลให้เจ้ามือด้วย
  if (!playerResult && !isDealer) return;

  const modalLayer = document.getElementById("modal-layer");
  const modal = document.getElementById("round-result-modal");
  if (!modalLayer || !modal) return;

  const dealerHand = summary.dealer?.hand || [];
  const dealerScore = dealerHand.length ? UI.calculateVisibleScore(dealerHand) : null;
  const player = playerResult?.player || {};
  const won = isDealer
    ? Object.values(summary.results || {}).some(r => r.winner === "dealer")
    : playerResult.winner === "player";
  const profit = isDealer
    ? Object.values(summary.results || {}).reduce((sum, r) => sum - Number(r.profit || 0), 0)
    : Number(playerResult.profit || 0);
  const balance = isDealer
    ? Number(summary.dealer?.balance || 0)
    : Number(playerResult.balance || 0);
  const resultCount = Object.keys(summary.results || {}).length;
  const scoreLabel = value => value == null ? "—" : String(value);
  const signedMoney = value => `${value >= 0 ? "+" : "−"}${UI.moneyLabel(Math.abs(value))}`;
  const handTypeLabel = {
    pok: "ป๊อก",
    double: "เด้ง / ไพ่คู่พิเศษ",
    three_of_a_kind: "ตอง",
    straight_flush: "เรียงสี",
    three_card_pok: "ป๊อก 3 ใบ",
    normal: "แต้มปกติ"
  };

  modalLayer.classList.remove("hidden");
  document.getElementById("tutorial-choice-modal").classList.add("hidden");
  document.getElementById("tutorial-modal").classList.add("hidden");
  document.getElementById("leaderboard-modal").classList.add("hidden");
  modal.classList.remove("hidden");

  modal.classList.toggle("is-win", won);
  modal.classList.toggle("is-lose", !won);
  document.getElementById("round-result-icon").textContent = won ? "✓" : "×";
  document.getElementById("round-result-kicker").textContent = `ROUND ${summary.round_number || ""} RESULT`;
  document.getElementById("round-result-title").textContent = isDealer ? (won ? "เจ้ามือชนะ" : "เจ้ามือเสียเปรียบ") : (won ? "ชนะ!" : "แพ้");
  document.getElementById("round-result-subtitle").textContent = isDealer
    ? `${resultCount} ผู้เล่น • ผลรวม ${signedMoney(profit)}`
    : `${handTypeLabel[player.hand_type] || player.hand_type || "แต้มปกติ"}${player.score != null ? ` • ${player.score} แต้ม` : ""} • ตัวคูณ x${playerResult.multiplier || 1}`;

  const details = isDealer ? `
    <div class="result-stat"><span>ผู้เล่นในรอบ</span><b>${resultCount} คน</b></div>
    <div class="result-stat"><span>แต้มเจ้ามือ</span><b>${scoreLabel(dealerScore)}</b></div>
    <div class="result-stat result-profit"><span>ผลรวมรอบนี้</span><b>${signedMoney(profit)}</b></div>
    <div class="result-stat"><span>ยอดคงเหลือ</span><b>${UI.moneyLabel(balance)}</b></div>
  ` : `
    <div class="result-stat"><span>ผลรอบนี้</span><b>${won ? "ชนะเจ้ามือ" : "เจ้ามือชนะ"}</b></div>
    <div class="result-stat"><span>แต้มคุณ</span><b>${scoreLabel(player.score)}</b></div>
    <div class="result-stat"><span>แต้มเจ้ามือ</span><b>${scoreLabel(dealerScore)}</b></div>
    <div class="result-stat"><span>เดิมพัน</span><b>${UI.moneyLabel(playerResult.bet || 0)}</b></div>
    <div class="result-stat result-profit"><span>${won ? "กำไร" : "ขาดทุน"}</span><b>${signedMoney(profit)}</b></div>
    <div class="result-stat"><span>ยอดคงเหลือ</span><b>${UI.moneyLabel(balance)}</b></div>
  `;
  document.getElementById("round-result-details").innerHTML = details;
};
