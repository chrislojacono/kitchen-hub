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

function showToast(message, ok = true) {
  toast.textContent = message;
  toast.classList.toggle("ok", ok);
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 3000);
}

function showError(error) {
  showToast(error.message || "Couldn't reach the kitchen hub", false);
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

const recipeDialog = document.getElementById("recipe");
const recipeForm = document.getElementById("recipe-form");
const recipeInput = document.getElementById("recipe-input");
const recipeError = document.getElementById("recipe-error");
const recipeReadButton = document.getElementById("recipe-read");
const recipeResult = document.getElementById("recipe-result");
const recipeTitle = document.getElementById("recipe-title");
const recipeSource = document.getElementById("recipe-source");
const recipeItems = document.getElementById("recipe-items");
const recipeAddButton = document.getElementById("recipe-add");

function showRecipeStep(result) {
  recipeForm.hidden = result;
  recipeResult.hidden = !result;
  recipeDialog.scrollTop = 0;
}

function selectedIngredients() {
  return [...recipeItems.querySelectorAll("li")]
    .filter((row) => row.querySelector("input[type=checkbox]").checked)
    .map((row) => row.querySelector(".ingredient input").value.trim())
    .filter(Boolean);
}

function updateAddButton() {
  const count = selectedIngredients().length;
  recipeAddButton.textContent = count ? `Add ${count} to list` : "Nothing selected";
  recipeAddButton.disabled = count === 0;
  recipeItems.querySelectorAll("li").forEach((row) => {
    row.classList.toggle("skipped", !row.querySelector("input[type=checkbox]").checked);
  });
}

function renderRecipe(recipe) {
  recipeTitle.textContent = recipe.title;
  recipeSource.hidden = !recipe.source;
  if (recipe.source && /^https?:\/\//.test(recipe.source)) {
    recipeSource.href = recipe.source;
    recipeSource.textContent = new URL(recipe.source).hostname.replace(/^www\./, "");
  }
  recipeItems.replaceChildren(...recipe.ingredients.map((ingredient, index) => {
    const row = document.createElement("li");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = ingredient.suggested;
    box.id = `ingredient-${index}`;
    box.addEventListener("change", updateAddButton);
    const details = document.createElement("div");
    details.className = "ingredient";
    const name = document.createElement("input");
    name.value = ingredient.name;
    name.maxLength = 80;
    name.setAttribute("aria-label", `Grocery item for: ${ingredient.line}`);
    name.addEventListener("input", updateAddButton);
    const line = document.createElement("small");
    line.textContent = ingredient.line;
    details.append(name, line);
    if (ingredient.in_pantry || ingredient.staple) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = ingredient.in_pantry ? "In pantry" : "Staple";
      details.append(tag);
    }
    row.append(box, details);
    return row;
  }));
  updateAddButton();
  showRecipeStep(true);
}

const recipeBackButton = document.getElementById("recipe-back");

document.getElementById("recipe-open").addEventListener("click", () => {
  recipeDialog.dataset.mode = "";
  recipeBackButton.textContent = "Back";
  recipeInput.value = "";
  recipeError.hidden = true;
  showRecipeStep(false);
  recipeDialog.showModal();
  recipeInput.focus();
});

recipeDialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => recipeDialog.close()));
recipeBackButton.addEventListener("click", () => {
  if (recipeDialog.dataset.mode === "meal") recipeDialog.close();
  else showRecipeStep(false);
});

recipeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = recipeInput.value.trim();
  if (!text) return;
  recipeError.hidden = true;
  recipeReadButton.disabled = true;
  recipeReadButton.textContent = "Reading...";
  try {
    renderRecipe(await api("POST", "/api/recipes/read", { link_or_text: text }));
  } catch (error) {
    recipeError.textContent = error.message;
    recipeError.hidden = false;
  } finally {
    recipeReadButton.disabled = false;
    recipeReadButton.textContent = "Read recipe";
  }
});

recipeAddButton.addEventListener("click", async () => {
  const names = selectedIngredients();
  recipeAddButton.disabled = true;
  try {
    await api("POST", "/api/grocery", names.map((name) => ({ name })));
    recipeDialog.close();
    showToast(`Added ${names.length} ${names.length === 1 ? "item" : "items"}`);
    await refresh();
  } catch (error) {
    updateAddButton();
    showError(error);
  }
});
