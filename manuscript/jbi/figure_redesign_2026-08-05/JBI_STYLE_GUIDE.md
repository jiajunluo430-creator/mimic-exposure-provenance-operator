# JBI data-first figure style guide

## Purpose

This redesign replaces rounded-card and presentation-slide composition with a restrained visual grammar suited to a biomedical-informatics methods paper. The redesign changes presentation only. Frozen counts, windows, analysis units, operator definitions, and claim boundaries are unchanged.

## Locked visual contract

- White background; no gradients, shadows, decorative containers, or dashboard composition.
- Square corners for true tables or data cells. Narrative text is not enclosed in cards.
- Arial or Helvetica live text. Panel titles are 14.5 pt in the drawing coordinate system; labels are generally 8–10 pt.
- Primary rules are 0.8–1.2 pt; quantitative marks use direct labels whenever space permits.
- Blue encodes source or order-defined information; teal encodes delivered or supported information; orange encodes unresolved, partial, or administration-defined contrasts; dark gray encodes unavailable or unmeasurable states.
- Status is redundant in shape and color: solid circle = supported, ring plus center dot = partial or relocated, cross = structurally unavailable.
- Architecture uses lanes and a process spine. Capability uses a glyph matrix. Proportions use lollipop or stacked-bar marks. Paired effects use aligned confidence intervals and connecting lines.
- Footnotes use a short rule and sentence, not a shaded callout box.

## Figure-specific redesign

1. Figure 1: source lanes and a canonical-event table replace nested rounded cards; the operator is a spine, validation chain, and explicit state branch.
2. Figure 2: the parity scatter remains on matched log axes; ablation bars become connected point profiles for A1 and A2.
3. Figure 3: filled capability cards become a shape-coded matrix; FHIR concordance becomes a lollipop plot; fail-closed states remain directly comparable stacked bars.
4. Figure 4: reporting percentages become lollipops; the decorative funnel becomes a count-retention curve on a common axis.
5. Figure 5: reclassification stays as a compact composition bar; the construct note becomes a footnote; paired effects remain a forest-style comparison with lighter row structure.

## Reuse

Use `scripts/70_make_jbi_redesigned_figures.py` as the canonical renderer. The template SVG and PDF in `template/` show the reusable process spine, status glyphs, quantitative marks, typography, and palette.

