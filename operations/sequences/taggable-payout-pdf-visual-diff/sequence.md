# Sequence: taggable-payout-pdf-visual-diff

Verify that the **operator payout PDF** rendered by `taggable-api` matches the **source template PDF**
element-by-element — a pixel-level diff whose differing regions are ranked by area, plus a structural
diff of every text run (font / size / colour / position), separators, and fills — so template
regressions are caught **objectively** instead of by eye. Promoted from discovery
`2026-07-16-taggable-payout-pdf-visual-diff`.

Automation: **`taggable-api:scripts/pdf_visual_diff.py`** (render a live PDF first with
**`taggable-api:scripts/verify-payout-report.sh`**).

## Why this sequence exists (the traps it encodes)
- The payout PDF (`PayoutReportPdfWriter.cs`) must match a hand-designed source template (DM Sans + PT
  Mono, exact colours/sizes/boxes/logo). Eyeballing side-by-side renders repeatedly missed real drift
  (font fallback, logo size, badge shape, spacing). This tool makes every delta measurable.
- **Fonts fell back to Lato on the deployed Windows server** even though they rendered on macOS — always
  confirm the LIVE PDF embeds DM Sans, not just a local render.

## Preconditions
- Python venv with the deps, and poppler's `pdftoppm` on PATH:
  ```bash
  python3 -m venv .venv && .venv/bin/pip install numpy Pillow pdfplumber
  # brew install poppler   # provides pdftoppm
  ```
- The **source template PDF** on disk (the design to match), e.g.
  `~/Downloads/6.16.26-6.30.26 - Grand Canyon Resort - Payout Report.pdf`.
- To render a LIVE generated PDF: `~/.taggable-verify.env` filled (see `taggable-api-authed-endpoint-verify`)
  and the change deployed (`taggable-api-deploy`).

## Steps
1. **Render the generated PDF** — live, real data (or render locally from a synthetic `PayoutReportModel`):
   ```bash
   OUT_DIR=<workdir> bash scripts/verify-payout-report.sh "Grand Canyon Resort" 2026-06-16 2026-06-30
   # -> <workdir>/payout-live.pdf ; expect: pdf HTTP 200, valid %PDF
   pdffonts <workdir>/payout-live.pdf   # MUST show DMSans-* + PTMono-Regular, NOT Lato
   ```
2. **Diff against the source template**:
   ```bash
   .venv/bin/python scripts/pdf_visual_diff.py \
     "<source-template>.pdf" <workdir>/payout-live.pdf --out <workdir>/pdfdiff_out
   ```
   Prints, per page: ranked pixel-diff regions (bbox in pt, %-of-page, and the source/generated text
   under each) + structural deltas (Δx/Δy/Δsize/font/colour per matched run, H-LINES, FILLED RECTS).
   Writes `side-by-side-p*.png` and `pixeldiff-p*.png` (differing pixels tinted red).
3. **Separate template drift from intended data differences.** Template drift = any font/colour/size
   delta, wrong logo size, or a large positional shift → fix in `taggable-api` `PayoutReportPdfWriter.cs`,
   re-render, re-diff. Data differences (the sample's invented refund, a legal-name subtitle the schema
   lacks, different money values) are NOT template bugs and will always show in the pixel diff.

## Verification / pass signal
- `pdf_visual_diff.py` reports **ZERO font / colour / size deltas** on both pages.
- Positional deltas are small (`<~8pt`) — expected in flow layout.
- The ranked pixel-diff regions are only the **intended data** differences (refund / legal-name / values).
- The LIVE PDF embeds **DM Sans (all weights) + PT Mono** — no Lato.

## Failure handling / known traps
- `pdftoppm: command not found` → `brew install poppler`.
- `ModuleNotFoundError: numpy/PIL/pdfplumber` → use the `.venv` python, not system python.
- Tool prints `!! PAGE COUNT DIFFERS` → the template overflowed a page (a real layout bug, not the tool).
- Whole-page red ghosting in `pixeldiff-p*.png` → a **global vertical offset**; adjust page margins /
  section spacing, not individual elements.
- Live fonts show **Lato** instead of DM Sans → the bundled fonts did not resolve on the Windows deploy
  target. Register them with QuestPDF `FontManager.RegisterFontWithCustomName` (one single-weight family
  per weight — do not rely on the fonts' internal names or on `.Bold()` weight-matching).

## Notes
- Secret discipline: `verify-payout-report.sh` never prints the token or credentials.
- Composes with `taggable-api-authed-endpoint-verify` (login/verify pattern) and `taggable-api-deploy`.
