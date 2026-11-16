# Shell and issue list design QA

Reference: `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-d351ae23-695f-4a1f-8138-6ff18f13cf5b.png` (user-supplied Frappe CRM screenshot).

The revision targets the pale full-height sidebar with account menu, icon navigation, help and collapse controls; compact breadcrumb bar and create action; full-width list, compact filters and bottom pagination with functional 20/50/100 page sizes. The detail view keeps its existing right-side issue details and timeline.

Intentional differences: UniCom branding, issue navigation and fields, and actual site records are retained. CRM-specific controls and features without UniCom functionality are omitted.

Status: **Passed** on deployed code `182a07c66d8ded4619fdb3c03f446f5d1a0d19f1`, 2026-11-16.

Compared the supplied 2057×1264 screenshot with the deployed 1704×1185 list, both together and at full size. Reference browser chrome (48px) and bottom black padding were excluded for the comparison; images were fitted to equal-width panels without stretching. Different viewport heights and screenshot density account for the remaining proportional differences. The deployed sidebar measures 248 CSS px (64px collapsed), with a 48px navbar. Pale sidebar, selected navigation border, compact gray filters and table header, white workspace, restrained typography, create action, and pinned footer follow the reference. UniCom's neutral message icon and smaller set of working controls are intentional.

Browser checks passed: actual Administrator account dropdown; collapse/expand; My Issues and Overdue navigation; status filter returning zero resolved records then restoring the issue; 20→50→20 page-size selection; list row opening detail; Reply opening its named editor with focus. No records were added or modified. Exact-tree mounted checks cover API page length and reset behavior. Existing timeline and right-side metadata remain intact.

At a measured 1549×364 CSS viewport, the metadata sidebar stays below the navbar, scrolls independently, and exposes Add private file after scrolling (button bottom 340px within the 364px viewport). At 774×909 CSS px, detail content stacks and the list table scrolls inside its own region; page-level scroll width equals viewport width. Pagination remains reachable. Viewport overrides were reset afterward.

Evidence: `/tmp/unicom-crm-layout/reference-comparison.png`, `list-after.png`, `detail-after.png`, `short-sidebar.png`, `narrow-detail.png`, and `narrow-list.png`. No remaining blocking layout findings. Frontend fallback build and scoped independent review passed; release verified all six compiled assets return HTTP 200. Backend tests and migrations were skipped because no backend or schema changed.

Further references: `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-d6859d65-6373-4fb5-9247-96edb18c1b55.png` (sidebar), `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-a8d986bc-d5f8-4258-a229-56d28b641d85.png` (breadcrumbs), and `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/codex-clipboard-c4e1e71c-03ad-4d57-8963-84268601d9cf.png` (detail sidebar). Compare font, tokens, selected navigation row, breadcrumb hierarchy, and issue details at desktop and mobile sizes. UniCom issue data and its existing working actions are intentional differences.
