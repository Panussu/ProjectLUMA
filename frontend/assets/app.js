(() => {
  "use strict";

  // เลือก API ของเครื่องพัฒนาหรือเส้นทางผ่าน Nginx และเก็บสถานะผู้ใช้ในหน้าเว็บ

  const API_BASE = window.LUMA_API_BASE || (window.location.port === "8080" ? "http://localhost:5000/api/v1" : "/api/v1");
  const TOKEN_KEY = "luma_access_token";
  const state = { token: localStorage.getItem(TOKEN_KEY), user: null, authMode: "login", pollTimer: null };

  // เตรียมตัวเลือก DOM และส่วนแสดงหน้าต่างกับข้อความแจ้งเตือนของ Bootstrap

  const $ = (selector) => document.querySelector(selector);
  const authModal = new bootstrap.Modal($("#authModal"));
  const toast = new bootstrap.Toast($("#appToast"), { delay: 3500 });

  // แสดงข้อความสั้นให้ผู้ใช้ด้วย textContent

  function showToast(message) {
    $("#toastMessage").textContent = message;
    toast.show();
  }

  // แนบ JWT ส่ง JSON หรือ FormData และแปลงคำตอบผิดพลาดเป็น Error

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : null;
    if (!response.ok) {
      if (response.status === 401 && state.token) logout(false);
      throw new Error(data?.error?.message || `Request failed (${response.status})`);
    }
    return data;
  }

  // อ่านสถานะ Backend กับ AI แล้วปรับป้ายความพร้อมบนหน้าเว็บ

  async function checkHealth() {
    const badge = $("#healthBadge");
    try {
      const data = await api("/health");
      const aiReady = data.dependencies?.ai_service === "ok";
      badge.className = `health-badge ${aiReady ? "ok" : "offline"}`;
      $(".health-label").textContent = aiReady ? "System ready" : "AI unavailable";
      badge.title = aiReady ? "Backend, database, and AI service are ready" : "Backend is running, but the AI service is unavailable";
    } catch {
      badge.className = "health-badge offline";
      $(".health-label").textContent = "Offline";
      badge.title = "The backend cannot be reached";
    }
  }

  // แสดงชื่อผู้ใช้ ซ่อนปุ่มเข้าสู่ระบบ และโหลดประวัติงาน

  function setAuthenticated(user) {
    state.user = user;
    $("#loginButton").classList.add("d-none");
    $("#heroSignIn").classList.add("d-none");
    $("#userMenu").classList.remove("d-none");
    $("#usernameLabel").textContent = user.username;
    loadJobs();
  }

  // ลบโทเคนในเบราว์เซอร์และล้างประวัติบนหน้าเว็บ ไม่ได้เพิกถอน JWT ฝั่งเซิร์ฟเวอร์

  function logout(notify = true) {
    state.token = null;
    state.user = null;
    localStorage.removeItem(TOKEN_KEY);
    $("#loginButton").classList.remove("d-none");
    $("#heroSignIn").classList.remove("d-none");
    $("#userMenu").classList.add("d-none");
    $("#jobsGrid").innerHTML = "";
    $("#emptyGallery").classList.remove("d-none");
    $("#emptyGallery").textContent = "Sign in to see your saved creations.";
    if (notify) showToast("You have signed out.");
  }

  // ตรวจโทเคนที่เก็บไว้กับ /auth/me เมื่อเปิดหน้าเว็บใหม่

  async function restoreSession() {
    if (!state.token) return;
    try {
      const data = await api("/auth/me");
      setAuthenticated(data.user);
    } catch {
      logout(false);
    }
  }

  // สลับฟอร์มเข้าสู่ระบบกับสมัครสมาชิกและเปิดหน้าต่าง

  function openAuth(mode = "login") {
    state.authMode = mode;
    const isLogin = mode === "login";
    $("#authTitle").textContent = isLogin ? "Sign in" : "Create an account";
    $("#authSubtitle").textContent = isLogin ? "Continue creating and keep your image history." : "Your creations stay connected to your account.";
    $("#authSubmit").textContent = isLogin ? "Sign in" : "Register";
    $("#authSwitch").textContent = isLogin ? "Need an account? Register" : "Already have an account? Sign in";
    $("#password").autocomplete = isLogin ? "current-password" : "new-password";
    $("#authError").classList.add("d-none");
    authModal.show();
  }

  // ส่งข้อมูลบัญชี เก็บโทเคนเมื่อสำเร็จ และแสดงข้อผิดพลาดในฟอร์ม

  async function handleAuth(event) {
    event.preventDefault();
    const errorBox = $("#authError");
    errorBox.classList.add("d-none");
    try {
      const data = await api(`/auth/${state.authMode}`, {
        method: "POST",
        body: JSON.stringify({ username: $("#username").value.trim(), password: $("#password").value })
      });
      state.token = data.access_token;
      localStorage.setItem(TOKEN_KEY, state.token);
      setAuthenticated(data.user);
      $("#authForm").reset();
      authModal.hide();
      showToast(state.authMode === "login" ? "Welcome back." : "Your account is ready.");
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("d-none");
    }
  }

  // ตรวจว่ามีโทเคนก่อนส่งงานและเปิดหน้าต่างเข้าสู่ระบบเมื่อยังไม่มี

  function requireAuth() {
    if (state.token) return true;
    openAuth("login");
    showToast("Sign in before starting an AI job.");
    return false;
  }

  // แสดงสถานะ queued หรือ processing และแถบความคืบหน้าที่ Backend ส่งมา

  function showJobProgress(job) {
    $("#emptyResult").classList.add("d-none");
    $("#resultView").classList.add("d-none");
    $("#jobProgress").classList.remove("d-none");
    $("#jobStatusText").textContent = job.status === "queued" ? "Waiting for the AI engine" : "Creating your image";
    $("#progressBar").style.width = `${Math.max(4, job.progress || 0)}%`;
    $("#jobIdLabel").textContent = `Job ${job.id.slice(0, 8)}`;
  }

  // เติม origin ของ Backend เฉพาะโหมดที่เรียก API ด้วย URL เต็ม

  function mediaUrl(path) {
    if (!path) return "";
    if (/^https?:\/\//.test(path)) return path;
    if (API_BASE.startsWith("http")) return `${new URL(API_BASE).origin}${path}`;
    return path;
  }

  // หยุดตัวจับเวลาปัจจุบัน แสดงภาพผ่านลิงก์มีลายเซ็น และโหลดประวัติใหม่

  function showResult(job) {
    clearInterval(state.pollTimer);
    $("#jobProgress").classList.add("d-none");
    $("#resultView").classList.remove("d-none");
    const url = mediaUrl(job.result_url);
    $("#resultImage").src = url;
    $("#resultPrompt").textContent = job.prompt;
    $("#downloadButton").href = url;
    loadJobs();
  }

  // ตรวจสถานะทันทีแล้วตั้ง polling ทุก 1.5 วินาที โดยตัวตรวจหยุดเมื่อจบงานหรือเกิดข้อผิดพลาด

  async function pollJob(jobId) {
    clearInterval(state.pollTimer);
    const check = async () => {
      try {
        const { job } = await api(`/jobs/${jobId}`);
        if (job.status === "completed") return showResult(job);
        if (job.status === "failed") {
          clearInterval(state.pollTimer);
          $("#jobProgress").classList.add("d-none");
          $("#emptyResult").classList.remove("d-none");
          showToast(job.error || "The AI job failed.");
          return;
        }
        showJobProgress(job);
      } catch (error) {
        clearInterval(state.pollTimer);
        showToast(error.message);
      }
    };
    await check();
    state.pollTimer = setInterval(check, 1500);
  }

  // อ่าน prompt ขนาดภาพ และ seed แล้วส่งงานสร้างภาพเป็น JSON

  async function submitGeneration(event) {
    event.preventDefault();
    if (!requireAuth()) return;
    const [width, height] = $("#imageSize").value.split("x").map(Number);
    const seedText = $("#seed").value;
    const payload = {
      prompt: $("#prompt").value.trim(),
      negative_prompt: $("#negativePrompt").value.trim(),
      width,
      height,
      steps: 20
    };
    if (seedText !== "") payload.seed = Number(seedText);
    try {
      const { job } = await api("/jobs/generate", { method: "POST", body: JSON.stringify(payload) });
      showJobProgress(job);
      pollJob(job.id);
    } catch (error) {
      showToast(error.message);
    }
  }

  // ส่งไฟล์ต้นทาง prompt และ strength ด้วย FormData เพื่อสร้างงานแก้ไขภาพ

  async function submitEdit(event) {
    event.preventDefault();
    if (!requireAuth()) return;
    const data = new FormData();
    data.append("image", $("#editImage").files[0]);
    data.append("prompt", $("#editPrompt").value.trim());
    data.append("strength", $("#strength").value);
    try {
      const { job } = await api("/jobs/edit", { method: "POST", body: data });
      showJobProgress(job);
      pollJob(job.id);
    } catch (error) {
      showToast(error.message);
    }
  }

  // สร้างการ์ดประวัติด้วย DOM และ textContent เพื่อไม่ตีความ prompt เป็น HTML

  function renderJobs(jobs) {
    const grid = $("#jobsGrid");
    const empty = $("#emptyGallery");
    grid.innerHTML = "";
    if (!jobs.length) {
      empty.textContent = "Your completed and pending jobs will appear here.";
      empty.classList.remove("d-none");
      return;
    }
    empty.classList.add("d-none");
    jobs.forEach((job) => {
      const col = document.createElement("div");
      col.className = "col-sm-6 col-lg-4";
      const card = document.createElement("article");
      card.className = "gallery-card";
      if (job.status === "completed" && job.result_url) {
        const image = document.createElement("img");
        image.className = "gallery-image";
        image.src = mediaUrl(job.result_url);
        image.alt = job.prompt;
        card.append(image);
      } else {
        const placeholder = document.createElement("div");
        placeholder.className = "gallery-placeholder";
        placeholder.textContent = job.status === "failed" ? "Generation failed" : "Image in progress";
        card.append(placeholder);
      }
      const meta = document.createElement("div");
      meta.className = "gallery-meta";
      const prompt = document.createElement("p");
      prompt.textContent = job.prompt;
      const date = document.createElement("small");
      date.textContent = new Date(job.created_at).toLocaleString();
      const status = document.createElement("span");
      status.className = `status-pill status-${job.status}`;
      status.textContent = job.status;
      meta.append(prompt, date, document.createElement("br"), status);
      card.append(meta);
      if (job.status === "completed") card.addEventListener("click", () => showResult(job));
      col.append(card);
      grid.append(col);
    });
  }

  // อ่านประวัติงานล่าสุด 24 งานของผู้ใช้ที่มีโทเคน

  async function loadJobs() {
    if (!state.token) return;
    try {
      const data = await api("/jobs?limit=24");
      renderJobs(data.jobs);
    } catch (error) {
      showToast(error.message);
    }
  }

  // สลับแท็บและฟอร์ม พร้อมปรับ aria-selected ให้ตรงกับโหมด

  function selectMode(mode) {
    const isGenerate = mode === "generate";
    $("#generateTab").classList.toggle("active", isGenerate);
    $("#editTab").classList.toggle("active", !isGenerate);
    $("#generateTab").setAttribute("aria-selected", isGenerate);
    $("#editTab").setAttribute("aria-selected", !isGenerate);
    $("#generateForm").classList.toggle("d-none", !isGenerate);
    $("#editForm").classList.toggle("d-none", isGenerate);
  }

  // ผูกปุ่ม ฟอร์ม และช่องข้อมูลเข้ากับฟังก์ชันควบคุมหน้าเว็บ

  $("#loginButton").addEventListener("click", () => openAuth("login"));
  $("#heroSignIn").addEventListener("click", () => openAuth("login"));
  $("#logoutButton").addEventListener("click", () => logout());
  $("#authSwitch").addEventListener("click", () => openAuth(state.authMode === "login" ? "register" : "login"));
  $("#authForm").addEventListener("submit", handleAuth);
  $("#generateForm").addEventListener("submit", submitGeneration);
  $("#editForm").addEventListener("submit", submitEdit);
  $("#generateTab").addEventListener("click", () => selectMode("generate"));
  $("#editTab").addEventListener("click", () => selectMode("edit"));
  $("#refreshJobs").addEventListener("click", loadJobs);
  $("#prompt").addEventListener("input", (event) => { $("#promptCount").textContent = `${event.target.value.length} / 1000`; });
  $("#strength").addEventListener("input", (event) => { $("#strengthValue").textContent = `${Math.round(Number(event.target.value) * 100)}%`; });
  $("#editImage").addEventListener("change", (event) => { $("#fileName").textContent = event.target.files[0]?.name || ""; });

  // เริ่มตรวจระบบ กู้สถานะล็อกอิน และตรวจความพร้อมซ้ำทุก 30 วินาที

  checkHealth();
  restoreSession();
  setInterval(checkHealth, 30000);
})();

