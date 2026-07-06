import { dateText, rawSubtitle, rawTitle, shortText } from "./format.js";

export function renderNodeList(container, items, selectedId, onSelect) {
  container.replaceChildren();
  if (!items.length) {
    container.append(empty("No records"));
    return;
  }
  for (const item of items) {
    const row = buttonRow(item.id === selectedId);
    row.append(title(item.title));
    row.append(meta(`${item.kind} | updated ${dateText(item.updated_at)}`));
    row.append(subtitle(item.subtitle || shortText(item.content)));
    row.onclick = () => onSelect(item.id);
    container.append(row);
  }
}

export function renderRawList(container, rows, selectedIndex, onSelect) {
  container.replaceChildren();
  if (!rows.length) {
    container.append(empty("No rows"));
    return;
  }
  rows.forEach((record, index) => {
    const row = buttonRow(index === selectedIndex);
    row.append(title(rawTitle(record)));
    row.append(subtitle(rawSubtitle(record)));
    row.onclick = () => onSelect(record, index);
    container.append(row);
  });
}

function buttonRow(selected) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = `record-row${selected ? " selected" : ""}`;
  return row;
}

function title(text) {
  const node = document.createElement("div");
  node.className = "row-title";
  node.textContent = text || "Untitled";
  return node;
}

function subtitle(text) {
  const node = document.createElement("div");
  node.className = "row-subtitle";
  node.textContent = text || "";
  return node;
}

function meta(text) {
  const node = document.createElement("div");
  node.className = "row-meta";
  node.textContent = text;
  return node;
}

function empty(text) {
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = text;
  return node;
}
