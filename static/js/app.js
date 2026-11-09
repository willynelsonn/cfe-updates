// Comportamentos globais do FolhaWeb (sem dependências externas).
(function () {
  // Confirmação antes de ações importantes: <form data-confirmar="Texto">
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    var msg = form.getAttribute("data-confirmar");
    if (msg && !window.confirm(msg)) { ev.preventDefault(); return; }
    // Evita clique duplo e mostra que está processando
    form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (b) {
      b.classList.add("ocupado");
      if (b.dataset.ocupado) b.textContent = b.dataset.ocupado;
    });
  });

  // Título da página na barra superior (quando o template não definiu)
  var migalha = document.querySelector(".migalha strong");
  if (migalha && !migalha.textContent.trim()) migalha.textContent = document.title.split(" · ")[0];

  // Menu lateral no celular
  var sidebar = document.getElementById("sidebar");
  document.querySelectorAll("[data-abrir-menu]").forEach(function (b) {
    b.addEventListener("click", function () { sidebar.classList.toggle("aberta"); });
  });
  document.addEventListener("click", function (ev) {
    if (sidebar && sidebar.classList.contains("aberta") && !sidebar.contains(ev.target) && !ev.target.closest("[data-abrir-menu]"))
      sidebar.classList.remove("aberta");
  });

  // Tema claro/escuro (respeita o sistema até o usuário escolher)
  document.querySelectorAll("[data-tema]").forEach(function (b) {
    b.addEventListener("click", function () {
      var raiz = document.documentElement;
      var escuroAgora = raiz.dataset.theme ? raiz.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      raiz.dataset.theme = escuroAgora ? "light" : "dark";
      try { localStorage.setItem("tema", raiz.dataset.theme); } catch (e) {}
      document.dispatchEvent(new Event("tema-alterado"));
    });
  });

  // Status do eSocial: processa a fila automaticamente enquanto houver algo em andamento.
  var caixa = document.getElementById("status-esocial");
  if (!caixa) return;
  var urlProcessar = caixa.dataset.processar, urlSituacao = caixa.dataset.situacao;
  var csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
  var recarregar = caixa.dataset.recarregar === "1";
  var ultimo = null;

  function mostrar(s) {
    var andamento = (s.pendentes || 0) + (s.enviados || 0);
    caixa.classList.toggle("trabalhando", andamento > 0 && !s.erro);
    caixa.classList.toggle("erro", !!s.erro || (s.problemas || 0) > 0);
    var linhas = [];
    if (s.erro) linhas.push("<b>eSocial pausado</b>: " + s.erro.replace(/[<>&]/g, ""));
    else if (andamento) linhas.push("<b>Enviando ao eSocial…</b>");
    else linhas.push("<b>eSocial em dia</b>");
    linhas.push("Na fila: " + (s.pendentes || 0) + " · Com o governo: " + (s.enviados || 0));
    linhas.push("Aceitos: " + (s.aceitos || 0) + (s.problemas ? " · Com erro: " + s.problemas : ""));
    caixa.querySelector(".texto").innerHTML = linhas.join("<br>");
    var chave = [s.pendentes, s.enviados, s.aceitos, s.problemas].join("/");
    if (recarregar && ultimo !== null && chave !== ultimo && !andamento) window.location.reload();
    ultimo = chave;
    return andamento > 0 && !s.erro;
  }

  function ciclo() {
    fetch(urlProcessar, { method: "POST", headers: { "X-CSRFToken": csrf }, credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (s) { if (mostrar(s)) setTimeout(ciclo, 15000); })
      .catch(function () { setTimeout(ciclo, 30000); });
  }

  fetch(urlSituacao, { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (s) {
    if (mostrar(s)) setTimeout(ciclo, 3000);
  });
})();
