/*
 * Diet Builder — logica admin per il piano alimentare strutturato.
 * Usa SOLO le API Flask interne (/api/admin/...). Nessuna chiamata diretta
 * al provider esterno dal browser.
 */
(function () {
  "use strict";

  var root = document.getElementById("diet-builder");
  if (!root) return;

  var SEARCH_URL = root.dataset.searchUrl;
  var IMPORT_URL = root.dataset.importUrl;
  var MEALS_URL = root.dataset.mealsUrl;
  var PLAN_TOTALS_URL = root.dataset.planTotalsUrl;
  var MEAL_ITEM_BASE = root.dataset.mealItemBase; // + {id}/items
  var MEAL_TOTAL_BASE = root.dataset.mealTotalBase; // + {id}/totals

  var mealsContainer = document.getElementById("meals-container");
  var msgBox = document.getElementById("diet-msg");

  // Alimento selezionato per ogni pasto: { mealId: foodObj }
  var selected = {};

  // -------------------- utility --------------------
  function fmt0(v) { return (Math.round((v || 0))).toString(); }
  function fmt1(v) { return (Math.round((v || 0) * 10) / 10).toFixed(1); }

  function showMsg(text) {
    msgBox.textContent = text;
    msgBox.style.display = "block";
    clearTimeout(showMsg._t);
    showMsg._t = setTimeout(function () { msgBox.style.display = "none"; }, 6000);
  }

  function jsonFetch(url, options) {
    options = options || {};
    options.credentials = "same-origin";
    return fetch(url, options).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        return { ok: r.ok, status: r.status, data: data };
      });
    });
  }

  function macrosText(c) {
    return fmt0(c.kcal) + " kcal · P " + fmt1(c.protein) +
      " · C " + fmt1(c.carbs) + " · G " + fmt1(c.fat) + " · Fib " + fmt1(c.fiber);
  }

  // -------------------- totali --------------------
  function refreshMealTotals(mealId) {
    jsonFetch(MEAL_TOTAL_BASE + mealId + "/totals").then(function (res) {
      if (!res.ok) return;
      var t = res.data.totals || {};
      var el = root.querySelector('[data-meal-total="' + mealId + '"]');
      if (el) writeTotals(el, t);
    });
  }

  function refreshPlanTotals() {
    jsonFetch(PLAN_TOTALS_URL).then(function (res) {
      if (!res.ok) return;
      var t = (res.data.totals && res.data.totals.total) || {};
      var el = root.querySelector("[data-plan-total]");
      if (el) writeTotals(el, t);
    });
  }

  function writeTotals(el, t) {
    var map = { kcal: fmt0(t.kcal), protein: fmt1(t.protein), carbs: fmt1(t.carbs), fat: fmt1(t.fat), fiber: fmt1(t.fiber) };
    Object.keys(map).forEach(function (k) {
      var span = el.querySelector('[data-k="' + k + '"]');
      if (span) span.textContent = map[k];
    });
  }

  // -------------------- ricerca alimenti --------------------
  function renderResults(mealId, results) {
    var box = root.querySelector('[data-results="' + mealId + '"]');
    if (!box) return;
    box.innerHTML = "";
    if (!results.length) {
      box.innerHTML = '<div class="food-loading">Nessun risultato.</div>';
      box.classList.add("open");
      return;
    }
    results.forEach(function (food) {
      var div = document.createElement("div");
      div.className = "food-res-item";
      var meta = [];
      if (food.brand) meta.push(food.brand);
      if (food.kcal_per_100g != null) meta.push(fmt0(food.kcal_per_100g) + " kcal/100g");
      div.innerHTML =
        '<div class="food-res-name"></div><div class="food-res-meta"></div>';
      div.querySelector(".food-res-name").textContent = food.name;
      div.querySelector(".food-res-meta").textContent = meta.join(" · ");
      div.addEventListener("click", function () {
        selected[mealId] = food;
        var sel = root.querySelector('[data-selected="' + mealId + '"]');
        if (sel) sel.textContent = "Selezionato: " + food.name + (food.brand ? " (" + food.brand + ")" : "");
        var input = root.querySelector('.food-search[data-meal="' + mealId + '"]');
        if (input) input.value = food.name;
        box.classList.remove("open");
      });
      box.appendChild(div);
    });
    box.classList.add("open");
  }

  function doSearch(mealId, query) {
    var box = root.querySelector('[data-results="' + mealId + '"]');
    if (box) { box.innerHTML = '<div class="food-loading">Ricerca…</div>'; box.classList.add("open"); }
    jsonFetch(SEARCH_URL + "?q=" + encodeURIComponent(query) + "&limit=8").then(function (res) {
      if (!res.ok) { showMsg(res.data.error || "Errore nella ricerca alimenti."); if (box) box.classList.remove("open"); return; }
      renderResults(mealId, res.data.results || []);
    }).catch(function () { showMsg("Errore di rete durante la ricerca."); });
  }

  // debounce per input
  root.addEventListener("input", function (e) {
    var input = e.target.closest(".food-search");
    if (!input) return;
    var mealId = input.dataset.meal;
    // se l'utente riscrive, la selezione precedente non è più valida
    selected[mealId] = null;
    var q = input.value.trim();
    clearTimeout(input._t);
    if (q.length < 2) {
      var box = root.querySelector('[data-results="' + mealId + '"]');
      if (box) box.classList.remove("open");
      return;
    }
    input._t = setTimeout(function () { doSearch(mealId, q); }, 300);
  });

  // chiudi i dropdown cliccando fuori
  document.addEventListener("click", function (e) {
    if (e.target.closest(".food-adder")) return;
    root.querySelectorAll(".food-results.open").forEach(function (b) { b.classList.remove("open"); });
  });

  // -------------------- aggiungi item --------------------
  function addItem(mealId) {
    var food = selected[mealId];
    var gramsInput = root.querySelector('[data-grams="' + mealId + '"]');
    var grams = parseFloat((gramsInput && gramsInput.value || "").replace(",", "."));

    if (!food) { showMsg("Seleziona prima un alimento dalla ricerca."); return; }
    if (!grams || grams <= 0) { showMsg("Inserisci una quantità in grammi valida."); return; }

    var btn = root.querySelector('[data-add-item="' + mealId + '"]');
    if (btn) btn.disabled = true;

    // 1) import/riuso alimento locale
    jsonFetch(IMPORT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: food.provider, external_id: food.external_id })
    }).then(function (res) {
      if (!res.ok) throw new Error(res.data.error || "Errore import alimento.");
      var foodId = res.data.food.id;
      // 2) aggiungi item al pasto
      return jsonFetch(MEAL_ITEM_BASE + mealId + "/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ food_id: foodId, quantity_g: grams })
      });
    }).then(function (res) {
      if (!res.ok) throw new Error(res.data.error || "Errore aggiunta alimento.");
      appendItemRow(mealId, food, res.data.item);
      refreshMealTotals(mealId);
      refreshPlanTotals();
      // reset UI
      selected[mealId] = null;
      if (gramsInput) gramsInput.value = "";
      var searchInput = root.querySelector('.food-search[data-meal="' + mealId + '"]');
      if (searchInput) searchInput.value = "";
      var sel = root.querySelector('[data-selected="' + mealId + '"]');
      if (sel) sel.textContent = "";
    }).catch(function (err) {
      showMsg(err.message || "Errore imprevisto.");
    }).finally(function () {
      if (btn) btn.disabled = false;
    });
  }

  function appendItemRow(mealId, food, item) {
    var container = root.querySelector('[data-items="' + mealId + '"]');
    if (!container) return;
    var empty = container.querySelector(".diet-empty-items");
    if (empty) empty.remove();

    var tpl = document.getElementById("item-tpl").innerHTML;
    var name = food.name + (food.brand ? ' · ' + food.brand : '');
    var html = tpl
      .replace("__ITEM_ID__", item.id)
      .replace("__QTY__", fmt0(item.quantity_g))
      .replace("__MACROS__", macrosText(item.computed || {}));
    var wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    var node = wrap.firstChild;
    node.querySelector(".di-name").textContent = name;
    container.appendChild(node);
  }

  root.addEventListener("click", function (e) {
    var addBtn = e.target.closest("[data-add-item]");
    if (addBtn) { e.preventDefault(); addItem(addBtn.dataset.addItem); }
  });

  // -------------------- aggiungi pasto --------------------
  var mealForm = document.getElementById("meal-form");
  if (mealForm) {
    mealForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var name = mealForm.meal_name.value.trim();
      if (!name) { showMsg("Inserisci il nome del pasto."); return; }
      var dayInput = parseInt(mealForm.day_index.value, 10) || 1;
      var payload = {
        meal_name: name,
        day_index: Math.max(0, dayInput - 1), // UI 1-based → backend 0-based
        meal_time: mealForm.meal_time.value || null
      };
      var btn = mealForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      jsonFetch(MEALS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (res) {
        if (!res.ok) { showMsg(res.data.error || "Errore creazione pasto."); return; }
        appendMealCard(res.data.meal);
        mealForm.reset();
        mealForm.day_index.value = dayInput;
      }).catch(function () { showMsg("Errore di rete."); })
        .finally(function () { btn.disabled = false; });
    });
  }

  function appendMealCard(meal) {
    var tpl = document.getElementById("meal-tpl").innerHTML;
    var sub = "Giorno " + ((meal.day_index || 0) + 1) + (meal.meal_time ? " · " + meal.meal_time : "");
    var html = tpl.replace(/__MEAL_ID__/g, meal.id).replace("__MEAL_SUB__", sub);
    var wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    var node = wrap.firstChild;
    node.querySelector(".diet-meal-title").textContent = meal.meal_name;
    mealsContainer.appendChild(node);
  }
})();
