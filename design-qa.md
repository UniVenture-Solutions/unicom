# UniCom CRM fidelity QA

Source visual truth:
- Sidebar: `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-d6859d65-6373-4fb5-9247-96edb18c1b55.png` (562×864).
- Breadcrumbs: `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-a8d986bc-d5f8-4258-a229-56d28b641d85.png` (2144×68).
- Right pane: `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-c4e1e71c-03ad-4d57-8963-84268601d9cf.png` (790×1732).

Implementation: development site issue `5db7ktud6h`, public ID `ISU-0001`, authenticated Administrator, light theme. Full-context capture `/tmp/unicom-crm-exact/detail-final.png`, list capture `list-after.png`, focused combined comparison `focused-comparison-final.png`. The three provided references are focused regions, with different CRM content. They were viewed together with corresponding implementation regions; the complete implementation was also inspected for context. Close-up references were normalized by inferred 2.2× density (528px sidebar / 240 CSS px); breadcrumb reference by 1.1×. No typography conclusions were drawn from browser zoom alone. Default implementation viewport measured 1705×1185 CSS px, screenshot 1704×1185; subpixel rounding accounts for the width difference.

## Findings and comparison history

1. Initial mismatch: generic Tailwind gray palette, 16px navigation, 4px corners, and declared font without a bundled face. Fixed with installed Frappe UI preset and its Inter variable font. Browser computes navigation 14px/420, inactive #525252, active #171717, background #f8f8f8 and radius 8px. Font asset returns HTTP 200. Breadcrumb parents are 16px/400/#7c7c7c, current title 16px/500/#171717; list icon and separators match the reference hierarchy.
2. First rendered comparison found P2 value alignment drift: equal-width detail columns placed values approximately 160px after labels. Changed to 110px labels plus 12px gap, matching the source's approximately 123px offset. Avatar now uses the issue ID instead of a leading punctuation character from the demonstration title.
3. The revised column width exposed P2 label wrapping. Added single-line truncation and full-text title attributes. Final rendered verification is recorded below.

Typography, spacing, colors, assets, and content were checked. Sidebar rows use the source 28px height/4px gap and 240px rail; white selected row has border/shadow. The right pane uses a 350px rail, ID header, 48px avatar, 20px summary, section borders, aligned gray labels and dark values. Actual UniCom fields, longer issue title, available actions, and existing FeatherIcon glyphs are intentional content differences; CRM-specific entities and unsupported actions were not copied. No raster assets were required. Inter is bundled rather than fetched from a third party.

## Verification

- Sidebar account menu and collapse/expand remain functional. Keyboard Enter on List returns to the list. All Accessible Issues + Stock search + Waiting filter were retained through opening an issue and returning through breadcrumbs.
- Details collapses/expands and its edit action opens the existing edit dialog; dismissed without saving. Attachments remain private and reachable. Existing comments and communication replies remain present.
- At measured 1549×364 CSS px, right pane stays below the 48px navbar; scrolling exposes Add private file inside the viewport. At 636×909 CSS px, the sidebar becomes top navigation, breadcrumbs adapt, Create remains reachable, and document scroll width equals viewport width. Viewport overrides were restored.
- Browser console reported no warnings/errors. Focused build and mounted UI checks passed. Independent scoped reviews passed.
- Pre-change database backup was created. Initial migration stopped before schema changes because both patch section headers were required; reviewed correction passed the actual Frappe parser and migration succeeded. Existing issue became ISU-0001 without renaming or changing its modified timestamp.
- Eleven real-database checks passed for unique sequential numbering, immutability, >9999 expansion, repeated backfill idempotence, old-name API compatibility, and two-connection allocation serialization/rollback. Narrow access/private-attachment checks passed for owner, outsider, and Guest. Test transactions rolled back; no test records remained or IDs consumed (series current=1).
- Later visual revisions changed frontend only; successful exact-backend evidence was reused. Seven compiled assets including Inter font returned HTTP 200. No additional schema migration was run for visual-only fixes.

Final deployed verification on `2dc4daa25b827b370cf6864d09ecf51a6162f3f8` confirms every detail label remains one line (16.09px), uses ellipsis, and retains its full title. The updated combined reference/implementation image was inspected after these fixes; no actionable P0/P1/P2 differences remain. Attachments collapse and reopen correctly.

Final result: passed
