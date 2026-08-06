# JBI figure redesign package

## Deliverables

- `final_figures/JBI_Figure1` through `JBI_Figure5` in SVG, PDF, PNG, and 300-dpi LZW TIFF.
- Every multi-panel figure is also exported as separate SVG and PDF panels under `final_figures/panels/`.
- `template/JBI_Style_Template` in SVG, PDF, PNG, and TIFF, with a separate editable panel export.
- `JBI_STYLE_GUIDE.md` and `references/JBI_REFERENCE_MATRIX.md` document the synthesized design language and the recent JBI figures inspected.
- `data/` contains the committed aggregate inputs copied into figure-facing CSV or JSON artifacts.
- `qc/` contains structural SVG/PDF checks and later Illustrator-open checks.
- `FIGURE_LEGENDS_AND_ALT_TEXT.md` contains updated legends and accessibility text.

## Rebuild

From the repository root:

    python scripts/70_make_jbi_redesigned_figures.py

The script reads only committed aggregate outputs. It does not rerun scientific models or access row-level medication records.

## Submission boundary

Only files under `final_figures/` are candidate manuscript artwork. The template, style guide, references, data extracts, and QC records are documentation and should not be uploaded as article figures.
