# Sequence Discovery Log: taggable-payout-pdf-visual-diff

DiscoveryId: discovery-89094bbd-9afc-5495-bd36-e4f44ecdbe79
Status: discovery
CreatedAtUtc: 2026-07-16T11:11:21Z
RegisteredSequenceMatch: none

## Intended Outcome

Verify the operator payout PDF (rendered from taggable-api getPayoutReportPdf, or a local render) matches the source template PDF element-by-element — pixel-diff regions ranked by area plus a structural diff of every text run (font/size/color/position), separators and fills — so template regressions are caught objectively instead of by eye.

## Why This Looks Repeatable

Needed every time PayoutReportPdfWriter (fonts, colors, sizes, spacing, boxes, logo) changes, to prove the payout PDF still matches the Grand Canyon Resort source template and to locate any drift.

## Required Inputs, Auth, Or Environment




- Python venv with numpy, Pillow, pdfplumber; poppler's pdftoppm on PATH

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify-automation | /private/tmp/claude-501/-Users-kamenkamenov-taggable-api/cfc8b113-420c-4715-a9ec-c6f809d10fb8/scratchpad/.venv/bin/python /Users/kamenkamenov/taggable-api/scripts/pdf_visual_diff.py "/Users/kamenkamenov/Downloads/6.16.26-6.30.26 - Grand Canyon Resort - Payout Report.pdf" /private/tmp/claude-501/-Users-kamenkamenov-taggable-api/cfc8b113-420c-4715-a9ec-c6f809d10fb8/scratchpad/payout-render.pdf --out /private/tmp/claude-501/-Users-kamenkamenov-taggable-api/cfc8b113-420c-4715-a9ec-c6f809d10fb8/scratchpad/pdfdiff_out | exit 0; per-page ranked pixel regions + structural deltas printed; zero font/color/size deltas | The canonical proof command: renders (or reuses) the payout PDF and diffs it against the source template. |
| Separate template drift from intended data differences | # interpret the diff output | Data diffs (sample's refund -33.25 / Corporation legal name / different money) are NOT template bugs (live data has refunds=0, no legal-name field). Template drift = any font/color/size delta, logo size, or large positional shift. | Fix drift in taggable-api PayoutReportPdfWriter.cs, re-render, re-diff until only intended-data diffs remain. |
| Diff the generated PDF against the source template | .venv/bin/python scripts/pdf_visual_diff.py '<source-template>.pdf' <workdir>/payout-live.pdf --out <workdir>/pdfdiff_out | Per page: ranked pixel-diff regions (bbox pt, %page, text under each) + structural deltas (Δx/Δy/Δsize/font/color per matched run, H-LINES, FILLED RECTS); writes side-by-side-p*.png and pixeldiff-p*.png. | taggable-api:scripts/pdf_visual_diff.py — template PASS = ZERO font/color/size deltas; positional Δ small (<~8pt); ranked regions+heatmap surface biggest drift. |
| Render the generated payout PDF (live, real data) | OUT_DIR=<workdir> bash scripts/verify-payout-report.sh 'Grand Canyon Resort' 2026-06-16 2026-06-30 | pdf -> HTTP 200, valid %PDF at <workdir>/payout-live.pdf; fonts=DM Sans+PT Mono (not Lato) | taggable-api:scripts/verify-payout-report.sh — logs in via ~/.taggable-verify.env (never printed), resolves companyId by name, POSTs getPayoutReportPdf. Confirm fonts: pdffonts payout-live.pdf. |
| Set up the diff toolchain (once) | python3 -m venv .venv && .venv/bin/pip install numpy Pillow pdfplumber   # needs poppler pdftoppm on PATH | venv with numpy/Pillow/pdfplumber; pdftoppm available | pdf_visual_diff.py rasterizes via pdftoppm and analyses via numpy+Pillow+pdfplumber. |

## Failure Handling


pdftoppm not found -> brew install poppler. numpy/pdfplumber ImportError -> use the .venv python. Tool prints 'PAGE COUNT DIFFERS' -> the template overflowed (real bug, not the tool). Whole-page red ghosting in pixeldiff -> a global vertical offset (adjust page margins/section spacing). Live fonts show Lato instead of DM Sans -> fonts did not register on the Windows server; register via QuestPDF FontManager.RegisterFontWithCustomName with one family per weight.

## Verified Path


- 2026-07-16: diffed source template vs live getPayoutReportPdf (Grand Canyon Resort, companyId 79, Jun 16-30 2026). Result: ZERO font/color/size deltas both pages; logo 73.8x17.6pt vs source 73.8x17.3pt; live fonts = DM Sans (all weights)+PT Mono, no Lato; residual pixel diff is the intended data (refund/legal-name/values).

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
