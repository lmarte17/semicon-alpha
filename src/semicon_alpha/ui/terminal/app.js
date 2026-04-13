const state = {
  currentEventId: null,
  currentEntityId: null,
  currentWorkspace: "dashboard",
};

const els = {
  metricList: document.getElementById("metric-list"),
  eventList: document.getElementById("event-list"),
  searchResults: document.getElementById("search-results"),
  workspaceHeader: document.getElementById("workspace-header"),
  workspaceBody: document.getElementById("workspace-body"),
  evidencePanel: document.getElementById("evidence-panel"),
  copilotOutput: document.getElementById("copilot-output"),
  pathOutput: document.getElementById("path-output"),
  searchForm: document.getElementById("search-form"),
  searchInput: document.getElementById("search-input"),
  copilotForm: document.getElementById("copilot-form"),
  copilotInput: document.getElementById("copilot-input"),
  pathForm: document.getElementById("path-form"),
  pathSource: document.getElementById("path-source"),
  pathTarget: document.getElementById("path-target"),
  dashboardButton: document.getElementById("dashboard-button"),
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

async function loadDashboard() {
  const payload = await api("/api/dashboard/overview");
  state.currentWorkspace = "dashboard";
  state.currentEventId = null;
  state.currentEntityId = null;

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
    <h2 class="workspace-title">Recent event flow and hidden impact candidates</h2>
    <div class="workspace-subtitle">Use the left rail to open events or search across the world model.</div>
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
    const row = createCard(
      `<strong>${impact.ticker}</strong>
       <div class="helper-text">${impact.headline || "event context unavailable"}</div>
       <div class="pill-row">
         <span class="pill ${signalClass(impact.impact_direction)}">${impact.impact_direction}</span>
         <span class="pill">${impact.predicted_lag_bucket}</span>
         <span class="pill">score ${pct(impact.total_rank_score)}</span>
       </div>`,
      "impact-card"
    );
    dashboardImpacts.appendChild(row);
  });

  els.evidencePanel.innerHTML = `<p>Select an event or entity to inspect source evidence and reasoning traces.</p>`;
  els.copilotOutput.innerHTML = `<p>Ask for a dashboard summary or open a specific event/entity first for a scoped answer.</p>`;
  els.pathOutput.innerHTML = `<p>Use path trace to inspect a specific graph chain.</p>`;
}

async function loadEvent(eventId) {
  const payload = await api(`/api/events/${eventId}`);
  state.currentWorkspace = "event";
  state.currentEventId = eventId;
  state.currentEntityId = null;

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
      <div class="chip-row">${(payload.event.primary_themes || [])
        .map((theme) => `<span class="chip">${theme}</span>`)
        .join("")}</div>
    </section>
    <section>
      <h3>Impact Candidates</h3>
      <div class="table-like" id="impact-table"></div>
    </section>
    <section>
      <h3>Propagation Paths</h3>
      <div class="table-like" id="path-table"></div>
    </section>
    <section>
      <h3>Historical Analogs</h3>
      <div class="table-like" id="analog-table"></div>
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

  const pathTable = document.getElementById("path-table");
  payload.propagation_paths.forEach((path) => {
    const row = createCard(
      `<strong>${path.target_node_id}</strong>
       <div class="path-row">${(path.path_nodes || [])
         .map((node) => `<span class="path-node">${node}</span>`)
         .join("")}</div>
       <div class="helper-text">hops ${path.hop_count} · score ${pct(path.path_score)}</div>`,
      "path-card"
    );
    pathTable.appendChild(row);
  });

  const analogTable = document.getElementById("analog-table");
  if (payload.historical_analogs.length === 0) {
    analogTable.appendChild(createCard(`<div class="helper-text">No historical analogs available yet.</div>`));
  } else {
    payload.historical_analogs.forEach((analog) => {
      const row = createCard(
        `<strong>${analog.headline}</strong><div class="helper-text">${analog.published_at_utc || "unknown time"}</div>`,
        "list-card clickable"
      );
      row.addEventListener("click", () => loadEvent(analog.event_id));
      analogTable.appendChild(row);
    });
  }

  renderEvidence(payload.supporting_evidence);
  els.pathSource.value = payload.themes[0]?.theme_id || "";
  els.pathTarget.value = payload.impact_candidates[0]?.entity_id || "";
}

async function loadEntity(entityId) {
  const payload = await api(`/api/entities/${entityId}`);
  state.currentWorkspace = "entity";
  state.currentEventId = null;
  state.currentEntityId = entityId;

  els.workspaceHeader.innerHTML = `
    <div class="eyebrow">Entity Workspace</div>
    <h2 class="workspace-title">${payload.entity.label}</h2>
    <div class="workspace-subtitle">${fmt(payload.entity.ecosystem_role)} · ${fmt(payload.entity.segment_primary)} · ${fmt(payload.entity.country)}</div>
  `;
  els.workspaceBody.innerHTML = `
    <section class="workspace-grid">
      <div>
        <h3>Profile</h3>
        <p>${payload.entity.description || payload.entity.notes || "No description available."}</p>
        <div class="chip-row">${(payload.entity.segment_secondary || [])
          .map((segment) => `<span class="chip">${segment}</span>`)
          .join("")}</div>
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

  renderEvidence(payload.evidence);
  els.pathSource.value = entityId;
  els.pathTarget.value = payload.neighbors.outgoing[0]?.other_node_id || "";
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

async function runSearch(query) {
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

async function runCopilot() {
  const query = els.copilotInput.value.trim();
  if (!query) return;
  const payload = await api("/api/copilot/query", {
    method: "POST",
    body: JSON.stringify({
      query,
      event_id: state.currentEventId,
      entity_id: state.currentEntityId,
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
      <ul>${citations
        .map((item) => `<li>${item.title || item.article_id || item.id || "Reference"}</li>`)
        .join("")}</ul>
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
         <div class="path-row">${path.path_labels
           .map((label) => `<span class="path-node">${label}</span>`)
           .join("")}</div>
         <div class="helper-text">hops ${path.hop_count} · score ${pct(path.score)}</div>`,
        "path-card"
      )
    );
  });
}

els.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = els.searchInput.value.trim();
  if (query) await runSearch(query);
});

els.copilotForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runCopilot();
});

els.pathForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runPathTrace();
});

els.dashboardButton.addEventListener("click", async () => {
  await loadDashboard();
});

loadDashboard().catch((error) => {
  els.workspaceHeader.innerHTML = `<div class="eyebrow">Error</div><h2 class="workspace-title">Wave 1 terminal failed to load</h2>`;
  els.workspaceBody.innerHTML = `<section><p>${error.message}</p></section>`;
});
