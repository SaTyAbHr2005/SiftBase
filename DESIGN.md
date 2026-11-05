# SiftBase site design

The public site in `web/`: one long page plus a 404, built with Next.js on Vercel. Product facts live in PRODUCT.md. Direction: Gold Pan, chosen by the user on 2026-11-05 to replace the Evidence Binder. The flat build already in `web/` stays as the fallback for reduced motion and devices without WebGL, re-skinned in this palette and this surface language.

## 1. Concept

Pan 6,970 pages like river gravel, and keep only the gold: the passages that prove the answer.

Adjectives: elemental, patient, exacting, glinting, honest.

The page is a prospector's pan of dark river water seen from above, rendered in WebGL. Every page of the 35 documents is a chip of gravel in it. Scrolling swirls and tilts the pan through the ten pipeline steps: gravel washes out over the lip, the passages that survive verification turn over and show gold, and one flake that looked like gold turns out to be pyrite, which is how the page shows a withdrawn claim. What stays in the pan at the end is the cited evidence. Every count on screen comes from the real index or a recorded run.

Nothing on the page is a plain box. Text rests on calm water, river stones, wet field slips and gold, so the interface reads as part of the river rather than cards laid over it (section 3, "Surfaces").

## 2. References

| Reference | What we borrow |
|---|---|
| [Igloo Inc.](https://www.igloo.inc) | Thousands of instanced pieces that regroup as you scroll: our gravel washing down to flakes. |
| [Lusion](https://lusion.co) | Water and light handled with restraint around one 3D centrepiece; the interface stays out of its way. |
| [Studio Kogel on Awwwards](https://www.awwwards.com/inspiration/scroll-animation-studio-kogel) | GSAP + Three.js storytelling where one pinned scene changes per chapter: our pan through ten steps. |
| [Monogrid on Awwwards](https://www.awwwards.com/inspiration/3d-webgl-scroll-monogrid-com) | Scroll-scrubbed camera moves with text passing over the canvas. |
| [Codrops: Studio375's interactive comic](https://tympanus.net/codrops/?p=116812) | A physical object carried into WebGL without losing its material feel. |
| [Yale Law Journal](https://www.yalelawjournal.org) | Footnotes that open beside the text: a gold citation opens its source page next to the answer. |
| [Perplexity](https://www.perplexity.ai) | The category's small grey citation numbers, as the anti-reference. Ours are gold and worth clicking. |
| [Poly Haven](https://polyhaven.com) | Real scanned lighting and surfaces (CC0): the river light the gold reflects, the pebble riverbed and the worn steel of the pan. Section 7 lists the exact assets. |

## 3. Colour system

Dark, because the scene is water in a pan and gold only reads against depth. It is a river teal, not black, and the one bright colour is earned: gold appears only on verified evidence and on the actions that lead to it.

| Token | Hex | Role |
|---|---|---|
| `--shallow` | `#123236` | The page ground at the top: shallow water (bone 11.9:1, bone-2 7.8:1, gold 7.1:1, quartz 7.5:1, ember 5.0:1) |
| `--deep` | `#0F2A2E` | The page ground through the middle, the water, the 3D background and fog |
| `--pool` | `#0B2225` | Still water: behind text over the scene, inputs, error notices, the footer riverbed |
| `--stone` | `#1E4A4C` | River stones: answer slabs, the console, notices |
| `--gravel` | `#5E6F6B` | Gravel chips and ruled-out material (3D and decoration only, never text) |
| `--bone` | `#F2EFE6` | Primary text (13.1:1 on deep, 14.4:1 on pool, 7.3:1 on textured stone) |
| `--bone-2` | `#B9C6C1` | Secondary text (8.6:1 on deep, 9.4:1 on pool, 4.8:1 on textured stone) |
| `--slip` | `#E9E4D6` | Wet field slips: source passages and assay slips (ink 13.0:1) |
| `--ink` | `#16211F` | Text on slips and on gold |
| `--ink-2` | `#3B4A47` | Secondary text on slips (7.3:1) |
| `--slip-link` | `#2C5E5B` | Document names and links on slips (5.8:1) |
| `--gold` | `#E8B23A` | Accent: verified evidence and the primary action |
| `--gold-hi` | `#F6D27A` | Light edge of the gold sheen (ink 11.3:1) |
| `--gold-lo` | `#B9861F` | Dark edge of the gold sheen (ink 5.1:1, the lowest stop text ever sits on) |
| `--gold-tint` | `#F6E2A8` | Highlighted passage on slips (ink 12.9:1) |
| `--quartz` | `#9FC7C4` | Sources and links on water and stone (8.2:1 on deep, 4.6:1 on textured stone, always underlined there) |
| `--pyrite` | `#A39A6B` | The false flake: withdrawn claims (decoration; the word WITHDRAWN carries the meaning) |
| `--ember` | `#F07A63` | Real failures only. 6.0:1 on pool, so error notices always sit on pool, never on stone (3.6:1 fails). |

Why it fits: the product's job is separating a little true material from a lot of noise. Water and gravel are the noise; gold is the evidence; quartz marks where it came from. Every ratio above was measured, including text over the textured stone.

### Surfaces: nothing is a box

Every container takes its form from the river. No surface has a plain border, a uniform radius or a flat grey fill.

| Element | Becomes | How it is made |
|---|---|---|
| Page background | Water deepening as you scroll | A vertical blend from `--shallow` at the top to `--deep` and, by the footer, `--pool`. No section has a hard edge. |
| Section breaks | Waterlines | A single 1px `--bone` line at 12% opacity drawn as a long, slow sine wave; it drifts sideways by `transform` only. Replaces every divider band. |
| Text over the 3D scene (cover, pan captions) | A still pool | No box. The water shader takes the caption's screen rectangle as a uniform, darkens it toward `--pool` with a soft elliptical falloff and damps the ripples there to a fifth, so the words sit on calm water. Fallback without WebGL: a feathered radial blend of `--pool` at 85% behind the text. |
| Cards and panels (answer, console, notices, assay base) | River stones | `--stone` fill under the [Ganges River Pebbles](https://polyhaven.com/a/ganges_river_pebbles) texture at 6% opacity (never more: at 10% secondary text fails AA). Elliptical, slightly uneven corner radii, three variants so no two neighbouring stones match. A wet sheen: a 1px top-edge highlight in `--bone` at 10% and a soft inner shade along the bottom. Depth: one soft drop shadow toward the water (`0 18px 40px -18px`, near-black teal at 70%). No borders. |
| Source passages, assay slips | Wet field slips | `--slip` with an irregular, slightly torn-looking radius (a few px, never a clip-path polygon), a 1° resting tilt, and a faint caustic light pattern sliding across at 8% (a 256px tileable caustic WebP on a pseudo-element, moved by `transform`). Highlighted lines in `--gold-tint`. |
| Inputs (question box) | A pool cut into the stone | Recessed: `--pool` fill, an inner shadow along the top edge, no border. Gold caret. Focus: a gold ripple ring expands once from the field (scale and opacity), then a steady 2px `--gold` ring stays for accessibility. |
| Primary buttons | Gold nuggets | A metallic gradient from `--gold-hi` to `--gold-lo` with `--ink` text, a pill with uneven radii. Hover: a band of light sweeps across once (a pseudo-element moved by `transform`). Pressed: sinks 1px and the gradient darkens. |
| Secondary buttons and links | Quartz | Links in `--quartz`, underlined. Secondary buttons: quartz text on a pool-recessed pill with a 1px quartz ring at 50%. |
| Citation chips | Gold flakes | Small chips with uneven radii, the same gold gradient, `--ink` text. The active one brightens and its sheen moves. |
| Withdrawn claims | Pyrite | Struck-through text with a dull `--pyrite` flake chip reading WITHDRAWN. |
| Trace tabs | Stepping stones | Ten small stones across a thin waterline; the panel below is a stone slab. The active stone lifts 2px and gains a gold inner rim. |
| Navigation | A river gauge | The depth gauge: `--bone` hairline ticks on the water, the active tick filled gold with its label. |
| Capacity notices | A stone with gold rim light | A river stone with a 1px inner `--gold` rim at 40% and a small flake mark. |
| Error notices | A dark pool | `--pool` slab with an ember title and a 1px ember inner ring. |
| Loading placeholders | Light on the water | Caustic light passing over a stone instead of grey bars. |
| Footer | The riverbed | `--pool` with the pebble texture at 6%. |
| Browser surfaces | Same world | Text selection gold with ink text, caret gold, scrollbar thumb `--stone` on a `--deep` track, focus ring 2px `--gold` at 2px offset. |

The CSS surfaces reuse the riverbed WebP the 3D scene already ships, so stones cost no extra download. The caustic tile is the only new image (budgeted in section 7).

## 4. Typography

| Use | Face | Weights | Why |
|---|---|---|---|
| Headlines and body | Bricolage Grotesque (Google Fonts, variable weight, width and optical size) | 400 to 800 | A grotesque with grit; its weight and width axes move with the water on the cover. |
| Counters, step labels, figures | Big Shoulders Display (Google Fonts) | 700, 800 | Tall, condensed figures like an assay office's stamped numbers; 6,970 reads at a glance. |
| Quoted source text | Source Serif 4 (Google Fonts) | 400 | Source passages are set like the document page they came from. |

Scale (rem, 16px base): 0.8125 label, 1 body, 1.3125 lede, 1.75 h3, 2.75 h2, 4.75 h1 (`clamp(2.75rem, 6.2vw, 4.75rem)`), 10 for counters. Body line-height 1.6 on dark; headlines 1.0 with -0.02em tracking.

Text technique per section:
- Cover: kinetic headline. The two lines rise out of a mask in CSS (no SplitText, so the headline paints with the page and stays the LCP), and "gold" is set in `--gold`.
- The pan: sticky storytelling. A pinned caption, resting in a still pool, shows the step number in Big Shoulders, its `step_name` decoding from scrambled characters (ScrambleText), and one line on what the step did. The counter beside it rolls like an odometer.
- Specimen: highlight as you read. Claims take a gold underline as they enter the viewport.
- Assay (measured): numbers that move, and the TARGET 80% · NOT MET stamp lands once on the slip.
- Ask: four example questions, written for this site, sit under the pool as recessed buttons.
- Source: a marquee of the stack on a slow constant loop.

All final states are real DOM text. The canvas is `aria-hidden`; every fact it shows also exists as text.

## 5. Layout

- Grid: 12 columns, max content width 1200px, 24px gutters.
- Spacing scale (px): 4, 8, 12, 16, 24, 32, 48, 72, 112, 160. More space above a heading than below it.
- Breakpoints: 360, 640, 1024 (full 3D and the depth gauge appear), 1440.
- One fixed full-viewport `<canvas>` sits behind the first part of the page. HTML sections scroll over it, and the canvas dims to 20% behind the later sections instead of disappearing, so the water is always there and the stones look like they rest in it.
- Navigation: the depth gauge down the right edge, like a river's measuring staff: ticks for Cover, the ten steps, Specimen, Assay, Ask and Source. The active tick fills gold and shows its label. Below 1024px it becomes a row of small stones under the top bar.

Sections, top to bottom:
1. Cover (`#cover`). The pan fills the right two-thirds, seen from above at 35°. Headline, lede and the question pool on the left, resting in a still pool of the scene's own water.
2. The pan (`#pan`, steps 1 to 10). A pinned stage about 1000vh tall. The canvas fills the viewport, the caption holds the left third in its still pool, the counter sits bottom left. Beats in section 6.
3. Specimen (`#specimen`). A waterline, then the recorded answer on a river stone with gold flake citations; the source passage slides out beside it on a wet field slip with the cited line in gold tint.
4. Assay (`#measured`). A waterline, then the measured runs as wet assay slips laid on one wide stone (four since run_rep_b on 2026-11-05): answer precision as "purity", with recall, context scores and times beside it. The stamp lands on the middle slip; the variance note sits on the water below.
5. Ask the documents (`#ask`). A waterline, then the console: one large stone with the question pool cut into it. Calm on purpose: it is a tool.
6. Source (`#source`). The riverbed footer: marquee, links, checks, and one line crediting Poly Haven for the scanned light and surfaces.

Phones: the same pinned pan with about 700 chips (one per 10 pages), no caustics and no pan-steel or riverbed detail maps; the camera backs off on tall screens so the whole pan fits. The caption and odometer stack above and below the pan. The section stones under the top bar replace the gauge.

## 6. Motion and scroll story

Library split:
- Lenis runs smooth scrolling, driven by GSAP's ticker (`lenis.on('scroll', ScrollTrigger.update)`, `gsap.ticker.add(t => lenis.raf(t * 1000))`, `gsap.ticker.lagSmoothing(0)`). Gauge links scroll through `lenis.scrollTo`.
- The pan stage is a tall track with a `position: sticky` pin (cheaper than a GSAP pin). ScrollTrigger writes its progress into a shared mutable object (`web/lib/stage.ts`); the React Three Fiber scene reads it in `useFrame` and eases toward it, so scrolling never re-renders React. Only the beat index (11 values) is React state.
- ScrambleText decodes each step's title; `useGSAP` scopes and cleans up every trigger and tween.
- React Three Fiber renders the scene without drei: three's `HDRLoader` loads the 256×128 river HDRI as `scene.environment`, and a small governor lowers the pixel ratio when frames drop, then hands over to the flat steps after three slow 2-second windows in a row.
- The caption's still pool: a small hook measures the caption's rectangle on resize and scroll and passes it to the water shader as a uniform.

Scroll story, with progress through the pinned stage:
- 0%, cover. Still water over a bed of gravel. The cursor's position drives ripples in the water shader, and the pan tilts toward it by at most 5°. Caustic light moves slowly across the gravel.
- On load, the pour: 6,970 chips fall into the pan over 2.6 s, one document after another, so the cover already shows gravel under still water. 0 to 8% of the stage holds the count, 6,970, and "35 documents, 6,970 pages". Hovering the gravel (cover and pour only) highlights one document's wedge and names it with its page count.
- 10 to 20%, plan and route (steps 1 and 2). The question types into the caption. The water swirls; chips from routed documents rise to the top and catch the light, the rest sink and darken to `--gravel`.
- 20 to 35%, candidate pages and survey (steps 3 and 4). The pan tilts and the first wash runs: unrouted gravel slides over the lip and out of frame. The counter drops to the real candidate count.
- 35 to 50%, gather and order (steps 5 and 6). A slow swirl sorts what is left into rings, the reranker's order from the centre outward.
- 50 to 65%, verify (step 7). The second wash. Chips turn over one by one; the passages that pass verification show gold on their underside, the rest wash out. The counter shows passages kept out of passages checked.
- 65 to 85%, write and check (steps 8 and 9). The flakes gather along the pan's ridge, one per kept page. When the recorded run withdrew a claim, its flake dulls to pyrite; the current run (19 of 19 claims held) withdrew none, so the caption explains the mechanism instead.
- 85 to 100%, cite (step 10). The remaining flakes lift toward the camera and line up, each labelled in the DOM with its document and page, then settle into the specimen's gold flake citations as the stage unpins.

Signature moment: the pan itself, reversible with scroll, with real counts at every step, ripples under the cursor, and the hover that names any document in the gravel. After a live query in the console, the gauge's step ticks open that answer's trace steps.

Other motion, all in the river's own vocabulary:
- Page load: a static poster of the pan is visible at once; the canvas fades in over it when ready.
- Stones arrive as if settling through water: they rise 16px with a slight blur clearing (opacity and `filter: blur` on a transform layer), once per stone.
- Waterlines drift sideways continuously and slowly (40s per cycle).
- Hover: stones lift 3px and their top sheen brightens; gold buttons and flakes get one sweep of light; gauge ticks lengthen.
- Specimen: the source slip slides out from under the answer stone with a 3° tilt that settles to 1°.
- Assay: the three slips start fanned at -6°, 0° and 6° on their stone and straighten as they enter; the stamp lands from 1.15 scale in 220ms.
- Focus: the gold ripple on the question pool.
- Easing `power3.out` for entrances, `none` for scrubbed timelines, `cubic-bezier(0.2, 0, 0, 1)` in CSS. Durations: 160ms hover, 260ms chips and stones, 420ms slips, 900ms counters.
- `prefers-reduced-motion`: no Lenis, no pinning, no WebGL, no drifting waterlines or sweeps. Stones, slips and gold keep their full look, at rest; counters show final values; the stamp is in place.

## 7. 3D and visual elements

- The pan: a shallow steel pan from a `LatheGeometry` profile with a riffle ridge on one side, brushed metal (`MeshStandardMaterial`, metalness 0.8, roughness 0.45). No model files.
- Water: one plane with a custom shader: gentle normal ripples, a cursor-driven ripple ring, a depth tint toward `--deep`, the still-pool region behind captions, and refraction faked by offsetting the gravel's colour.
- Gravel: one `InstancedMesh` of low-poly chips (a squashed icosahedron, 6,970 instances, about 700 on phones), per-instance colour across greys and teal-greys, so documents can be told apart on hover.
- Gold flakes: a second small `InstancedMesh` of thin irregular discs, high metalness, lit by the river HDRI so they catch light as they turn. Pyrite uses the same mesh in `--pyrite` with higher roughness.
- Caustics: a moving procedural caustic pattern projected onto the gravel from the light, in the gravel shader. Off on phones.
- Light: one cool key light from above, a low warm fill so the gold reads warm against the teal. No bloom; the highlights come from the material.
- Camera: a perspective camera on a path keyed to the timeline; no free orbit.
- Data: `web/data/corpus.json` holds the 35 document names and real page counts, exported from the local index. `web/data/recorded-run.json` holds one recorded run (2026-11-05) of a freshly written question, never a benchmark question: "How does the Basel framework treat credit valuation adjustment risk?". `scripts/record_run.py` keeps only public fields: the answer, its chunks, the limitations, the count at each step, the pages gathered, kept and cited, and a trimmed trace.
- Icons: an arrow, a check and a small flake mark in inline SVG.
- No photographs on the page itself; the real-world look comes from the scanned assets below.

### Scanned assets (Poly Haven, CC0)

All from [Poly Haven](https://polyhaven.com), licensed [CC0](https://polyhaven.com/license): free for any use including commercial, redistributable, no credit required (we credit them in the footer anyway). Each file is downloaded once at its 1K size, shrunk, and committed under `web/public/assets/`, so the site never loads from Poly Haven at runtime. `web/public/assets/SOURCES.md` records each file's source URL, author and the resize applied.

| Asset | Source | Used for | Shipped as | Size |
|---|---|---|---|---|
| River light | [Blau River](https://polyhaven.com/a/blau_river) HDRI by Andreas Mischok | Reflections on the gold flakes, the steel pan and nothing else; the visible background stays the page's water colour | Radiance `.hdr`, 256×128 | 105 KB |
| Riverbed | [Ganges River Pebbles](https://polyhaven.com/a/ganges_river_pebbles) by Amal Kumar | The pan's floor under the water (tinted toward teal) and the 6% texture on every river stone and the footer | WebP 512px: colour, normal (OpenGL), roughness | 38 + 70 + 11 KB |
| Pan steel | [Metal Plate 02](https://polyhaven.com/a/metal_plate_02) by Rob Tuytel | Wear and scratches on the brushed pan: normal and roughness only | WebP 512px: normal, roughness | 2 + 46 KB |
| Caustic light | Generated by our own script (procedural, no source asset) | The light sliding over wet slips, the waiting stone and the pan floor | Tileable WebP, 256px | 8 KB |

Rules for these assets:
- The 1K source files are far too heavy for the web (the Blau River 1K `.hdr` alone is 1.6 MB, the pebble set about 2.5 MB), which is why only the shrunk copies ship.
- `scripts/prepare_assets.py` does the download and resize once (OpenCV for the HDRI, Pillow for the WebP files) and generates the caustic tile, so anyone can reproduce every shipped file.
- Total budget for these assets: 430 KB; shipped 284 KB (measured). The riverbed colour map and the caustic tile load with the CSS (the stones need them at first view, about 80 KB); the rest loads with the 3D bundle after first paint, never before LCP.
- Phones load the HDRI, the riverbed colour map and the caustic tile only; the pan's steel and the riverbed's normal and roughness maps are skipped.
- Swapping an asset means rerunning the script with a new Poly Haven id and updating this table and `SOURCES.md`.

## 8. Components

| Component | Source |
|---|---|
| `SmoothScroll` | Custom wrapper around [Lenis](https://github.com/darkroomengineering/lenis) (MIT), synced to the GSAP ticker. |
| `PanStage` | Custom: GSAP ScrollTrigger pin and master timeline, the caption in its still pool, the odometer. |
| `PanScene` | Custom React Three Fiber scene ([R3F](https://github.com/pmndrs/react-three-fiber), MIT): pan, water shader, gravel and flake instances, camera path. Loaded with `next/dynamic` and `ssr: false`. |
| `Gravel`, `Flakes` | Custom `InstancedMesh` components driven by `corpus.json` and `recorded-run.json`. |
| `useStillPool` | Custom hook passing a caption's screen rectangle to the water shader. |
| Scene helpers | [drei](https://github.com/pmndrs/drei) (MIT): `PerformanceMonitor`, `AdaptiveDpr`, `Environment`, `useProgress`. |
| `KineticHeadline`, `ScrambleCaption` | Custom on GSAP [SplitText and ScrambleText](https://gsap.com/docs/v3/Plugins/) (GreenSock standard no-charge license, free for commercial use; confirm at gsap.com/standard-license before shipping). |
| Surface primitives: `Stone` (three radius variants), `Slip`, `Pool`, `Waterline`, `GoldButton`, `QuartzButton` | Custom CSS components implementing section 3's surface table; every other component is built from these, never from a bare box. |
| `Odometer`, `DepthGauge`, `AssaySlip`, `Stamp`, `Marquee` | Custom. |
| `CitedAnswer`, `TraceTabs`, `AskConsole` | From the flat build, rebuilt on the surface primitives (gold flake citations, stepping-stone tabs, the question pool). `CitedAnswer` is adapted from 21st's [Source Citation Rail](https://21st.dev/@rmahammad/components/source-citation-rail). |
| `StepStrip` | Custom phone version of the ten steps: a horizontal pinned row of stones. |

Considered and not used: 21st's [Scroll Morph Hero](https://21st.dev/@prashantsom75/components/scroll-morph-hero) (the instanced gravel does the same job with real data) and 21st's text scramble components (GSAP's ScrambleText covers it).

New dependencies: `gsap` 3.15.1, `@gsap/react` 2.1.2, `lenis` 1.3.27, `three` 0.187.0, `@react-three/fiber` 9.8.2 (needs React below 19.4; the app is on 19.3), `@react-three/drei` 10.7.9. No postprocessing package.

## 9. Experience

Flow: see the pan, watch a real question wash 6,970 pages down to its gold, read the recorded answer, check the assay, pan your own question.

- Loading: the cover shows a static poster of the pan (an inline SVG plus a small blurred image) as part of the first paint, with the headline already in its still pool. The canvas loads when the page is idle and fades in. Under the counter, "Pouring 6,970 pages" shows `useProgress` until ready, on a stone with caustic light passing over it.
- No WebGL, a lost context or a slow device: `PerformanceMonitor` lowers the pixel ratio first, then drops the caustics, then the chip count; if frames still fall below 30fps or the context is lost, the stage swaps to the flat row of step stones at the reader's current step. Stones, slips and gold look the same either way, because they are CSS.
- Asking: 8 to 500 characters, checked on submit with an inline hint under the pool in `--bone-2`. One question at a time; Cancel (a quartz button) stops it.
- Waiting: the water behind the console swirls gently, an elapsed clock counts on the stone, and one honest line explains the cold start and the 40-second to 3-minute query time.
- Result: the answer on a stone with gold flake citations, the source slip, the limitations list and ten stepping-stone trace tabs; the gauge's step ticks now open those tabs.
- Empty result: an empty pan with still water, and one line on the stone saying no source passage matched, with the API's coverage note.
- Capacity: a stone with gold rim light for the daily allowance (503 `AT_CAPACITY`) and another for the hourly limit (429), each with the time it frees up.
- Errors: a dark pool notice with an ember title, the status code, a plain message and a gold Try again button.
- 404: an empty pan, still water, one pyrite flake drifting, and "Nothing panned here" with a link home.

## 10. Quality bar

- Responsive from 360px phones to wide desktops; phones get a lighter pan and the row of step stones, designed for the width.
- Lighthouse performance 90 or higher. The 3D bundle loads with `next/dynamic` after first paint and never blocks LCP (the cover headline). Gravel and flakes are two draw calls. Pixel ratio capped at 1.75, lowered under load. Scanned and generated assets stay within their 430 KB budget (section 7), served from `web/public/assets/` with long cache headers.
- Surfaces stay cheap: textures and sheens are static layers; only `transform` and `opacity` animate (sweeps, ripples, drifting waterlines), and the blur on settling stones runs once on its own layer.
- `prefers-reduced-motion` keeps all content and the full surface look, and removes Lenis, pinning, WebGL and drifting motion.
- Semantic HTML, keyboard access to the gauge, chips, tabs and console, a visible focus ring (2px gold, 2px offset), AA contrast as measured in section 3, including text over the 6% stone texture. The canvas is `aria-hidden`; each step's caption is real text in reading order.
- 60fps: scroll writes one progress value, motion lives in shaders and instance matrices, and the DOM animates only transform and opacity.
