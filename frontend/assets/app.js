(() => {
  "use strict";

  const API_BASE = window.LUMA_API_BASE || (window.location.port === "8080" ? "http://localhost:5000/api/v1" : "/api/v1");
  const TOKEN_KEY = "luma_access_token";
  const state = {
    token: localStorage.getItem(TOKEN_KEY),
    user: null,
    authMode: "login",
    pollTimer: null,
    models: [],
    activeModel: null,
    loras: [],
    activeJob: null,
    activeImageUrl: null,
    currentFilter: "original",
    filterCache: {},
    pngInfoData: null,
    tags: [],
    tagsLoaded: false,
    activeTagInput: null,
    tagMatches: [],
    tagSelectedIndex: 0,
    tagTokenStart: 0,
    tagTokenEnd: 0,
    isGenerating: false,
    progressPollTimer: null,
    activeJobId: null,
  };

  const $ = (selector) => document.querySelector(selector);
  const authModal = new bootstrap.Modal($("#authModal"));
  const toast = new bootstrap.Toast($("#appToast"), { delay: 3500 });

  function showToast(message) {
    $("#toastMessage").textContent = message;
    toast.show();
  }

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

  async function apiBlob(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!response.ok) {
      let errMsg = `Request failed (${response.status})`;
      try {
        const errData = await response.json();
        errMsg = errData?.error?.message || errMsg;
      } catch {
        // Fallback to text status
      }
      throw new Error(errMsg);
    }
    return await response.blob();
  }

  async function getImageBlob(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Could not download image data");
    return await res.blob();
  }

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

  /* ==========================================================================
     Model Checkpoint Selector (Cog Icon Removed)
     ========================================================================== */

  function createModelFallback(title) {
    const div = document.createElement("div");
    div.className = "model-avatar-fallback";
    const clean = (title || "M").replace(/[^a-zA-Z0-9\s]/g, " ").trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    const initials = parts.length > 1 ? (parts[0][0] + parts[1][0]).toUpperCase() : clean.slice(0, 2).toUpperCase() || "M";
    div.textContent = initials;
    return div;
  }

  function getModelPreviewUrl(model) {
    if (!model) return "";
    return `${API_BASE}/preview/model/${encodeURIComponent(model.name)}`;
  }

  function updateModelTrigger(model) {
    const titleEl = $("#triggerModelTitle");
    const subEl = $("#triggerModelSubtitle");
    const avatarImg = $("#triggerModelAvatar");
    const placeholder = $("#triggerModelPlaceholder");
    const hiddenInput = $("#selectedModelInput");

    if (!model) {
      if (titleEl) {
        titleEl.textContent = "Select Model...";
        titleEl.title = "";
      }
      if (subEl) subEl.textContent = "Click to choose checkpoint";
      if (avatarImg) avatarImg.style.display = "none";
      if (placeholder) {
        placeholder.style.display = "grid";
        placeholder.textContent = "✦";
      }
      if (hiddenInput) hiddenInput.value = "";
      return;
    }

    const displayName = model.title || model.name;
    if (titleEl) {
      titleEl.textContent = displayName;
      titleEl.title = displayName;
    }
    const versionText = model.version ? ` · ${model.version}` : "";
    if (subEl) subEl.textContent = `${model.base_model || "SDXL 1.0"}${versionText}`;
    if (hiddenInput) hiddenInput.value = model.name;

    if (model.has_preview) {
      avatarImg.src = getModelPreviewUrl(model);
      avatarImg.onload = () => {
        avatarImg.style.display = "block";
        placeholder.style.display = "none";
      };
      avatarImg.onerror = () => {
        avatarImg.style.display = "none";
        placeholder.style.display = "grid";
        placeholder.textContent = (model.title || model.name).slice(0, 2).toUpperCase();
      };
    } else {
      avatarImg.style.display = "none";
      placeholder.style.display = "grid";
      placeholder.textContent = (model.title || model.name).slice(0, 2).toUpperCase();
    }
  }

  function selectModel(model) {
    if (!model) return;
    state.activeModel = model;
    updateModelTrigger(model);

    document.querySelectorAll(".model-item-row").forEach((row) => {
      row.classList.toggle("selected", row.dataset.modelName === model.name);
    });
  }

  function renderModelList(modelsToRender) {
    const container = $("#modelListContainer");
    if (!container) return;
    container.innerHTML = "";

    if (!modelsToRender || !modelsToRender.length) {
      const empty = document.createElement("div");
      empty.className = "model-empty-msg";
      empty.textContent = "No matching checkpoints found.";
      container.append(empty);
      return;
    }

    modelsToRender.forEach((m) => {
      const row = document.createElement("div");
      row.className = "model-item-row";
      row.dataset.modelName = m.name;
      if (state.activeModel && state.activeModel.name === m.name) {
        row.classList.add("selected");
      }

      const left = document.createElement("div");
      left.className = "model-item-left";

      if (m.has_preview) {
        const img = document.createElement("img");
        img.className = "model-avatar-circle";
        img.alt = m.title || m.name;
        img.loading = "lazy";
        img.src = getModelPreviewUrl(m);
        img.onerror = () => {
          img.replaceWith(createModelFallback(m.title || m.name));
        };
        left.append(img);
      } else {
        left.append(createModelFallback(m.title || m.name));
      }

      const textStack = document.createElement("div");
      textStack.className = "model-text-stack";

      const title = document.createElement("div");
      title.className = "model-item-title";
      title.textContent = m.title || m.name;

      const version = document.createElement("div");
      version.className = "model-item-version";
      version.textContent = m.version || "v1.0";

      const filename = document.createElement("div");
      filename.className = "model-item-filename";
      filename.textContent = m.filename || `${m.name}.safetensors`;

      textStack.append(title, version, filename);
      left.append(textStack);

      const badge = document.createElement("span");
      badge.className = "model-pill-badge";
      badge.textContent = m.base_model || "SDXL 1.0";

      row.append(left, badge);

      row.addEventListener("click", () => {
        selectModel(m);
        closeModelDropdown();
      });

      container.append(row);
    });
  }

  function openModelDropdown() {
    const menu = $("#modelDropdownMenu");
    const trigger = $("#modelTriggerBtn");
    if (!menu) return;
    menu.classList.remove("d-none");
    if (trigger) trigger.setAttribute("aria-expanded", "true");
    const searchInput = $("#modelSearchInput");
    if (searchInput) {
      searchInput.value = "";
      renderModelList(state.models);
      setTimeout(() => searchInput.focus(), 50);
    }
  }

  function closeModelDropdown() {
    const menu = $("#modelDropdownMenu");
    const trigger = $("#modelTriggerBtn");
    if (menu) menu.classList.add("d-none");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  function toggleModelDropdown() {
    const menu = $("#modelDropdownMenu");
    if (!menu) return;
    if (menu.classList.contains("d-none")) {
      openModelDropdown();
    } else {
      closeModelDropdown();
    }
  }

  async function loadModels(isRefresh = false) {
    const badge = $("#modelCountBadge");

    try {
      const data = await api("/models");
      state.models = data.models || [];
      if (badge) {
        badge.textContent = `${state.models.length} checkpoint${state.models.length !== 1 ? "s" : ""}`;
      }

      if (state.models.length > 0) {
        let current = state.models.find((m) => m.name === state.activeModel?.name);
        if (!current && data.active_model) {
          current = state.models.find((m) => m.name === data.active_model);
        }
        if (!current) {
          current = state.models[0];
        }
        selectModel(current);
      } else {
        updateModelTrigger(null);
      }
      renderModelList(state.models);
      if (isRefresh) showToast("Checkpoints rescanned successfully.");
    } catch (err) {
      if (badge) badge.textContent = "Offline";
      if (isRefresh) showToast(`Could not load models: ${err.message}`);
    }
  }

  /* ==========================================================================
     LoRA Pop-up Selector with Preview Images & Trigger Words
     ========================================================================== */

  function getLoraPreviewUrl(lora) {
    if (!lora) return "";
    return `${API_BASE}/preview/lora/${encodeURIComponent(lora.name)}`;
  }

  function updateLoraTrigger(lora) {
    const titleEl = $("#triggerLoraTitle");
    const subEl = $("#triggerLoraSubtitle");
    const avatarImg = $("#triggerLoraAvatar");
    const placeholder = $("#triggerLoraPlaceholder");

    if (!lora) {
      if (titleEl) {
        titleEl.textContent = "Select LoRA to Insert...";
        titleEl.title = "";
      }
      if (subEl) subEl.textContent = "Click to browse list";
      if (avatarImg) avatarImg.style.display = "none";
      if (placeholder) placeholder.style.display = "grid";
      return;
    }

    const displayName = lora.title || lora.name;
    if (titleEl) {
      titleEl.textContent = displayName;
      titleEl.title = displayName;
    }
    if (subEl) subEl.textContent = `${lora.base_model || "SDXL"} · Active`;

    if (lora.has_preview) {
      avatarImg.src = getLoraPreviewUrl(lora);
      avatarImg.onload = () => {
        avatarImg.style.display = "block";
        if (placeholder) placeholder.style.display = "none";
      };
      avatarImg.onerror = () => {
        avatarImg.style.display = "none";
        if (placeholder) placeholder.style.display = "grid";
      };
    } else {
      if (avatarImg) avatarImg.style.display = "none";
      if (placeholder) placeholder.style.display = "grid";
    }
  }

  function insertLoraIntoPrompt(lora) {
    if (!lora) return;
    const promptInput = $("#prompt");
    if (!promptInput) return;

    const tag = lora.tag || `<lora:${lora.name}:1.0>`;
    let text = promptInput.value.trim();

    // Append LoRA tag only if not already in prompt (bring only LoRA, no trigger words)
    if (!text.includes(tag)) {
      text = text ? `${text} ${tag}` : tag;
    }

    promptInput.value = text;
    $("#promptCount").textContent = `${text.length} / 1000`;
    promptInput.dispatchEvent(new Event("input", { bubbles: true }));
    promptInput.focus();

    updateLoraTrigger(lora);
    showToast(`Selected LoRA: ${lora.title || lora.name}`);
    closeLoraDropdown();
  }

  function renderLoraList(lorasToRender) {
    const container = $("#loraListContainer");
    if (!container) return;
    container.innerHTML = "";

    if (!lorasToRender || !lorasToRender.length) {
      const empty = document.createElement("div");
      empty.className = "model-empty-msg";
      empty.textContent = "No matching LoRAs found.";
      container.append(empty);
      return;
    }

    lorasToRender.forEach((lora) => {
      const card = document.createElement("div");
      card.className = "lora-item-card";

      // Circular Avatar (Preview image or fallback like checkpoint!)
      if (lora.has_preview) {
        const img = document.createElement("img");
        img.className = "lora-avatar-circle";
        img.alt = lora.title || lora.name;
        img.loading = "lazy";
        img.src = getLoraPreviewUrl(lora);
        img.onerror = () => {
          img.replaceWith(createModelFallback(lora.title || lora.name));
        };
        card.append(img);
      } else {
        card.append(createModelFallback(lora.title || lora.name));
      }

      // Card body
      const body = document.createElement("div");
      body.className = "lora-item-body";

      // Top row: Title and Base Model Pill
      const top = document.createElement("div");
      top.className = "lora-item-top";

      const title = document.createElement("div");
      title.className = "lora-title-text";
      title.textContent = lora.title || lora.name;
      title.title = lora.title || lora.name;

      const badge = document.createElement("span");
      badge.className = "model-pill-badge";
      badge.textContent = lora.base_model || "SDXL";

      top.append(title, badge);

      // Middle: Filename / Tag badge
      const mid = document.createElement("div");
      mid.className = "d-flex align-items-center gap-2 mb-1";
      const tagBadge = document.createElement("span");
      tagBadge.className = "lora-tag-badge";
      tagBadge.textContent = lora.tag || `<lora:${lora.name}:1.0>`;
      mid.append(tagBadge);

      body.append(top, mid);

      // Bottom: Trigger words chips (if available)
      if (Array.isArray(lora.trained_words) && lora.trained_words.length > 0) {
        const triggersWrap = document.createElement("div");
        triggersWrap.className = "trigger-words-wrap";

        const label = document.createElement("small");
        label.style.color = "#94a3b8";
        label.style.fontSize = "0.7rem";
        label.style.marginRight = "4px";
        label.textContent = "Triggers:";
        triggersWrap.append(label);

        lora.trained_words.slice(0, 8).forEach((word) => {
          if (typeof word === "string" && word.trim()) {
            const chip = document.createElement("span");
            chip.className = "trigger-chip";
            chip.textContent = word;
            chip.title = `Click to add trigger word "${word}"`;
            chip.addEventListener("click", (e) => {
              e.stopPropagation();
              const promptInput = $("#prompt");
              if (!promptInput) return;
              let curText = promptInput.value.trim();
              if (!curText.toLowerCase().includes(word.toLowerCase())) {
                curText = curText ? `${curText}, ${word}` : word;
                promptInput.value = curText;
                $("#promptCount").textContent = `${curText.length} / 1000`;
                promptInput.dispatchEvent(new Event("input", { bubbles: true }));
              }
              showToast(`Added trigger: ${word}`);
            });
            triggersWrap.append(chip);
          }
        });
        body.append(triggersWrap);
      }

      card.append(body);

      // Clicking LoRA card brings ONLY LoRA tag into prompt
      card.addEventListener("click", () => {
        insertLoraIntoPrompt(lora);
      });

      container.append(card);
    });
  }

  function openLoraDropdown() {
    const menu = $("#loraDropdownMenu");
    const trigger = $("#loraTriggerBtn");
    if (!menu) return;
    menu.classList.remove("d-none");
    if (trigger) trigger.setAttribute("aria-expanded", "true");
    const searchInput = $("#loraSearchInput");
    if (searchInput) {
      searchInput.value = "";
      renderLoraList(state.loras);
      setTimeout(() => searchInput.focus(), 50);
    }
  }

  function closeLoraDropdown() {
    const menu = $("#loraDropdownMenu");
    const trigger = $("#loraTriggerBtn");
    if (menu) menu.classList.add("d-none");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  function toggleLoraDropdown() {
    const menu = $("#loraDropdownMenu");
    if (!menu) return;
    if (menu.classList.contains("d-none")) {
      openLoraDropdown();
    } else {
      closeLoraDropdown();
    }
  }

  async function loadLoras() {
    const badge = $("#loraCountBadge");
    try {
      const data = await api("/loras");
      state.loras = data.loras || [];
      if (badge) {
        badge.textContent = `${state.loras.length} LoRA${state.loras.length !== 1 ? "s" : ""}`;
      }
      renderLoraList(state.loras);
    } catch {
      if (badge) badge.textContent = "0 LoRAs";
    }
  }

  /* ==========================================================================
     Samplers, Schedulers & Upscalers Catalog Loaders
     ========================================================================== */

  function setSelectValueFuzzy(selectEl, targetValue) {
    if (!selectEl || !targetValue) return false;
    const target = String(targetValue).trim().toLowerCase();

    // 1. Exact match by option value or option text
    for (let i = 0; i < selectEl.options.length; i++) {
      const opt = selectEl.options[i];
      if (opt.value.toLowerCase() === target || opt.text.toLowerCase() === target) {
        selectEl.selectedIndex = i;
        selectEl.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    }

    // 2. StartsWith match (e.g. "DPM++ 2M Karras" -> matches "DPM++ 2M", or "karras" -> matches "Karras")
    for (let i = 0; i < selectEl.options.length; i++) {
      const opt = selectEl.options[i];
      const valLower = opt.value.toLowerCase();
      const textLower = opt.text.toLowerCase();
      if (target.startsWith(valLower) || target.startsWith(textLower) || valLower.startsWith(target) || textLower.startsWith(target)) {
        selectEl.selectedIndex = i;
        selectEl.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    }

    // 3. Includes / Substring match
    for (let i = 0; i < selectEl.options.length; i++) {
      const opt = selectEl.options[i];
      const valLower = opt.value.toLowerCase();
      const textLower = opt.text.toLowerCase();
      if (target.includes(valLower) || valLower.includes(target) || target.includes(textLower)) {
        selectEl.selectedIndex = i;
        selectEl.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    }

    // 4. Fallback: if not found, create and append option so it is guaranteed to show up in the box
    const fallbackOpt = document.createElement("option");
    fallbackOpt.value = targetValue;
    fallbackOpt.textContent = targetValue;
    selectEl.append(fallbackOpt);
    selectEl.selectedIndex = selectEl.options.length - 1;
    selectEl.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  async function loadSamplers() {
    const select = $("#samplerSelect");
    if (!select) return;
    try {
      const data = await api("/samplers");
      if (Array.isArray(data.samplers) && data.samplers.length > 0) {
        select.innerHTML = "";
        data.samplers.forEach((s) => {
          const opt = document.createElement("option");
          opt.value = s.name;
          opt.textContent = s.label || s.name;
          if (s.name.toLowerCase().includes("euler a") || s.name.toLowerCase() === "euler ancestral") {
            opt.selected = true;
          }
          select.append(opt);
        });
      }
    } catch {
      // Retain defaults from HTML
    }
  }

  async function loadSchedulers() {
    const select = $("#schedulerSelect");
    if (!select) return;
    try {
      const data = await api("/schedulers");
      if (Array.isArray(data.schedulers) && data.schedulers.length > 0) {
        select.innerHTML = "";
        data.schedulers.forEach((s) => {
          const opt = document.createElement("option");
          opt.value = s.name;
          opt.textContent = s.label || s.name;
          if (s.name.toLowerCase() === "normal" || s.name.toLowerCase() === "karras") {
            opt.selected = true;
          }
          select.append(opt);
        });
      }
    } catch {
      // Retain defaults from HTML
    }
  }

  async function loadUpscalers() {
    const select = $("#upscalerSelect");
    if (!select) return;
    try {
      const data = await api("/upscalers");
      if (Array.isArray(data.upscalers) && data.upscalers.length > 0) {
        select.innerHTML = "";
        data.upscalers.forEach((u) => {
          if (u.name) {
            const opt = document.createElement("option");
            opt.value = u.name;
            opt.textContent = u.label || u.name;
            if (u.name.toLowerCase().includes("esrgan") || u.name.toLowerCase().includes("lanczos")) {
              opt.selected = true;
            }
            select.append(opt);
          }
        });
      }
    } catch {
      // Retain defaults from HTML
    }
  }

  /* ==========================================================================
     Authentication & Session
     ========================================================================== */

  function setAuthenticated(user) {
    state.user = user;
    $("#loginButton").classList.add("d-none");
    $("#heroSignIn").classList.add("d-none");
    $("#userMenu").classList.remove("d-none");
    $("#usernameLabel").textContent = user.username;
    loadJobs();
  }

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

  async function restoreSession() {
    if (!state.token) return;
    try {
      const data = await api("/auth/me");
      setAuthenticated(data.user);
    } catch {
      logout(false);
    }
  }

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

  async function handleAuth(event) {
    event.preventDefault();
    const errorBox = $("#authError");
    errorBox.classList.add("d-none");
    try {
      const data = await api(`/auth/${state.authMode}`, {
        method: "POST",
        body: JSON.stringify({ username: $("#username").value.trim(), password: $("#password").value }),
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

  function requireAuth() {
    if (state.token) return true;
    openAuth("login");
    showToast("Sign in before starting an AI job.");
    return false;
  }

  /* ==========================================================================
     Job Execution & Result Views
     ========================================================================== */

  function setGeneratingState(isBusy, text = "Generating...") {
    state.isGenerating = Boolean(isBusy);
    const genBtn = $("#generateSubmitBtn");
    const editBtn = $("#editSubmitBtn");
    const genText = $("#generateBtnText");
    const genIcon = $("#generateBtnIcon");
    const editText = $("#editBtnText");
    const editIcon = $("#editBtnIcon");

    if (genBtn) {
      // NOTE: Button remains clickable so user can press again to interrupt!
      genBtn.disabled = false;
      if (isBusy) {
        genBtn.classList.add("btn-interrupting");
        genBtn.title = "Click again to interrupt this process";
        if (genText) {
          genText.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Interrupt process (<span id="genBtnPercent">0%</span>)`;
        }
        if (genIcon) {
          genIcon.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>`;
          genIcon.style.display = "inline";
        }
      } else {
        genBtn.classList.remove("btn-interrupting");
        genBtn.title = "Generate image";
        if (genText) genText.textContent = "Generate image";
        if (genIcon) {
          genIcon.innerHTML = "✦";
          genIcon.style.display = "inline";
        }
      }
    }

    if (editBtn) {
      editBtn.disabled = false;
      if (isBusy) {
        editBtn.classList.add("btn-interrupting");
        editBtn.title = "Click again to interrupt this process";
        if (editText) {
          editText.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Interrupt process (<span id="editBtnPercent">0%</span>)`;
        }
        if (editIcon) {
          editIcon.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>`;
          editIcon.style.display = "inline";
        }
      } else {
        editBtn.classList.remove("btn-interrupting");
        editBtn.title = "Edit image";
        if (editText) editText.textContent = "Edit image";
        if (editIcon) {
          editIcon.innerHTML = "✦";
          editIcon.style.display = "inline";
        }
      }
    }
  }

  function updateLiveProgressDisplay(pct, prog = {}) {
    const percentStr = `${Math.round(pct)}%`;

    // 1. Process percent in Image Box
    const percentEl = $("#jobProgressPercent");
    if (percentEl) percentEl.textContent = percentStr;

    const barEl = $("#progressBar");
    if (barEl) barEl.style.width = percentStr;

    // 2. Process percent on Generate / Edit button
    const genBtnPct = $("#genBtnPercent");
    if (genBtnPct) genBtnPct.textContent = percentStr;
    const editBtnPct = $("#editBtnPercent");
    if (editBtnPct) editBtnPct.textContent = percentStr;

    // 3. Status text & substats
    const statusText = $("#jobStatusText");
    if (statusText) statusText.textContent = `Creating your image (${percentStr})`;

    const stepText = $("#jobStepText");
    if (stepText) {
      if (prog.sampling_steps > 0) {
        stepText.textContent = `Step ${prog.sampling_step || 0} / ${prog.sampling_steps}`;
      } else if (pct > 5) {
        stepText.textContent = `Processing (${percentStr})`;
      }
    }

    const etaText = $("#jobEtaText");
    if (etaText && prog.eta_relative !== undefined) {
      etaText.textContent = prog.eta_relative > 0 ? `ETA: ${prog.eta_relative.toFixed(1)}s` : (pct > 90 ? "Finishing..." : "");
    }

    // 4. Live denoising preview image if available
    const previewContainer = $("#jobLivePreviewContainer");
    const previewImg = $("#jobLivePreviewImg");
    if (previewContainer && previewImg) {
      if (prog.preview_image) {
        previewImg.src = prog.preview_image;
        previewContainer.classList.remove("d-none");
      }
    }
  }

  function showJobProgress(job) {
    $("#emptyResult")?.classList.add("d-none");
    $("#resultView")?.classList.add("d-none");
    $("#jobProgress")?.classList.remove("d-none");
    $("#jobLivePreviewContainer")?.classList.add("d-none");

    const initialPct = job.status === "queued" ? 2 : 5;
    updateLiveProgressDisplay(initialPct, { sampling_step: 0, sampling_steps: job.steps || 0 });

    $("#jobStatusText").textContent = job.status === "queued" ? "Waiting for the AI engine" : "Creating your image";
    if (job.status === "queued") {
      const stepText = $("#jobStepText");
      if (stepText) stepText.textContent = "Waiting in queue...";
    }
    $("#jobIdLabel").textContent = `Job ${job.id.slice(0, 8)}`;
  }

  function mediaUrl(path) {
    if (!path) return "";
    if (/^https?:\/\//.test(path)) return path;
    if (API_BASE.startsWith("http")) return `${new URL(API_BASE).origin}${path}`;
    return path;
  }

  function stopPolling() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    if (state.progressPollTimer) {
      clearInterval(state.progressPollTimer);
      state.progressPollTimer = null;
    }
  }

  function showResult(job) {
    stopPolling();
    setGeneratingState(false);
    $("#emptyResult")?.classList.add("d-none");
    $("#jobProgress")?.classList.add("d-none");
    $("#jobLivePreviewContainer")?.classList.add("d-none");
    $("#resultView")?.classList.remove("d-none");

    state.activeJob = job;
    state.activeImageUrl = mediaUrl(job.result_url);
    state.filterCache = { original: state.activeImageUrl };
    state.currentFilter = "original";

    // Reset filter little boxes active state
    document.querySelectorAll(".filter-little-box").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.filter === "original");
    });

    $("#resultImage").src = state.activeImageUrl;
    $("#resultPrompt").textContent = job.prompt;
    $("#downloadButton").href = state.activeImageUrl;
    $("#downloadButton").download = `luma-${job.id.slice(0, 8)}.png`;
    loadJobs();
  }

  async function interruptCurrentGeneration() {
    if (!state.isGenerating) return;
    showToast("Interrupting generation process...");

    // Immediate tactile feedback on button
    const genText = $("#generateBtnText");
    if (genText) genText.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Interrupting...';
    const editText = $("#editBtnText");
    if (editText) editText.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Interrupting...';

    const interruptedJobId = state.activeJobId;
    stopPolling();

    try {
      await api("/interrupt", {
        method: "POST",
        body: JSON.stringify({ job_id: interruptedJobId })
      });
      showToast("Generation process was interrupted.");
    } catch (err) {
      console.warn("Interrupt request notice:", err);
    }

    if (interruptedJobId) {
      try {
        await api(`/jobs/${interruptedJobId}/cancel`, { method: "POST" });
      } catch {
        // Ignore fallback
      }
    }

    setGeneratingState(false);
    const statusText = $("#jobStatusText");
    if (statusText) statusText.textContent = "Generation interrupted";
    const stepText = $("#jobStepText");
    if (stepText) stepText.textContent = "Stopped by user";
    const etaText = $("#jobEtaText");
    if (etaText) etaText.textContent = "";
    $("#jobLivePreviewContainer")?.classList.add("d-none");

    // Immediately reload history so interrupted job displays right away
    loadJobs();

    setTimeout(() => {
      if (!state.isGenerating && !state.activeImageUrl) {
        $("#jobProgress")?.classList.add("d-none");
        $("#emptyResult")?.classList.remove("d-none");
      }
    }, 1800);
  }

  function pollJob(jobId) {
    stopPolling();
    state.activeJobId = jobId;

    // 1. Live Progress Poller: queries real-time Forge progress every 500ms
    state.progressPollTimer = setInterval(async () => {
      if (!state.isGenerating) return;
      try {
        const prog = await api("/progress?include_preview=true");
        if (prog && prog.active) {
          const pct = Math.max(1, Math.min(99, Math.round(prog.progress_percent || (prog.progress * 100))));
          updateLiveProgressDisplay(pct, prog);
        }
      } catch {
        // Ignore background polling glitches
      }
    }, 500);

    // 2. Job Database Status Poller: checks job status every 1000ms
    const check = async () => {
      try {
        const { job } = await api(`/jobs/${jobId}`);
        if (job.status === "completed") {
          stopPolling();
          return showResult(job);
        }
        if (job.status === "failed") {
          stopPolling();
          setGeneratingState(false);
          $("#jobProgress")?.classList.add("d-none");
          $("#emptyResult")?.classList.remove("d-none");
          showToast(job.error || "The AI job failed or was interrupted.");
          return;
        }
        if (job.status === "queued") {
          $("#jobStatusText").textContent = "Waiting for the AI engine";
          $("#jobStepText").textContent = "Waiting in queue...";
        }
      } catch (error) {
        stopPolling();
        setGeneratingState(false);
        showToast(error.message);
      }
    };
    check();
    state.pollTimer = setInterval(check, 1000);
  }

  async function submitGeneration(event) {
    event.preventDefault();
    // If generation is active, clicking the button again INTERRUPTS the process!
    if (state.isGenerating) {
      interruptCurrentGeneration();
      return;
    }
    if (!requireAuth()) return;

    const width = parseInt($("#widthInput")?.value) || 1024;
    const height = parseInt($("#heightInput")?.value) || 1024;
    const steps = parseInt($("#stepsInput")?.value) || 30;
    const cfg_scale = parseFloat($("#cfgScaleInput")?.value) || 5.0;
    const sampler = $("#samplerSelect")?.value || "Euler a";
    const scheduler = $("#schedulerSelect")?.value || "Normal";
    const seedText = $("#seed").value.trim();

    const payload = {
      prompt: $("#prompt").value.trim(),
      negative_prompt: $("#negativePrompt").value.trim(),
      width,
      height,
      steps,
      cfg_scale,
      sampler,
      scheduler,
    };
    if (seedText !== "") payload.seed = Number(seedText);

    // Attach selected checkpoint model
    const selectedModel = $("#selectedModelInput")?.value || state.activeModel?.name;
    if (selectedModel) {
      payload.model = selectedModel;
    }

    setGeneratingState(true, "Generating image...");

    try {
      const { job } = await api("/jobs/generate", { method: "POST", body: JSON.stringify(payload) });
      showJobProgress(job);
      pollJob(job.id);
    } catch (error) {
      setGeneratingState(false);
      showToast(error.message);
    }
  }

  async function submitEdit(event) {
    event.preventDefault();
    // If edit is active, clicking the button again INTERRUPTS the process!
    if (state.isGenerating) {
      interruptCurrentGeneration();
      return;
    }
    if (!requireAuth()) return;
    const data = new FormData();
    data.append("image", $("#editImage").files[0]);
    data.append("prompt", $("#editPrompt").value.trim());
    data.append("strength", $("#strength").value);

    const selectedModel = $("#selectedModelInput")?.value || state.activeModel?.name;
    if (selectedModel) {
      data.append("model", selectedModel);
    }
    const sampler = $("#samplerSelect")?.value;
    const scheduler = $("#schedulerSelect")?.value;
    if (sampler) data.append("sampler", sampler);
    if (scheduler) data.append("scheduler", scheduler);

    setGeneratingState(true, "Editing image...");

    try {
      const { job } = await api("/jobs/edit", { method: "POST", body: data });
      showJobProgress(job);
      pollJob(job.id);
    } catch (error) {
      setGeneratingState(false);
      showToast(error.message);
    }
  }

  /* ==========================================================================
     Image Box Filters & Upscaling Operations
     ========================================================================== */

  async function applyFilter(operation) {
    if (!state.activeImageUrl) return;

    // Update active highlight on little boxes
    document.querySelectorAll(".filter-little-box").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.filter === operation);
    });
    state.currentFilter = operation;

    if (operation === "original") {
      $("#resultImage").src = state.activeImageUrl;
      $("#downloadButton").href = state.activeImageUrl;
      $("#downloadButton").download = `luma-${state.activeJob?.id?.slice(0, 8) || "art"}-original.png`;
      return;
    }

    // Fast return from memory cache if already processed
    if (state.filterCache[operation]) {
      $("#resultImage").src = state.filterCache[operation];
      $("#downloadButton").href = state.filterCache[operation];
      $("#downloadButton").download = `luma-${state.activeJob?.id?.slice(0, 8) || "art"}-${operation}.png`;
      return;
    }

    // Process via /api/v1/process
    const overlay = $("#filterLoadingOverlay");
    const loadingText = $("#filterLoadingText");
    if (overlay) overlay.classList.remove("d-none");
    if (loadingText) loadingText.textContent = `Applying ${operation} filter...`;

    try {
      const imageBlob = await getImageBlob(state.activeImageUrl);
      const formData = new FormData();
      formData.append("file", imageBlob, "image.png");
      formData.append("operation", operation);

      const filteredBlob = await apiBlob("/process", {
        method: "POST",
        body: formData,
      });

      const filteredUrl = URL.createObjectURL(filteredBlob);
      state.filterCache[operation] = filteredUrl;

      if (state.currentFilter === operation) {
        $("#resultImage").src = filteredUrl;
        $("#downloadButton").href = filteredUrl;
        $("#downloadButton").download = `luma-${state.activeJob?.id?.slice(0, 8) || "art"}-${operation}.png`;
      }
      showToast(`Applied ${operation} filter.`);
    } catch (err) {
      showToast(`Filter error: ${err.message}`);
      // Revert active box back to original
      document.querySelectorAll(".filter-little-box").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.filter === "original");
      });
      state.currentFilter = "original";
      $("#resultImage").src = state.activeImageUrl;
    } finally {
      if (overlay) overlay.classList.add("d-none");
    }
  }

  async function applyUpscale() {
    if (!state.activeImageUrl) {
      showToast("No active image to upscale.");
      return;
    }

    const upscaler = $("#upscalerSelect")?.value || "R-ESRGAN 4x+";
    const scaleFactor = $("#upscaleFactorSelect")?.value || "2.0";
    const upscaleBtn = $("#quickUpscaleBtn");
    const overlay = $("#filterLoadingOverlay");
    const loadingText = $("#filterLoadingText");

    if (overlay) overlay.classList.remove("d-none");
    if (loadingText) loadingText.textContent = `Upscaling (${scaleFactor}x with ${upscaler})...`;
    if (upscaleBtn) upscaleBtn.disabled = true;

    try {
      const currentSrc = $("#resultImage").src || state.activeImageUrl;
      const imageBlob = await getImageBlob(currentSrc);
      const formData = new FormData();
      formData.append("image", imageBlob, "image.png");
      formData.append("upscaler", upscaler);
      formData.append("scale_factor", scaleFactor);

      const upscaledBlob = await apiBlob("/upscale", {
        method: "POST",
        body: formData,
      });

      const upscaledUrl = URL.createObjectURL(upscaledBlob);
      state.filterCache[`upscale_${scaleFactor}x_${upscaler}`] = upscaledUrl;
      $("#resultImage").src = upscaledUrl;
      $("#downloadButton").href = upscaledUrl;
      $("#downloadButton").download = `luma-${state.activeJob?.id?.slice(0, 8) || "art"}-${scaleFactor}x.png`;
      showToast(`Upscaled ${scaleFactor}x with ${upscaler} successfully!`);
    } catch (err) {
      showToast(`Upscale failed: ${err.message}`);
    } finally {
      if (overlay) overlay.classList.add("d-none");
      if (upscaleBtn) upscaleBtn.disabled = false;
    }
  }

  /* ==========================================================================
     Gallery History
     ========================================================================== */

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
        if (job.status === "interrupted") {
          placeholder.classList.add("placeholder-interrupted");
          placeholder.innerHTML = '<span class="placeholder-icon">⏹</span><span>Generation interrupted</span>';
        } else if (job.status === "failed") {
          placeholder.classList.add("placeholder-failed");
          placeholder.innerHTML = '<span class="placeholder-icon">✕</span><span>Generation failed</span>';
        } else {
          placeholder.innerHTML = '<span class="placeholder-icon">✦</span><span>Image in progress</span>';
        }
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
      if (job.status === "completed") {
        card.addEventListener("click", () => showResult(job));
      } else {
        card.addEventListener("click", () => {
          if (job.prompt && $("#prompt")) {
            $("#prompt").value = job.prompt;
            $("#prompt").dispatchEvent(new Event("input", { bubbles: true }));
            showToast(`Loaded prompt from ${job.status} job.`);
          }
        });
      }
      col.append(card);
      grid.append(col);
    });
  }

  async function loadJobs() {
    if (!state.token) return;
    try {
      const data = await api("/jobs?limit=24");
      renderJobs(data.jobs);
    } catch (error) {
      showToast(error.message);
    }
  }

  function selectMode(mode) {
    const isGenerate = mode === "generate";
    const isEdit = mode === "edit";
    const isPngInfo = mode === "pnginfo";

    $("#generateTab")?.classList.toggle("active", isGenerate);
    $("#editTab")?.classList.toggle("active", isEdit);
    $("#pngInfoTab")?.classList.toggle("active", isPngInfo);

    $("#generateTab")?.setAttribute("aria-selected", isGenerate);
    $("#editTab")?.setAttribute("aria-selected", isEdit);
    $("#pngInfoTab")?.setAttribute("aria-selected", isPngInfo);

    $("#generateForm")?.classList.toggle("d-none", !isGenerate);
    $("#editForm")?.classList.toggle("d-none", !isEdit);
    $("#pngInfoForm")?.classList.toggle("d-none", !isPngInfo);

    // Toggle right-hand image panel
    const pngRight = $("#pngInfoResultView");
    const emptyRes = $("#emptyResult");
    const jobProg = $("#jobProgress");
    const resView = $("#resultView");

    if (isPngInfo) {
      if (pngRight) pngRight.classList.remove("d-none");
      if (emptyRes) emptyRes.classList.add("d-none");
      if (jobProg) jobProg.classList.add("d-none");
      if (resView) resView.classList.add("d-none");
    } else {
      if (pngRight) pngRight.classList.add("d-none");
      if (state.activeJob && state.activeImageUrl) {
        if (resView) resView.classList.remove("d-none");
        if (emptyRes) emptyRes.classList.add("d-none");
      } else {
        if (emptyRes) emptyRes.classList.remove("d-none");
        if (resView) resView.classList.add("d-none");
      }
    }
  }

  /* ==========================================================================
     PNG Info (.png to Prompt) Implementation
     ========================================================================== */

  async function inspectPngFile(file, autoFillPromptOnly = false) {
    if (!file) return;
    if (!file.type.startsWith("image/") && !file.name.match(/\.(png|jpe?g|webp)$/i)) {
      showToast("Please select a valid image file (PNG, JPEG, WebP).");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", file);

      // Call backend proxy route /api/v1/png-info
      const data = await api("/png-info", {
        method: "POST",
        body: formData,
      });

      if (autoFillPromptOnly) {
        // Direct drop onto prompt textarea or prompt hint button
        if (data.parsed?.prompt) {
          $("#prompt").value = data.parsed.prompt;
        } else if (data.raw_parameters) {
          $("#prompt").value = data.raw_parameters;
        }
        if (data.parsed?.negative_prompt) {
          $("#negativePrompt").value = data.parsed.negative_prompt;
        }
        $("#prompt")?.dispatchEvent(new Event("input", { bubbles: true }));
        showToast("Extracted prompt from PNG!");
        return;
      }

      // Display preview in PNG Info Tab (Matches Reference Screenshot)
      const imgUrl = URL.createObjectURL(file);
      const previewImg = $("#pngPreviewImg");
      if (previewImg) previewImg.src = imgUrl;

      $("#pngUploadPrompt")?.classList.add("d-none");
      $("#pngPreviewContainer")?.classList.remove("d-none");

      const paramsBox = $("#pngParamsBox");
      const txt2imgBtn = $("#pngSendToTxt2imgBtn");
      const img2imgBtn = $("#pngSendToImg2imgBtn");

      if (data.has_metadata && data.raw_parameters) {
        if (paramsBox) paramsBox.textContent = data.raw_parameters;
        if (txt2imgBtn) txt2imgBtn.disabled = false;
        if (img2imgBtn) img2imgBtn.disabled = false;
        showToast("Generation parameters extracted successfully.");
      } else {
        if (paramsBox) {
          paramsBox.innerHTML = '<span class="png-empty-text">No generation metadata (parameters) found in this image.</span>';
        }
        if (txt2imgBtn) txt2imgBtn.disabled = true;
        if (img2imgBtn) img2imgBtn.disabled = true;
        showToast("No generation parameters found in PNG.");
      }

      state.pngInfoData = {
        ...data,
        file,
        imgUrl,
      };
    } catch (err) {
      showToast(`PNG Info error: ${err.message}`);
    }
  }

  function clearPngInfo() {
    const previewImg = $("#pngPreviewImg");
    if (previewImg) previewImg.src = "";
    $("#pngUploadPrompt")?.classList.remove("d-none");
    $("#pngPreviewContainer")?.classList.add("d-none");
    const paramsBox = $("#pngParamsBox");
    if (paramsBox) {
      paramsBox.innerHTML = '<span class="png-empty-text">Drop or upload a PNG image on the left to read and inspect its prompt, seed, sampler, and settings.</span>';
    }
    const txt2imgBtn = $("#pngSendToTxt2imgBtn");
    const img2imgBtn = $("#pngSendToImg2imgBtn");
    if (txt2imgBtn) txt2imgBtn.disabled = true;
    if (img2imgBtn) img2imgBtn.disabled = true;
    const fileInput = $("#pngFileInput");
    if (fileInput) fileInput.value = "";
    state.pngInfoData = null;
  }

  function sendPngToTxt2Img() {
    if (!state.pngInfoData) return;
    const p = state.pngInfoData.parsed || {};

    if (p.prompt) $("#prompt").value = p.prompt;
    if (p.negative_prompt) $("#negativePrompt").value = p.negative_prompt;
    if (p.steps) $("#stepsInput").value = p.steps;
    if (p.cfg_scale) $("#cfgScaleInput").value = parseFloat(p.cfg_scale).toFixed(2);
    if (p.seed !== undefined) $("#seed").value = p.seed;
    if (p.width) $("#widthInput").value = p.width;
    if (p.height) $("#heightInput").value = p.height;

    // Match Sampler
    if (p.sampler) {
      setSelectValueFuzzy($("#samplerSelect"), p.sampler);
    }

    // Match Scheduler
    if (p.scheduler) {
      setSelectValueFuzzy($("#schedulerSelect"), p.scheduler);
    }

    // Match Checkpoint Model
    if (p.model && state.models?.length) {
      const match = state.models.find(
        (m) =>
          (m.name && m.name.toLowerCase().includes(p.model.toLowerCase())) ||
          (m.title && m.title.toLowerCase().includes(p.model.toLowerCase())) ||
          p.model.toLowerCase().includes(m.name.toLowerCase())
      );
      if (match) selectModel(match);
    }

    $("#prompt")?.dispatchEvent(new Event("input", { bubbles: true }));
    $("#negativePrompt")?.dispatchEvent(new Event("input", { bubbles: true }));
    selectMode("generate");
    showToast("Parameters sent to txt2img (Generate)!");
    $("#generateForm")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function sendPngToImg2Img() {
    if (!state.pngInfoData?.file) return;

    try {
      const dt = new DataTransfer();
      dt.items.add(state.pngInfoData.file);
      $("#editImage").files = dt.files;
      $("#fileName").textContent = state.pngInfoData.file.name;
    } catch {
      // Fallback
    }

    if (state.pngInfoData.parsed?.prompt) {
      $("#editPrompt").value = state.pngInfoData.parsed.prompt;
    }

    selectMode("edit");
    showToast("Image and prompt sent to img2img (Edit image)!");
    $("#editForm")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /* ==========================================================================
     Danbooru Tag Auto-Complete (DominikDoom a1111-sd-webui-tagcomplete format)
     ========================================================================== */

  async function loadDanbooruTags() {
    if (state.tagsLoaded) return;
    try {
      const resp = await fetch("assets/danbooru_tags.json");
      if (!resp.ok) return;
      const raw = await resp.json();
      state.tags = raw.map((item) => ({
        name: item[0],
        type: item[1],
        count: item[2],
        aliases: item[3] ? item[3].split(",") : [],
      }));
      state.tagsLoaded = true;
    } catch (e) {
      console.warn("Could not load danbooru_tags.json:", e);
    }
  }

  function formatTagCount(count) {
    if (!count) return "";
    if (count >= 1000000) return (count / 1000000).toFixed(1) + "M";
    if (count >= 1000) return Math.round(count / 1000) + "k";
    return count.toString();
  }

  function getTagTypeBadge(type) {
    switch (type) {
      case 0: return { label: "general", cls: "tag-type-0" };
      case 1: return { label: "artist", cls: "tag-type-1" };
      case 3: return { label: "series", cls: "tag-type-3" };
      case 4: return { label: "char", cls: "tag-type-4" };
      case 5: return { label: "quality", cls: "tag-type-5" };
      default: return { label: "tag", cls: "tag-type-0" };
    }
  }

  function getActiveToken(input) {
    const val = input.value;
    const caret = input.selectionStart;
    if (caret === null || caret === undefined) return null;

    // Search backwards for delimiter (comma, newline, or start of string)
    let start = caret;
    while (start > 0 && val[start - 1] !== "," && val[start - 1] !== "\n") {
      start--;
    }
    // Skip leading spaces
    while (start < caret && val[start] === " ") {
      start++;
    }

    // Search forward for delimiter (comma, newline, or end of string)
    let end = caret;
    while (end < val.length && val[end] !== "," && val[end] !== "\n") {
      end++;
    }

    const token = val.slice(start, caret);
    return {
      raw: token,
      clean: token.trim().toLowerCase().replace(/\s+/g, "_"),
      start,
      end,
      caret,
    };
  }

  function searchDanbooruTags(query, limit = 12) {
    if (!query || query.length < 1) return [];
    if (!state.tags.length) return [];

    const starts = [];
    const aliasStarts = [];
    const contains = [];

    for (let i = 0; i < state.tags.length; i++) {
      const tag = state.tags[i];
      if (tag.name.startsWith(query)) {
        starts.push(tag);
        if (starts.length >= limit) break;
      } else if (tag.aliases.some((a) => a.startsWith(query))) {
        aliasStarts.push(tag);
      } else if (tag.name.includes(query)) {
        contains.push(tag);
      }
    }

    const combined = [...starts, ...aliasStarts, ...contains];
    return combined.slice(0, limit);
  }

  function renderTagSuggestions(input, matches, query) {
    const menu = $("#tagCompleteMenu");
    const list = $("#tagCompleteList");
    if (!menu || !list) return;

    if (!matches.length) {
      hideTagComplete();
      return;
    }

    state.tagMatches = matches;
    state.tagSelectedIndex = 0;
    state.activeTagInput = input;
    list.innerHTML = "";

    matches.forEach((tag, idx) => {
      const badge = getTagTypeBadge(tag.type);
      const item = document.createElement("div");
      item.className = `tag-complete-item ${idx === 0 ? "selected" : ""}`;
      item.dataset.index = idx;

      // Highlight matched prefix in tag name
      const displayName = tag.name.replace(/_/g, " ");
      const queryDisplay = query.replace(/_/g, " ");
      let highlightedHtml = displayName;
      if (displayName.toLowerCase().startsWith(queryDisplay)) {
        highlightedHtml = `<mark class="tag-match-highlight">${displayName.slice(0, queryDisplay.length)}</mark>${displayName.slice(queryDisplay.length)}`;
      }

      item.innerHTML = `
        <span class="tag-type-badge ${badge.cls}">${badge.label}</span>
        <span class="tag-name">${highlightedHtml}</span>
        <span class="tag-count">${formatTagCount(tag.count)}</span>
      `;

      item.addEventListener("mousedown", (e) => {
        e.preventDefault(); // Don't lose focus
        applyTagComplete(idx);
      });

      list.appendChild(item);
    });

    // Position menu directly under the input field
    const rect = input.getBoundingClientRect();
    menu.style.top = `${rect.bottom + window.scrollY + 6}px`;
    menu.style.left = `${Math.min(rect.left + window.scrollX, window.innerWidth - 400)}px`;
    menu.classList.remove("d-none");
  }

  function updateTagMenuSelection() {
    const items = document.querySelectorAll(".tag-complete-item");
    items.forEach((item, idx) => {
      const isSelected = idx === state.tagSelectedIndex;
      item.classList.toggle("selected", isSelected);
      if (isSelected) {
        item.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function applyTagComplete(index) {
    const tag = state.tagMatches[index];
    const input = state.activeTagInput;
    if (!tag || !input) return;

    const token = getActiveToken(input);
    if (!token) return;

    const tagName = tag.name.replace(/_/g, " ");
    const val = input.value;
    const before = val.slice(0, token.start);
    const after = val.slice(token.end);

    // Add trailing comma and space
    const sep = after.trim().startsWith(",") ? "" : ", ";
    const nextText = before + tagName + sep + after.trimStart();

    input.value = nextText;
    const nextCaret = before.length + tagName.length + sep.length;
    input.selectionStart = input.selectionEnd = nextCaret;

    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
    hideTagComplete();
  }

  function hideTagComplete() {
    const menu = $("#tagCompleteMenu");
    if (menu) menu.classList.add("d-none");
    state.tagMatches = [];
    state.activeTagInput = null;
  }

  function handleTagInput(e) {
    const input = e.target;
    if (!state.tagsLoaded) {
      loadDanbooruTags();
    }
    const token = getActiveToken(input);
    if (!token || !token.clean || token.clean.length < 1) {
      hideTagComplete();
      return;
    }
    const matches = searchDanbooruTags(token.clean, 12);
    renderTagSuggestions(input, matches, token.clean);
  }

  function handleTagKeydown(e) {
    const menu = $("#tagCompleteMenu");
    if (!menu || menu.classList.contains("d-none") || !state.tagMatches.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      state.tagSelectedIndex = (state.tagSelectedIndex + 1) % state.tagMatches.length;
      updateTagMenuSelection();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      state.tagSelectedIndex = (state.tagSelectedIndex - 1 + state.tagMatches.length) % state.tagMatches.length;
      updateTagMenuSelection();
    } else if (e.key === "Tab" || e.key === "Enter") {
      e.preventDefault();
      e.stopPropagation();
      applyTagComplete(state.tagSelectedIndex);
    } else if (e.key === "Escape") {
      e.preventDefault();
      hideTagComplete();
    }
  }

  /* ==========================================================================
     Event Listeners & Initialization
     ========================================================================== */

  // Checkpoint Dropdown events (Cog removed)
  $("#modelTriggerBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleModelDropdown();
  });

  $("#modelSearchToggleBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    openModelDropdown();
  });

  $("#modelSearchInput")?.addEventListener("input", (e) => {
    const query = e.target.value.trim().toLowerCase();
    if (!query) {
      renderModelList(state.models);
      return;
    }
    const filtered = state.models.filter((m) => {
      const title = (m.title || "").toLowerCase();
      const name = (m.name || "").toLowerCase();
      const filename = (m.filename || "").toLowerCase();
      const base = (m.base_model || "").toLowerCase();
      const version = (m.version || "").toLowerCase();
      return title.includes(query) || name.includes(query) || filename.includes(query) || base.includes(query) || version.includes(query);
    });
    renderModelList(filtered);
  });

  // LoRA Dropdown events
  $("#loraTriggerBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleLoraDropdown();
  });

  $("#loraSearchInput")?.addEventListener("input", (e) => {
    const query = e.target.value.trim().toLowerCase();
    if (!query) {
      renderLoraList(state.loras);
      return;
    }
    const filtered = state.loras.filter((l) => {
      const title = (l.title || "").toLowerCase();
      const name = (l.name || "").toLowerCase();
      const base = (l.base_model || "").toLowerCase();
      const tag = (l.tag || "").toLowerCase();
      const triggers = Array.isArray(l.trained_words) ? l.trained_words.join(" ").toLowerCase() : "";
      return title.includes(query) || name.includes(query) || base.includes(query) || tag.includes(query) || triggers.includes(query);
    });
    renderLoraList(filtered);
  });

  // Numeric Steppers (Steps, CFG, Width, Height)
  $("#stepsUpBtn")?.addEventListener("click", () => {
    const input = $("#stepsInput");
    input.value = Math.min(150, (parseInt(input.value) || 30) + 1);
  });
  $("#stepsDownBtn")?.addEventListener("click", () => {
    const input = $("#stepsInput");
    input.value = Math.max(1, (parseInt(input.value) || 30) - 1);
  });

  $("#cfgUpBtn")?.addEventListener("click", () => {
    const input = $("#cfgScaleInput");
    input.value = (Math.min(30, (parseFloat(input.value) || 5) + 0.5)).toFixed(2);
  });
  $("#cfgDownBtn")?.addEventListener("click", () => {
    const input = $("#cfgScaleInput");
    input.value = (Math.max(1, (parseFloat(input.value) || 5) - 0.5)).toFixed(2);
  });

  $("#widthUpBtn")?.addEventListener("click", () => {
    const input = $("#widthInput");
    input.value = Math.min(1536, (parseInt(input.value) || 1024) + 64);
  });
  $("#widthDownBtn")?.addEventListener("click", () => {
    const input = $("#widthInput");
    input.value = Math.max(256, (parseInt(input.value) || 1024) - 64);
  });

  $("#heightUpBtn")?.addEventListener("click", () => {
    const input = $("#heightInput");
    input.value = Math.min(1536, (parseInt(input.value) || 1024) + 64);
  });
  $("#heightDownBtn")?.addEventListener("click", () => {
    const input = $("#heightInput");
    input.value = Math.max(256, (parseInt(input.value) || 1024) - 64);
  });

  // Swap Width and Height
  $("#dimSwapBtn")?.addEventListener("click", () => {
    const wInput = $("#widthInput");
    const hInput = $("#heightInput");
    const temp = wInput.value;
    wInput.value = hInput.value;
    hInput.value = temp;
    showToast(`Swapped dimensions: ${wInput.value} × ${hInput.value}`);
  });

  // Presets Toggle & Options
  $("#presetsToggleBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    $("#presetsMenu")?.classList.toggle("d-none");
  });

  document.querySelectorAll(".preset-chip-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const w = btn.dataset.w;
      const h = btn.dataset.h;
      if (w && h) {
        $("#widthInput").value = w;
        $("#heightInput").value = h;
        showToast(`Preset resolution set to ${w} × ${h}`);
        $("#presetsMenu")?.classList.add("d-none");
      }
    });
  });

  document.querySelectorAll(".preset-quality-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (btn.dataset.sampler) setSelectValueFuzzy($("#samplerSelect"), btn.dataset.sampler);
      if (btn.dataset.scheduler) setSelectValueFuzzy($("#schedulerSelect"), btn.dataset.scheduler);
      if (btn.dataset.steps) $("#stepsInput").value = btn.dataset.steps;
      if (btn.dataset.cfg) $("#cfgScaleInput").value = parseFloat(btn.dataset.cfg).toFixed(2);
      const chosenSampler = $("#samplerSelect")?.selectedOptions?.[0]?.text || $("#samplerSelect")?.value || "";
      const chosenSched = $("#schedulerSelect")?.selectedOptions?.[0]?.text || $("#schedulerSelect")?.value || "";
      showToast(`Preset applied: ${chosenSampler} · ${chosenSched}`);
      $("#presetsMenu")?.classList.add("d-none");
    });
  });

  // Filter Little Boxes (Original, Edge, Blur, Grayscale, Invert)
  document.querySelectorAll(".filter-little-box").forEach((btn) => {
    btn.addEventListener("click", () => {
      const op = btn.dataset.filter;
      if (op) applyFilter(op);
    });
  });

  // Upscaling Switch (Tick Box to Activate / Deactivate)
  function setUpscaleActive(isActive) {
    const upscaleSwitch = $("#enableUpscaleSwitch");
    const upscaleWrap = $("#upscaleControlsWrap");
    const upscaleBadge = $("#upscaleStatusBadge");
    const upscalerSelect = $("#upscalerSelect");
    const upscaleFactorSelect = $("#upscaleFactorSelect");

    if (upscaleSwitch) upscaleSwitch.checked = isActive;
    if (upscaleWrap) upscaleWrap.classList.toggle("disabled-state", !isActive);
    if (upscalerSelect) upscalerSelect.disabled = !isActive;
    if (upscaleFactorSelect) upscaleFactorSelect.disabled = !isActive;
    if (upscaleBadge) {
      upscaleBadge.textContent = isActive ? "Active" : "Disabled";
      upscaleBadge.className = `upscale-status-badge ${isActive ? "active" : "inactive"}`;
    }
  }

  $("#enableUpscaleSwitch")?.addEventListener("change", (e) => {
    setUpscaleActive(e.target.checked);
    showToast(e.target.checked ? "Upscaling activated." : "Upscaling deactivated.");
  });

  // Quick Upscale Button
  $("#quickUpscaleBtn")?.addEventListener("click", () => {
    if (!$("#enableUpscaleSwitch")?.checked) {
      setUpscaleActive(true);
    }
    applyUpscale();
  });

  // PNG Info Drag & Drop / File Selection
  const pngDropZone = $("#pngDropZone");
  const pngFileInput = $("#pngFileInput");

  pngDropZone?.addEventListener("click", (e) => {
    if (e.target.closest("#pngClearBtn")) return;
    pngFileInput?.click();
  });

  pngFileInput?.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) inspectPngFile(file);
  });

  pngDropZone?.addEventListener("dragover", (e) => {
    e.preventDefault();
    pngDropZone.classList.add("dragover");
  });

  pngDropZone?.addEventListener("dragleave", () => {
    pngDropZone.classList.remove("dragover");
  });

  pngDropZone?.addEventListener("drop", (e) => {
    e.preventDefault();
    pngDropZone.classList.remove("dragover");
    const file = e.dataTransfer?.files?.[0];
    if (file) inspectPngFile(file);
  });

  // Clear PNG preview
  $("#pngClearBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    clearPngInfo();
  });

  // PNG Action Buttons (Send to txt2img, Send to img2img)
  $("#pngSendToTxt2imgBtn")?.addEventListener("click", sendPngToTxt2Img);
  $("#pngSendToImg2imgBtn")?.addEventListener("click", sendPngToImg2Img);

  // Copy parameters text
  $("#copyPngParamsBtn")?.addEventListener("click", () => {
    if (state.pngInfoData?.raw_parameters) {
      navigator.clipboard.writeText(state.pngInfoData.raw_parameters).then(() => {
        showToast("Parameters copied to clipboard!");
      }).catch(() => {
        showToast("Copy to clipboard failed.");
      });
    }
  });

  // Direct PNG Drop onto Prompt Textarea & Hint Button
  const promptEl = $("#prompt");
  const promptDropInput = $("#promptPngDropInput");

  promptEl?.addEventListener("dragover", (e) => {
    e.preventDefault();
    promptEl.classList.add("border-primary");
  });

  promptEl?.addEventListener("dragleave", () => {
    promptEl.classList.remove("border-primary");
  });

  promptEl?.addEventListener("drop", (e) => {
    e.preventDefault();
    promptEl.classList.remove("border-primary");
    const file = e.dataTransfer?.files?.[0];
    if (file && (file.type.startsWith("image/") || file.name.match(/\.(png|jpe?g|webp)$/i))) {
      inspectPngFile(file, true);
    }
  });

  promptDropInput?.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) inspectPngFile(file, true);
  });

  // Tag-Complete listeners on Prompt & Negative Prompt
  promptEl?.addEventListener("input", handleTagInput);
  promptEl?.addEventListener("keydown", handleTagKeydown);

  const negPromptEl = $("#negativePrompt");
  negPromptEl?.addEventListener("input", handleTagInput);
  negPromptEl?.addEventListener("keydown", handleTagKeydown);

  // Outside click & Escape to close popups
  document.addEventListener("click", (e) => {
    if (!$("#modelDropdownContainer")?.contains(e.target)) {
      closeModelDropdown();
    }
    if (!$("#loraDropdownContainer")?.contains(e.target)) {
      closeLoraDropdown();
    }
    if (!$("#presetsToggleBtn")?.contains(e.target) && !$("#presetsMenu")?.contains(e.target)) {
      $("#presetsMenu")?.classList.add("d-none");
    }
    if (!$("#tagCompleteMenu")?.contains(e.target) && e.target !== promptEl && e.target !== negPromptEl) {
      hideTagComplete();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModelDropdown();
      closeLoraDropdown();
      $("#presetsMenu")?.classList.add("d-none");
      hideTagComplete();
    }
  });

  // Studio & Auth forms
  $("#loginButton").addEventListener("click", () => openAuth("login"));
  $("#heroSignIn").addEventListener("click", () => openAuth("login"));
  $("#logoutButton").addEventListener("click", () => logout());
  $("#authSwitch").addEventListener("click", () => openAuth(state.authMode === "login" ? "register" : "login"));
  $("#authForm").addEventListener("submit", handleAuth);
  $("#generateForm").addEventListener("submit", submitGeneration);
  $("#editForm").addEventListener("submit", submitEdit);
  $("#generateSubmitBtn")?.addEventListener("click", (e) => {
    if (state.isGenerating) {
      e.preventDefault();
      interruptCurrentGeneration();
    }
  });
  $("#editSubmitBtn")?.addEventListener("click", (e) => {
    if (state.isGenerating) {
      e.preventDefault();
      interruptCurrentGeneration();
    }
  });
  $("#cancelJobProgressBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    interruptCurrentGeneration();
  });
  $("#generateTab").addEventListener("click", () => selectMode("generate"));
  $("#editTab").addEventListener("click", () => selectMode("edit"));
  $("#pngInfoTab")?.addEventListener("click", () => selectMode("pnginfo"));
  $("#refreshJobs").addEventListener("click", loadJobs);
  $("#prompt").addEventListener("input", (event) => { $("#promptCount").textContent = `${event.target.value.length} / 1000`; });
  $("#negativePrompt")?.addEventListener("input", (event) => {
    const counter = $("#negativePromptCount");
    if (counter) counter.textContent = `${event.target.value.length} / 1000`;
  });
  $("#strength").addEventListener("input", (event) => { $("#strengthValue").textContent = `${Math.round(Number(event.target.value) * 100)}%`; });
  $("#editImage").addEventListener("change", (event) => { $("#fileName").textContent = event.target.files[0]?.name || ""; });

  // Initial loads
  checkHealth();
  restoreSession();
  loadModels();
  loadLoras();
  loadSamplers();
  loadSchedulers();
  loadUpscalers();
  loadDanbooruTags();
  setInterval(checkHealth, 30000);
})();
