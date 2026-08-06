# LibreOffice renderer environment failure

On 2026-08-05 the bundled `render_docx.py` initially failed because LibreOffice was not on `PATH`. After adding the installed LibreOffice program directory, the first conversion remained inactive for more than 100 seconds and produced no PDF or PNG page. The parent Python process and its two LibreOffice child processes were audited and safely terminated.

This is recorded as an environment-specific rendering implementation failure, not a manuscript, statistical, or analytical failure. Visual QA was rerouted to the installed Microsoft Word COM renderer followed by the bundled Poppler `pdftoppm` wrapper. The DOCX sources themselves were unchanged by the fallback.
