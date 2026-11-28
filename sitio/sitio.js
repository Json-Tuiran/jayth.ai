// Jayth · web del proyecto. Sin bibliotecas ni servicios de terceros: elige la descarga para el sistema del visitante,
// da movimiento a la portada y muestra la última versión publicada (API pública de GitHub). No guarda nada.
(function () {
  var doc = document.documentElement;
  doc.classList.add("js");
  var calma = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var REL = "https://github.com/Json-Tuiran/jayth.ai/releases/latest/download/";
  var es = (doc.lang || "es").slice(0, 2) === "es";
  var T = es ? {
    win: "Descargar para Windows", winS: "Instalador .exe · Windows 10/11",
    macA: "Descargar para Mac con chip Apple", macAS: ".dmg · M1 a M4",
    macI: "Mac con Intel", macIS: ".dmg",
    lin: "Descargar para Linux", linS: "AppImage · x86_64",
    mobile: "Jayth es una app de ordenador (Windows, macOS y Linux). Abre esta página en tu ordenador para descargarla.",
    ver: "Última versión: ", flo: "Descargar"
  } : {
    win: "Download for Windows", winS: ".exe installer · Windows 10/11",
    macA: "Download for Mac with Apple chip", macAS: ".dmg · M1 to M4",
    macI: "Mac with Intel", macIS: ".dmg",
    lin: "Download for Linux", linS: "AppImage · x86_64",
    mobile: "Jayth is a desktop app (Windows, macOS and Linux). Open this page on your computer to download it.",
    ver: "Latest version: ", flo: "Download"
  };
  var ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14"/></svg>';

  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // ---- descarga para el sistema del visitante
  var ua = navigator.userAgent || "";
  var plat = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "").toLowerCase();
  var mobile = /android|iphone|ipad|ipod/i.test(ua) || (plat.indexOf("mac") >= 0 && navigator.maxTouchPoints > 1);
  var os = mobile ? "mobile" : /win/.test(plat) || /windows/i.test(ua) ? "win" : /mac/.test(plat) || /mac os/i.test(ua) ? "mac"
    : /linux|x11|cros/.test(plat) || /linux/i.test(ua) ? "lin" : "";
  var MAIN = { win: "Jayth-Setup-x64.exe", mac: "Jayth-macos-arm64.dmg", lin: "Jayth-linux-x86_64.AppImage" };

  function button(cls, href, text, sub) {
    var a = document.createElement("a");
    a.className = "btn " + cls;
    a.href = REL + href;
    a.innerHTML = ICON + "<span>" + text + "<small>" + sub + "</small></span>";
    return a;
  }

  $$("[data-download]").forEach(function (box) {
    if (!os) return;                                  // sin saber el sistema se quedan los botones de la página
    box.innerHTML = "";
    if (os === "win") box.appendChild(button("btn-main", MAIN.win, T.win, T.winS));
    if (os === "mac") {
      box.appendChild(button("btn-main", MAIN.mac, T.macA, T.macAS));
      box.appendChild(button("btn-soft", "Jayth-macos-x64.dmg", T.macI, T.macIS));
    }
    if (os === "lin") box.appendChild(button("btn-main", MAIN.lin, T.lin, T.linS));
    if (os === "mobile") {
      var p = document.createElement("p");
      p.className = "lead";
      p.textContent = T.mobile;
      box.appendChild(p);
    }
    var gh = box.getAttribute("data-github");
    if (gh) {
      var a = document.createElement("a");
      a.className = "btn btn-soft";
      a.href = "https://github.com/Json-Tuiran/jayth.ai";
      a.textContent = gh;
      box.appendChild(a);
    }
  });
  if (MAIN[os]) $$("[data-direct]").forEach(function (a) { a.href = REL + MAIN[os]; });

  // ---- última versión
  var ver = document.querySelector("[data-version]");
  if (ver && window.fetch) {
    fetch("https://api.github.com/repos/Json-Tuiran/jayth.ai/releases/latest", { headers: { Accept: "application/vnd.github+json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && j.tag_name) ver.textContent = T.ver + j.tag_name.replace(/^v/, ""); })
      .catch(function () {});
  }

  // ---- el vídeo: quien pide menos movimiento lo ve parado, con sus controles
  if (calma) $$("video[autoplay]").forEach(function (v) { v.removeAttribute("autoplay"); v.pause(); v.controls = true; });

  // ---- lo que «le pides»: se escribe y se borra solo
  var typed = document.querySelector("[data-rotate]");
  if (typed) {
    var frases = JSON.parse(typed.getAttribute("data-rotate"));
    if (calma) typed.textContent = frases[0];
    else (function () {
      var i = 0, n = 0, borrando = false;
      function paso() {
        var f = frases[i];
        n += borrando ? -1 : 1;
        typed.textContent = f.slice(0, n);
        var espera = borrando ? 28 : 55;
        if (!borrando && n >= f.length) { borrando = true; espera = 1700; }
        else if (borrando && n <= 0) { borrando = false; i = (i + 1) % frases.length; espera = 350; }
        setTimeout(paso, espera);
      }
      typed.textContent = "";
      setTimeout(paso, 700);
    })();
  }

  // ---- aparecer al llegar, contadores y barras
  function contar(el) {
    var fin = parseFloat(el.getAttribute("data-count")), suf = el.getAttribute("data-suffix") || "";
    if (calma) { el.textContent = fin + suf; return; }
    var t0 = null, dur = 1300;
    function cuadro(t) {
      if (!t0) t0 = t;
      var k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(fin * e) + suf;
      if (k < 1) requestAnimationFrame(cuadro);
    }
    requestAnimationFrame(cuadro);
  }
  function llenar(root) { $$(".meter .fill", root).forEach(function (f) { f.style.width = f.style.getPropertyValue("--v") || f.getAttribute("data-v"); }); }

  var vistos = $$(".reveal, .steps, [data-count], .meter, .chat");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        el.classList.add("in");
        if (el.hasAttribute("data-count")) contar(el);
        if (el.classList.contains("meter")) llenar(el.parentNode);
        if (el.classList.contains("chat")) animarChat(el);
        io.unobserve(el);
      });
    }, { threshold: 0.18, rootMargin: "0px 0px -40px 0px" });
    vistos.forEach(function (el) { io.observe(el); });
  } else {
    vistos.forEach(function (el) { el.classList.add("in"); if (el.hasAttribute("data-count")) contar(el); });
    llenar(document);
    $$(".bubble li").forEach(function (li) { li.classList.add("on"); });
  }

  // ---- ejemplos: los pasos del agente van apareciendo, con «escribiendo…» antes
  function animarChat(chat) {
    var items = $$(".bubble li", chat), dots = chat.querySelector(".typing");
    if (calma || !items.length) { items.forEach(function (li) { li.classList.add("on"); }); if (dots) dots.remove(); return; }
    items.forEach(function (li) { li.classList.remove("on"); });
    if (dots) dots.style.display = "";
    var k = 0;
    setTimeout(function sig() {
      if (dots && k === 0) dots.style.display = "none";
      if (k < items.length) { items[k++].classList.add("on"); setTimeout(sig, 520); }
    }, 900);
  }

  // ---- pestañas accesibles (flechas para moverse)
  $$("[role='tablist']").forEach(function (lista) {
    var tabs = $$("[role='tab']", lista);
    function elegir(tab, foco) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        var p = document.getElementById(t.getAttribute("aria-controls"));
        if (!p) return;
        p.hidden = !on;
        if (on) {
          llenar(p);
          var chat = p.querySelector(".chat");
          if (chat) animarChat(chat);
        }
      });
      if (foco) tab.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { elegir(t, false); });
      t.addEventListener("keydown", function (e) {
        var j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
        if (j === null) return;
        e.preventDefault();
        elegir(tabs[(j + tabs.length) % tabs.length], true);
      });
    });
  });

  // ---- el vídeo se inclina un poco hacia el ratón (solo con ratón y sin «reducir movimiento»)
  var shot = document.querySelector(".shot");
  if (shot && !calma && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    var stage = shot.parentNode;
    stage.addEventListener("mousemove", function (e) {
      var r = stage.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      shot.style.transform = "rotateY(" + (x * 5).toFixed(2) + "deg) rotateX(" + (-y * 4).toFixed(2) + "deg)";
    });
    stage.addEventListener("mouseleave", function () { shot.style.transform = ""; });
  }

  // ---- botón de descarga que aparece al dejar atrás la portada (y se esconde en la sección de descargas)
  var flo = document.querySelector(".float-cta"), hero = document.querySelector(".hero"), dl = document.getElementById(es ? "descargar" : "download");
  if (flo && hero && "IntersectionObserver" in window) {
    var fuera = false, enDl = false;
    function pinta() { flo.classList.toggle("show", fuera && !enDl); }
    new IntersectionObserver(function (e) { fuera = !e[0].isIntersecting; pinta(); }, { threshold: 0 }).observe(hero);
    if (dl) new IntersectionObserver(function (e) { enDl = e[0].isIntersecting; pinta(); }, { threshold: 0 }).observe(dl);
  }
})();
