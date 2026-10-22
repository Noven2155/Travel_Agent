---
name: Travel Comparison Studio
description: The confirmed open white Hebrew comparison workspace with navy text and restrained blue.
colors:
  navy: '#102b43'
  blue: '#2559cb'
  blue-hover: '#1746aa'
  white: '#fff'
  muted: '#617181'
  line: '#dce4ec'
  soft: '#f4f7fa'
  rail: '#f5f8fb'
  nav-active: '#eaf0fb'
  nav-hover: '#eaf0f7'
  working-bg: '#edf2fc'
  input-border: '#c9d5e1'
  focus: '#91b3ff'
  panel: '#f6f8fc'
  button-pale: '#e3eafb'
  green: '#267058'
  success-bg: '#eff7f2'
  amber: '#8a5a14'
  pending-bg: '#faf5e9'
  offline-bg: '#faf6ed'
  offline-text: '#755219'
  error-bg: '#fff2f0'
  error-text: '#9a352c'
typography:
  display:
    fontFamily: Noto, Arial, sans-serif
    fontSize: clamp(36px, 3.7vw, 56px)
    fontWeight: 700
    lineHeight: 1.24
    letterSpacing: -.035em
  headline:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 21px
    fontWeight: 700
    letterSpacing: -.02em
  title:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 20px
    fontWeight: 700
  body:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.85
  label:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 13px
    fontWeight: 400
  result-metric:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: -.02em
  action:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 15px
    fontWeight: 700
  compact:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 12px
    fontWeight: 400
  note:
    fontFamily: Noto, Arial, sans-serif
    fontSize: 11px
    fontWeight: 400
rounded:
  tag: 4px
  brand: 5px
  control: 6px
  panel: 8px
  results-phone: 10px
  results: 12px
spacing:
  '4': 4px
  '6': 6px
  '8': 8px
  '10': 10px
  '12': 12px
  '14': 14px
  '16': 16px
  '18': 18px
  '20': 20px
  '22': 22px
  '24': 24px
  '28': 28px
  '32': 32px
  '42': 42px
  '44': 44px
components:
  button-primary:
    backgroundColor: '{colors.blue}'
    textColor: '{colors.white}'
    typography: '{typography.action}'
    rounded: '{rounded.control}'
    padding: 0 28px
    height: 54px
  button-primary-hover:
    backgroundColor: '{colors.blue-hover}'
  button-small-primary:
    backgroundColor: '{colors.blue}'
    textColor: '{colors.white}'
    typography: '{typography.compact}'
    rounded: '{rounded.control}'
    padding: 9px 16px
  button-small-primary-hover:
    backgroundColor: '{colors.blue-hover}'
  button-text:
    textColor: '{colors.blue}'
    typography: '{typography.compact}'
    padding: 8px 0
  button-pale:
    backgroundColor: '{colors.button-pale}'
    textColor: '{colors.blue}'
    typography: '{typography.compact}'
    rounded: '{rounded.control}'
    padding: 9px 15px
  input:
    backgroundColor: '{colors.white}'
    textColor: '{colors.navy}'
    typography: '{typography.body}'
    rounded: '{rounded.control}'
    padding: 10px 12px
  textarea:
    backgroundColor: '{colors.white}'
    textColor: '{colors.navy}'
    rounded: '{rounded.control}'
    padding: 16px 18px
    width: 100%
  navigation-active:
    backgroundColor: '{colors.nav-active}'
    textColor: '{colors.blue}'
    rounded: '{rounded.control}'
    padding: 15px 12px
  chip:
    backgroundColor: '{colors.soft}'
    textColor: '{colors.navy}'
    typography: '{typography.note}'
    rounded: '{rounded.tag}'
    padding: 5px 9px
  results-container:
    backgroundColor: '{colors.white}'
    rounded: '{rounded.results}'
  tab-active:
    textColor: '{colors.blue}'
    typography: '{typography.compact}'
    padding: 11px 0
  status-neutral:
    backgroundColor: '{colors.soft}'
    textColor: '{colors.muted}'
    typography: '{typography.compact}'
    padding: 10px 20px
  status-good:
    backgroundColor: '{colors.success-bg}'
    textColor: '{colors.green}'
  status-pending:
    backgroundColor: '{colors.pending-bg}'
    textColor: '{colors.amber}'
  status-working:
    backgroundColor: '{colors.working-bg}'
    textColor: '{colors.blue}'
---

# Design System: Travel Comparison Studio

## Overview

**Creative North Star: "Open white workspace"**

The confirmed direction is an open white React workspace, navy typography, restrained blue and a narrow right navigation rail. This document records the implemented system; it extends the selected visual direction without introducing another visual identity. The confirmed anti-reference is a dense, generic AI dashboard.

Whitespace, thin dividers and grouped content establish hierarchy. The current comparison surface uses one shared request and a primary run action, with package, itinerary and evidence details inside result tabs. This describes the implemented surface rather than requiring every future screen to repeat its composition.

**Key Characteristics:**

- White workspace with navy text and restrained blue actions.
- A narrow pale right rail in the desktop layout.
- Flat surfaces separated by strokes, spacing and pale status fills.
- Hebrew RTL content with explicit LTR treatment for routes, prices and technical values.

Evidence: `PRODUCT.md`, `AGENTS.md`, `frontend/src/App.tsx` and `frontend/src/styles.css`. The selected direction image at `../tourism_react_studio/design/selected-direction.png` was inspected. The current desktop capture at `.impeccable/review/desktop.jpg` (1363 × 936) was also inspected; it shows the A itinerary with B/C missing-model panels. The phone layout CSS exists, but a phone viewport capture was unavailable. Values below are extracted from source; they are not a claim of full responsive visual verification.

## Colors

The palette uses navy and a single restrained blue accent, supported by pale neutrals and state-specific green, amber and red. Frontmatter is the normative color source; the following describes its application.

### Primary

- **Navy** (`navy`): default text, major headings, route and metric values.
- **Blue** (`blue`): the main run action, links, active navigation, selected scenario underline, active result tabs, route times and focus-related input behavior. The primary hover variant uses `blue-hover`.
- **Pale blue** (`nav-active`, `working-bg`, `button-pale`): separate implemented fills for active navigation, working state/system letters and the inline connection action. Preserve these roles rather than applying one broad blue wash.

### Neutral

- **White** (`white`): the workspace, request editor, inputs and result columns.
- **Muted slate** (`muted`): supporting copy, labels and notes.
- **Divider** (`line`): section rules, result-column separation, tab boundaries and table-related grouping.
- **Soft neutral** (`soft`): interest tags, neutral run status and table headings.
- **Pale rail** (`rail`): desktop navigation background. `nav-hover` is the navigation-button hover fill.
- **Utility panel** (`panel`): the expanded settings and history surfaces.
- **Input border** (`input-border`): the shared field outline. **Focus blue** (`focus`) supplies the common focus-visible outline.

State colors are semantic: `green` with `success-bg` for a valid plan; `amber` with `pending-bg` for a missing model; `blue` with `working-bg` while running; `offline-text` with `offline-bg` for the connection notice; `error-text` with `error-bg` for an error banner. Labels and icons accompany the fills.

## Typography

**Display and body font:** locally served Noto Sans Hebrew, registered as `Noto`, followed by Arial and sans-serif. The CSS loads regular and bold files (400 and 700) with font-display swap and disables font synthesis. There is no separate display face or monospace system.

The hierarchy uses size, bold weight, restrained negative letter spacing and generous Hebrew body leading. It is an observed set of roles rather than a mathematically imposed type scale.

### Hierarchy

- **Display** (`display`): the two-line page heading; blue emphasizes its second line. Its responsive size, weight, line height and tracking are in frontmatter.
- **Headline** (`headline`): section headings. Phone section headings reduce to 19px.
- **Title** (`title`): desktop result-column headings. At the compact desktop breakpoint they reduce to 17px; stacked results use 21px.
- **Body** (`body`): the root size and paragraph leading. The page introduction overrides leading to 1.9; the request textarea uses 15px with 1.9 leading.
- **Label** (`label`): default form labels and desktop rail labels. Dense result labels use 11px; result tabs and supporting controls commonly use `compact`.
- **Metric** (`result-metric`): result price and engine time; tabular numerals preserve alignment. The compact desktop metric size is 21px and the stacked result size is 27px.
- **Notes** (`note`): supporting request and measurement copy. Fine result evidence and footer text uses 9–10px in source; do not promote those values into the general body role.

## Layout

The shell is RTL. On the regular desktop layout, a fixed right rail occupies 192px and the main content has the corresponding right margin, maximum width of 1690px and padding of 28px 42px 0. Main sections are full-width white regions separated by thin horizontal rules. No central card wraps the whole workspace.

The current surface uses a four-column scenario picker, flexible route summary, one shared request editor and a toolbar whose run action is visually strongest. Results share a single bordered container split into three equal columns. Internal result regions generally use 20px padding. Advanced fields begin as four columns, settings and measurement notes as two columns. Spacing tokens list recurring source values; they are an observed vocabulary, not a new mandatory spacing scale.

| Source condition | Implemented behavior |
| --- | --- |
| At least 1600px | Main horizontal padding becomes 65px; result heading and content padding becomes 24px. |
| At most 1180px | Rail is 160px; main padding is 24px. Heading copy moves below the heading, result content becomes denser and advanced fields use three columns. |
| At most 850px | Rail is 76px and primarily icons. Main padding is 22px. Result columns stack vertically and regain larger text and padding; settings become one column and advanced fields become two columns. |
| At most 540px | Navigation becomes a static top row, main right margin is removed and main padding is 20px. Scenario choices use two columns, the run action spans the available width, and measurement notes become one column. The main heading is 38px. |

The results container clips to its radius, while long technical text and evidence logs have their own bounded scroll areas. The metric table wrapper allows horizontal scrolling. The source limits the width of supporting prose in several contexts; those local limits are not a universal body measure.

## Elevation & Depth

The implementation is flat: it defines no box-shadow vocabulary. Pale fills identify the rail, active navigation, utility panels and run states; borders separate adjacent content. The fixed rail has a z-index of 10 for placement. Do not infer floating cards, modals or ambient shadows from that stacking value.

## Shapes

Corners are modest. Interest tags and system letters use `tag`; the brand mark uses `brand`; controls, notices and active navigation use `control`; settings/history panels use `panel`. The shared results frame uses `results`, reduced to `results-phone` at the phone breakpoint. State dots are circular. Separators and field outlines are thin (1px); selected scenarios and active result tabs use a 2px bottom rule.

## Components

### Buttons

The main action is a solid blue rectangle with bold white text, a 54px minimum height, 217px minimum width, 14px internal icon gap and `control` corners. The phone rule changes its minimum height to 55px and makes it full width. Hover changes its background to `blue-hover` without a transform or shadow. The small solid action uses regular compact text with 9px 16px padding and the same hover color.

Text actions use blue, a transparent background and 8px 0 padding; export has its own 10px 0 spacing and an icon. The inline connection action uses `button-pale`, compact blue text and 9px 15px padding. Buttons disabled by application state use opacity 0.48 and a not-allowed cursor. There are no authored press animations.

All focusable controls share a 3px `focus` outline with 3px offset. Links underline on hover. The shared focus treatment, disabled treatment and state animation definitions are carried in the sidecar because they do not fit component frontmatter.

### Chips

Interest and pace tags are noninteractive text spans with a soft neutral fill, no border, `tag` corners and 5px 9px padding. They do not have a selected or hover state.

### Cards / Containers

The result container is the signature comparison pattern: one border and rounded outer frame containing equal white columns, thin separators and no shadow. Each column contains a system heading, run-state strip, then metrics and tabbed content or an explicit waiting/missing-model state. Its footer settles at the bottom of the flex column. Settings and history use a pale utility fill with 24px padding, reduced to 18px on phones.

### Inputs / Fields

Text fields and selects share a white fill, navy text, `input-border`, `control` corners and 10px 12px padding. Default labels sit above fields with an 8px gap. The request textarea is resizable vertically, full-width, and has 16px 18px padding with 120px minimum height. On phones it uses 14px padding, 13px text and 170px minimum height. Checkboxes use the blue accent and 17px dimensions.

There is no separate authored invalid-field visual variant. Errors appear in the existing banner; source-disabled fields remain native controls, while the custom opacity rule applies to buttons only.

### Navigation

Desktop navigation sits in the pale fixed right rail. Entries have icons, 13px labels, 15px 12px padding and 50px minimum height. The active entry uses blue text, bold weight and the active pale-blue fill. Navigation buttons have the separate `nav-hover` fill on hover. The compact rail hides labels at 850px; the phone navigation is a static top row with 37px minimum-height icon controls. The source retains the same navigation structure across these breakpoints.

### Tabs and disclosures

Result tabs are a simple text row over a bottom divider. The selected tab is blue and bold with a 2px bottom underline; each tab uses 11px 0 padding. The React uses tab, tablist and tabpanel roles with selected-state and control associations. Native details/summary elements reveal price breakdowns, tradeoffs, check details, advanced evaluation settings and technical connection messages. Opening a disclosure adds 12px below its summary.

### Run states and motion

Neutral, good, pending and working strips use the documented semantic fills and a 39px minimum height. Waiting, missing-model and no-package states remain explicit text in the relevant column. Running uses a 1-second linear spinning icon and a 1.7-second progress sweep with the existing easing curve. Starting a comparison scrolls results into view with smooth behavior. The reduced-motion query disables animations/transitions and sets scroll behavior to auto with important declarations; visual verification of that interaction was not part of this extraction.

## Do's and Don'ts

### Do:

- **Do** preserve the confirmed white, navy and restrained-blue direction.
- **Do** use the shared Noto family, the existing weight contrast and the documented role sizes.
- **Do** distinguish active, working, success, pending and error states using the existing colors and text labels.
- **Do** keep RTL layout and preserve explicit LTR direction for routes, prices and technical values.
- **Do** use borders and spacing to group content and reserve pale fills for the existing navigation, state and utility roles.
- **Do** keep the primary task visible and use existing tabs and disclosures for supporting detail.

### Don't:

- **Don't** replace this interface with a dense generic AI dashboard.
- **Don't** add gradients, glass effects or shadows as if they were established parts of this system.
- **Don't** turn all white sections into separate filled cards.
- **Don't** present the phone layout as visually verified until a phone viewport capture has been inspected.
