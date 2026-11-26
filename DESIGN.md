---
name: SiftBase
description: A dark sorting table where a whole collection lies in stacks, pages fly out one by one, and only the ones that hold get highlighted, stacked and cited.
platform: desktop (Electron)
colors:
  ground: "#0B0D12"
  shell: "#11141B"
  raised: "#181C25"
  line: "#262C38"
  text: "#E8EAEE"
  text-2: "#A3AAB7"
  text-3: "#8A92A0"
  paper: "#EEE9DD"
  paper-ink: "#1A1C22"
  paper-dim: "#4A4B4F"
  highlight: "#D8F25B"
  highlight-ink: "#1B2400"
  pencil: "#8FB8FF"
  withdrawn: "#FF6B5E"
  partial: "#F2B84B"
  ok: "#6FD39B"
typography:
  display: "Hubot Sans Variable (wdth 75-125, wght 200-900)"
  ui: "Mona Sans Variable (wdth 75-125, wght 200-900)"
  data: "Martian Mono Variable (wdth 75-112.5)"
---

# SiftBase desktop: design

This replaces the old `web/` site design completely. Nothing from the Gold Pan or stream scenes carries over: no teal, no gold, no river, no bird.

## 1. Concept

**A night sorting table.** Your whole collection lies on a dark table as stacks of paper, one stack per document. Ask a question and pages fly out of the stacks one at a time, get looked at, and either fall back or get a highlighter stroke and join a neat pile. The answer is written from that pile, and every line points back to a page you can pull up and read.

The app opens on **Home**, a full-window landing page with no sidebar. Its opening shows how pages get onto the table: a page slides in from the left edge, a scan line passes down it and boxes every heading, paragraph, table and chart it finds, its passages lift off, and the page is filed onto the index pile, while the right half lists the indexer's seven real steps as they happen to that page. Scrolling down plays the rest of the story on the same 3D table, one section per stage, from stacks to cited answer. Buttons in Home's header open the workspace, and only then does the sidebar appear.

Adjectives: **exact, calm, physical, candid, quick.**

The world lends the app four things only: the palette (night table, paper stock, highlighter), type (a variable grotesque that can go wide or narrow), density (a working desktop tool, not a poster) and one signature move (the Sift replay you can scrub). Navigation, buttons, inputs, tables and menus stay standard desktop controls.

### It works for any collection

The table is drawn from the collection's real numbers, never from the training set.

| Collection | Table layout | Stack height | Labels |
|---|---|---|---|
| 1-12 documents | one arc of stacks | log scale against the collection's largest document, with a visible minimum | every stack labelled |
| 13-80 documents | 2-4 arcs, largest at the back | same | labels on hover, on routed stacks and in the side list |
| 81+ documents | dense grid of short stacks (tiles), camera higher | same, compressed | hover and search only; the list view is the main way in |

- Sheets drawn in flight are capped (candidates 240, picked pages 24, passages 120, kept 40, cited 24). Exact counts always show as numbers, with a "+1,412 more" chip when the cap cuts in.
- Long file names are cut in the middle (`Integrated Annual R…2025-26.pdf`) with the full name in the tooltip and the list.
- Edge cases each have a state: an empty collection, a single document, a one-page document, a document still indexing, a query that found nothing.

## 2. References

| Reference | What we take |
|---|---|
| [Igloo Inc](https://www.igloo.inc/) (Awwwards Site of the Year 2024, [case study](https://www.awwwards.com/igloo-inc-case-study.html)) | One continuous 3D scene whose camera moves between states instead of cutting between pages. Library to Ask is a camera move across the same table. |
| [Lusion](https://lusion.co/) (Site of the Year 2023) | Objects with weight: sheets accelerate, overshoot a little and settle. No floaty fades. |
| [Linear](https://linear.app/) | Desktop shell density: slim rail, quiet chrome, ⌘K for everything, keyboard first. |
| [Raycast](https://www.raycast.com/) | The question box as the main control, always one key away. |
| [Readwise Reader](https://readwise.io/read) | Highlighter marks on real document text, which is how kept evidence reads in the page reader. |
| [Langfuse](https://langfuse.com/) trace view | Steps as a timed waterfall. Our timeline shows the ten real trace steps with their measured durations. |
| [Agent Trace on 21st.dev](https://21st.dev/@n1m4mz/components/agent-trace) | A replay playhead you drag to scrub a run. We build our own from that idea and drive the 3D scene with it. |

## 3. Colour system

The scene is someone at a desk at night with one cool overhead light: dark room, bright paper. That scene sets the dark theme. The only saturated colour is highlighter, and it means one thing: this was kept as evidence.

| Token | Hex | Job |
|---|---|---|
| `ground` | #0B0D12 | The table and the window background |
| `shell` | #11141B | Rail, top bar, drawers |
| `raised` | #181C25 | Inputs, menus, hovered rows |
| `line` | #262C38 | 1 px dividers and input borders |
| `text` | #E8EAEE | Main text |
| `text-2` | #A3AAB7 | Secondary text |
| `text-3` | #8A92A0 | Meta text such as timings and counts |
| `paper` | #EEE9DD | Paper stock: 3D sheets, the answer page, the page reader |
| `paper-ink` | #1A1C22 | Text on paper |
| `paper-dim` | #4A4B4F | Pages and stacks ruled out of a query |
| `highlight` | #D8F25B | Kept evidence, the citation underline, focus rings, the primary button |
| `highlight-ink` | #1B2400 | Text on highlight |
| `pencil` | #8FB8FF | Work in progress: a query running, models online, the playhead |
| `withdrawn` | #FF6B5E | A claim struck out, errors, models offline |
| `partial` | #F2B84B | Coverage gaps ("not fully supported"), capacity warnings |
| `ok` | #6FD39B | A finished step, an index gone live |

Rules: highlighter is never decoration; state colours appear only where they carry meaning; no gradients, no glow halos, no glass. Text selection is highlighter on highlight-ink, the caret is pencil, scrollbars are thin `line` on `shell`. Contrast ratios for every text pair are listed in section 10.

## 4. Typography

All three faces ship inside the app as woff2 files from Fontsource (SIL Open Font License). Mona Sans and Hubot Sans are GitHub's open type family; Martian Mono is Evil Martians' open mono. All three have a width axis, which the app uses instead of extra font files.

- **Hubot Sans** for display and numbers: collection names, counters, step names. Big counts are set wide (wdth 118-120, wght 760) and step names narrower (wdth 88-92, wght 650), so the funnel reads at a glance.
- **Mona Sans** for all UI and reading text.
- **Martian Mono** (wdth 87.5) only for data: page references (`p113`), file names, timings, keys.

| Role | Face | Size / line | Weight |
|---|---|---|---|
| Collection name on Home | Hubot Sans wdth 118 | 44/44 | 760 |
| Counter (documents → routed → pages → kept → cited) | Hubot Sans wdth 120 | 40/40 | 760 |
| Screen title | Hubot Sans wdth 108 | 20-28 | 700-760 |
| Step label | Hubot Sans wdth 88 | 13/16 | 650 |
| Answer body | Mona Sans | 15/24, 68ch max | 430 |
| UI default | Mona Sans | 13.5/19 | 450 |
| Small UI | Mona Sans | 12/16 | 550 |
| Data | Martian Mono wdth 87.5 | 10.5-11.5/16, tabular | 450-500 |

Text techniques, one per place:

- **Numbers that move:** stage counters roll as odometer digits when the replay passes them.
- **Highlight as you read:** in the page reader, the kept passage gets a highlighter stroke swept left to right (a clip-path reveal) when the page opens.
- **Struck in red pencil:** a withdrawn claim gets a hand-drawn strike line, then dims.
- **Typewriter:** answer lines appear line by line during the answer step of a replay, then stay as plain text.

All of it ends as real, selectable text. Under reduced motion it is simply there.

## 5. Layout

Window: default 1440×900, minimum 1100×700. Spacing scale (px): 4, 8, 12, 16, 24, 32, 48, 64. Corner radius: 8-9 for controls, 12 for rail items, 14 for floating panels, 4-6 for paper. A frameless window with our own 40 px title bar (Windows caption buttons through Electron's title bar overlay).

**Floating panels.** On the three screens with the 3D scene (Home, Ask, Library), every panel floats 12 px in from the edges over the scene: translucent `shell` (84%) with an 18 px background blur, a 1 px `line` border, a soft drop shadow and a faint top highlight. The blur is there so text stays readable over moving sheets, not as decoration. History and Settings are solid screens with no scene behind them.

**Two modes.** Home is a landing page that fills the window under the title bar, with no sidebar. The workspace (Ask, Library, History, Settings) has the sidebar. "Open workspace" (or Ask this collection / Index a folder on the page) enters the workspace, and the rail slides in from the left. Clicking the SiftBase name in the title bar goes back to Home.

**Workspace rail.** 80 px on the left: Ask, Library, History, Settings, each with icon and short label (Ctrl+1-4). The active item sits on a raised pill that slides to the new item when you switch. The rail's foot holds three status lines: local API (running / starting / stopped), models (online / offline / at capacity until a time) and the free model allowance left today.

**Home** (what the app opens on). One page that scrolls, with the 3D scene fixed behind it.

- Header (52 px, floating, stays pinned while scrolling): only the API and model status on the left and the primary "Open workspace" on the right. No collection picker and no screen links: Home always shows the most recently used collection, and choosing collections and screens happens in the workspace.
- Opening (one screen tall). Left: waiting pages queue off the left edge; one page at a time slides to the centre, is scanned and filed onto the index pile in front of it. A caption top left says what it shows, and a "Scroll to see how a question is answered" hint sits bottom centre until you scroll. Right panel (46%, up to 620 px): the collection name, its status (live / indexing now, date indexed, a "real index" or "synthetic" tag), Ask this collection (primary) and Index a folder, four counts (documents, pages, passages, page vectors), then "Reading a page" with the current file and page, a one-line note, and the seven steps. Each step shows its real indexer name and number (`1/7 Reading pages` … `7/7 Saving the index`), a detail line for this page, and a state: waiting, running (spinner), done (check) or skipped (dimmed, for example "No charts on this page"). The vector step shows 48 small bars changing while it runs. While a real indexing job runs, the steps follow the job instead.
- Story sections (each one screen tall), a floating card on the left with a short heading, one or two lines and two numbers that count up; the scene on the right plays that stage (section 6 has the table). The numbers come from the selected collection and its latest run, so the story works for any collection.
- Closing: "Start with a question or a folder", with Open workspace and Index a folder.

**Ask** (the main working screen)

- Top bar (52 px, floating): collection picker (name, document count, page count) and the question field with Ask (Enter) and ⌘K.
- Centre: the 3D table, full bleed behind everything.
- Right drawer (440 px, floating, resizable 360-640): the answer on paper stock with citation chips, then "Not covered" (the API's limitations), then the sources grouped by document.
- Bottom (104 px, floating): the run timeline. Ten segments sized by each step's real duration, each with its stage name and its count (documents routed, candidate pages, passages checked, kept, claims, pages cited). A playhead scrubs the replay.
- Wide counters sit top left over the scene: documents → routed → pages → kept → cited.

**Library**

- Left list (320 px): collections with document and page counts and status (live, indexing 62%, failed). "Index a folder" button and drag-and-drop for a folder or ZIP.
- Centre: the same 3D table showing the selected collection's stacks.
- Right (360 px): the document list (name, pages, type), sortable and searchable. At 81+ documents this list is the main view.

**History**

- Table of past questions: question, collection, time, duration, documents used, claims kept / withdrawn, status. Newest first, searchable.
- Right panel (480 px): the selected run's trace as a waterfall (ten steps, durations, counts, model used) with "Replay on the table" and "Open answer".

**Settings**

One 720 px column of grouped rows: model providers and keys (stored in the local `.env`, never shown back in full), the writer and judge models (free by default, or the user's own paid model if they added one), provider order, private mode, daily usage from the spend ledger, data folder.

## 6. Motion and the Sift

An app has no scroll story. Here the story is the run, and the user controls its playback.

**The Sift (signature moment).** One GSAP timeline per answered query, built from the real response and scrubbed by the timeline's playhead. Each trace step is one act:

| Step | On the table |
|---|---|
| query_planning | The question lands as a paper slip at the front of the table |
| routing_guard | Routed stacks lift and stay bright; every other stack sinks and dims to `paper-dim` |
| candidate_pages | Pages fly out of the routed stacks one by one into a loose cloud above the table |
| page_survey | The picked pages come forward into a fan; the rest fly home to their stacks |
| element_retrieval | Passages peel off the fanned pages as paper strips |
| element_triage | Strips line up in a queue, best first |
| element_verification | Each strip crosses a pencil-blue scan line: kept strips take a highlighter stroke and stack neatly; rejected strips drop and fade |
| answer_generation | The answer page rises; the kept pile feeds into it; answer lines type into the drawer |
| answer_verification | Claims tick; a withdrawn claim is struck in red pencil |
| citation_render | Cited pages fly to a neat stack beside the answer, each with a tab (`report.pdf p113`) |

Clicking a citation chip lifts that page off the cited stack into the page reader, with its passage highlighted.

**Honest timing.** `/query` is blocking, so the app cannot show stages live while a query runs. While waiting, the table riffles: top sheets of every stack lift and drop at random, with an elapsed timer and the typical duration ("usually 35-40 s"). When the response arrives, the Sift replays the real run in about 12 s, and the timeline shows the real durations. Live stage events need a progress hook in `kb/query/pipeline.py` and a streaming route; that is a later backend task for whoever owns `kb/query`.

**Home: reading a page (the opening moment).** One GSAP timeline per page, about 6.5 s, then the next page:

| Time | Page on the left | Step on the right |
|---|---|---|
| 0-1.0 s | slides in from the queue off the left edge, turning to face you | waiting |
| 1.0-3.2 s | a pencil-blue scan line passes top to bottom; each region it passes gets a box and a tag (Heading, Paragraph in pencil blue; Table, Chart in highlighter) | 1/7 Reading pages (text layer or OCR), then 2/7 charts (or skipped), 3/7 Checking every word |
| 3.2-4.0 s | page holds | 4/7 Document summaries, 5/7 Page summaries |
| 4.0-5.1 s | its passages lift off as paper strips (highlighter for tables and charts) and fly right, towards the panel | 6/7 Search vectors, bars moving |
| 5.1-6.0 s | the page tips flat and drops onto the index pile, which grows | 7/7 Saving the index |

The indexer really runs each step over all pages in turn, so Home labels this loop as an illustration of what each step does to one page. During a real indexing job it switches to the job's live step and page counts.

**Home scroll story.** Lenis smooths the page scroll, and the scroll position (in screen heights) drives the scene directly, so scrolling back plays it backwards. The camera eases toward each section's view (about 7% of the gap per frame).

| Section | Card | Scene |
|---|---|---|
| Opening | the seven indexing steps | the page-scanning loop |
| 1 | Every document becomes a stack: documents, pages | the collection's stacks rise from the table |
| 2 | Ask, and only the right documents move: documents routed, candidate pages | the Sift scrubs through plan, route, candidates and survey |
| 3 | Every passage is checked: passages checked, kept (highlighter) | passages peel off, queue and cross the scan line; kept ones stack |
| 4 | Answers cite the exact page: claims, pages cited | the answer page rises and the cited pages stack beside it |
| 5 | Runs on your PC: three plain facts (local search, which calls go online and private mode, traces kept) | the camera pulls back over the whole table |

In a real (non-prototype) build these numbers come from the collection's most recent run in History; a collection with no runs yet shows sections 1 and 5 only.

**Indexing.** Dropping a folder flies its pages in one by one into new stacks that grow as pages are read. Progress comes from the indexer's progress callback (the seven `*_STEP` names in `kb/ingest/pipeline.py`), read by the Electron main process.

**Smoothness.** Screen changes: the rail pill slides (550 ms, `expo.out`), the new screen's panels rise 12 px and fade in with a 50 ms stagger (600 ms, `expo.out`), and the camera glides to the new view (1.1 s, `expo.inOut`). Buttons lift 1 px on hover and press to 98%. Answer lines arrive with a short blur-to-sharp fade. The page reader rises and scales in. Lenis smooths every scrolling panel: the Home panel, the answer drawer, the document list, History and Settings.

**Timing and easing.** Sheet flights: 700 ms, `power3.inOut`, staggered so they leave one at a time, one act capped at about 1.6 s. UI: 200-450 ms, `expo.out`. Hover on a stack: it lifts slightly and shows its label.

**Libraries.** GSAP 3.15.1 (timelines, the scrubbed replay, odometer digits); Three.js 0.187.0 used directly (scene, instancing, camera); Lenis 1.3.27 (Home, drawer and list scroll). Pinned in `desktop/package.json`. The renderer is the approved prototype ported as plain ES modules, with no React layer or build step.

**Reduced motion.** The replay becomes a sequence of crossfaded still states, one per step, with no flights; counters show final numbers; the scrubber still steps through states.

## 7. 3D and visual elements

- **Scene:** one Three.js scene for the whole app. A matte dark table plane, one cool key light from above with soft shadows, a faint fill. No HDRI, no particles, no bloom.
- **Stacks:** one box per document with a paper-edge texture (fine page lines drawn on a canvas at startup) and a top sheet. Height on a log scale against the collection's largest document.
- **Sheets:** one instanced mesh of thin paper planes for every flying page, and one for passage strips. One draw call each.
- **Answer page and cited stack:** paper planes with tabs; tab text is an HTML label pinned to the 3D position, so it stays sharp and readable by screen readers.
- **Icons:** Lucide (ISC licence), 1.5 px stroke, 16 and 20 px.
- **No stock imagery.** The only pictures are the document pages themselves; the page reader shows the real page text from the index.
- **Performance:** device pixel ratio capped at 2; render on demand when the table is still; pause when the window is hidden; shadows off at 81+ documents.

## 8. Components

| Component | Source |
|---|---|
| Window, title bar, rail, status lines | custom |
| Question field (Ctrl K focuses it) | custom |
| Collection picker, selects, dialogs (reader, "Connect your models") | native `<select>`, `<dialog>`-style overlays and form fields, restyled to these tokens |
| Run timeline and scrubber | custom (idea from the 21st.dev Agent Trace) |
| Trace waterfall (History) | custom |
| Answer drawer, citation chips, "Not covered" list | custom |
| Page reader with highlighted passage | custom |
| Data tables (History, document list) | custom on a plain `<table>` with sortable headers |
| Toasts (index done, capacity reached) | custom |
| 3D table, stacks, sheets, replay | custom (Three.js / GSAP) |

## 9. Experience

**Flows**

0. First-run setup (once per PC or user, before Home): a short "Connect your models" step. It asks for the API keys this user wants to use, starting with the free providers (Cloudflare Workers AI, Groq), each with a link to get a key and a "Test" button that makes one small call. An optional "Use your own paid models" section lets a user who has a paid account pick a stronger model for the writer (answers) and for the judge (scoring), entered as provider, model name and key. Free providers stay the default; paid models are used only when the user adds them. Keys are stored locally in `.env` (never shown back in full) and can be changed later in Settings.
1. First launch: the app starts the local API (a "Starting SiftBase" state with the Python log one click away), finds collections and opens Home on the most recent one. With no collection, Home shows a single page waiting at the left edge and one action, "Index a folder". From Home's header, any button opens the workspace and the sidebar.
2. Index: pick a folder or ZIP, name the collection, watch pages stack; when done it shows the document and page counts and "Ask this collection".
3. Ask: type, Enter; the table riffles; the answer arrives and the Sift replays; read, click a citation, read the page.
4. Review: History lists every run; open one to replay it or read its trace.

**States**

- API starting / failed to start (with the error and "Open log").
- Models offline: the question field still works; sending shows "No internet: answers need the model service. The library and past answers still work."
- At capacity (503 `AT_CAPACITY`): a notice in `partial` with the time it frees up, from `Retry-After`.
- Rate limited (429): the same notice with the wait.
- Query found nothing: the table shows the routed stacks with zero pages kept, and the drawer says what was searched.
- Partial answer: "Not covered" lists each limitation the API returned.
- Indexing failed: the collection shows the error code and "Retry".

**Feedback:** every control has hover, pressed, focus and disabled states; focus rings are 2 px highlighter with a 2 px offset; long actions show elapsed time, never a bare spinner.

## 10. Quality bar

- Window sizes from 1100×700 to 2560×1440; drawers become overlays below 1280 px wide.
- 60 fps on a mid-range laptop GPU with 400 sheets in flight; DOM animation on transforms and opacity only.
- Cold start to a usable shell in under 2 s (the API may still be starting, and says so).
- WCAG AA on every text pair: text on shell 15.3:1, text-2 on shell 7.9:1, text-3 on shell 5.9:1 (5.4:1 on raised), paper-ink on paper 14.1:1, highlight-ink on highlight 12.9:1, pencil 9.2:1, withdrawn 6.6:1, partial 10.3:1 and ok 10.1:1 on shell (checked with the WCAG formula).
- Full keyboard use (Ctrl+1-4 for the rail, ⌘K, Enter to ask, arrow keys on the timeline) and visible focus everywhere.
- Every fact the 3D table shows is also in text: counts in the counters, routed documents and cited pages in the sources list. The canvas is `aria-hidden` with a live text summary beside it.
- `prefers-reduced-motion` keeps every state and drops the flights.
- Electron security: `contextIsolation` on, `sandbox` on, `nodeIntegration` off, a strict Content Security Policy (`default-src 'self'`), a preload that exposes only the app's own calls, and the API key held in the main process only.
- Fully offline package: fonts, libraries and icons bundled; nothing leaves the machine except the model calls the Python API makes.

## Prototype

A clickable prototype of this design is at `.impeccable/mocks/desktop/index.html` (local only, not committed). It plays one real recorded run on the 35-document training collection, plus two synthetic collections (labelled as such) to show the table at 4 and 240 documents. The training collection's counts on Home (35 documents, 6,970 pages, 68,769 passages) come from its real index; the page layouts in the Home loop are drawn for illustration.
