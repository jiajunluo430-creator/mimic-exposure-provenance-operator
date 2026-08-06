# JBI figure redesign acceptance

## Outcome

PASS. Five redesigned main figures and one reusable style template are visually clean, structurally editable, and numerically unchanged from the prior figure-facing aggregate data.

## Numerical continuity

The seven figure-facing CSV/JSON files for Figures 2–5 are byte-identical to the prior JBI figure package by SHA-256:

- Figure2_native_parity.csv
- Figure2_ablation.csv
- Figure3_transport_summary.json
- Figure4_reporting_dimensions.csv
- Figure4_reported_dimension_distribution.csv
- Figure5_reclassification.csv
- Figure5_effects.csv

Figure 1 is conceptual and preserves the same source, identity, time, event-semantics, metadata, validation-state, and noncausal stress-test definitions.

## Structural vector QC

- All 5 assembled SVG files and the template contain live text and the required panel/axis/data/labels/legend/annotations semantic groups.
- Image elements: 0.
- Duplicate IDs: 0.
- Clip paths and duplicate clip paths: 0.
- Abnormal paths: 0.
- PDF image XObjects: 0.
- Type 3 fonts: absent.

## Illustrator open QC

All files passed direct Adobe Illustrator opening:

- Assembled Figures 1–5: TextFrames 66, 40, 55, 54, and 43; PlacedItems 0; RasterItems 0.
- Eleven separate main-figure panels: every file has TextFrames greater than 0; PlacedItems 0; RasterItems 0.
- Style template and its separate panel: TextFrames 28; PlacedItems 0; RasterItems 0.

## Rendered visual review

The 300-dpi previews rendered from the final vector PDFs were inspected at original resolution. One first-pass issue, a clipped Figure 4B title, was corrected by shortening the title without changing meaning. The second-pass render showed no clipping, overlap, illegible labels, or panel-order problems.

## Scientific boundary

This is a presentation-only redesign. The frozen medication classes, whitelists, exposure operators, time windows, analysis units, estimates, and eICU semantic-comparison boundary were not changed. The paired association estimates remain measurement stress tests and are not presented as causal drug effects.

