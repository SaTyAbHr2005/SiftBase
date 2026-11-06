---
name: SiftBase
description: One question runs down a rainforest stream of ten pools, and only the gold that holds is kept.
colors:
  gold: "#E8B23A"
  gold-hi: "#F6D27A"
  gold-lo: "#B9861F"
  gold-tint: "#F6E2A8"
  kingfisher: "#5DB8E3"
  silt: "#A8916F"
  ember: "#F07A63"
  shallow: "#12261A"
  deep: "#0B1A12"
  ink-deep: "#06100A"
  pool: "#07120C"
  stone: "#1C3326"
  gravel: "#5E6B60"
  mist: "#F2EFE6"
  mist-2: "#B9C4B4"
  slip: "#ECE7D8"
  ink: "#141C16"
  ink-2: "#3D4A40"
  slip-link: "#2D5C43"
typography:
  display:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "clamp(2.75rem, 5vw, 4.5rem)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.022em"
    fontVariation: "'wdth' 86"
  headline:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "clamp(2rem, 4.2vw, 2.75rem)"
    fontWeight: 750
    lineHeight: 1.05
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 90"
  title:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  lede:
    fontFamily: "Bricolage Grotesque, system-ui, sans-serif"
    fontSize: "clamp(1.0625rem, 1.6vw, 1.3125rem)"
    fontWeight: 400
    lineHeight: 1.6
  figure:
    fontFamily: "Big Shoulders, Bricolage Grotesque, sans-serif"
    fontSize: "clamp(4rem, 9vw, 8.5rem)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.01em"
    fontFeature: "'tnum'"
  label:
    fontFamily: "Big Shoulders, Bricolage Grotesque, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
  quote:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  stone: "34px 26px 38px 30px / 28px 36px 30px 40px"
  stone-b: "26px 40px 30px 36px / 36px 28px 40px 30px"
  stone-c: "40px 32px 26px 38px / 30px 40px 34px 28px"
  nugget: "24px 30px 22px 32px / 22px 28px 24px 30px"
  quartz: "22px 28px 20px 30px / 20px 26px 22px 28px"
  pool: "18px 24px 16px 26px / 16px 22px 18px 24px"
  pebble: "14px 18px 12px 20px / 12px 16px 14px 18px"
  slip: "7px 4px 8px 5px / 5px 8px 4px 7px"
spacing:
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "32px"
  xl: "48px"
  reach: "72px"
  section: "112px"
components:
  button-primary:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.ink}"
    rounded: "{rounded.nugget}"
    padding: "0.8rem 1.45rem"
  button-primary-sm:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.ink}"
    rounded: "{rounded.nugget}"
    padding: "0.5rem 1rem"
  button-secondary:
    backgroundColor: "{colors.pool}"
    textColor: "{colors.kingfisher}"
    rounded: "{rounded.quartz}"
    padding: "0.65rem 1.2rem"
  input-pool:
    backgroundColor: "{colors.pool}"
    textColor: "{colors.mist}"
    rounded: "{rounded.pool}"
    padding: "0.85rem 1.1rem"
  card-stone:
    backgroundColor: "{colors.stone}"
    textColor: "{colors.mist}"
    rounded: "{rounded.stone}"
    padding: "24px 26px"
  card-slip:
    backgroundColor: "{colors.slip}"
    textColor: "{colors.ink}"
    rounded: "{rounded.slip}"
    padding: "24px 26px"
  chip-flake:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.ink}"
    rounded: "{rounded.slip}"
    padding: "0.05rem 0.45rem"
  chip-pyrite:
    backgroundColor: "{colors.silt}"
    textColor: "{colors.ink}"
    rounded: "{rounded.slip}"
    padding: "0.1rem 0.5rem"
  nav-pebble:
    backgroundColor: "{colors.stone}"
    textColor: "{colors.mist-2}"
    rounded: "{rounded.pebble}"
    padding: "5px 12px"
  nav-pebble-active:
    backgroundColor: "{colors.gold}"
    textColor: "{colors.ink}"
---

# Design System: SiftBase

The public site in `web/` (Next.js): one long page and a 404. Product facts live in PRODUCT.md. This file records the Stream world as it shipped on 2026-11-06, read from `web/app/globals.css`, the components and the assets. It replaces the retired Gold Pan document; nothing from the pan, the gravel chips or the Three.js scene ships any more.

## Overview

**Creative North Star: "The Stream of Ten Pools"**

**Concept:** One real question runs down a rainforest stream of ten pools below a waterfall; each pool is one pipeline step and keeps less, and only the gold that holds is picked.

**Adjectives:** alive, patient, exacting, glinting, honest.

The page opens on a living photograph. Three photographs (the falls over terraced rock pools, one pool close up with silt and gold, a kingfisher lifting a gold nugget) are drawn in raw WebGL2 with depth parallax, pouring and rippling water, drifting mist, light shafts and gold glints. Scrolling dollies the camera down the pools through the ten trace steps, dives into a pool, and rises to the kingfisher. Every count on screen comes from the real index or one recorded run.

Below the story the page sits on deep moss. Nothing there is a plain box: text rests on wet slate stones, source text on wet field slips, actions and citations are gold nuggets and flakes, links are kingfisher blue, and slow waterlines replace dividers. Gold is reserved for evidence and for the actions that lead to it.

The site refuses the dev-tool default (black hero, gradient blob, three feature cards), the RAG-demo default (small grey citation numbers), and a static page: the scene moves like footage.

**Key Characteristics:**
- A pinned, scroll-scrubbed, reversible photographic scene carries the pipeline story.
- Deep moss ground, one bright accent (gold) that always means evidence or action.
- Every surface is a river material with irregular elliptical corners; no borders anywhere.
- Real numbers, rolled on odometers and counters, never invented.
- Every effect has a still fallback that keeps all content.

## Colors

A dark rainforest palette: moss and slate for the ground, mist for text, gold as the single earned accent, kingfisher blue for links, silt and ember held back for withdrawn claims and failures. Ratios below are measured against the flat token colours (WCAG 2.x formula).

### Primary
- **Picked Gold** (gold): primary actions (nugget buttons), citation flakes, the active gauge tick and pebble, the focus ring, the selection highlight, the caret and gold words in the headline. 9.3:1 on deep, 7.0:1 on stone; ink on gold 9.0:1.
- **Sunlit Gold** (gold-hi): the bright edge of the gold sheen, figures in the stream and console (odometer label, beat counts, waiting clock), footer column headings and warning hints. 12.3:1 on deep; ink on it 11.9:1.
- **Shadowed Gold** (gold-lo): the dark end of the sheen gradient only. Ink on it 5.4:1, the lowest stop any text sits on.
- **Gold Wash** (gold-tint): the highlight behind quoted source text on slips. Ink on it 13.6:1.

### Secondary
- **Kingfisher Blue** (kingfisher): every link on moss and stone, and the secondary (quartz) button text and rim. 8.1:1 on deep, 6.1:1 on flat stone, 8.6:1 on pool.

### Tertiary
- **River Silt** (silt): the pyrite chip that marks a withdrawn claim. Decoration; the word "Withdrawn" carries the meaning. Ink on it 5.8:1.
- **Ember** (ember): real failures only, as the title of an error pool and its 1px inner ring at 60%. 7.0:1 on pool.

### Neutral
- **Shallow Moss** (shallow): the top of the page gradient.
- **Deep Moss** (deep): the page ground through the middle, the browser theme colour, the scrollbar track.
- **Forest Floor** (ink-deep): the bottom of the page gradient and the solid backing of the top bar and the mobile section row.
- **Still Pool** (pool): recessed surfaces: inputs, the secondary button, example chips, the waiting panel, error pools, nested panels inside the console, the trace output.
- **Wet Slate** (stone): the river stones (answer, beats, assay, console, notices, trace panel), under the riverbed texture.
- **Gravel** (gravel): decoration only (the ring of a cited-but-unreturned flake). 2.4 to 3.5:1, never text.
- **Mist** (mist): primary text. 15.6:1 on deep, 11.8:1 on flat stone.
- **Damp Mist** (mist-2): secondary text, ledes, labels, hints. 9.9:1 on deep, 7.5:1 on flat stone.
- **Field Slip** (slip): wet field slips for source passages and assay results.
- **Slip Ink** (ink): text on slips and on gold. 14.1:1 on slip.
- **Faded Ink** (ink-2): secondary text on slips. 7.5:1.
- **Slip Green** (slip-link): document names and the "not met" stamp on slips. 6.2:1.

### Named Rules
**The Earned Gold Rule.** Gold appears only on verified evidence, on the actions that lead to it, and on the current position (gauge tick, pebble). Never on decoration that means nothing.

**The Pool For Errors Rule.** Error notices are always a still pool with an ember title and ring. Ember text never sits on the textured stone.

**The Gravel Is Not Text Rule.** Gravel never carries words; at 2.4 to 3.5:1 it fails AA.

## Typography

**Display Font:** Bricolage Grotesque (variable, wdth and opsz axes), with system-ui
**Body Font:** Bricolage Grotesque, with system-ui
**Figures and Labels Font:** Big Shoulders (700 and 800), with Bricolage Grotesque
**Quote Font:** Source Serif 4, with Georgia
**Code:** the system monospace stack (ui-monospace, Cascadia Mono, Consolas)

All three faces are Google Fonts loaded through `next/font`. **Character:** a warm, slightly condensed grotesque that narrows its width axis as it grows, tall condensed figures for every number, and a book serif only where the page quotes a source.

### Hierarchy
- **Display** (800, clamp(2.75rem, 5vw, 4.5rem), 0.95, wdth 86%): the cover headline only. "Only the *gold*" sets its key word in gold.
- **Beat title** (780, clamp(2.25rem, 4.6vw, 4.25rem), 0.98, -0.03em, wdth 84%): the pinned caption title in the stream.
- **Headline** (750, clamp(2rem, 4.2vw, 2.75rem), 1.05, wdth 90%): section headings.
- **Title** (700, 1.375rem to 1.75rem): beat headings in the still layout, the question above an answer.
- **Body** (400, 1rem, 1.6): running text, max 72ch in answers and 75ch in notes.
- **Lede** (400, clamp(1.0625rem, 1.6vw, 1.3125rem)): under section headings, max 62ch (40ch on the cover).
- **Figure** (Big Shoulders 800, tabular): the odometer (clamp(4rem, 9vw, 8.5rem); clamp(3.25rem, 14vw, 5rem) under 1024px), assay purity (clamp(3.25rem, 5vw, 4.5rem)), the waiting clock (2.75rem), beat numbers (2.5rem).
- **Label** (Big Shoulders 700, 0.75 to 0.9375rem, 0.08 to 0.1em tracking, uppercase): small headings that name a group (footer columns, "The trace, step by step"), page numbers on slips, the odometer unit, the marquee.
- **Quote** (Source Serif 4 400, 1rem, 1.6): source passages on slips.

### Text technique per section
- **Cover:** each headline line rises out of a mask (900ms, second line 120ms later).
- **Stream:** the beat title decodes with GSAP ScrambleText (0.6s) on every beat change; the supporting line settles in from a 6px blur; the count rolls on an odometer; a ten-pebble rail marks the step.
- **The answer:** highlight as you read: each cited claim gets a gold underline drawn by a scroll-linked view timeline.
- **The assay:** purity counts up once on entry; the fanned slips straighten as they scroll in; the "Target 80% · not met" stamp lands.
- **Ask:** a gold ripple runs once round the question field on focus; a running clock while a query waits.
- **Footer:** a marquee of the stack drifts sideways.

### Named Rules
**The Numbers In Big Shoulders Rule.** Every figure is Big Shoulders with tabular numerals. Words stay in Bricolage.

**The Serif Means Source Rule.** Source Serif 4 appears only on quoted source text.

## Layout

A single column of full-bleed chapters. Content sits in a centred wrap (`min(1200px, 100% - 48px)`). The cover is 100svh with copy on the left moss slope (max 600px) and the falls right of it. The stream track is 1100svh tall when the scene runs; a sticky 100svh pin holds the caption (left, 22svh from the top) and the odometer with its rail (left, 8svh from the bottom). Sections below use 112px top and 48px bottom padding, a 48px gap under each heading block, and a waterline 72px above content.

Spacing steps observed: 8, 16, 24, 32, 48, 72 and 112px. Fixed chrome: a top bar (wordmark, Source, Ask) and a section gauge on the right edge from 1024px; below 1024px a scrollable row of pebble links under the bar.

**Breakpoints:** 520px (Source link and "a question" appear), 768px (the caption shade switches from a left-side wash to a full-width vertical wash), 1024px (gauge replaces pebble row; answer and sources go to a 1.5fr / 1fr grid with sticky sources; caption moves from 15svh to 22svh).

**Wireframes:**
- **Cover:** living photo of the falls full bleed; left: two-line display headline, lede, question field with "Pan it" nugget, hint; bottom left: a falling gold scroll cue.
- **Stream:** pinned. Caption top left, odometer and pebble rail bottom left, water and photo behind. Eleven beats: the falls, then the ten trace steps.
- **The answer:** stone with the recorded answer and gold flakes (left), source pebbles and a wet slip with the cited passage (right), then run meta and the gaps the answer reported.
- **The assay:** one wide stone with five fanned slips (one per run), then two short paragraphs on variance.
- **Ask:** one large stone with the question pool, example chips, and the answer, waiting, notice or error state.
- **Source (footer):** the riverbed: marquee, heading, three columns (Code, Stack, Checks), credit line.
- **404:** the pool photo dimmed full bleed, one stone with "This page washed downstream." and a nugget back to the falls.

## Elevation & Depth

Depth comes from the photographs and from wet material, not from a shadow scale. Raised things (stones, slips, nuggets) carry a soft drop toward the water; recessed things (pools, inputs) carry inner shade. Stones nested inside the console stone become pools, so a stone never sits on a stone.

### Shadow Vocabulary
- **Drop** (`box-shadow: 0 18px 40px -18px rgb(2 8 4 / 0.75)`): under every river stone and the still-layout photographs.
- **Wet** (`inset 0 2px 0 rgb(242 239 230 / 0.24), inset 0 0 0 1px rgb(242 239 230 / 0.06), inset 0 18px 30px -18px rgb(242 239 230 / 0.12), inset 0 -18px 28px -16px rgb(2 10 5 / 0.65)`): a bright film on the top lip and a shadowed underside; on stones, pebbles and stepping stones.
- **Slip lift** (`0 14px 30px -16px rgb(2 8 4 / 0.8), inset 0 -2px 0 rgb(20 28 22 / 0.06)`): wet field slips.
- **Nugget** (`inset 0 1px 0 rgb(255 255 255 / 0.45), 0 12px 24px -12px rgb(2 8 4 / 0.85)`): gold buttons.
- **Recess** (`inset 0 3px 8px rgb(0 0 0 / 0.5), inset 0 -1px 0 rgb(242 239 230 / 0.06)`): the question pool; lighter variants on chips and the waiting panel.

### Named Rules
**The Wet Not Lifted Rule.** Every raised surface is wet slate or wet paper: a lit top lip and a dark underside. There is no generic card shadow.

**The No Stone On Stone Rule.** Inside a stone, panels are pools cut into it.

## Shapes

No border and no uniform radius anywhere. Every surface uses an elliptical radius with four different corners, so each reads as a worn stone or torn paper. Stones come in three variants (stone, stone-b, stone-c) and neighbouring beats cycle through them. Slips use a tight 4 to 8px irregular radius and rest at a 1deg tilt. Indicator marks (gauge ticks, rail pebbles) are small uneven ovals. Dividers are a single 1.2px mist line at 12% drawn as a slow sine. The footer's top edge is one wide uneven curve. Iconography is limited to the wordmark: two wave strokes and a gold dot drawn in inline SVG.

### Named Rules
**The Nothing Is A Box Rule.** Use one of the recorded irregular radii; never a plain border or a single-value radius.

## Components

### Buttons
- **Gold nugget (primary):** the sheen gradient (`160deg, gold-hi, gold 46%, gold-lo`) with ink text, 700 weight. Hover: a band of light sweeps across once (600ms). Pressed: sinks 1px and darkens to 90%. Busy: `aria-disabled` desaturates and shows a progress cursor. A small variant sits in the top bar.
- **Quartz (secondary):** a still pool with kingfisher text, underlined, and a 1px kingfisher inner rim at 50% that goes full on hover. Used for Cancel and "See the recorded answer".
- **Example chips:** pool fill with mist text; hover turns the text gold-hi and adds a faint gold rim.

### Chips
- **Gold flake (citation):** a small sheen chip reading "p12" after each claim. Hover scales to 1.08; the active one scales to 1.1 with a pool gap and a gold-hi ring, so the state is never colour alone. A page cited without a returned passage is a bare flake: no fill, mist-2 text, gravel ring.
- **Pyrite:** silt chip, uppercase "Withdrawn", beside struck-through text.

### Cards / Containers
- **River stone:** stone fill under the Poly Haven riverbed texture: 95% solid where text sits, thinning to 48% at the rim. Wet plus drop shadow. Internal padding 24 to 48px by size.
- **Wet field slip:** slip fill, ink text, caustic light sliding across at 4% (22s loop), 1deg tilt. Source slips slide in from the left (420ms).
- **Notices:** capacity and rate-limit notices are stones with a gold inner rim at 40%; errors are pools with an ember ring.

### Inputs / Fields
- **Question pool:** recessed pool, mist text, gold caret, placeholder in mist-2. Focus: a gold ring ripples out once (700ms), then the steady 2px gold focus outline remains.

### Navigation
- **Top bar:** fixed, solid forest floor behind its text fading to clear. Wordmark, a "Source" link in mist (not kingfisher), and a small gold nugget "Ask".
- **Depth gauge (from 1024px):** a column of ovals on the right edge; hover or focus widens the oval and slides its label in; the current section's oval is gold and wider.
- **Pebble row (under 1024px):** small stones under the bar; the current one turns gold with ink text.

### Stream caption and odometer (signature)
The pinned caption (scrambled beat title, step name in code, settling line), the odometer whose digit strips roll 900ms to each real count, and a ten-pebble rail: passed pebbles pale, the current one gold and wider.

### Stepping stones (trace tabs)
Ten small stones across a thin waterline. Arrow keys, Home and End move between them. The selected stone lifts 2px with a gold inner rim; the panel below shows the step's description and its JSON output in a pool.

## Do's and Don'ts

### Do:
- **Do** reserve gold for evidence, primary actions and the current position.
- **Do** put text over the photographs only on the moss-slope side or the bottom edge, under the shade gradient, never in the middle of the frame.
- **Do** use Big Shoulders with tabular numerals for every figure, and show the real number from the index or the recorded run.
- **Do** build every new surface from the river materials: stone, slip, pool, nugget, flake, waterline.
- **Do** give every motion a still state: under reduced motion all animations and transitions stop and the content stays.
- **Do** use the one easing (`cubic-bezier(0.2, 0, 0, 1)`) and 160ms for state changes.

### Don't:
- **Don't** add borders, single-value radii or flat grey fills.
- **Don't** set citations as small grey numbers; citations are gold flakes that open their source.
- **Don't** put ember text on stone or use gravel for text.
- **Don't** put a stone inside a stone; nest pools instead.
- **Don't** add a gradient blob hero, three identical feature cards or glassmorphism.

## References

| Reference | What was borrowed |
|---|---|
| [Monogrid on Awwwards](https://www.awwwards.com/inspiration/3d-webgl-scroll-monogrid-com) | Scroll-scrubbed camera moves with text passing over the canvas: the pinned stream. |
| [Yale Law Journal](https://www.yalelawjournal.org) | Notes that open beside the text: a gold flake brings its source page up beside the claim. |
| [21st: Source Citation Rail](https://21st.dev/@rmahammad/components/source-citation-rail) | The citation interaction: marker and source in sync, arrow keys rove the sources, active state not by colour alone. |
| [Perplexity](https://www.perplexity.ai) | Anti-reference: the category's small grey citation numbers. |
| [Poly Haven: Ganges River Pebbles](https://polyhaven.com/a/ganges_river_pebbles) | The riverbed texture on every stone and the footer (CC0). |
| [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2) | The Small model (Apache-2.0), run locally, made the three depth maps. |
| [Google Stitch](https://stitch.withgoogle.com) | Generated the three photographs on 2026-11-06. |

## Motion and Scroll Story

**Libraries:** GSAP 3.15.1 with ScrollTrigger (scroll progress, cover progress, the fade-out past the stream) and ScrambleTextPlugin (beat titles), via @gsap/react 2.1.2; Lenis 1.3.27 for smooth scroll (lerp 0.11) driven by the GSAP ticker; raw WebGL2 for the scene (no Three.js); CSS keyframes and scroll-driven view timelines for everything else.

**Page load:** the falls photo paints with the page (fetch priority high). An inline script decides before first paint whether the scene can run. The scene loads when the browser is idle and fades in over the photo (900ms) after its first frame. The headline lines rise.

**Scroll story (eleven equal beats over the track):**
- Beats 0 to 3, the falls: the camera dollies from 1.04x to 2.3x into the pools with depth push; mist and light shafts drift; the falls pour.
- Dive (7% of the track, centred on beat 4): a circular ripple crosses the screen and the view sinks into the pool.
- Beats 4 to 8, the pool: silt flows over the stone lip along the pool's flow direction while the gold stays and glints; zoom 1.06x to 1.45x.
- Rise (centred on beat 9): a horizontal ripple and the view rises to the kingfisher.
- Beats 9 to 10, the kingfisher: mostly zoom (1.04x to 1.32x) with a fifth of the sway and push, because strong parallax tears the wing edges.
- Past the stream the water fades out over the next 65% of a viewport and stops rendering.

**Signature moment:** the reversible pinned stream with pointer sway (the camera glides toward the pointer at 2.5% of the frame), the ripple dive and rise, the odometer and the ten-pebble rail with the recorded run's real counts.

**Hover and state:** 160ms for colour, lift and scale; 600ms nugget sheen; 420ms slip slide; 900ms headline rise, odometer roll and scene fade; 520ms beat-line settle. Ambient loops: caustic light 22s (slips) and 12s (waiting panel), waterlines 40s, marquee 48s, scroll cue 1.8s. One easing everywhere: `cubic-bezier(0.2, 0, 0, 1)`. The shader smooths scroll with the same glide at any frame rate.

## 3D and Visual Elements

- **The stream scene:** one full-screen fragment shader over three 1376x768 photographs. Each photo has a depth map (parallax, three refinement steps) and a water mask (R still water that ripples, G falling water that pours along a direction, B gold that tints and glints). Mist, light shafts, a vignette and a value-noise texture are computed in the shader. The canvas is capped near 1.2 million pixels.
- **Still photographs:** the same three WebP photos, shown in the cover, in the still stream layout and (dimmed) on the 404.
- **Textures:** the riverbed WebP on stones and the footer; a generated 256px caustic tile on slips and the waiting panel.
- **Icons:** none beyond the inline SVG wordmark.
- **Provenance:** every shipping raster is listed with source and licence in `web/public/assets/SOURCES.md` and is rebuilt by `scripts/prepare_assets.py`. Assets total 897 KB.

## Experience

- **Main flow:** read the cover, scroll the stream, read the recorded answer and pick its citations, read the assay, then ask. A question typed on the cover is checked (8 characters or more), the page scrolls to the console and the console runs it.
- **Waiting:** a still pool with caustic light, a running clock, the expected wait (about a minute to wake the server, then 40 seconds to 3 minutes) and a Cancel button. A polite live region announces the state.
- **Done:** focus moves to the result: the answer with gold flakes and source slips, status, server time, passages checked, gaps reported, and the ten-step trace as stepping stones.
- **Expected limits:** daily allowance used up (gold-rimmed stone, the time it frees up, link to the recorded answer); too many questions (gold-rimmed stone with the time); API not connected yet (gold-rimmed stone).
- **Error:** an ember-ringed pool with the HTTP status, the message and a gold "Try again".
- **Empty:** a slip explains when an answer cites no page or a cited passage was not returned.
- **404:** "This page washed downstream." with a nugget back to the falls.

## Quality Bar

- **Measured performance:** 145 fps at 1440x900 in the user's browser; under 1 ms of GPU time per frame on an RTX 3050. Assets 897 KB in total; the first-viewport photo (falls.webp) is 287 KB.
- **Fallbacks:** the scene gives way to the still photographs under `prefers-reduced-motion`, without WebGL2, on software-only GL (`failIfMajorPerformanceCaveat`), after 10 s of visible time without a first frame, on context loss, and when the governor sees three 2 s windows in a row under 24 fps (first at half resolution, then off). On fallback the reader is kept on the beat they were reading.
- **Accessibility:** skip link to the question box; semantic sections with labelled headings; the pinned caption is `aria-hidden` and the beats exist as real list items; roving keyboard focus in sources and trace tabs; a 2px gold focus ring at 2px offset; AA contrast for all text tokens (see Colors); descriptive alt text on the still photos; counters show the real value under reduced motion; Lenis is off under reduced motion.
- **Responsive:** from 360px phones to wide screens; the bar, section navigation, caption position, odometer size and photo shade each change at the breakpoints in Layout.
