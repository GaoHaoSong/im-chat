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

    const showGearMenu = ref(false);

    const onlineUsers = computed(() => state.users.filter(u => u.online && u.username !== state.currentUser?.username));
    const offlineUsers = computed(() => state.users.filter(u => !u.online && u.username !== state.currentUser?.username));

    function avatarInitial(name) { return (name || "?").slice(0, 1).toUpperCase(); }

    async function selectChat(username) {
      state.activeChat = username;
      state.unread[username] = 0;
      state.mobileView = "chat";
      try { await API.post("/api/messages/read", { peer: username }, state.token); } catch {}
      if (!state.messages[username]) {
        const data = await API.get(`/api/messages?peer=${encodeURIComponent(username)}&limit=30`, state.token);
        state.messages[username] = data.messages.map(m => ({ ...m, status: "sent" }));
      }
      await nextTick();
      scrollChatToBottom();
    }

    function backToList() { state.mobileView = "list"; }

    function scrollChatToBottom() {
      const el = document.querySelector(".messages");
      if (el) el.scrollTop = el.scrollHeight;
    }

    async function doLogout() {
      try { await API.post("/api/logout", {}, state.token); } catch {}
      localStorage.removeItem("token");
      try { ws && ws.close(); } catch {}
      kicked = true;
      state.token = "";
      state.currentUser = null;
      state.users = [];
      state.messages = {};
      state.unread = {};
      state.activeChat = null;
      state.view = "login";
      showGearMenu.value = false;
    }

    function lastSeenText(ts) {
      if (!ts) return "从未登录";
      const diff = Math.floor(Date.now() / 1000 - ts);
      if (diff < 60) return "刚刚";
      if (diff < 3600) return `${Math.floor(diff/60)} 分钟前`;
      if (diff < 86400) return `${Math.floor(diff/3600)} 小时前`;
      return `${Math.floor(diff/86400)} 天前`;
    }

    function formatTime(ts) {
      const d = new Date(ts * 1000);
      return d.toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    }

    function shouldShowDivider(messages, idx) {
      if (idx === 0) return true;
      return messages[idx].created_at - messages[idx-1].created_at > 300;
    }

    function dividerLabel(ts) {
      const d = new Date(ts * 1000);
      const now = new Date();
      const sameDay = d.toDateString() === now.toDateString();
      const yesterday = new Date(now.getTime() - 86400000).toDateString() === d.toDateString();
      if (sameDay) return "今天 " + formatTime(ts);
      if (yesterday) return "昨天 " + formatTime(ts);
      return d.toLocaleDateString("zh-CN") + " " + formatTime(ts);
    }

    function sendText() {
      const text = state.input.trim();
      if (!text || !state.activeChat || !ws || ws.readyState !== 1) return;
      const temp_id = "t" + Date.now() + Math.random();
      const peer = state.activeChat;
      const local = {
        temp_id, id: null, from_user: state.currentUser.username, to_user: peer,
        kind: "text", content: text, created_at: Math.floor(Date.now()/1000),
        reply_to_id: null, mentions: [], recalled: false, status: "sending",
      };
      if (!state.messages[peer]) state.messages[peer] = [];
      state.messages[peer].push(local);
      ws.send(JSON.stringify({ type: "send", to: peer, kind: "text", content: text, temp_id }));
      state.input = "";
      nextTick(scrollChatToBottom);
    }

    function onInputKeydown(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendText();
      }
    }

    const activePeerObj = computed(() => state.users.find(u => u.username === state.activeChat));
    const activeMessages = computed(() => (state.activeChat && state.messages[state.activeChat]) || []);

    const isMobile = ref(window.matchMedia("(max-width: 768px)").matches);
    window.matchMedia("(max-width: 768px)").addEventListener("change", e => { isMobile.value = e.matches; });

    const EMOJIS = [
      "😀","😁","😂","🤣","😅","😊","😍","😘","😎","🤔",
      "😢","😭","😡","😱","😴","🤤","🤗","🤐","🙄","😏",
      "👍","👎","👌","✌️","🤝","🙏","💪","👀","👋","🤙",
      "❤️","💔","💕","💖","💗","💘","💞","🌹","🌸","🎉",
      "🔥","✨","⭐","🌟","💯","✅","❌","⚠️","❓","❗",
      "🐶","🐱","🦊","🐻","🐼","🐨","🐯","🦁","🐮","🐷",
      "🍎","🍔","🍕","🍰","🍻","☕","🍵","🍜","🍦","🍓",
      "⚽","🏀","🎮","🎵","📷","🎬","🚀","✈️","🚗","🏠",
    ];
    const showEmoji = ref(false);
    function insertEmoji(e) {
      state.input += e;
      showEmoji.value = false;
    }

    onMounted(tryAutoLogin);

    return {
      state, loginForm, submitLogin,
      onlineUsers, offlineUsers, avatarInitial, selectChat, backToList,
      showGearMenu, doLogout, lastSeenText,
      formatTime, shouldShowDivider, dividerLabel, sendText, onInputKeydown,
      activePeerObj, activeMessages, isMobile,
      EMOJIS, showEmoji, insertEmoji,
    };
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
        <div class="sidebar" v-show="state.mobileView === 'list'" style="position:relative">
          <div class="me-row">
            <div class="avatar">{{ avatarInitial(state.currentUser.display_name) }}</div>
            <div class="name">{{ state.currentUser.display_name }}</div>
            <button class="gear" @click="showGearMenu = !showGearMenu">⚙</button>
          </div>
          <div v-if="showGearMenu" class="gear-menu">
            <button @click="doLogout">退出登录</button>
          </div>
          <div class="user-list">
            <div class="group-header" @click="state.collapseOnline = !state.collapseOnline">
              {{ state.collapseOnline ? '▶' : '▼' }} 在线 ({{ onlineUsers.length }})
            </div>
            <template v-if="!state.collapseOnline">
              <div v-for="u in onlineUsers" :key="u.username" :class="['user-row', { active: state.activeChat === u.username }]" @click="selectChat(u.username)">
                <div class="avatar">{{ avatarInitial(u.display_name) }}</div>
                <span class="dot online"></span>
                <span class="name">{{ u.display_name }}</span>
                <span v-if="state.unread[u.username]" class="badge">{{ state.unread[u.username] }}</span>
              </div>
            </template>
            <div class="group-header" @click="state.collapseOffline = !state.collapseOffline">
              {{ state.collapseOffline ? '▶' : '▼' }} 离线 ({{ offlineUsers.length }})
            </div>
            <template v-if="!state.collapseOffline">
              <div v-for="u in offlineUsers" :key="u.username" :class="['user-row', { active: state.activeChat === u.username }]" @click="selectChat(u.username)">
                <div class="avatar" style="background:#9ca3af">{{ avatarInitial(u.display_name) }}</div>
                <span class="dot"></span>
                <span class="name">{{ u.display_name }}<small style="color:#9ca3af;margin-left:6px">{{ lastSeenText(u.last_seen_at) }}</small></span>
                <span v-if="state.unread[u.username]" class="badge">{{ state.unread[u.username] }}</span>
              </div>
            </template>
          </div>
        </div>
        <div class="chat-panel" v-show="state.mobileView === 'chat' || !isMobile">
          <div v-if="!state.activeChat" class="chat-empty">选择左侧用户开始聊天</div>
          <template v-else>
            <div class="chat-header">
              <button class="back" @click="backToList">←</button>
              <div class="peer-name">{{ activePeerObj?.display_name || state.activeChat }}</div>
              <div class="peer-status">
                <span :class="['dot', { online: activePeerObj?.online }]"></span>
                {{ activePeerObj?.online ? '在线' : '离线' }}
              </div>
            </div>
            <div class="messages">
              <template v-for="(m, idx) in activeMessages" :key="m.id || m.temp_id">
                <div v-if="shouldShowDivider(activeMessages, idx)" class="divider">{{ dividerLabel(m.created_at) }}</div>
                <div :class="['msg', { mine: m.from_user === state.currentUser.username }]">
                  <div class="avatar">{{ avatarInitial(m.from_user) }}</div>
                  <div class="bubble">
                    <span v-if="m.recalled" class="recalled">该消息已撤回</span>
                    <template v-else>{{ m.content }}</template>
                    <div class="meta">{{ formatTime(m.created_at) }} <span v-if="m.status === 'sending'">·发送中</span></div>
                  </div>
                </div>
              </template>
            </div>
            <div class="input-area">
              <div class="tools">
                <button title="表情" @click="showEmoji = !showEmoji">😀</button>
                <button title="图片">📎</button>
                <button title="文件">📁</button>
              </div>
              <div v-if="showEmoji" class="emoji-panel">
                <span v-for="e in EMOJIS" :key="e" @click="insertEmoji(e)">{{ e }}</span>
              </div>
              <div class="input-row">
                <textarea v-model="state.input" @keydown="onInputKeydown" placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"></textarea>
                <button class="send-btn" @click="sendText">发送</button>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  `,
});

app.mount("#app");
