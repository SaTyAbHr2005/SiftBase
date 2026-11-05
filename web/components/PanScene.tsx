"use client";
/* eslint-disable react-hooks/immutability -- three.js objects (textures, uniforms, the scene) are
   mutated every frame in useFrame by design; React never renders from them. */

// The pan in WebGL: steel pan, riverbed, gravel (one chip per page), gold flakes (kept pages)
// and a water surface with cursor ripples and still pools behind captions. Everything moves
// from `stage` in useFrame; React renders this tree once.
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";
import { NO_SCENE, stage } from "@/lib/stage.ts";
import { buildChips, pose, totals, PAN_RADIUS, ROLE, type ChipPose, type Corpus, type RunPages } from "@/lib/pan.ts";

type Props = { corpus: Corpus; run: { pages: RunPages }; onHover: (doc: number | null, x: number, y: number) => void; onReady: () => void; active: boolean };

const A = "/assets/";
const WATER_Y = 0.42;
const GOLD = new THREE.Color("#E8B23A");
const GRAVEL = new THREE.Color("#5E6F6B");
const FLAKE_RAW = new THREE.Color("#7D8A86");
const QUARTZ = new THREE.Color("#9FC7C4");

export default function PanScene(props: Props) {
  const [phone] = useState(() => innerWidth < 1024 || matchMedia("(pointer: coarse)").matches);
  const [dpr, setDpr] = useState(() => Math.min(devicePixelRatio, phone ? 1.5 : 1.75));
  return (
    <Canvas
      dpr={dpr} frameloop={props.active ? "always" : "never"} gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      camera={{ fov: 34, near: 0.1, far: 80, position: [0, 16.4, 11.5] }}
      eventSource={document.body} eventPrefix="client"
      onCreated={({ gl }) => {
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.domElement.addEventListener("webglcontextlost", () => window.dispatchEvent(new Event(NO_SCENE)));
      }}
    >
      <Suspense fallback={null}>
        <World {...props} phone={phone} />
        <Ready onReady={props.onReady} />
      </Suspense>
      <Governor dpr={dpr} setDpr={setDpr} />
    </Canvas>
  );
}

function Ready({ onReady }: { onReady: () => void }) {
  useEffect(onReady, [onReady]);
  return null;
}

// Lowers the pixel ratio when frames drop; after three slow windows in a row (6 s under 24fps) at a
// ratio of 1, hands over to the flat steps. One stall (a tab switch, a screenshot) never does.
function Governor({ dpr, setDpr }: { dpr: number; setDpr: (d: number) => void }) {
  const win = useRef({ t: 0, n: 0, slow: 0 });
  useFrame((_, dt) => {
    if (dt > 0.5) return; // first frame after a pause or a hidden tab, not a slow one
    const w = win.current;
    w.t += dt; w.n++;
    if (w.t < 2) return;
    const fps = w.n / w.t;
    w.t = 0; w.n = 0;
    if (document.hidden || stage.dim >= 1) return;
    if (fps < 45 && dpr > 1) setDpr(Math.max(1, +(dpr - 0.25).toFixed(2)));
    w.slow = fps < 24 ? w.slow + 1 : 0;
    if (w.slow >= 3 && dpr <= 1) window.dispatchEvent(new Event(NO_SCENE));
  });
  return null;
}

function World({ corpus, run, onHover, phone }: Props & { phone: boolean }) {
  const { scene, camera, pointer, raycaster, size } = useThree();
  // On tall, narrow screens the camera backs off so the whole pan fits the width.
  useEffect(() => {
    const k = Math.min(2.1, Math.max(1, 1.25 / (size.width / size.height)));
    camera.position.set(0, 16.4 * k, 11.5 * k);
    camera.lookAt(0, 0, 0.4);
  }, [camera, size.width, size.height]);
  const hdr = useLoader(HDRLoader, `${A}river.hdr`);
  const [bedColor, caustic] = useLoader(THREE.TextureLoader, [`${A}riverbed-color.webp`, `${A}caustic.webp`]);
  const detail = useLoader(THREE.TextureLoader, phone ? [] : [`${A}riverbed-normal.webp`, `${A}riverbed-rough.webp`, `${A}pan-normal.webp`, `${A}pan-rough.webp`]);
  const [bedNormal, bedRough, panNormal, panRough] = detail;

  useMemo(() => {
    hdr.mapping = THREE.EquirectangularReflectionMapping;
    bedColor.colorSpace = THREE.SRGBColorSpace;
    for (const t of [bedColor, caustic, ...detail]) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(3, 3); }
    caustic.repeat.set(2.2, 2.2);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `detail` is a new array each render; `phone` decides it
  }, [hdr, bedColor, caustic, phone]);
  useEffect(() => { scene.environment = hdr; scene.environmentIntensity = 0.9; }, [scene, hdr]);

  const chips = useMemo(() => buildChips(corpus, run, phone ? 10 : 1), [corpus, run, phone]);
  const tot = useMemo(() => totals(chips, corpus.documents.length), [chips, corpus]);
  const gravel = useMemo(() => chips.filter((c) => c.role < ROLE.kept), [chips]);
  const flakes = useMemo(() => chips.filter((c) => c.role >= ROLE.kept), [chips]);
  // River-gravel tones (warm browns, greys, teal-greys), one family per document so wedges read apart.
  const base = useMemo(() => gravel.map((c) => new THREE.Color().setHSL([0.08, 0.12, 0.45, 0.5, 0.42][c.doc % 5] + c.seed * 0.03, 0.06 + (c.doc % 3) * 0.04, 0.08 + c.seed * 0.11)), [gravel]);

  const gravelRef = useRef<THREE.InstancedMesh>(null!);
  const flakeRef = useRef<THREE.InstancedMesh>(null!);
  const group = useRef<THREE.Group>(null!);
  const causticRef = useRef<THREE.Mesh>(null!);
  const water = useMemo(() => waterMaterial(), []);
  useEffect(() => () => water.dispose(), [water]);
  const hovered = useRef(-1);
  const shown = useRef({ p: -1, cover: -1, hover: -2, pour: -1 });
  const born = useRef(-1);
  const smooth = useRef({ p: 0, cover: 0, tiltX: 0, tiltZ: 0 });
  const tmp = useMemo(() => ({ m: new THREE.Matrix4(), q: new THREE.Quaternion(), e: new THREE.Euler(), v: new THREE.Vector3(), s: new THREE.Vector3(), c: new THREE.Color(), pose: {} as ChipPose, plane: new THREE.Plane(new THREE.Vector3(0, 1, 0), -WATER_Y), hit: new THREE.Vector3() }), []);

  useFrame((state, dt) => {
    const k = 1 - Math.exp(-dt * 6);
    const sm = smooth.current;
    sm.p += (stage.p - sm.p) * k;
    sm.cover += (stage.cover - sm.cover) * k;
    if (Math.abs(stage.p - sm.p) < 1e-4) sm.p = stage.p;

    // On the cover the pan sits on the right; it slides to the centre as the stage pins.
    const wide = state.size.width >= 1024;
    group.current.position.x = wide ? 3.7 * (1 - sm.cover) : 0;
    group.current.position.z = wide ? 0 : 0.6 * (1 - sm.cover);
    // The pan tilts toward the cursor by at most 5 degrees, and swirls through the steps, back to
    // square at the end so the cited flakes line up across the view.
    sm.tiltX += (pointer.y * -0.087 - sm.tiltX) * k;
    sm.tiltZ += (pointer.x * -0.087 - sm.tiltZ) * k;
    group.current.rotation.set(sm.tiltX, Math.sin(sm.p * Math.PI) * 0.9, sm.tiltZ);

    water.uniforms.uTime.value = state.clock.elapsedTime;
    raycaster.setFromCamera(pointer, camera);
    if (raycaster.ray.intersectPlane(tmp.plane, tmp.hit)) {
      group.current.worldToLocal(tmp.hit);
      water.uniforms.uPointer.value.set(tmp.hit.x, tmp.hit.z);
    }
    const dprNow = state.gl.getPixelRatio();
    const [x, y, w, h] = stage.pool;
    water.uniforms.uPool.value.set(x * dprNow, (state.size.height - y - h) * dprNow, w * dprNow, h * dprNow);
    if (causticRef.current) {
      const t = (causticRef.current.material as THREE.MeshBasicMaterial).map!;
      t.offset.set(state.clock.elapsedTime * 0.012, state.clock.elapsedTime * 0.007);
    }

    // The gravel pours in over 2.6 s once the scene is up.
    if (born.current < 0) born.current = state.clock.elapsedTime;
    const pour = Math.min(1, (state.clock.elapsedTime - born.current) / 2.6);
    const sh = shown.current;
    if (sh.p === sm.p && sh.cover === sm.cover && sh.hover === hovered.current && sh.pour === pour) return;
    sh.p = sm.p; sh.cover = sm.cover; sh.hover = hovered.current; sh.pour = pour;
    const P = tmp.pose;
    gravel.forEach((c, i) => {
      pose(c, sm.p, tot, P, pour);
      tmp.e.set(c.seed * 6, c.seed * 40, 0);
      tmp.s.set(1 + c.seed * 0.5, 0.45, 0.8 + c.seed * 0.3).multiplyScalar(P.s);
      tmp.m.compose(tmp.v.set(P.x, P.y, P.z), tmp.q.setFromEuler(tmp.e), tmp.s);
      gravelRef.current.setMatrixAt(i, tmp.m);
      tmp.c.copy(base[i]).lerp(GRAVEL, P.dim * 0.7).multiplyScalar(1 - P.dim * 0.45).lerp(QUARTZ, P.lit * 0.55);
      if (c.doc === hovered.current) tmp.c.offsetHSL(0, 0.05, 0.22);
      gravelRef.current.setColorAt(i, tmp.c);
    });
    flakes.forEach((c, i) => {
      pose(c, sm.p, tot, P, pour);
      tmp.e.set(P.flip, c.seed * 40, c.seed * 0.6);
      tmp.s.set(1.1, 0.22, 0.9).multiplyScalar(P.s * (1 + P.gold * 0.5));
      tmp.m.compose(tmp.v.set(P.x, P.y, P.z), tmp.q.setFromEuler(tmp.e), tmp.s);
      flakeRef.current.setMatrixAt(i, tmp.m);
      flakeRef.current.setColorAt(i, tmp.c.copy(FLAKE_RAW).lerp(GOLD, P.gold));
    });
    for (const m of [gravelRef.current, flakeRef.current]) {
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    }
  });

  const profile = useMemo(() => [
    [0, -0.1], [4.5, -0.1], [4.85, 0.02], [5.35, 0.72], [5.62, 0.9], [5.7, 0.86], [5.42, 0.7], [4.9, 0.0], [4.55, -0.16], [0, -0.16],
  ].map(([x, y]) => new THREE.Vector2(x, y)), []);

  return (
    <>
      <directionalLight position={[-3, 9, 2]} intensity={1.3} color="#dff1ee" />
      <ambientLight intensity={0.25} color="#9fc7c4" />
      <group ref={group}>
        {/* The warm fill travels with the pan, so the gravel reads the same on the cover and in the steps. */}
        <pointLight position={[5, 1.4, 4]} intensity={5} distance={14} color="#ffc98a" />
        <mesh>
          <latheGeometry args={[profile, 96]} />
          <meshStandardMaterial color="#7f8986" metalness={0.8} roughness={0.45} normalMap={panNormal} roughnessMap={panRough} side={THREE.DoubleSide} />
        </mesh>
        {/* Riffles: three ridges on one side of the pan's wall. */}
        {[0.18, 0.38, 0.58].map((y, i) => (
          <mesh key={y} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 2.2]}>
            <torusGeometry args={[4.95 + i * 0.16, 0.035, 6, 48, 1.5]} />
            <meshStandardMaterial color="#8d9794" metalness={0.85} roughness={0.35} />
          </mesh>
        ))}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.06, 0]}>
          <circleGeometry args={[4.62, 72]} />
          <meshStandardMaterial map={bedColor} normalMap={bedNormal} roughnessMap={bedRough} color="#3a5553" roughness={0.9} />
        </mesh>
        {!phone && (
          <mesh ref={causticRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
            <circleGeometry args={[4.6, 72]} />
            <meshBasicMaterial map={caustic} color="#cfe8e2" transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} />
          </mesh>
        )}
        <instancedMesh
          ref={gravelRef} args={[undefined, undefined, gravel.length]} frustumCulled={false}
          onPointerMove={(e) => {
            if (stage.p > 0.15 || e.instanceId === undefined) {
              if (hovered.current >= 0) { hovered.current = -1; onHover(null, 0, 0); }
              return;
            }
            e.stopPropagation();
            hovered.current = gravel[e.instanceId].doc;
            onHover(hovered.current, e.clientX, e.clientY);
          }}
          onPointerOut={() => { hovered.current = -1; onHover(null, 0, 0); }}
        >
          <icosahedronGeometry args={[phone ? 0.18 : 0.09, 0]} />
          <meshStandardMaterial roughness={0.85} metalness={0.05} envMapIntensity={0.35} />
        </instancedMesh>
        <instancedMesh ref={flakeRef} args={[undefined, undefined, flakes.length]} frustumCulled={false}>
          <icosahedronGeometry args={[0.12, 1]} />
          <meshStandardMaterial metalness={0.92} roughness={0.26} envMapIntensity={1.4} />
        </instancedMesh>
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, WATER_Y, 0]} material={water}>
          <circleGeometry args={[PAN_RADIUS + 1.15, 96]} />
        </mesh>
      </group>
    </>
  );
}

function waterMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: {
      uTime: { value: 0 },
      uPointer: { value: new THREE.Vector2(99, 99) },
      uPool: { value: new THREE.Vector4(0, 0, 0, 0) },
      uShallow: { value: new THREE.Color("#123236") },
      uDeep: { value: new THREE.Color("#0F2A2E") },
      uStill: { value: new THREE.Color("#0B2225") },
    },
    vertexShader: /* glsl */ `
      varying vec2 vXZ;
      void main() {
        vXZ = position.xy * vec2(1.0, -1.0);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: /* glsl */ `
      uniform float uTime; uniform vec2 uPointer; uniform vec4 uPool;
      uniform vec3 uShallow, uDeep, uStill;
      varying vec2 vXZ;
      void main() {
        float r = length(vXZ) / ${(PAN_RADIUS + 1.15).toFixed(2)};
        // Still pool: calm, darker water behind the caption's screen rectangle.
        vec2 c = uPool.xy + uPool.zw * 0.5;
        vec2 q = (gl_FragCoord.xy - c) / max(uPool.zw * 0.62, vec2(1.0));
        float pool = uPool.z > 0.0 ? 1.0 - smoothstep(0.55, 1.0, length(q)) : 0.0;
        float calm = 1.0 - 0.8 * pool;
        float d = distance(vXZ, uPointer);
        float ring = sin(d * 9.0 - uTime * 3.2) * exp(-d * 1.5);
        float waves = sin(vXZ.x * 2.1 + uTime * 0.7) * 0.5 + sin(vXZ.y * 2.7 - uTime * 0.55) * 0.5
                    + sin((vXZ.x + vXZ.y) * 3.4 + uTime * 1.1) * 0.3;
        float h = (waves * 0.22 + ring * 0.55) * calm;
        float glint = smoothstep(0.42, 0.75, h) * 0.22 + length(vec2(dFdx(h), dFdy(h))) * 1.6 * calm;
        vec3 col = mix(uShallow, uDeep, r);
        col = mix(col, uStill, pool * 0.85) + vec3(0.95, 0.94, 0.9) * glint * 0.5;
        float a = mix(0.34, 0.62, r) + pool * 0.3;
        a *= 1.0 - smoothstep(0.93, 1.0, r);
        gl_FragColor = vec4(col, a);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  });
}
