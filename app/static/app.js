const { createApp, reactive, ref, computed, onMounted, nextTick, watch } = Vue;

const API = {
  async post(path, body, token) {
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const r = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
    const data = await r.json();
    if (!r.ok) throw new Error(data?.error?.message || r.statusText);
    return data;
  },
  async get(path, token) {
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const r = await fetch(path, { headers });
    const data = await r.json();
    if (!r.ok) throw new Error(data?.error?.message || r.statusText);
    return data;
  },
  async upload(file, token) {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/upload", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: fd,
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data?.error?.message || r.statusText);
    return data;
  },
};

const app = createApp({
  setup() {
    const state = reactive({
      view: "loading",
      mode: "login",
      token: "",
      currentUser: null,
      users: [],
      activeChat: null,
      messages: {},
      unread: {},
      input: "",
      banner: "",
      bannerKind: "",
      mobileView: "list",
      collapseOnline: false,
      collapseOffline: true,
    });

    const loginForm = reactive({ username: "", pin: "", display_name: "", error: "" });

    let ws = null;
    let reconnectDelay = 1000;
    let reconnectTimer = null;
    let pingTimer = null;
    let pongTimer = null;
    let kicked = false;

    function setBanner(msg, kind = "warning") {
      state.banner = msg;
      state.bannerKind = kind;
    }
    function clearBanner() { state.banner = ""; state.bannerKind = ""; }

    function connectWs() {
      if (!state.token || kicked) return;
      ws = new WebSocket(`ws://${location.host}/ws?token=${encodeURIComponent(state.token)}`);
      ws.onopen = () => {
        clearBanner();
        reconnectDelay = 1000;
        schedulePing();
      };
      ws.onmessage = (e) => {
        let m;
        try { m = JSON.parse(e.data); } catch { return; }
        handleWsMessage(m);
      };
      ws.onclose = () => {
        clearTimers();
        if (kicked) return;
        setBanner("连接已断开，正在重连...", "warning");
        reconnectTimer = setTimeout(() => {
          reconnectDelay = Math.min(reconnectDelay * 2, 30000);
          connectWs();
        }, reconnectDelay);
      };
      ws.onerror = () => { try { ws.close(); } catch {} };
    }

    function schedulePing() {
      clearTimeout(pingTimer);
      pingTimer = setTimeout(() => {
        try { ws.send(JSON.stringify({ type: "ping" })); } catch { return; }
        pongTimer = setTimeout(() => { try { ws.close(); } catch {} }, 10000);
      }, 30000);
    }

    function clearTimers() {
      clearTimeout(pingTimer); pingTimer = null;
      clearTimeout(pongTimer); pongTimer = null;
      clearTimeout(reconnectTimer); reconnectTimer = null;
    }

    function handleWsMessage(m) {
      if (m.type === "pong") {
        clearTimeout(pongTimer);
        schedulePing();
      } else if (m.type === "presence") {
        const u = state.users.find(x => x.username === m.user);
        if (u) u.online = m.online;
      } else if (m.type === "message") {
        onIncomingMessage(m);
      } else if (m.type === "recalled") {
        onRecalled(m);
      } else if (m.type === "kicked") {
        kicked = true;
        setBanner("你已在其他设备登录", "error");
        try { ws.close(); } catch {}
      } else if (m.type === "error") {
        setBanner(`错误: ${m.message}`, "error");
      }
    }

    function onIncomingMessage(m) {
      const msg = m.message;
      const peer = msg.from_user === state.currentUser.username ? msg.to_user : msg.from_user;
      if (!state.messages[peer]) state.messages[peer] = [];
      if (m.temp_id) {
        const idx = state.messages[peer].findIndex(x => x.temp_id === m.temp_id);
        if (idx >= 0) {
          state.messages[peer].splice(idx, 1, { ...msg, status: "sent" });
          return;
        }
      }
      state.messages[peer].push({ ...msg, status: "sent" });
      if (msg.from_user !== state.currentUser.username && state.activeChat !== msg.from_user) {
        state.unread[msg.from_user] = (state.unread[msg.from_user] || 0) + 1;
      }
    }

    function onRecalled(m) {
      for (const peer of Object.keys(state.messages)) {
        const idx = state.messages[peer].findIndex(x => x.id === m.message_id);
        if (idx >= 0) {
          state.messages[peer][idx] = { ...state.messages[peer][idx], recalled: true };
        }
      }
    }

    async function tryAutoLogin() {
      const token = localStorage.getItem("token");
      if (!token) { state.view = "login"; return; }
      try {
        const data = await API.post("/api/auto_login", { token });
        state.token = token;
        state.currentUser = data;
        await enterMain();
      } catch {
        localStorage.removeItem("token");
        state.view = "login";
      }
    }

    async function submitLogin() {
      loginForm.error = "";
      try {
        const path = state.mode === "register" ? "/api/register" : "/api/login";
        const body = state.mode === "register"
          ? { username: loginForm.username, pin: loginForm.pin, display_name: loginForm.display_name || loginForm.username }
          : { username: loginForm.username, pin: loginForm.pin };
        const data = await API.post(path, body);
        state.token = data.token;
        localStorage.setItem("token", data.token);
        const me = await API.post("/api/auto_login", { token: data.token });
        state.currentUser = me;
        await enterMain();
      } catch (e) {
        loginForm.error = e.message;
      }
    }

    async function enterMain() {
      state.view = "main";
      kicked = false;
      await loadUsers();
      connectWs();
    }

    async function loadUsers() {
      const data = await API.get("/api/users", state.token);
      state.users = data.users;
      state.unread = {};
      for (const u of data.users) {
        if (u.unread > 0) state.unread[u.username] = u.unread;
      }
    }

    onMounted(tryAutoLogin);

    return { state, loginForm, submitLogin };
  },
  template: `
    <div v-if="state.view === 'loading'" class="login-page"><div>加载中...</div></div>

    <div v-else-if="state.view === 'login'" class="login-page">
      <div class="login-card">
        <h2>{{ state.mode === 'register' ? '注册账号' : '登录' }}</h2>
        <div v-if="loginForm.error" class="error">{{ loginForm.error }}</div>
        <input v-model="loginForm.username" placeholder="用户名 (3-20 字母/数字/下划线)">
        <input v-if="state.mode === 'register'" v-model="loginForm.display_name" placeholder="昵称">
        <input v-model="loginForm.pin" placeholder="PIN (4-6 位数字)" type="password" inputmode="numeric">
        <button @click="submitLogin">{{ state.mode === 'register' ? '注册并登录' : '登录' }}</button>
        <div class="switch" @click="state.mode = state.mode === 'register' ? 'login' : 'register'">
          {{ state.mode === 'register' ? '已有账号？去登录' : '没有账号？注册一个' }}
        </div>
      </div>
    </div>

    <div v-else style="display:flex;flex-direction:column;height:100dvh">
      <div v-if="state.banner" :class="['banner', state.bannerKind]">{{ state.banner }}</div>
      <div class="main" style="flex:1;min-height:0">
        <div class="sidebar">用户列表（后续实现）</div>
        <div class="chat-panel"><div class="chat-empty">选择左侧用户开始聊天</div></div>
      </div>
    </div>
  `,
});

app.mount("#app");
