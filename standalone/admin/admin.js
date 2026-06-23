(function () {
  "use strict";

  var NAV = [
    { id: "dashboard", label: "Dashboard", go: "dashboard" },
    { id: "pazienti", label: "Pazienti", go: "pazienti-lista" },
    { id: "agenda", label: "Agenda", go: "agenda-unificata" },
    { id: "economia", label: "Economia", go: "economia" },
    { id: "messaggi", label: "Messaggi", go: "broadcast-dashboard" },
    { id: "logout", label: "Logout", go: null, extraClass: "logout" }
  ];

  function renderNav(active) {
    var links = NAV.map(function (item) {
      var cls = "nav-link" + (item.id === active ? " active" : "") + (item.extraClass ? " " + item.extraClass : "");
      if (item.go) {
        return '<a href="#" data-go="' + item.go + '" class="' + cls + '">' + item.label + "</a>";
      }
      return '<a href="#" class="' + cls + '">' + item.label + "</a>";
    }).join("");

    return (
      '<nav class="navbar">' +
      '<div class="logo"><span class="logo-my">MyNutri</span><span class="logo-app">APP</span></div>' +
      '<button class="nav-toggle" type="button" aria-label="Menu">☰</button>' +
      '<div class="nav-links">' + links + "</div>" +
      "</nav>"
    );
  }

  function renderFooter() {
    return (
      '<footer class="footer">' +
      "© 2026 MyNutriAPP — Tutti i diritti riservati | " +
      '<span>Powered by <a href="#">Roberto Libanora</a></span>' +
      "</footer>"
    );
  }

  function showFlash(message, type) {
    var page = document.querySelector(".spa-page.is-active");
    if (!page) return;
    var wrap = page.querySelector(".flash-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "flash-wrap";
      page.insertBefore(wrap, page.firstChild);
    }
    var el = document.createElement("div");
    el.className = "flash flash--" + (type || "success");
    el.textContent = message;
    wrap.appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  }

  function initNav() {
    var toggle = document.querySelector(".nav-toggle");
    var links = document.querySelector(".nav-links");
    if (toggle && links) {
      toggle.addEventListener("click", function () {
        links.classList.toggle("open");
      });
    }
    document.querySelector(".nav-link.logout")?.addEventListener("click", function (e) {
      e.preventDefault();
      showFlash("Logout simulato — demo standalone senza backend.", "warning");
    });
  }

  function initForms() {
    document.querySelectorAll("form[data-mock]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var msg = form.getAttribute("data-success") || "Operazione simulata con successo.";
        showFlash(msg, "success");
        var redirect = form.getAttribute("data-redirect");
        if (redirect && window.goTo) {
          setTimeout(function () { window.goTo(redirect); }, 600);
        }
      });
    });
    document.querySelectorAll("[data-confirm]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        if (!confirm(el.getAttribute("data-confirm"))) e.preventDefault();
      });
    });
  }

  function initPatientCards() {
    document.querySelectorAll(".patient-card[data-go]").forEach(function (card) {
      card.addEventListener("click", function (e) {
        if (e.target.closest("a, button")) return;
        if (window.goTo) window.goTo(card.getAttribute("data-go"));
      });
    });
  }

  window.showTab = function (tabId, btn) {
    var page = document.querySelector(".spa-page.is-active");
    if (!page) return;
    page.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
    page.querySelectorAll(".tab-btn").forEach(function (b) { b.classList.remove("active"); });
    var panel = page.querySelector("#" + tabId + "-tab");
    if (panel) panel.classList.add("active");
    if (btn) btn.classList.add("active");
  };

  window.toggleTrigger = function (btn) {
    var on = btn.classList.contains("btn-on");
    btn.classList.toggle("btn-on", !on);
    btn.classList.toggle("btn-off", on);
    btn.textContent = on ? "● OFF" : "● ON";
    showFlash("Trigger " + (on ? "disattivato" : "attivato") + " (simulazione).", "success");
  };

  function initDateTime() {
    var days = ["Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"];
    var months = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];
    function tick() {
      var now = new Date();
      var dateStr = days[now.getDay()] + ", " + now.getDate() + " " + months[now.getMonth()] + " " + now.getFullYear();
      var timeStr = now.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
      document.querySelectorAll(".live-date").forEach(function (el) { el.textContent = dateStr; });
      document.querySelectorAll(".live-time").forEach(function (el) { el.textContent = timeStr; });
    }
    tick();
    setInterval(tick, 30000);
  }

  function mountChrome() {
    var navHost = document.getElementById("site-nav");
    var footerHost = document.getElementById("site-footer");
    if (navHost) navHost.innerHTML = renderNav(document.body.getAttribute("data-nav") || "dashboard");
    if (footerHost) footerHost.innerHTML = renderFooter();
    initNav();
  }

  window.__spaAfterNav = function () {
    mountChrome();
  };

  document.addEventListener("DOMContentLoaded", function () {
    mountChrome();
    initForms();
    initPatientCards();
    initDateTime();
  });

  window.adminFlash = showFlash;
})();
