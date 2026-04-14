const state = {
  currentWorkspace: "dashboard",
  currentEventId: null,
  currentEventType: null,
  currentEntityId: null,
  currentScenarioId: null,
  currentThesisId: null,
  currentBoardId: null,
  currentWatchlistId: null,
  currentSearchQuery: "",
  watchlists: [],
  boards: [],
  scenarios: [],
  theses: [],
  currentWatchItem: null,
  currentBoardItem: null,
  currentNoteSubject: null,
};

const els = {
  metricList: document.getElementById("metric-list"),
  eventList: document.getElementById("event-list"),
  watchlistList: document.getElementById("watchlist-list"),
  boardList: document.getElementById("board-list"),
  scenarioList: document.getElementById("scenario-list"),
  thesisList: document.getElementById("thesis-list"),
  alertList: document.getElementById("alert-list"),
  queryList: document.getElementById("query-list"),
  searchResults: document.getElementById("search-results"),
  workspaceHeader: document.getElementById("workspace-header"),
  workspaceBody: document.getElementById("workspace-body"),
  evidencePanel: document.getElementById("evidence-panel"),
  notesPanel: document.getElementById("notes-panel"),
  copilotOutput: document.getElementById("copilot-output"),
  reportList: document.getElementById("report-list"),
  pathOutput: document.getElementById("path-output"),
  searchForm: document.getElementById("search-form"),
  searchInput: document.getElementById("search-input"),
  watchlistForm: document.getElementById("watchlist-form"),
  watchlistName: document.getElementById("watchlist-name"),
  boardForm: document.getElementById("board-form"),
  boardName: document.getElementById("board-name"),
  scenarioForm: document.getElementById("scenario-form"),
  scenarioName: document.getElementById("scenario-name"),
  scenarioAnchorType: document.getElementById("scenario-anchor-type"),
  scenarioAnchorId: document.getElementById("scenario-anchor-id"),
  scenarioDirection: document.getElementById("scenario-direction"),
  thesisForm: document.getElementById("thesis-form"),
  thesisTitle: document.getElementById("thesis-title"),
  thesisStatement: document.getElementById("thesis-statement"),
  thesisLinkType: document.getElementById("thesis-link-type"),
  thesisLinkId: document.getElementById("thesis-link-id"),
  thesisStance: document.getElementById("thesis-stance"),
  saveQueryForm: document.getElementById("save-query-form"),
  queryName: document.getElementById("query-name"),
  watchlistSelect: document.getElementById("watchlist-select"),
  boardSelect: document.getElementById("board-select"),
  contextActionsForm: document.getElementById("context-actions-form"),
  boardActionsForm: document.getElementById("board-actions-form"),
  noteForm: document.getElementById("note-form"),
  noteTitle: document.getElementById("note-title"),
  noteStance: document.getElementById("note-stance"),
  noteBody: document.getElementById("note-body"),
  copilotForm: document.getElementById("copilot-form"),
  copilotInput: document.getElementById("copilot-input"),
  reportForm: document.getElementById("report-form"),
  reportType: document.getElementById("report-type"),
  reportCompareEntity: document.getElementById("report-compare-entity"),
  pathForm: document.getElementById("path-form"),
  pathSource: document.getElementById("path-source"),
  pathTarget: document.getElementById("path-target"),
  dashboardButton: document.getElementById("dashboard-button"),
  ontologyButtons: document.querySelectorAll(".ontology-button"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `Request failed: ${response.status}`);
  }
  return response.json();
}

function signalClass(direction) {
  if (direction === "positive") return "signal signal-positive";
  if (direction === "negative") return "signal signal-negative";
  return "signal signal-neutral";
}

function fmt(value) {
  return value === null || value === undefined || value === "" ? "n/a" : value;
}

function pct(value) {
  return value === null || value === undefined ? "n/a" : Number(value).toFixed(2);
}

function createCard(html, className = "list-card") {
  const div = document.createElement("div");
  div.className = className;
  div.innerHTML = html;
  return div;
}

function emptyCard(text) {
  return createCard(`<div class="empty-state">${text}</div>`);
}

function setContext({
  workspace,
  eventId = null,
  eventType = null,
  entityId = null,
  scenarioId = null,
  thesisId = null,
  boardId = null,
  watchlistId = null,
  watchItem = null,
  boardItem = null,
  noteSubject = null,
}) {
  state.currentWorkspace = workspace;
  state.currentEventId = eventId;
  state.currentEventType = eventType;
  state.currentEntityId = entityId;
  state.currentScenarioId = scenarioId;
  state.currentThesisId = thesisId;
  state.currentBoardId = boardId;
  state.currentWatchlistId = watchlistId;
  state.currentWatchItem = watchItem;
  state.currentBoardItem = boardItem;
  state.currentNoteSubject = noteSubject;
  updateActionControls();
}

function populateSelect(select, items, idKey, labelKey, placeholder) {
  select.innerHTML = "";
  if (items.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = placeholder;
    select.appendChild(option);
    return;
  }
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item[idKey];
    option.textContent = item[labelKey];
    select.appendChild(option);
  });
}

function updateActionControls() {
  populateSelect(els.watchlistSelect, state.watchlists, "watchlist_id", "name", "No watchlists available");
  populateSelect(els.boardSelect, state.boards, "board_id", "name", "No boards available");
  const hasWatchContext = Boolean(state.currentWatchItem) && state.watchlists.length > 0;
  const hasBoardContext = Boolean(state.currentBoardItem) && state.boards.length > 0;
  els.watchlistSelect.disabled = !hasWatchContext;
  els.boardSelect.disabled = !hasBoardContext;
  document.getElementById("watch-context-button").disabled = !hasWatchContext;
  document.getElementById("board-context-button").disabled = !hasBoardContext;
}

async function refreshSidebar() {
  const [watchlists, boards, scenarios, theses, alertPayload, queries] = await Promise.all([
    api("/api/watchlists"),
    api("/api/boards"),
    api("/api/scenarios"),
    api("/api/theses"),
    api("/api/alerts?limit=20&refresh=true"),
    api("/api/queries"),
  ]);
  state.watchlists = watchlists;
  state.boards = boards;
  state.scenarios = scenarios;
  state.theses = theses;
  renderWatchlists(watchlists);
  renderBoards(boards);
  renderScenarios(scenarios);
  renderTheses(theses);
  renderAlerts(alertPayload.alerts);
  renderSavedQueries(queries);
  updateActionControls();
}

function renderWatchlists(watchlists) {
  els.watchlistList.innerHTML = "";
  if (watchlists.length === 0) {
    els.watchlistList.appendChild(emptyCard("No watchlists yet."));
    return;
  }
  watchlists.forEach((watchlist) => {
    const card = createCard(
      `<strong>${watchlist.name}</strong><div class="helper-text">${fmt(watchlist.item_count)} tracked items</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadWatchlist(watchlist.watchlist_id));
    els.watchlistList.appendChild(card);
  });
}

function renderBoards(boards) {
  els.boardList.innerHTML = "";
  if (boards.length === 0) {
    els.boardList.appendChild(emptyCard("No boards yet."));
    return;
  }
  boards.forEach((board) => {
    const card = createCard(
      `<strong>${board.name}</strong><div class="helper-text">${fmt(board.item_count)} saved items</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadBoard(board.board_id));
    els.boardList.appendChild(card);
  });
}

function renderScenarios(scenarios) {
  els.scenarioList.innerHTML = "";
  if (scenarios.length === 0) {
    els.scenarioList.appendChild(emptyCard("No scenarios yet."));
    return;
  }
  scenarios.forEach((scenario) => {
    const card = createCard(
      `<strong>${scenario.name}</strong><div class="helper-text">${fmt(scenario.assumption_count)} assumptions · ${fmt(scenario.run_count)} runs</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadScenario(scenario.scenario_id));
    els.scenarioList.appendChild(card);
  });
}

function renderTheses(theses) {
  els.thesisList.innerHTML = "";
  if (theses.length === 0) {
    els.thesisList.appendChild(emptyCard("No theses yet."));
    return;
  }
  theses.forEach((thesis) => {
    const card = createCard(
      `<strong>${thesis.title}</strong><div class="helper-text">${fmt(thesis.stance)} · confidence ${pct(thesis.confidence)}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadThesis(thesis.thesis_id));
    els.thesisList.appendChild(card);
  });
}

function renderAlerts(alerts) {
  els.alertList.innerHTML = "";
  if (alerts.length === 0) {
    els.alertList.appendChild(emptyCard("No active alerts."));
    return;
  }
  alerts.forEach((alert) => {
    const card = createCard(
      `<strong>${alert.title}</strong>
       <div class="helper-text">${alert.alert_type} · ${alert.severity}</div>
       <div>${alert.body}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => {
      const eventId = alert.event_ids_json?.[0];
      const entityId = alert.entity_ids_json?.[0];
      const scenarioId = alert.scenario_ids_json?.[0];
      const thesisId = alert.thesis_ids_json?.[0];
      if (scenarioId && String(alert.alert_type || "").startsWith("scenario_")) loadScenario(scenarioId);
      else if (thesisId && String(alert.alert_type || "").startsWith("thesis_")) loadThesis(thesisId);
      else if (eventId) loadEvent(eventId);
      else if (entityId) loadEntity(entityId);
      else if (scenarioId) loadScenario(scenarioId);
      else if (thesisId) loadThesis(thesisId);
    });
    els.alertList.appendChild(card);
  });
}

function renderSavedQueries(queries) {
  els.queryList.innerHTML = "";
  if (queries.length === 0) {
    els.queryList.appendChild(emptyCard("No saved queries yet."));
    return;
  }
  queries.forEach((query) => {
    const card = createCard(
      `<strong>${query.name}</strong><div class="helper-text">${query.query_text}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => runSavedQuery(query.query_id));
    els.queryList.appendChild(card);
  });
}

async function loadReportsPanel() {
  const reports = await api("/api/reports?limit=12");
  els.reportList.innerHTML = "";
  if (reports.length === 0) {
    els.reportList.appendChild(emptyCard("Generated reports appear here."));
    return;
  }
  reports.forEach((report) => {
    const card = createCard(
      `<strong>${report.title}</strong>
       <div class="helper-text">${report.report_type} · ${report.created_at_utc}</div>
       <div>${report.summary || "No summary available."}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadReport(report.report_id));
    els.reportList.appendChild(card);
  });
}

function renderEvidence(payload) {
  if (!payload) {
    els.evidencePanel.innerHTML = "<p>No evidence available.</p>";
    return;
  }
  const sourceDocs = payload.source_documents || [];
  const linkedEvents = payload.linked_events || [];
  const relationEvidence = payload.relationship_evidence || [];
  const observations = payload.observations || [];

  let html = "";
  if (observations.length) {
    html += `<div class="evidence-card"><strong>Observed facts</strong><ul>${observations
      .map((item) => `<li>${item}</li>`)
      .join("")}</ul></div>`;
  }
  sourceDocs.forEach((doc) => {
    html += `<div class="evidence-card">
      <strong>${doc.title || doc.article_id}</strong>
      <div class="helper-text">${doc.site_name || doc.source_url || "source"}</div>
      <div class="evidence-snippet">${doc.supporting_snippet || "No snippet retained."}</div>
      ${doc.canonical_url || doc.source_url ? `<a href="${doc.canonical_url || doc.source_url}" target="_blank" rel="noreferrer">Open source</a>` : ""}
    </div>`;
  });
  linkedEvents.forEach((item) => {
    html += `<div class="evidence-card"><strong>${item.headline || item.event_id}</strong><div class="evidence-snippet">${item.explanation || ""}</div></div>`;
  });
  relationEvidence.forEach((item) => {
    html += `<div class="evidence-card"><strong>${item.edge_id}</strong><div class="evidence-snippet">${item.evidence || "No edge evidence available."}</div></div>`;
  });
  els.evidencePanel.innerHTML = html || "<p>No evidence available.</p>";
}

function renderNotesPanel(notes) {
  els.notesPanel.innerHTML = "";
  if (!notes || notes.length === 0) {
    els.notesPanel.appendChild(emptyCard("Notes for the current context appear here."));
    return;
  }
  notes.forEach((note) => {
    els.notesPanel.appendChild(
      createCard(
        `<strong>${note.title || note.note_id}</strong>
         <div class="helper-text">${fmt(note.stance)} · ${note.updated_at_utc}</div>
         <div>${note.body}</div>`,
        "note-card"
      )
    );
  });
}

async function loadNotesForCurrentContext() {
  const subject = state.currentNoteSubject;
  if (!subject) {
    renderNotesPanel([]);
    return;
  }
  const params = new URLSearchParams();
  if (subject.subject_type && subject.subject_type !== "board") {
    params.set("subject_type", subject.subject_type);
    params.set("subject_id", subject.subject_id);
  }
  if (subject.board_id) {
    params.set("board_id", subject.board_id);
  }
  const notes = await api(`/api/notes?${params.toString()}`);
  renderNotesPanel(notes);
}

async function loadDashboard() {
  const payload = await api("/api/dashboard/overview");
  setContext({
    workspace: "dashboard",
    noteSubject: { subject_type: "dashboard", subject_id: "dashboard" },
  });

  els.metricList.innerHTML = "";
  Object.entries(payload.metrics).forEach(([key, value]) => {
    els.metricList.appendChild(
      createCard(
        `<div class="metric-label">${key.replaceAll("_", " ")}</div><strong>${fmt(value)}</strong>`,
        "metric-card"
      )
    );
  });

  els.eventList.innerHTML = "";
  payload.recent_events.forEach((event) => {
    const card = createCard(
      `<strong>${event.headline}</strong>
       <div class="helper-text">${event.event_type} · ${event.source}</div>
       <div class="pill-row">${event.top_impacts
         .slice(0, 3)
         .map((impact) => `<span class="pill">${impact.ticker} · ${impact.predicted_lag_bucket}</span>`)
         .join("")}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadEvent(event.event_id));
    els.eventList.appendChild(card);
  });

  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Dashboard</div>
    <h2 class="workspace-title">Operational event flow and non-obvious exposure signals</h2>
    <div class="workspace-subtitle">Wave 4 adds explicit scenarios and thesis tracking on top of the Wave 1-3 intelligence engine.</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>Recent Event Feed</h3>
      <div id="dashboard-events" class="table-like"></div>
    </section>
    <section>
      <h3>Top Non-Obvious Impact Candidates</h3>
      <div id="dashboard-impacts" class="table-like"></div>
    </section>
  `;

  const dashboardEvents = document.getElementById("dashboard-events");
  payload.recent_events.forEach((event) => {
    const row = createCard(
      `<strong>${event.headline}</strong>
       <div class="helper-text">${event.event_type} · ${event.published_at_utc || "unknown time"}</div>
       <div class="pill-row">${event.top_themes
         .map((theme) => `<span class="pill">${theme.theme_name}</span>`)
         .join("")}</div>`,
      "list-card clickable"
    );
    row.addEventListener("click", () => loadEvent(event.event_id));
    dashboardEvents.appendChild(row);
  });

  const dashboardImpacts = document.getElementById("dashboard-impacts");
  payload.top_non_obvious_impacts.forEach((impact) => {
    dashboardImpacts.appendChild(
      createCard(
        `<strong>${impact.ticker}</strong>
         <div class="helper-text">${impact.headline || "event context unavailable"}</div>
         <div class="pill-row">
           <span class="pill ${signalClass(impact.impact_direction)}">${impact.impact_direction}</span>
           <span class="pill">${impact.predicted_lag_bucket}</span>
           <span class="pill">score ${pct(impact.total_rank_score)}</span>
         </div>`,
        "impact-card"
      )
    );
  });

  renderEvidence(null);
  renderNotesPanel([]);
  els.copilotOutput.innerHTML = `<p>Ask for a dashboard summary or open a specific event/entity first for a scoped answer.</p>`;
  els.pathOutput.innerHTML = `<p>Use path trace to inspect a specific graph chain.</p>`;
  await loadReportsPanel();
}

async function loadEvent(eventId) {
  const [payload, analogs, backtest] = await Promise.all([
    api(`/api/events/${eventId}`),
    api(`/api/events/${eventId}/analogs`),
    api(`/api/events/${eventId}/backtest`),
  ]);
  setContext({
    workspace: "event",
    eventId,
    eventType: payload.event.event_type,
    watchItem: { item_type: "event_type", item_id: payload.event.event_type, label: payload.event.event_type },
    boardItem: { item_type: "event", item_id: eventId, title: payload.event.headline },
    noteSubject: { subject_type: "event", subject_id: eventId },
  });

  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Event Workspace</div>
    <h2 class="workspace-title">${payload.event.headline}</h2>
    <div class="workspace-subtitle">${payload.event.event_type} · ${payload.event.source} · ${payload.event.published_at_utc || "unknown time"}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>Summary</h3>
      <p>${payload.event.summary || "No summary available."}</p>
      <div class="pill-row">
        <span class="pill ${signalClass(payload.event.direction)}">${payload.event.direction}</span>
        <span class="pill">${payload.event.severity}</span>
        <span class="pill">confidence ${pct(payload.event.confidence)}</span>
      </div>
      <div class="chip-row">${(payload.event.primary_themes || []).map((theme) => `<span class="chip">${theme}</span>`).join("")}</div>
    </section>
    <section>
      <h3>Impact Candidates</h3>
      <div id="impact-table" class="table-like"></div>
    </section>
    <section>
      <h3>Historical Analogs</h3>
      <div id="analog-table" class="table-like"></div>
    </section>
    <section>
      <h3>Backtest Workspace</h3>
      <div id="backtest-table" class="table-like"></div>
    </section>
    <section>
      <h3>Propagation Paths</h3>
      <div id="path-table" class="table-like"></div>
    </section>
  `;

  const impactTable = document.getElementById("impact-table");
  payload.impact_candidates.forEach((impact) => {
    const row = createCard(
      `<div class="table-row">
         <div><strong>${impact.ticker}</strong></div>
         <div>${impact.explanation || "No explanation retained."}</div>
         <div class="${signalClass(impact.impact_direction)}">${impact.impact_direction}</div>
         <div>${impact.predicted_lag_bucket}</div>
       </div>`,
      "impact-card clickable"
    );
    row.addEventListener("click", () => loadEntity(impact.entity_id));
    impactTable.appendChild(row);
  });

  const analogTable = document.getElementById("analog-table");
  if (analogs.length === 0) analogTable.appendChild(emptyCard("No analogs available yet."));
  analogs.forEach((analog) => {
    const row = createCard(
      `<strong>${analog.headline}</strong>
       <div class="helper-text">similarity ${pct(analog.similarity_score)} · ${analog.published_at_utc || "unknown time"}</div>
       <div>${(analog.similarity_reasons || []).join(", ")}</div>`,
      "list-card clickable"
    );
    row.addEventListener("click", () => loadEvent(analog.event_id));
    analogTable.appendChild(row);
  });

  const backtestTable = document.getElementById("backtest-table");
  if (backtest.predicted_vs_realized.length === 0) backtestTable.appendChild(emptyCard("No realized reaction rows yet."));
  backtest.predicted_vs_realized.forEach((row) => {
    backtestTable.appendChild(
      createCard(
        `<div class="table-row">
           <div><strong>${row.ticker}</strong></div>
           <div>pred ${row.predicted_direction} / ${row.predicted_lag_bucket} | realized ${fmt(row.realized_lag_bucket)}</div>
           <div>${pct(row.predicted_rank_score)}</div>
           <div>${fmt(row.hit_flag)}</div>
         </div>`,
        "impact-card"
      )
    );
  });

  const pathTable = document.getElementById("path-table");
  payload.propagation_paths.forEach((path) => {
    pathTable.appendChild(
      createCard(
        `<strong>${path.target_node_id}</strong>
         <div class="path-row">${(path.path_nodes || []).map((node) => `<span class="path-node">${node}</span>`).join("")}</div>
         <div class="helper-text">hops ${path.hop_count} · score ${pct(path.path_score)}</div>`,
        "path-card"
      )
    );
  });

  renderEvidence(payload.supporting_evidence);
  await loadNotesForCurrentContext();
  await loadReportsPanel();
  els.pathSource.value = payload.themes[0]?.theme_id || "";
  els.pathTarget.value = payload.impact_candidates[0]?.entity_id || "";
}

async function loadEntity(entityId) {
  const payload = await api(`/api/entities/${entityId}`);
  setContext({
    workspace: "entity",
    entityId,
    watchItem: { item_type: "entity", item_id: entityId, label: payload.entity.label },
    boardItem: { item_type: "entity", item_id: entityId, title: payload.entity.label },
    noteSubject: { subject_type: "entity", subject_id: entityId },
  });

  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Entity Workspace</div>
    <h2 class="workspace-title">${payload.entity.label}</h2>
    <div class="workspace-subtitle">${fmt(payload.entity.node_type)} · ${fmt(payload.entity.ecosystem_role)} · ${fmt(payload.entity.segment_primary)} · ${fmt(payload.entity.country)}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section class="workspace-grid">
      <div>
        <h3>Profile</h3>
        <p>${payload.entity.description || payload.entity.notes || "No description available."}</p>
        <div class="chip-row">${(payload.entity.segment_secondary || []).map((segment) => `<span class="chip">${segment}</span>`).join("")}</div>
      </div>
      <div>
        <h3>Exposure Summary</h3>
        <div class="two-col">
          <div class="metric-card"><div class="metric-label">Linked events</div><strong>${fmt(payload.exposure_summary.event_count)}</strong></div>
          <div class="metric-card"><div class="metric-label">Avg rank score</div><strong>${fmt(payload.exposure_summary.avg_rank_score)}</strong></div>
          <div class="metric-card"><div class="metric-label">Positive exposures</div><strong>${fmt(payload.exposure_summary.positive_exposure_count)}</strong></div>
          <div class="metric-card"><div class="metric-label">Negative exposures</div><strong>${fmt(payload.exposure_summary.negative_exposure_count)}</strong></div>
        </div>
      </div>
    </section>
    <section>
      <h3>Recent Events</h3>
      <div id="entity-events" class="table-like"></div>
    </section>
    <section>
      <h3>Relationship Map</h3>
      <div class="two-col">
        <div><h4>Outgoing</h4><div id="neighbor-outgoing" class="table-like"></div></div>
        <div><h4>Incoming</h4><div id="neighbor-incoming" class="table-like"></div></div>
      </div>
    </section>
    <section>
      <h3>Effect Pathways</h3>
      <div id="entity-pathways" class="table-like"></div>
    </section>
    <section>
      <h3>History</h3>
      <div id="entity-history" class="table-like"></div>
    </section>
  `;

  const entityEvents = document.getElementById("entity-events");
  payload.recent_events.forEach((row) => {
    const card = createCard(
      `<strong>${row.headline || row.event_id}</strong>
       <div class="helper-text">${row.predicted_lag_bucket} · score ${pct(row.total_rank_score)}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadEvent(row.event_id));
    entityEvents.appendChild(card);
  });

  const neighborOutgoing = document.getElementById("neighbor-outgoing");
  payload.neighbors.outgoing.forEach((row) => {
    const card = createCard(
      `<strong>${row.other_node_label}</strong><div class="helper-text">${row.edge_type} · ${pct(row.score_hint)}</div>`,
      "neighbor-card clickable"
    );
    card.addEventListener("click", () => loadEntity(row.other_node_id));
    neighborOutgoing.appendChild(card);
  });
  const neighborIncoming = document.getElementById("neighbor-incoming");
  payload.neighbors.incoming.forEach((row) => {
    const card = createCard(
      `<strong>${row.other_node_label}</strong><div class="helper-text">${row.edge_type} · ${pct(row.score_hint)}</div>`,
      "neighbor-card clickable"
    );
    card.addEventListener("click", () => loadEntity(row.other_node_id));
    neighborIncoming.appendChild(card);
  });

  const pathways = document.getElementById("entity-pathways");
  payload.effect_pathways.forEach((row) => {
    pathways.appendChild(
      createCard(
        `<strong>${row.event_id}</strong>
         <div class="helper-text">${row.predicted_lag_bucket} · score ${pct(row.total_rank_score)}</div>
         <div>${row.explanation || "No explanation retained."}</div>`,
        "path-card"
      )
    );
  });

  if (payload.effect_pathways.length === 0) pathways.appendChild(emptyCard("No retained effect pathways."));

  const history = document.getElementById("entity-history");
  payload.history.forEach((row) => {
    history.appendChild(
      createCard(
        `<strong>${row.summary}</strong><div class="helper-text">${fmt(row.change_type)} · ${fmt(row.snapshot_at_utc)}</div>`,
        "list-card"
      )
    );
  });
  if (payload.history.length === 0) history.appendChild(emptyCard("No graph-history records yet."));

  renderEvidence(payload.evidence);
  await loadNotesForCurrentContext();
  await loadReportsPanel();
  els.pathSource.value = entityId;
  els.pathTarget.value = payload.neighbors.outgoing[0]?.other_node_id || "";
}

async function loadEntityDirectory(nodeType) {
  const rows = await api(`/api/entities?node_type=${encodeURIComponent(nodeType)}&limit=50`);
  setContext({
    workspace: "ontology",
    watchItem: { item_type: "ontology_type", item_id: nodeType, label: nodeType },
    boardItem: { item_type: "ontology_type", item_id: nodeType, title: `${nodeType} directory` },
    noteSubject: null,
  });

  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Ontology Directory</div>
    <h2 class="workspace-title">${nodeType}</h2>
    <div class="workspace-subtitle">${rows.length} nodes in the current graph</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>${nodeType} Nodes</h3>
      <div id="ontology-directory" class="table-like"></div>
    </section>
  `;
  const directory = document.getElementById("ontology-directory");
  rows.forEach((row) => {
    const card = createCard(
      `<strong>${row.label}</strong><div class="helper-text">${fmt(row.description)}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadEntity(row.node_id));
    directory.appendChild(card);
  });
  if (rows.length === 0) directory.appendChild(emptyCard(`No ${nodeType} nodes available.`));

  els.evidencePanel.innerHTML = `<p>Open a specific ${nodeType} node to inspect linked events, evidence, and graph history.</p>`;
  await loadNotesForCurrentContext();
  await loadReportsPanel();
}

async function loadScenario(scenarioId) {
  const payload = await api(`/api/scenarios/${scenarioId}`);
  const latestRun = payload.latest_run || null;
  const impactedEntities = latestRun?.impacted_entities_json || [];
  setContext({
    workspace: "scenario",
    scenarioId,
    boardItem: { item_type: "scenario", item_id: scenarioId, title: payload.scenario.name },
    noteSubject: { subject_type: "scenario", subject_id: scenarioId },
  });

  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Scenario Workspace</div>
    <h2 class="workspace-title">${payload.scenario.name}</h2>
    <div class="workspace-subtitle">${payload.scenario.summary || payload.scenario.description || "Assumption-driven scenario branch"}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>Assumptions</h3>
      <div id="scenario-assumptions" class="table-like"></div>
    </section>
    <section>
      <h3>Latest Run</h3>
      <div class="pill-row">
        <span class="pill">${payload.run_history.length} runs</span>
        <span class="pill">${payload.monitors.length} monitors</span>
        <button id="scenario-run-button" type="button">Run Scenario</button>
      </div>
      <p>${latestRun?.run_summary || "No scenario run has been saved yet."}</p>
      <div id="scenario-impacts" class="table-like"></div>
    </section>
    <section>
      <h3>Support Signals</h3>
      <div id="scenario-support" class="table-like"></div>
    </section>
    <section>
      <h3>Contradiction Signals</h3>
      <div id="scenario-contradictions" class="table-like"></div>
    </section>
  `;

  const assumptionTable = document.getElementById("scenario-assumptions");
  payload.assumptions.forEach((row) => {
    assumptionTable.appendChild(
      createCard(
        `<strong>${row.label || row.item_id_value}</strong>
         <div class="helper-text">${row.item_type} · ${row.expected_direction} · ${row.magnitude}</div>
         <div>${row.rationale || "No rationale captured."}</div>`,
        "list-card"
      )
    );
  });

  const impactTable = document.getElementById("scenario-impacts");
  if (impactedEntities.length === 0) impactTable.appendChild(emptyCard("Run the scenario to generate impacted entities."));
  impactedEntities.forEach((row) => {
    const card = createCard(
      `<strong>${row.ticker || row.label}</strong>
       <div class="helper-text">${row.direction} · hop ${fmt(row.best_hop_count)} · score ${pct(row.total_score)}</div>`,
      "list-card clickable"
    );
    if (row.entity_id) {
      card.addEventListener("click", () => loadEntity(row.entity_id));
    }
    impactTable.appendChild(card);
  });

  const supportTable = document.getElementById("scenario-support");
  if (payload.support_signals.length === 0) supportTable.appendChild(emptyCard("No supportive signals yet."));
  payload.support_signals.forEach((row) => {
    const card = createCard(
      `<strong>${row.headline || row.item_label}</strong><div class="helper-text">${row.item_label} · ${row.direction}</div>`,
      "list-card clickable"
    );
    if (row.event_id) {
      card.addEventListener("click", () => loadEvent(row.event_id));
    }
    supportTable.appendChild(card);
  });

  const contradictionTable = document.getElementById("scenario-contradictions");
  if (payload.contradiction_signals.length === 0) contradictionTable.appendChild(emptyCard("No contradiction signals yet."));
  payload.contradiction_signals.forEach((row) => {
    const card = createCard(
      `<strong>${row.headline || row.item_label}</strong><div class="helper-text">${row.item_label} · ${row.direction}</div>`,
      "list-card clickable"
    );
    if (row.event_id) {
      card.addEventListener("click", () => loadEvent(row.event_id));
    }
    contradictionTable.appendChild(card);
  });

  document.getElementById("scenario-run-button").addEventListener("click", async () => {
    await api(`/api/scenarios/${scenarioId}/run`, { method: "POST" });
    await refreshSidebar();
    await loadScenario(scenarioId);
  });

  renderEvidence({
    observations: [
      `${payload.assumptions.length} explicit assumptions`,
      `${payload.monitors.length} monitor variables`,
      latestRun?.run_summary || "No saved run summary yet.",
    ],
    linked_events: [...payload.support_signals.slice(0, 3), ...payload.contradiction_signals.slice(0, 3)],
  });
  await loadNotesForCurrentContext();
  await loadReportsPanel();
}

async function loadThesis(thesisId) {
  const payload = await api(`/api/theses/${thesisId}`);
  setContext({
    workspace: "thesis",
    thesisId,
    boardItem: { item_type: "thesis", item_id: thesisId, title: payload.thesis.title },
    noteSubject: { subject_type: "thesis", subject_id: thesisId },
  });

  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Thesis Workspace</div>
    <h2 class="workspace-title">${payload.thesis.title}</h2>
    <div class="workspace-subtitle">${payload.thesis.statement}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>Thesis State</h3>
      <div class="pill-row">
        <span class="pill ${signalClass(payload.thesis.stance)}">${payload.thesis.stance}</span>
        <span class="pill">confidence ${pct(payload.thesis.confidence)}</span>
        <span class="pill">${payload.links.length} linked items</span>
      </div>
    </section>
    <section>
      <h3>Linked Items</h3>
      <div id="thesis-links" class="table-like"></div>
    </section>
    <section>
      <h3>Support Signals</h3>
      <div id="thesis-support" class="table-like"></div>
    </section>
    <section>
      <h3>Contradiction Signals</h3>
      <div id="thesis-contradictions" class="table-like"></div>
    </section>
    <section>
      <h3>Update Log</h3>
      <div id="thesis-updates" class="table-like"></div>
    </section>
  `;

  const linkTable = document.getElementById("thesis-links");
  payload.links.forEach((row) => {
    const card = createCard(
      `<strong>${row.label || row.item_id_value}</strong><div class="helper-text">${row.item_type} · ${row.relationship}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => {
      if (row.item_type === "entity") loadEntity(row.item_id_value);
      if (row.item_type === "scenario") loadScenario(row.item_id_value);
      if (row.item_type === "event" && row.item_id_value) loadEvent(row.item_id_value);
    });
    linkTable.appendChild(card);
  });

  const supportTable = document.getElementById("thesis-support");
  if (payload.support_signals.length === 0) supportTable.appendChild(emptyCard("No supportive thesis signals yet."));
  payload.support_signals.forEach((row) => {
    const card = createCard(
      `<strong>${row.headline || row.item_label}</strong><div class="helper-text">${row.item_label} · ${row.direction}</div>`,
      "list-card clickable"
    );
    if (row.event_id) {
      card.addEventListener("click", () => loadEvent(row.event_id));
    }
    supportTable.appendChild(card);
  });

  const contradictionTable = document.getElementById("thesis-contradictions");
  if (payload.contradiction_signals.length === 0) contradictionTable.appendChild(emptyCard("No contradictory thesis signals yet."));
  payload.contradiction_signals.forEach((row) => {
    const card = createCard(
      `<strong>${row.headline || row.item_label}</strong><div class="helper-text">${row.item_label} · ${row.direction}</div>`,
      "list-card clickable"
    );
    if (row.event_id) {
      card.addEventListener("click", () => loadEvent(row.event_id));
    }
    contradictionTable.appendChild(card);
  });

  const updateTable = document.getElementById("thesis-updates");
  if (payload.updates.length === 0) updateTable.appendChild(emptyCard("No thesis updates logged yet."));
  payload.updates.forEach((row) => {
    updateTable.appendChild(
      createCard(
        `<strong>${row.created_at_utc}</strong><div class="helper-text">confidence ${fmt(row.confidence)}</div><div>${row.summary}</div>`,
        "list-card"
      )
    );
  });

  renderEvidence({
    observations: [
      payload.thesis.statement,
      `${payload.support_signals.length} supportive signals`,
      `${payload.contradiction_signals.length} contradictory signals`,
    ],
    linked_events: [...payload.support_signals.slice(0, 3), ...payload.contradiction_signals.slice(0, 3)],
  });
  await loadNotesForCurrentContext();
  await loadReportsPanel();
}

async function loadWatchlist(watchlistId) {
  const payload = await api(`/api/watchlists/${watchlistId}`);
  setContext({
    workspace: "watchlist",
    watchlistId,
    boardItem: { item_type: "watchlist", item_id: watchlistId, title: payload.watchlist.name },
    noteSubject: { subject_type: "watchlist", subject_id: watchlistId },
  });
  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Watchlist</div>
    <h2 class="workspace-title">${payload.watchlist.name}</h2>
    <div class="workspace-subtitle">${payload.watchlist.description || "Operational monitoring list"}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>Tracked Items</h3>
      <div id="watchlist-items" class="table-like"></div>
    </section>
    <section>
      <h3>Event Feed</h3>
      <div id="watchlist-feed" class="table-like"></div>
    </section>
    <section>
      <h3>Related Alerts</h3>
      <div id="watchlist-alerts" class="table-like"></div>
    </section>
  `;
  const items = document.getElementById("watchlist-items");
  if (payload.items.length === 0) items.appendChild(emptyCard("Add entities, themes, or segments from the current context."));
  payload.items.forEach((item) => {
    items.appendChild(
      createCard(
        `<strong>${item.label || item.item_id_value}</strong><div class="helper-text">${item.item_type}</div>`,
        "list-card"
      )
    );
  });
  const feed = document.getElementById("watchlist-feed");
  if (payload.event_feed.length === 0) feed.appendChild(emptyCard("No matching events yet."));
  payload.event_feed.forEach((event) => {
    const card = createCard(
      `<strong>${event.headline}</strong><div class="helper-text">${event.event_type} · ${event.published_at_utc || "unknown time"}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadEvent(event.event_id));
    feed.appendChild(card);
  });
  const alerts = document.getElementById("watchlist-alerts");
  if (payload.alerts.length === 0) alerts.appendChild(emptyCard("No alerts for this watchlist yet."));
  payload.alerts.forEach((alert) => alerts.appendChild(createCard(`<strong>${alert.title}</strong><div>${alert.body}</div>`, "list-card")));
  renderEvidence(null);
  await loadNotesForCurrentContext();
  await loadReportsPanel();
}

async function loadBoard(boardId) {
  const payload = await api(`/api/boards/${boardId}`);
  setContext({
    workspace: "board",
    boardId,
    boardItem: { item_type: "board", item_id: boardId, title: payload.board.name },
    noteSubject: { subject_type: "board", subject_id: boardId, board_id: boardId },
  });
  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Board</div>
    <h2 class="workspace-title">${payload.board.name}</h2>
    <div class="workspace-subtitle">${payload.board.description || "Saved thematic workspace"}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>Saved Items</h3>
      <div id="board-items" class="table-like"></div>
    </section>
    <section>
      <h3>Board Event Feed</h3>
      <div id="board-feed" class="table-like"></div>
    </section>
    <section>
      <h3>Board Reports</h3>
      <div id="board-reports" class="table-like"></div>
    </section>
  `;
  const items = document.getElementById("board-items");
  if (payload.items.length === 0) items.appendChild(emptyCard("Save entities, events, themes, queries, or reports into this board."));
  payload.items.forEach((item) => {
    const card = createCard(
      `<strong>${item.title || item.item_id_value || item.board_item_id}</strong><div class="helper-text">${item.item_type}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => {
      if (item.item_type === "entity" && item.item_id_value) loadEntity(item.item_id_value);
      if (item.item_type === "event" && item.item_id_value) loadEvent(item.item_id_value);
      if (item.item_type === "scenario" && item.item_id_value) loadScenario(item.item_id_value);
      if (item.item_type === "thesis" && item.item_id_value) loadThesis(item.item_id_value);
      if (item.item_type === "report" && item.item_id_value) loadReport(item.item_id_value);
    });
    items.appendChild(card);
  });
  const feed = document.getElementById("board-feed");
  if (payload.event_feed.length === 0) feed.appendChild(emptyCard("No matching events for this board yet."));
  payload.event_feed.forEach((event) => {
    const card = createCard(
      `<strong>${event.headline}</strong><div class="helper-text">${event.event_type} · ${event.published_at_utc || "unknown time"}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadEvent(event.event_id));
    feed.appendChild(card);
  });
  const reports = document.getElementById("board-reports");
  if (payload.reports.length === 0) reports.appendChild(emptyCard("No reports pinned to this board."));
  payload.reports.forEach((report) => {
    const card = createCard(
      `<strong>${report.title}</strong><div class="helper-text">${report.report_type}</div><div>${report.summary || ""}</div>`,
      "list-card clickable"
    );
    card.addEventListener("click", () => loadReport(report.report_id));
    reports.appendChild(card);
  });
  renderEvidence(null);
  renderNotesPanel(payload.notes);
  await loadReportsPanel();
}

async function loadReport(reportId) {
  const report = await api(`/api/reports/${reportId}`);
  setContext({
    workspace: "report",
    boardItem: { item_type: "report", item_id: reportId, title: report.title },
    noteSubject: { subject_type: "report", subject_id: reportId },
  });
  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Report</div>
    <h2 class="workspace-title">${report.title}</h2>
    <div class="workspace-subtitle">${report.report_type} · ${report.created_at_utc}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section>
      <h3>Summary</h3>
      <p>${report.summary || "No summary available."}</p>
    </section>
    <section>
      <h3>Markdown Export</h3>
      <pre id="report-markdown"></pre>
    </section>
  `;
  document.getElementById("report-markdown").textContent = report.markdown;
  renderEvidence({ source_documents: report.citations_json || [] });
  await loadNotesForCurrentContext();
  await loadReportsPanel();
}

async function runSearch(query) {
  state.currentSearchQuery = query;
  const payload = await api(`/api/search?q=${encodeURIComponent(query)}`);
  els.searchResults.innerHTML = "";
  ["entities", "events", "themes", "documents"].forEach((groupKey) => {
    const items = payload[groupKey];
    const group = createCard(`<strong>${groupKey}</strong>`, "search-group");
    if (items.length === 0) {
      group.innerHTML += `<div class="helper-text">No matches.</div>`;
    } else {
      items.forEach((item) => {
        const row = createCard(
          `<strong>${item.title}</strong><div class="helper-text">${item.subtitle || item.type}</div>`,
          "list-card clickable"
        );
        row.addEventListener("click", () => {
          if (item.type === "event") loadEvent(item.id);
          else if (item.type === "entity" || item.type === "theme") loadEntity(item.id);
          else if (item.url) window.open(item.url, "_blank", "noopener");
        });
        group.appendChild(row);
      });
    }
    els.searchResults.appendChild(group);
  });
}

async function runSavedQuery(queryId) {
  const payload = await api(`/api/queries/${queryId}/run`);
  state.currentSearchQuery = payload.saved_query.query_text;
  els.searchInput.value = payload.saved_query.query_text;
  els.searchResults.innerHTML = "";
  Object.entries(payload.results).forEach(([groupKey, items]) => {
    const group = createCard(`<strong>${groupKey}</strong>`, "search-group");
    items.forEach((item) => {
      const row = createCard(
        `<strong>${item.title}</strong><div class="helper-text">${item.subtitle || item.type}</div>`,
        "list-card clickable"
      );
      row.addEventListener("click", () => {
        if (item.type === "event") loadEvent(item.id);
        else if (item.type === "entity" || item.type === "theme") loadEntity(item.id);
      });
      group.appendChild(row);
    });
    els.searchResults.appendChild(group);
  });
}

async function runCopilot() {
  const query = els.copilotInput.value.trim();
  if (!query) return;
  const payload = await api("/api/copilot/query", {
    method: "POST",
    body: JSON.stringify({
      query,
      event_id: state.currentEventId,
      entity_id: state.currentEntityId,
      scenario_id: state.currentScenarioId,
      thesis_id: state.currentThesisId,
    }),
  });
  const citations = payload.citations || [];
  els.copilotOutput.innerHTML = `
    <div class="copilot-card">
      <strong>Answer</strong>
      <p>${payload.answer}</p>
      <strong>Observations</strong>
      <ul>${payload.observations.map((item) => `<li>${item}</li>`).join("")}</ul>
      <strong>Inferences</strong>
      <ul>${payload.inferences.map((item) => `<li>${item}</li>`).join("")}</ul>
      <strong>Citations</strong>
      <ul>${citations.map((item) => `<li>${item.title || item.article_id || item.id || "Reference"}</li>`).join("")}</ul>
    </div>
  `;
}

async function runPathTrace() {
  const sourceId = els.pathSource.value.trim();
  const targetId = els.pathTarget.value.trim();
  if (!sourceId || !targetId) return;
  const payload = await api("/api/graph/path-trace", {
    method: "POST",
    body: JSON.stringify({
      source_id: sourceId,
      target_id: targetId,
      max_hops: 4,
      max_paths: 5,
    }),
  });
  els.pathOutput.innerHTML = "";
  if (payload.paths.length === 0) {
    els.pathOutput.innerHTML = "<p>No path found with the current constraints.</p>";
    return;
  }
  payload.paths.forEach((path) => {
    els.pathOutput.appendChild(
      createCard(
        `<strong>${payload.source_label} -> ${payload.target_label}</strong>
         <div class="path-row">${path.path_labels.map((label) => `<span class="path-node">${label}</span>`).join("")}</div>
         <div class="helper-text">hops ${path.hop_count} · score ${pct(path.score)}</div>`,
        "path-card"
      )
    );
  });
}

async function createWatchlist() {
  const name = els.watchlistName.value.trim();
  if (!name) return;
  const payload = await api("/api/watchlists", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  els.watchlistName.value = "";
  await refreshSidebar();
  await loadWatchlist(payload.watchlist.watchlist_id);
}

async function createBoard() {
  const name = els.boardName.value.trim();
  if (!name) return;
  const payload = await api("/api/boards", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  els.boardName.value = "";
  await refreshSidebar();
  await loadBoard(payload.board.board_id);
}

async function createScenario() {
  const name = els.scenarioName.value.trim();
  const itemType = els.scenarioAnchorType.value;
  const itemId = els.scenarioAnchorId.value.trim();
  const direction = els.scenarioDirection.value;
  if (!name || !itemId) return;
  const payload = await api("/api/scenarios", {
    method: "POST",
    body: JSON.stringify({
      name,
      assumptions: [
        {
          item_type: itemType,
          item_id: itemId,
          direction,
        },
      ],
    }),
  });
  els.scenarioName.value = "";
  els.scenarioAnchorId.value = "";
  await refreshSidebar();
  await loadScenario(payload.scenario.scenario_id);
}

async function createThesis() {
  const title = els.thesisTitle.value.trim();
  const statement = els.thesisStatement.value.trim();
  const itemType = els.thesisLinkType.value;
  const itemId = els.thesisLinkId.value.trim();
  const stance = els.thesisStance.value;
  if (!title || !statement) return;
  const links = itemId
    ? [
        {
          item_type: itemType,
          item_id: itemId,
        },
      ]
    : [];
  const payload = await api("/api/theses", {
    method: "POST",
    body: JSON.stringify({
      title,
      statement,
      stance,
      links,
      initial_update: "Initial thesis created from the terminal workspace.",
    }),
  });
  els.thesisTitle.value = "";
  els.thesisStatement.value = "";
  els.thesisLinkId.value = "";
  await refreshSidebar();
  await loadThesis(payload.thesis.thesis_id);
}

async function saveCurrentSearch() {
  const name = els.queryName.value.trim();
  if (!name || !state.currentSearchQuery) return;
  await api("/api/queries", {
    method: "POST",
    body: JSON.stringify({
      name,
      query_text: state.currentSearchQuery,
    }),
  });
  els.queryName.value = "";
  await refreshSidebar();
}

async function addCurrentContextToWatchlist() {
  if (!state.currentWatchItem || !els.watchlistSelect.value) return;
  await api(`/api/watchlists/${els.watchlistSelect.value}/items`, {
    method: "POST",
    body: JSON.stringify({
      item_type: state.currentWatchItem.item_type,
      item_id: state.currentWatchItem.item_id,
      label: state.currentWatchItem.label || null,
    }),
  });
  await refreshSidebar();
  if (state.currentWatchlistId) await loadWatchlist(state.currentWatchlistId);
}

async function saveCurrentContextToBoard() {
  if (!state.currentBoardItem || !els.boardSelect.value) return;
  await api(`/api/boards/${els.boardSelect.value}/items`, {
    method: "POST",
    body: JSON.stringify({
      item_type: state.currentBoardItem.item_type,
      item_id: state.currentBoardItem.item_id,
      title: state.currentBoardItem.title || null,
      content: state.currentBoardItem.content || null,
    }),
  });
  await refreshSidebar();
  if (state.currentBoardId) await loadBoard(state.currentBoardId);
}

async function saveNote() {
  const subject = state.currentNoteSubject;
  const body = els.noteBody.value.trim();
  if (!subject || !body) return;
  await api("/api/notes", {
    method: "POST",
    body: JSON.stringify({
      subject_type: subject.subject_type,
      subject_id: subject.subject_id,
      board_id: subject.board_id || null,
      title: els.noteTitle.value.trim() || null,
      body,
      stance: els.noteStance.value || null,
    }),
  });
  els.noteTitle.value = "";
  els.noteBody.value = "";
  els.noteStance.value = "";
  await refreshSidebar();
  await loadNotesForCurrentContext();
}

async function generateReport() {
  const reportType = els.reportType.value;
  const payload = { report_type: reportType };
  if (reportType === "event_impact_brief" && state.currentEventId) {
    payload.event_id = state.currentEventId;
  }
  if (reportType === "weekly_thematic_brief") {
    if (state.currentBoardId) payload.board_id = state.currentBoardId;
    if (state.currentSearchQuery) payload.query = state.currentSearchQuery;
  }
  if (reportType === "entity_comparison_brief" && state.currentEntityId) {
    payload.entity_id = state.currentEntityId;
    if (els.reportCompareEntity.value.trim()) {
      payload.compare_entity_id = els.reportCompareEntity.value.trim();
    } else {
      return;
    }
  }
  if (reportType === "scenario_memo" && state.currentScenarioId) {
    payload.scenario_id = state.currentScenarioId;
  }
  if (reportType === "thesis_change_report" && state.currentThesisId) {
    payload.thesis_id = state.currentThesisId;
  }
  const report = await api("/api/reports/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (state.currentBoardId) {
    await api(`/api/boards/${state.currentBoardId}/items`, {
      method: "POST",
      body: JSON.stringify({
        item_type: "report",
        item_id: report.report_id,
        title: report.title,
        content: report.summary || null,
      }),
    });
  }
  await refreshSidebar();
  await loadReportsPanel();
  await loadReport(report.report_id);
}

els.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = els.searchInput.value.trim();
  if (query) await runSearch(query);
});

els.watchlistForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await createWatchlist();
});

els.boardForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await createBoard();
});

els.scenarioForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await createScenario();
});

els.thesisForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await createThesis();
});

els.saveQueryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveCurrentSearch();
});

els.contextActionsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await addCurrentContextToWatchlist();
});

els.boardActionsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveCurrentContextToBoard();
});

els.noteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveNote();
});

els.copilotForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runCopilot();
});

els.reportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await generateReport();
});

els.pathForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runPathTrace();
});

els.dashboardButton.addEventListener("click", async () => {
  await loadDashboard();
});

els.ontologyButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const nodeType = button.dataset.nodeType;
    if (nodeType) await loadEntityDirectory(nodeType);
  });
});

async function bootstrap() {
  await refreshSidebar();
  await loadDashboard();
}

bootstrap().catch((error) => {
  els.workspaceHeader.innerHTML = `<div class="eyebrow">Error</div><h2 class="workspace-title">Wave 5 terminal failed to load</h2>`;
  els.workspaceBody.innerHTML = `<section><p>${error.message}</p></section>`;
});
