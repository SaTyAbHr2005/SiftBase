"use client";

// The living stream: three photographs (the falls, one pool up close, the kingfisher) drawn in raw
// WebGL2 with depth parallax, pouring and rippling water, mist, light shafts and gold glints. Each
// photo has a depth map and a water mask (R still, G falling, B gold) made by
// scripts/prepare_assets.py. Scroll progress comes from `stage`; lib/stream.ts holds the timeline.
import { useEffect, useRef } from "react";
import { NO_SCENE, stage } from "@/lib/stage.ts";
import { timeline } from "@/lib/stream.ts";

const FILES = ["falls", "pool", "bird"].flatMap((s) => [s, `${s}-depth`, `${s}-water`]);
const UNITS = ["uF0", "uF1", "uF2", "uP0", "uP1", "uP2", "uB0", "uB1", "uB2"];

const VS = `#version 300 es
in vec2 a; void main(){ gl_Position = vec4(a, 0., 1.); }`;

const FS = `#version 300 es
precision highp float;
uniform sampler2D uF0, uF1, uF2, uP0, uP1, uP2, uB0, uB1, uB2, uNoise;
uniform vec2 uRes, uMouse;
uniform float uT, uAspect, uCover, uDive, uRise, uPa, uPb, uPc;
out vec4 o;

// Value noise from a 256px random texture with bilinear filtering: one fetch per octave.
float noise(vec2 p){ return texture(uNoise, p/256.).r; }
float fbm(vec2 p){ return texture(uNoise, p/256.).r*.5 + texture(uNoise, p/128.3).g*.25 + texture(uNoise, p/64.7).b*.125 + texture(uNoise, p/32.1).a*.0625; }
float ss(float a, float b, float x){ return smoothstep(a, b, x); }

// Cover-fit the 16:9 photo; on tall screens keep the scene's subject (fx) in view.
vec2 cover(vec2 uv, float fx){
  float sa = uRes.x/uRes.y; vec2 k = sa > uAspect ? vec2(1., uAspect/sa) : vec2(sa/uAspect, 1.);
  return (uv - .5)*k + vec2(clamp(fx, k.x*.5, 1. - k.x*.5), .5);
}

vec3 scene(sampler2D img, sampler2D dep, sampler2D wat, vec2 uv, float fx, vec2 c, float zoom, vec2 cam, float push, vec2 dir, float t){
  vec2 q = c + (cover(uv, fx) - c)/zoom, p = q;
  for (int i = 0; i < 3; i++) { float d = texture(dep, p).r - .45; p = q + cam*d - (q - c)*d*push; }
  vec3 m = texture(wat, p).rgb; float still = m.r, fall = m.g, gold = m.b;
  p += (vec2(fbm(p*vec2(10., 30.) + vec2(t*.18, t*.06)), fbm(p*vec2(12., 34.) - vec2(t*.15, 0.))) - .5) * .0035 * still;
  float f1 = fract(t*.55), f2 = fract(t*.55 + .5), L = .025;
  vec2 side = vec2(-dir.y, dir.x);
  vec2 jit = side * (noise(vec2(dot(p, side)*300., dot(p, dir)*8.)) - .5) * .002 * fall;
  vec3 col = mix(texture(img, p - dir*f1*L*fall + jit).rgb, texture(img, p - dir*f2*L*fall + jit).rgb, abs(f1*2. - 1.));
  col += fall * ss(.62, 1., noise(vec2(dot(p, side)*240., dot(p, dir)*12. - t*4.5))) * .14;
  col += still * pow(noise(p*vec2(170., 190.) + t*vec2(.35, .12)), 10.) * .3;
  float lum = dot(col, vec3(.3, .55, .15));
  col = mix(col, vec3(1., .76, .26)*(lum*1.35 + .12), gold*.75);
  col += gold * pow(noise(p*420. + t*2.), 10.) * vec3(1., .9, .62) * 2.6;
  return col;
}

void main(){
  vec2 uv = vec2(gl_FragCoord.x/uRes.x, 1. - gl_FragCoord.y/uRes.y), cam = uMouse*.025;
  float t = uT;
  // A ripple passes over the screen on the dive into the pool and on the rise to the kingfisher.
  float rip = sin(uDive*3.1416)*sin(length(uv - vec2(.5, .62))*60. - t*3.)*.012 + sin(uRise*3.1416)*sin(uv.y*48. + t*3.)*.01;
  vec3 a = vec3(0.), b = vec3(0.), c = vec3(0.);
  if (uDive < 1.) {
    a = scene(uF0, uF1, uF2, uv + rip, .45, mix(vec2(.5), vec2(.52, .66), uPa), mix(1.04, 2.3, uPa) + uCover*.06 + uDive*.8,
              cam + vec2(0., -.02*uPa), .35*uPa, vec2(0., 1.), t);
    float mist = fbm(uv*vec2(3., 5.) + vec2(t*.03, -t*.012));
    vec2 m = (uv - vec2(.41, .46))*vec2(6., 9.);
    a += vec3(.86, .92, .9) * mist*mist * (.22*(1. - ss(.1, .6, uv.y)) + .35*exp(-dot(m, m)));
    float ray = pow(sin((uv.x*1.1 + uv.y*.8)*26. + t*.25)*.5 + .5, 6.) * fbm(uv*4. + t*.05);
    a += vec3(.95, .93, .8) * ray * .08 * (1. - ss(.2, .7, uv.y));
  }
  if (uDive > 0. && uRise < 1.)
    b = scene(uP0, uP1, uP2, uv - rip, .5, vec2(.5, .62), mix(1.06, 1.45, uPb) + (1. - uDive)*.5, cam, .25*uPb, normalize(vec2(-.75, .66)), t);
  if (uRise > 0.)
    // The bird's wings meet the background in sharp depth edges, where strong parallax tears the photo
    // like a rubber sheet; this scene moves mostly by zoom, with a fifth of the sway and push.
    c = scene(uB0, uB1, uB2, uv + rip, .66, vec2(.6, .45), mix(1.04, 1.32, uPc) + (1. - uRise)*.35, cam*.2, .06*uPc, vec2(0., 1.), t);
  vec3 col = mix(mix(a, b, uDive), c, uRise);
  vec2 v = gl_FragCoord.xy/uRes - .5;
  o = vec4(col * (1. - dot(v, v)*.55), 1.);
}`;

type Props = { active: boolean; onReady: () => void };

export default function StreamScene({ active, onReady }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const live = useRef(active);
  useEffect(() => { live.current = active; }, [active]);

  useEffect(() => {
    const canvas = ref.current!;
    const fail = () => { window.dispatchEvent(new Event(NO_SCENE)); };
    // A software-only context (no GPU) would run the shader at a few frames a second: use the stills.
    const gl = canvas.getContext("webgl2", { antialias: false, alpha: false, powerPreference: "high-performance", failIfMajorPerformanceCaveat: true });
    if (!gl) return fail();

    const shader = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    };
    const prog = gl.createProgram();
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return fail();
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const U = (name: string) => gl.getUniformLocation(prog, name);
    const u = Object.fromEntries(["uRes", "uMouse", "uT", "uCover", "uDive", "uRise", "uPa", "uPb", "uPc"].map((k) => [k, U(k)]));

    let frame = 0, gone = false;
    // A lost context (common on mobile Safari after backgrounding) is not restored: the page switches
    // to the still photos for the rest of the visit.
    const lost = () => { gone = true; cancelAnimationFrame(frame); fail(); };
    canvas.addEventListener("webglcontextlost", lost);

    // Pointer sway, eased, so the camera glides instead of following the mouse exactly.
    let tx = 0, ty = 0;
    const point = (e: PointerEvent) => { tx = e.clientX / innerWidth - 0.5; ty = e.clientY / innerHeight - 0.5; };
    addEventListener("pointermove", point, { passive: true });

    // The photos are 1376px wide: past ~1.2 million pixels the canvas adds cost, not detail.
    let scale = 1;
    const resize = () => {
      const d = Math.min(devicePixelRatio, Math.sqrt(1.2e6 / (innerWidth * innerHeight))) * scale;
      const w = Math.round(innerWidth * d), h = Math.round(innerHeight * d);
      if (w === canvas.width && h === canvas.height) return; // iOS fires resize for every toolbar change
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(u.uRes, canvas.width, canvas.height);
    };

    const load = (src: string) => new Promise<HTMLImageElement>((ok, no) => {
      const img = new Image();
      img.onload = () => ok(img);
      img.onerror = no;
      img.src = src;
    });

    Promise.all(FILES.map((f) => load(`/assets/stream/${f}.webp`))).then((imgs) => {
      if (gone) return;
      // Depth and masks are data, not colour: no colour-profile conversion on upload.
      gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
      imgs.forEach((img, i) => {
        gl.activeTexture(gl.TEXTURE0 + i);
        gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.MIRRORED_REPEAT);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.MIRRORED_REPEAT);
        gl.uniform1i(U(UNITS[i]), i);
      });
      const rnd = Uint8Array.from({ length: 256 * 256 * 4 }, () => Math.random() * 256);
      gl.activeTexture(gl.TEXTURE0 + FILES.length);
      gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 256, 0, gl.RGBA, gl.UNSIGNED_BYTE, rnd);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.uniform1i(U("uNoise"), FILES.length);
      gl.uniform1f(U("uAspect"), imgs[0].width / imgs[0].height);
      resize();
      addEventListener("resize", resize);

      let p = stage.p, cover = stage.cover, mx = 0, my = 0, last = performance.now(), first = true;
      // Governor: three 2 s windows in a row under 24 fps first halve the resolution, then hand over
      // to the still photos. Gaps over 0.5 s (a background tab, a debugger) are not counted.
      let win = 0, frames = 0, slow = 0;
      const start = last;
      const draw = (now: number) => {
        frame = requestAnimationFrame(draw);
        const dt = (now - last) / 1000;
        last = now;
        if (!live.current && !first) return; // the first frame always draws, so a page loaded below the stream still turns ready
        if (dt < 0.5) {
          win += dt; frames++;
          if (win > 2) {
            slow = frames / win < 24 ? slow + 1 : 0;
            win = 0; frames = 0;
            if (slow >= 3) {
              if (scale > 0.5) { scale = 0.5; slow = 0; resize(); } else { cancelAnimationFrame(frame); fail(); return; }
            }
          }
        }
        const k = 1 - Math.pow(0.93, Math.min(dt, 0.1) * 60); // the same glide at any frame rate
        p += (stage.p - p) * k; cover += (stage.cover - cover) * k;
        mx += (tx - mx) * k * 0.7; my += (ty - my) * k * 0.7;
        const tl = timeline(p);
        gl.uniform1f(u.uT, (now - start) / 1000);
        gl.uniform2f(u.uMouse, mx, my);
        gl.uniform1f(u.uCover, cover);
        gl.uniform1f(u.uDive, tl.dive); gl.uniform1f(u.uRise, tl.rise);
        gl.uniform1f(u.uPa, tl.falls); gl.uniform1f(u.uPb, tl.pool); gl.uniform1f(u.uPc, tl.bird);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        if (first) { first = false; onReady(); }
      };
      frame = requestAnimationFrame(draw);
    }).catch(fail); // a failed image load or a throw during setup (out of memory, lost context)

    return () => {
      gone = true;
      cancelAnimationFrame(frame);
      removeEventListener("pointermove", point);
      removeEventListener("resize", resize);
      canvas.removeEventListener("webglcontextlost", lost);
      // No loseContext() here: React's dev double mount reuses this canvas, and a lost context
      // would never come back. The browser frees it when the canvas is removed.
    };
  }, [onReady]);

  return <canvas ref={ref} className="stream-canvas" />;
}
