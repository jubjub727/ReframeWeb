export function renderTabs(container, views, activeView, onSelect) {
  container.replaceChildren();
  for (const view of views) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = view.label;
    button.dataset.view = view.key;
    button.onclick = () => onSelect(view.key);
    container.append(button);
  }
  updateTabs(container, activeView);
}

export function updateTabs(container, activeView) {
  for (const button of container.querySelectorAll("button")) {
    button.classList.toggle("tab-active", button.dataset.view === activeView);
  }
}

export function renderTables(select, tables, activeTable) {
  select.replaceChildren();
  for (const table of tables) {
    const option = document.createElement("option");
    option.value = table;
    option.textContent = table;
    select.append(option);
  }
  select.value = activeTable;
}

export function renderOverview(container, data) {
  container.replaceChildren();
  container.append(countRow("All nodes", data.total_nodes));
  for (const root of data.roots) {
    container.append(countRow(root.name, root.count));
  }
}

function countRow(label, count) {
  const row = document.createElement("div");
  row.className = "count-row";
  const name = document.createElement("span");
  name.textContent = label;
  const value = document.createElement("strong");
  value.textContent = count;
  row.append(name, value);
  return row;
}
