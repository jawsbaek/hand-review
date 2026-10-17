---
name: hand-review
description: A local poker replay with readable table states and explainable decision review.
colors:
  ink: "#183c33"
  muted: "#4f665e"
  ground: "#eef2f0"
  paper: "#fff"
  line: "#cdd8d2"
  green: "#216549"
  green-hover: "#194c38"
  felt: "#21594b"
  deep: "#143e34"
  surface: "#f8faf9"
  selected: "#dbe9e0"
  selected-line: "#8cae99"
  control-hover: "#e6eee9"
  best: "#236b49"
  best-bg: "#e5f3e9"
  blunder: "#a32e38"
  blunder-bg: "#fcebed"
  review: "#80520e"
  review-bg: "#fff1d5"
  focus: "#b9811e"
  card-ink: "#172e28"
  card-red: "#b3303b"
  seat: "#f5f8f6"
  hero: "#b48a32"
  active-seat: "#cfab5e"
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  brand:
    fontSize: "21px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "-0.025em"
  headline:
    fontSize: "23px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "-0.02em"
  title:
    fontSize: "17px"
    fontWeight: 700
    lineHeight: 1.55
    letterSpacing: "-0.02em"
  subheading:
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.55
  control:
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.55
  detail:
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.75
  label:
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.55
  card:
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1
rounded:
  badge: "4px"
  card: "5px"
  field: "6px"
  button: "7px"
  row-seat: "8px"
  felt: "46%"
spacing:
  compact: "4px"
  small: "6px"
  control: "8px"
  regular: "12px"
  section: "16px"
  inset: "20px"
  panel: "22px"
  wide: "24px"
components:
  button-default:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.button}"
    padding: "8px 12px"
  button-default-hover:
    backgroundColor: "{colors.control-hover}"
  button-primary:
    backgroundColor: "{colors.green}"
    textColor: "{colors.paper}"
    typography: "{typography.control}"
    rounded: "{rounded.button}"
    padding: "8px 12px"
  button-primary-hover:
    backgroundColor: "{colors.green-hover}"
  search-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
    padding: "7px 9px"
  filter:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "5px 9px"
  filter-selected:
    backgroundColor: "{colors.deep}"
    textColor: "{colors.paper}"
  hand-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.row-seat}"
    padding: "11px 10px"
  hand-row-selected:
    backgroundColor: "{colors.selected}"
  street:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "6px 3px"
  street-current:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.deep}"
  badge-best:
    backgroundColor: "{colors.best-bg}"
    textColor: "{colors.best}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
  badge-blunder:
    backgroundColor: "{colors.blunder-bg}"
    textColor: "{colors.blunder}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
  badge-review:
    backgroundColor: "{colors.review-bg}"
    textColor: "{colors.review}"
    rounded: "{rounded.badge}"
    padding: "3px 7px"
  playing-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.card-ink}"
    typography: "{typography.card}"
    rounded: "{rounded.card}"
    width: "41px"
    height: "57px"
  player-seat:
    backgroundColor: "{colors.seat}"
    textColor: "{colors.ink}"
    rounded: "{rounded.row-seat}"
    padding: "5px 8px"
---

# Design System: hand-review

## Overview

The implemented visual system uses a dark green poker table inside a pale, compact review workspace. The table carries the game state; ordinary browser controls, restrained panels and Korean UI text support replay and decision inspection.

Color and emphasis explain state. White cards stand out against felt, warm outlines distinguish the reviewing player and active seat, and labeled review badges separate decision classifications. This document records the working screen without adding a metaphor or an unconfirmed aesthetic preference.

**Key Characteristics:**

- Dark felt and pale work surfaces.
- Compact Korean UI typography with aligned numeric values.
- Explicit current, selected, hidden and unavailable states.
- Brief card movement with a reduced-motion alternative.

## Colors

The palette combines green structure, pale neutral surfaces and three labeled review classifications. The frontmatter contains the normative values; additional table-specific colors remain in the implementation and component snippets.

### Primary

- **Control Green** (`green`, `green-hover`): primary playback and comparison actions, links, range controls and checkboxes.
- **Deep Green** (`deep`): the header and selected classification filters.
- **Table Felt** (`felt`): the playing surface behind cards and seats.

### Secondary

- **Best Green** (`best`, `best-bg`): the best-candidate classification.
- **Blunder Red** (`blunder`, `blunder-bg`): the blunder-candidate classification.
- **Review Amber** (`review`, `review-bg`): decisions needing review; the pale background also supports warnings.
- **Focus Amber** (`focus`): the keyboard focus outline. `hero` and `active-seat` are distinct warm accents for table participants.
- **Card Red** (`card-red`): known red card suits; it has a separate role from blunder classification.

### Neutral

- **Green Ink** (`ink`) and **Muted Ink** (`muted`): primary text and supporting copy.
- **Ground**, **Paper** and **Surface** (`ground`, `paper`, `surface`): the workspace, controls/cards, and supporting panels.
- **Divider** (`line`): thin panel boundaries, control borders and table rules.
- **Selected Surface** (`selected`, `selected-line`): current library rows and street navigation, with distinct border treatments in each component.

**The Labeled State Rule.** Review colors accompany classification text; selection and current states also use semantic control attributes.

## Typography

The body font is the system UI stack in the frontmatter, including Korean fallbacks. Headings, controls and labels inherit that stack. The build uses compact interface hierarchy rather than a separate display face.

- **Headline:** the current hand heading uses `headline`, reducing to the brand size on narrow screens.
- **Brand / title / subheading:** identify the product, panels and decisions without competing with the table.
- **Body / detail:** standard UI text uses `body`; decision explanations use `detail` for extra line spacing.
- **Control / label:** controls use semibold text; supporting labels use the smaller label size. Classification badges increase the label weight to bold.
- **Card:** ranks use the card role, with smaller variants for opponent seats and narrow screens.

Pot, stack, contribution, progress and analysis values use tabular numerals. Supporting table labels reduce to smaller sizes inside seats; these are component-specific exceptions, not a general text scale. On narrow screens, decision copy has a maximum width of 65ch.

## Layout

The workspace is centered with a maximum width of 1720px. Its wide layout has a 254px library, a flexible stage with a 410px minimum, and a 318px inspector. Panel boundaries use thin dividers rather than detached cards. Standard stage padding is 22px vertically and 24px horizontally; the library and inspector use their own compact insets.

At 1150px and below, the library narrows to 220px, the stage has a 390px minimum, and the inspector moves below the stage in two columns. At 740px and below, the workspace becomes one column: table, inspector, then library. Header controls wrap, filters retain larger narrow-screen targets, and the library scrolls within its own bounded list.

The table is 468px tall by default, 480px in the middle layout, 410px on narrow screens, and 530px at widths of 1550px and above. The narrow layout reduces card and seat dimensions while keeping the table centered. Spacing tokens record recurring measurements; the implementation does not impose a single arithmetic spacing scale.

## Elevation & Depth

Depth comes mostly from tonal layers and borders. The felt has a thick rail, a fine inset outline and a shallow cast shadow. Face-up cards have a small shadow; card backs and unrevealed slots have none. Panels and controls remain flat. Exact shadow values are retained in the local design sidecar.

## Shapes

The felt and its inset outline share the rounded oval silhouette. Small control corners distinguish buttons, fields, library rows and seat labels. Cards use a tighter radius, while badges and contribution labels use compact corners. The frontmatter records the reused radii; the unused source radius variable is not part of the documented scale.

## Components

### Buttons

Default buttons are white with a thin divider-colored border, semibold text and a minimum height of 40px. Primary buttons fill with Control Green and darken on hover. Default buttons use the pale control-hover surface. Disabled buttons reduce opacity to 0.4. Icon controls use inline SVG; the regular transport width is 40px and the play control is 48px wide.

Interactive buttons, fields, selects and disclosure summaries share a visible amber focus outline (3px, offset 3px). Filter and street controls have compact component-specific heights. Re-rendered controls preserve keyboard focus, and practice submission moves focus to the resulting replay action.

Practice choices use the default button treatment. With no call cost, visible preflop bets produce check and raise choices; an unopened street produces check and bet choices. The raise or bet choice is omitted when raising is unavailable. The status line changes from a choice prompt to a recorded-choice confirmation after selection.

### Inputs / Fields

Search and select controls have white surfaces, thin borders, field corners, padding of 7px by 9px and a minimum height of 38px. Search fills its column. Range controls and checkboxes use the primary green accent. Header selects use the darker header treatment; the speed select is a smaller transport variant.

### Chips

Classification filters are actual buttons with `aria-pressed`; selected filters use the deep fill and white text. Review badges are static labels with paired foreground/background colors. Badges retain visible text so classification does not depend on color alone.

### Navigation

Library entries are full-width button rows, with a two-column heading area and a truncated supporting line. The current row uses a pale selected surface and a visible green border; hover uses a separate pale surface. Street navigation distributes buttons evenly and marks the current street with a pale fill and border. Both patterns expose current state with `aria-current`.

### Cards / Containers

Supporting regions use ground or pale surface fills and divider lines; they are not shadowed floating cards. The decision inspector pairs short headings with explanation text, a two-column numeric summary and optional tabular analysis. Action logs scroll independently and emphasize the current action with green bold text.

Recorded raise copy names the street total, followed by the additional payment in parentheses when the amounts differ. The same wording appears in the decision inspector and action log.

### Playing Cards and Seats

Board cards are white rank-and-suit tiles. Known red suits use Card Red. The unknown suit remains a literal `/s4`, with reduced suffix text. Opponent card backs use a solid border; unrevealed board slots use a dashed border. Neither hidden state implies an unknown future value.

Seat labels use pale fills and compact text. The reviewing player's label has a warm border; the active seat has an additional outline. Folded seats and departed seats that are not all in share the muted surface and text. Departed seats append `이탈` to the position label. A departed all-in seat keeps the live treatment, `ALL IN` stack label and card backs until its cards are revealed. Separate contribution labels use tabular values.

Street changes trigger a brief card-deal motion (0.3s); seat opacity transitions last 0.18s. The reduced-motion preference disables both animations and transitions.

## Do's and Don'ts

### Do:

- **Do** inherit the Korean-capable UI font stack and use tabular numerals for changing amounts.
- **Do** pair classification colors with visible labels and preserve selected/current control semantics.
- **Do** retain the common focus outline and keyboard focus when controls are rebuilt.
- **Do** preserve separate visual states for a card back, an unrevealed slot and a literal unknown suit.
- **Do** keep narrow-screen content in table, inspector, library order and honor reduced motion.

### Don't:

- **Don't** use a red suit or a financial result as a decision-quality signal.
- **Don't** reveal future cards or infer an unknown suit to complete the visual presentation.
- **Don't** put local export content, player identities or session statistics into shared design examples.
