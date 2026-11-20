# DeepExamCast — Material 3 Expressive UI Specification

**Date:** 2026-11-20  
**Design System:** Material 3 (Expressive) — Nocturnal Study-Lamp Dark Theme (Default)  
**Target File:** `static/index.html` (Zero-build Web ESM + Inline M3 Token & Layout CSS + Tailwind CDN)  
**Core Spec:** [2026-11-20-deepexamcast-design.md](2026-11-20-deepexamcast-design.md)

---

## Stage 1: Archaeology & Physics Stratification

### 1.1 Element Inventory

| ID | Screen / Region | Type | Label / Content | Current / Target M3 Treatment |
| :--- | :--- | :--- | :--- | :--- |
| `E-01` | Global Chrome | Top App Bar (`<header>`) | Global study workspace header | M3 Small Top App Bar (`surfaceContainer`, `64px` height, tonal separation) |
| `E-02` | Top App Bar | Brand Identity | `DeepExamCast` wordmark + inline SVG acoustic waveform mark | `TitleMedium` emphasized (`Sora`), `primary` SVG mark, `onSurface` label |
| `E-03` | Top App Bar | Session Selector (`<select>`) | Saved chapters (`title — X/Y full pgs · ~18m`) | M3 Outlined Dropdown control (`surfaceContainerHigh`, `outline` border, `medium` 12dp radius) |
| `E-04` | Top App Bar | Icon Button (`<button>`) | Delete current session (trash SVG, `aria-label`) | M3 Standard Icon Button (`48x48dp` touch target on touch, `40px` pointer-fine), `onSurfaceVariant` → `error` hover |
| `E-05` | Top App Bar | Tonal Action Button (`<button>`) | `Upload PDF` + hidden `<input type="file" accept="application/pdf">` | M3 Filled Tonal Button (`secondaryContainer` / `onSecondaryContainer`, `full` → `medium` morph) |
| `E-06` | Top App Bar | Primary Toggle Button (`<button aria-expanded>`) | `Add / Generate Deep Script` + chevron SVG | M3 Filled Button (`primary` / `onPrimary`) when script empty; Tonal (`primaryContainer` / `onPrimaryContainer`) when active |
| `E-07` | Script Workspace | Top-Anchored Docked Sheet + Scrim | Collapsible Gemini prompt & JSON paste workspace | M3 Expressive Top-Anchored Sheet (`surfaceContainerHigh`, `extraLarge` 28dp bottom corners, GPU `transform` + `opacity` reveal, no layout reflow) |
| `E-08` | Script Sheet | Numeric Range Inputs | `From Page` & `To Page` (`<input type="number">`) | M3 Outlined Text Fields (`surfaceContainerHighest` fill, `outline` border, `small` 8dp corners, `JetBrains Mono` `tabular-nums`) |
| `E-09` | Script Sheet | Coverage Meter & Partial Page Chips | `Covered: X / Y chunks · Z / N full pages` + skipped chunk badges | M3 Linear Progress Indicator (`primary` track on `surfaceContainerHighest`) + static tonal status pills (`errorContainer` for partial/skipped) |
| `E-10` | Script Sheet | Tonal Action Button (`<button>`) | `Copy Prompt for Gemini Pro` + copy SVG | M3 Filled Tonal Button (`primaryContainer` / `onPrimaryContainer`, `full` → `medium` morph) |
| `E-11` | Script Sheet | Multiline Text Field (`<textarea>`) | Paste Gemini JSON response | M3 Outlined Multiline Field (`surfaceContainerLowest` well, `outline` → `primary` focus border, `medium` 12dp corners) |
| `E-12` | Script Sheet | Voice Pair Select + Outlined Action | Voice Pair dropdown (US / Indian / UK) + `Re-synthesize Voice` button | M3 Outlined Select + Outlined Button (`outline` border, `full` → `medium` morph, disabled when script empty) |
| `E-13` | Script Sheet | Generation Button Group | `Append to Lecture`, `Replace & Generate Audio`, `Undo Last Batch` | M3 Expressive Button Group: Filled (`primary`), Tonal (`secondaryContainer`), and Outlined (`outline`) buttons with `full` → `small` press morph |
| `E-14` | Script Sheet | Live Synthesis Progress Region | `Synthesizing 14 / 48 clips (3 cached) · 11s` + determinate bar | M3 Expressive Determinate Linear Indicator (`primary` fill on `surfaceContainerHighest`, `full` pill caps, `aria-live="polite"`) |
| `E-15` | Script Sheet | Inline Alert Banner | JSON syntax line/col error, Gemini-skipped chunk IDs, or `502` retry banner | M3 Expressive Banner (`errorContainer` / `onErrorContainer` for errors; `primaryContainer` / `onPrimaryContainer` for warnings, `large` 16dp radius, full 1px outline, dismiss icon button) |
| `E-16` | Playback Bar | Transport Control Cluster (`<nav>`) | Previous, Play/Pause Primary Button, Next, Repeat (`R`) | M3 Floating/Docked Playback Toolbar (`surfaceContainer`); Play/Pause uses Expressive Filled Pill (`primary`/`onPrimary`, `full` → `medium` morph); transport icons use Standard Icon Buttons (`48x48dp` touch target) |
| `E-17` | Playback Bar | Segmented Speed Group | `1x`, `1.25x`, `1.5x`, `1.75x`, `2x` (`aria-pressed`) | M3 Expressive Connected Button Group (`surfaceContainerHigh` unselected, `primaryContainer` / `onPrimaryContainer` selected, `full` → `small` radius morph) |
| `E-18` | Playback Bar | Line-Index Scrub Bar & Readout | Interactive line scrubber (`<input type="range">`) + `Line X / Y · Page P / N · ~14m left` | M3 Expressive Slider (`primary` active track, `surfaceContainerHighest` inactive track, morphing pill thumb) + `JetBrains Mono` `tabular-nums` label |
| `E-19` | Playback Bar | Filter Toggle Chip (`<button aria-pressed>`) | `Auto-Scroll: ON` / `OFF` | M3 Filter Chip (`small` 8dp unselected ↔ `full` 9999dp / `medium` 12dp selected with `secondaryContainer` / `onSecondaryContainer`) |
| `E-20` | Primary Pane (68%) | Synced PDF Viewer Surface | Zoom toolbar (`-`, `100%`, `+`, `Fit Width`), lazy HiDPI PDF canvases, normalized `%` chunk overlays | M3 Primary Pane (`surfaceContainerLowest` canvas well, tonal zoom pill bar in `surfaceContainerHigh`, active chunk highlight `rgba(250, 204, 21, 0.35)` + `1.5px` amber border) |
| `E-21` | Supporting Pane (32%) | Live Dialogue & Exam Notes Panel | Script header, composed empty states, scrollable dialogue cards, `Professor`/`Student` badges, `exam_note` callouts | M3 Supporting Pane (`surfaceContainerLow` rail, `largeIncreased` 20dp cards in `surfaceContainer`; active card `primaryContainer` tonal tint + 1px `primary` border + leading dot; `Professor` `secondaryContainer`, `Student` `tertiaryContainer`; zero >1px side-stripe borders) |
| `E-22` | Global Overlay | Snackbar / Toast Stack (`aria-live="polite"`) | `Copied!`, upload confirmation, audio error with `Retry Line` & `Skip` actions | M3 Expressive Snackbar (`inverseSurface` / `onInverseSurface`, `inversePrimary` action buttons, `medium` 12dp radius, `Level2` elevation) |
| `E-23` | Compact/Medium Chrome | Mobile Pane Switcher (`<div role="tablist">`) | `PDF Viewer` \| `Dialogue & Notes` (visible `< 840px` only) | M3 Expressive Segmented Navigation Pill (`surfaceContainerHigh` container, `secondaryContainer` active indicator, `48dp` height) |

---

### 1.2 Interaction Table

| ID | Trigger Element(s) | Input | Resulting State / Route | Target M3 Feedback |
| :--- | :--- | :--- | :--- | :--- |
| `I-01` | `E-03` | Change (`<select>`) | `GET /api/sessions/{id}`, loads PDF, restores `last_line_index` & speed without auto-playing | Effects fade on PDF/Dialogue swap; focus stays clear |
| `I-02` | `E-04` | Tap / Click + confirm | `DELETE /api/sessions/{id}`, refreshes session list, shows empty state if none left | Tactile press morph + Snackbar confirmation (`E-22`) |
| `I-03` | `E-05` | Click → file pick | `POST /api/upload`, creates session, auto-opens `E-07` sheet for 0-line PDF | Tonal press morph + upload indicator + `E-22` warning if 0 text chunks |
| `I-04` | `E-06`, `E-07` | Click toggle / click scrim / `Esc` | Opens or collapses Top-Anchored Script Sheet (`aria-expanded`) | GPU `transform` + `opacity` sheet reveal (`default-spatial` + `default-effects`) without reflowing `E-20` |
| `I-05` | `E-08` | Type / increment | Updates batch page range (`From Page`..`To Page`), validates `1 <= start <= end <= page_count` | Immediate focus ring (`3px` `secondary`) + live chunk count update |
| `I-06` | `E-10`, `E-22` | Click | `GET /api/sessions/{id}/prompt`, copies text to clipboard, records `lastCopiedRange` | Button morph (`fast-spatial`) + `"Copied! C1–C24"` snackbar (`E-22`) |
| `I-07` | `E-11`, `E-13`, `E-14`, `E-15` | Paste JSON + Click Append/Replace | `POST /api/sessions/{id}/generate` + 1s polling `GET /generate/status`; on success collapses `E-07` and loads audio | Determinate progress bar (`E-14`), inline `E-15` warnings on skipped chunks or syntax errors |
| `I-08` | `E-13` | Click `Undo Last Batch` | `POST /api/sessions/{id}/undo`, restores previous script & updates coverage | Tactile morph + `E-22` snackbar reporting restored line count |
| `I-09` | `E-12`, `E-14` | Select voice + Click `Re-synthesize Voice` | `POST /api/sessions/{id}/resynthesize` + 1s polling `GET /generate/status` | Live progress (`E-14`) + updated voice clips on decks |
| `I-10` | `E-16` | Click Play/Pause or `Space` | Unlocks `standbyDeck` on first gesture; plays or pauses `activeDeck` | Click: `full` ↔ `medium` morph (`fast-spatial`); Keyboard `Space`: **0ms instant** state toggle |
| `I-11` | `E-16` | Click Prev/Next or `ArrowLeft`/`ArrowRight` | Jumps active line `i ± 1`, preloads `i + 1`, updates PDF highlight & sidebar | Click: icon press morph; Keyboard arrows: **0ms instant** jump |
| `I-12` | `E-16` | Click Repeat or `R` | Cancels `200ms` breath timer, restarts `activeDeck` at `t = 0` | Click: icon press morph; Keyboard `R`: **0ms instant** replay |
| `I-13` | `E-17` | Click speed pill | Sets `defaultPlaybackRate` + `playbackRate` on both decks, debounced `PATCH /state` | Expressive radius morph (`full` → `small`, `fast-spatial`) + tonal highlight (`fast-effects`) |
| `I-14` | `E-18` | Click / drag line scrubber | Jumps directly to scrubbed line index `0..Y-1`, syncs PDF & sidebar | Active track update + thumb scale feedback (`fast-spatial`) |
| `I-15` | `E-19` | Click Auto-Scroll chip | Toggles `auto_scroll`, persists via `PATCH /state` | Chip shape morph + tonal swap (`fast-spatial` + `fast-effects`) |
| `I-16` | `E-20` | Click `-`, `+`, `Fit Width` | Cancels in-flight `RenderTask`s, updates zoom scale, re-renders visible `±4` pages | Button press morph + crisp re-render of visible canvases |
| `I-17` | `E-20` | Hover / click PDF chunk overlay | Hover shows status tooltip; clicking covered chunk jumps playback to its first line (**Reverse Sync**) | Tier 3 opacity fade (`fast-effects`); immediate playback jump + sidebar scroll |
| `I-18` | `E-21` | Click dialogue card | Jumps audio playback & PDF highlight to clicked line index | Tier 3 tonal state-layer (`fast-effects`) + active card elevation (`default-effects`) |
| `I-19` | `E-23` | Tap `PDF` or `Dialogue` tab (`<840px`) | Switches visible full-width pane on `Compact`/`Medium` screens preserving scroll & playback state | Segmented pill indicator slide (`default-spatial`) + pane cross-fade (`fast-effects`) |
| `I-20` | `E-22` | Click Retry / Skip / Dismiss (or timer) | Retries failed audio clip, skips to `i + 1`, or dismisses snackbar (auto-dismiss pauses when `document.hidden`) | Interruptible `transform` + `opacity` exit (`fast-effects` / `default-spatial`) |

---

### 1.3 Adaptive Window Size Matrix

| Screen / Workspace | Compact (`<600dp`) | Medium (`600–839dp`) | Expanded (`840–1199dp`) | Large (`1200–1599dp`) | Extra-large (`>=1600dp`) | Compact-Height Landscape (`<480dp` h) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **DeepExamCast Study Workspace** | **Single Column** + Top App Bar (`E-01`) + Mobile Pane Switcher (`E-23`: `PDF` \| `Dialogue`) + Bottom-docked compact Playback Bar (`E-16`..`E-19`). Touch targets strictly `>=48dp`. | **Single Column** or tabbed **Supporting Pane** toggle (`E-23`), Top App Bar (`E-01`), full Playback Bar (`E-16`..`E-19`), `>=48dp` touch targets. Script Sheet (`E-07`) full-width below Top App Bar. | **Supporting Pane** CSS Grid (`68%` PDF Viewer `E-20` / `32%` Dialogue `E-21`), `E-23` hidden. Sticky Playback Bar beneath Top App Bar. Script Sheet (`E-07`) centered `max-w-[960px]`. | **Supporting Pane** (`68%` / `32%`) with `40px` pointer-fine desktop controls, full inline speed pills (`E-17`) and coverage readout (`E-09`), `8%` hover state layers. | **Desktop Workspace Supporting Pane** (`68%` / `32%`), max-width centered PDF page column, full keyboard accelerators (`Space`, `←`, `→`, `R`, `Esc`), `3px` `:focus-visible` rings, `8%` hover state layers. | Collapses Top App Bar + Playback Bar into slim `44px` bars, hides secondary badges, keeps PDF canvas & Dialogue readable with state preserved across resize/rotation. |

*Navigation & Resize State Preservation:* Never renders mobile pane switcher (`E-23`) simultaneously with the side-by-side Supporting Pane (`>=840px`). Resizing across breakpoints preserves active session, audio playback continuity, PDF zoom, and scroll position without tearing down `<audio>` decks or PDF.js document handles.

---

## Stage 2: Tokenized Spec & Performance Tiering

### 2.1 Material 3 Expressive Design Token JSON

```json
{
  "meta": {
    "designSystem": "Material 3 Expressive",
    "defaultTheme": "dark",
    "seedColor": "#F5C84C",
    "brandVoice": ["nocturnal", "studious", "razor-sharp"]
  },
  "color": {
    "dark": {
      "primary": "#F5C84C",
      "onPrimary": "#3D2E00",
      "primaryContainer": "#574300",
      "onPrimaryContainer": "#FFE08A",
      "primaryFixed": "#FFE08A",
      "primaryFixedDim": "#F5C84C",
      "onPrimaryFixed": "#241A00",
      "onPrimaryFixedVariant": "#574300",
      "secondary": "#ADC6FF",
      "onSecondary": "#102F60",
      "secondaryContainer": "#2B4678",
      "onSecondaryContainer": "#D8E2FF",
      "secondaryFixed": "#D8E2FF",
      "secondaryFixedDim": "#ADC6FF",
      "onSecondaryFixed": "#001A41",
      "onSecondaryFixedVariant": "#2B4678",
      "tertiary": "#80D5C8",
      "onTertiary": "#003731",
      "tertiaryContainer": "#005048",
      "onTertiaryContainer": "#9DF2E4",
      "tertiaryFixed": "#9DF2E4",
      "tertiaryFixedDim": "#80D5C8",
      "onTertiaryFixed": "#00201C",
      "onTertiaryFixedVariant": "#005048",
      "surface": "#111318",
      "surfaceDim": "#0D1015",
      "surfaceBright": "#37393E",
      "surfaceContainerLowest": "#0C0E13",
      "surfaceContainerLow": "#171A20",
      "surfaceContainer": "#1C1F26",
      "surfaceContainerHigh": "#262A33",
      "surfaceContainerHighest": "#313540",
      "onSurface": "#E2E2E9",
      "onSurfaceVariant": "#C4C6D0",
      "outline": "#8E9099",
      "outlineVariant": "#44474F",
      "inverseSurface": "#E2E2E9",
      "onInverseSurface": "#2E3036",
      "inversePrimary": "#745B00",
      "error": "#FFB4AB",
      "onError": "#690005",
      "errorContainer": "#93000A",
      "onErrorContainer": "#FFDAD6",
      "scrim": "#000000",
      "shadow": "#000000",
      "pdfHighlightFill": "rgba(250, 204, 21, 0.35)",
      "pdfHighlightBorder": "rgba(245, 158, 11, 0.85)"
    },
    "light": {
      "primary": "#745B00",
      "onPrimary": "#FFFFFF",
      "primaryContainer": "#FFE08A",
      "onPrimaryContainer": "#241A00",
      "primaryFixed": "#FFE08A",
      "primaryFixedDim": "#F5C84C",
      "onPrimaryFixed": "#241A00",
      "onPrimaryFixedVariant": "#574300",
      "secondary": "#445E91",
      "onSecondary": "#FFFFFF",
      "secondaryContainer": "#D8E2FF",
      "onSecondaryContainer": "#001A41",
      "secondaryFixed": "#D8E2FF",
      "secondaryFixedDim": "#ADC6FF",
      "onSecondaryFixed": "#001A41",
      "onSecondaryFixedVariant": "#2B4678",
      "tertiary": "#006A60",
      "onTertiary": "#FFFFFF",
      "tertiaryContainer": "#9DF2E4",
      "onTertiaryContainer": "#00201C",
      "tertiaryFixed": "#9DF2E4",
      "tertiaryFixedDim": "#80D5C8",
      "onTertiaryFixed": "#00201C",
      "onTertiaryFixedVariant": "#005048",
      "surface": "#F9F9FF",
      "surfaceDim": "#D9D9E0",
      "surfaceBright": "#F9F9FF",
      "surfaceContainerLowest": "#FFFFFF",
      "surfaceContainerLow": "#F3F3FA",
      "surfaceContainer": "#EDEDF4",
      "surfaceContainerHigh": "#E7E8EE",
      "surfaceContainerHighest": "#E2E2E9",
      "onSurface": "#191C20",
      "onSurfaceVariant": "#44474F",
      "outline": "#74777F",
      "outlineVariant": "#C4C6D0",
      "inverseSurface": "#2E3036",
      "onInverseSurface": "#F0F0F7",
      "inversePrimary": "#F5C84C",
      "error": "#BA1A1A",
      "onError": "#FFFFFF",
      "errorContainer": "#FFDAD6",
      "onErrorContainer": "#410002",
      "scrim": "#000000",
      "shadow": "#000000"
    }
  },
  "typography": {
    "families": {
      "display": "'Sora', system-ui, -apple-system, sans-serif",
      "body": "'Figtree', system-ui, -apple-system, sans-serif",
      "mono": "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace"
    },
    "scale": {
      "headlineSmall": { "sizePx": 24, "lineHeightPx": 32, "weight": 600 },
      "titleLarge": { "sizePx": 22, "lineHeightPx": 28, "weight": 600 },
      "titleMedium": { "sizePx": 16, "lineHeightPx": 24, "weight": 600 },
      "titleSmall": { "sizePx": 14, "lineHeightPx": 20, "weight": 600 },
      "bodyLarge": { "sizePx": 15, "lineHeightPx": 25, "weight": 400 },
      "bodyMedium": { "sizePx": 14, "lineHeightPx": 22, "weight": 400 },
      "bodySmall": { "sizePx": 12, "lineHeightPx": 18, "weight": 400 },
      "labelLarge": { "sizePx": 14, "lineHeightPx": 20, "weight": 600 },
      "labelMedium": { "sizePx": 12, "lineHeightPx": 16, "weight": 600 },
      "labelSmall": { "sizePx": 11, "lineHeightPx": 16, "weight": 600 }
    }
  },
  "shape": {
    "none": "0px",
    "extraSmall": "4px",
    "small": "8px",
    "medium": "12px",
    "large": "16px",
    "largeIncreased": "20px",
    "extraLarge": "28px",
    "extraLargeIncreased": "32px",
    "extraExtraLarge": "48px",
    "full": "9999px"
  },
  "elevation": {
    "Level0": "0dp (surfaceContainerLowest)",
    "Level1": "1dp (surfaceContainerLow / surfaceContainer)",
    "Level2": "3dp (surfaceContainerHigh + 0 4px 16px rgba(0,0,0,0.32))",
    "Level3": "6dp (surfaceContainerHighest + 0 8px 24px rgba(0,0,0,0.38))",
    "Level4": "8dp",
    "Level5": "12dp"
  },
  "stateLayerOpacity": {
    "hover": 0.08,
    "focus": 0.12,
    "pressed": 0.12,
    "dragged": 0.16
  },
  "motion": {
    "scheme": "expressive",
    "compiledBy": "m3-expressive-architect/scripts/compile_springs.py --platform web --scheme expressive",
    "springs": {
      "fast-spatial": { "zeta": 0.6, "k": 800, "durationMs": 359 },
      "default-spatial": { "zeta": 0.8, "k": 380, "durationMs": 434 },
      "slow-spatial": { "zeta": 0.8, "k": 200, "durationMs": 599 },
      "fast-effects": { "zeta": 1.0, "k": 3800, "durationMs": 149 },
      "default-effects": { "zeta": 1.0, "k": 1600, "durationMs": 230 },
      "slow-effects": { "zeta": 1.0, "k": 800, "durationMs": 326 }
    }
  }
}
```

### 2.2 Component & Physics Tier Mapping

| Element ID | M3 Component + Exact Variant | Physics Tier | Shape Morph Rule | Touch Target (`>=48dp`) & Contrast Pair |
| :--- | :--- | :--- | :--- | :--- |
| `E-01` | M3 Small Top App Bar (`surfaceContainer`) | Tier 3 | Static `none` (`0px`) | Full-width `64px` bar; `onSurface` on `surfaceContainer` (`>12:1`) |
| `E-02` | Brand Wordmark & Emblem | Tier 3 | Static `none` | Non-interactive header mark; `onSurface` + `primary` on `surfaceContainer` (`>10:1`) |
| `E-03` | M3 Outlined Select Dropdown | Tier 2 | Static `medium` (`12px`), focus outline accent | `48px` height (`40px` pointer-fine desktop); `onSurface` on `surfaceContainerHigh` (`>10:1`) |
| `E-04` | M3 Standard Icon Button (Delete) | Tier 2 | `full` (`9999px`) → `medium` (`12px`) on `:active` | `48x48dp` touch target (`40x40px` pointer-fine); `onSurfaceVariant` / `error` on `surfaceContainer` (`>=7:1`) |
| `E-05` | M3 Filled Tonal Button (`Upload PDF`) | Tier 2 | `full` (`9999px`) → `medium` (`12px`) on `:active` | `48dp` min-height touch (`40px` pointer-fine); `onSecondaryContainer` on `secondaryContainer` (`>8:1`) |
| `E-06` | M3 Filled / Tonal Toggle Button (`Add / Generate Deep Script`) | Tier 2 | `full` (`9999px`) → `medium` (`12px`) when expanded/pressed | `48dp` min-height touch (`40px` pointer-fine); `onPrimary` on `primary` (`>10:1`) or `onPrimaryContainer` on `primaryContainer` (`>8:1`) |
| `E-07` | M3 Top-Anchored Expressive Sheet + Scrim | Tier 1 | Static `extraLarge` (`28px`) bottom corners (`0 0 28px 28px`) | Scrim full-viewport dismiss hit target; `onSurface` on `surfaceContainerHigh` (`>10:1`) |
| `E-08` | M3 Outlined Number Text Fields (`From Page` / `To Page`) | Tier 3 | Static `small` (`8px`) | `48dp` height touch (`40px` pointer-fine); `onSurface` on `surfaceContainerHighest` (`>9:1`) |
| `E-09` | M3 Linear Coverage Indicator + Status Pills | Tier 3 | Static `full` (`9999px`) track & badges | Read-only status strip; `onErrorContainer` on `errorContainer` (`>8:1`) for skipped warnings |
| `E-10` | M3 Filled Tonal Button (`Copy Prompt for Gemini Pro`) | Tier 2 | `full` (`9999px`) → `medium` (`12px`) on `:active` | `48dp` height touch (`40px` pointer-fine); `onPrimaryContainer` on `primaryContainer` (`>8:1`) |
| `E-11` | M3 Outlined Multiline Textarea (Gemini JSON) | Tier 3 | Static `medium` (`12px`) | `>=120px` tap area; `onSurface` on `surfaceContainerLowest` (`>13:1`) |
| `E-12` | M3 Outlined Select + Outlined Button (`Re-synthesize Voice`) | Tier 2 | Button `full` → `medium` (`12px`) on `:active` | `48dp` height touch (`40px` pointer-fine); `onSurface` on `surfaceContainerHigh` (`>10:1`) |
| `E-13` | M3 Expressive Action Button Group (`Append`, `Replace`, `Undo`) | Tier 2 | `full` (`9999px`) → `small` (`8px`) on `:active` | `48dp` height touch (`40px` pointer-fine); `onPrimary`/`primary`, `onSecondaryContainer`/`secondaryContainer`, `onSurface`/`outline` (`>=7:1`) |
| `E-14` | M3 Determinate Linear Progress Indicator | Tier 3 | Static `full` (`9999px`) bar ends; GPU `transform: scaleX()` progress fill | Read-only `aria-live="polite"` region; `primary` indicator on `surfaceContainerHighest` |
| `E-15` | M3 Inline Alert Banner (Error / Warning) | Tier 3 | Static `large` (`16px`) corners, 1px full outline (no side-stripe) | Dismiss icon `48x48dp` touch (`40px` desktop); `onErrorContainer`/`errorContainer` (`>8:1`) |
| `E-16` | M3 Docked Playback Toolbar + Primary Play/Pause Pill | Tier 2 | Play/Pause `full` (`9999px`) ↔ `medium` (`12px`) when playing/pressed; Prev/Next/Repeat `full` → `small` | `48x48dp` touch targets (`40px` pointer-fine desktop); `onPrimary` on `primary` (`>10:1`) |
| `E-17` | M3 Expressive Connected Speed Button Group | Tier 2 | Unselected `full` (`9999px`) ↔ Selected `small` (`8px`) via `fast-spatial` | `48dp` height touch (`36–40px` pointer-fine); `onPrimaryContainer` on `primaryContainer` (`>8:1`) |
| `E-18` | M3 Expressive Line-Index Scrubber + Tabular Readout | Tier 2 | Slider thumb pill morphs on press/drag (`fast-spatial`) | `48dp` vertical hit strip around track; `primary` fill + `onSurface` readout (`>12:1`) |
| `E-19` | M3 Filter Chip (`Auto-Scroll: ON/OFF`) | Tier 2 | Unselected `small` (`8px`) ↔ Selected `full` (`9999px`) via `fast-spatial` | `48dp` touch wrapper (`40px` pointer-fine); `onSecondaryContainer` on `secondaryContainer` (`>8:1`) |
| `E-20` | M3 Primary Pane — Synced PDF Viewer + Chunk Overlays | Tier 3 | Zoom buttons Tier 2 (`full` → `small`); PDF pages & chunk overlays Tier 3 static tonal (`extraSmall` 4px overlay corners) | Zoom controls `48dp` touch (`40px` desktop); chunk highlight `rgba(250, 204, 21, 0.35)` + amber border on white PDF pages |
| `E-21` | M3 Supporting Pane — Live Dialogue & Exam Notes List | Tier 3 | Cards `largeIncreased` (`20px`), `exam_note` callout `medium` (`12px`), speaker badges `full` (`9999px`) — zero spatial spring on list rows | Full card clickable (`>=64px` height); `onSurface` on `surfaceContainer` (`>12:1`), `onPrimaryContainer` on `primaryContainer` (`>8:1`) |
| `E-22` | M3 Expressive Snackbar / Toast Stack | Tier 2 | Static `medium` (`12px`) container; action buttons `full` (`9999px`) | Action buttons `48dp` touch (`40px` desktop); `onInverseSurface` on `inverseSurface` (`>12:1`) |
| `E-23` | M3 Segmented Mobile Pane Switcher (`<840px`) | Tier 2 | Pill outer (`full`), active tab pill indicator (`full` → `medium` on press) | `48dp` height touch target; `onSecondaryContainer` on `secondaryContainer` (`>8:1`) |

---

### 2.3 Motion Specification (Split Spatial / Effects Springs)

All CSS `linear(...)` spring values are generated verbatim by `python scripts/compile_springs.py --platform web --scheme expressive`. Never animate `width`, `height`, `top`, `left`, `margin`, or `padding`.

| Interaction ID | Tier | Spatial Track (Property + Spring Token) | Effects Track (Property + Spring Token) | Interruption Rule | Reduced-Motion Fallback (`<=200ms` fade) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `I-01` | Tier 3 | None (instant swap of PDF/Dialogue views) | `opacity` (`default-effects`, 230ms) | Latest session selection cancels prior fetch via `AbortController` | `opacity 150ms ease-out` |
| `I-02` | Tier 2 | `transform: scale(0.97)` + `border-radius` (`fast-spatial`, 359ms) | State-layer `opacity` (`fast-effects`, 149ms) | Pointer-up reverses CSS transition from current frame | `opacity 150ms ease-out` (no scale/morph) |
| `I-03` | Tier 2 | `transform: scale(0.97)` + `border-radius` (`fast-spatial`, 359ms) | `background-color` state-layer (`fast-effects`, 149ms) | Interruptible CSS transition; disabled during active upload | `opacity 150ms ease-out` |
| `I-04` | Tier 1 | `transform: translateY(-12px)` + `clip-path` on `E-07` (`default-spatial`, 434ms) | Sheet & scrim `opacity` (`default-effects`, 230ms) | Toggling mid-flight immediately reverses transform & opacity from current progress | `opacity 150ms ease-out` (instant visibility toggle, zero translate) |
| `I-05` | Tier 3 | None | `border-color` focus state (`fast-effects`, 149ms) | Immediate input updates | `border-color 150ms ease-out` |
| `I-06` | Tier 2 | `transform: scale(0.97)` + `border-radius` on `E-10` (`fast-spatial`, 359ms) | State-layer & icon swap `opacity` (`fast-effects`, 149ms) | Repeated clicks restart snackbar timer cleanly | `opacity 150ms ease-out` |
| `I-07` | Tier 2 | `transform: scale(0.97)` on `E-13`; `transform: scaleX()` on `E-14` (`default-spatial`, 434ms) | Banner `opacity` on `E-15` (`default-effects`, 230ms) | Polling stops immediately on completion/error; `409` prevents double submit | `opacity 150ms ease-out` (bar updates without spring overshoot) |
| `I-08` | Tier 2 | `transform: scale(0.97)` + `border-radius` (`fast-spatial`, 359ms) | `background-color` / `opacity` (`fast-effects`, 149ms) | Interruptible press; disabled while undo request in flight | `opacity 150ms ease-out` |
| `I-09` | Tier 2 | `transform: scale(0.97)` on `E-12` + `transform: scaleX()` on `E-14` (`default-spatial`, 434ms) | State-layer `opacity` (`fast-effects`, 149ms) | `409` prevents overlap; status resets in `finally` | `opacity 150ms ease-out` |
| `I-10` | Tier 2 | Pointer click: `transform: scale(0.97)` + `border-radius` (`fast-spatial`, 359ms). Keyboard `Space`: **0ms instant** | Play/Pause SVG `opacity` (`fast-effects`, 149ms) | Clicking/pressing `Space` increments `playbackToken` and cancels pending `200ms` breath timer | `opacity 150ms ease-out` (0ms on `Space`) |
| `I-11` | Tier 2 | Pointer click: `transform: scale(0.95)` (`fast-spatial`, 359ms). Keyboard arrows: **0ms instant** | State-layer `opacity` (`fast-effects`, 149ms) | Rapid taps/arrows cancel prior preload/timers via `playbackToken` | `opacity 150ms ease-out` (0ms on arrows) |
| `I-12` | Tier 2 | Pointer click: `transform: scale(0.95)` (`fast-spatial`, 359ms). Keyboard `R`: **0ms instant** | State-layer `opacity` (`fast-effects`, 149ms) | Immediately resets `activeDeck.currentTime = 0` | `opacity 150ms ease-out` (0ms on `R`) |
| `I-13` | Tier 2 | `border-radius` (`full` ↔ `small`) + `transform: scale(0.97)` (`fast-spatial`, 359ms) | `background-color` + `color` (`fast-effects`, 149ms) | Selecting another pill mid-morph retargets CSS transition cleanly | `opacity 150ms ease-out`, instant radius |
| `I-14` | Tier 2 | Thumb `transform: scale(1.12)` on drag (`fast-spatial`, 359ms) | Track fill `opacity` (`fast-effects`, 149ms) | Pointer-up commits final line index cleanly | Instant thumb update, `opacity 150ms ease-out` |
| `I-15` | Tier 2 | `border-radius` (`small` ↔ `full`) + `transform: scale(0.97)` (`fast-spatial`, 359ms) | `background-color` + `color` (`fast-effects`, 149ms) | Retargets immediately on rapid toggles | `background-color 150ms ease-out`, no morph |
| `I-16` | Tier 2 | Zoom button `transform: scale(0.96)` (`fast-spatial`, 359ms) | Canvas swap `opacity` (`fast-effects`, 149ms) | Rapid `+/-` clicks cancel active PDF.js `RenderTask`s immediately | `opacity 150ms ease-out` |
| `I-17` | Tier 3 | None (zero spatial spring on PDF overlays) | Overlay `background-color` + `border-color` (`fast-effects`, 149ms) | Clicking any chunk jumps playback immediately via `playbackToken` | `opacity 150ms ease-out` |
| `I-18` | Tier 3 | None (zero spatial spring on scrolling dialogue rows) | Card tonal `background-color` + `border-color` (`default-effects`, 230ms) | Rapid card clicks update active index immediately without queueing | `background-color 150ms ease-out` |
| `I-19` | Tier 2 | Active tab indicator `transform: translateX()` (`default-spatial`, 434ms) | Pane `opacity` (`fast-effects`, 149ms) | Tapping opposite tab mid-slide reverses smoothly | `opacity 150ms ease-out` (no slide) |
| `I-20` | Tier 2 | Snackbar `transform: translateY(8px) scale(0.96)` → `translateY(0) scale(1)` (`default-spatial`, 434ms; exit faster `fast-effects`) | Snackbar `opacity` (`fast-effects`, 149ms) | New toasts retarget cleanly; auto-dismiss timer pauses when `document.hidden` | `opacity 150ms ease-out` (no translate/scale) |

---

### 2.4 State, Offline & Accessibility Coverage

- **Loading States:**
  - *Session / PDF Load:* Subtle tonal skeleton surfaces (`surfaceContainerHigh` pulse via `opacity` on `slow-effects`) inside `E-20` and `E-21` before pages render.
  - *TTS Synthesis (`E-14`):* Determinate M3 linear progress bar driven by `GET /generate/status` polling (`Synthesizing 14 / 48 clips (3 cached) · 11s`) scaled via GPU `transform: scaleX()` (zero `width` animation!).
- **Empty States:**
  - *No PDF Uploaded:* Left pane (`E-20`) displays a structured upload prompt card (`surfaceContainer`, `largeIncreased` 20px corners) with primary `Upload PDF` CTA; Right pane (`E-21`) outlines the 3-step workflow (`1. Upload PDF → 2. Copy Prompt to Gemini → 3. Paste JSON & Listen`).
  - *PDF Loaded, 0 Script Lines:* Auto-opens Top-Anchored Sheet (`E-07`) with `From Page`/`To Page` pre-filled from `suggested_next_range`; Right pane displays a clean callout prompting the user to paste Gemini's JSON.
- **Error States:**
  - *Upload / JSON / Skipped Chunks / `502` TTS:* Rendered inside `E-15` (`errorContainer`/`onErrorContainer` or `primaryContainer`/`onPrimaryContainer` for warnings) with line/column snippet, skipped chunk ID pills, and retry guidance.
  - *Audio Clip Load Failure:* Non-blocking Snackbar (`E-22`) with `Retry Line` and `Skip to Next` buttons.
- **Offline State:**
  - Inline `<style>` declares full M3 Dark tokens, compiled `linear()` springs, AND complete structural layout classes (`E-01`..`E-23`) so saved chapters render identically offline even without Tailwind CDN.
  - PDF.js tries local `/static/vendor/pdf.min.mjs` before falling back to jsDelivr CDN (`4.10.38`) with same-origin Blob worker shim.
- **Accessibility & Keyboard Traversal:**
  - Semantic landmarks (`<header>`, `<main>`, `<aside>`, `<nav>`), real `<button>` elements for all interactive controls, `aria-expanded` on `E-06`, `aria-pressed` on `E-17`/`E-19`, `aria-live="polite"` on `E-14`/`E-22`.
  - Visible `3px` `:focus-visible` outline using `var(--md-sys-color-secondary)` with `2px` offset across every interactive control.
  - Minimum `48x48dp` interactive hit target on touch viewports (`Compact`/`Medium`), `40px` allowed on pointer-fine desktop (`Expanded`/`Large`/`Extra-large`).
  - All hover state-layer rules (`8%` tint) gated behind `@media (hover: hover) and (pointer: fine)`.
  - Zero `innerHTML` with untrusted text; exclusively `textContent` / `document.createElement`.
