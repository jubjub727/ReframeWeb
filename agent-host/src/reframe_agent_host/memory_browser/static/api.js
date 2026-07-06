export async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  return parseResponse(response);
}

export async function patchJson(path, body) {
  const response = await fetch(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseResponse(response);
}

export async function deleteJson(path) {
  const response = await fetch(path, { method: "DELETE" });
  return parseResponse(response);
}

async function parseResponse(response) {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || response.statusText);
  }
  return payload;
}
