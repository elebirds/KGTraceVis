# Fix Analysis Visual Evidence Overflow

## Goal

Fix Analysis detail usability regressions reported by the user: long evidence/artifact text must not overflow cards, and the visual evidence panel must not label a four-panel MVTec visualization as the original source image.

## Requirements

- Constrain/wrap Evidence Summary and Artifacts text inside cards.
- Preserve readable long local paths with truncation or wrapping.
- Detect MVTec visualizer/composite images and label them accurately instead of showing them as source image.
- Prefer a true raw image path when available; otherwise mark the source preview as generated visualization.
- Verify the reported run pages in the browser.

## Acceptance Criteria

- [x] `/analysis/run_20260513T103348Z_6e236690_mvtec_records` no longer has text overflow in Model Evidence.
- [x] `/analysis/run_20260513T102509Z_108b509d_mvtec_records` no longer mislabels a four-panel visualization as source image.
- [x] Existing visual evidence and case selector tests pass.
- [x] Frontend build passes.

## Completion Notes

- Added visual-evidence normalization so persisted MVTec model visualization panels are labeled as generated panels instead of raw source images.
- Added long-text wrapping for Evidence Summary, Visual Evidence metadata, and Artifacts list values.
- Verified both reported Analysis URLs in the in-app browser.
