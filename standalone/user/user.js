(function () {
  "use strict";

  var USER_NAME = "Marco";

  var BOTTOM_NAV = [
    { id: "home", label: "Home", icon: "🏠", go: "home" },
    { id: "progressi", label: "Progressi", icon: "📈", go: "progressi-lista" },
    { id: "prenota", label: "Prenota", icon: "📅", go: "appuntamenti-lista" },
    { id: "profilo", label: "Profilo", icon: "👤", go: "profilo" }
  ];

  function renderHeader() {
    var initial = USER_NAME.charAt(0).toUpperCase();
    return (
      '<header class="user-header">' +
      '<div class="user-header-content">' +
      '<div class="user-greeting">' +
      '<span class="user-greeting-text">Ciao,</span>' +
      '<span class="user-name">' + USER_NAME + "</span>" +
      "</div>" +
      '<a href="#" data-go="profilo" class="user-avatar">' + initial + "</a>" +
      "</div></header>"
    );
  }

  function renderBottomNav(active) {
    var items = BOTTOM_NAV.map(function (item) {
      var cls = "nav-item" + (item.id === active ? " active" : "");
      return (
        '<a href="#" data-go="' + item.go + '" class="' + cls + '">' +
        '<span class="nav-icon">' + item.icon + "</span>" +
        '<span class="nav-label">' + item.label + "</span></a>"
      );
    }).join("");
    return '<nav class="bottom-nav">' + items + "</nav>";
  }

  function renderPoweredBy() {
    return (
      '<div class="powered-by">' +
      'Powered by <a href="#">Roberto Libanora</a>' +
      "</div>"
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

  function initForms() {
    document.querySelectorAll("form[data-mock]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var msg = form.getAttribute("data-success") || "Operazione completata (simulazione).";
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
    var logout = document.querySelector("[data-logout]");
    if (logout) {
      logout.addEventListener("click", function (e) {
        e.preventDefault();
        if (confirm("Uscire dall'app?")) {
          showFlash("Logout simulato — demo standalone senza backend.", "warning");
        }
      });
    }
  }

  function mountChrome() {
    var active = document.body.getAttribute("data-nav") || "home";
    var headerHost = document.getElementById("site-header");
    var navHost = document.getElementById("site-bottom-nav");
    var poweredHost = document.getElementById("site-powered");
    if (headerHost) headerHost.innerHTML = renderHeader();
    if (navHost) navHost.innerHTML = renderBottomNav(active);
    if (poweredHost) poweredHost.innerHTML = renderPoweredBy();
  }

  window.__spaAfterNav = function () {
    mountChrome();
  };

  document.addEventListener("DOMContentLoaded", function () {
    mountChrome();
    initForms();
  });

  window.userFlash = showFlash;
})();
