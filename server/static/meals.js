const views = { groceries: document.getElementById("view-groceries"), meals: document.getElementById("view-meals") };
const tabButtons = document.querySelectorAll(".tabs button");
const daysList = document.getElementById("days");
const weekLabel = document.getElementById("week-label");
const mealDialog = document.getElementById("meal");
const mealForm = document.getElementById("meal-form");
const mealHeading = document.getElementById("meal-heading");
const mealTitle = document.getElementById("meal-title");
const mealTakeout = document.getElementById("meal-takeout");
const mealCooks = document.getElementById("meal-cooks");
const mealCookField = document.getElementById("meal-cook-field");
const mealNotes = document.getElementById("meal-notes");
const mealNotesLabel = document.getElementById("meal-notes-label");
const mealRecipeSummary = document.getElementById("meal-recipe-summary");
const mealRecipeText = document.getElementById("meal-recipe-text");
const mealRecipeEntry = document.getElementById("meal-recipe-entry");
const mealRecipeInput = document.getElementById("meal-recipe-input");
const mealRecipeRead = document.getElementById("meal-recipe-read");
const mealIngredients = document.getElementById("meal-ingredients");
const mealDay = document.getElementById("meal-day");
const mealError = document.getElementById("meal-error");
const mealDelete = document.getElementById("meal-delete");
const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
let cooks = [];
let weekOffset = 0;
let meals = {};
let editing = null;

function isoDate(day) {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}

function addDays(day, count) {
  const next = new Date(day);
  next.setDate(next.getDate() + count);
  return next;
}

function weekStart(offset) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return addDays(today, -((today.getDay() + 6) % 7) + offset * 7);
}

function shortDate(day) {
  return day.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function longDate(key, options) {
  return new Date(`${key}T12:00`).toLocaleDateString(undefined, options);
}

function weekTitle(offset) {
  const names = { "-1": "Last week", "0": "This week", "1": "Next week" };
  const start = weekStart(offset);
  return names[offset] || `${shortDate(start)} - ${shortDate(addDays(start, 6))}`;
}

function badge(text, className) {
  const element = document.createElement("span");
  element.className = `badge ${className}`;
  element.textContent = text;
  return element;
}

function recipeLines(meal) {
  const recipe = meal && meal.recipe;
  return recipe ? (recipe.lines || recipe.ingredients || []) : [];
}

function hostname(url) {
  return /^https?:\/\//.test(url || "") ? new URL(url).hostname.replace(/^www\./, "") : "";
}

function showView(name) {
  Object.entries(views).forEach(([key, view]) => { view.hidden = key !== name; });
  tabButtons.forEach((button) => {
    if (button.dataset.view === name) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  history.replaceState(null, "", name === "meals" ? "#dinners" : location.pathname);
  if (name === "meals") loadMeals();
}

async function loadMeals() {
  try {
    const start = weekStart(weekOffset);
    const list = await api("GET", `/api/meals?start=${isoDate(addDays(start, -7))}&days=28`);
    meals = Object.fromEntries(list.filter((meal) => meal.slot === "dinner").map((meal) => [meal.date, meal]));
    renderWeek();
  } catch (error) {
    showError(error);
  }
}

function renderWeek() {
  const start = weekStart(weekOffset);
  const today = isoDate(new Date());
  weekLabel.textContent = weekTitle(weekOffset);
  daysList.replaceChildren(...Array.from({ length: 7 }, (_, index) => {
    const day = addDays(start, index);
    const key = isoDate(day);
    const meal = meals[key];
    const card = document.createElement("button");
    card.type = "button";
    card.className = `day${key === today ? " today" : ""}`;
    const dateBox = document.createElement("span");
    dateBox.className = "day-date";
    const dayName = document.createElement("b");
    dayName.textContent = key === today ? "Today" : DAY_NAMES[day.getDay()];
    dateBox.append(dayName, shortDate(day));
    const body = document.createElement("span");
    body.className = "day-body";
    if (meal) {
      const title = document.createElement("span");
      title.className = "day-title";
      title.textContent = meal.title;
      const badges = document.createElement("span");
      badges.className = "badges";
      if (meal.takeout && meal.title !== "Take-Out!") badges.append(badge("Take-Out!", "takeout"));
      if (meal.takeout && meal.title === "Take-Out!") title.classList.add("takeout-title");
      if (meal.cook && !meal.takeout) badges.append(badge(meal.cook, `cook-${Math.max(0, cooks.indexOf(meal.cook)) % 3}`));
      if (recipeLines(meal).length) badges.append(badge(`${recipeLines(meal).length} ingredients`, ""));
      body.append(title);
      if (meal.notes) {
        const notes = document.createElement("span");
        notes.className = "day-notes";
        notes.textContent = meal.notes;
        body.append(notes);
      }
      if (badges.childElementCount) body.append(badges);
    } else {
      const empty = document.createElement("span");
      empty.className = "day-empty";
      empty.textContent = "+ Plan dinner";
      body.append(empty);
    }
    card.append(dateBox, body);
    card.addEventListener("click", () => openMeal(key));
    const row = document.createElement("li");
    row.append(card);
    return row;
  }));
}

function setPressed(button, pressed) {
  button.setAttribute("aria-pressed", pressed ? "true" : "false");
}

function renderCookButtons(selected) {
  mealCooks.replaceChildren(...[...cooks, null].map((cook) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = cook || "Nobody";
    button.dataset.cook = cook || "";
    setPressed(button, cook === selected);
    button.addEventListener("click", () => {
      mealCooks.querySelectorAll("button").forEach((other) => setPressed(other, other === button));
    });
    return button;
  }));
}

function renderTakeout() {
  const takeout = mealTakeout.getAttribute("aria-pressed") === "true";
  mealCookField.hidden = takeout;
  mealNotesLabel.textContent = takeout ? "Where from?" : "Notes";
  mealNotes.placeholder = takeout ? "Options, e.g. Thai Basil or pizza from Lou's" : "Optional, e.g. double the sauce";
}

function renderMealRecipe() {
  const lines = recipeLines(editing);
  mealRecipeSummary.hidden = lines.length === 0;
  mealRecipeEntry.hidden = lines.length > 0;
  mealIngredients.hidden = lines.length === 0 || !editing.originalDate;
  if (lines.length) {
    const source = hostname(editing.recipe.source);
    mealRecipeText.textContent = `${lines.length} ingredients${source ? ` from ${source}` : ""}`;
  }
}

function renderDayOptions(selected) {
  const start = weekStart(weekOffset);
  mealDay.replaceChildren(...Array.from({ length: 21 }, (_, index) => {
    const key = isoDate(addDays(start, index - 7));
    const option = document.createElement("option");
    option.value = key;
    const label = longDate(key, { weekday: "long", month: "short", day: "numeric" });
    const other = meals[key];
    option.textContent = other && key !== selected ? `${label} (swap with ${other.title})` : label;
    option.selected = key === selected;
    return option;
  }));
}

function openMeal(key) {
  editing = meals[key] ? structuredClone(meals[key]) : { date: key, title: "", cook: null, takeout: false, recipe: null };
  editing.originalDate = meals[key] ? key : null;
  mealHeading.textContent = longDate(key, { weekday: "long", month: "long", day: "numeric" });
  mealTitle.value = editing.title;
  setPressed(mealTakeout, editing.takeout);
  mealNotes.value = editing.notes || "";
  renderTakeout();
  renderCookButtons(editing.cook);
  mealRecipeInput.value = "";
  renderMealRecipe();
  renderDayOptions(key);
  mealError.hidden = true;
  mealDelete.hidden = !editing.originalDate;
  mealDialog.showModal();
}

function mealFailed(error) {
  mealError.textContent = error.message;
  mealError.hidden = false;
}

async function openIngredients(key, title) {
  try {
    const ingredients = await api("GET", `/api/meals/${key}/ingredients`);
    if (!ingredients.length) return;
    renderRecipe({ title: `Ingredients for ${title}`, source: null, ingredients });
    recipeDialog.dataset.mode = "meal";
    recipeBackButton.textContent = "Skip";
    recipeDialog.showModal();
  } catch (error) {
    showError(error);
  }
}

mealTakeout.addEventListener("click", () => {
  const on = mealTakeout.getAttribute("aria-pressed") !== "true";
  setPressed(mealTakeout, on);
  if (on && !mealTitle.value.trim()) mealTitle.value = "Take-Out!";
  if (!on && mealTitle.value.trim() === "Take-Out!") mealTitle.value = "";
  renderTakeout();
});

mealRecipeRead.addEventListener("click", async () => {
  const text = mealRecipeInput.value.trim();
  if (!text) return;
  mealRecipeRead.disabled = true;
  mealRecipeRead.textContent = "Reading...";
  try {
    const recipe = await api("POST", "/api/recipes/read", { link_or_text: text });
    editing.recipe = { title: recipe.title, source: recipe.source, lines: recipe.lines, steps: recipe.steps };
    if (!mealTitle.value.trim() && recipe.source) mealTitle.value = recipe.title;
    mealError.hidden = true;
    renderMealRecipe();
  } catch (error) {
    mealFailed(error);
  } finally {
    mealRecipeRead.disabled = false;
    mealRecipeRead.textContent = "Read recipe";
  }
});

document.getElementById("meal-recipe-remove").addEventListener("click", () => {
  editing.recipe = null;
  renderMealRecipe();
});

mealIngredients.addEventListener("click", () => {
  mealDialog.close();
  openIngredients(editing.originalDate, editing.title);
});

mealForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const pressedCook = mealCooks.querySelector("[aria-pressed=true]");
  const dinner = {
    title: mealTitle.value.trim(),
    takeout: mealTakeout.getAttribute("aria-pressed") === "true",
    cook: pressedCook && pressedCook.dataset.cook ? pressedCook.dataset.cook : null,
    recipe: editing.recipe,
    notes: mealNotes.value.trim() || null,
  };
  const target = mealDay.value;
  const newRecipe = dinner.recipe && JSON.stringify(dinner.recipe) !== JSON.stringify((meals[editing.originalDate] || {}).recipe);
  try {
    if (editing.originalDate && editing.originalDate !== target) {
      await api("PUT", `/api/meals/${editing.originalDate}`, dinner);
      await api("POST", `/api/meals/${editing.originalDate}/move?to=${target}`);
    } else {
      await api("PUT", `/api/meals/${target}`, dinner);
    }
    mealDialog.close();
    await loadMeals();
    if (newRecipe) openIngredients(target, dinner.title);
  } catch (error) {
    mealFailed(error);
  }
});

mealDelete.addEventListener("click", async () => {
  if (!confirm(`Delete ${editing.title || "this dinner"}?`)) return;
  try {
    await api("DELETE", `/api/meals/${editing.originalDate}`);
    mealDialog.close();
    await loadMeals();
  } catch (error) {
    mealFailed(error);
  }
});

mealDialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => mealDialog.close()));
document.getElementById("week-prev").addEventListener("click", () => { weekOffset -= 1; loadMeals(); });
document.getElementById("week-next").addEventListener("click", () => { weekOffset += 1; loadMeals(); });
tabButtons.forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));

api("GET", "/api/cooks").then((names) => { cooks = names; }).catch(() => {}).finally(() => {
  if (location.hash === "#dinners") showView("meals");
});
