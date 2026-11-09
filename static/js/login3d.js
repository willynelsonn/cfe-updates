// Cena da tela de login (Three.js r170): um campo de pontos em onda, laranja ao fundo e claro à frente,
// que respira devagar e acompanha o mouse com leve paralaxe. Uma cena só, leve (~7 mil pontos, 1 draw call).
// Com "reduzir movimento", desenha um quadro parado. Pausa sozinha com a aba em segundo plano.
import * as THREE from "../vendor/three/three.module.min.js";

const tela = document.querySelector("[data-cena-login]");
if (tela) {
  const reduzir = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  tela.appendChild(renderer.domElement);

  const cena = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 3.2, 9);
  camera.lookAt(0, 0, 0);

  const COLS = 140, LINHAS = 52, LARG = 22, PROF = 10;
  const total = COLS * LINHAS;
  const pos = new Float32Array(total * 3);
  const cores = new Float32Array(total * 3);
  const base = new Float32Array(total * 2);
  const corFundo = new THREE.Color("#c2410c"), corFrente = new THREE.Color("#ffd2bd"), c = new THREE.Color();
  for (let j = 0, k = 0; j < LINHAS; j++) {
    for (let i = 0; i < COLS; i++, k++) {
      const x = (i / (COLS - 1) - 0.5) * LARG, z = (j / (LINHAS - 1) - 0.5) * PROF;
      base[k * 2] = x; base[k * 2 + 1] = z;
      pos[k * 3] = x; pos[k * 3 + 2] = z;
      c.copy(corFundo).lerp(corFrente, j / (LINHAS - 1));
      cores[k * 3] = c.r; cores[k * 3 + 1] = c.g; cores[k * 3 + 2] = c.b;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(cores, 3));
  const mat = new THREE.PointsMaterial({ size: 0.055, vertexColors: true, transparent: true, opacity: 0.9, depthWrite: false });
  const pontos = new THREE.Points(geo, mat);
  cena.add(pontos);

  function ajustar() {
    const w = tela.clientWidth, h = tela.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  ajustar();
  new ResizeObserver(ajustar).observe(tela);

  const mouse = { x: 0, y: 0 }, alvo = { x: 0, y: 0 };
  tela.parentElement.addEventListener("pointermove", (ev) => {
    const r = tela.getBoundingClientRect();
    alvo.x = ((ev.clientX - r.left) / r.width - 0.5) * 2;
    alvo.y = ((ev.clientY - r.top) / r.height - 0.5) * 2;
  });

  const relogio = new THREE.Clock();
  function quadro() {
    const t = reduzir ? 2 : relogio.getElapsedTime();
    const p = geo.attributes.position.array;
    for (let k = 0; k < total; k++) {
      const x = base[k * 2], z = base[k * 2 + 1];
      p[k * 3 + 1] = Math.sin(x * 0.45 + t * 0.6) * 0.45 + Math.cos(z * 0.6 + t * 0.4) * 0.35 + Math.sin((x + z) * 0.2 + t * 0.3) * 0.25;
    }
    geo.attributes.position.needsUpdate = true;
    mouse.x += (alvo.x - mouse.x) * 0.04;
    mouse.y += (alvo.y - mouse.y) * 0.04;
    camera.position.x = mouse.x * 0.8;
    camera.position.y = 3.2 - mouse.y * 0.5;
    camera.lookAt(0, 0, 0);
    renderer.render(cena, camera);
  }
  if (reduzir) quadro(); else renderer.setAnimationLoop(quadro);

  addEventListener("pagehide", () => { renderer.setAnimationLoop(null); geo.dispose(); mat.dispose(); renderer.dispose(); });
}
