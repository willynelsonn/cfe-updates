// Gráficos do FolhaWeb em SVG puro (sem bibliotecas externas).
// Especificação: barras <= 24px com topo arredondado de 4px, 2px de espaço entre segmentos,
// grade recessiva, eixo único, tooltip em hover/foco e tabela equivalente para acessibilidade.
(function () {
  var NS = "http://www.w3.org/2000/svg";

  function cor(nome) { return getComputedStyle(document.documentElement).getPropertyValue(nome).trim() || nome; }
  function el(tag, attrs, pai) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (pai) pai.appendChild(e);
    return e;
  }
  function moeda(v) {
    return "R$ " + Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function compacto(v) {
    if (Math.abs(v) >= 1e6) return "R$ " + (v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mi";
    if (Math.abs(v) >= 1e3) return "R$ " + (v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " mil";
    return "R$ " + Math.round(v);
  }
  function passoBonito(max, n) {
    if (max <= 0) return 1;
    var bruto = max / n, pot = Math.pow(10, Math.floor(Math.log10(bruto))), r = bruto / pot;
    return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 2.5 ? 2.5 : r <= 5 ? 5 : 10) * pot;
  }
  function dados(caixa) { return JSON.parse(document.getElementById(caixa.dataset.fonte).textContent); }

  // Caminho de barra com topo arredondado e base reta
  function caminhoBarra(x, y, w, h, raio) {
    raio = Math.min(raio, h, w / 2);
    if (h <= 0) return "";
    return "M" + x + "," + (y + h) + "V" + (y + raio) + "Q" + x + "," + y + " " + (x + raio) + "," + y +
      "H" + (x + w - raio) + "Q" + (x + w) + "," + y + " " + (x + w) + "," + (y + raio) + "V" + (y + h) + "Z";
  }

  function tooltip(caixa) {
    var t = caixa.querySelector(".dica-grafico");
    if (!t) { t = document.createElement("div"); t.className = "dica-grafico"; caixa.appendChild(t); }
    return t;
  }
  function mostrarDica(caixa, t, titulo, linhas, x, y) {
    t.textContent = "";
    var h = document.createElement("div"); h.className = "titulo"; h.textContent = titulo; t.appendChild(h);
    linhas.forEach(function (l) {
      var d = document.createElement("div"); d.className = "linha";
      var esq = document.createElement("span");
      if (l.cor) { var i = document.createElement("i"); i.style.background = l.cor; esq.appendChild(i); esq.append(" "); }
      esq.append(l.nome);
      var b = document.createElement("b"); b.textContent = l.valor;
      d.appendChild(esq); d.appendChild(b); t.appendChild(d);
    });
    t.style.display = "block";
    var larg = caixa.clientWidth, tw = t.offsetWidth;
    t.style.left = Math.max(0, Math.min(x + 12, larg - tw)) + "px";
    t.style.top = Math.max(0, y - 10) + "px";
  }

  function colunasEmpilhadas(caixa) {
    var d = dados(caixa), series = d.series, pontos = d.pontos;
    caixa.querySelectorAll("svg").forEach(function (s) { s.remove(); });
    var W = Math.max(caixa.clientWidth, 280), H = 250, m = { t: 10, r: 8, b: 26, l: 64 };
    var iw = W - m.l - m.r, ih = H - m.t - m.b;
    var totais = pontos.map(function (p) {
      return series.reduce(function (s, se) { return s + (p.valores[se.chave] || 0); }, 0);
    });
    var max = Math.max.apply(null, totais.concat([1]));
    var passo = passoBonito(max, 4), topo = Math.ceil(max / passo) * passo;
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": d.titulo || "" });
    caixa.insertBefore(svg, caixa.firstChild);
    var grade = el("g", { "class": "grade" }, svg), eixo = el("g", { "class": "eixo" }, svg);
    for (var v = 0; v <= topo + 1e-9; v += passo) {
      var y = m.t + ih - (v / topo) * ih;
      if (v > 0) el("line", { x1: m.l, x2: W - m.r, y1: y, y2: y }, grade);
      var tx = el("text", { x: m.l - 8, y: y + 4, "text-anchor": "end" }, eixo); tx.textContent = compacto(v);
    }
    el("line", { "class": "base", x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih }, svg);
    var banda = iw / pontos.length, bw = Math.min(24, banda * 0.55);
    var dica = tooltip(caixa), mostrarRotulo = banda >= 34 ? 1 : 2;
    pontos.forEach(function (p, i) {
      var cx = m.l + banda * i + banda / 2, x = cx - bw / 2, base = m.t + ih;
      var g = el("g", { "class": "marca", tabindex: "0" }, svg);
      var segs = series.filter(function (se) { return p.valores[se.chave]; });
      segs.forEach(function (se, k) {
        var h = (p.valores[se.chave] / topo) * ih;
        var gap = k < segs.length - 1 ? 2 : 0, alt = Math.max(h - gap, 0.5);
        var y = base - h;
        var forma = k === segs.length - 1
          ? el("path", { d: caminhoBarra(x, y, bw, alt, 4) }, g)
          : el("rect", { x: x, y: y + gap, width: bw, height: alt }, g);
        forma.setAttribute("fill", cor(se.cor));
        base -= h;
      });
      if (!segs.length) {
        var s = el("text", { x: cx, y: m.t + ih - 6, "text-anchor": "middle", "class": "eixo" }, svg);
        s.textContent = "–";
        s.setAttribute("fill", cor("--muted"));
      }
      if (i % mostrarRotulo === 0 || i === pontos.length - 1) {
        var r = el("text", { x: cx, y: H - 6, "text-anchor": "middle" }, eixo); r.textContent = p.rotulo;
      }
      var alvo = el("rect", { x: m.l + banda * i, y: m.t, width: banda, height: ih, fill: "transparent", "class": "alvo" }, g);
      function abrir(ev) {
        var linhas = series.slice().reverse().map(function (se) {
          var val = p.valores[se.chave];
          return { nome: se.nome, valor: val == null ? "—" : moeda(val), cor: cor(se.cor) };
        });
        linhas.push({ nome: "Total", valor: totais[i] ? moeda(totais[i]) : "sem folha calculada" });
        var ret = caixa.getBoundingClientRect();
        var px = ev && ev.clientX ? ev.clientX - ret.left : (cx / W) * caixa.clientWidth;
        mostrarDica(caixa, dica, p.rotulo, linhas, px, 0);
        alvo.setAttribute("fill", cor("--surface-3")); alvo.setAttribute("fill-opacity", ".5");
        g.insertBefore(alvo, g.firstChild);
      }
      function fechar() { dica.style.display = "none"; alvo.setAttribute("fill", "transparent"); }
      g.addEventListener("pointermove", abrir); g.addEventListener("focus", abrir);
      g.addEventListener("pointerleave", fechar); g.addEventListener("blur", fechar);
    });
    animarColunas(caixa, svg, m.t + ih);
  }

  // Primeira exibição: as colunas crescem a partir da linha de base (GSAP), uma vez só.
  function animarColunas(caixa, svg, baseY) {
    if (caixa.dataset.animado || !window.gsap) return;
    caixa.dataset.animado = "1";
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var grupos = svg.querySelectorAll("g.marca");
    var tween = window.gsap.from(grupos, {
      scaleY: 0, duration: 0.8, ease: "power3.out", stagger: 0.04, paused: true,
      svgOrigin: function (i, alvo) { var b = alvo.getBBox(); return (b.x + b.width / 2) + " " + baseY; },
    });
    if (window.ScrollTrigger) window.ScrollTrigger.create({ trigger: caixa, start: "top bottom", once: true, onEnter: function () { tween.play(); } });
    else tween.play();
  }

  function sparkline(caixa) {
    var valores = dados(caixa);
    caixa.querySelectorAll("svg").forEach(function (s) { s.remove(); });
    var W = Math.max(caixa.clientWidth, 100), H = 34, p = 4;
    var max = Math.max.apply(null, valores), min = Math.min.apply(null, valores);
    if (max === min) { max += 1; min -= 1; }
    var pts = valores.map(function (v, i) {
      return [p + (i / (valores.length - 1 || 1)) * (W - 2 * p), H - p - ((v - min) / (max - min)) * (H - 2 * p)];
    });
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, "class": "sparkline", "aria-hidden": "true" });
    caixa.appendChild(svg);
    el("polyline", { points: pts.map(function (q) { return q.join(","); }).join(" "), fill: "none",
      stroke: cor("--axis"), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    var u = pts[pts.length - 1];
    el("circle", { cx: u[0], cy: u[1], r: 4, fill: cor("--s1"), stroke: cor("--surface"), "stroke-width": 2 }, svg);
  }

  function desenhar() {
    document.querySelectorAll("[data-grafico='colunas']").forEach(colunasEmpilhadas);
    document.querySelectorAll("[data-grafico='sparkline']").forEach(sparkline);
  }
  var espera;
  window.addEventListener("resize", function () { clearTimeout(espera); espera = setTimeout(desenhar, 120); });
  document.addEventListener("tema-alterado", desenhar);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", desenhar);
  desenhar();
})();
