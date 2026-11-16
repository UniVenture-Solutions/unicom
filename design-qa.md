# Thread reply UI QA

Source: `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-1f66c0a5-b646-4fbe-a3dc-1f1ab278ee09.png` (512×116). Target is the compact participant-avatar/reply-count/latest-activity pattern, adapted to the established light Frappe styling. Unsupported Following behavior and the reference dark theme are intentionally omitted. Actual participant names, counts and dates come from the issue.

Implementation: authenticated issue ISU-0001, Call thread with two existing replies, at desktop and narrow widths. Initial captures: `/tmp/unicom-thread-summary/desktop.png` and `narrow-before.png`. Existing shared white backgrounds, avatar photos, root message and child replies are retained. User additionally requested Reply on every child, appending to the same root sequence.

## Findings / comparison history

[P1] First rendered candidate 2b4843d stacked its summary content within Frappe UI Button’s default label wrapper. Its fixed 28px height contained an 88px child, overlapping message text on desktop and mobile. Fix applied in 3f1d3f9: explicit flex wrapper for participant avatars/icon/count/chevron; place latest-reply timestamp beside the button in a wrapping action row. No horizontal divider should remain above replies; their section uses a vertical connector.

Functional browser checks already passed: two child Reply controls, child click opens and focuses the root composer named Reply in thread, and root section has 0px top border and approximately 2px left border. No records were modified. Mounted checks cover root-targeted posting and same-thread draft preservation.

## Final rendered verification

Code: `3f1d3f9e42e35035d8bfbfde0538cbfa96cb5d8a`. Full implementation captures: `/tmp/unicom-thread-summary/desktop-final.png` (composer open), `expanded-final.png` (thread open), and `narrow-final.png`. Combined source/implementation comparison: `/tmp/unicom-thread-summary/comparison.png`; focused crop: `summary-row.png`. The source is a focused component capture rather than a complete application viewport, so full-page source comparison is unavailable; the surrounding live application was inspected separately.

Desktop measured 1643×1185 CSS px; screenshot 1629×1176 px. Crop coordinates were normalized by those measured scale ratios. Reference 512×116 was retained at native dimensions in the combined input. Its avatar/count/latest-activity relationship was compared directly with the rendered summary. UniCom intentionally retains the light Frappe palette, Inter font, existing compact type scale and icons, actual participant count, and absolute site timestamp. The source dark skin, Following action, sample copy and relative-time wording are not part of this adaptation.

The repaired toggle is 28px high and its inner content is 27.36px high, fully contained. The timestamp is a sibling in the wrapping action row. At a measured 364px narrow CSS viewport, the summary button is 155.38px wide within a 210.60px action area; the row expands to 85.78px and places the timestamp below without overlap. The visible mobile capture confirms readable controls and reply text. Document scroll width did not exceed the viewport. Viewport overrides were reset.

The expanded section has 0px top border and approximately 2px left border, preserving a shared white container. Every child has a visible Reply action. Clicking both child entry points opened the same root composer; desktop focus was confirmed in its named textbox. Cancellation and expansion/collapse worked. Mounted checks prove the submitted reply_to remains the original root, the sequence remains flat, and a same-thread draft survives switching reply entry points. No issue records or comments were changed during browser checks.

Fonts, spacing, colors, assets and copy were checked: uploaded participant photos load with existing initials fallback; up to three distinct participants are shown; reply counts and latest time are derived from existing replies; native Frappe type and button styling remain consistent. No custom raster or icon assets were introduced. Browser console had no warnings/errors. Scoped independent review and frontend build passed; release checked all seven assets return HTTP 200. Backend tests and migrations were skipped because backend/schema were untouched.

No remaining actionable P0/P1/P2 findings.

Final result: passed
