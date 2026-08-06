/*
 * Diet Builder — vista per giorno (admin).
 * Usa SOLO le API Flask interne (/api/admin/...).
 */
(function () {
  "use strict";

  var root = document.getElementById("diet-builder");
  if (!root) return;

  var SEARCH_URL = root.dataset.searchUrl;
  var IMPORT_URL = root.dataset.importUrl;
  var MEALS_URL = root.dataset.mealsUrl;
  var ENSURE_DAY_URL = root.dataset.ensureDayUrl;
  var COPY_DAY_URL = root.dataset.copyDayUrl;
  var PLAN_TOTALS_URL = root.dataset.planTotalsUrl;
  var PLAN_DELETE_URL = root.dataset.planDeleteUrl;
  var MEAL_ITEM_BASE = root.dataset.mealItemBase;
  var MEAL_TOTAL_BASE = root.dataset.mealTotalBase;
  var MEAL_DELETE_BASE = root.dataset.mealDeleteBase;
  var ITEM_DELETE_BASE = root.dataset.itemDeleteBase;
  var ITEM_UPDATE_BASE = root.dataset.itemUpdateBase;
  var CUSTOM_FOOD_URL = root.dataset.customFoodUrl;

  var mealsContainer = document.getElementById("meals-container");
  var dayTabs = document.getElementById("day-tabs");
  var dayEmpty = document.getElementById("day-empty");
  var dayKpiLabel = document.getElementById("day-kpi-label");
  var msgBox = document.getElementById("diet-msg");
  var selected = {};
  var perDayTotals = {};
  var currentDay = parseInt(root.dataset.initialDay || "1", 10) || 1;
  var dayCount = Math.max(7, parseInt(root.dataset.dayCount || "7", 10) || 7);
  var DEFAULT_DAY_MEALS = ["Colazione", "Spuntino", "Pranzo", "Cena"];

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
      " · C " + fmt1(c.carbs) + " · G " + fmt1(c.fat);
  }

  function writeTotals(el, t) {
    if (!el || !t) return;
    var map = { kcal: fmt0(t.kcal), protein: fmt1(t.protein), carbs: fmt1(t.carbs), fat: fmt1(t.fat), fiber: fmt1(t.fiber) };
    Object.keys(map).forEach(function (k) {
      var span = el.querySelector('[data-k="' + k + '"]');
      if (span) span.textContent = map[k];
    });
    refreshMacroPcts(el);
  }

  function bumpTotals(el, delta) {
    if (!el || !delta) return;
    var keys = ["kcal", "protein", "carbs", "fat", "fiber"];
    keys.forEach(function (k) {
      var node = el.querySelector('[data-k="' + k + '"]');
      if (!node) return;
      var cur = parseFloat(String(node.textContent).replace(",", ".")) || 0;
      var next = cur + (parseFloat(delta[k]) || 0);
      node.textContent = k === "kcal" ? fmt0(next) : fmt1(next);
    });
    refreshMacroPcts(el);
  }

  function refreshMacroPcts(el) {
    if (!el || !el.querySelector("[data-pct]")) return;
    function grams(k) {
      var n = el.querySelector('[data-k="' + k + '"]');
      return n ? (parseFloat(String(n.textContent).replace(",", ".")) || 0) : 0;
    }
    var kcals = { protein: grams("protein") * 4, carbs: grams("carbs") * 4, fat: grams("fat") * 9 };
    var total = kcals.protein + kcals.carbs + kcals.fat;
    Object.keys(kcals).forEach(function (k) {
      var node = el.querySelector('[data-pct="' + k + '"]');
      if (node) node.textContent = (total > 0 ? Math.round((kcals[k] / total) * 100) : 0) + "%";
    });
  }

  function mealTotalEl(mealId) {
    return document.querySelector('[data-meal-total="' + mealId + '"]');
  }

  function dayTotalEl() {
    return document.querySelector("[data-day-total]");
  }

  function emptyTotals() {
    return { kcal: 0, protein: 0, carbs: 0, fat: 0, fiber: 0 };
  }

  function mealCoversDay(card, day) {
    var from = parseInt(card.getAttribute("data-day-from"), 10) || 1;
    var to = parseInt(card.getAttribute("data-day-to"), 10) || from;
    if (to < from) to = from;
    return from <= day && day <= to;
  }

  function visibleMealCards() {
    return Array.prototype.filter.call(
      root.querySelectorAll(".diet-meal[data-meal-id]"),
      function (card) { return mealCoversDay(card, currentDay); }
    );
  }

  function syncDayView() {
    var any = false;
    root.querySelectorAll(".diet-meal[data-meal-id]").forEach(function (card) {
      var show = mealCoversDay(card, currentDay);
      card.hidden = !show;
      if (show) any = true;
    });
    if (dayEmpty) dayEmpty.hidden = any;
    if (dayKpiLabel) dayKpiLabel.textContent = "Giorno " + currentDay;
    writeTotals(dayTotalEl(), perDayTotals[currentDay] || emptyTotals());
    renderDayTabs();
  }

  function renderDayTabs() {
    if (!dayTabs) return;
    dayTabs.innerHTML = "";
    for (var d = 1; d <= dayCount; d++) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "diet-day-tab" + (d === currentDay ? " is-active" : "");
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", d === currentDay ? "true" : "false");
      btn.dataset.day = String(d);
      btn.textContent = "G" + d;
      btn.title = "Giorno " + d;
      dayTabs.appendChild(btn);
    }
  }

  function expandDayCountTo(n) {
    dayCount = Math.max(dayCount, n, 7);
    root.dataset.dayCount = String(dayCount);
  }

  function refreshMealTotals(mealId) {
    if (!MEAL_TOTAL_BASE) return;
    jsonFetch(MEAL_TOTAL_BASE + mealId + "/totals").then(function (res) {
      if (!res.ok) return;
      writeTotals(mealTotalEl(mealId), res.data.totals || {});
    });
  }

  function applyPerDayFromResponse(totals) {
    perDayTotals = {};
    var raw = (totals && totals.per_day) || {};
    Object.keys(raw).forEach(function (k) {
      var day1 = parseInt(k, 10) + 1;
      if (!isNaN(day1)) {
        perDayTotals[day1] = raw[k];
        if (day1 > dayCount) expandDayCountTo(day1);
      }
    });
    writeTotals(dayTotalEl(), perDayTotals[currentDay] || emptyTotals());
  }

  function refreshPlanTotals() {
    if (!PLAN_TOTALS_URL) return Promise.resolve();
    return jsonFetch(PLAN_TOTALS_URL).then(function (res) {
      if (!res.ok) return;
      applyPerDayFromResponse(res.data.totals || {});
    });
  }

  function refreshAllTotals() {
    refreshPlanTotals();
    visibleMealCards().forEach(function (card) {
      var mealId = card.getAttribute("data-meal-id");
      if (mealId && mealId.indexOf("__") === -1) refreshMealTotals(mealId);
    });
  }

  // -------------------- ricerca --------------------
  function renderResults(mealId, results, warning) {
    var box = root.querySelector('[data-results="' + mealId + '"]');
    if (!box) return;
    box.innerHTML = "";
    if (warning && results.length) {
      var warnEl = document.createElement("div");
      warnEl.className = "food-loading food-loading--warn";
      warnEl.textContent = warning;
      box.appendChild(warnEl);
    }
    if (!results.length) {
      var emptyMsg = warning
        ? warning
        : 'Nessun risultato. Prova in italiano (es. "petto di pollo") o in inglese ("chicken breast").';
      box.innerHTML = '<div class="food-loading food-loading--warn">' + emptyMsg + "</div>";
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
      renderResults(mealId, res.data.results || [], res.data.warning || null);
    }).catch(function () {
      showMsg("Errore di rete durante la ricerca.");
    });
  }

  root.addEventListener("input", function (e) {
    var input = e.target.closest(".food-search");
    if (input) {
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
      return;
    }

    var qtyInput = e.target.closest("[data-qty-item]");
    if (qtyInput) {
      clearTimeout(qtyInput._t);
      qtyInput._t = setTimeout(function () {
        updateItemQty(qtyInput.dataset.qtyItem, qtyInput);
      }, 500);
    }
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest(".food-search-wrap")) return;
    root.querySelectorAll(".food-results.open").forEach(function (b) { b.classList.remove("open"); });
  });

  // -------------------- item qty --------------------
  function updateItemQty(itemId, inputEl) {
    var grams = parseFloat(String(inputEl.value || "").replace(",", "."));
    if (!grams || grams <= 0) {
      showMsg("Inserisci una quantità in grammi valida.");
      return;
    }
    if (!ITEM_UPDATE_BASE) return;
    inputEl.classList.add("is-saving");
    jsonFetch(ITEM_UPDATE_BASE + itemId, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity_g: grams })
    }).then(function (res) {
      if (!res.ok) throw new Error(res.data.error || "Impossibile aggiornare i grammi.");
      var item = res.data.item || {};
      var macrosEl = root.querySelector('[data-item-macros="' + itemId + '"]');
      if (macrosEl) macrosEl.textContent = macrosText(item.computed || {});
      var mealCard = inputEl.closest("[data-meal-id]");
      var mealId = mealCard && mealCard.dataset.mealId;
      if (mealId) refreshMealTotals(mealId);
      refreshPlanTotals();
    }).catch(function (err) {
      showMsg(err.message || "Errore aggiornamento grammi.");
    }).finally(function () {
      inputEl.classList.remove("is-saving");
    });
  }

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
      var computed = (res.data.item && res.data.item.computed) || {};
      bumpTotals(mealTotalEl(mealId), computed);
      refreshMealTotals(mealId);
      refreshPlanTotals();
      selected[mealId] = null;
      if (gramsInput) gramsInput.value = "";
      var searchInput = root.querySelector('.food-search[data-meal="' + mealId + '"]');
      if (searchInput) searchInput.value = "";
      var sel = root.querySelector('[data-selected="' + mealId + '"]');
      if (sel) sel.textContent = "";
      showMsg("Alimento aggiunto.", true);
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
      .replace(/__QTY__/g, fmt0(item.quantity_g))
      .replace("__MACROS__", macrosText(item.computed || {}))
      .replace("__NAME__", "");
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
      syncDayView();
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

  var planStatusSelect = document.getElementById("plan-status");
  var planStatusLabel = document.getElementById("plan-status-label");
  if (planStatusSelect) {
    var planStatusPrev = planStatusSelect.value;
    planStatusSelect.addEventListener("change", function () {
      var nextStatus = planStatusSelect.value;
      var updateUrl = planStatusSelect.dataset.planUpdateUrl;
      if (!updateUrl) return;

      planStatusSelect.classList.add("is-saving");
      jsonFetch(updateUrl, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus })
      }).then(function (res) {
        if (!res.ok) throw new Error(res.data.error || "Impossibile aggiornare lo stato.");
        planStatusPrev = nextStatus;
        if (planStatusLabel) {
          planStatusLabel.textContent = nextStatus === "published" ? "Pubblicata" : "Bozza";
        }
        showMsg(
          nextStatus === "published"
            ? "Dieta pubblicata: il paziente può vederla."
            : "Dieta salvata come bozza: non visibile al paziente.",
          true
        );
      }).catch(function (err) {
        planStatusSelect.value = planStatusPrev;
        showMsg(err.message || "Errore aggiornamento stato.");
      }).finally(function () {
        planStatusSelect.classList.remove("is-saving");
      });
    });
  }

  var targetsToggle = document.getElementById("targets-toggle");
  var targetsForm = document.getElementById("targets-form");
  if (targetsToggle && targetsForm) {
    targetsToggle.addEventListener("click", function () {
      targetsForm.hidden = !targetsForm.hidden;
    });

    targetsForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var updateUrl = targetsForm.dataset.planUpdateUrl;
      if (!updateUrl) return;

      var payload = {};
      ["target_kcal", "target_protein_pct", "target_carbs_pct", "target_fat_pct"].forEach(function (name) {
        var input = targetsForm.querySelector('[name="' + name + '"]');
        if (input) payload[name] = input.value.trim() === "" ? null : input.value;
      });

      var submitBtn = targetsForm.querySelector('[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
      jsonFetch(updateUrl, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (res) {
        if (!res.ok) throw new Error(res.data.error || "Impossibile salvare gli obiettivi.");
        window.location.reload();
      }).catch(function (err) {
        showMsg(err.message || "Errore salvataggio obiettivi.");
        if (submitBtn) submitBtn.disabled = false;
      });
    });
  }

  // -------------------- pasti / giorno --------------------
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function appendMealCard(meal) {
    if (!mealsContainer) return;
    var from = ((meal && meal.day_index) || 0) + 1;
    var to = meal && meal.day_index_to != null ? meal.day_index_to + 1 : from;
    if (to < from) to = from;
    expandDayCountTo(to);

    var sharedBadge = from !== to
      ? ' <span class="diet-shared-badge" title="Pasto condiviso su più giorni">Giorni ' + from + "–" + to + "</span>"
      : "";

    var tpl = document.getElementById("meal-tpl").innerHTML;
    var html = tpl
      .replace(/__MEAL_ID__/g, meal.id)
      .replace(/__DAY_FROM__/g, String(from))
      .replace(/__DAY_TO__/g, String(to))
      .replace(/__MEAL_NAME_HTML__/g, escapeHtml(meal.meal_name || "") + sharedBadge)
      .replace(/__MEAL_NAME__/g, escapeHtml(meal.meal_name || ""));

    var wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    var node = wrap.firstChild;
    node.setAttribute("data-meal-name", meal.meal_name || "");
    // title text already in HTML; ensure plain name in title node text if needed
    mealsContainer.appendChild(node);
    syncDayView();
    return node;
  }

  function createMeal(name, day1) {
    day1 = day1 || currentDay;
    if (!MEALS_URL) {
      showMsg("URL pasti non configurato. Ricarica la pagina.");
      return Promise.reject(new Error("missing meals url"));
    }
    var dayIdx = Math.max(0, day1 - 1);
    return jsonFetch(MEALS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        meal_name: name,
        day_index: dayIdx,
        day_index_to: dayIdx
      })
    }).then(function (res) {
      if (!res.ok) throw new Error((res.data && res.data.error) || "Errore creazione pasto.");
      if (res.data && res.data.meal) appendMealCard(res.data.meal);
      return res.data.meal;
    });
  }

  function ensureDayMeals(names) {
    if (!ENSURE_DAY_URL) return Promise.reject(new Error("missing ensure url"));
    return jsonFetch(ENSURE_DAY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: currentDay, meals: names || DEFAULT_DAY_MEALS })
    }).then(function (res) {
      if (!res.ok) throw new Error((res.data && res.data.error) || "Errore creazione giornata.");
      (res.data.meals || []).forEach(function (meal) { appendMealCard(meal); });
      syncDayView();
      var n = (res.data.meals || []).length;
      if (n) showMsg("Giornata preparata (" + n + " pasti).", true);
      else showMsg("I pasti tipici sono già presenti per questo giorno.", true);
      return res.data;
    });
  }

  function dayHasMealName(name) {
    var key = String(name || "").trim().toLowerCase();
    return visibleMealCards().some(function (card) {
      return String(card.getAttribute("data-meal-name") || "").trim().toLowerCase() === key;
    });
  }

  // -------------------- copia giorno --------------------
  var copyDialog = document.getElementById("copy-day-dialog");
  var copyCheckboxes = document.getElementById("copy-day-checkboxes");
  var copyFromLabel = document.getElementById("copy-from-label");

  function openCopyDayDialog() {
    if (!copyDialog || !copyCheckboxes) return;
    if (!visibleMealCards().length) {
      showMsg("Aggiungi almeno un pasto prima di copiare il giorno.");
      return;
    }
    if (copyFromLabel) copyFromLabel.textContent = String(currentDay);
    copyCheckboxes.innerHTML = "";
    for (var d = 1; d <= dayCount; d++) {
      if (d === currentDay) continue;
      var label = document.createElement("label");
      label.className = "diet-copy-day-option";
      label.innerHTML = '<input type="checkbox" name="to_day" value="' + d + '" checked> Giorno ' + d;
      copyCheckboxes.appendChild(label);
    }
    if (typeof copyDialog.showModal === "function") copyDialog.showModal();
    else copyDialog.setAttribute("open", "");
  }

  function closeCopyDayDialog() {
    if (!copyDialog) return;
    if (typeof copyDialog.close === "function") copyDialog.close();
    else copyDialog.removeAttribute("open");
  }

  function submitCopyDay(e) {
    if (e) e.preventDefault();
    if (!COPY_DAY_URL || !copyCheckboxes) return;
    var toDays = Array.prototype.map.call(
      copyCheckboxes.querySelectorAll('input[name="to_day"]:checked'),
      function (el) { return parseInt(el.value, 10); }
    ).filter(function (n) { return n && n !== currentDay; });

    if (!toDays.length) {
      showMsg("Seleziona almeno un giorno destinazione.");
      return;
    }

    var confirmBtn = document.getElementById("copy-day-confirm");
    if (confirmBtn) confirmBtn.disabled = true;

    jsonFetch(COPY_DAY_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_day: currentDay, to_days: toDays })
    }).then(function (res) {
      if (!res.ok) throw new Error((res.data && res.data.error) || "Errore copia giorno.");
      closeCopyDayDialog();
      showMsg(
        "Giorno copiato su " + (res.data.to_days || toDays).join(", ") +
          " (" + (res.data.meals_created || 0) + " pasti).",
        true
      );
      // Ricarica per mostrare i pasti clonati con gli item
      window.location.reload();
    }).catch(function (err) {
      showMsg(err.message || "Errore copia giorno.");
    }).finally(function () {
      if (confirmBtn) confirmBtn.disabled = false;
    });
  }

  // -------------------- eventi UI --------------------
  if (dayTabs) {
    dayTabs.addEventListener("click", function (e) {
      var tab = e.target.closest("[data-day]");
      if (!tab) return;
      currentDay = parseInt(tab.dataset.day, 10) || 1;
      syncDayView();
    });
  }

  var addDayBtn = document.getElementById("add-day-btn");
  if (addDayBtn) {
    addDayBtn.addEventListener("click", function () {
      expandDayCountTo(dayCount + 1);
      currentDay = dayCount;
      syncDayView();
      showMsg("Aggiunto Giorno " + currentDay + ". Usa i chip per creare i pasti.", true);
    });
  }

  var createDayBtn = document.getElementById("create-day-template-btn");
  if (createDayBtn) {
    createDayBtn.addEventListener("click", function () {
      createDayBtn.disabled = true;
      ensureDayMeals(DEFAULT_DAY_MEALS).catch(function (err) {
        showMsg(err.message || "Errore creazione giornata.");
      }).finally(function () {
        createDayBtn.disabled = false;
      });
    });
  }

  var copyDayBtn = document.getElementById("copy-day-btn");
  if (copyDayBtn) copyDayBtn.addEventListener("click", openCopyDayDialog);

  var copyCancel = document.getElementById("copy-day-cancel");
  if (copyCancel) copyCancel.addEventListener("click", closeCopyDayDialog);

  var copyForm = document.getElementById("copy-day-form");
  if (copyForm) copyForm.addEventListener("submit", submitCopyDay);

  root.addEventListener("click", function (e) {
    var chip = e.target.closest("[data-add-meal-name]");
    if (chip) {
      e.preventDefault();
      var name = chip.getAttribute("data-add-meal-name");
      if (dayHasMealName(name)) {
        showMsg('Il pasto "' + name + '" è già presente in questo giorno.');
        return;
      }
      chip.disabled = true;
      createMeal(name, currentDay).then(function () {
        showMsg("Pasto \"" + name + "\" aggiunto.", true);
      }).catch(function (err) {
        showMsg(err.message || "Errore creazione pasto.");
      }).finally(function () {
        chip.disabled = false;
      });
      return;
    }

    if (e.target.closest("#add-custom-meal-btn")) {
      e.preventDefault();
      var customName = window.prompt("Nome del pasto:", "");
      if (!customName) return;
      customName = customName.trim();
      if (!customName) return;
      if (dayHasMealName(customName)) {
        showMsg('Il pasto "' + customName + '" è già presente in questo giorno.');
        return;
      }
      createMeal(customName, currentDay).then(function () {
        showMsg("Pasto \"" + customName + "\" aggiunto.", true);
      }).catch(function (err) {
        showMsg(err.message || "Errore creazione pasto.");
      });
      return;
    }

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
        var computed = (itemRes.data.item && itemRes.data.item.computed) || {};
        bumpTotals(mealTotalEl(mealId), computed);
        refreshMealTotals(mealId);
        refreshPlanTotals();
        form.querySelectorAll("input").forEach(function (inp) { inp.value = ""; });
        showMsg("Alimento custom aggiunto.", true);
      });
    }).catch(function (err) {
      showMsg(err.message || "Errore imprevisto.");
    }).finally(function () {
      if (btn) btn.disabled = false;
    });
  }

  // Init: espandi dayCount dai pasti già in pagina
  root.querySelectorAll(".diet-meal[data-day-to]").forEach(function (card) {
    var to = parseInt(card.getAttribute("data-day-to"), 10) || 1;
    expandDayCountTo(to);
  });

  syncDayView();
  refreshAllTotals();
})();
