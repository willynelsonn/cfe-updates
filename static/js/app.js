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
    var linhas = [];
    if (s.erro) linhas.push("⚠ " + s.erro);
    else if (andamento) linhas.push("Enviando ao eSocial…");
    else linhas.push("eSocial em dia");
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
