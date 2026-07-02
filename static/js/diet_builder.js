/*
 * Diet Builder — logica admin per il piano alimentare strutturato.
 * Usa SOLO le API Flask interne (/api/admin/...).
 */
(function () {
  "use strict";

  var root = document.getElementById("diet-builder");
  if (!root) return;

  var SEARCH_URL = root.dataset.searchUrl;
  var IMPORT_URL = root.dataset.importUrl;
  var MEALS_URL = root.dataset.mealsUrl;
  var PLAN_TOTALS_URL = root.dataset.planTotalsUrl;
  var PLAN_DELETE_URL = root.dataset.planDeleteUrl;
  var MEAL_ITEM_BASE = root.dataset.mealItemBase;
  var MEAL_TOTAL_BASE = root.dataset.mealTotalBase;
  var MEAL_DELETE_BASE = root.dataset.mealDeleteBase;
  var ITEM_DELETE_BASE = root.dataset.itemDeleteBase;
  var CUSTOM_FOOD_URL = root.dataset.customFoodUrl;

  var mealsContainer = document.getElementById("meals-container");
  var msgBox = document.getElementById("diet-msg");
  var selected = {};

  function fmt0(v) { return (Math.round(v || 0)).toString(); }
  function fmt1(v) { return (Math.round((v || 0) * 10) / 10).toFixed(1); }

  function showMsg(text, isSuccess) {
    if (!msgBox) return;
    msgBox.textContent = text;
    msgBox.style.display = "block";
    msgBox.classList.toggle("is-success", isSuccess === true);
    clearTimeout(showMsg._t);
    showMsg._t = setTimeout(function () {
      msgBox.style.display = "none";
      msgBox.classList.remove("is-success");
    }, 6000);
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

  function writeTotals(el, t) {
    var map = { kcal: fmt0(t.kcal), protein: fmt1(t.protein), carbs: fmt1(t.carbs), fat: fmt1(t.fat), fiber: fmt1(t.fiber) };
    Object.keys(map).forEach(function (k) {
      var span = el.querySelector('[data-k="' + k + '"]');
      if (span) span.textContent = map[k];
    });
  }

  function refreshMealTotals(mealId) {
    jsonFetch(MEAL_TOTAL_BASE + mealId + "/totals").then(function (res) {
      if (!res.ok) return;
      var el = root.querySelector('[data-meal-total="' + mealId + '"]');
      if (el) writeTotals(el, res.data.totals || {});
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

  // -------------------- ricerca --------------------
  function renderResults(mealId, results) {
    var box = root.querySelector('[data-results="' + mealId + '"]');
    if (!box) return;
    box.innerHTML = "";
    if (!results.length) {
      box.innerHTML = '<div class="food-loading">Nessun risultato. Prova un termine più specifico (es. "petto di pollo").</div>';
      box.classList.add("open");
      return;
    }
    results.forEach(function (food) {
      var div = document.createElement("div");
      div.className = "food-res-item";
      var meta = [];
      if (food.source === "local") meta.push("Salvato in studio");
      else if (food.brand) meta.push(food.brand);
      if (food.kcal_per_100g != null) meta.push(fmt0(food.kcal_per_100g) + " kcal/100g");

      var nameEl = document.createElement("div");
      nameEl.className = "food-res-name";
      nameEl.textContent = food.name;
      if (food.source === "local") {
        var badge = document.createElement("span");
        badge.className = "food-res-badge";
        badge.textContent = "locale";
        nameEl.appendChild(badge);
      }

      var metaEl = document.createElement("div");
      metaEl.className = "food-res-meta";
      metaEl.textContent = meta.join(" · ");

      div.appendChild(nameEl);
      div.appendChild(metaEl);

      div.addEventListener("click", function () {
        selected[mealId] = food;
        var sel = root.querySelector('[data-selected="' + mealId + '"]');
        if (sel) {
          sel.textContent = "Selezionato: " + food.name + (food.brand ? " (" + food.brand + ")" : "");
        }
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
    if (box) {
      box.innerHTML = '<div class="food-loading">Ricerca in corso…</div>';
      box.classList.add("open");
    }
    jsonFetch(SEARCH_URL + "?q=" + encodeURIComponent(query) + "&limit=10").then(function (res) {
      if (!res.ok) {
        showMsg(res.data.error || "Errore nella ricerca alimenti.");
        if (box) box.classList.remove("open");
        return;
      }
      renderResults(mealId, res.data.results || []);
    }).catch(function () {
      showMsg("Errore di rete durante la ricerca.");
    });
  }

  root.addEventListener("input", function (e) {
    var input = e.target.closest(".food-search");
    if (!input) return;
    var mealId = input.dataset.meal;
    selected[mealId] = null;
    var q = input.value.trim();
    clearTimeout(input._t);
    if (q.length < 2) {
      var box = root.querySelector('[data-results="' + mealId + '"]');
      if (box) box.classList.remove("open");
      return;
    }
    input._t = setTimeout(function () { doSearch(mealId, q); }, 350);
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest(".food-search-wrap")) return;
    root.querySelectorAll(".food-results.open").forEach(function (b) { b.classList.remove("open"); });
  });

  // -------------------- aggiungi item --------------------
  function resolveFoodId(food) {
    if (food.local_food_id) {
      return Promise.resolve(food.local_food_id);
    }
    if (food.source === "local") {
      return Promise.resolve(parseInt(food.external_id, 10));
    }
    return jsonFetch(IMPORT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: food.provider, external_id: food.external_id })
    }).then(function (res) {
      if (!res.ok) throw new Error(res.data.error || "Errore import alimento.");
      return res.data.food.id;
    });
  }

  function addItem(mealId) {
    var food = selected[mealId];
    var gramsInput = root.querySelector('[data-grams="' + mealId + '"]');
    var grams = parseFloat((gramsInput && gramsInput.value || "").replace(",", "."));

    if (!food) { showMsg("Seleziona un alimento dall'elenco dei risultati."); return; }
    if (!grams || grams <= 0) { showMsg("Inserisci una quantità in grammi valida."); return; }

    var btn = root.querySelector('[data-add-item="' + mealId + '"]');
    if (btn) btn.disabled = true;

    resolveFoodId(food).then(function (foodId) {
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
      selected[mealId] = null;
      if (gramsInput) gramsInput.value = "";
      var searchInput = root.querySelector('.food-search[data-meal="' + mealId + '"]');
      if (searchInput) searchInput.value = "";
      var sel = root.querySelector('[data-selected="' + mealId + '"]');
      if (sel) sel.textContent = "";
      showMsg("Alimento aggiunto.", false);
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
    var html = tpl
      .replace(/__ITEM_ID__/g, item.id)
      .replace("__QTY__", fmt0(item.quantity_g))
      .replace("__MACROS__", macrosText(item.computed || {}));
    var wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    var node = wrap.firstChild;
    node.querySelector(".di-name").textContent = food.name + (food.brand ? " · " + food.brand : "");
    container.appendChild(node);
  }

  // -------------------- elimina --------------------
  function deleteMeal(mealId) {
    if (!confirm("Eliminare questo pasto e tutti gli alimenti al suo interno?")) return;
    jsonFetch(MEAL_DELETE_BASE + mealId, { method: "DELETE" }).then(function (res) {
      if (!res.ok) { showMsg(res.data.error || "Impossibile eliminare il pasto."); return; }
      var card = root.querySelector('[data-meal-id="' + mealId + '"]');
      if (card) card.remove();
      refreshPlanTotals();
      showMsg("Pasto eliminato.", false);
    });
  }

  function deleteItem(itemId, mealId) {
    jsonFetch(ITEM_DELETE_BASE + itemId, { method: "DELETE" }).then(function (res) {
      if (!res.ok) { showMsg(res.data.error || "Impossibile rimuovere l'alimento."); return; }
      var row = root.querySelector('[data-item-id="' + itemId + '"]');
      if (row) row.remove();
      var container = root.querySelector('[data-items="' + mealId + '"]');
      if (container && !container.querySelector(".diet-item")) {
        var empty = document.createElement("div");
        empty.className = "diet-empty-items";
        empty.textContent = "Nessun alimento in questo pasto.";
        container.appendChild(empty);
      }
      refreshMealTotals(mealId);
      refreshPlanTotals();
    });
  }

  var deletePlanBtn = document.getElementById("delete-plan-btn");
  if (deletePlanBtn) {
    deletePlanBtn.addEventListener("click", function () {
      if (!confirm("Eliminare definitivamente questa dieta? L'operazione non è reversibile.")) return;
      jsonFetch(PLAN_DELETE_URL, { method: "DELETE" }).then(function (res) {
        if (!res.ok) { showMsg(res.data.error || "Impossibile eliminare la dieta."); return; }
        window.location = deletePlanBtn.dataset.patientUrl;
      });
    });
  }

  root.addEventListener("click", function (e) {
    var addBtn = e.target.closest("[data-add-item]");
    if (addBtn) { e.preventDefault(); addItem(addBtn.dataset.addItem); return; }

    var delMeal = e.target.closest("[data-delete-meal]");
    if (delMeal) { e.preventDefault(); deleteMeal(delMeal.dataset.deleteMeal); return; }

    var delItem = e.target.closest("[data-delete-item]");
    if (delItem) {
      e.preventDefault();
      var mealCard = delItem.closest("[data-meal-id]");
      var mealId = mealCard && mealCard.dataset.mealId;
      deleteItem(delItem.dataset.deleteItem, mealId);
      return;
    }

    var customBtn = e.target.closest("[data-add-custom]");
    if (customBtn) {
      e.preventDefault();
      addCustomItem(customBtn.dataset.addCustom);
    }
  });

  function addCustomItem(mealId) {
    var form = root.querySelector('[data-custom-meal="' + mealId + '"]');
    if (!form) return;
    var name = (form.querySelector("[data-c-name]") || {}).value || "";
    name = name.trim();
    var grams = parseFloat((form.querySelector("[data-c-grams]") || {}).value || "");
    if (!name) { showMsg("Inserisci il nome dell'alimento custom."); return; }
    if (!grams || grams <= 0) { showMsg("Inserisci i grammi."); return; }

    var payload = {
      name: name,
      kcal_per_100g: parseFloat(form.querySelector("[data-c-kcal]").value) || null,
      protein_per_100g: parseFloat(form.querySelector("[data-c-protein]").value) || null,
      carbs_per_100g: parseFloat(form.querySelector("[data-c-carbs]").value) || null,
      fat_per_100g: parseFloat(form.querySelector("[data-c-fat]").value) || null
    };

    var btn = form.querySelector("[data-add-custom]");
    if (btn) btn.disabled = true;

    jsonFetch(CUSTOM_FOOD_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) throw new Error(res.data.error || "Errore creazione alimento custom.");
      var food = res.data.food;
      food.local_food_id = food.id;
      food.source = "local";
      return jsonFetch(MEAL_ITEM_BASE + mealId + "/items", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ food_id: food.id, quantity_g: grams })
      }).then(function (itemRes) {
        if (!itemRes.ok) throw new Error(itemRes.data.error || "Errore aggiunta alimento.");
        appendItemRow(mealId, food, itemRes.data.item);
        refreshMealTotals(mealId);
        refreshPlanTotals();
        form.querySelectorAll("input").forEach(function (inp) { inp.value = ""; });
        showMsg("Alimento custom aggiunto.", false);
      });
    }).catch(function (err) {
      showMsg(err.message || "Errore imprevisto.");
    }).finally(function () {
      if (btn) btn.disabled = false;
    });
  }

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
        day_index: Math.max(0, dayInput - 1),
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
        showMsg("Pasto aggiunto.", false);
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
