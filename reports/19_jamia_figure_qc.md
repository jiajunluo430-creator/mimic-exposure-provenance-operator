# JAMIA figure QC

Date: 2026-07-30  
Scope: four assembled figures and seven separately editable panels generated
from the source-corrected JAMIA v1.1 aggregate outputs.

## Outcome

All 11 SVG/PDF pairs passed structural vector QC, and all 11 SVG files opened
successfully in Adobe Illustrator.

## Structural and PDF checks

- Live SVG text was retained; no SVG contained an embedded image.
- Every expected panel contained exactly one parent panel group and exactly one
  `axis`, `data`, `labels`, `legend`, and `annotations` semantic subgroup.
- No duplicate IDs, duplicate clip paths, transparent artifact rectangles, or
  abnormal path coordinates were detected.
- PDFs used Type 0/CIDFontType2 fonts, contained no Type 3 fonts, and contained
  zero image XObjects.
- Machine-readable results are under
  `outputs/researchwrite/mimic_order_administration_validity_jamia/qa_logs/vector_figures_final/`.

## Illustrator-open checks

- Four assembled SVGs: 4/4 passed.
- Seven separate panel SVGs: 7/7 passed.
- Each document contained editable text frames and zero placed or raster items.
- Machine-readable results:
  `qa_logs/illustrator_open_main.json` and
  `qa_logs/illustrator_open_panels.json`.

## Rendered visual review

All four PNG previews were inspected at original detail. The initial Figure 3
title/annotation collision and Figure 4 agreement-label placement were
corrected and the full export/QC cycle was repeated. The final figures have
legible titles and axes, distinct order/administration encodings, no clipped
data labels, and a visible story hierarchy:

1. data-generating pathway and audit sequence;
2. observability transition followed by residual delivery discordance;
3. event-semantic and workflow structure;
4. patient reclassification followed by question-specific effect drift.

The figure workflow therefore changed the manuscript materially: the visual
argument now leads with the positive informatics contribution—an evaluated
provenance audit—rather than presenting a defensive catalogue of data
limitations.
