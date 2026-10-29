const list = document.getElementById("list");
const chips = document.getElementById("chips");
const empty = document.getElementById("empty");
const count = document.getElementById("count");
const clearButton = document.getElementById("clear");
const form = document.getElementById("add-form");
const input = document.getElementById("add-input");
const toast = document.getElementById("toast");
let items = [];

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) {
    location.href = "/m";
    throw new Error("Not connected");
  }
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))).detail;
    throw new Error(typeof detail === "string" ? detail : "Something went wrong");
  }
  return response.json();
}

function showError(error) {
  toast.textContent = error.message || "Couldn't reach the kitchen hub";
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3000);
}

function formatQty(item) {
  if (item.qty === null) return "";
  return item.unit ? `${item.qty} ${item.unit}` : `${item.qty}`;
}

function parseEntry(text) {
  const match = text.match(/^(\d+(?:\.\d+)?)\s+(.+)$/);
  return match ? { name: match[2], qty: Number(match[1]) } : { name: text };
}

function render() {
  list.replaceChildren(...items.map((item) => {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.className = item.checked ? "done" : "";
    button.setAttribute("aria-pressed", item.checked ? "true" : "false");
    const box = document.createElement("span");
    box.className = "box";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.name;
    const qty = document.createElement("span");
    qty.className = "qty";
    qty.textContent = formatQty(item);
    button.append(box, name, qty);
    button.addEventListener("click", () => toggle(item));
    row.append(button);
    return row;
  }));
  const remaining = items.filter((item) => !item.checked).length;
  const checked = items.length - remaining;
  count.textContent = items.length ? (remaining ? `${remaining} to get` : "All done") : "";
  empty.hidden = items.length > 0;
  clearButton.hidden = checked === 0;
  clearButton.textContent = `Clear ${checked} checked`;
}

function renderChips(names) {
  chips.replaceChildren(...names.map((name) => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.type = "button";
    chip.textContent = name;
    chip.addEventListener("click", () => add({ name }));
    return chip;
  }));
}

async function refresh() {
  try {
    const [groceries, frequent] = await Promise.all([
      api("GET", "/api/grocery?include_checked=true"),
      api("GET", "/api/grocery/frequent?limit=10"),
    ]);
    items = groceries;
    render();
    renderChips(frequent);
  } catch (error) {
    showError(error);
  }
}

async function add(entry) {
  try {
    await api("POST", "/api/grocery", [entry]);
    await refresh();
  } catch (error) {
    showError(error);
  }
}

async function toggle(item) {
  item.checked = item.checked ? 0 : 1;
  render();
  try {
    await api("POST", `/api/grocery/${item.id}/check?checked=${item.checked ? "true" : "false"}`);
  } catch (error) {
    item.checked = item.checked ? 0 : 1;
    render();
    showError(error);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  add(parseEntry(text));
});

clearButton.addEventListener("click", async () => {
  try {
    await api("POST", "/api/grocery/clear-checked");
    await refresh();
  } catch (error) {
    showError(error);
  }
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
setInterval(() => { if (!document.hidden) refresh(); }, 15000);
refresh();
