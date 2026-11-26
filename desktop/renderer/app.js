// SiftBase desktop renderer. Plain ES module; three.js, GSAP and Lenis ship in node_modules.
// Everything outside the page (API, keys, files) goes through window.sift (preload.js).
import * as THREE from '../node_modules/three/build/three.module.js';

const gsap = window.gsap;
const sift = window.sift;
const EMPTY = { id: '', name: 'No collection yet', docs: [], run: null, empty: true };
let COLLS = [];
const $ = (s) => document.querySelector(s);
const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const lerp = (a, b, u) => a + (b - a) * u;
const fmt = (n) => (n == null ? '–' : Number(n).toLocaleString('en-US'));
const secs = (ms) => (ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : ms > 0 ? Math.round(ms) + ' ms' : '<1 ms');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const midTrim = (s, n = 34) => (s.length <= n ? s : s.slice(0, Math.ceil(n * 0.6) - 1) + '…' + s.slice(-Math.floor(n * 0.4)));
const pagesOf = (c) => c.docs.reduce((a, d) => a + d.pages, 0);
function rng(seed) { let s = seed % 2147483647 || 1; return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646; }

const S = { screen: 'home', coll: EMPTY, t: 0, playing: false, mode: 'idle', drawerOpen: false,
  api: 'starting', apiError: '', keys: null, dataDir: '', indexing: null, capacityUntil: 0 };

// ---------------------------------------------------------------- scene
const main = $('#main');
const canvas = $('#scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene();
const BG = new THREE.Color('#0B0D12');
scene.background = BG;
scene.fog = new THREE.Fog(BG, 17, 36);
const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
const cam = { x: 0, y: 6.6, z: 10.2, tx: 0, ty: 0.55, tz: 0.2, ox: 0, oy: 28 };
const par = { x: 0, y: 0, mx: 0, my: 0 };

scene.add(new THREE.HemisphereLight(0xc9d4ff, 0x0b0d12, 0.6));
const key = new THREE.DirectionalLight(0xf3f5ff, 2.3);
key.position.set(3, 12, 7);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -11, right: 11, top: 11, bottom: -11, near: 1, far: 40 });
key.shadow.bias = -0.0004;
key.shadow.radius = 5;
scene.add(key);
const rim = new THREE.DirectionalLight(0x8fb8ff, 0.4);
rim.position.set(-6, 4, -8);
scene.add(rim);
const table = new THREE.Mesh(new THREE.PlaneGeometry(90, 90), new THREE.MeshStandardMaterial({ color: 0x12151c, roughness: 0.97 }));
table.rotation.x = -Math.PI / 2;
table.receiveShadow = true;
scene.add(table);

const PAPER = new THREE.Color('#EEE9DD'), DIM = new THREE.Color('#55565B'), HL = new THREE.Color('#D8F25B');
const stackMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9 });
stackMat.onBeforeCompile = (s) => {
  // Fine page lines on the sides of each stack, from world height.
  s.vertexShader = s.vertexShader
    .replace('#include <common>', '#include <common>\nvarying float vSide;\nvarying float vWy;')
    .replace('#include <worldpos_vertex>', `#include <worldpos_vertex>
      { vec4 p = vec4(transformed, 1.0);
      #ifdef USE_INSTANCING
        p = instanceMatrix * p;
      #endif
        p = modelMatrix * p; vWy = p.y; vSide = 1.0 - step(0.5, abs(objectNormal.y)); }`);
  s.fragmentShader = s.fragmentShader
    .replace('#include <common>', '#include <common>\nvarying float vSide;\nvarying float vWy;')
    .replace('#include <color_fragment>', `#include <color_fragment>
      { float l = abs(fract(vWy * 70.0) - 0.5) * 2.0;
        diffuseColor.rgb *= mix(1.0, 0.8 + 0.12 * smoothstep(0.2, 0.8, l), vSide); }`);
};
const sheetMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.85, side: THREE.DoubleSide });
const boxGeo = new THREE.BoxGeometry(1, 1, 1);
boxGeo.translate(0, 0.5, 0);
const SW = 0.56, SD = 0.78;
const sheetGeo = new THREE.PlaneGeometry(SW, SD); sheetGeo.rotateX(-Math.PI / 2);
const stripGeo = new THREE.PlaneGeometry(0.52, 0.1); stripGeo.rotateX(-Math.PI / 2);
const CAP = { sheets: 240, picked: 24, strips: 120, kept: 40, cited: 24, free: 90 };

function instanced(geo, mat, n) {
  const m = new THREE.InstancedMesh(geo, mat, n);
  m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false;
  for (let i = 0; i < n; i++) m.setColorAt(i, PAPER);
  m.count = 0; scene.add(m); return m;
}
const sheets = instanced(sheetGeo, sheetMat, CAP.sheets);
const strips = instanced(stripGeo, sheetMat, CAP.strips);
const free = instanced(sheetGeo, sheetMat, CAP.free);
let stacks = null;

function canvasPlane(w, h, cw, ch) {
  const c = document.createElement('canvas'); c.width = cw; c.height = ch;
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  const geo = new THREE.PlaneGeometry(w, h); geo.rotateX(-Math.PI / 2);
  const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: tex, roughness: 0.85, side: THREE.DoubleSide }));
  mesh.castShadow = true; mesh.visible = false; scene.add(mesh);
  return { mesh, c, g: c.getContext('2d'), tex };
}
const answerPage = canvasPlane(1.3, 1.78, 390, 534);
const scan = new THREE.Mesh(new THREE.BoxGeometry(0.025, 1.5, 0.025), new THREE.MeshBasicMaterial({ color: 0x8fb8ff, transparent: true }));
scan.visible = false; scene.add(scan);

const P = { // fixed places on the front of the table
  answer: new THREE.Vector3(0.1, 1.05, 2.45), kept: new THREE.Vector3(-2.6, 0, 2.75), cited: new THREE.Vector3(2.3, 0, 2.55),
  scan: new THREE.Vector3(0, 0.9, 2.75), drop: new THREE.Vector3(0, 2.4, 1.4),
};
const SC = { cloud: 0.8, fan: 0.72, cited: 0.8 }; // sheet sizes away from the stacks

// ---------------------------------------------------------------- layout: any collection size
function layout(docs) {
  const n = docs.length, maxP = Math.max(1, ...docs.map((d) => d.pages));
  const big = n > 80;
  const fp = n <= 12 ? 1 : big ? 0.62 : 0.8;
  // Reams, not cubes: the tallest stack is about two-thirds of its own depth.
  const hMax = big ? 0.3 : n <= 12 ? 0.62 : 0.5;
  const H = (p) => 0.025 + hMax * Math.log1p(Math.max(0, p)) / Math.log1p(maxP);
  const order = docs.map((_, i) => i).sort((a, b) => docs[b].pages - docs[a].pages);
  const st = new Array(n);
  if (!big) {
    const caps = []; let left = n, r = 0;
    while (left > 0) { const c = n <= 12 ? n : Math.min(left, 9 + 5 * r); caps.push(c); left -= c; r++; }
    const cz = 2.4, R0 = n <= 12 ? Math.max(2.6, 1.0 + n * 0.3) : 3.5, gap = 0.74 * fp;
    let k = 0;
    for (let r = caps.length - 1; r >= 0; r--) { // biggest documents on the outer, back row
      const c = caps[r], R = R0 + r * 1.2 * fp, span = Math.min(2.5, (c - 1) * gap / R);
      const angles = Array.from({ length: c }, (_, j) => (c > 1 ? -span / 2 + (span * j) / (c - 1) : 0)).sort((a, b) => Math.abs(a) - Math.abs(b));
      for (let j = 0; j < c; j++, k++) {
        const i = order[k], a = angles[j];
        st[i] = { x: R * Math.sin(a), z: cz - R * Math.cos(a), rot: -a, w: SW * fp, d: SD * fp, h: H(docs[i].pages) };
      }
    }
  } else {
    const cols = Math.ceil(Math.sqrt(n * 2.4)), rows = Math.ceil(n / cols), cx = 0.5, czs = 0.62, back = -0.6 - (rows - 1) * czs;
    for (let k = 0; k < n; k++) {
      const i = order[k], r = Math.floor(k / cols), c = k % cols;
      st[i] = { x: (c - (cols - 1) / 2) * cx, z: back + r * czs, rot: 0, w: SW * fp, d: SD * fp, h: H(docs[i].pages) };
    }
  }
  return { st, H, big, n, fp };
}
let L = null;

const VIEWS = {
  ask: (l) => (l.big ? { x: 0, y: 10.4, z: 12.4, tx: 0, ty: 0, tz: -1.3 } : { x: 0, y: 6.6, z: 10.2, tx: 0, ty: 0.55, tz: 0.2 }),
  // The library sees only the strip between its two side panels, so it sits further back.
  library: (l) => (l.big ? { x: 0, y: 17, z: 11.5, tx: 0, ty: 0, tz: -3.4 } : l.n <= 12 ? { x: 0, y: 8.2, z: 12.2, tx: 0, ty: 0.5, tz: -1.0 } : { x: 0, y: 11, z: 12, tx: 0, ty: 0.3, tz: -2.0 }),
};
const HOME_VIEW = { x: 0.3, y: 2.3, z: 7.8, tx: 0.2, ty: 1.15, tz: 0.4 };
function moveCamera(instant) {
  let v;
  if (S.screen === 'home') { gsap.killTweensOf(cam); if (instant) Object.assign(cam, HOME_VIEW, { ox: Math.round(main.clientWidth * 0.235), oy: 0 }); return; } // the scroll drives it
  else {
    v = { ...VIEWS[S.screen === 'library' ? 'library' : 'ask'](L) };
    v.ox = S.screen === 'library' ? 20 : S.drawerOpen ? 232 : 0;
    v.oy = S.screen === 'library' ? 0 : 30;
  }
  if (instant || RM) Object.assign(cam, v); else gsap.to(cam, { ...v, duration: 1.1, ease: 'expo.inOut', overwrite: true });
}

function buildStacks(col) {
  if (stacks) { scene.remove(stacks); stacks.dispose(); }
  L = layout(col.docs);
  stacks = new THREE.InstancedMesh(boxGeo, stackMat, Math.max(1, L.n));
  stacks.count = L.n;
  stacks.castShadow = stacks.receiveShadow = !L.big;
  for (let i = 0; i < L.n; i++) stacks.setColorAt(i, PAPER);
  scene.add(stacks);
}

// ---------------------------------------------------------------- the run: built from a real response
let run = null;
function buildRun(col) {
  const r = col.run, rnd = rng(97 + col.docs.length);
  const idx = new Map(col.docs.map((d, i) => [d.name, i]));
  const routed = r.routed.map((n) => idx.get(n)).filter((i) => i != null);
  if (!routed.length) routed.push(0); // the collection was re-indexed since this answer: its documents changed
  const nS = Math.min(r.candidates, CAP.sheets), nP = Math.max(1, Math.min(r.picked, CAP.picked, nS));
  const nC = Math.min(r.cited.length, nP, CAP.cited), fanW = Math.min(4.2, nP * 0.24);
  const pickAt = new Map(); for (let j = 0; j < nP; j++) pickAt.set(Math.floor(((j + 0.5) * nS) / nP), j);
  const fan = [];
  const sh = Array.from({ length: nS }, (_, k) => {
    const doc = routed[k % routed.length], a = L.st[doc];
    const ang = rnd() * Math.PI * 2, rad = Math.sqrt(rnd());
    const j = pickAt.has(k) ? pickAt.get(k) : -1;
    const s = {
      k, doc, j, cited: j >= 0 && j < nC ? j : -1, ry: a.rot,
      A: new THREE.Vector3(a.x + (rnd() - 0.5) * 0.04, 0, a.z + (rnd() - 0.5) * 0.04),
      B: new THREE.Vector3(Math.cos(ang) * rad * 3.4, 1.35 + rnd() * 0.75, 0.5 + Math.sin(ang) * rad * 1.2),
      cr: new THREE.Vector3((rnd() - 0.5) * 1.3, rnd() * 6.28, (rnd() - 0.5) * 0.8),
    };
    if (j >= 0) {
      const u = nP > 1 ? j / (nP - 1) : 0.5;
      // A hand of cards: overlapping, turned out from a common centre.
      s.C = new THREE.Vector3((u - 0.5) * fanW, 0.75 + Math.sin(u * Math.PI) * 0.18 + j * 0.004, 1.75 + j * 0.01 - Math.abs(u - 0.5) * 0.3);
      s.fr = new THREE.Vector3(0.75, 0, -(u - 0.5) * 0.7);
      fan[j] = s;
    }
    return s;
  });
  const nR = Math.min(r.passages, CAP.strips), nK = Math.min(r.kept, CAP.kept, nR);
  const ranks = Array.from({ length: nR }, (_, i) => i).sort(() => rnd() - 0.5);
  const keptRank = new Map(); for (let q = 0; q < nK; q++) keptRank.set(Math.floor((q * 0.85 * nR) / nK), q);
  const st = Array.from({ length: nR }, (_, s) => {
    const rank = ranks[s];
    return {
      s, rank, src: fan[s % nP], ki: keptRank.has(rank) ? keptRank.get(rank) : -1,
      Q: new THREE.Vector3((rnd() - 0.5) * 6.2, 1.7 + rnd() * 0.6, 1.0 + rnd() * 0.5), qr: (rnd() - 0.5) * 2,
      queue: new THREE.Vector3(0.7 + (rank * 2.5) / Math.max(1, nR - 1), 0.3, 2.7),
      jit: (rnd() - 0.5) * 0.3,
    };
  });
  const lines = r.answer.flatMap((s) => s.lines);
  return { r, col, routed, routedSet: new Set(routed), nS, nP, nC, nR, nK, sh, st, lines, struck: lines.findIndex((l) => l.withdrawn) };
}

let apState = '';
function drawAnswerPage(n, struck, cross) {
  const k = n + ':' + cross; if (k === apState) return; apState = k;
  const { g, c, tex } = answerPage;
  g.fillStyle = '#EEE9DD'; g.fillRect(0, 0, c.width, c.height);
  g.fillStyle = '#1A1C22'; g.fillRect(34, 38, 170, 16);
  const widths = [300, 270, 310, 220, 290, 300, 180, 280, 305, 240, 290, 200, 260, 300];
  for (let i = 0; i < n && i < widths.length; i++) {
    const y = 84 + i * 31;
    g.fillStyle = i === struck ? '#a8a398' : '#5b5953'; g.fillRect(34, y, widths[i], 9);
    if (i === struck && cross) { g.strokeStyle = '#FF6B5E'; g.lineWidth = 4; g.beginPath(); g.moveTo(28, y + 6); g.lineTo(44 + widths[i], y + 2); g.stroke(); }
    if (i % 3 === 1) { g.fillStyle = '#D8F25B'; g.fillRect(34 + widths[i] - 46, y - 3, 40, 15); }
  }
  tex.needsUpdate = true;
}

// ---------------------------------------------------------------- per-frame poses
const dummy = new THREE.Object3D(), V = new THREE.Vector3(), A = new THREE.Vector3(), D = new THREE.Vector3(), col3 = new THREE.Color();
function put(mesh, i, p, rx, ry, rz, s) {
  dummy.position.copy(p); dummy.rotation.set(rx, ry, rz); dummy.scale.setScalar(Math.max(s, 0)); dummy.updateMatrix();
  mesh.setMatrixAt(i, dummy.matrix);
}
const hide = (mesh, i) => put(mesh, i, V.set(0, -5, 0), 0, 0, 0, 0);
function arc(out, a, b, u, lift) { out.lerpVectors(a, b, u); out.y += Math.sin(Math.PI * u) * lift; return out; }
function stg(t, act, k, n, dur = 0.36) { return ease(clamp((t - (act + 0.04 + (n > 1 ? (0.58 * k) / (n - 1) : 0))) / dur)); }
const viewT = () => (RM && S.playing ? Math.ceil(S.t) : S.t);
const lift = (t) => 0.12 * ease(clamp(t - 1));
function stackH(i) { return L.st[i].h; }

function poseStacks(t) {
  for (let i = 0; i < L.n; i++) {
    const s = L.st[i];
    let y = 0, sy = 1;
    const showRun = run && (S.screen === 'ask' || S.story);
    const routedNow = showRun && run.routedSet.has(i);
    if (showRun) { const e = ease(clamp(t - 1)); if (routedNow) y = lift(t); else sy = 1 - 0.05 * e; col3.copy(PAPER).lerp(DIM, routedNow ? 0 : e); }
    else col3.copy(PAPER);
    if (hover === i) y += 0.05;
    dummy.position.set(s.x, y, s.z); dummy.rotation.set(0, s.rot, 0); dummy.scale.set(s.w, Math.max(0.002, stackH(i) * sy * (S.story ? S.grow : 1)), s.d); dummy.updateMatrix();
    stacks.setMatrixAt(i, dummy.matrix); stacks.setColorAt(i, col3);
  }
  stacks.instanceMatrix.needsUpdate = true; if (stacks.instanceColor) stacks.instanceColor.needsUpdate = true; // null with 0 documents
}

function poseRun(t, now) {
  const R = run;
  if (!R || !(S.screen === 'ask' || S.story)) { sheets.count = strips.count = 0; answerPage.mesh.visible = scan.visible = false; return; }
  sheets.count = R.nS; strips.count = R.nR;
  const fp = L.fp;
  for (const s of R.sh) {
    const st = L.st[s.doc];
    A.set(s.A.x, st.h + lift(t) + 0.01, s.A.z);
    const u2 = stg(t, 2, s.k, R.nS), u3 = stg(t, 3, s.k, R.nS);
    if (u2 <= 0) { hide(sheets, s.k); continue; }
    if (u3 <= 0) { arc(V, A, s.B, u2, 0.7); put(sheets, s.k, V, s.cr.x * u2, lerp(s.ry, s.cr.y, u2), s.cr.z * u2, lerp(fp, SC.cloud, u2)); continue; }
    if (s.j < 0) {
      if (u3 >= 1) { hide(sheets, s.k); continue; }
      arc(V, s.B, A, u3, 0.4); put(sheets, s.k, V, s.cr.x * (1 - u3), lerp(s.cr.y, s.ry, u3), s.cr.z * (1 - u3), lerp(SC.cloud, fp, u3)); continue;
    }
    const u9 = stg(t, 9, s.j, R.nP);
    if (u9 <= 0) {
      arc(V, s.B, s.C, u3, 0.3); if (u3 >= 1) V.y += Math.sin(now * 1.4 + s.k) * 0.01;
      put(sheets, s.k, V, lerp(s.cr.x, s.fr.x, u3), lerp(s.cr.y, 0, u3), lerp(s.cr.z, s.fr.z, u3), lerp(SC.cloud, SC.fan, u3));
    } else if (s.cited >= 0) {
      D.set(P.cited.x, 0.015 + s.cited * 0.022, P.cited.z);
      arc(V, s.C, D, u9, 0.6); put(sheets, s.k, V, s.fr.x * (1 - u9), lerp(0, (s.cited % 3 - 1) * 0.05, u9), s.fr.z * (1 - u9), lerp(SC.fan, SC.cited, u9));
    } else {
      if (u9 >= 1) { hide(sheets, s.k); continue; }
      arc(V, s.C, A, u9, 0.5); put(sheets, s.k, V, s.fr.x * (1 - u9), lerp(0, s.ry, u9), s.fr.z * (1 - u9), lerp(SC.fan, fp, u9));
    }
  }
  for (const s of R.st) {
    const u4 = stg(t, 4, s.s, R.nR), u5 = stg(t, 5, s.rank, R.nR), u6 = stg(t, 6, s.rank, R.nR);
    col3.copy(PAPER);
    if (u4 <= 0) { hide(strips, s.s); continue; }
    if (u5 <= 0) { V.lerpVectors(s.src.C, s.Q, u4); put(strips, s.s, V, lerp(0.95, 0.4, u4), 0, s.qr * u4, u4); strips.setColorAt(s.s, col3); continue; }
    if (u6 <= 0) { arc(V, s.Q, s.queue, u5, 0.2); put(strips, s.s, V, lerp(0.4, 1.2, u5), 0, s.qr * (1 - u5), 1); strips.setColorAt(s.s, col3); continue; }
    if (u6 < 0.5) { V.lerpVectors(s.queue, P.scan, u6 * 2); put(strips, s.s, V, 1.2, 0, 0, 1); strips.setColorAt(s.s, col3); continue; }
    const v = (u6 - 0.5) * 2;
    if (s.ki < 0) {
      if (v >= 1) { hide(strips, s.s); continue; }
      V.copy(P.scan); V.y -= 0.9 * v; V.z += 0.45 * v; col3.lerp(DIM, v);
      put(strips, s.s, V, 1.2 + v, 0, v * s.qr, 1 - v); strips.setColorAt(s.s, col3); continue;
    }
    D.set(P.kept.x + s.jit * 0.2, 0.012 + s.ki * 0.02, P.kept.z);
    const u7 = stg(t, 7, s.ki, R.nK);
    col3.copy(HL);
    if (u7 <= 0) { arc(V, P.scan, D, v, 0.4); put(strips, s.s, V, 1.2 * (1 - v), s.jit * v, 0, 1); }
    else if (u7 < 1) { arc(V, D, P.answer, u7, 0.6); put(strips, s.s, V, lerp(0, 0.9, u7), s.jit, 0, 1 - 0.9 * u7); }
    else hide(strips, s.s);
    strips.setColorAt(s.s, col3);
  }
  sheets.instanceMatrix.needsUpdate = strips.instanceMatrix.needsUpdate = true;
  strips.instanceColor.needsUpdate = true;
  // answer page, question slip, scan line
  const ua = ease(clamp((t - 7) / 0.35));
  answerPage.mesh.visible = ua > 0;
  answerPage.mesh.position.copy(P.answer); answerPage.mesh.position.y = lerp(0.02, P.answer.y, ua);
  answerPage.mesh.rotation.set(0.9 * ua, 0, 0); answerPage.mesh.scale.setScalar(Math.max(0.001, ua));
  drawAnswerPage(Math.round(clamp((t - 7.1) / 0.85) * 13), R.struck >= 0 ? 5 : -1, t >= 8.4);
  scan.visible = t > 6 && t < 7.05; scan.position.copy(P.scan); scan.material.opacity = Math.sin(clamp(t - 6) * Math.PI);
}

// free sheets: the waiting riffle and indexing flights
const flights = [];
function fly(a, b, dur, liftH, cb) {
  if (flights.length >= CAP.free) { cb && cb(); return; }
  flights.push({ a: a.clone(), b: b.clone(), t0: performance.now() / 1000, dur, lift: liftH, spin: (Math.random() - 0.5) * 2, cb });
}
function poseFree(now) {
  for (let i = flights.length - 1; i >= 0; i--) {
    const f = flights[i];
    if ((now - f.t0) / f.dur >= 1) { flights.splice(i, 1); f.cb && f.cb(); }
  }
  free.count = flights.length;
  flights.forEach((f, i) => {
    const u = ease(clamp((now - f.t0) / f.dur));
    arc(V, f.a, f.b, u, f.lift); put(free, i, V, Math.sin(u * Math.PI) * 0.6, f.spin * u, Math.sin(u * Math.PI) * 0.3 * f.spin, L.fp);
  });
  free.instanceMatrix.needsUpdate = true;
}

// ---------------------------------------------------------------- labels, hover
const labels = $('#labels'), tip = $('#tip');
const labPool = Array.from({ length: 12 }, () => { const d = document.createElement('div'); d.className = 'lab'; d.style.display = 'none'; labels.appendChild(d); return d; });
function project(x, y, z) { V.set(x, y, z).project(camera); return [((V.x + 1) / 2) * main.clientWidth, ((1 - V.y) / 2) * main.clientHeight, V.z < 1]; }
function updateLabels(t) {
  let used = 0;
  const placed = [];
  const show = (x, y, z, text, cls = '') => {
    if (used >= labPool.length) return; let [sx, sy, ok] = project(x, y, z); if (!ok) return;
    const w = Math.min(240, text.length * 6.7 + 14);
    // Nudge up until it clears the labels already placed.
    for (let guard = 0; guard < 6 && placed.some((p) => Math.abs(p[0] - sx) < (p[2] + w) / 2 && Math.abs(p[1] - sy) < 22); guard++) sy -= 22;
    placed.push([sx, sy, w]);
    const d = labPool[used++]; d.textContent = text; d.className = 'lab ' + cls; d.style.display = 'block'; d.style.left = sx + 'px'; d.style.top = sy - 6 + 'px';
  };
  const onAsk = S.screen === 'ask' || S.story, onLib = S.screen === 'library';
  if (onAsk && run && t >= 1.3 && t < 9.2 && run.routed.length <= 8) {
    for (const i of run.routed) { const s = L.st[i], d = S.coll.docs[i]; show(s.x, s.h + 0.2, s.z, `${midTrim(d.name, 30)} · ${fmt(d.pages)} p`); }
  }
  if (onAsk && run && t >= 6.7 && t < 7.6) show(P.kept.x, 0.15 + run.nK * 0.02, P.kept.z, `${fmt(run.r.kept)} kept`);
  if (onAsk && run && t >= 9.7) show(P.cited.x, 0.2 + run.nC * 0.026, P.cited.z, `${fmt(run.r.cited.length)} pages cited`, 'cite');
  if (onLib && L.n <= 12) S.coll.docs.forEach((d, i) => { const s = L.st[i]; show(s.x, stackH(i) + 0.15, s.z, midTrim(d.name, 26)); });
  for (let i = used; i < labPool.length; i++) labPool[i].style.display = 'none';
}
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
let hover = -1;
main.addEventListener('pointermove', (e) => {
  const r = main.getBoundingClientRect();
  par.mx = ((e.clientX - r.left) / r.width - 0.5) * 2; par.my = ((e.clientY - r.top) / r.height - 0.5) * 2;
  const overScene = e.target === canvas || e.target.classList.contains('screen');
  hover = -1;
  if (overScene && stacks && (S.screen === 'ask' || S.screen === 'library')) {
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObject(stacks)[0];
    if (hit) hover = hit.instanceId;
  }
  if (hover >= 0) {
    const d = S.coll.docs[hover];
    tip.innerHTML = `<b>${esc(d.name)}</b><span>${fmt(d.pages)} pages${run && run.routedSet.has(hover) ? ' · routed' : ''}</span>`;
    tip.style.display = 'block'; tip.style.left = Math.min(e.clientX - r.left + 14, r.width - 280) + 'px'; tip.style.top = e.clientY - r.top + 14 + 'px';
  } else tip.style.display = 'none';
});

// ---------------------------------------------------------------- loop
function resize() { renderer.setSize(main.clientWidth, main.clientHeight, false); camera.aspect = main.clientWidth / main.clientHeight; }
addEventListener('resize', resize); resize();
function frame() { requestAnimationFrame(frame); draw(); }
function draw() {
  if (S.screen === 'history' || S.screen === 'settings') return;
  if (S.screen === 'home') homeScroll();
  const now = performance.now() / 1000, t = viewT();
  par.x += (par.mx * 0.35 - par.x) * 0.04; par.y += (par.my * 0.2 - par.y) * 0.04;
  camera.position.set(cam.x + par.x, cam.y - par.y, cam.z);
  camera.lookAt(cam.tx, cam.ty, cam.tz);
  const W = main.clientWidth, H = main.clientHeight;
  camera.setViewOffset(W, H, cam.ox, cam.oy, W, H);
  const onHome = S.screen === 'home', hero = onHome && !S.story;
  homeG.visible = hero; stacks.visible = !hero; free.visible = !onHome;
  if (hero) poseHome(now); else poseStacks(t);
  poseRun(t, now);
  if (!onHome) poseFree(now);
  updateLabels(t);
  renderer.render(scene, camera);
}

// ---------------------------------------------------------------- Ask screen UI
const collSel = $('#coll'), qin = $('#qin'), askbtn = $('#askbtn');
function renderCollSelect() {
  collSel.innerHTML = COLLS.filter((c) => !c.indexing).map((c) =>
    `<option value="${esc(c.id)}" ${c === S.coll ? 'selected' : ''}>${esc(c.name)} · ${fmt(c.docs.length)} docs · ${fmt(pagesOf(c))} pages</option>`).join('') || '<option value="">No collection yet</option>';
}
collSel.addEventListener('change', () => setCollection(COLLS.find((c) => c.id === collSel.value)));
function setCollection(col) {
  pause(); stopWait(); S.coll = col; run = null; S.t = 0; S.mode = 'idle'; flights.length = 0;
  buildStacks(col); setDrawer(false); renderCollSelect(); renderTimeline(); renderCounters(); renderCaption(); renderLibrary();
  qin.value = col.run ? col.run.question : '';
  renderHome();
  if (col.id) try { localStorage.setItem('coll', col.id); } catch { /* storage off: start on the first collection */ }
  moveCamera(false);
}

function renderCounters() {
  const c = S.coll, r = run && run.r, t = S.t;
  const val = (from, to, a) => (t < a ? null : t < a + 1 ? Math.round(lerp(from, to, ease(t - a))) : to);
  const items = [
    [fmt(c.docs.length), 'documents', false],
    [r ? fmt(val(c.docs.length, run.routed.length, 1)) : '–', 'routed', false],
    [r ? fmt(val(0, r.candidates, 2)) : '–', 'candidate pages', false],
    [r ? fmt(val(0, r.kept, 6)) : '–', 'passages kept', true],
    [r ? fmt(val(0, r.cited.length, 9)) : '–', 'pages cited', true],
  ];
  $('#counters').innerHTML = items.map(([v, l, h], i) =>
    `${i ? '<svg class="i s arrow" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>' : ''}<div class="ctr ${v === '–' ? 'off' : h ? 'hl' : ''}"><b>${v}</b><span>${l}</span></div>`).join('');
}

function captionFor(i) {
  const r = run.r, n = S.coll.docs.length, cut = (real, cap) => (real > cap ? ` Showing ${cap} of ${fmt(real)}.` : '');
  return [
    'Reading the question and splitting it into tasks.',
    `${fmt(run.routed.length)} of ${fmt(n)} documents routed. The rest are set aside.`,
    `${fmt(r.candidates)} candidate pages pulled from the routed documents.${cut(r.candidates, CAP.sheets)}`,
    `${fmt(r.picked)} pages picked for a closer look. The others go back.`,
    `${fmt(r.passages)} passages taken from those pages.${cut(r.passages, CAP.strips)}`,
    'Passages ranked by a local model, best first.',
    `${fmt(r.passages)} passages checked against the question; ${fmt(r.kept)} kept as evidence.`,
    'The answer is written from the kept evidence only.',
    `${fmt(r.claims)} claims checked against the sources; ${fmt(r.withdrawn)} withdrawn.`,
    `${fmt(r.cited.length)} pages cited. Open a citation to read the page.`,
  ][i];
}
function renderCaption() {
  const el = $('#capline');
  if (!run) { el.innerHTML = ''; return; }
  const i = Math.min(9, Math.floor(S.t));
  el.innerHTML = `<em>${esc(run.r.steps[i].label)}</em>${esc(captionFor(i))}`;
}

// timeline
const tl = $('#tl');
let segEls = [], track = null, head = null;
function renderTimeline() {
  if (!run) {
    tl.innerHTML = `<div class="tl-empty">${S.mode === 'waiting' ? 'The steps appear here when the answer comes back.' : 'Ask a question to see how SiftBase answered it, step by step.'}</div>`;
    segEls = []; return;
  }
  const r = run.r, total = r.steps.reduce((a, s) => a + s.ms, 0) || 1;
  tl.innerHTML = `<div class="tl-ctl"><button class="icon-btn" id="tl-play" aria-label="Play"><svg class="i s"><use href="#i-play"/></svg></button><button class="icon-btn" id="tl-again" aria-label="Replay from the start"><svg class="i s"><use href="#i-replay"/></svg></button></div>
    <div class="track" id="track" tabindex="0" role="slider" aria-label="Run replay" aria-valuemin="0" aria-valuemax="10">
      ${r.steps.map((s, i) => `<div class="seg ${i === 6 || i === 9 ? 'keep' : ''}" style="flex:${Math.max(s.ms, total * 0.075)} 1 0"><span class="nm">${s.label}</span><span class="dt">${secs(s.ms)}${s.count != null ? ' · ' + fmt(s.count) + ' ' + s.unit : ''}</span><div class="bar"><i></i></div></div>`).join('')}
      <div class="playhead" id="head"></div></div>
    <div class="tl-sum"><b>${secs(r.latency_ms)}</b><span>total, ${esc(r.model)}</span><span>${fmt(r.claims - r.withdrawn)} claims kept</span></div>`;
  segEls = [...tl.querySelectorAll('.seg')]; track = $('#track'); head = $('#head');
  $('#tl-play').onclick = () => (S.playing ? pause() : play());
  $('#tl-again').onclick = () => play(0);
  const tAt = (x) => {
    const rx = x - track.getBoundingClientRect().left;
    for (let i = 0; i < segEls.length; i++) { const e = segEls[i]; if (rx <= e.offsetLeft + e.offsetWidth + 1.5 || i === 9) return clamp(i + (rx - e.offsetLeft) / e.offsetWidth, 0, 10); }
    return 10;
  };
  track.addEventListener('pointerdown', (e) => { track.setPointerCapture(e.pointerId); seek(tAt(e.clientX)); });
  track.addEventListener('pointermove', (e) => { if (track.hasPointerCapture(e.pointerId)) seek(tAt(e.clientX)); });
  track.addEventListener('keydown', (e) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (step) { e.preventDefault(); seek(step > 0 ? Math.floor(S.t) + 1 : Math.ceil(S.t) - 1); }
    if (e.key === 'Home') seek(0); if (e.key === 'End') seek(10);
    if (e.key === ' ') { e.preventDefault(); S.playing ? pause() : play(); }
  });
  syncTimeline();
}
function syncTimeline() {
  if (!run || !segEls.length) return;
  const t = S.t, i = Math.min(9, Math.floor(t));
  segEls.forEach((e, k) => { e.querySelector('.bar i').style.width = clamp(t - k) * 100 + '%'; e.classList.toggle('now', k === i && t < 10); });
  const e = segEls[i]; head.style.left = e.offsetLeft + clamp(t - i) * e.offsetWidth - 1 + 'px';
  track.setAttribute('aria-valuenow', t.toFixed(1)); track.setAttribute('aria-valuetext', `${run.r.steps[i].label}: ${captionFor(i)}`);
  const pb = $('#tl-play'); pb.innerHTML = `<svg class="i s"><use href="#i-${S.playing ? 'pause' : 'play'}"/></svg>`; pb.setAttribute('aria-label', S.playing ? 'Pause' : 'Play');
}

// drawer
const drawer = $('#drawer');
function setDrawer(open) { S.drawerOpen = open; $('#s-ask').classList.toggle('drawer-open', open); moveCamera(false); setTimeout(syncTimeline, 520); }
$('#dr-close').onclick = () => setDrawer(false);
function renderDrawer() {
  const r = run.r;
  $('#dr-q').textContent = r.question;
  const chips = (cs) => cs.map((c) => `<button class="cite" data-doc="${esc(c.doc)}" data-page="${c.page}" title="${esc(c.doc)}, page ${c.page}">${esc(midTrim(c.doc, 22))} p${c.page}</button>`).join('');
  let li = 0;
  const page = r.answer.map((s) => `<h3>${esc(s.heading)}</h3><ul>${s.lines.map((l) => `<li data-i="${li++}" class="${l.withdrawn ? 'struck' : ''}">${esc(l.text)}${chips(l.cites)}${l.withdrawn ? '<svg class="strike" viewBox="0 0 100 24" preserveAspectRatio="none"><path pathLength="1" d="M1 13 C 30 10, 60 15, 99 11"/></svg><span class="why">Withdrawn: no source supports it.</span>' : ''}</li>`).join('')}</ul>`).join('');
  const byDoc = {}; r.cited.forEach((c) => (byDoc[c.doc] = byDoc[c.doc] || []).push(c.page));
  $('#dr-content').innerHTML = `<div class="page">${page}</div>
    ${r.limitations.length ? `<div class="dr-sec"><h4>Not covered</h4>${r.limitations.map((x) => `<div class="gap"><svg class="i s"><use href="#i-gap"/></svg><span>${esc(x)}</span></div>`).join('')}</div>` : ''}
    <div class="dr-sec"><h4>Sources · ${fmt(r.cited.length)} pages in ${Object.keys(byDoc).length} documents</h4>
    ${Object.entries(byDoc).map(([d, ps]) => `<div class="src"><span class="nm" title="${esc(d)}">${esc(d)}</span>${ps.sort((a, b) => a - b).map((p) => `<button class="chip" data-doc="${esc(d)}" data-page="${p}">p${p}</button>`).join('')}</div>`).join('')}</div>
    <div class="meta"><span>${secs(r.latency_ms)}</span><span>${esc(r.model)}</span><span>${fmt(r.claims)} claims, ${fmt(r.withdrawn)} withdrawn</span></div>`;
}
$('#dr-body').addEventListener('click', (e) => { const b = e.target.closest('[data-doc]'); if (b) openReader(b.dataset.doc, +b.dataset.page); });
function syncDrawer() {
  if (!run) return;
  const t = S.t, n = run.lines.length;
  drawer.querySelectorAll('.page li').forEach((li) => {
    const i = +li.dataset.i; li.classList.toggle('in', t >= 7.05 + (0.85 * i) / Math.max(1, n)); li.classList.toggle('cross', t >= 8.35);
  });
}

// reader
const reader = $('#reader');
let lastFocus = null;
function openReader(doc, page) {
  const c = run && run.r.cited.find((x) => x.doc === doc && x.page === page);
  const text = c ? c.text.replace(/<\/?su[bp]>/g, '') : 'This page is not part of this answer\u2019s evidence.';
  const [first, ...rest] = text.split(/\n\n/);
  $('#rd-title').textContent = `${doc} · page ${page}`;
  $('#rd-body').innerHTML = `<span class="mark-hl">${esc(first)}</span>${rest.length ? '\n\n' + esc(rest.join('\n\n')) : ''}`;
  $('#rd-foot').textContent = c ? 'Highlighted: the passage this answer cites.' : '';
  lastFocus = document.activeElement; reader.classList.add('on'); reader.classList.remove('lit');
  requestAnimationFrame(() => requestAnimationFrame(() => reader.classList.add('lit')));
  $('#rd-close').focus();
}
function closeReader() { reader.classList.remove('on', 'lit'); lastFocus && lastFocus.focus(); }
$('#rd-close').onclick = closeReader;
reader.addEventListener('click', (e) => { if (e.target === reader) closeReader(); });

// playback
let tween = null;
function onT() { renderCounters(); renderCaption(); syncTimeline(); syncDrawer(); if (run && S.t >= 7 && !S.autoOpened) { S.autoOpened = true; setDrawer(true); } }
function play(from) {
  if (!run) return; tween && tween.kill();
  if (from != null || S.t >= 10) S.t = from || 0;
  if (S.t < 7) S.autoOpened = false;
  S.playing = true;
  tween = gsap.to(S, { t: 10, duration: (10 - S.t) * 1.2, ease: RM ? 'steps(' + Math.ceil(10 - S.t) + ')' : 'none', onUpdate: onT, onComplete: () => { S.playing = false; onT(); } });
  onT();
}
function pause() { tween && tween.kill(); S.playing = false; if (run) onT(); }
function seek(t) { pause(); S.t = clamp(t, 0, 10); S.autoOpened = S.t >= 7; if (S.t >= 7 && !S.drawerOpen) setDrawer(true); onT(); }

// asking
let waitTimer = null, riffleTimer = null, waitStart = 0;
const notice = $('#notice');
function showNotice(kind, html) { notice.className = 'notice on ' + kind; notice.innerHTML = html; }
$('#qform').addEventListener('submit', (e) => {
  e.preventDefault();
  notice.className = 'notice';
  if (!qin.value.trim()) { qin.focus(); return; }
  if (S.coll.empty) return showNotice('warn', '<svg class="i s"><use href="#i-gap"/></svg><div><b>Nothing to ask yet.</b> Index a folder in the Library first.</div>');
  if (!navigator.onLine) return showNotice('bad', '<svg class="i s"><use href="#i-off"/></svg><div><b>No internet.</b> Answers need the model service. The library and past answers still work.</div>');
  if (S.keys && !S.keys.ready) return showNotice('warn', '<svg class="i s"><use href="#i-gap"/></svg><div><b>No model keys yet.</b> Add them in Settings, then ask again.</div>');
  if (S.api !== 'running') return showNotice('warn', `<svg class="i s"><use href="#i-gap"/></svg><div><b>The local API is ${S.api === 'starting' ? 'still starting' : 'not running'}.</b> ${esc(S.apiError || 'Try again in a moment.')}</div>`);
  if (S.capacityUntil > Date.now()) return capacityNotice();
  ask(S.coll, qin.value.trim());
});
function capacityNotice() {
  const at = new Date(S.capacityUntil), mins = Math.ceil((S.capacityUntil - Date.now()) / 60000);
  showNotice('warn', `<svg class="i s"><use href="#i-gap"/></svg><div><b>The free model allowance is used up for now.</b> Asking works again at ${at.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}, in ${mins >= 60 ? Math.floor(mins / 60) + ' h ' : ''}${mins % 60} min. Your question stays here.</div>`);
}
const FAIL = {
  PROVIDER_UNAVAILABLE: ['bad', 'The model service did not answer.', 'Check the internet connection and your keys in Settings, then ask again.'],
  TIMEOUT: ['bad', 'No answer after 5 minutes.', 'The models may be overloaded. Ask again in a few minutes.'],
  COLLECTION_NOT_FOUND: ['warn', 'This collection has no live index.', 'Index the folder again in the Library.'],
  COLLECTION_NOT_READY: ['warn', 'This collection is not ready.', 'Wait for indexing to finish, then ask again.'],
};
async function ask(col, question) {
  startWait();
  const res = await sift.query(col.id, question);
  loadHistory();
  // The user moved to another collection while waiting (it may have its own wait running): the answer is in History.
  if (S.coll.id !== col.id) return;
  stopWait();
  if (res.ok) { S.coll.run = res.run; startRun(S.coll, 0); return; }
  S.mode = 'idle'; renderTimeline();
  if (res.code === 'AT_CAPACITY') { S.capacityUntil = Date.now() + (res.retryAfter || 3600) * 1000; renderStatus(); return capacityNotice(); }
  const [kind, head, tail] = FAIL[res.code] || ['bad', 'The question could not be answered.', res.message || res.code];
  showNotice(kind, `${kind === 'bad' ? '<svg class="i s"><use href="#i-off"/></svg>' : '<svg class="i s"><use href="#i-gap"/></svg>'}<div><b>${esc(head)}</b> ${esc(tail)}</div>`);
}
function startWait() {
  pause(); run = null; S.t = 0; S.mode = 'waiting'; setDrawer(false); renderTimeline(); renderCounters(); renderCaption();
  askbtn.disabled = true; askbtn.textContent = 'Asking';
  $('#wait').classList.add('on');
  $('#waittext').innerHTML = `Searching ${fmt(S.coll.docs.length)} documents · usually 35-40 s, up to 3 min<br><span style="color:var(--text-3)">The steps replay on the table when the answer is back.</span>`;
  waitStart = performance.now(); $('#elapsed').textContent = '0:00';
  waitTimer = setInterval(() => { const s = Math.floor((performance.now() - waitStart) / 1000); $('#elapsed').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; }, 250);
  riffleTimer = setInterval(() => {
    if (RM || !L.n) return; const i = Math.floor(Math.random() * L.n), s = L.st[i];
    A.set(s.x, stackH(i) + 0.01, s.z); fly(A, A, 0.9 + Math.random() * 0.4, 0.4 + Math.random() * 0.5);
  }, L.big ? 30 : 70);
}
function stopWait() { clearInterval(waitTimer); clearInterval(riffleTimer); $('#wait').classList.remove('on'); askbtn.disabled = false; askbtn.textContent = 'Ask'; }
function startRun(col, t) {
  if (!col.docs.length) return; // re-indexed to nothing since this answer
  S.mode = 'run'; run = buildRun(col); apState = ''; renderTimeline(); renderDrawer();
  S.autoOpened = false; if (t >= 10) { S.t = 10; S.autoOpened = true; setDrawer(true); onT(); } else play(0);
}

// ---------------------------------------------------------------- navigation
const where = $('#where');
const SCREENS = ['ask', 'library', 'history', 'settings'];
function go(screen, instant) {
  const was = S.screen; S.screen = screen;
  // Home is a landing page with no sidebar; the workspace screens share the rail.
  const app = $('#app'), wasHome = app.classList.contains('home-mode');
  app.classList.toggle('home-mode', screen === 'home');
  if (screen !== 'home') { S.story = false; if (wasHome && !instant && !RM) gsap.from('.rail', { x: -40, opacity: 0, duration: 0.7, ease: 'expo.out', clearProps: 'all' }); }
  resize();
  document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('on', s.id === 's-' + screen));
  document.querySelectorAll('.rail [data-go]').forEach((b) => (b.getAttribute('data-go') === screen ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current')));
  where.textContent = screen[0].toUpperCase() + screen.slice(1);
  tip.style.display = 'none';
  const scened = screen === 'home' || screen === 'ask' || screen === 'library';
  canvas.style.visibility = labels.style.visibility = scened ? 'visible' : 'hidden';
  // The rail's highlight slides to the new item; the screen's panels rise in.
  const b = document.querySelector(`.rail [data-go="${screen}"]`);
  if (b) gsap.to('#railind', { y: b.offsetTop - 10, duration: instant || RM || wasHome ? 0 : 0.55, ease: 'expo.out' });
  if (!instant && !RM && was !== screen) {
    gsap.fromTo($('#s-' + screen).querySelectorAll('.top, .tl, .lib-l, .lib-r, .home-panel, .counters, .lib-title, .hist, .set-col, .home-cap'),
      { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.6, ease: 'expo.out', stagger: 0.05, clearProps: 'transform,opacity' });
  }
  if (screen === 'home') startHome(); else pauseHome();
  if (screen === 'library') renderLibrary();
  if (screen === 'history') renderHistory();
  if (scened) moveCamera(instant);
}
document.querySelectorAll('.rail [data-go]').forEach((b) => (b.onclick = () => go(b.getAttribute('data-go'))));
addEventListener('keydown', (e) => {
  if (e.ctrlKey && /^[1-4]$/.test(e.key)) { e.preventDefault(); enter(SCREENS[+e.key - 1]); }
  if (e.ctrlKey && e.key.toLowerCase() === 'k') { e.preventDefault(); go('ask'); qin.focus(); qin.select(); }
  if (e.key === 'Escape') { if (setup.classList.contains('on')) closeSetup(); else if (reader.classList.contains('on')) closeReader(); else if (S.drawerOpen) setDrawer(false); }
});

// ---------------------------------------------------------------- library
let sortKey = 'pages', sortDir = -1;
function renderLibrary() {
  const c = S.coll;
  const ix = S.indexing;
  $('#colls').innerHTML = (ix ? `<div class="coll indexing" role="status"><span class="r1">${esc(ix.collection)}</span>
      <span class="r2">Indexing · ${esc(ix.step || 'Starting')}${ix.total ? ` · ${fmt(ix.done)} of ${fmt(ix.total)}` : ''}</span>
      <span class="prog"><i style="width:${ix.pct || 0}%"></i></span></div>` : '') + COLLS.map((x) =>
    `<button class="coll" data-id="${esc(x.id)}" aria-current="${x === c}"><span class="r1">${esc(x.name)}</span>
      <span class="r2">${fmt(x.docs.length)} documents · ${fmt(pagesOf(x))} pages · live${x.indexedAt ? ' · ' + esc(x.indexedAt) : ''}</span></button>`).join('');
  $('#libtitle').innerHTML = `<b>${esc(c.name)}</b><span>${c.empty ? 'Index a folder to start' : `${fmt(c.docs.length)} documents · ${fmt(pagesOf(c))} pages`}</span>`;
  const f = $('#docfilter').value.toLowerCase();
  const rows = c.docs.map((d, i) => ({ ...d, i })).filter((d) => d.name.toLowerCase().includes(f))
    .sort((a, b) => (sortKey === 'name' ? a.name.localeCompare(b.name) : a.pages - b.pages) * sortDir);
  $('#doccount').textContent = `${fmt(rows.length)} of ${fmt(c.docs.length)}`;
  $('#docrows').innerHTML = rows.map((d) => `<tr><td><div class="doc-nm" title="${esc(d.name)}">${esc(d.name)}</div></td><td class="r">${fmt(d.pages)}</td></tr>`).join('');
}
$('#colls').addEventListener('click', (e) => { const b = e.target.closest('.coll'); if (b) setCollection(COLLS.find((x) => x.id === b.dataset.id)); });
$('#docfilter').addEventListener('input', renderLibrary);
document.querySelectorAll('th [data-sort]').forEach((b) => (b.onclick = () => { const k = b.dataset.sort; sortDir = sortKey === k ? -sortDir : k === 'name' ? 1 : -1; sortKey = k; renderLibrary(); }));

async function startIndex(folder) {
  if (S.indexing) return toast(`<i class="dot warn"></i><span><b>${esc(S.indexing.collection)} is still indexing.</b> One folder at a time.</span>`);
  folder = folder || (await sift.pickFolder());
  if (!folder) return;
  const base = folder.split(/[\\/]/).filter(Boolean).pop().replace(/\.zip$/i, '');
  const name = base.replace(/[^A-Za-z0-9_-]+/g, '-').replace(/^[-_]+|-+$/g, '').slice(0, 64) || 'documents';
  if (COLLS.some((c) => c.id === name) && !confirm(`Index ${name} again? The current index stays live until the new one is ready.`)) return;
  const r = await sift.index(folder, name);
  if (!r.ok) return toast(`<i class="dot bad"></i><span><b>Indexing did not start.</b> ${esc(r.message)}</span>`);
  S.indexing = { collection: name, step: 'Starting', pct: 0 };
  renderLibrary();
}
sift.onIndexProgress((p) => {
  S.indexing = p;
  if (S.screen === 'library') renderLibrary();
  // Pages drop onto the table as the indexer reports progress (every 5%).
  if (RM || !L || !L.n || S.screen === 'home') return;
  for (let k = 0; k < 6; k++) {
    const i = Math.floor(Math.random() * L.n), s = L.st[i];
    D.set(P.drop.x + (Math.random() - 0.5) * 3, P.drop.y, P.drop.z); A.set(s.x, stackH(i) + 0.02, s.z);
    setTimeout(() => fly(D, A, 0.75, 0.2), k * 90);
  }
});
sift.onIndexDone(async (d) => {
  S.indexing = null;
  if (!d.ok) { renderLibrary(); return toast(`<i class="dot bad"></i><span><b>Indexing ${esc(d.collection)} stopped.</b> ${esc(d.message)}</span>`); }
  await loadCollections(d.collection);
  const col = S.coll;
  toast(`<i class="dot"></i><span><b>${esc(col.name)} is live.</b> ${fmt(col.docs.length)} documents, ${fmt(pagesOf(col))} pages.</span><button class="btn primary" id="toast-ask">Ask this collection</button>`);
  $('#toast-ask').onclick = () => { hideToast(); go('ask'); qin.focus(); };
});
$('#indexbtn').onclick = () => startIndex();
const drop = $('#drop');
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.style.borderColor = 'var(--hl)'; });
drop.addEventListener('dragleave', () => (drop.style.borderColor = ''));
drop.addEventListener('drop', (e) => { e.preventDefault(); drop.style.borderColor = ''; const f = e.dataTransfer.files[0]; if (f) startIndex(sift.pathForFile(f)); });

const toastEl = $('#toast'); let toastT = null;
function toast(html) { toastEl.innerHTML = html; toastEl.classList.add('on'); clearTimeout(toastT); toastT = setTimeout(hideToast, 9000); }
function hideToast() { toastEl.classList.remove('on'); }

// ---------------------------------------------------------------- history
let HIST = [];
async function loadHistory() { HIST = (await sift.history()) || []; if (S.screen === 'history') renderHistory(); }
const lastRun = (name) => (HIST.find((h) => h.collection === name && h.run) || {}).run || null;
const FAILED = { AT_CAPACITY: 'At capacity', TIMEOUT: 'Timed out', PROVIDER_UNAVAILABLE: 'Model unavailable', API_UNREACHABLE: 'API stopped' };
let histSel = 0;
function renderHistory() {
  histSel = Math.min(histSel, Math.max(0, HIST.length - 1));
  $('#histrows').innerHTML = HIST.map((h, i) => {
    const r = h.run || null;
    const status = h.failed ? `<span class="st"><i class="dot warn"></i>${esc(FAILED[h.failed] || 'Failed')}</span>` : r.limitations.length ? `<span class="st"><i class="dot warn"></i>Partial</span>` : `<span class="st"><i class="dot"></i>Answered</span>`;
    const q = h.question;
    return `<tr data-i="${i}" aria-selected="${i === histSel}" tabindex="0"><td><div class="q-cell" title="${esc(q)}">${esc(q)}</div><span class="mono" style="color:var(--text-3)">${new Date(h.when).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span></td>
      <td class="mono">${esc(h.collection)}</td><td class="r">${r ? secs(r.latency_ms) : '–'}</td><td class="r">${r ? fmt(r.routed.length) : '–'}</td><td class="r">${r ? `${fmt(r.claims - r.withdrawn)} / ${fmt(r.withdrawn)}` : '–'}</td><td>${status}</td></tr>`;
  }).join('');
  const h = HIST[histSel], det = $('#histdetail');
  if (!h) { det.innerHTML = `<h3>No questions yet</h3><p style="color:var(--text-2);margin-top:8px">Every question you ask is kept here with its ten-step trace, timings and what was not covered.</p>`; return; }
  const r = h.run || null, col = COLLS.find((c) => c.id === h.collection);
  if (!r) { det.innerHTML = `<h3>${esc(FAILED[h.failed] || 'Not answered')}</h3><p style="color:var(--text-2);margin-top:8px">${esc(h.question)}</p><p style="color:var(--text-3);margin-top:8px">Nothing was answered, so there is no trace. Ask it again from the Ask screen.</p>`; return; }
  const total = r.steps.reduce((a, s) => a + s.ms, 0) || 1; let at = 0;
  det.innerHTML = `<h3>${esc(r.question)}</h3>
    <dl class="kv"><dt>Collection</dt><dd class="mono">${esc(h.collection)}</dd><dt>Took</dt><dd>${secs(r.latency_ms)}</dd><dt>Model</dt><dd>${esc(r.model)}</dd>
    <dt>Documents used</dt><dd>${fmt(r.routed.length)}${col ? ' of ' + fmt(col.docs.length) : ''}</dd><dt>Claims</dt><dd>${fmt(r.claims - r.withdrawn)} kept, ${fmt(r.withdrawn)} withdrawn</dd><dt>Not covered</dt><dd>${fmt(r.limitations.length)}</dd></dl>
    <div class="wf">${r.steps.map((s, i) => { const l = (100 * at) / total, w = (100 * s.ms) / total; at += s.ms;
      return `<div class="wf-row"><span class="n">${s.label}</span><div class="wf-track"><i class="${i === 6 ? 'keep' : ''}" style="left:${l}%;width:${w}%"></i></div><span class="t">${secs(s.ms)}</span>${s.count != null ? `<span class="wf-c">${fmt(s.count)} ${s.unit}</span>` : ''}</div>`; }).join('')}</div>
    <div class="btns"><button class="btn primary" id="h-replay" ${col ? '' : 'disabled'}>Replay on the table</button><button class="btn ghost" id="h-open" ${col ? '' : 'disabled'}>Open answer</button></div>
    ${col ? '' : '<p style="color:var(--text-3);margin-top:10px">This collection is no longer on this PC, so the table cannot replay it.</p>'}`;
  const openRun = (t) => { go('ask'); if (S.coll !== col) setCollection(col); col.run = r; qin.value = r.question; startRun(col, t); };
  if (col) { $('#h-replay').onclick = () => openRun(0); $('#h-open').onclick = () => openRun(10); }
}
$('#histrows').addEventListener('click', (e) => { const tr = e.target.closest('tr'); if (tr) { histSel = +tr.dataset.i; renderHistory(); } });
$('#histrows').addEventListener('keydown', (e) => { if (e.key === 'Enter') { const tr = e.target.closest('tr'); if (tr) { histSel = +tr.dataset.i; renderHistory(); } } });

// ---------------------------------------------------------------- settings
const API_STATE = { running: ['', 'API<br>running'], starting: ['warn', 'API<br>starting'], failed: ['bad', 'API<br>stopped'], stopped: ['bad', 'API<br>stopped'] };
function renderStatus() {
  const a = API_STATE[S.api] || API_STATE.starting;
  const m = !navigator.onLine ? ['bad', 'Models<br>offline'] : S.keys && !S.keys.ready ? ['warn', 'No model<br>keys'] : S.capacityUntil > Date.now() ? ['warn', 'At<br>capacity'] : ['pencil', 'Models<br>online'];
  $('#st-api').innerHTML = `<i class="dot ${a[0]}"></i>${a[1]}`; $('#st-api').title = S.apiError || 'Local API on 127.0.0.1';
  $('#st-model').innerHTML = `<i class="dot ${m[0]}"></i>${m[1]}`;
  $('#hh-status').innerHTML = `<i class="dot ${a[0]}"></i>${a[1].replace('<br>', ' ')}<i class="dot ${m[0]}"></i>${m[1].replace('<br>', ' ')}`;
  $('#api-detail').textContent = S.api === 'running' ? 'Running on 127.0.0.1, reachable from this PC only.' : S.apiError || 'Starting.';
}
function renderSettings() {
  const k = S.keys; if (!k) return;
  const v = k.values, env = (n) => (k.fromEnv || []).includes(n) ? 'from .env' : 'Not set';
  $('#k-cf').textContent = v.CLOUDFLARE_API_TOKEN ? `account ${v.CLOUDFLARE_ACCOUNT_ID || '?'} · token ${v.CLOUDFLARE_API_TOKEN}` : env('CLOUDFLARE_API_TOKEN');
  $('#k-groq').textContent = v.GROQ_API_KEY || env('GROQ_API_KEY');
  const p = k.paid || {};
  $('#k-paid').textContent = p.writer || p.judge ? [p.writer && `Writer: ${p.writer.provider} ${p.writer.model}`, p.judge && `Judge: ${p.judge.provider} ${p.judge.model}`].filter(Boolean).join(' · ') : 'None. The free models write answers and judge evidence.';
  $('#k-private').textContent = k.allowShare ? 'Off. Providers that may keep document text are allowed.' : 'On. Document text goes only to Cloudflare and Groq, which keep none of it.';
  $('#datadir').textContent = S.dataDir;
}
$('#keys-edit').onclick = () => openSetup(false);
$('#data-open').onclick = () => sift.openDataFolder();
$('#data-change').onclick = async () => { const d = await sift.pickDataFolder(); if (d) { S.dataDir = d; renderSettings(); } };
addEventListener('online', renderStatus); addEventListener('offline', renderStatus);

// ---------------------------------------------------------------- first run: each person connects their own models
const setup = $('#setup'), kf = $('#keysform');
const FREE_KEYS = ['CLOUDFLARE_ACCOUNT_ID', 'CLOUDFLARE_API_TOKEN', 'GROQ_API_KEY'];
let setupFocus = null;
function openSetup(first) {
  const k = S.keys || { values: {}, paid: {} };
  for (const n of FREE_KEYS) kf.elements[n].value = k.values[n] || '';
  for (const role of ['writer', 'judge']) {
    const p = (k.paid || {})[role] || {};
    kf.elements[role + '.provider'].value = p.provider || ''; kf.elements[role + '.model'].value = p.model || ''; kf.elements[role + '.key'].value = p.key || '';
  }
  kf.elements.allowShare.checked = !!k.allowShare;
  $('#paid').open = !!(k.paid && (k.paid.writer || k.paid.judge));
  $('#su-cancel').textContent = first ? 'Skip for now' : 'Cancel'; $('#su-err').textContent = '';
  kf.querySelectorAll('.res').forEach((r) => { r.textContent = ''; r.className = 'res'; });
  setupFocus = document.activeElement; setup.classList.add('on'); kf.elements.CLOUDFLARE_ACCOUNT_ID.focus();
}
function closeSetup() { setup.classList.remove('on'); setupFocus && setupFocus.focus(); }
$('#su-cancel').onclick = closeSetup;
kf.addEventListener('click', async (e) => {
  const b = e.target.closest('[data-test]'); if (!b) return;
  const role = b.dataset.role, res = b.parentElement.querySelector('.res'), el = kf.elements;
  const provider = role ? el[role + '.provider'].value : b.dataset.test;
  if (!provider) { res.className = 'res bad'; res.textContent = 'Pick a provider first.'; return; }
  const values = role ? { key: el[role + '.key'].value, role } : provider === 'cloudflare' ? { CLOUDFLARE_API_TOKEN: el.CLOUDFLARE_API_TOKEN.value } : { key: el.GROQ_API_KEY.value };
  res.className = 'res'; res.textContent = 'Testing…'; b.disabled = true;
  const r = await sift.testKey(provider, values);
  b.disabled = false; res.className = 'res ' + (r.ok ? 'ok' : 'bad'); res.textContent = r.message;
});
kf.addEventListener('submit', async (e) => {
  e.preventDefault();
  const el = kf.elements, input = { values: {}, paid: {}, allowShare: el.allowShare.checked };
  for (const n of FREE_KEYS) input.values[n] = el[n].value;
  for (const role of ['writer', 'judge']) if (el[role + '.provider'].value) input.paid[role] = { provider: el[role + '.provider'].value, model: el[role + '.model'].value, key: el[role + '.key'].value };
  const btn = kf.querySelector('[type=submit]'); btn.disabled = true;
  const r = await sift.saveKeys(input);
  btn.disabled = false;
  if (!r.ok) { $('#su-err').textContent = r.message; return; }
  S.keys = r.keys; renderSettings(); renderStatus(); closeSetup();
  toast('<i class="dot"></i><span><b>Keys saved.</b> The local API restarts with them.</span>');
});

// ---------------------------------------------------------------- home: pages fly in, get scanned and filed
const homeG = new THREE.Group(); homeG.visible = false; scene.add(homeG);
const PW = 1.7, PH = 2.34, HC = new THREE.Vector3(0, 1.38, 0.5), HSTACK = new THREE.Vector3(1.3, 0, 2.05);
const H = { fly: 0, scan: 0, lift: 0, drop: 0, stackH: 0.12 };
const pageCv = document.createElement('canvas'); pageCv.width = 560; pageCv.height = 770;
const pg = pageCv.getContext('2d');
const pageTex = new THREE.CanvasTexture(pageCv); pageTex.colorSpace = THREE.SRGBColorSpace; pageTex.anisotropy = 8;
const hPage = new THREE.Mesh(new THREE.PlaneGeometry(PW, PH), new THREE.MeshStandardMaterial({ map: pageTex, roughness: 0.78, side: THREE.DoubleSide }));
hPage.castShadow = true; homeG.add(hPage);
const blankCv = document.createElement('canvas'); blankCv.width = 280; blankCv.height = 385;
{ const g = blankCv.getContext('2d'); g.fillStyle = '#EEE9DD'; g.fillRect(0, 0, 280, 385); g.fillStyle = '#b9b5aa';
  g.fillRect(28, 34, 140, 10); for (let i = 0; i < 18; i++) g.fillRect(28, 64 + i * 16, i % 6 === 5 ? 120 : 224, 4); }
const blankTex = new THREE.CanvasTexture(blankCv); blankTex.colorSpace = THREE.SRGBColorSpace;
const queue = Array.from({ length: 4 }, () => {
  const m = new THREE.Mesh(hPage.geometry, new THREE.MeshStandardMaterial({ map: blankTex, roughness: 0.85, side: THREE.DoubleSide, transparent: true }));
  m.castShadow = true; homeG.add(m); return m;
});
const beam = new THREE.Mesh(new THREE.BoxGeometry(PW * 1.06, 0.014, 0.014), new THREE.MeshBasicMaterial({ color: 0x8fb8ff }));
const band = new THREE.Mesh(new THREE.PlaneGeometry(PW * 1.06, 0.26), new THREE.MeshBasicMaterial({ color: 0x8fb8ff, transparent: true, opacity: 0.13, depthWrite: false }));
homeG.add(beam, band);
const hStack = new THREE.Mesh(boxGeo, stackMat); hStack.castShadow = hStack.receiveShadow = true; homeG.add(hStack);
const hStrips = instanced(stripGeo, sheetMat, 16); scene.remove(hStrips); homeG.add(hStrips);
// Waiting pages queue up off the left edge and slide in one at a time.
const qpos = (i) => new THREE.Vector3(-3.3 - i * 0.62, 1.42 + i * 0.04, -0.1 - i * 0.45);
let homePage = null, homeTl = null, homeK = 0, vecTimer = null;

function makePage(k) {
  const docs = S.coll.docs.length ? S.coll.docs : [{ name: 'Your first document.pdf', pages: 12 }], r = rng(k * 7919 + 13);
  const d = docs[Math.floor(r() * docs.length)];
  const kind = r(), table = kind < 0.32, chart = !table && kind < 0.55, scanned = r() < 0.22;
  const blocks = [{ x: 0.1, y: 0.09, w: 0.55, h: 0.045, kind: 'heading' }];
  let y = 0.18;
  const para = (lines) => { const h = lines * 0.022 + 0.012; blocks.push({ x: 0.1, y, w: 0.8, h, kind: 'text', lines }); y += h + 0.03; };
  para(4 + Math.floor(r() * 4));
  if (table) { blocks.push({ x: 0.1, y, w: 0.8, h: 0.2, kind: 'table' }); y += 0.23; }
  if (chart) { blocks.push({ x: 0.1, y, w: 0.52, h: 0.18, kind: 'chart' }); y += 0.21; }
  if (r() < 0.6) { blocks.push({ x: 0.1, y, w: 0.45, h: 0.032, kind: 'heading' }); y += 0.06; }
  while (y < 0.8) para(3 + Math.floor(r() * 4));
  const kept = blocks.filter((b) => b.y + b.h < 0.92);
  return { doc: d.name, total: d.pages, pno: 1 + Math.floor(r() * d.pages), table, chart, scanned, blocks: kept,
    chars: kept.reduce((a, b) => a + (b.lines || 2) * 86, 0), lines: kept.reduce((a, b) => a + (b.lines || 1), 0) };
}
const LABEL = { heading: 'Heading', text: 'Paragraph', table: 'Table', chart: 'Chart' };
function drawPage(p, scan) {
  const g = pg, W = pageCv.width, Hh = pageCv.height;
  g.globalAlpha = 1; g.fillStyle = p.scanned ? '#E4DFD1' : '#EEE9DD'; g.fillRect(0, 0, W, Hh);
  g.fillStyle = '#8a877e'; g.font = '500 12px "Martian Mono", monospace';
  g.fillText(midTrim(p.doc, 44), W * 0.1, 32); g.fillText('p' + p.pno, W * 0.84, Hh - 26);
  for (const b of p.blocks) {
    const x = b.x * W, y = b.y * Hh, w = b.w * W, h = b.h * Hh;
    if (b.kind === 'heading') { g.fillStyle = '#1A1C22'; g.fillRect(x, y, w, h * 0.7); }
    else if (b.kind === 'text') {
      g.fillStyle = p.scanned ? '#7f7b72' : '#64625c';
      for (let i = 0; i < b.lines; i++) g.fillRect(x, y + i * 0.022 * Hh + 3, i === b.lines - 1 ? w * 0.55 : w * (0.9 + ((i * 37) % 10) / 100), 6);
    } else if (b.kind === 'table') {
      g.fillStyle = '#d9d3c4'; g.fillRect(x, y, w, h / 5);
      g.strokeStyle = '#8a877e'; g.lineWidth = 1.2;
      for (let i = 0; i <= 5; i++) { g.beginPath(); g.moveTo(x, y + (i * h) / 5); g.lineTo(x + w, y + (i * h) / 5); g.stroke(); }
      for (let j = 0; j <= 4; j++) { g.beginPath(); g.moveTo(x + (j * w) / 4, y); g.lineTo(x + (j * w) / 4, y + h); g.stroke(); }
      g.fillStyle = '#64625c'; for (let i = 1; i < 5; i++) for (let j = 0; j < 4; j++) g.fillRect(x + (j * w) / 4 + 8, y + (i * h) / 5 + h / 10 - 3, w / 4 - 30 - ((i + j) % 3) * 8, 5);
    } else {
      g.strokeStyle = '#64625c'; g.lineWidth = 1.5; g.beginPath(); g.moveTo(x, y); g.lineTo(x, y + h); g.lineTo(x + w, y + h); g.stroke();
      g.fillStyle = '#7c8a99'; for (let i = 0; i < 6; i++) { const bh = h * (0.3 + ((i * 53) % 60) / 100); g.fillRect(x + 12 + i * (w / 6.4), y + h - bh, w / 9, bh); }
    }
  }
  // Regions found so far: everything the scan line has passed.
  for (const b of p.blocks) {
    const reveal = clamp((scan - (b.y + b.h)) * 12); if (reveal <= 0) continue;
    const strong = b.kind === 'table' || b.kind === 'chart', pad = 7;
    const x = b.x * W - pad, y = b.y * Hh - pad, w = b.w * W + pad * 2, h = b.h * Hh + pad * 2;
    g.globalAlpha = reveal;
    if (strong) { g.fillStyle = 'rgba(216,242,91,.22)'; g.fillRect(x, y, w, h); }
    g.strokeStyle = strong ? '#93ae1f' : '#5b8be0'; g.lineWidth = 2.5; g.beginPath(); g.roundRect(x, y, w, h, 6); g.stroke();
    g.font = '600 11px "Mona Sans", sans-serif'; const label = LABEL[b.kind], tw = g.measureText(label).width + 10;
    g.fillStyle = strong ? '#D8F25B' : '#8FB8FF'; g.beginPath(); g.roundRect(x, y - 17, tw, 16, 4); g.fill();
    g.fillStyle = '#1A1C22'; g.fillText(label, x + 5, y - 5);
  }
  g.globalAlpha = 1; pageTex.needsUpdate = true;
}
function poseHome(now) {
  const f = ease(H.fly), d = ease(H.drop);
  queue.forEach((m, i) => {
    m.position.lerpVectors(qpos(i + 1), qpos(i), f); m.rotation.set(0, lerp(0.55 + (i + 1) * 0.05, 0.55 + i * 0.05, f), 0);
    m.material.opacity = i === 3 ? f : 1;
  });
  if (H.drop <= 0) {
    arc(V, qpos(0), HC, f, 0.25); V.y += Math.sin(now * 1.2) * 0.012 * f;
    hPage.position.copy(V); hPage.rotation.set(lerp(0, -0.06, f), lerp(0.55, 0, f), lerp(0.1, 0, f)); hPage.scale.setScalar(1);
  } else {
    D.set(HSTACK.x, H.stackH + 0.01, HSTACK.z); arc(V, HC, D, d, 0.35);
    hPage.position.copy(V); hPage.rotation.set(lerp(-0.06, -Math.PI / 2, d), lerp(0, 0.08, d), 0); hPage.scale.setScalar(lerp(1, 0.36, d));
  }
  const scanning = H.scan > 0 && H.scan < 1;
  beam.visible = band.visible = scanning;
  if (scanning) { const y = HC.y + PH / 2 - H.scan * PH; beam.position.set(HC.x, y, HC.z + 0.03); band.position.set(HC.x, y + 0.13, HC.z + 0.02); }
  hStack.position.copy(HSTACK); hStack.scale.set(PW * 0.36, H.stackH, PH * 0.36);
  const p = homePage, n = p ? Math.min(16, p.blocks.length) : 0;
  hStrips.count = n;
  for (let i = 0; i < n; i++) {
    const b = p.blocks[i], u = ease(clamp((H.lift - (i * 0.5) / Math.max(1, n)) / 0.5));
    if (u <= 0 || u >= 1) { hide(hStrips, i); continue; }
    A.set(HC.x + (b.x + b.w / 2 - 0.5) * PW, HC.y + (0.5 - (b.y + b.h / 2)) * PH, HC.z + 0.04);
    D.set(5.4, 0.9 + i * 0.12, 0.6);
    arc(V, A, D, u, 0.3); put(hStrips, i, V, lerp(Math.PI / 2, 0.4, u), 0, 0, lerp(1.4, 0.8, u));
    hStrips.setColorAt(i, b.kind === 'table' || b.kind === 'chart' ? HL : PAPER);
  }
  hStrips.instanceMatrix.needsUpdate = true; if (hStrips.instanceColor) hStrips.instanceColor.needsUpdate = true;
}

const OPS = ['Reading pages', 'Summarising charts', 'Checking every word', 'Document summaries', 'Page summaries', 'Search vectors', 'Saving the index'];
const opsEl = $('#ops');
opsEl.innerHTML = OPS.map((n, i) => `<li class="op" data-i="${i}"><span class="n">${i + 1}/7</span><div><b>${n}</b><small></small>${i === 5 ? `<div class="vec">${'<i></i>'.repeat(48)}</div>` : ''}</div><span class="st"></span></li>`).join('');
const opEls = [...opsEl.children];
function setOp(i, state, text) { const el = opEls[i]; el.className = 'op ' + state; if (text != null) el.querySelector('small').textContent = text; }
function opText(p, i) {
  const heads = p.blocks.filter((b) => b.kind === 'heading').length, paras = p.blocks.filter((b) => b.kind === 'text').length;
  return [
    p.scanned ? `Scanned page: OCR read ${p.lines} lines` : `Text layer read: ${fmt(p.chars)} characters`,
    p.chart ? '1 chart described in words' : 'No charts on this page',
    `${paras} paragraph${paras === 1 ? '' : 's'} · ${heads} heading${heads === 1 ? '' : 's'}${p.table ? ' · 1 table' : ''}${p.chart ? ' · 1 chart' : ''}, every word placed`,
    `Summary card for ${midTrim(p.doc, 34)}`,
    `Topics, names and figures on page ${p.pno}`,
    '1 page vector, 384 numbers',
    `${p.blocks.length} passages to full-text search, page ${p.pno} stored`,
  ][i];
}
function vecRun(on) {
  clearInterval(vecTimer);
  const bars = opEls[5].querySelectorAll('.vec i');
  if (on) vecTimer = setInterval(() => bars.forEach((b) => (b.style.height = 15 + Math.random() * 85 + '%')), 120);
}
function homeCycle() {
  const p = (homePage = makePage(homeK++));
  Object.assign(H, { fly: 0, scan: 0, lift: 0, drop: 0 }); drawPage(p, 0);
  $('#hp-page').textContent = `${p.doc} · page ${p.pno} of ${fmt(p.total)}`;
  opEls.forEach((_, i) => setOp(i, '', ''));
  if (RM) { drawPage(p, 1); Object.assign(H, { fly: 1, scan: 1 }); opEls.forEach((_, i) => setOp(i, i === 1 && !p.chart ? 'skip' : 'done', opText(p, i))); return; }
  homeTl = gsap.timeline({ onComplete: homeCycle })
    .to(H, { fly: 1, duration: 1.0, ease: 'power3.out' })
    .call(() => setOp(0, 'run', opText(p, 0)), null, 1.0)
    .to(H, { scan: 1, duration: 2.2, ease: 'power1.inOut', onUpdate: () => drawPage(p, H.scan) }, 1.0)
    .call(() => { setOp(0, 'done'); setOp(2, 'run', opText(p, 2)); setOp(1, p.chart ? 'run' : 'skip', opText(p, 1)); }, null, 1.7)
    .call(() => p.chart && setOp(1, 'done'), null, 2.6)
    .call(() => { setOp(2, 'done'); setOp(3, 'run', opText(p, 3)); }, null, 3.2)
    .call(() => { setOp(3, 'done'); setOp(4, 'run', opText(p, 4)); }, null, 3.6)
    .call(() => { setOp(4, 'done'); setOp(5, 'run', opText(p, 5)); vecRun(true); }, null, 4.0)
    .to(H, { lift: 1, duration: 1.1, ease: 'none' }, 4.0)
    .call(() => { vecRun(false); setOp(5, 'done'); setOp(6, 'run', opText(p, 6)); }, null, 5.1)
    .to(H, { drop: 1, duration: 0.9, ease: 'power2.inOut' }, 5.1)
    .call(() => { setOp(6, 'done'); H.stackH = Math.min(0.55, H.stackH + 0.012); }, null, 6.0)
    .to({}, { duration: 0.5 });
}
function startHome() { if (homeTl) homeTl.resume(); else homeCycle(); }
function pauseHome() { homeTl && homeTl.pause(); vecRun(false); }
function renderHome() {
  const c = S.coll, pages = pagesOf(c), passages = c.elements ?? Math.round(pages * 9.9);
  $('#hp-name').textContent = c.name;
  $('#hp-meta').innerHTML = c.empty ? 'Nothing indexed yet. Index a folder to start.' : `Live${c.indexedAt ? ' · indexed ' + esc(c.indexedAt) : ''}`;
  $('#hp-stats').innerHTML = [[c.docs.length, 'documents'], [pages, 'pages'], [passages, 'passages'], [pages, 'page vectors']]
    .map(([v, l]) => `<div><b>${fmt(v)}</b><span>${l}</span></div>`).join('');
  $('#homecap').innerHTML = '<b>How SiftBase reads a page</b>Scanned, split into passages, given a search vector, then filed into the index.';
  renderStory();
  homeK = 0; homeTl && homeTl.kill(); homeTl = null;
  if (S.screen === 'home') homeCycle();
}
// ---------------------------------------------------------------- home: the scroll story below the opening
const homescroll = $('#homescroll');
const tick = '<svg class="i s" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>';
function renderStory() {
  const c = S.coll, r = c.run, n = c.docs.length, pages = pagesOf(c);
  const tag = '<span class="tag real">from your last question</span>';
  const big = (items) => `<div class="bigs">${items.map(([v, l, hl]) => `<div><b class="${hl ? 'hl' : ''}" data-n="${v}">0</b><span>${l}</span></div>`).join('')}</div>`;
  const cards = [
    `<h2>Every document becomes a stack</h2><p>${fmt(n)} documents and ${fmt(pages)} pages, read once and kept on this PC. A stack's height comes from its page count.</p>${big([[n, 'documents'], [pages, 'pages']])}`,
  ];
  if (r) cards.push(
    `${tag}<h2>Ask, and only the right documents move</h2><p>The question is split into tasks and routed to ${fmt(r.routed.length)} of ${fmt(n)} documents. ${fmt(r.candidates)} candidate pages fly out and ${fmt(r.picked)} are picked for a closer look.</p>${big([[r.routed.length, 'documents routed'], [r.candidates, 'candidate pages']])}`,
    `${tag}<h2>Every passage is checked</h2><p>${fmt(r.passages)} passages are checked against the question one at a time. ${fmt(r.kept)} hold up and get the highlighter; the rest drop away.</p>${big([[r.passages, 'passages checked'], [r.kept, 'kept as evidence', true]])}`,
    `${tag}<h2>Answers cite the exact page</h2><p>${fmt(r.claims)} claims are written from kept evidence only, checked again, and cited to ${fmt(r.cited.length)} pages you can open.${r.withdrawn ? ` ${fmt(r.withdrawn)} claim was withdrawn because no source supported it.` : ''}</p>${big([[r.claims, 'claims'], [r.cited.length, 'pages cited', true]])}`);
  cards.push(`<h2>Runs on your PC</h2><ul class="facts">
    <li>${tick}<span>Search, embeddings and reranking run locally. Your documents stay in the data folder.</span></li>
    <li>${tick}<span>Only the model calls go online, to Cloudflare and Groq. Private mode sends text only to providers that keep none of it.</span></li>
    <li>${tick}<span>Every answer keeps its ten-step trace in History, with timings and what was not covered.</span></li></ul>`);
  $('#stories').innerHTML = cards.map((h) => `<section class="story"><div class="card glass">${h}</div></section>`).join('') +
    `<section class="cta"><h2>Start with a question or a folder</h2><p>${c.empty ? 'Index a folder to begin.' : esc(c.name) + ' is ready to ask.'}</p><div class="hp-actions"><button class="btn primary lg" data-enter="ask">Open workspace</button><button class="btn ghost lg" data-enter="index"><svg class="i s"><use href="#i-folder"/></svg>Index a folder</button></div></section>`;
  S.storyActs = r ? 3 : 0;
  document.querySelectorAll('#stories .card').forEach((el) => seen.observe(el));
}
// Cards rise in as they enter, and their numbers count up once.
const seen = new IntersectionObserver((es) => es.forEach((e) => {
  if (!e.isIntersecting || e.target.classList.contains('in')) return;
  e.target.classList.add('in');
  e.target.querySelectorAll('[data-n]').forEach((b) => {
    const to = +b.dataset.n, o = { v: 0 };
    if (RM) b.textContent = fmt(to); else gsap.to(o, { v: to, duration: 1.4, ease: 'expo.out', onUpdate: () => (b.textContent = fmt(Math.round(o.v))) });
  });
}), { root: homescroll, threshold: 0.35 });

// Scroll position (in screen heights) picks the scene: the opening loop, then the table, then the Sift by acts.
function homeScroll() {
  const vh = homescroll.clientHeight, p = homescroll.scrollTop / vh;
  const story = p > 0.5;
  if (story !== S.story) {
    S.story = story;
    if (story) { pauseHome(); if (S.coll.run && S.coll.docs.length && (!run || run.col !== S.coll)) { run = buildRun(S.coll); apState = ''; } }
    else startHome();
  }
  $('#scrollhint').style.opacity = p > 0.05 ? 0 : 1;
  S.grow = ease(clamp((p - 0.5) / 0.6));
  if (story && run) {
    S.t = p < 1.4 ? 0 : p < 2.4 ? lerp(0, 3.6, clamp((p - 1.4) / 0.9)) : p < 3.4 ? lerp(3.6, 7, clamp((p - 2.4) / 0.9)) : lerp(7, 10, clamp((p - 3.4) / 0.9));
  }
  const w = homescroll.clientWidth;
  const v = story ? { ...VIEWS.ask(L), ox: -Math.round(Math.min(240, w * 0.17)), oy: 0 } : { ...HOME_VIEW, ox: Math.round(w * 0.235), oy: 0 };
  if (story && p > 4.5) { v.y += 1.6; v.z += 1.8; }
  for (const k in v) cam[k] += (v[k] - cam[k]) * (RM ? 1 : 0.07);
}

// Header and page buttons open the workspace, where the sidebar appears.
function enter(screen) {
  if (S.screen === 'home') { S.story = false; setCollection(S.coll); }
  if (screen === 'index') { go('library'); startIndex(); return; }
  go(screen); if (screen === 'ask') qin.focus();
}
$('#s-home').addEventListener('click', (e) => { const b = e.target.closest('[data-enter]'); if (b) enter(b.dataset.enter); });
$('#tbhome').onclick = () => { if (S.screen !== 'home') { setCollection(S.coll); go('home'); } };

// smooth scrolling for the home page and inside panels
if (window.Lenis && !RM) new window.Lenis({ wrapper: homescroll, content: homescroll.firstElementChild, autoRaf: true, lerp: 0.1 });
if (window.Lenis && !RM) for (const sel of ['#dr-body', '#docwrap', '#histwrap', '#setwrap']) {
  const w = $(sel); new window.Lenis({ wrapper: w, content: w.firstElementChild, autoRaf: true, lerp: 0.12 });
}

// ---------------------------------------------------------------- start
async function loadCollections(prefer) {
  const r = await sift.collections();
  if (!r.ok) return false;
  const old = new Map(COLLS.map((c) => [c.id, c]));
  const day = (iso) => (iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '');
  COLLS = r.collections.map((c) => ({ id: c.name, name: c.name, docs: c.docs, elements: c.elements, indexedAt: day(c.indexed_at),
    generation: c.generation_id, run: (old.get(c.name) || {}).run || lastRun(c.name) }));
  // Same collection, same index: swap in the fresh object and keep the table, the typed question and the open answer.
  const same = !prefer && COLLS.find((c) => c.id === S.coll.id && c.generation === S.coll.generation);
  if (same) { same.run = S.coll.run || same.run; S.coll = same; if (run) run.col = same; renderCollSelect(); renderLibrary(); return true; }
  let id = prefer || (S.coll.empty ? '' : S.coll.id);
  if (!id) try { id = localStorage.getItem('coll'); } catch { /* storage off */ }
  setCollection(COLLS.find((c) => c.id === id) || COLLS[0] || EMPTY);
  return true;
}
async function boot() {
  setCollection(EMPTY);
  go('home', true);
  frame();
  sift.onApi(async (a) => {
    S.api = a.state; S.apiError = a.error; renderStatus();
    if (a.state === 'running') { await loadHistory(); await loadCollections(); }
  });
  const st = await sift.status();
  Object.assign(S, { api: st.api.state, apiError: st.api.error, keys: st.keys, dataDir: st.dataDir });
  if (st.indexing) S.indexing = { collection: st.indexing, step: 'Indexing' };
  renderStatus(); renderSettings();
  await loadHistory();
  if (S.api === 'running') await loadCollections();
  if (!st.keys.ready) openSetup(true);
}
boot();
document.fonts.ready.then(() => { renderTimeline(); homePage && drawPage(homePage, H.scan); });
