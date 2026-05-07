const API = "/api/v1";
const AUTO_REFRESH_MS = 5 * 60 * 1000;

const state = {
  filter: "all",
  health: null,
  costs: null,
  opportunities: [],
  doNow: [],
  drafts: [],
  approvals: [],
  runs: [],
  contacts: [],
  scrapers: [],
  metrics: [],
  currentWeek: null,
  losses: [],
  weights: null,
  strategy: null,
  audit: [],
  cognitive: null,
  lastRefreshAt: null,
  failedPanels: 0,
};

const charts = {
  opps: null,
  revenue: null,
  loss: null,
};

document.addEventListener("DOMContentLoaded", () => {
  primeStaticBits();
  bindEvents();
  refreshDashboard();
  window.setInterval(refreshDashboard, AUTO_REFRESH_MS);
});

function primeStaticBits() {
  const now = new Date();
  const headerDate = document.getElementById("headerDate");
  if (headerDate) {
    headerDate.textContent = now.toLocaleDateString("en-GB", {
      weekday: "long",
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
}

function bindEvents() {
  document.getElementById("refreshButton")?.addEventListener("click", refreshDashboard);
  document.getElementById("updateStateButton")?.addEventListener("click", () => {
    document.getElementById("stateDialog")?.showModal();
  });
  document.getElementById("closeDialogButton")?.addEventListener("click", () => {
    document.getElementById("stateDialog")?.close();
  });
  document
    .getElementById("closeOpportunityDialogButton")
    ?.addEventListener("click", () => document.getElementById("opportunityDialog")?.close());
  document.getElementById("checkinForm")?.addEventListener("submit", submitCheckin);
  document.getElementById("rollbackWeightsButton")?.addEventListener("click", rollbackWeights);

  [
    ["energyInput", "energyValue", " / 10"],
    ["stressInput", "stressValue", " / 10"],
    ["hoursInput", "hoursValue", "h"],
    ["examInput", "examValue", " / 10"],
  ].forEach(([inputId, outputId, suffix]) => {
    const input = document.getElementById(inputId);
    const output = document.getElementById(outputId);
    input?.addEventListener("input", () => {
      output.textContent = `${input.value}${suffix}`;
    });
  });

  document.querySelectorAll("#opportunityFilters .filter-chip").forEach((button) => {
    button.addEventListener("click", () => {
      state.filter = button.dataset.filter || "all";
      document
        .querySelectorAll("#opportunityFilters .filter-chip")
        .forEach((node) => node.classList.toggle("is-active", node === button));
      renderOpportunityTable();
    });
  });
}

async function refreshDashboard() {
  try {
    const results = await Promise.allSettled([
      getJson(`${API}/system/health`),
      getJson(`${API}/system/costs`),
      getJson(`${API}/opportunities?limit=50`),
      getJson(`${API}/opportunities?action_priority=do_now&limit=20`),
      getJson(`${API}/drafts?status=pending`),
      getJson(`${API}/contacts`),
      getJson(`${API}/system/scraper-health`),
      getJson(`${API}/metrics/history?weeks=8`),
      getJson(`${API}/metrics/current-week`),
      getJson(`${API}/metrics/loss-analysis`),
      getJson(`${API}/system/weights`),
      getJson(`${API}/system/strategy`),
      getJson(`${API}/system/audit-log?limit=20`),
      getJson(`${API}/cognitive/today`),
      getJson(`${API}/approvals?status=pending&limit=10`),
      getJson(`${API}/runs?limit=10`),
    ]);

    state.failedPanels = results.filter((result) => result.status !== "fulfilled").length;
    state.lastRefreshAt = new Date();

    state.health = resolved(results[0], null);
    state.costs = resolved(results[1], null);
    state.opportunities = resolved(results[2], { items: [] }).items || [];
    state.doNow = resolved(results[3], { items: [] }).items || [];
    state.drafts = resolved(results[4], { items: [] }).items || [];
    state.contacts = resolved(results[5], []);
    state.scrapers = resolved(results[6], []);
    state.metrics = [...resolved(results[7], [])].reverse();
    state.currentWeek = resolved(results[8], null);
    state.losses = resolved(results[9], []);
    state.weights = resolved(results[10], { current: null, history: [] });
    state.strategy = resolved(results[11], { status: "empty", strategy: null });
    state.audit = resolved(results[12], []);
    state.cognitive = resolved(results[13], null);
    state.approvals = resolved(results[14], { items: [] }).items || [];
    state.runs = resolved(results[15], { items: [] }).items || [];

    renderDashboard();
  } catch (error) {
    setStatus("blocked", "Offline");
    setText("heroCopy", `Backend request failed: ${error.message}`);
  }
}

async function getJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || detail;
    } catch {
      // keep default detail
    }
    throw new Error(detail);
  }
  return response.json();
}

function resolved(result, fallback) {
  return result.status === "fulfilled" ? result.value : fallback;
}

function renderDashboard() {
  renderHeader();
  renderCognitiveBar();
  renderDiagnostics();
  renderApprovals();
  renderRuns();
  renderMetricCards();
  renderOpportunityTable();
  renderFollowups();
  renderDrafts();
  renderScrapers();
  renderStrategy();
  renderCharts();
  renderWeights();
  renderAudit();
}

function renderHeader() {
  if (!state.health) {
    setStatus("blocked", "Offline");
    setText("scraperHealthValue", "0 / 0 healthy");
    setText("costTodayValue", "$0.00");
    setText("geminiCallsValue", "0");
    setText("heroCopy", "Backend health endpoint is unavailable. Live data cannot be trusted right now.");
    return;
  }

  const mode = state.health?.readiness?.mode || state.health?.status || "online";
  const degraded =
    mode === "degraded" ||
    mode === "blocked" ||
    state.health?.llm_degraded ||
    state.health?.llm_cost_paused ||
    state.failedPanels > 0;
  const statusMode = mode === "blocked" ? "blocked" : degraded ? "degraded" : "online";
  const statusLabel = mode === "blocked" ? "Blocked" : degraded ? "Degraded" : "Online";
  setStatus(statusMode, statusLabel);

  const healthy = state.health?.scraper_summary?.healthy ?? 0;
  const total = state.health?.scraper_summary?.total ?? 0;
  setText("scraperHealthValue", `${healthy} / ${total} healthy`);
  setText("costTodayValue", formatCurrency(state.costs?.cost_today_usd ?? 0, "USD"));
  setText("geminiCallsValue", number(state.costs?.calls_today ?? state.health?.gemini_calls_today ?? 0));

  const topMove = state.doNow[0];
  const issues = state.health?.readiness?.issues || [];
  if (issues.length) {
    setText("heroCopy", `System has ${issues.length} blocking issue(s). Fix the diagnostics panel before trusting automation.`);
  } else if (topMove) {
    setText(
      "heroCopy",
      `Top move right now is "${topMove.title}". Score ${formatScore(topMove.total_score)} with decision ${topMove.decision || "pending"}.`
    );
  } else if (state.opportunities.length) {
    setText("heroCopy", "The engine is live, but nothing is currently above the do_now threshold.");
  } else {
    setText("heroCopy", "No opportunities are loaded yet. Trigger a scan or wait for the scheduled discovery loop.");
  }
}

function renderDiagnostics() {
  const container = document.getElementById("diagnosticsList");
  const refreshNode = document.getElementById("lastRefreshText");
  if (refreshNode) {
    refreshNode.textContent = state.lastRefreshAt
      ? `${formatDateTime(state.lastRefreshAt)} · ${state.failedPanels} panel(s) failed`
      : "Not refreshed yet.";
  }

  const items = [];
  const readiness = state.health?.readiness;
  const issues = readiness?.issues || [];
  const mode = readiness?.mode || state.health?.status || "unknown";

  if (issues.length) {
    issues.forEach((issue) => {
      items.push({
        kind: mode === "blocked" ? "blocked" : "warning",
        title: mode === "blocked" ? "Blocking issue" : "Readiness warning",
        body: issue,
      });
    });
  }

  if (state.failedPanels > 0) {
    items.push({
      kind: "warning",
      title: "Partial dashboard data",
      body: `${state.failedPanels} API panel(s) could not be loaded on the last refresh. Visible data may be incomplete.`,
    });
  }

  if (!items.length) {
    items.push({
      kind: "ok",
      title: "Readiness clear",
      body: "No blocking readiness issue is currently exposed by the backend.",
    });
  }

  container.innerHTML = items
    .map(
      (item) => `
        <article class="diagnostic-item is-${item.kind}">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="font-semibold text-mist">${escapeHtml(item.title)}</div>
              <p class="mt-2 text-sm leading-6 text-steel">${escapeHtml(item.body)}</p>
            </div>
            <span class="badge ${item.kind === "blocked" ? "badge--blocked" : item.kind === "warning" ? "badge--ask-user" : "badge--do-now"}">${escapeHtml(item.kind)}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function setStatus(mode, label) {
  const dot = document.getElementById("statusDot");
  const pill = document.getElementById("statusLabel");
  dot.className = `status-dot status-dot--${mode}`;
  pill.className = `status-pill status-pill--${mode}`;
  pill.textContent = label;
}

function renderCognitiveBar() {
  if (!state.cognitive) {
    return;
  }
  const cognitive = state.cognitive;
  setText("energyBarText", `Energy ${cognitive.energy}/10`);
  setText("stressBarText", `Stress ${cognitive.stress}/10`);
  setText("hoursBarText", `Hours ${cognitive.available_hours_this_week}h`);
  setText("examBarText", `Exam ${cognitive.exam_pressure}/10`);
  setText(
    "moodBarText",
    cognitive.mood_note || "No mood note captured for today."
  );

  syncRange("energyInput", "energyValue", cognitive.energy, " / 10");
  syncRange("stressInput", "stressValue", cognitive.stress, " / 10");
  syncRange("hoursInput", "hoursValue", cognitive.available_hours_this_week, "h");
  syncRange("examInput", "examValue", cognitive.exam_pressure, " / 10");
  const moodInput = document.getElementById("moodNoteInput");
  if (moodInput) {
    moodInput.value = cognitive.mood_note || "";
  }
  setText("checkinStatus", `Loaded current state for ${formatDate(cognitive.date)}.`);
}

function syncRange(inputId, outputId, value, suffix) {
  const input = document.getElementById(inputId);
  const output = document.getElementById(outputId);
  if (input) input.value = value;
  if (output) output.textContent = `${value}${suffix}`;
}

function renderMetricCards() {
  const queueBreakdown = summarizeDecisions(state.opportunities);
  const pendingApprovals = state.approvals.length;
  const pipelineValue = state.opportunities.reduce((sum, item) => sum + numeric(item.total_score || 0), 0) * 10000;

  setText("metricActiveOpps", number(state.opportunities.length));
  setText(
    "metricDecisionBreakdown",
    `${queueBreakdown.do_now} do_now · ${queueBreakdown.delay} delay · ${queueBreakdown.queue} queue`
  );
  setText("metricPendingApprovals", number(pendingApprovals));
  setText(
    "metricPendingHint",
    pendingApprovals > 0 ? "Human approval is now the bottleneck." : "No review pressure."
  );
  setText("metricPipelineValue", formatCurrency(pipelineValue, "THB"));
  setText("metricRevenueWeek", formatCurrency(state.currentWeek?.revenue_thb ?? 0, "THB"));
  setText(
    "metricRevenueNote",
    state.currentWeek ? `Week of ${formatDate(state.currentWeek.week_start)}` : "Waiting for current-week metrics."
  );
  setText("metricAiCost", formatCurrency(state.costs?.cost_today_usd ?? 0, "USD"));
  const costRatio = numeric(state.costs?.cost_today_usd ?? 0) / Math.max(2, 0.0001);
  setText(
    "metricAiCostNote",
    costRatio >= 0.8 ? "Approaching daily limit." : "Within budget."
  );
  setText(
    "metricDecisionAccuracy",
    `${number(state.currentWeek?.decision_accuracy_score ?? 0)}%`
  );
}

function renderOpportunityTable() {
  const tbody = document.getElementById("opportunityTableBody");
  const filtered = state.opportunities.filter((item) => {
    if (state.filter === "all") return true;
    return item.decision === state.filter;
  });

  if (!filtered.length) {
    tbody.innerHTML =
      '<tr><td colspan="7"><div class="empty-state">No opportunities match this filter.</div></td></tr>';
    return;
  }

  tbody.innerHTML = filtered
    .map(
      (item) => `
        <tr data-opportunity-id="${item.id}">
          <td>${escapeHtml(item.type || "other")}</td>
          <td>
            <div class="space-y-1">
              <div class="font-semibold text-mist">${escapeHtml(item.title || "Untitled")}</div>
              <div class="text-xs text-steel">${escapeHtml(trim(item.fit_summary || item.scoring_rationale || item.description || "", 90))}</div>
            </div>
          </td>
          <td>${formatScore(item.total_score)}</td>
          <td>${decisionBadge(item.decision || item.action_priority || "queue")}</td>
          <td>${item.decision_confidence ? `${Math.round(numeric(item.decision_confidence) * 100)}%` : "n/a"}</td>
          <td>${escapeHtml(deadlineLabel(item.deadline))}</td>
          <td>${escapeHtml(item.status || "found")}</td>
        </tr>
      `
    )
    .join("");

  tbody.querySelectorAll("tr[data-opportunity-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const item = state.opportunities.find((opp) => opp.id === row.dataset.opportunityId);
      if (item) openOpportunityDialog(item);
    });
  });
}

function renderFollowups() {
  const container = document.getElementById("followupList");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const items = state.contacts
    .filter((contact) => contact.next_followup_date && new Date(contact.next_followup_date) <= today)
    .slice(0, 8);

  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No contacts need follow-up today.</div>';
    return;
  }

  container.innerHTML = items
    .map(
      (contact) => `
        <article class="panel-list-item">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h3 class="font-semibold text-mist">${escapeHtml(contact.name)}</h3>
              <p class="mt-1 text-sm text-steel">${escapeHtml(contact.company || contact.role || "No company recorded")}</p>
              <p class="mt-2 text-xs text-steel">${escapeHtml(contact.followup_reason || "No follow-up reason recorded")}</p>
            </div>
            <span class="badge badge--delay">${escapeHtml(formatDate(contact.next_followup_date))}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function renderDrafts() {
  const container = document.getElementById("draftList");
  if (!state.drafts.length) {
    container.innerHTML = '<div class="empty-state">No drafts are waiting for approval.</div>';
    return;
  }

  container.innerHTML = state.drafts
    .slice(0, 8)
    .map(
      (draft) => `
        <article class="panel-list-item">
          <div class="space-y-3">
            <div class="flex flex-wrap items-center gap-2">
              <span class="badge badge--queue">${escapeHtml(draft.type || "draft")}</span>
              ${draft.model_used ? `<span class="badge badge--delay">${escapeHtml(draft.model_used)}</span>` : ""}
            </div>
            <div>
              <h3 class="font-semibold text-mist">${escapeHtml(draft.title || "Untitled draft")}</h3>
              <p class="mt-2 text-sm leading-6 text-steel">${escapeHtml(trim(draft.content || "", 140))}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button class="command-button command-button--primary" data-draft-action="approve" data-draft-id="${draft.id}" type="button">Approve</button>
              <button class="command-button" data-draft-action="reject" data-draft-id="${draft.id}" type="button">Reject</button>
            </div>
          </div>
        </article>
      `
    )
    .join("");

  container.querySelectorAll("[data-draft-action]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const action = button.dataset.draftAction;
      const draftId = button.dataset.draftId;
      if (action === "approve") {
        await getJson(`${API}/drafts/${draftId}/approve`, { method: "PATCH" });
      } else {
        const reason = window.prompt("Optional rejection reason:", "") || "";
        await getJson(
          `${API}/drafts/${draftId}/reject?reason=${encodeURIComponent(reason)}`,
          { method: "PATCH" }
        );
      }
      await refreshDashboard();
    });
  });
}

function renderApprovals() {
  const container = document.getElementById("approvalList");
  if (!state.approvals.length) {
    container.innerHTML = '<div class="empty-state">No pending approvals in the queue.</div>';
    return;
  }

  container.innerHTML = state.approvals
    .map(
      (approval) => `
        <article class="panel-list-item">
          <div class="space-y-3">
            <div class="flex flex-wrap items-center gap-2">
              <span class="badge badge--ask-user">${escapeHtml(approval.action_type || "approval")}</span>
              ${approval.batch_key ? `<span class="badge badge--queue">${escapeHtml(approval.batch_key)}</span>` : ""}
            </div>
            <div>
              <h3 class="font-semibold text-mist">${escapeHtml(approval.title || "Approval")}</h3>
              <p class="mt-2 text-sm leading-6 text-steel">${escapeHtml(trim(approval.preview?.content_preview || JSON.stringify(approval.details || {}), 140))}</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button class="command-button command-button--primary" data-approval-action="approve" data-approval-id="${approval.id}" type="button">Approve</button>
              <button class="command-button" data-approval-action="reject" data-approval-id="${approval.id}" type="button">Reject</button>
            </div>
          </div>
        </article>
      `
    )
    .join("");

  container.querySelectorAll("[data-approval-action]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const action = button.dataset.approvalAction;
      const approvalId = button.dataset.approvalId;
      if (action === "approve") {
        await getJson(`${API}/approvals/${approvalId}/approve`, { method: "PATCH" });
      } else {
        const note = window.prompt("Optional rejection reason:", "") || "";
        await getJson(`${API}/approvals/${approvalId}/reject?note=${encodeURIComponent(note)}`, {
          method: "PATCH",
        });
      }
      await refreshDashboard();
    });
  });
}

function renderRuns() {
  const container = document.getElementById("runList");
  if (!state.runs.length) {
    container.innerHTML = '<div class="empty-state">No runs recorded yet.</div>';
    return;
  }

  container.innerHTML = state.runs
    .map(
      (run) => `
        <article class="panel-list-item">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h3 class="font-semibold text-mist">${escapeHtml(run.name || run.task_type || "Run")}</h3>
              <p class="mt-1 text-sm text-steel">${escapeHtml(run.task_type || "unknown")} via ${escapeHtml(run.trigger_source || "unknown")}</p>
              <p class="mt-2 text-xs text-steel">${escapeHtml(run.error_message || trim(JSON.stringify(run.result || {}), 120) || "No result payload yet.")}</p>
            </div>
            <span class="badge ${run.status === "completed" ? "badge--do-now" : run.status === "failed" ? "badge--blocked" : "badge--queue"}">${escapeHtml(run.status || "queued")}</span>
          </div>
        </article>
      `
    )
    .join("");
}

function renderScrapers() {
  const container = document.getElementById("scraperList");
  if (!state.scrapers.length) {
    container.innerHTML = '<div class="empty-state">No scraper health has been recorded yet.</div>';
    return;
  }

  container.innerHTML = state.scrapers
    .map((scraper) => {
      const badgeClass = scraper.is_muted
        ? "badge--blocked"
        : scraper.consecutive_failures > 0
          ? "badge--ask-user"
          : "badge--do-now";
      const label = scraper.is_muted
        ? "muted"
        : scraper.consecutive_failures > 0
          ? "warning"
          : "healthy";
      return `
        <article class="panel-list-item">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h3 class="font-semibold text-mist">${escapeHtml(scraper.source_name)}</h3>
              <p class="mt-1 text-sm text-steel">
                Success ${number(scraper.success_rate)}% · last success ${escapeHtml(scraper.last_success_at ? formatDateTime(scraper.last_success_at) : "never")}
              </p>
              <p class="mt-2 text-xs text-steel">${escapeHtml(scraper.last_error || "No recent scraper errors.")}</p>
            </div>
            <span class="badge ${badgeClass}">${label}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderStrategy() {
  const container = document.getElementById("strategyBlock");
  const tags = document.getElementById("strategyTags");
  const fill = document.getElementById("allocationFill");
  const allocationLabel = document.getElementById("allocationLabel");

  if (!state.strategy?.strategy) {
    container.innerHTML = '<div class="empty-state">No strategy brief saved yet. Run the weekly strategy cycle or trigger it manually.</div>';
    tags.innerHTML = "";
    fill.style.width = "0%";
    allocationLabel.textContent = "0%";
    return;
  }

  const strategy = state.strategy.strategy;
  container.innerHTML = `<p>${escapeHtml(strategy).replace(/\n/g, "<br />")}</p>`;

  const doNowCount = state.doNow.length;
  const totalOpps = Math.max(state.opportunities.length, 1);
  const allocation = Math.min(Math.round((doNowCount / totalOpps) * 100), 100);
  fill.style.width = `${allocation}%`;
  allocationLabel.textContent = `${allocation}%`;

  tags.innerHTML = [
    badgeHtml("Weekly Bet", "badge--do-now"),
    badgeHtml("Kill List", "badge--blocked"),
    badgeHtml("Double Down", "badge--queue"),
  ].join("");
}

function renderCharts() {
  renderOppsChart();
  renderRevenueChart();
  renderLossChart();
}

function renderOppsChart() {
  const ctx = document.getElementById("oppsChart");
  if (!ctx) return;
  charts.opps?.destroy();
  charts.opps = new Chart(ctx, {
    type: "bar",
    data: {
      labels: state.metrics.map((metric) => shortWeek(metric.week_start)),
      datasets: [
        {
          label: "Found",
          data: state.metrics.map((metric) => numeric(metric.opps_found || 0)),
          backgroundColor: "rgba(107, 240, 199, 0.75)",
          borderRadius: 10,
        },
        {
          label: "Actioned",
          data: state.metrics.map((metric) => numeric(metric.opps_actioned || 0)),
          backgroundColor: "rgba(246, 199, 96, 0.82)",
          borderRadius: 10,
        },
      ],
    },
    options: chartOptions(),
  });
}

function renderRevenueChart() {
  const ctx = document.getElementById("revenueChart");
  if (!ctx) return;
  charts.revenue?.destroy();
  charts.revenue = new Chart(ctx, {
    type: "line",
    data: {
      labels: state.metrics.map((metric) => shortWeek(metric.week_start)),
      datasets: [
        {
          label: "Revenue",
          data: state.metrics.map((metric) => numeric(metric.revenue_thb || 0)),
          borderColor: "rgba(107, 240, 199, 1)",
          backgroundColor: "rgba(107, 240, 199, 0.14)",
          tension: 0.32,
          fill: true,
        },
        {
          label: "Target",
          data: state.metrics.map(() => 30000),
          borderColor: "rgba(255, 139, 97, 0.8)",
          borderDash: [6, 6],
          tension: 0,
        },
      ],
    },
    options: chartOptions(),
  });
}

function renderLossChart() {
  const ctx = document.getElementById("lossChart");
  if (!ctx) return;
  charts.loss?.destroy();
  charts.loss = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: state.losses.map((loss) => loss.reason),
      datasets: [
        {
          data: state.losses.map((loss) => numeric(loss.count)),
          backgroundColor: [
            "rgba(255, 139, 97, 0.9)",
            "rgba(246, 199, 96, 0.85)",
            "rgba(107, 240, 199, 0.8)",
            "rgba(127, 208, 255, 0.8)",
            "rgba(180, 145, 255, 0.8)",
          ],
        },
      ],
    },
    options: chartOptions({ legendPosition: "bottom" }),
  });
}

function chartOptions(overrides = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          color: "#e5f4ef",
          font: { family: "IBM Plex Mono", size: 11 },
        },
        position: overrides.legendPosition || "top",
      },
    },
    scales: overrides.legendPosition
      ? {}
      : {
          x: {
            ticks: { color: "#9fb5c8", font: { family: "IBM Plex Mono", size: 10 } },
            grid: { color: "rgba(159,181,200,0.08)" },
          },
          y: {
            ticks: { color: "#9fb5c8", font: { family: "IBM Plex Mono", size: 10 } },
            grid: { color: "rgba(159,181,200,0.08)" },
          },
        },
  };
}

function renderWeights() {
  const weightBars = document.getElementById("weightBars");
  const weightTimeline = document.getElementById("weightTimeline");
  const current = state.weights?.current;
  const history = state.weights?.history || [];

  if (!current?.weights) {
    weightBars.innerHTML = '<div class="empty-state">No weight history available yet.</div>';
    weightTimeline.innerHTML = "";
    return;
  }

  weightBars.innerHTML = Object.entries(current.weights)
    .map(
      ([key, value]) => `
        <div class="space-y-2">
          <div class="flex items-center justify-between gap-3 text-sm">
            <span class="text-mist">${escapeHtml(key)}</span>
            <span class="font-mono text-steel">${Math.round(numeric(value) * 100)}%</span>
          </div>
          <div class="weight-bar-track"><span style="width:${Math.round(numeric(value) * 100)}%"></span></div>
        </div>
      `
    )
    .join("");

  weightTimeline.innerHTML = history
    .map(
      (item) => `
        <article class="timeline-item ${item.is_current ? "is-current" : ""}">
          <div class="flex items-center justify-between gap-3">
            <strong class="text-mist">v${item.version}</strong>
            <span class="badge ${item.is_current ? "badge--do-now" : "badge--queue"}">${item.changed_by || "system"}</span>
          </div>
          <p class="mt-2 text-sm text-steel">${escapeHtml(item.change_reason || "No reason recorded.")}</p>
          <p class="mt-2 text-xs text-steel">${escapeHtml(item.applied_at ? formatDateTime(item.applied_at) : "unknown date")}</p>
        </article>
      `
    )
    .join("");
}

function renderAudit() {
  const container = document.getElementById("auditLogList");
  if (!state.audit.length) {
    container.innerHTML = '<div class="empty-state">No audit entries found.</div>';
    return;
  }
  container.innerHTML = state.audit
    .map(
      (entry) => `
        <article class="audit-item ${entry.was_fallback ? "is-fallback" : ""}">
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="font-semibold text-mist">${escapeHtml(entry.action)}</div>
              <p class="mt-1 text-sm text-steel">${escapeHtml(trim(JSON.stringify(entry.details || {}), 140))}</p>
              <p class="mt-2 text-xs text-steel">${escapeHtml(formatDateTime(entry.created_at))}</p>
            </div>
            ${entry.was_fallback ? '<span class="badge badge--ask-user">fallback</span>' : ""}
          </div>
        </article>
      `
    )
    .join("");
}

function openOpportunityDialog(item) {
  const title = document.getElementById("opportunityDialogTitle");
  const content = document.getElementById("opportunityDialogContent");
  title.textContent = item.title || "Opportunity";
  content.innerHTML = `
    <div class="grid gap-3 sm:grid-cols-2">
      <div class="panel-list-item">
        <div class="panel-kicker">Decision</div>
        <div class="mt-2">${decisionBadge(item.decision || item.action_priority || "queue")}</div>
      </div>
      <div class="panel-list-item">
        <div class="panel-kicker">Confidence</div>
        <div class="mt-2 text-lg font-semibold text-mist">${item.decision_confidence ? `${Math.round(numeric(item.decision_confidence) * 100)}%` : "n/a"}</div>
      </div>
    </div>
    <article class="panel-list-item">
      <div class="panel-kicker">Reasoning</div>
      <p class="mt-2 text-sm leading-7 text-steel">${escapeHtml(item.decision_reasoning || item.scoring_rationale || "No reasoning recorded.")}</p>
    </article>
    <article class="panel-list-item">
      <div class="panel-kicker">Fit Summary</div>
      <p class="mt-2 text-sm leading-7 text-steel">${escapeHtml(item.fit_summary || item.description || "No summary available.")}</p>
    </article>
    <div class="flex flex-wrap gap-3">
      <button id="dialogApproveButton" class="command-button command-button--primary" type="button">Approve</button>
      <button id="dialogSkipButton" class="command-button" type="button">Skip</button>
      ${item.source_url ? `<a class="command-button" href="${item.source_url}" target="_blank" rel="noreferrer">Open Source</a>` : ""}
    </div>
  `;
  document.getElementById("dialogApproveButton")?.addEventListener("click", async () => {
    await getJson(`${API}/opportunities/${item.id}/approve`, { method: "PATCH" });
    document.getElementById("opportunityDialog")?.close();
    await refreshDashboard();
  });
  document.getElementById("dialogSkipButton")?.addEventListener("click", async () => {
    await getJson(`${API}/opportunities/${item.id}/skip`, { method: "PATCH" });
    document.getElementById("opportunityDialog")?.close();
    await refreshDashboard();
  });
  document.getElementById("opportunityDialog")?.showModal();
}

async function submitCheckin(event) {
  event.preventDefault();
  const payload = {
    energy: numeric(document.getElementById("energyInput")?.value),
    stress: numeric(document.getElementById("stressInput")?.value),
    available_hours_this_week: numeric(document.getElementById("hoursInput")?.value),
    exam_pressure: numeric(document.getElementById("examInput")?.value),
    mood_note: document.getElementById("moodNoteInput")?.value?.trim() || null,
  };
  setText("checkinStatus", "Saving check-in...");
  try {
    state.cognitive = await getJson(`${API}/cognitive/checkin`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setText("checkinStatus", "Check-in saved. Decision engine context updated.");
    document.getElementById("stateDialog")?.close();
    renderDashboard();
  } catch (error) {
    setText("checkinStatus", `Check-in failed: ${error.message}`);
  }
}

async function rollbackWeights() {
  try {
    await getJson(`${API}/system/weights/rollback`, { method: "POST" });
    await refreshDashboard();
  } catch (error) {
    window.alert(`Rollback failed: ${error.message}`);
  }
}

function summarizeDecisions(items) {
  return items.reduce(
    (acc, item) => {
      const key = item.decision || item.action_priority || "queue";
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    },
    { do_now: 0, delay: 0, queue: 0, ask_user: 0, skip: 0 }
  );
}

function decisionBadge(decision) {
  const normalized = String(decision || "queue").toLowerCase();
  const classes = {
    do_now: "badge--do-now",
    queue: "badge--delay",
    delay: "badge--queue",
    ask_user: "badge--ask-user",
    skip: "badge--skip",
  };
  return `<span class="badge ${classes[normalized] || "badge--queue"}">${escapeHtml(normalized)}</span>`;
}

function badgeHtml(label, className) {
  return `<span class="badge ${className}">${escapeHtml(label)}</span>`;
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

function formatCurrency(value, currency) {
  if (currency === "THB") {
    return `THB ${number(value)}`;
  }
  return `$${numeric(value).toFixed(2)}`;
}

function formatScore(value) {
  return numeric(value).toFixed(2);
}

function deadlineLabel(value) {
  if (!value) return "No deadline";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(value);
  target.setHours(0, 0, 0, 0);
  const delta = Math.round((target - today) / 86400000);
  if (delta === 0) return "Today";
  if (delta > 0) return `${delta}d left`;
  return `${Math.abs(delta)}d overdue`;
}

function formatDate(value) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatDateTime(value) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortWeek(value) {
  return new Date(value).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
  });
}

function number(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(numeric(value));
}

function numeric(value) {
  return Number(value || 0);
}

function trim(value, max) {
  const text = String(value || "");
  return text.length > max ? `${text.slice(0, max).trim()}...` : text;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
