export function prettyJson(value) {
  return JSON.stringify(value ?? {}, null, 2);
}

export function dateText(value) {
  if (!value) {
    return "never";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

export function rawTitle(row) {
  if (row.id) {
    return String(row.id);
  }
  if (row.in || row.out) {
    return `${row.in || ""} -> ${row.out || ""}`;
  }
  return "record";
}

export function rawSubtitle(row) {
  if (row.name || row.description) {
    return [row.name, row.description].filter(Boolean).join(" ");
  }
  if (row.content) {
    return shortText(row.content);
  }
  return shortText(row);
}

export function shortText(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}

export function tagsText(tags) {
  return Array.isArray(tags) ? tags.join(", ") : "";
}

export function tagsArray(text) {
  return text
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}
