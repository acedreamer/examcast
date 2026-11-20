# DeepExamCast v3 — Material 3 Expressive UI Specification

**Date:** 2026-11-20  
**Design System:** Material 3 (Expressive) — Nocturnal Warm-Charcoal Dark Theme (Default)  
**Target File:** `static/index.html` (Zero-build Web ESM + Inline M3 Token & Component CSS)  
**Reference Mockups:** `references/ui.png`, `references/side_panel.jpg` (grounded for real multi-page PDFs & desktop/mobile browsers)

---

## Stage 1: Archaeology & Physics Stratification

### 1.1 Element Inventory

| ID | Screen / Region | Type | Label / Content | Target M3 Treatment |
| :--- | :--- | :--- | :--- | :--- |
| `E-01` | Global Chrome | Top App Bar (`<header>`) | Global study workspace header (`56px`) | M3 Small Top App Bar (`surfaceContainerLow` `#1B1B1F`, tonal separation on `#131316` canvas) |
| `E-02` | Top App Bar | Brand Identity | `DeepExamCast` wordmark + rounded-12 amber waveform icon | `TitleMedium` emphasized (`Plus Jakarta Sans`), `primary` `#F3C669` icon tile with `onPrimary` `#1D1500` bars |
| `E-03` | Top App Bar | Session Selector Pill (`<select>`) | Saved chapters (`max-width: 340px`, `text-overflow: ellipsis`) | M3 Tonal Pill container (`surfaceContainer` `#212126`, `full` pill radius) |
| `E-04` | Top App Bar | Status Badge (`<span>`) | `modeStatusBadge` (`Deep Dive · EN`, `Revision · ML`, etc.) | Compact tonal pill (`surfaceContainerHigh`, `JetBrains Mono` `tabular-nums`) |
| `E-05` | Top App Bar | Icon Button (`<button>`) | `deleteSessionBtn` (trash SVG, `aria-label`) | M3 Standard Icon Button (`48x48dp` touch target on touch, `40px` pointer-fine), `onSurfaceVariant` → `error` hover |
| `E-06` | Top App Bar | Tonal Action Button (`<button>`) | `Upload PDF` + hidden `<input type="file" accept="application/pdf">` | M3 Filled Tonal Button (`surfaceContainerHigh` / `onSurface`, `full` → `medium` morph) |
| `E-07` | Top App Bar | Primary Action Button (`<button aria-expanded>`) | `Script Studio` + sparkle SVG icon | M3 Filled Button (`primary` `#F3C669` / `onPrimary` `#1D1500`, `full` → `medium` morph) |
| `E-08` | Primary Pane (64%) | Synced PDF Reader Surface (`#pdfPane`) | Variable-height multi-page scrollable PDF stack (`padding-bottom: 88px`) | M3 Primary Pane (`surfaceContainerLow` `#1B1B1F`, `24px` radius, thin dark scrollbar, active chunk highlight `rgba(243,198,105,0.32)`) |
| `E-09` | PDF Pane | Floating M3 PDF Toolbar | `-`, `125%`, `+`, `Fit`, `Page X / Y`, Paper Mode (`Light` · `Sepia` · `Dark`) | M3 Floating Pill Toolbar (`surfaceContainerHigh` `#2B2B31`, `full` radius, `position: absolute; bottom: 18px`), filters applied strictly to `<canvas>` only |
| `E-10` | Supporting Pane (36%) | Lecture Transcript Panel (`#dialoguePane`) | Header `Lecture Transcript` + tonal pill `104 turns · ~27m` | M3 Supporting Pane (`surfaceContainerLow` `#1B1B1F`, `24px` radius) |
| `E-11` | Transcript Panel | Dialogue Turn Cards | `Professor` (`#39384D`/`#DDD9F6`) & `Student` (`#253D32`/`#B7E4CE`), compacted `Pg P · C127–C133`, pulsing 3-bar active indicator, `Exam Note` chip (`#3F310E`/`#FFE09B`) | Inactive `surfaceContainer` (`#212126`), active `surfaceContainerHigh` (`#2B2B31`) + `1px` `primary` border + subtle warm tint, `largeIncreased` `20px` radius |
| `E-12` | Bottom Dock | Floating Audio Player Dock (`<nav>`) | Elevated full-width tonal pill (`#25252B`, `margin: 10px 12px 12px`, `full`/`28px` radius) | M3 Floating Docked Toolbar |
| `E-13` | Player Dock | 4-Button Transport Cluster | Circular `Play/Pause` (`primary`), circular tonal `Prev (\|<)`, `Next (>\|)`, `Repeat (↺)` | Expressive `Play/Pause` (`48x48dp` circle → `16px` square morph when playing) + Standard Icon Buttons |
| `E-14` | Player Dock | Connected Speed Button Group | `1x`, `1.25x`, `1.5x`, `1.75x`, `2x` (`aria-pressed`) | M3 Expressive Connected Button Group (`surfaceContainerHigh` unselected, `primary` / `onPrimary` active pill) |
| `E-15` | Player Dock | Wavy Amber Progress Scrubber + Readout | Accessible `<input type="range">` over inline SVG sine-wave `<path>` + `Line 34 / 104 · ~19m left` | M3 Expressive Wavy Linear Slider (`primary` sine wave, `surfaceContainerHighest` track, `primary` thumb; flat under `prefers-reduced-motion`) |
| `E-16` | Player Dock | Auto-Scroll Switch (`<button aria-pressed>`) | `Auto-Scroll` M3 Expressive switch | M3 Switch (`surfaceContainerHighest` off, `primary` on, GPU `translateX` thumb) |
| `E-17` | Script Studio | Right-Side Modal Side Sheet + Scrim | `clamp(400px, 40vw, 520px)`, `border-radius: 28px 0 0 28px`, `#24242A`, scrim over transcript side only (`>=900px`) | M3 Expressive Modal Side Sheet (`Tier 1` GPU `translateX` reveal, leaving PDF visible & scrollable) |
| `E-18` | Script Studio Header | Vision OCR Pill & Re-parse Button | `visionStatusPill` (`Vision OCR: Ready` / `Text Mode`), `reparseBtn`, `closeSheetBtn` | Tonal status pill + Standard Icon Buttons (`40px` desktop / `48dp` touch) |
| `E-19` | Script Studio | Study Pacing Connected Group | `Deep Dive`, `Revision`, `Viva Q&A`, `ELI5` | M3 Expressive Connected Button Group (`primary` / `onPrimary` selected) |
| `E-20` | Script Studio | Language Filter Chips | `English`, `Hindi (Hinglish)`, `Malayalam (Manglish)` | M3 Filter Chips (`mint` `#B7E4CE` active check state, `small` → `full` morph) |
| `E-21` | Script Studio | Voice Pair Select & Re-synthesize | `<select id="voicePairSelect">` (filtered by language) + `Re-synthesize Voice` button | M3 Outlined Select + Filled Tonal Button |
| `E-22` | Script Studio | Smart Batch Coverage Card | `chapterCompleteBadge`, `From Page` & `To Page` `<input type="number">`, wavy amber coverage SVG, `Covered: X / Y pages · A / B chunks`, `Copy Prompt for Gemini Pro` | M3 Card (`surfaceContainerLow` `#1B1B1F`, `20px` radius) + Wavy Progress + Tonal CTA |
| `E-23` | Script Studio | JSON Paste Textarea (`<textarea>`) | Monospace JSON paste well (`#151519`, `20px` radius) | M3 Outlined Multiline Field (`JetBrains Mono`) |
| `E-24` | Script Studio | Live Synthesis Progress Box | `Synthesizing 14 / 48 clips (3 cached) · 11s` + determinate fill | M3 Determinate Linear Indicator (`aria-live="polite"`) |
| `E-25` | Script Studio | Dismissible Inline Alert Banner | JSON syntax line/col error, missed-chunk warnings, Vision fallback notices | M3 Banner (`errorContainer` / `primaryContainer`, `16px` radius, dismiss button) |
| `E-26` | Script Studio Footer | Action Footer & Split Button | `Undo`, `Append`, Split Button (`Generate Audio` + `⌄` menu: `Replace Entire Lecture`, `Re-synthesize Existing Audio`) | M3 Expressive Split Button (`primary` / `onPrimary`) + Tonal Footer Actions + M3 Menu (`Level2`) |
| `E-27` | Global Overlay | Snackbar Stack (`aria-live="polite"`) | `Copied!`, upload confirmation, audio error (`Retry Line` / `Skip`) | M3 Expressive Snackbar (`inverseSurface` / `onInverseSurface`) |
| `E-28` | Compact/Medium Chrome | Mobile Pane Switcher (`<div role="tablist">`) | `PDF Viewer` \| `Lecture Transcript` (`<900px` only) | M3 Segmented Pill (`48dp` touch height) |
| `E-29` | Empty States | PDF & Transcript Empty Cards | First-run upload CTA and 3-step guide | M3 Tonal Cards (`surfaceContainer`, `20px` radius) |
| `E-30` | Custom Scrollbars | Pane Scrollbar Chrome | `scrollbar-width: thin` + `6px` translucent dark WebKit thumb | Static visual polish (`Tier 3`) |

---

### 1.2 Interaction Table

| ID | Trigger Element(s) | Input | Resulting State / Route | Target M3 Feedback |
| :--- | :--- | :--- | :--- | :--- |
| `I-01` | `E-03` | Change (`<select>`) | `GET /api/sessions/{id}`, loads PDF, restores `last_line_index`, speed, pacing, language | Effects fade (`default-effects`) |
| `I-02` | `E-05` | Click + confirm | `DELETE /api/sessions/{id}`, refreshes list, loads next or empty state | Press morph (`fast-spatial`) + Snackbar (`E-27`) |
| `I-03` | `E-06`, `E-29` | Click → file pick | `POST /api/upload` (`use_vision=true`), opens Script Studio on empty script | Tonal press morph (`fast-spatial`) + `E-27` |
| `I-04` | `E-07`, `E-17`, `E-18` | Click toggle / scrim / `Esc` | Slides Right-Side Script Studio sheet in/out leaving left PDF visible & scrollable | GPU `translateX` (`default-spatial`) + scrim fade (`default-effects`) |
| `I-05` | `E-09` | Click `-`, `+`, `Fit` | Cancels `RenderTask`s, updates zoom, re-renders `±4` visible pages | Button morph (`fast-spatial`) |
| `I-06` | `E-09` | Click Light / Sepia / Dark | Updates `.paper-*` class on `#pdfPagesContainer` (`<canvas>` only), persists `localStorage` | Effects filter transition (`fast-effects`) |
| `I-07` | `E-08` | Scroll `#pdfScroll` | Updates `Page X / Y` readout from max-visibility page (`IntersectionObserver`) | Static readout update |
| `I-08` | `E-08` | Click covered chunk box | Reverse-syncs playback to first line explaining that chunk | Tier 3 highlight (`fast-effects`) |
| `I-09` | `E-11` | Click dialogue card | Jumps audio playback & PDF highlight to clicked line | Effects border/tint (`default-effects`) |
| `I-10` | `E-13` | Click Play/Pause or `Space` | Unlocks `standbyDeck` on first gesture; plays/pauses `activeDeck` | Click: circle ↔ squircle (`fast-spatial`); `Space`: `0ms` instant |
| `I-11` | `E-13` | Click Prev/Next or `ArrowLeft`/`ArrowRight` | Jumps `i ± 1`, preloads `i + 1`, syncs PDF & transcript | Click: press morph (`fast-spatial`); Keys: `0ms` instant |
| `I-12` | `E-13` | Click Repeat or `R` | Cancels breath timer, restarts current line at `t = 0` | Click: press morph (`fast-spatial`); `R`: `0ms` instant |
| `I-13` | `E-14` | Click speed pill | Sets `defaultPlaybackRate` + `playbackRate` on both decks, debounced `PATCH /state` | Pill morph (`fast-spatial`) + color (`fast-effects`) |
| `I-14` | `E-15` | Drag / click wavy scrubber | Jumps to scrubbed line index, redraws SVG wave & thumb | Thumb feedback (`fast-spatial`) |
| `I-15` | `E-16` | Click Auto-Scroll switch | Toggles `auto_scroll`, debounced `PATCH /state` | Switch thumb `translateX` (`fast-spatial`) + track (`fast-effects`) |
| `I-16` | `E-18` | Click `reparseBtn` | `POST /api/sessions/{id}/reparse`, reloads PDF chunk overlays & warnings | Icon spin/morph (`fast-spatial`) + `E-25`/`E-27` |
| `I-17` | `E-19` | Click pacing button | Updates `pacing`, badge `E-04`, debounced `PATCH /state`, applies returned `coverage` | Connected pill morph (`fast-spatial`) + color (`fast-effects`) |
| `I-18` | `E-20` | Click language chip | Updates `language`, filters `voicePairSelect`, debounced `PATCH /state` | Chip morph (`fast-spatial`) + mint check (`fast-effects`) |
| `I-19` | `E-21` | Change voice / click `Re-synthesize Voice` | `POST /api/sessions/{id}/resynthesize` + 900ms `/generate/status` polling | Determinate progress (`E-24`) + `E-27` |
| `I-20` | `E-22` | Edit `From Page` / `To Page` | Marks manual range edit, validates `1 <= sp <= ep <= page_count` | Focus ring (`fast-effects`) |
| `I-21` | `E-22` | Click `Copy Prompt for Gemini Pro` | `GET /api/sessions/{id}/prompt?start_page&end_page&pacing&language`, copies to clipboard | Button morph (`fast-spatial`) + `E-27` |
| `I-22` | `E-23`, `E-26` | Click `Append` or `Generate Audio` | `POST /api/sessions/{id}/generate` + live progress polling | Progress bar (`E-24`) + `E-25` warnings / sheet close |
| `I-23` | `E-26` | Click `⌄` split chevron | Toggles `splitActionMenu` (`Replace Entire Lecture`, `Re-synthesize Existing Audio`) | Menu scale/opacity (`fast-spatial` + `fast-effects`) |
| `I-24` | `E-26` | Click `Replace Entire Lecture` | Confirms overwrite, calls `handleGenerate("replace")` | Confirm + `E-24` progress |
| `I-25` | `E-26` | Click `Undo` | `POST /api/sessions/{id}/undo`, restores previous script & updates coverage | Press morph (`fast-spatial`) + `E-27` |
| `I-26` | `E-25` | Click dismiss `×` | Hides inline alert banner | Opacity fade (`fast-effects`) |
| `I-27` | `E-27` | Click `Retry Line` / `Skip` / auto-timer | Retries failed audio, skips to `i + 1`, or dismisses toast | `transform` + `opacity` exit (`default-spatial` + `fast-effects`) |
| `I-28` | `E-28` | Tap `PDF Viewer` / `Lecture Transcript` (`<900px`) | Switches active mobile pane preserving PDF.js & `<audio>` state | Segmented pill (`fast-spatial`) + fade (`fast-effects`) |

---

### 1.3 Adaptive Window Size Matrix

| Screen / Workspace | Compact (`<600dp`) | Medium (`600–839dp`) | Expanded (`840–1199dp`) | Large (`1200–1599dp`) | Extra-large (`>=1600dp`) | Compact-Height Landscape (`<480dp` h) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DeepExamCast v3 Workspace** | **Single Column** + `56px` Top App Bar (`E-01`) + Mobile Switcher (`E-28`) + compact floating Player Dock (`E-12`). All targets `>=48dp`. Full-width Script Studio sheet (`E-17`). | **Single Column** (`<900px` stack) + `E-28` switcher, `>=48dp` touch targets, full-width Script Studio sheet (`E-17`). | **Supporting Pane** (`64%` PDF / `36%` Transcript at `>=900px`), `E-28` hidden. Floating Player Dock (`E-12`) + Floating PDF Toolbar (`E-09`). Right-side Script Studio sheet (`400–520px`) with transcript-only scrim. | **Supporting Pane** (`64%` / `36%`) with `40px` pointer-fine desktop controls, connected speed/pacing groups, `8%` hover state layers. | **Desktop Supporting Pane** (`64%` / `36%`), centered Fit-Width PDF column, full keyboard accelerators (`Space`, `←`, `→`, `R`, `Esc`), `3px` `:focus-visible` secondary rings. | Slim `44px` Top App Bar and compact Player Dock; preserves active session, PDF zoom, and `<audio>` playback continuity across resize. |

---

## Stage 2: Tokenized Spec & Performance Tiering

### 2.1 Material 3 Expressive Design Token JSON

```json
{
  "meta": {
    "designSystem": "Material 3 Expressive",
    "defaultTheme": "dark",
    "seedColor": "#F3C669"
  },
  "color": {
    "dark": {
      "primary": "#F3C669",
      "onPrimary": "#1D1500",
      "primaryContainer": "#3F310E",
      "onPrimaryContainer": "#FFE09B",
      "primaryFixed": "#FFE09B",
      "primaryFixedDim": "#F3C669",
      "onPrimaryFixed": "#1D1500",
      "onPrimaryFixedVariant": "#3F310E",
      "secondary": "#DDD9F6",
      "onSecondary": "#222136",
      "secondaryContainer": "#39384D",
      "onSecondaryContainer": "#DDD9F6",
      "tertiary": "#B7E4CE",
      "onTertiary": "#0E281D",
      "tertiaryContainer": "#253D32",
      "onTertiaryContainer": "#B7E4CE",
      "surface": "#131316",
      "surfaceDim": "#131316",
      "surfaceBright": "#383842",
      "surfaceContainerLowest": "#151519",
      "surfaceContainerLow": "#1B1B1F",
      "surfaceContainer": "#212126",
      "surfaceContainerHigh": "#2B2B31",
      "surfaceContainerHighest": "#383842",
      "onSurface": "#F4F4F8",
      "onSurfaceVariant": "#B9B9C6",
      "outline": "#7E7E8D",
      "outlineVariant": "rgba(255, 255, 255, 0.08)",
      "inverseSurface": "#F4F4F8",
      "onInverseSurface": "#1B1B1F",
      "inversePrimary": "#7A5800",
      "error": "#FFB4AB",
      "onError": "#690005",
      "errorContainer": "#93000A",
      "onErrorContainer": "#FFDAD6",
      "scrim": "rgba(0, 0, 0, 0.45)",
      "shadow": "#000000"
    }
  },
  "shape": {
    "extraSmall": "4px",
    "small": "8px",
    "medium": "12px",
    "large": "16px",
    "largeIncreased": "20px",
    "extraLarge": "24px",
    "extraLargeIncreased": "28px",
    "extraExtraLarge": "48px",
    "full": "9999px"
  }
}
```

### 2.2 Component & Physics Tier Mapping

| Element ID | M3 Component + Variant | Physics Tier | Shape Morph Rule | Touch Target & Contrast Pair |
| :--- | :--- | :--- | :--- | :--- |
| `E-01` | Small Top App Bar | `Tier 3` | Static `none` | `56px` height; `onSurface` on `surfaceContainerLow` |
| `E-02` | Brand Lockup + Icon Tile | `Tier 3` | Static `12px` | Decorative; `onPrimary` on `primary` |
| `E-03` | Tonal Select Pill | `Tier 3` | Static `full` | `40px` desktop / `48dp` touch; `onSurface` on `surfaceContainer` |
| `E-04` | Tonal Status Badge | `Tier 3` | Static `full` | Static; `onSurfaceVariant` on `surfaceContainerHigh` |
| `E-05` | Standard Icon Button | `Tier 2` | `full` → `small` | `40px` desktop / `48dp` touch; `onSurfaceVariant` / `error` |
| `E-06` | Filled Tonal Button | `Tier 2` | `full` → `medium` | `40px` desktop / `48dp` touch; `onSurface` on `surfaceContainerHigh` |
| `E-07` | Filled Expressive Button | `Tier 2` | `full` → `medium` | `40px` desktop / `48dp` touch; `onPrimary` on `primary` |
| `E-08` | Primary PDF Pane | `Tier 3` | Static `24px` | `>=48dp` scroll area; `onSurface` on `surfaceContainerLow` |
| `E-09` | Floating Pill Toolbar | `Tier 2` | `full` → `small` on buttons | `40px` desktop / `48dp` touch; `onSurface` on `surfaceContainerHigh` |
| `E-10` | Supporting Transcript Pane | `Tier 3` | Static `24px` | Header `onSurface` on `surfaceContainerLow` |
| `E-11` | Transcript Turn Cards | `Tier 3` | Static `20px` | Full-width card `>=64px` height; `onSurface` on `surfaceContainerHigh` |
| `E-12` | Floating Docked Player | `Tier 3` | Static `full` / `28px` | `onSurface` on `surfaceContainer` |
| `E-13` | Transport Cluster | `Tier 2` | `Play`: `full` ↔ `16px`; Icons: `full` → `small` | `48x48dp` touch target; `onPrimary` on `primary` |
| `E-14` | Connected Speed Group | `Tier 2` | `full` ↔ `small` | `36px` desktop / `48dp` touch; `onPrimary` on `primary` |
| `E-15` | Expressive Wavy Slider | `Tier 2` | Thumb scale on active | `40px` hit height; `primary` on `surfaceContainerHighest` |
| `E-16` | Expressive Switch | `Tier 2` | Track `full`, thumb `translateX` | `48dp` touch target; `onPrimary` / `primary` |
| `E-17` | Modal Right Side Sheet | `Tier 1` | `28px 0 0 28px` | GPU `translateX`; `onSurface` on `#24242A` |
| `E-18` | Vision Pill & Icon Buttons | `Tier 2` | `full` → `small` | `40px` desktop / `48dp` touch |
| `E-19` | Connected Pacing Group | `Tier 2` | `full` ↔ `medium` | `38px` desktop / `48dp` touch; `onPrimary` on `primary` |
| `E-20` | Language Filter Chips | `Tier 2` | `small` ↔ `full` | `38px` desktop / `48dp` touch; `onTertiaryContainer` on `tertiaryContainer` |
| `E-21` | Outlined Select + Tonal Button | `Tier 2` | `full` → `medium` | `40px` desktop / `48dp` touch |
| `E-22` | Batch Coverage Card | `Tier 2` | Button `full` → `medium` | Inputs `>=40px` (`48dp` touch) |
| `E-23` | Outlined Multiline Field | `Tier 3` | Static `20px` | `>=110px` height; `onSurface` on `surfaceContainerLowest` |
| `E-24` | Determinate Linear Indicator | `Tier 2` | Static `full` | `primary` on `surfaceContainerHighest` |
| `E-25` | Inline Alert Banner | `Tier 3` | Static `16px` | `onErrorContainer` / `onPrimaryContainer` |
| `E-26` | Footer & Split Button + Menu | `Tier 2` | `full` → `medium` | `40px` desktop / `48dp` touch; `onPrimary` on `primary` |
| `E-27` | Expressive Snackbar | `Tier 2` | Static `12px` | `onInverseSurface` on `inverseSurface` |
| `E-28` | Mobile Pane Switcher | `Tier 2` | `full` | `48dp` height; `onPrimary` on `primary` |
| `E-29` | Empty State Cards | `Tier 3` | Static `20px` | `onSurface` on `surfaceContainer` |
| `E-30` | Custom Thin Scrollbars | `Tier 3` | Static `full` | `outlineVariant` thumb |

### 2.3 Motion Specification (Split-Spring Law)

| Interaction ID | Tier | Spatial Track | Effects Track | Interruption Rule | Reduced-Motion Fallback |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `I-01` | `Tier 3` | None | `opacity` (`default-effects`) | Immediate state swap | `150ms` opacity fade |
| `I-02` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-03` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-04` | `Tier 1` | `transform` (`default-spatial`) | `opacity` (`default-effects`) | Interruptible mid-slide | `150ms` opacity fade |
| `I-05` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Cancels prior `RenderTask` | `150ms` opacity fade |
| `I-06` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `filter`, `background-color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-07` | `Tier 3` | None | None | Passive observer | Static |
| `I-08` | `Tier 3` | None | `background-color`, `border-color` (`fast-effects`) | Immediate jump | `150ms` opacity fade |
| `I-09` | `Tier 3` | None | `background-color`, `border-color` (`default-effects`) | Immediate jump | `150ms` opacity fade |
| `I-10` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | `Space` uses `0ms` instant | `150ms` opacity fade |
| `I-11` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Arrows use `0ms` instant | `150ms` opacity fade |
| `I-12` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | `R` uses `0ms` instant | `150ms` opacity fade |
| `I-13` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color`, `color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-14` | `Tier 2` | `transform` (`fast-spatial`) | `opacity` (`fast-effects`) | Tracks pointer live | Flat progress bar |
| `I-15` | `Tier 2` | `transform` (`fast-spatial`) | `background-color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-16` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Guarded by `state.generating` | `150ms` opacity fade |
| `I-17` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color`, `color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-18` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color`, `border-color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-19` | `Tier 2` | `transform` (`default-spatial`) | `opacity` (`fast-effects`) | Guarded by `state.generating` | `150ms` opacity fade |
| `I-20` | `Tier 3` | None | `border-color` (`fast-effects`) | Immediate validation | Static |
| `I-21` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-22` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Guarded by `state.generating` | `150ms` opacity fade |
| `I-23` | `Tier 2` | `transform` (`fast-spatial`) | `opacity` (`fast-effects`) | Closes on outside click/`Esc` | `150ms` opacity fade |
| `I-24` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Confirm dialog guard | `150ms` opacity fade |
| `I-25` | `Tier 2` | `transform`, `border-radius` (`fast-spatial`) | `background-color` (`fast-effects`) | Retargets immediately | `150ms` opacity fade |
| `I-26` | `Tier 3` | None | `opacity` (`fast-effects`) | Immediate hide | `150ms` opacity fade |
| `I-27` | `Tier 2` | `transform` (`default-spatial`) | `opacity` (`fast-effects`) | Pauses timer when hidden | `150ms` opacity fade |
| `I-28` | `Tier 2` | `transform` (`fast-spatial`) | `background-color`, `opacity` (`fast-effects`) | Preserves PDF/audio state | `150ms` opacity fade |

### 2.4 State & Accessibility Coverage

- **Touch Targets:** Minimum `48x48dp` (`48px`) hit area on `<900px` touch viewports; `40px` mouse-only targets on desktop pointer-fine.
- **Focus & Screen Readers:** `3px` `:focus-visible` secondary ring, `aria-pressed` on toggles/pills/paper modes, `aria-expanded` on Script Studio and Split Menu, `aria-live="polite"` on synthesis progress and snackbars, `role="alert"` on error banners.
- **Reduced Motion:** `@media (prefers-reduced-motion: reduce)` replaces all Spatial/Effects springs with `150ms ease-out`, disables pulsing waveform keyframes, and renders flat linear scrubber progress.
