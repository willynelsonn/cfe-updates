// Camada de movimento do FolhaWeb (GSAP 3, ScrollTrigger).
//
// Tese de interação: "corporativo premium". A página entra uma vez, de baixo para cima,
// em cascata curta; números grandes contam até o valor; barras crescem a partir da base;
// a pílula escura da navegação desliza até o item sob o mouse. Nada se move sem motivo,
// nada fica em loop chamando atenção. Com "reduzir movimento" ligado, tudo aparece pronto.
//
// Curvas e tempos (skill motion-design, personalidade Corporate/Premium):
//   entrada  power3.out  0,55 s  cascata 0,06 s  deslocamento 18 px
//   números  power2.out  1,2 s
//   barras   power3.out  0,8 s
//   micro    power2.out  0,2 s
(function () {
  if (!window.gsap) return;
  var gsap = window.gsap;
  if (window.ScrollTrigger) gsap.registerPlugin(window.ScrollTrigger);
  gsap.defaults({ ease: "power3.out", duration: 0.55 });

  var raiz = document.documentElement;
  var mm = gsap.matchMedia();

  // ---- Formatação dos números (pt-BR) ------------------------------------------
  function formatar(v, tipo) {
    if (tipo === "inteiro") return Math.round(v).toLocaleString("pt-BR");
    if (tipo === "pct") return v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
    if (tipo === "compacto") {
      if (Math.abs(v) >= 1e6) return "R$ " + (v / 1e6).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " mi";
      if (Math.abs(v) >= 1e4) return "R$ " + (v / 1e3).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " mil";
    }
    return "R$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // ---- Pílula deslizante da navegação ----------------------------------------------
  function navegacao(animar) {
    var nav = document.querySelector("[data-pilulas]");
    if (!nav) return;
    var ind = nav.querySelector(".indicador");
    var itens = Array.prototype.slice.call(nav.querySelectorAll(":scope > a"));
    var ativo = nav.querySelector(":scope > a.ativo");
    nav.classList.add("pronto");
    function irPara(el, rapido) {
      itens.forEach(function (i) { i.classList.toggle("sob", i === el); });
      if (!el) { gsap.to(ind, { autoAlpha: 0, duration: 0.2 }); return; }
      var props = { x: el.offsetLeft, width: el.offsetWidth, autoAlpha: 1 };
      if (rapido || !animar) gsap.set(ind, props);
      else gsap.to(ind, Object.assign(props, { duration: 0.35, ease: "power3.out", overwrite: "auto" }));
    }
    irPara(ativo, true);
    itens.forEach(function (i) {
      i.addEventListener("pointerenter", function () { irPara(i); });
      i.addEventListener("focus", function () { irPara(i); });
    });
    nav.addEventListener("pointerleave", function () { irPara(ativo); });
    window.addEventListener("resize", function () { irPara(ativo, true); });
  }

  // ---- Título: palavras sobem de uma máscara ------------------------------------
  function revelarTitulo() {
    var h1 = document.querySelector(".conteudo .topo h1, .tela-login h1, .tela-login .lado h2");
    if (!h1 || h1.dataset.revelado) return;
    h1.dataset.revelado = "1";
    var palavras = [];
    (function quebrar(no) {
      Array.prototype.slice.call(no.childNodes).forEach(function (filho) {
        if (filho.nodeType === 3) {
          var frag = document.createDocumentFragment();
          filho.textContent.split(/(\s+)/).forEach(function (pedaco) {
            if (!pedaco) return;
            if (/^\s+$/.test(pedaco)) { frag.appendChild(document.createTextNode(pedaco)); return; }
            var masc = document.createElement("span");
            masc.style.cssText = "display:inline-block;overflow:hidden;vertical-align:top;padding-bottom:.08em;margin-bottom:-.08em";
            var p = document.createElement("span");
            p.style.display = "inline-block";
            p.textContent = pedaco;
            masc.appendChild(p); frag.appendChild(masc); palavras.push(p);
          });
          no.replaceChild(frag, filho);
        } else if (filho.nodeType === 1 && !filho.classList.contains("tag") && !filho.classList.contains("badge")) {
          quebrar(filho);
        }
      });
    })(h1);
    gsap.from(palavras, { yPercent: 110, duration: 0.7, ease: "power4.out", stagger: 0.05 });
  }

  // ---- Entrada da página em cascata + revelação ao rolar ------------------------------
  var SELETOR_BLOCOS = [
    ".conteudo > .msg", ".topo .subtitulo", ".topo .acoes", ".stepper", ".kpis > .kpi", ".bento > *",
    ".cols-2 > *", ".cols-meio > *", ".grid > *", ".acoes-grid > *", ".conteudo > .tabela",
    ".conteudo > .card", ".conteudo > form.card", ".conteudo > h2", ".conteudo > .explica", ".tela-login .caixa > *",
  ].join(",");

  function entrada() {
    var blocos = Array.prototype.slice.call(document.querySelectorAll(SELETOR_BLOCOS))
      .filter(function (el) { return !el.closest("[data-sem-animacao]"); });
    var altura = window.innerHeight;
    var visiveis = [], abaixo = [];
    blocos.forEach(function (el) { (el.getBoundingClientRect().top < altura * 0.95 ? visiveis : abaixo).push(el); });
    gsap.from(visiveis, { y: 18, autoAlpha: 0, stagger: 0.06, clearProps: "transform,opacity,visibility" });
    if (window.ScrollTrigger && abaixo.length) {
      gsap.set(abaixo, { y: 24, autoAlpha: 0 });
      window.ScrollTrigger.batch(abaixo, {
        start: "top bottom", once: true,
        onEnter: function (lote) { gsap.to(lote, { y: 0, autoAlpha: 1, stagger: 0.07, clearProps: "transform,opacity,visibility" }); },
      });
    }
  }

  // ---- Números que contam ---------------------------------------------------------
  function contadores() {
    document.querySelectorAll("[data-contar]").forEach(function (el) {
      var alvo = parseFloat(el.dataset.valor);
      if (isNaN(alvo)) return;
      var tipo = el.dataset.contar, obj = { v: 0 };
      var tween = gsap.to(obj, {
        v: alvo, duration: 1.2, ease: "power2.out", paused: true,
        onUpdate: function () { el.textContent = formatar(obj.v, tipo); },
      });
      el.textContent = formatar(0, tipo);
      if (window.ScrollTrigger) window.ScrollTrigger.create({ trigger: el, start: "top bottom", once: true, onEnter: function () { tween.play(); } });
      else tween.play();
    });
  }

  // ---- Barras crescem a partir da base ------------------------------------------------
  function barras() {
    var grupos = document.querySelectorAll(".barras-h, .seg-barra, .medidor");
    grupos.forEach(function (g) {
      var partes = g.querySelectorAll(".preenche, :scope > div");
      if (!partes.length) return;
      var tween = gsap.from(partes, { scaleX: 0, duration: 0.8, stagger: 0.05, paused: true, transformOrigin: "left center" });
      if (window.ScrollTrigger) window.ScrollTrigger.create({ trigger: g, start: "top bottom", once: true, onEnter: function () { tween.play(); } });
      else tween.play();
    });
  }

  // ---- Cartão laranja: brilho que acompanha o mouse --------------------------------------
  function brilho() {
    document.querySelectorAll(".cartao-laranja").forEach(function (c) {
      var x = gsap.quickTo(c, "--brilho-x", { duration: 0.6, ease: "power3" });
      var y = gsap.quickTo(c, "--brilho-y", { duration: 0.6, ease: "power3" });
      c.addEventListener("pointermove", function (ev) {
        var r = c.getBoundingClientRect();
        x(((ev.clientX - r.left) / r.width) * 100 + "%");
        y(((ev.clientY - r.top) / r.height) * 100 + "%");
      });
    });
  }

  // ---- Ícones das mensagens se desenham (sucesso, erro, aviso) ---------------------
  function mensagens() {
    document.querySelectorAll(".msg").forEach(function (m) {
      var tracos = m.querySelectorAll("svg use");
      gsap.from(m, { y: -8, autoAlpha: 0, duration: 0.35 });
      if (tracos.length) gsap.from(m.querySelector("svg"), { scale: 0.6, rotation: -20, duration: 0.45, ease: "back.out(2)", delay: 0.1 });
    });
  }

  // ---- API pública usada por app.js -----------------------------------------------------
  var permitido = false;
  window.FolhaMovimento = {
    surgir: function (el) { if (permitido) gsap.fromTo(el, { y: -6, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.2, ease: "power2.out" }); },
    listaEmCascata: function (nos) { if (permitido) gsap.from(nos, { x: -14, autoAlpha: 0, stagger: 0.025, duration: 0.3, ease: "power2.out" }); },
    formatar: formatar,
  };

  mm.add({ animar: "(prefers-reduced-motion: no-preference)", reduzir: "(prefers-reduced-motion: reduce)" }, function (ctx) {
    permitido = ctx.conditions.animar;
    navegacao(permitido);
    if (!permitido) return;
    revelarTitulo();
    entrada();
    contadores();
    barras();
    brilho();
    mensagens();
  });
  raiz.classList.remove("js-anima");
  // Fontes e imagens mudam a altura da página: recalcula os gatilhos depois de carregar.
  if (window.ScrollTrigger) {
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { window.ScrollTrigger.refresh(); });
    window.addEventListener("load", function () { window.ScrollTrigger.refresh(); });
  }
  // Impressão e "salvar como PDF": tudo visível, sem esperar a rolagem.
  window.addEventListener("beforeprint", function () {
    if (window.ScrollTrigger) window.ScrollTrigger.getAll().forEach(function (t) { if (t.animation) t.animation.progress(1); });
    gsap.set(document.querySelectorAll(SELETOR_BLOCOS), { clearProps: "transform,opacity,visibility" });
  });
})();
