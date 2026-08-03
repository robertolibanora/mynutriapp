/**
 * Ricerca globale paziente (header admin) — debounce, tastiera, Cmd/Ctrl+K.
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 220;
  var MIN_LEN = 2;

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function init() {
    var root = qs("[data-global-search]");
    if (!root) return;

    var input = qs("[data-gs-input]", root);
    var panel = qs("[data-gs-panel]", root);
    var list = qs("[data-gs-list]", root);
    var empty = qs("[data-gs-empty]", root);
    var hint = qs("[data-gs-hint]", root);
    var searchUrl = root.getAttribute("data-search-url");
    if (!input || !panel || !list || !searchUrl) return;

    var timer = null;
    var abortCtrl = null;
    var items = [];
    var activeIdx = -1;

    function openPanel() {
      panel.hidden = false;
      root.classList.add("is-open");
    }

    function closePanel() {
      panel.hidden = true;
      root.classList.remove("is-open");
      activeIdx = -1;
    }

    function setActive(idx) {
      var nodes = list.querySelectorAll("[data-gs-item]");
      nodes.forEach(function (n) {
        n.classList.remove("is-active");
        n.setAttribute("aria-selected", "false");
      });
      if (idx < 0 || idx >= nodes.length) {
        activeIdx = -1;
        return;
      }
      activeIdx = idx;
      nodes[idx].classList.add("is-active");
      nodes[idx].setAttribute("aria-selected", "true");
      nodes[idx].scrollIntoView({ block: "nearest" });
    }

    function goTo(idx) {
      if (idx < 0 || idx >= items.length) return;
      window.location.href = items[idx].url;
    }

    function render(results, query) {
      items = results || [];
      list.innerHTML = "";
      activeIdx = -1;

      if (hint) hint.hidden = true;

      if (!query || query.length < MIN_LEN) {
        if (empty) {
          empty.hidden = false;
          empty.textContent = "Digita almeno 2 caratteri per cercare un paziente.";
        }
        openPanel();
        return;
      }

      if (!items.length) {
        if (empty) {
          empty.hidden = false;
          empty.textContent = 'Nessun paziente trovato per "' + query + '".';
        }
        openPanel();
        return;
      }

      if (empty) empty.hidden = true;

      items.forEach(function (r, i) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.setAttribute("data-gs-item", String(i));
        li.setAttribute("aria-selected", "false");
        li.tabIndex = -1;

        var contact = r.telefono || r.email || "";
        var next = r.prossimo_appuntamento_label
          ? '<span class="gs-next">Prossimo: ' + escapeHtml(r.prossimo_appuntamento_label) + "</span>"
          : '<span class="gs-next gs-next--muted">Nessun appuntamento futuro</span>';

        li.innerHTML =
          '<div class="gs-row">' +
          '<div class="gs-main">' +
          '<span class="gs-name">' +
          escapeHtml(r.nome_completo) +
          "</span>" +
          '<span class="gs-status gs-status--' +
          escapeHtml(r.stato) +
          '">' +
          escapeHtml(r.stato_label || r.stato) +
          "</span>" +
          "</div>" +
          '<div class="gs-meta">' +
          (contact ? '<span class="gs-contact">' + escapeHtml(contact) + "</span>" : "") +
          next +
          "</div>" +
          "</div>";

        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          goTo(i);
        });
        list.appendChild(li);
      });

      openPanel();
      setActive(0);
    }

    function escapeHtml(s) {
      return String(s || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function fetchResults(query) {
      if (abortCtrl) abortCtrl.abort();
      abortCtrl = new AbortController();
      var url = searchUrl + (searchUrl.indexOf("?") >= 0 ? "&" : "?") + "q=" + encodeURIComponent(query) + "&limit=8";

      fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: abortCtrl.signal,
      })
        .then(function (res) {
          if (!res.ok) throw new Error("search failed");
          return res.json();
        })
        .then(function (data) {
          render((data && data.results) || [], query);
        })
        .catch(function (err) {
          if (err && err.name === "AbortError") return;
          if (empty) {
            empty.hidden = false;
            empty.textContent = "Errore durante la ricerca. Riprova.";
          }
          list.innerHTML = "";
          openPanel();
        });
    }

    input.addEventListener("input", function () {
      var q = input.value.trim();
      clearTimeout(timer);
      if (q.length < MIN_LEN) {
        render([], q);
        return;
      }
      timer = setTimeout(function () {
        fetchResults(q);
      }, DEBOUNCE_MS);
    });

    input.addEventListener("focus", function () {
      if (input.value.trim().length >= MIN_LEN || items.length) {
        openPanel();
      } else {
        render([], "");
      }
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        closePanel();
        input.blur();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!items.length) return;
        setActive(activeIdx < 0 ? 0 : Math.min(items.length - 1, activeIdx + 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (!items.length) return;
        setActive(activeIdx <= 0 ? 0 : activeIdx - 1);
        return;
      }
      if (e.key === "Enter") {
        if (activeIdx >= 0) {
          e.preventDefault();
          goTo(activeIdx);
        }
      }
    });

    document.addEventListener("click", function (e) {
      if (!root.contains(e.target)) closePanel();
    });

    document.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        var tag = (e.target && e.target.tagName) || "";
        if (tag === "INPUT" || tag === "TEXTAREA" || (e.target && e.target.isContentEditable)) {
          if (e.target !== input) return;
        }
        e.preventDefault();
        input.focus();
        input.select();
        openPanel();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
