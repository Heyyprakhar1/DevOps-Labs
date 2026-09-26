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
  selectLevel(selectedLevel, false);
  fetchStatus();
  fetchLibrary();
  fetchProgress();

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
  const wsUrl = `${protocol}//${window.location.host}/ws/terminal`;

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

      // Investigation Guidance
      const guidanceSec = document.getElementById("guidance-section");
      const guidanceBox = document.getElementById("incident-guidance");
      if (guidanceSec && guidanceBox) {
        if (incident.investigation_guidance && incident.investigation_guidance.trim()) {
          guidanceSec.style.display = "block";
          guidanceBox.textContent = incident.investigation_guidance;
        } else {
          guidanceSec.style.display = "none";
        }
      }

      // Recommended Tools
      const toolsSec = document.getElementById("tools-section");
      const toolsBox = document.getElementById("incident-tools");
      if (toolsSec && toolsBox) {
        if (incident.expected_tools && incident.expected_tools.length > 0) {
          toolsSec.style.display = "block";
          toolsBox.innerHTML = incident.expected_tools
            .map(t => `<span class="tool-tag">${t}</span>`)
            .join(" ");
        } else {
          toolsSec.style.display = "none";
        }
      }

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
    try {
      const res = await fetch("/api/incidents/random", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: selectedLevel }),
      });
      if (res.ok) {
        switchToTab("incident-pane");
        fetchStatus();
      } else {
        alert("Failed to inject random incident. Check lab container status.");
      }
    } catch (e) {
      alert("Error starting incident: " + e);
    }
  });

  // Reset Environment
  document.getElementById("btn-reset-env").addEventListener("click", async () => {
    if (!confirm("Are you sure you want to reset the lab sandbox environment?")) return;
    try {
      const res = await fetch("/api/incidents/reset", { method: "POST" });
      const data = await res.json();
      alert(data.message || "Environment reset complete.");
      fetchStatus();
      // Keep existing terminal session attached to sandbox
    } catch (e) {
      alert("Error resetting environment: " + e);
    }
  });

  // Request Hint
  document.getElementById("btn-request-hint").addEventListener("click", () => {
    openHintModal();
  });

  document.getElementById("btn-unlock-next-hint").addEventListener("click", async () => {
    try {
      const res = await fetch("/api/incidents/hint", { method: "POST" });
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
      const res = await fetch("/api/incidents/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explanation: explanation }),
      });
      const data = await res.json();
      renderEvaluationReport(data);
      fetchStatus();
      fetchProgress();
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

  // Filter Library
  const filterCat = document.getElementById("filter-category");
  if (filterCat) filterCat.addEventListener("change", fetchLibrary);
  const filterDiff = document.getElementById("filter-difficulty");
  if (filterDiff) filterDiff.addEventListener("change", fetchLibrary);
  document.getElementById("btn-refresh-progress").addEventListener("click", fetchProgress);

  // Interview Mode
  document.getElementById("btn-new-interview").addEventListener("click", fetchInterviewQuestion);
  document.getElementById("btn-submit-interview-ans").addEventListener("click", submitInterviewAnswer);
}

function switchToTab(tabId) {
  const btn = document.querySelector(`.btn-nav[data-tab="${tabId}"]`);
  if (btn) btn.click();
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
  if (report.is_solved) {
    badge.textContent = "✅ SOLVED";
    badge.className = "report-result-badge result-solved";
    document.getElementById("btn-eval-next").style.display = "inline-flex";
  } else {
    badge.textContent = "❌ UNRESOLVED / FAILED";
    badge.className = "report-result-badge result-failed";
    document.getElementById("btn-eval-next").style.display = "none";
  }

  document.getElementById("report-score").textContent = `${report.score}/100`;
  document.getElementById("report-signal").textContent = report.feedback_msg;

  // Render structured postmortem sections matching level
  const pmContainer = document.getElementById("report-postmortem-container");
  if (pmContainer) {
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
  try {
    const res = await fetch(`/api/incidents/${id}/start`, { method: "POST" });
    if (res.ok) {
      switchToTab("incident-pane");
      fetchStatus();
    } else {
      alert("Failed to start scenario " + id);
    }
  } catch (e) {
    alert("Error loading scenario: " + e);
  }
};

// --- Progress Dashboard ---

async function fetchProgress() {
  try {
    const res = await fetch("/api/progress");
    const data = await res.json();

    document.getElementById("stat-total").textContent = data.total_incidents;
    document.getElementById("stat-solved").textContent = data.solved_count;
    document.getElementById("stat-avg").textContent = `${data.avg_score}/100`;
    document.getElementById("stat-hints-used").textContent = data.total_hints;

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
          <td style="font-family: var(--font-mono); color: var(--accent-green); letter-spacing: 2px;">${stats.bar}</td>
          <td>${stats.solved} / 5 solved (${stats.attempted} attempted)</td>
          <td style="color: ${rateColor}; font-weight: 700;">${stats.rate}%</td>
          <td>${stats.avg_score}/100</td>
        `;
        lvlTbody.appendChild(tr);
      });
    }

    if (data.recommended_next_level) {
      const recEl = document.getElementById("recommended-level-text");
      if (recEl) recEl.textContent = data.recommended_next_level;
    }

    const tbody = document.getElementById("progress-tbody");
    tbody.innerHTML = "";

    for (const [cat, stats] of Object.entries(data.categories)) {
      const tr = document.createElement("tr");
      const rateColor = stats.rate >= 80 ? "var(--accent-green)" : (stats.rate >= 50 ? "var(--accent-yellow)" : "var(--accent-red)");
      tr.innerHTML = `
        <td style="font-weight: 700; text-transform: uppercase;">${cat}</td>
        <td>${stats.attempted}</td>
        <td>${stats.solved}</td>
        <td style="color: ${rateColor}; font-weight: 700;">${stats.rate}%</td>
        <td>${stats.avg_score}/100</td>
      `;
      tbody.appendChild(tr);
    }

    const weakBox = document.getElementById("weak-areas-box");
    if (data.weakest && data.weakest.length > 0) {
      weakBox.style.display = "block";
      document.getElementById("weak-areas-text").textContent = data.weakest.map(w => w.toUpperCase()).join(", ");
    } else {
      weakBox.style.display = "none";
    }
  } catch (e) {
    console.error("Progress fetch error:", e);
  }
}

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
