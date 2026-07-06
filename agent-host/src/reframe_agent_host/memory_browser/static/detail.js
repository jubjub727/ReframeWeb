import { dateText, prettyJson, tagsArray, tagsText } from "./format.js";

export function renderEmptyDetail(container) {
  container.replaceChildren(empty("Select a record"));
}

export function renderRawDetail(container, record) {
  container.replaceChildren();
  container.append(header(record.id || "Raw record", ""));
  container.append(jsonBlock(record));
}

export function renderNodeDetail(container, detail, onSave, onDelete) {
  const record = detail.record;
  const summary = detail.summary;
  const tagsInput = input(tagsText(record.tags));
  const contentEditor = textarea(prettyJson(record.content));
  container.replaceChildren();
  container.append(header(summary.title, summary.kind));
  container.append(metaBlock(record, summary));
  appendChildren(container, "Messages", messageRows(detail.messages));
  appendChildren(container, "Conversations", nodeRows(detail.conversations));
  appendChildren(container, "Session memories", nodeRows(detail.session_memories));
  appendRelations(container, detail.relations);
  container.append(editor(tagsInput, contentEditor, () => {
    onSave({
      id: record.id,
      tags: tagsArray(tagsInput.value),
      content: JSON.parse(contentEditor.value),
    });
  }, () => onDelete(record.id, summary.title)));
}

function header(title, meta) {
  const wrap = document.createElement("div");
  wrap.className = "detail-header";
  const text = document.createElement("div");
  const heading = document.createElement("h2");
  heading.className = "detail-title";
  heading.textContent = title || "Untitled";
  const small = document.createElement("div");
  small.className = "detail-meta";
  small.textContent = meta || "";
  text.append(heading, small);
  wrap.append(text);
  return wrap;
}

function metaBlock(record, summary) {
  const section = block("Record");
  section.append(line("Id", record.id));
  section.append(line("Roots", (summary.roots || []).join(", ") || "none"));
  section.append(line("Created", dateText(record.created_at)));
  section.append(line("Updated", dateText(record.updated_at)));
  section.append(line("Read", dateText(record.read_at)));
  return section;
}

function editor(tagsInput, contentEditor, onSave, onDelete) {
  const section = block("Edit");
  section.append(field("Tags", tagsInput));
  section.append(field("Content JSON", contentEditor));
  const actions = document.createElement("div");
  actions.className = "editor-actions";
  const save = document.createElement("button");
  save.type = "button";
  save.className = "primary";
  save.textContent = "Save";
  save.onclick = onSave;
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "danger";
  deleteButton.textContent = "Delete";
  deleteButton.onclick = onDelete;
  actions.append(save, deleteButton);
  section.append(actions);
  return section;
}

function messageRows(messages) {
  return messages.map((message) => {
    const row = document.createElement("div");
    row.className = "message-row";
    const role = document.createElement("div");
    role.className = "message-role";
    role.textContent = `${message.position ?? ""} ${message.content?.role || ""}`;
    const text = document.createElement("div");
    text.className = "message-text";
    text.textContent = message.content?.content || "";
    row.append(role, text);
    return row;
  });
}

function nodeRows(nodes) {
  return nodes.map((node) => {
    const row = document.createElement("div");
    row.className = "relation-row";
    row.textContent = `${node.id} ${prettyJson(node.content)}`;
    return row;
  });
}

function appendRelations(container, relations) {
  const rows = [];
  for (const [table, records] of Object.entries(relations || {})) {
    for (const record of records) {
      rows.push(relationRow(table, record));
    }
  }
  appendChildren(container, "Relations", rows);
}

function relationRow(table, record) {
  const row = document.createElement("div");
  row.className = "relation-row";
  row.textContent = `${table}: ${record.in || ""} -> ${record.out || ""}`;
  return row;
}

function appendChildren(container, label, children) {
  if (!children.length) {
    return;
  }
  const section = block(label);
  section.append(...children);
  container.append(section);
}

function block(label) {
  const section = document.createElement("section");
  section.className = "detail-section";
  const heading = document.createElement("h2");
  heading.textContent = label;
  section.append(heading);
  return section;
}

function field(label, control) {
  const wrap = document.createElement("label");
  wrap.className = "field";
  const text = document.createElement("span");
  text.textContent = label;
  wrap.append(text, control);
  return wrap;
}

function input(value) {
  const node = document.createElement("input");
  node.value = value;
  return node;
}

function textarea(value) {
  const node = document.createElement("textarea");
  node.spellcheck = false;
  node.value = value;
  return node;
}

function line(label, value) {
  const node = document.createElement("div");
  node.className = "detail-meta";
  node.textContent = `${label}: ${value || ""}`;
  return node;
}

function jsonBlock(record) {
  const block = document.createElement("pre");
  block.className = "json-view";
  block.textContent = prettyJson(record);
  return block;
}

function empty(text) {
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = text;
  return node;
}
