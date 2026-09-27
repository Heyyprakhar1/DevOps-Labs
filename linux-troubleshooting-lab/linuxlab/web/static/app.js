// Linux Troubleshooting Lab - Web UI Client Script

let term = null;
let fitAddon = null;
let termWs = null;
let isTerminalInitialized = false;
let termDataDisposable = null;

let currentIncident = null;
let statusInterval = null;
let elapsedSeconds = 0;
let interviewCurrent = null;
let interviewAnswers = [];
let selectedLevel = localStorage.getItem("linuxlab_level") || "EASY";

let currentUser = null;
let authToken = localStorage.getItem("linuxlab_token") || "";
let authMode = "login"; // "login" or "register"

async function apiFetch(url, options = {}) {
  options.headers = options.headers || {};
  if (authToken && !options.headers["Authorization"]) {
    options.headers["Authorization"] = `Bearer ${authToken}`;
  }
  options.credentials = "same-origin";
  const res = await fetch(url, options);
  if (res.status === 401 && !url.includes("/api/auth/")) {
    currentUser = null;
    updateAuthUI();
  }
  return res;
}

const LEVEL_DESCRIPTIONS = {
  "EASY": "Focus: Linux fundamentals + guided troubleshooting",
  "MODERATE": "Focus: Multi-command investigation & symptom correlation",
  "FLUENT": "Focus: Realistic production incidents with minimal guidance",
  "ADVANCED": "Focus: Multi-signal, multi-layer & cascading failures",
  "EXPERT": "Focus: Ambiguous production incidents & root cause reasoning"
};

// Initialize once on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}

function initApp() {
  initTerminal();
  initNav();
  initActions();
  initAuth();
  selectLevel(selectedLevel, false);
  checkAuthStatus();
  fetchStatus();
  fetchLibrary();
  fetchProgress();
  fetchHistory();

  if (!statusInterval) {
    statusInterval = setInterval(fetchStatus, 3000);
  }
}

function selectLevel(level, updateDropdowns = true) {
  if (!level) return;
  selectedLevel = level.toUpperCase();
  localStorage.setItem("linuxlab_level", selectedLevel);

  // Update level button styling
  document.querySelectorAll(".btn-level").forEach((btn) => {
    if (btn.getAttribute("data-level") === selectedLevel) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  // Update level tags and badges
  const lvlClass = "badge-level-" + selectedLevel.toLowerCase();

  const headerBadge = document.getElementById("header-level-badge");
  if (headerBadge) {
    headerBadge.textContent = selectedLevel;
    headerBadge.className = "logo-badge " + lvlClass;
  }

  const activeBadge = document.getElementById("level-active-badge");
  if (activeBadge) {
    activeBadge.textContent = selectedLevel;
    activeBadge.className = "level-badge-tag " + lvlClass;
  }

  const descEl = document.getElementById("level-active-desc");
  if (descEl) {
    descEl.textContent = LEVEL_DESCRIPTIONS[selectedLevel] || "";
  }

  const statusLvl = document.getElementById("status-active-level");
  if (statusLvl) {
    statusLvl.textContent = selectedLevel;
  }

  if (updateDropdowns) {
    const filterLvl = document.getElementById("filter-level");
    if (filterLvl) filterLvl.value = selectedLevel;
    const interviewLvl = document.getElementById("interview-filter-level");
    if (interviewLvl) interviewLvl.value = selectedLevel;
  }
}

// --- Terminal Setup ---

function initTerminal() {
  if (isTerminalInitialized) return;

  const container = document.getElementById("terminal-container");
  if (!container) return;

  container.innerHTML = "";

  term = new Terminal({
    cursorBlink: true,
    cursorStyle: "block",
    fontSize: 14,
    fontFamily: '"Fira Code", "JetBrains Mono", Consolas, monospace',
    theme: {
      background: "#000000",
      foreground: "#dcdcdc",
      cursor: "#3fb950",
      black: "#000000",
      red: "#f85149",
      green: "#3fb950",
      yellow: "#d29922",
      blue: "#58a6ff",
      magenta: "#bc8cff",
      cyan: "#39c5cf",
      white: "#ffffff",
    },
  });

  if (window.FitAddon && window.FitAddon.FitAddon) {
    fitAddon = new window.FitAddon.FitAddon();
    term.loadAddon(fitAddon);
  }

  term.open(container);
  if (fitAddon) {
    fitAddon.fit();
  }

  // Register onData listener EXACTLY ONCE on the Terminal instance
  if (termDataDisposable) {
    try { termDataDisposable.dispose(); } catch (e) {}
    termDataDisposable = null;
  }
  termDataDisposable = term.onData((data) => {
    if (termWs && termWs.readyState === WebSocket.OPEN) {
      termWs.send(data);
    }
  });

  isTerminalInitialized = true;

  // Connect WebSocket to backend PTY
  connectTerminalWs();

  window.addEventListener("resize", () => {
    if (fitAddon && term) {
      fitAddon.fit();
      sendResize();
    }
  });

  document.getElementById("btn-term-clear").addEventListener("click", () => {
    if (term) term.clear();
  });

  document.getElementById("btn-term-reconnect").addEventListener("click", () => {
    connectTerminalWs();
  });
}

function connectTerminalWs() {
  // Properly tear down previous WebSocket if present
  if (termWs) {
    termWs.onopen = null;
    termWs.onmessage = null;
    termWs.onerror = null;
    termWs.onclose = null;
    try {
      termWs.close();
    } catch (e) {}
    termWs = null;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = authToken
    ? `${protocol}//${window.location.host}/ws/terminal?token=${encodeURIComponent(authToken)}`
    : `${protocol}//${window.location.host}/ws/terminal`;

  term.write("\r\n\x1b[36mConnecting to sandbox terminal...\x1b[0m\r\n");

  termWs = new WebSocket(wsUrl);
  termWs.binaryType = "arraybuffer";

  termWs.onopen = () => {
    term.write("\x1b[32m✔ Connected to prod-app-server-01 (devops).\x1b[0m\r\n");
    sendResize();
  };

  termWs.onmessage = (event) => {
    if (typeof event.data === "string") {
      term.write(event.data);
    } else {
      const bytes = new Uint8Array(event.data);
      term.write(bytes);
    }
  };

  termWs.onclose = () => {
    term.write("\r\n\x1b[33m[Terminal session disconnected]\x1b[0m\r\n");
  };

  termWs.onerror = () => {
    term.write("\r\n\x1b[31m[WebSocket connection error]\x1b[0m\r\n");
  };

  // NOTE: term.onData is registered ONCE in initTerminal to prevent duplicate listeners on reconnect
}

function sendResize() {
  if (termWs && termWs.readyState === WebSocket.OPEN && term) {
    termWs.send(JSON.stringify({
      type: "resize",
      cols: term.cols,
      rows: term.rows,
    }));
  }
}

// --- Navigation Tabs ---

function initNav() {
  const navBtns = document.querySelectorAll(".btn-nav");
  navBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      navBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      document.querySelectorAll(".tab-pane").forEach((pane) => {
        pane.classList.remove("active");
      });

      const activePane = document.getElementById(targetId);
      if (activePane) {
        activePane.classList.add("active");
        if (targetId === "incident-pane") {
          setTimeout(() => {
            if (fitAddon) fitAddon.fit();
            if (term) term.focus();
          }, 50);
        } else if (targetId === "progress-pane") {
          fetchProgress();
        } else if (targetId === "history-pane") {
          fetchHistory();
        } else if (targetId === "library-pane") {
          fetchLibrary();
        }
      }
    });
  });

  // Command History Drawer toggle
  const historyToggle = document.getElementById("history-toggle");
  const historyContent = document.getElementById("history-content");
  const historyArrow = document.getElementById("history-arrow");
  if (historyToggle && historyContent) {
    historyToggle.addEventListener("click", () => {
      historyContent.classList.toggle("open");
      historyArrow.textContent = historyContent.classList.contains("open") ? "▼" : "▲";
      setTimeout(() => {
        if (fitAddon && term) {
          fitAddon.fit();
          sendResize();
        }
      }, 60);
    });
  }
}

// --- Status & Polling ---

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    const sb = data.sandbox;
    document.getElementById("status-sandbox").textContent = sb.status.toUpperCase();
    document.getElementById("status-webapp").textContent = sb.web_app.toUpperCase();
    document.getElementById("status-payment").textContent = sb.payment_api.toUpperCase();

    const dot = document.getElementById("status-dot");
    if (sb.status === "running") {
      dot.className = "status-indicator green";
    } else {
      dot.className = "status-indicator red";
    }

    const incident = data.active_incident;
    if (incident) {
      currentIncident = incident;
      document.getElementById("status-incident").textContent = incident.id.toUpperCase();
      document.getElementById("status-hints").textContent = `${incident.hints_used.length}/3`;

      // Update timer
      elapsedSeconds = incident.elapsed_seconds;
      updateTimerDisplay();

      // Render incident sidebar
      document.getElementById("no-incident-msg").style.display = "none";
      document.getElementById("incident-details").style.display = "flex";
      document.getElementById("sidebar-controls").style.display = "flex";

      document.getElementById("incident-cat").textContent = incident.category;
      const incLvl = (incident.level || incident.difficulty || "EASY").toUpperCase();
      const incLvlEl = document.getElementById("incident-level");
      if (incLvlEl) {
        incLvlEl.textContent = incLvl;
        incLvlEl.className = "badge badge-level badge-level-" + incLvl.toLowerCase();
      }
      document.getElementById("status-active-level").textContent = incLvl;

      document.getElementById("incident-title").textContent = incident.title;
      document.getElementById("incident-context").textContent = incident.context;
      document.getElementById("incident-objective").textContent = incident.objective;

      // Render Help Box and progressive hints (opt-in)
      renderHelpArea(incident);

      const symptomsList = document.getElementById("incident-symptoms");
      symptomsList.innerHTML = "";
      incident.symptoms.forEach((s) => {
        const li = document.createElement("li");
        li.textContent = s;
        symptomsList.appendChild(li);
      });

      // Update command history
      const cmds = incident.command_history || [];
      document.getElementById("cmd-count").textContent = cmds.length;
      const historyContent = document.getElementById("history-content");
      historyContent.innerHTML = "";
      cmds.forEach((cmd) => {
        const div = document.createElement("div");
        div.className = "cmd-line";
        div.textContent = cmd;
        historyContent.appendChild(div);
      });
    } else {
      currentIncident = null;
      document.getElementById("status-incident").textContent = "NONE";
      document.getElementById("status-active-level").textContent = selectedLevel;
      document.getElementById("status-timer").textContent = "00:00";
      document.getElementById("status-hints").textContent = "0/3";
      document.getElementById("no-incident-msg").style.display = "block";
      document.getElementById("incident-details").style.display = "none";
      document.getElementById("sidebar-controls").style.display = "none";
      document.getElementById("incident-title").textContent = "No Active Incident";
      document.getElementById("cmd-count").textContent = "0";
      document.getElementById("history-content").innerHTML = "";
      renderHelpArea(null);
      resetRightPanelEvaluation();
    }
  } catch (err) {
    console.error("Status poll error:", err);
  }
}

function updateTimerDisplay() {
  const mins = Math.floor(elapsedSeconds / 60).toString().padStart(2, "0");
  const secs = (elapsedSeconds % 60).toString().padStart(2, "0");
  document.getElementById("status-timer").textContent = `${mins}:${secs}`;
}

// --- Incident Controls ---

function initActions() {
  // Level selector buttons
  document.querySelectorAll(".btn-level").forEach((btn) => {
    btn.addEventListener("click", () => {
      const lvl = btn.getAttribute("data-level");
      selectLevel(lvl, true);
      fetchLibrary();
    });
  });

  // Level filters
  const filterLvl = document.getElementById("filter-level");
  if (filterLvl) {
    filterLvl.addEventListener("change", () => {
      if (filterLvl.value) {
        selectLevel(filterLvl.value, false);
      }
      fetchLibrary();
    });
  }

  const interviewFilterLvl = document.getElementById("interview-filter-level");
  if (interviewFilterLvl) {
    interviewFilterLvl.addEventListener("change", () => {
      fetchInterviewQuestion();
    });
  }

  // Random Incident
  document.getElementById("btn-random-incident").addEventListener("click", async () => {
    if (!currentUser) {
      openAuthModal("login");
      return;
    }
    try {
      const res = await apiFetch("/api/incidents/random", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: selectedLevel }),
      });
      if (res.ok) {
        resetRightPanelEvaluation();
        switchToTab("incident-pane");
        connectTerminalWs();
        fetchStatus();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "Failed to inject random incident. Check lab container status.");
      }
    } catch (e) {
      alert("Error starting incident: " + e);
    }
  });

  // Reset Environment
  document.getElementById("btn-reset-env").addEventListener("click", async () => {
    if (!confirm("Are you sure you want to reset the lab sandbox environment?")) return;
    try {
      const res = await apiFetch("/api/incidents/reset", { method: "POST" });
      const data = await res.json();
      alert(data.message || "Environment reset complete.");
      resetRightPanelEvaluation();
      fetchStatus();
      fetchProgress();
      fetchHistory();
    } catch (e) {
      alert("Error resetting environment: " + e);
    }
  });

  // Request Hint (opt-in approach guidance)
  const btnHint = document.getElementById("btn-request-hint");
  if (btnHint) {
    btnHint.addEventListener("click", requestApproachHint);
  }

  document.getElementById("btn-unlock-next-hint").addEventListener("click", async () => {
    try {
      const res = await apiFetch("/api/incidents/hint", { method: "POST" });
      if (!res.ok) {
        alert("Failed to unlock hint.");
        return;
      }
      const data = await res.json();
      renderHintsInModal(data);
      fetchStatus();
    } catch (e) {
      alert("Error unlocking hint: " + e);
    }
  });

  document.getElementById("btn-close-hint").addEventListener("click", closeHintModal);
  document.getElementById("btn-close-hint-footer").addEventListener("click", closeHintModal);

  // Evaluate Modal
  document.getElementById("btn-evaluate-incident").addEventListener("click", () => {
    openEvaluateModal();
  });

  document.getElementById("btn-submit-eval").addEventListener("click", async () => {
    const explanation = document.getElementById("eval-explanation-input").value;
    const btn = document.getElementById("btn-submit-eval");
    btn.disabled = true;
    btn.textContent = "Verifying Lab State...";

    try {
      const res = await apiFetch("/api/incidents/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explanation: explanation }),
      });
      const data = await res.json();
      renderEvaluationReport(data);
      closeEvaluateModal();
      fetchStatus();
      fetchProgress();
      fetchHistory();
    } catch (e) {
      alert("Evaluation failed: " + e);
    } finally {
      btn.disabled = false;
      btn.textContent = "Run Evaluation";
    }
  });

  document.getElementById("btn-close-eval").addEventListener("click", closeEvaluateModal);
  document.getElementById("btn-close-eval-footer").addEventListener("click", closeEvaluateModal);
  document.getElementById("btn-eval-next").addEventListener("click", () => {
    closeEvaluateModal();
    document.getElementById("btn-random-incident").click();
  });

  const btnToggleEv = document.getElementById("btn-toggle-evidence");
  const evContainer = document.getElementById("evidence-container");
  if (btnToggleEv && evContainer) {
    btnToggleEv.addEventListener("click", () => {
      const isHidden = evContainer.style.display === "none";
      evContainer.style.display = isHidden ? "block" : "none";
      btnToggleEv.textContent = isHidden ? "Hide Evidence" : "Show Evidence";
    });
  }

  const btnTogglePm = document.getElementById("btn-toggle-postmortem");
  const pmContainer = document.getElementById("report-postmortem-container");
  if (btnTogglePm && pmContainer) {
    btnTogglePm.addEventListener("click", () => {
      const isHidden = pmContainer.style.display === "none";
      pmContainer.style.display = isHidden ? "flex" : "none";
      btnTogglePm.textContent = isHidden ? "Hide Postmortem" : "View Postmortem";
    });
  }

  // Right Panel Subtabs
  const rTabEvalBtn = document.getElementById("right-tab-eval-btn");
  const rTabHistBtn = document.getElementById("right-tab-history-btn");
  const rEvalPane = document.getElementById("right-eval-pane");
  const rHistPane = document.getElementById("right-history-pane");

  if (rTabEvalBtn && rTabHistBtn && rEvalPane && rHistPane) {
    rTabEvalBtn.addEventListener("click", () => {
      rTabEvalBtn.classList.add("active");
      rTabHistBtn.classList.remove("active");
      rEvalPane.style.display = "flex";
      rHistPane.style.display = "none";
    });

    rTabHistBtn.addEventListener("click", () => {
      rTabHistBtn.classList.add("active");
      rTabEvalBtn.classList.remove("active");
      rHistPane.style.display = "flex";
      rEvalPane.style.display = "none";
      fetchHistory();
    });
  }

  // Right Panel Evidence Toggle
  const btnToggleRightEv = document.getElementById("btn-toggle-right-evidence");
  const rightEvContainer = document.getElementById("right-evidence-container");
  if (btnToggleRightEv && rightEvContainer) {
    btnToggleRightEv.addEventListener("click", () => {
      const isHidden = rightEvContainer.style.display === "none";
      rightEvContainer.style.display = isHidden ? "block" : "none";
      btnToggleRightEv.textContent = isHidden ? "Hide Evidence" : "Show Evidence";
    });
  }

  // Right Panel Postmortem Toggle
  const btnToggleRightPm = document.getElementById("btn-toggle-right-postmortem");
  const rightPmContainer = document.getElementById("right-report-postmortem-container");
  if (btnToggleRightPm && rightPmContainer) {
    btnToggleRightPm.addEventListener("click", () => {
      const isHidden = rightPmContainer.style.display === "none";
      rightPmContainer.style.display = isHidden ? "flex" : "none";
      btnToggleRightPm.textContent = isHidden ? "Hide Postmortem" : "View Postmortem";
    });
  }

  // Filter Library
  const filterCat = document.getElementById("filter-category");
  if (filterCat) filterCat.addEventListener("change", fetchLibrary);
  const filterDiff = document.getElementById("filter-difficulty");
  if (filterDiff) filterDiff.addEventListener("change", fetchLibrary);
  document.getElementById("btn-refresh-progress").addEventListener("click", fetchProgress);

  const btnRefreshHistory = document.getElementById("btn-refresh-history");
  if (btnRefreshHistory) btnRefreshHistory.addEventListener("click", fetchHistory);

  // Interview Mode
  document.getElementById("btn-new-interview").addEventListener("click", fetchInterviewQuestion);
  document.getElementById("btn-submit-interview-ans").addEventListener("click", submitInterviewAnswer);
}

// --- Authentication UI & Handlers ---

function initAuth() {
  const btnOpenAuth = document.getElementById("btn-open-auth");
  if (btnOpenAuth) btnOpenAuth.addEventListener("click", () => openAuthModal("login"));

  const btnCloseAuth = document.getElementById("btn-close-auth");
  if (btnCloseAuth) btnCloseAuth.addEventListener("click", closeAuthModal);

  const tabLogin = document.getElementById("tab-auth-login");
  const tabReg = document.getElementById("tab-auth-register");
  if (tabLogin) tabLogin.addEventListener("click", () => switchAuthTab("login"));
  if (tabReg) tabReg.addEventListener("click", () => switchAuthTab("register"));

  const btnSubmitAuth = document.getElementById("btn-submit-auth");
  if (btnSubmitAuth) btnSubmitAuth.addEventListener("click", handleAuthSubmit);

  const authForm = document.getElementById("auth-form");
  if (authForm) {
    authForm.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleAuthSubmit();
      }
    });
  }

  const btnLogout = document.getElementById("btn-logout");
  if (btnLogout) btnLogout.addEventListener("click", handleLogout);
}

function switchAuthTab(mode) {
  authMode = mode;
  const tabLogin = document.getElementById("tab-auth-login");
  const tabReg = document.getElementById("tab-auth-register");
  const title = document.getElementById("auth-modal-title");
  const btnSubmit = document.getElementById("btn-submit-auth");
  const errBox = document.getElementById("auth-error-msg");
  if (errBox) errBox.style.display = "none";

  if (mode === "login") {
    if (tabLogin) tabLogin.classList.add("active");
    if (tabReg) tabReg.classList.remove("active");
    if (title) title.textContent = "Sign In to Linux Lab";
    if (btnSubmit) btnSubmit.textContent = "Sign In";
  } else {
    if (tabLogin) tabLogin.classList.remove("active");
    if (tabReg) tabReg.classList.add("active");
    if (title) title.textContent = "Create an Account";
    if (btnSubmit) btnSubmit.textContent = "Create Account";
  }
}

function openAuthModal(mode = "login") {
  switchAuthTab(mode);
  const userIn = document.getElementById("auth-username");
  const passIn = document.getElementById("auth-password");
  if (userIn) userIn.value = "";
  if (passIn) passIn.value = "";
  const errBox = document.getElementById("auth-error-msg");
  if (errBox) errBox.style.display = "none";
  document.getElementById("auth-modal").classList.add("open");
  if (userIn) setTimeout(() => userIn.focus(), 50);
}

function closeAuthModal() {
  document.getElementById("auth-modal").classList.remove("open");
}

async function handleAuthSubmit() {
  const username = (document.getElementById("auth-username").value || "").trim();
  const password = document.getElementById("auth-password").value || "";
  const errBox = document.getElementById("auth-error-msg");

  if (!username || !password) {
    if (errBox) {
      errBox.style.display = "block";
      errBox.textContent = "Please enter both username and password.";
    }
    return;
  }

  const endpoint = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) {
      if (errBox) {
        errBox.style.display = "block";
        errBox.textContent = data.detail || "Authentication request failed.";
      }
      return;
    }

    authToken = data.token;
    localStorage.setItem("linuxlab_token", authToken);
    currentUser = data.user;
    closeAuthModal();
    updateAuthUI();
    connectTerminalWs();
    fetchStatus();
    fetchProgress();
    fetchHistory();
  } catch (e) {
    if (errBox) {
      errBox.style.display = "block";
      errBox.textContent = "Network error: " + e;
    }
  }
}

async function handleLogout() {
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: authToken ? { "Authorization": `Bearer ${authToken}` } : {}
    });
  } catch (e) {}

  authToken = "";
  localStorage.removeItem("linuxlab_token");
  currentUser = null;
  updateAuthUI();
  connectTerminalWs();
  fetchStatus();
  fetchProgress();
  fetchHistory();
}

async function checkAuthStatus() {
  if (!authToken) {
    currentUser = null;
    updateAuthUI();
    return;
  }
  try {
    const res = await apiFetch("/api/auth/me");
    if (res.ok) {
      const data = await res.json();
      currentUser = data.user;
      updateAuthUI();
      fetchHistory();
    } else {
      currentUser = null;
      authToken = "";
      localStorage.removeItem("linuxlab_token");
      updateAuthUI();
    }
  } catch (e) {
    currentUser = null;
    updateAuthUI();
  }
}

function updateAuthUI() {
  const userPill = document.getElementById("auth-user-pill");
  const btnOpenAuth = document.getElementById("btn-open-auth");
  const userDisplay = document.getElementById("user-display-name");
  const welcomeMsg = document.getElementById("dashboard-welcome-msg");
  const welcomeSub = document.getElementById("dashboard-welcome-sub");

  if (currentUser) {
    if (userPill) userPill.style.display = "flex";
    if (btnOpenAuth) btnOpenAuth.style.display = "none";
    if (userDisplay) userDisplay.textContent = `👤 ${currentUser.username}`;
    if (welcomeMsg) welcomeMsg.textContent = `WELCOME, ${currentUser.username.toUpperCase()}`;
    if (welcomeSub) welcomeSub.textContent = "Personalized DevOps learning progress and attempt history.";
  } else {
    if (userPill) userPill.style.display = "none";
    if (btnOpenAuth) btnOpenAuth.style.display = "inline-flex";
    if (welcomeMsg) welcomeMsg.textContent = "WELCOME, GUEST";
    if (welcomeSub) welcomeSub.textContent = "Sign in to save attempts, track level mastery, and access your personal learning history.";
  }
}

function switchToTab(tabId) {
  const btn = document.querySelector(`.btn-nav[data-tab="${tabId}"]`);
  if (btn) btn.click();
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderHelpArea(incident) {
  const hintsUsed = (incident && incident.hints_used) || [];
  const count = hintsUsed.length;
  const counterEl = document.getElementById("help-hint-counter");
  const btn = document.getElementById("btn-request-hint");
  const hintsList = document.getElementById("revealed-hints-list");
  const descEl = document.getElementById("help-box-desc");

  if (counterEl) {
    counterEl.textContent = `HINTS: ${count}/3`;
  }

  if (count === 0) {
    if (descEl) descEl.textContent = "Stuck? Reveal an approach hint when you're unsure how to proceed.";
    if (hintsList) {
      hintsList.style.display = "none";
      hintsList.innerHTML = "";
    }
    if (btn) {
      btn.textContent = "Show Approach Hint";
      btn.disabled = false;
      btn.style.display = "inline-flex";
    }
  } else {
    if (descEl) descEl.textContent = "Revealed approach guidance:";
    if (hintsList) {
      hintsList.style.display = "flex";
      const unlocked = (incident && incident.unlocked_hints) || [];
      if (unlocked.length > 0) {
        hintsList.innerHTML = unlocked.map(h => `
          <div class="revealed-hint-item">
            <div class="revealed-hint-header">
              <span class="revealed-hint-level">Hint ${h.level} — ${escapeHtml(h.type_label)}</span>
              <span class="revealed-hint-penalty">-${h.penalty} pts</span>
            </div>
            <div class="revealed-hint-text">${escapeHtml(h.hint)}</div>
          </div>
        `).join("");
      }
    }

    if (btn) {
      if (count >= 3) {
        btn.textContent = "All Hints Revealed";
        btn.disabled = true;
      } else {
        btn.textContent = "Show Stronger Hint";
        btn.disabled = false;
        btn.style.display = "inline-flex";
      }
    }
  }
}

async function requestApproachHint() {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  const btn = document.getElementById("btn-request-hint");
  if (!btn || btn.disabled) return;
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Revealing Hint...";

  try {
    const res = await apiFetch("/api/incidents/hint", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Failed to unlock hint.");
      btn.disabled = false;
      btn.textContent = originalText;
      return;
    }
    const data = await res.json();
    if (data.exhausted) {
      btn.textContent = "All Hints Revealed";
      btn.disabled = true;
    }
    await fetchStatus();
  } catch (e) {
    alert("Error unlocking hint: " + e);
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// --- Hints Modal Logic ---

function openHintModal() {
  document.getElementById("hint-modal").classList.add("open");
  if (!currentIncident || currentIncident.hints_used.length === 0) {
    document.getElementById("btn-unlock-next-hint").click();
  }
}

function closeHintModal() {
  document.getElementById("hint-modal").classList.remove("open");
}

function renderHintsInModal(data) {
  const body = document.getElementById("hint-modal-body");
  if (data.exhausted) {
    body.innerHTML = `
      <div style="color: var(--accent-yellow); font-size: 13px; margin-bottom: 12px;">
        All hints have been revealed.
      </div>
    `;
    data.hints.forEach((h, idx) => {
      const div = document.createElement("div");
      div.className = "hint-card";
      div.innerHTML = `<div class="hint-header">Hint #${idx + 1}</div><div class="hint-text">${h}</div>`;
      body.appendChild(div);
    });
    document.getElementById("btn-unlock-next-hint").style.display = "none";
    return;
  }

  const div = document.createElement("div");
  div.className = "hint-card";
  const typeLabel = data.type_label || `Hint Level ${data.level}`;
  div.innerHTML = `
    <div class="hint-header">${typeLabel} (-${data.penalty} pts penalty)</div>
    <div class="hint-text">${data.hint}</div>
  `;
  body.appendChild(div);

  if (data.level >= 3) {
    document.getElementById("btn-unlock-next-hint").style.display = "none";
  }
}

// --- Evaluate Modal Logic ---

function openEvaluateModal() {
  document.getElementById("eval-form").style.display = "block";
  document.getElementById("eval-report").style.display = "none";
  document.getElementById("eval-footer").style.display = "none";
  document.getElementById("eval-explanation-input").value = "";

  const evContainer = document.getElementById("evidence-container");
  const btnToggleEv = document.getElementById("btn-toggle-evidence");
  if (evContainer) evContainer.style.display = "none";
  if (btnToggleEv) btnToggleEv.textContent = "Show Evidence";

  const pmContainer = document.getElementById("report-postmortem-container");
  const btnTogglePm = document.getElementById("btn-toggle-postmortem");
  if (pmContainer) pmContainer.style.display = "none";
  if (btnTogglePm) btnTogglePm.textContent = "View Postmortem";

  const feedbackSection = document.getElementById("report-feedback-section");
  if (feedbackSection) feedbackSection.style.display = "none";

  document.getElementById("evaluate-modal").classList.add("open");
}

function closeEvaluateModal() {
  document.getElementById("evaluate-modal").classList.remove("open");
}

function renderEvaluationReport(report) {
  document.getElementById("eval-form").style.display = "none";
  document.getElementById("eval-report").style.display = "flex";
  document.getElementById("eval-footer").style.display = "flex";

  const badge = document.getElementById("report-badge");
  const isSolved = Boolean(report.is_solved);
  const verdict = report.overall_verdict || (isSolved ? "INCIDENT RESOLVED" : "INCIDENT UNRESOLVED");
  if (isSolved) {
    badge.textContent = `✅ ${verdict}`;
    badge.className = "report-result-badge result-solved";
    document.getElementById("btn-eval-next").style.display = "inline-flex";
  } else {
    badge.textContent = `❌ ${verdict}`;
    badge.className = "report-result-badge result-failed";
    document.getElementById("btn-eval-next").style.display = "none";
  }

  document.getElementById("report-score").textContent = `${report.score}/100`;
  document.getElementById("report-signal").textContent = report.feedback_msg;

  // Explanation feedback callout (shows when system state passed but explanation needs improvement)
  const feedbackSection = document.getElementById("report-feedback-section");
  const feedbackEl = document.getElementById("report-explanation-feedback");
  if (feedbackSection && feedbackEl) {
    if (report.explanation_feedback) {
      feedbackSection.style.display = "block";
      feedbackEl.textContent = report.explanation_feedback;
    } else {
      feedbackSection.style.display = "none";
    }
  }

  // Four Dimensions Grid
  const dimGrid = document.getElementById("eval-dimensions-grid");
  if (dimGrid) {
    dimGrid.innerHTML = "";
    const dims = report.dimensions || {};
    const dimKeys = [
      { key: "system_state", title: "System State" },
      { key: "root_cause", title: "Root Cause / Diagnosis" },
      { key: "remediation", title: "Remediation" },
      { key: "explanation", title: "Explanation" }
    ];

    dimKeys.forEach(({ key, title }) => {
      const data = dims[key] || { status: "UNKNOWN", detail: "" };
      const status = (data.status || "UNKNOWN").toUpperCase();
      let badgeClass = "badge-unknown";
      if (status === "PASS") badgeClass = "badge-pass";
      else if (status === "PARTIAL") badgeClass = "badge-partial";
      else if (status === "NEEDS IMPROVEMENT") badgeClass = "badge-needs-improvement";
      else if (status === "FAIL") badgeClass = "badge-fail";

      const scoreText = (data.score !== undefined && data.max_score) ? ` (${data.score}/${data.max_score} pts)` : "";

      const card = document.createElement("div");
      card.className = "dim-card";
      card.innerHTML = `
        <div class="dim-header">
          <span class="dim-title">${data.name || title}</span>
          <span class="dim-badge ${badgeClass}">${status}</span>
        </div>
        <div class="dim-detail">${data.detail || ""}${scoreText}</div>
      `;
      dimGrid.appendChild(card);
    });
  }

  // Machine Evidence Summary Table
  const evidenceContainer = document.getElementById("evidence-container");
  const btnToggleEv = document.getElementById("btn-toggle-evidence");
  if (evidenceContainer) {
    evidenceContainer.style.display = "none";
    if (btnToggleEv) btnToggleEv.textContent = "Show Evidence";

    if (report.evidence && report.evidence.summary && report.evidence.summary.length > 0) {
      let html = `<table class="evidence-table">
        <thead>
          <tr>
            <th>Metric / Subsystem</th>
            <th>Before Fix</th>
            <th>After Fix</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>`;
      report.evidence.summary.forEach((item) => {
        const isPass = item.status === "PASS" || item.status === "HEALTHY";
        const badgeCls = isPass ? "badge-pass" : "badge-fail";
        html += `<tr>
          <td><strong>${item.metric}</strong><br><span style="color: var(--text-muted); font-size: 11px;">${item.detail || ""}</span></td>
          <td style="color: var(--accent-red); font-family: monospace;">${item.before || "N/A"}</td>
          <td style="color: var(--accent-green); font-family: monospace;">${item.after || "N/A"}</td>
          <td><span class="dim-badge ${badgeCls}">${item.status}</span></td>
        </tr>`;
      });
      html += `</tbody></table>`;
      evidenceContainer.innerHTML = html;
    } else {
      evidenceContainer.innerHTML = `<div style="font-size: 12px; color: var(--text-muted); padding: 8px;">No machine evidence recorded.</div>`;
    }
  }

  // Render structured postmortem sections matching level
  const pmContainer = document.getElementById("report-postmortem-container");
  const btnTogglePm = document.getElementById("btn-toggle-postmortem");
  if (pmContainer) {
    pmContainer.style.display = "none";
    if (btnTogglePm) btnTogglePm.textContent = "View Postmortem";
    pmContainer.innerHTML = "";
    if (report.structured_postmortem && report.structured_postmortem.sections) {
      const rawSecs = report.structured_postmortem.sections;
      const entries = Array.isArray(rawSecs)
        ? rawSecs.map((s) => [s.title, s.content])
        : Object.entries(rawSecs);

      entries.forEach(([title, content]) => {
        const card = document.createElement("div");
        card.className = "postmortem-card";
        card.innerHTML = `
          <div class="postmortem-title">${title}</div>
          <div class="postmortem-body">${content}</div>
        `;
        pmContainer.appendChild(card);
      });
    } else {
      if (report.expected_root_cause) {
        const rcCard = document.createElement("div");
        rcCard.className = "postmortem-card";
        rcCard.innerHTML = `
          <div class="postmortem-title">Root Cause Diagnosis</div>
          <div class="postmortem-body">${report.expected_root_cause}</div>
        `;
        pmContainer.appendChild(rcCard);
      }
      if (report.expected_fix) {
        const fixCard = document.createElement("div");
        fixCard.className = "postmortem-card";
        fixCard.innerHTML = `
          <div class="postmortem-title">Remediation & Fix</div>
          <div class="postmortem-body">${report.expected_fix}</div>
        `;
        pmContainer.appendChild(fixCard);
      }
    }
  }

  if (report.ai_critique && report.ai_critique.trim()) {
    document.getElementById("report-ai-section").style.display = "block";
    document.getElementById("report-ai-critique").textContent = report.ai_critique;
  } else {
    document.getElementById("report-ai-section").style.display = "none";
  }

  const learningsList = document.getElementById("report-learnings");
  learningsList.innerHTML = "";
  if (report.learning_points) {
    report.learning_points.forEach((pt) => {
      const li = document.createElement("li");
      li.textContent = pt;
      learningsList.appendChild(li);
    });
  }

  // Also render into right panel
  renderRightPanelReport(report);
}

function resetRightPanelEvaluation() {
  const rightNoEvalMsg = document.getElementById("right-no-eval-msg");
  const rightEvalReport = document.getElementById("right-eval-report");
  if (rightNoEvalMsg) rightNoEvalMsg.style.display = "flex";
  if (rightEvalReport) rightEvalReport.style.display = "none";
}

function renderRightPanelReport(report) {
  const rightNoEvalMsg = document.getElementById("right-no-eval-msg");
  const rightEvalReport = document.getElementById("right-eval-report");
  if (rightNoEvalMsg) rightNoEvalMsg.style.display = "none";
  if (rightEvalReport) rightEvalReport.style.display = "flex";

  // Switch to evaluation subtab in right panel
  const rTabEvalBtn = document.getElementById("right-tab-eval-btn");
  const rTabHistBtn = document.getElementById("right-tab-history-btn");
  const rEvalPane = document.getElementById("right-eval-pane");
  const rHistPane = document.getElementById("right-history-pane");
  if (rTabEvalBtn && rTabHistBtn && rEvalPane && rHistPane) {
    rTabEvalBtn.classList.add("active");
    rTabHistBtn.classList.remove("active");
    rEvalPane.style.display = "flex";
    rHistPane.style.display = "none";
  }

  const isSolved = Boolean(report.is_solved);
  const verdict = report.overall_verdict || (isSolved ? "INCIDENT RESOLVED" : "INCIDENT UNRESOLVED");

  const badge = document.getElementById("right-report-badge");
  if (badge) {
    badge.textContent = isSolved ? `✅ ${verdict}` : `❌ ${verdict}`;
    badge.className = isSolved ? "report-result-badge result-solved" : "report-result-badge result-failed";
  }

  const scoreEl = document.getElementById("right-report-score");
  if (scoreEl) scoreEl.textContent = `${report.score}/100`;

  const signalEl = document.getElementById("right-report-signal");
  if (signalEl) signalEl.textContent = report.feedback_msg;

  // Explanation feedback callout
  const feedbackSection = document.getElementById("right-report-feedback-section");
  const explanationFeedback = document.getElementById("right-report-explanation-feedback");
  if (feedbackSection && explanationFeedback) {
    if (report.explanation_feedback) {
      feedbackSection.style.display = "block";
      explanationFeedback.textContent = report.explanation_feedback;
    } else {
      feedbackSection.style.display = "none";
    }
  }

  // Four Dimensions Grid
  const dimGrid = document.getElementById("right-eval-dimensions-grid");
  if (dimGrid) {
    dimGrid.innerHTML = "";
    const dims = [
      { key: "technical_state", label: "1. Technical State" },
      { key: "remediation_quality", label: "2. Remediation Quality" },
      { key: "diagnostic_reasoning", label: "3. Diagnostic Reasoning" },
      { key: "operational_efficiency", label: "4. Efficiency & Signals" },
    ];

    dims.forEach((d) => {
      const dimData = report.dimensions ? report.dimensions[d.key] : null;
      const status = dimData ? (dimData.status || "UNKNOWN") : "UNKNOWN";
      const detail = dimData ? (dimData.detail || "No data recorded") : "No dimension data";
      const score = dimData && dimData.score !== undefined ? `${dimData.score} pts` : "";

      let badgeClass = "badge-unknown";
      if (status === "PASS" || status === "OPTIMAL") badgeClass = "badge-pass";
      else if (status === "PARTIAL" || status === "ACCEPTABLE") badgeClass = "badge-partial";
      else if (status === "NEEDS_IMPROVEMENT") badgeClass = "badge-needs-improvement";
      else if (status === "FAIL" || status === "INEFFICIENT") badgeClass = "badge-fail";

      const card = document.createElement("div");
      card.className = "dim-card";
      card.innerHTML = `
        <div class="dim-header">
          <span class="dim-title">${d.label}</span>
          <span class="dim-badge ${badgeClass}">${status}</span>
        </div>
        <div class="dim-detail">${detail}</div>
        ${score ? `<div style="font-size: 11px; color: var(--text-muted); font-weight: 600; margin-top: 4px;">Score: ${score}</div>` : ""}
      `;
      dimGrid.appendChild(card);
    });
  }

  // State-Based Machine Evidence Section
  const evSection = document.getElementById("right-report-evidence-section");
  const evidenceContainer = document.getElementById("right-evidence-container");
  const btnToggleEv = document.getElementById("btn-toggle-right-evidence");
  if (evSection && evidenceContainer) {
    evidenceContainer.style.display = "none";
    if (btnToggleEv) btnToggleEv.textContent = "Show Evidence";
    evidenceContainer.innerHTML = "";
    if (report.evidence && report.evidence.summary && report.evidence.summary.length > 0) {
      evSection.style.display = "block";
      let html = `<table class="evidence-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Before</th>
            <th>After</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>`;
      report.evidence.summary.forEach((item) => {
        const isPass = item.status === "PASS" || item.status === "HEALTHY";
        const badgeCls = isPass ? "badge-pass" : "badge-fail";
        html += `<tr>
          <td><strong>${item.metric}</strong><br><span style="color: var(--text-muted); font-size: 10px;">${item.detail || ""}</span></td>
          <td style="color: var(--accent-red); font-family: monospace; font-size: 11px;">${item.before || "N/A"}</td>
          <td style="color: var(--accent-green); font-family: monospace; font-size: 11px;">${item.after || "N/A"}</td>
          <td><span class="dim-badge ${badgeCls}">${item.status}</span></td>
        </tr>`;
      });
      html += `</tbody></table>`;
      evidenceContainer.innerHTML = html;
    } else {
      evSection.style.display = "block";
      evidenceContainer.innerHTML = `<div style="font-size: 12px; color: var(--text-muted); padding: 8px;">No machine evidence recorded.</div>`;
    }
  }

  // Structured postmortem sections
  const pmContainer = document.getElementById("right-report-postmortem-container");
  const btnTogglePm = document.getElementById("btn-toggle-right-postmortem");
  if (pmContainer) {
    pmContainer.style.display = "none";
    if (btnTogglePm) btnTogglePm.textContent = "View Postmortem";
    pmContainer.innerHTML = "";
    if (report.structured_postmortem && report.structured_postmortem.sections) {
      const rawSecs = report.structured_postmortem.sections;
      const entries = Array.isArray(rawSecs)
        ? rawSecs.map((s) => [s.title, s.content])
        : Object.entries(rawSecs);

      entries.forEach(([title, content]) => {
        const card = document.createElement("div");
        card.className = "postmortem-card";
        card.innerHTML = `
          <div class="postmortem-title">${title}</div>
          <div class="postmortem-body">${content}</div>
        `;
        pmContainer.appendChild(card);
      });
    } else {
      if (report.expected_root_cause) {
        const rcCard = document.createElement("div");
        rcCard.className = "postmortem-card";
        rcCard.innerHTML = `
          <div class="postmortem-title">Root Cause Diagnosis</div>
          <div class="postmortem-body">${report.expected_root_cause}</div>
        `;
        pmContainer.appendChild(rcCard);
      }
      if (report.expected_fix) {
        const fixCard = document.createElement("div");
        fixCard.className = "postmortem-card";
        fixCard.innerHTML = `
          <div class="postmortem-title">Remediation & Fix</div>
          <div class="postmortem-body">${report.expected_fix}</div>
        `;
        pmContainer.appendChild(fixCard);
      }
    }
  }

  // AI Senior SRE Feedback
  const aiSection = document.getElementById("right-report-ai-section");
  const aiCritique = document.getElementById("right-report-ai-critique");
  if (aiSection && aiCritique) {
    if (report.ai_critique && report.ai_critique.trim()) {
      aiSection.style.display = "block";
      aiCritique.textContent = report.ai_critique;
    } else {
      aiSection.style.display = "none";
    }
  }

  // Key DevOps Takeaways
  const learningsList = document.getElementById("right-report-learnings");
  if (learningsList) {
    learningsList.innerHTML = "";
    if (report.learning_points && report.learning_points.length > 0) {
      report.learning_points.forEach((pt) => {
        const li = document.createElement("li");
        li.textContent = pt;
        learningsList.appendChild(li);
      });
      learningsList.parentElement.style.display = "block";
    } else {
      learningsList.parentElement.style.display = "none";
    }
  }
}

// --- Scenario Library ---

async function fetchLibrary() {
  try {
    const cat = document.getElementById("filter-category") ? document.getElementById("filter-category").value : "";
    const diff = document.getElementById("filter-difficulty") ? document.getElementById("filter-difficulty").value : "";
    const lvl = document.getElementById("filter-level") ? document.getElementById("filter-level").value : "";
    const params = new URLSearchParams();
    if (cat) params.append("category", cat);
    if (diff) params.append("difficulty", diff);
    if (lvl) params.append("level", lvl);

    const res = await fetch(`/api/scenarios?${params.toString()}`);
    const scenarios = await res.json();

    const tbody = document.getElementById("scenarios-tbody");
    tbody.innerHTML = "";

    scenarios.forEach((s) => {
      const tr = document.createElement("tr");
      const rowLvl = (s.level || s.difficulty || "EASY").toUpperCase();
      const lvlClass = "badge-level-" + rowLvl.toLowerCase();
      tr.innerHTML = `
        <td style="font-family: var(--font-mono); font-weight: 700; color: var(--accent-cyan);">${s.id}</td>
        <td><span class="badge badge-cat">${s.category}</span></td>
        <td><span class="badge badge-level ${lvlClass}">${rowLvl}</span></td>
        <td style="font-weight: 600; color: var(--text-bright);">${s.title}</td>
        <td><button class="btn btn-primary" style="padding: 4px 10px; font-size: 12px;" onclick="loadSpecificScenario('${s.id}')">Start Incident</button></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Library fetch error:", e);
  }
}

window.loadSpecificScenario = async function(id) {
  if (!currentUser) {
    openAuthModal("login");
    return;
  }
  try {
    const res = await apiFetch(`/api/incidents/${id}/start`, { method: "POST" });
    if (res.ok) {
      resetRightPanelEvaluation();
      switchToTab("incident-pane");
      connectTerminalWs();
      fetchStatus();
    } else {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "Failed to start scenario " + id);
    }
  } catch (e) {
    alert("Error loading scenario: " + e);
  }
};

// --- Progress Dashboard ---

async function fetchProgress() {
  try {
    const res = await apiFetch("/api/progress");
    const data = await res.json();

    document.getElementById("stat-total").textContent = data.total_incidents || 0;
    document.getElementById("stat-solved").textContent = data.solved_count || 0;
    const rate = data.resolution_rate !== undefined ? data.resolution_rate : (data.total_incidents ? Math.round((data.solved_count / data.total_incidents) * 100) : 0);
    const rateEl = document.getElementById("stat-rate");
    if (rateEl) rateEl.textContent = `${rate}%`;
    document.getElementById("stat-avg").textContent = `${data.avg_score || 0}/100`;

    const overallScoreEl = document.getElementById("dashboard-overall-score");
    if (overallScoreEl) {
      overallScoreEl.textContent = data.overall_score !== undefined ? `${data.overall_score}/100` : `${data.avg_score || 0}/100`;
    }

    if (currentUser && currentUser.username) {
      document.getElementById("dashboard-welcome-msg").textContent = `WELCOME, ${currentUser.username.toUpperCase()}`;
    }

    // Render progressive level mastery rows
    const lvlTbody = document.getElementById("level-progress-tbody");
    if (lvlTbody && data.levels) {
      lvlTbody.innerHTML = "";
      const order = ["EASY", "MODERATE", "FLUENT", "ADVANCED", "EXPERT"];
      order.forEach((lvl) => {
        const stats = data.levels[lvl] || { attempted: 0, solved: 0, rate: 0, avg_score: 0, bar: "░░░░░░░░░░" };
        const tr = document.createElement("tr");
        const rateColor = stats.rate >= 80 ? "var(--accent-green)" : (stats.rate >= 50 ? "var(--accent-yellow)" : "var(--text-muted)");
        const lvlClass = "badge-level-" + lvl.toLowerCase();
        tr.innerHTML = `
          <td><span class="badge badge-level ${lvlClass}">${lvl}</span></td>
          <td style="font-family: var(--font-mono); color: var(--accent-green); letter-spacing: 2px;">${stats.bar || "░░░░░░░░░░"}</td>
          <td>${stats.solved} / 5 solved (${stats.attempted} attempted)</td>
          <td style="color: ${rateColor}; font-weight: 700;">${stats.rate}%</td>
          <td>${stats.avg_score}/100</td>
        `;
        lvlTbody.appendChild(tr);
      });
    }

    // Render recent attempts
    const recentTbody = document.getElementById("recent-attempts-tbody");
    if (recentTbody) {
      const recent = data.recent_attempts || [];
      if (recent.length === 0) {
        recentTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 14px;">No attempts recorded yet.</td></tr>`;
      } else {
        recentTbody.innerHTML = "";
        recent.forEach((a) => {
          const tr = document.createElement("tr");
          const isSolved = a.status === "SOLVED";
          const statusBadge = isSolved
            ? `<span class="status-badge-solved">SOLVED</span>`
            : `<span class="status-badge-unresolved">UNRESOLVED</span>`;
          const scoreClass = a.score >= 80 ? "high" : (a.score >= 60 ? "medium" : "low");
          const dateStr = a.created_at ? new Date(a.created_at).toLocaleString() : "Just now";
          tr.innerHTML = `
            <td><strong>${a.scenario_title || a.scenario_id}</strong></td>
            <td><span class="badge badge-level badge-level-${(a.level || 'EASY').toLowerCase()}">${a.level || 'EASY'}</span></td>
            <td>${statusBadge}</td>
            <td><span class="score-badge ${scoreClass}">${a.score}/100</span></td>
            <td style="color: var(--text-muted); font-size: 12px;">${dateStr}</td>
          `;
          recentTbody.appendChild(tr);
        });
      }
    }

    if (data.recommended_level || data.recommended_next_level) {
      const recEl = document.getElementById("recommended-level-text");
      if (recEl) recEl.textContent = data.recommended_level || data.recommended_next_level;
    }

    const tbody = document.getElementById("progress-tbody");
    if (tbody && data.categories) {
      tbody.innerHTML = "";
      for (const [cat, stats] of Object.entries(data.categories)) {
        const tr = document.createElement("tr");
        const rateColor = stats.rate >= 80 ? "var(--accent-green)" : (stats.rate >= 50 ? "var(--accent-yellow)" : "var(--accent-red)");
        tr.innerHTML = `
          <td style="font-weight: 700; text-transform: uppercase;">${cat}</td>
          <td>${stats.attempted}</td>
          <td>${stats.solved}</td>
          <td style="color: ${rateColor}; font-weight: 700;">${stats.rate !== undefined ? stats.rate : (stats.success_rate || 0)}%</td>
          <td>${stats.avg_score}/100</td>
        `;
        tbody.appendChild(tr);
      }
    }

    const weakBox = document.getElementById("weak-areas-box");
    if (data.weak_areas && data.weak_areas.length > 0) {
      weakBox.style.display = "block";
      document.getElementById("weak-areas-text").textContent = data.weak_areas.join(", ");
    } else if (data.weakest && data.weakest.length > 0) {
      weakBox.style.display = "block";
      document.getElementById("weak-areas-text").textContent = data.weakest.map(w => w.toUpperCase()).join(", ");
    } else {
      weakBox.style.display = "none";
    }
  } catch (e) {
    console.error("Progress fetch error:", e);
  }
}

// --- History View ---

async function fetchHistory() {
  const rightEmpty = document.getElementById("right-history-empty");
  const rightList = document.getElementById("right-history-list");
  const rightCount = document.getElementById("right-history-count");

  if (!currentUser) {
    const emptyMsg = document.getElementById("history-empty-msg");
    if (emptyMsg) {
      emptyMsg.style.display = "block";
      emptyMsg.textContent = "Please sign in to view your incident attempt history.";
    }
    const tbody = document.getElementById("history-tbody");
    if (tbody) tbody.innerHTML = "";
    if (rightEmpty) {
      rightEmpty.style.display = "block";
      rightEmpty.textContent = "Please sign in to view saved attempt history.";
    }
    if (rightList) rightList.innerHTML = "";
    if (rightCount) rightCount.textContent = "0";
    return;
  }

  try {
    const res = await apiFetch("/api/history");
    if (!res.ok) return;
    const attempts = await res.json();

    const emptyMsg = document.getElementById("history-empty-msg");
    const tbody = document.getElementById("history-tbody");
    if (rightCount) rightCount.textContent = attempts.length;

    if (attempts.length === 0) {
      if (emptyMsg) {
        emptyMsg.style.display = "block";
        emptyMsg.textContent = "No completed attempts recorded yet. Solve an incident to view your historical evaluations and postmortems.";
      }
      if (tbody) tbody.innerHTML = "";
      if (rightEmpty) {
        rightEmpty.style.display = "block";
        rightEmpty.textContent = "No completed attempts recorded yet.";
      }
      if (rightList) rightList.innerHTML = "";
      return;
    }

    if (emptyMsg) emptyMsg.style.display = "none";
    if (rightEmpty) rightEmpty.style.display = "none";
    if (tbody) tbody.innerHTML = "";
    if (rightList) rightList.innerHTML = "";

    attempts.forEach((a) => {
      const isSolved = a.status === "SOLVED";
      const statusBadge = isSolved
        ? `<span class="status-badge-solved">SOLVED</span>`
        : `<span class="status-badge-unresolved">UNRESOLVED</span>`;
      const scoreClass = a.score >= 80 ? "high" : (a.score >= 60 ? "medium" : "low");
      const dateStr = a.created_at ? new Date(a.created_at).toLocaleString() : "N/A";
      const durationStr = a.duration_sec ? `${Math.round(a.duration_sec)}s` : "<1m";

      if (tbody) {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>
            <strong>${a.scenario_title || a.scenario_id}</strong>
            <div style="font-size: 11px; color: var(--text-muted);">${a.scenario_id}</div>
          </td>
          <td><span class="badge badge-level badge-level-${(a.level || 'EASY').toLowerCase()}">${a.level || 'EASY'}</span></td>
          <td>${statusBadge}</td>
          <td><span class="score-badge ${scoreClass}">${a.score}/100</span></td>
          <td>${durationStr}</td>
          <td style="color: var(--text-muted); font-size: 12px;">${dateStr}</td>
          <td>
            <button class="btn btn-sm" onclick="inspectHistoryAttempt('${a.id}')" style="font-size: 11px; padding: 2px 8px;">Inspect Report</button>
          </td>
        `;
        tbody.appendChild(tr);
      }

      if (rightList) {
        const card = document.createElement("div");
        card.className = "right-history-card";
        const shortDate = a.created_at ? new Date(a.created_at).toLocaleDateString() : "";
        card.innerHTML = `
          <div class="right-history-header">
            <span class="right-history-title">${escapeHtml(a.scenario_title || a.scenario_id)}</span>
            <span class="score-badge ${scoreClass}">${a.score}/100</span>
          </div>
          <div class="right-history-meta">
            <span class="badge badge-level badge-level-${(a.level || 'EASY').toLowerCase()}">${a.level || 'EASY'}</span>
            ${statusBadge}
            <span>${shortDate}</span>
          </div>
        `;
        card.addEventListener("click", () => {
          inspectHistoryAttempt(a.id);
        });
        rightList.appendChild(card);
      }
    });
  } catch (e) {
    console.error("History fetch error:", e);
  }
}

window.inspectHistoryAttempt = async function(attemptId) {
  try {
    const res = await apiFetch(`/api/history/${attemptId}`);
    if (!res.ok) {
      alert("Failed to load attempt record.");
      return;
    }
    const attempt = await res.json();
    const isSolved = attempt.status === "SOLVED";

    const reportObj = {
      ...attempt,
      is_solved: isSolved,
      structured_postmortem: attempt.postmortem,
      feedback_msg: attempt.technical_resolution || "Machine evaluation record loaded from persistent history."
    };
    renderEvaluationReport(reportObj);

    // Switch to incident workspace & right evaluation subtab to view report cleanly beside terminal
    switchToTab("incident-pane");
    const rTabEvalBtn = document.getElementById("right-tab-eval-btn");
    if (rTabEvalBtn) rTabEvalBtn.click();
    closeEvaluateModal();
  } catch (e) {
    alert("Error loading attempt: " + e);
  }
};

// --- Interview Mode ---

async function fetchInterviewQuestion() {
  try {
    const interviewFilterLvl = document.getElementById("interview-filter-level");
    const lvl = interviewFilterLvl ? interviewFilterLvl.value : "";
    const url = lvl ? `/api/interview/random?level=${encodeURIComponent(lvl)}` : `/api/interview/random`;
    const res = await fetch(url);
    const data = await res.json();
    interviewCurrent = data;
    interviewAnswers = [];

    document.getElementById("interview-topic").textContent = data.topic;
    const qLvl = (data.level || "FLUENT").toUpperCase();
    const qLvlEl = document.getElementById("interview-level");
    if (qLvlEl) {
      qLvlEl.textContent = qLvl;
      qLvlEl.className = "badge badge-level badge-level-" + qLvl.toLowerCase();
    }
    document.getElementById("interview-question").textContent = data.initial_prompt;
    document.getElementById("interview-answer-input").value = "";
    document.getElementById("interview-follow-ups").style.display = "none";
    document.getElementById("interview-result-box").style.display = "none";
    document.getElementById("btn-submit-interview-ans").style.display = "block";
    document.getElementById("btn-submit-interview-ans").textContent = "Submit Answer";
  } catch (e) {
    console.error("Interview question error:", e);
  }
}

async function submitInterviewAnswer() {
  const ans = document.getElementById("interview-answer-input").value.trim();
  if (!ans) {
    alert("Please enter your diagnostic answer first.");
    return;
  }

  const followContainer = document.getElementById("interview-follow-ups");
  followContainer.innerHTML = "";
  followContainer.style.display = "flex";

  interviewCurrent.follow_ups.forEach((fq, idx) => {
    const box = document.createElement("div");
    box.style.display = "flex";
    box.style.flexDirection = "column";
    box.style.gap = "6px";
    box.innerHTML = `
      <label style="font-size: 13px; font-weight: 600; color: var(--accent-yellow);">Follow-up #${idx+1}: ${fq}</label>
      <textarea class="follow-up-ans" placeholder="Your answer..."></textarea>
    `;
    followContainer.appendChild(box);
  });

  const submitBtn = document.getElementById("btn-submit-interview-ans");
  submitBtn.textContent = "Finalize Interview & View SRE Benchmark";
  submitBtn.onclick = finalizeInterview;
}

async function finalizeInterview() {
  const initialAns = document.getElementById("interview-answer-input").value.trim();
  const followUpInputs = document.querySelectorAll(".follow-up-ans");
  const followUpAns = Array.from(followUpInputs).map(i => i.value.trim());

  const btn = document.getElementById("btn-submit-interview-ans");
  btn.disabled = true;
  btn.textContent = "Evaluating...";

  try {
    const res = await fetch("/api/interview/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_id: interviewCurrent.id,
        initial_answer: initialAns,
        follow_up_answers: followUpAns,
      }),
    });
    const data = await res.json();

    document.getElementById("interview-result-box").style.display = "flex";
    document.getElementById("interview-sre-breakdown").textContent = data.sre_breakdown;

    if (data.ai_evaluation) {
      document.getElementById("interview-ai-box").style.display = "block";
      document.getElementById("interview-ai-feedback").textContent = data.ai_evaluation;
    } else {
      document.getElementById("interview-ai-box").style.display = "none";
    }
  } catch (e) {
    alert("Interview evaluation error: " + e);
  } finally {
    btn.disabled = false;
    btn.style.display = "none";
  }
}
