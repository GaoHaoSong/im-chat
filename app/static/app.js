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
      input: "",
      banner: "",
      mobileView: "list",
    });

    const loginForm = reactive({ username: "", pin: "", display_name: "", error: "" });

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
      // Subsequent tasks: load users + open WebSocket
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

    <div v-else class="main">
      <div class="sidebar">用户列表（后续实现）</div>
      <div class="chat-panel"><div class="chat-empty">选择左侧用户开始聊天</div></div>
    </div>
  `,
});

app.mount("#app");
