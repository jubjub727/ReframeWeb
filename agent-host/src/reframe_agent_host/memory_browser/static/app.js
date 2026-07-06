import { deleteJson, getJson, patchJson } from "./api.js";
import { renderOverview, renderTables, renderTabs, updateTabs } from "./chrome.js";
import { renderNodeDetail, renderRawDetail, renderEmptyDetail } from "./detail.js";
import { renderNodeList, renderRawList } from "./list.js";

const state = {
  view: "sessions",
  table: "memory_node",
  query: "",
  limit: 100,
  selectedId: "",
  selectedRawIndex: -1,
  rawRows: [],
};

const tabs = document.querySelector("#viewTabs");
const overview = document.querySelector("#overview");
const tableSelect = document.querySelector("#tableSelect");
const searchInput = document.querySelector("#searchInput");
const limitSelect = document.querySelector("#limitSelect");
const recordList = document.querySelector("#recordList");
const detailPane = document.querySelector("#detailPane");
const status = document.querySelector("#status");
const toast = document.querySelector("#toast");

document.querySelector("#refreshButton").onclick = () => refresh();
searchInput.oninput = () => {
  state.query = searchInput.value;
  refreshList();
};
limitSelect.onchange = () => {
  state.limit = Number(limitSelect.value);
  refreshList();
};
tableSelect.onchange = () => {
  state.table = tableSelect.value;
  state.view = "raw";
  state.selectedRawIndex = -1;
  refresh();
};

init();

async function init() {
  try {
    const config = await getJson("/api/config");
    renderTabs(tabs, config.views, state.view, selectView);
    renderTables(tableSelect, config.tables, state.table);
    await refresh();
  } catch (error) {
    showError(error);
  }
}

async function refresh() {
  await Promise.all([refreshOverview(), refreshList()]);
}

async function refreshOverview() {
  const data = await getJson("/api/overview");
  renderOverview(overview, data);
}

async function refreshList() {
  setStatus("Loading");
  try {
    if (state.view === "raw") {
      await refreshRawList();
    } else {
      await refreshNodeList();
    }
    setStatus("Ready");
  } catch (error) {
    setStatus("Error");
    showError(error);
  }
}

async function refreshNodeList() {
  const params = new URLSearchParams({
    view: state.view,
    q: state.query,
    limit: String(state.limit),
  });
  const data = await getJson(`/api/nodes?${params}`);
  renderNodeList(recordList, data.items, state.selectedId, selectNode);
  if (!state.selectedId) {
    renderEmptyDetail(detailPane);
  }
}

async function refreshRawList() {
  const params = new URLSearchParams({
    name: state.table,
    limit: String(state.limit),
  });
  const data = await getJson(`/api/table?${params}`);
  const needle = state.query.trim().toLowerCase();
  state.rawRows = needle
    ? data.rows.filter((row) => JSON.stringify(row).toLowerCase().includes(needle))
    : data.rows;
  renderRawList(recordList, state.rawRows, state.selectedRawIndex, selectRaw);
  if (state.selectedRawIndex < 0) {
    renderEmptyDetail(detailPane);
  }
}

async function selectNode(id) {
  state.selectedId = id;
  state.selectedRawIndex = -1;
  const params = new URLSearchParams({ id });
  const detail = await getJson(`/api/node?${params}`);
  renderNodeDetail(detailPane, detail, saveNode, deleteNode);
  await refreshList();
}

async function selectRaw(record, index) {
  state.selectedRawIndex = index;
  state.selectedId = record.id || "";
  if (state.table === "memory_node" && record.id) {
    await selectNode(record.id);
    return;
  }
  renderRawDetail(detailPane, record);
  renderRawList(recordList, state.rawRows, state.selectedRawIndex, selectRaw);
}

async function saveNode(payload) {
  try {
    await patchJson("/api/node", payload);
    showToast("Saved");
    state.selectedId = payload.id;
    await refreshOverview();
    await selectNode(payload.id);
  } catch (error) {
    showError(error);
  }
}

async function deleteNode(id, title) {
  const label = title || id;
  const ok = window.confirm(
    `Delete ${label}?\n\nThis removes the memory node and its relation edges. It does not cascade into child records.`
  );
  if (!ok) {
    return;
  }
  try {
    const params = new URLSearchParams({ id });
    await deleteJson(`/api/node?${params}`);
    showToast("Deleted");
    state.selectedId = "";
    state.selectedRawIndex = -1;
    renderEmptyDetail(detailPane);
    await refresh();
  } catch (error) {
    showError(error);
  }
}

function selectView(view) {
  state.view = view;
  state.selectedId = "";
  state.selectedRawIndex = -1;
  updateTabs(tabs, state.view);
  refresh();
}

function setStatus(text) {
  status.textContent = text;
}

function showError(error) {
  showToast(error.message || String(error));
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => {
    toast.hidden = true;
  }, 3000);
}
