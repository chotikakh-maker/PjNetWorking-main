const GameSocket = (function () {
  let socket = null;
  let lastAddress = "";
  let reconnectTimer = null;
  let intentionalClose = false;
  const listeners = {};

  function normalizeAddress(rawAddress) {
    const address = (rawAddress || "").trim();
    if (!address) return `ws://${window.location.hostname}:8765`;
    if (address.startsWith("https://")) return "wss://" + address.slice(8);
    if (address.startsWith("http://")) return "ws://" + address.slice(7);
    if (address.startsWith("wss://") || address.startsWith("ws://")) return address;
    return `ws://${address}:8765`;
  }

  function connect(serverAddress, onOpenCallback, onFailCallback) {
    lastAddress = serverAddress || lastAddress || "";
    intentionalClose = false;
    clearTimeout(reconnectTimer);
    const wsUrl = normalizeAddress(lastAddress);
    let opened = false;
    socket = new WebSocket(wsUrl);
    socket.onopen = () => { opened = true; emit("connection_open"); if (onOpenCallback) onOpenCallback(); };
    socket.onmessage = event => {
      try { const message = JSON.parse(event.data); (listeners[message.type] || []).forEach(cb => cb(message)); }
      catch (e) { console.error("Invalid server message", e); }
    };
    socket.onclose = () => {
      emit("connection_lost");
      if (!opened && onFailCallback) onFailCallback(wsUrl);
      if (!intentionalClose && lastAddress !== "") {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => connect(lastAddress, () => {}, () => {}), 1800);
      }
    };
    socket.onerror = err => console.warn("WebSocket error", err);
  }

  function send(type, data = {}) {
    if (!socket || socket.readyState !== WebSocket.OPEN) { console.warn("WebSocket not ready"); return false; }
    socket.send(JSON.stringify({ type, ...data })); return true;
  }
  function on(messageType, callback) { if (!listeners[messageType]) listeners[messageType] = []; listeners[messageType].push(callback); }
  function emit(type, payload = {}) { (listeners[type] || []).forEach(cb => cb({ type, ...payload })); }
  function close() { intentionalClose = true; clearTimeout(reconnectTimer); if (socket) socket.close(); }
  return { connect, send, on, close, normalizeAddress };
})();
