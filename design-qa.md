# Assignment picker design QA

Source visual truth: user CRM screenshots in `/var/folders/nq/67sqxn453yq20sxjks5fc3rm0000gn/T/`, names `codex-clipboard-9ee4145b-668a-4fe0-830b-7c2f3845e6b9.png`, `codex-clipboard-58e15a7e-d3c3-4a61-a460-b5c6d0f8a83c.png`, and `codex-clipboard-0da44d6f-82ab-47e5-8153-b841530f76c2.png`.

Implementation: `/tmp/unicom-crm-assignment/single.png` and `search.png`, deployed a38854d.
Viewport: 1386 × 1077 CSS pixels. Capture: 1386 × 1077 pixels, browser devicePixelRatio 2.2. Source images are zoomed/cropped; normalize by reference text size (approximately 32px versus 14px UI) rather than treating crop width as viewport width. Different participant names are intentional live data.

Full view: implementation captures include navbar, issue and open picker. Focused comparison: `/tmp/unicom-crm-assignment/comparison-initial.png`, reference and implementation together.

## Findings
- P2: selected-chip field shrinks around the chip instead of spanning the popup. Fix nested popover width and field minimum height.
- P2: popup width differs from normalized reference; match approximately 470 CSS px, capped to viewport.
- P2: search rows display email addresses and truncate rather than showing reference-style avatar/name rows. Keep emails in tooltips if needed.

## Fidelity surfaces
- Typography: existing Inter and Frappe UI; reference labels require muted normal-weight text.
- Spacing/layout: corrections above required; rounded panel/chips and bottom self switch are present.
- Colors: neutral field, white chips, neutral avatars follow reference palette.
- Image fidelity: actual user profiles through Frappe Avatar; initials only when no uploaded image exists.
- Copy/content: Assign To, Assign To Me, Search and Clear match intended controls; live names differ intentionally.

## Interactions
Browser verified one selected participant displays navbar name; picker shows avatar/name chip and switch; clicking chip field opens nested searchable avatar menu and Clear. Mounted tests cover zero/multiple navbar states, autosave add/remove/self/clear, failure retry and rapid serialized changes. No live participant changes were made during QA.

Initial comparison result: blocked

## Corrected comparison — 9d9bb47
Implementation screenshots: `/tmp/unicom-crm-assignment/final-single.png` and `/tmp/unicom-crm-assignment/final-search.png`. Viewport and capture: 1280 × 720 CSS/output pixels; devicePixelRatio 2. Screenshot tooling returns CSS-resolution output. Reference single-selection crop 1040 × 300 was normalized to 470 × 136 using typography; reference search crop 1037 × 651 normalized to 470 × 295. Different live names and directory lengths are intentional.

Combined focused evidence: `/tmp/unicom-crm-assignment/comparison-final.png` and `/tmp/unicom-crm-assignment/comparison-search-final.png`. Full-view screenshots above include navbar and surrounding issue context. Prior P2 findings are corrected: popup now 470px, selected field spans 444px of inner content and measures 56px high, search shows avatar/name with longer directory in bounded scrolling. These were compared together with normalized source images, not from memory.

All required surfaces checked: existing Inter typography and normal label hierarchy; 12px padding with rounded panel/chips and aligned switch; white/gray neutral palette; Frappe Avatar uses uploaded profiles when available and initials otherwise; expected Assign To / Assign To Me / Search / Clear copy. Small P3 differences remain in switch-label tone and nested menu height for the larger live directory. These do not block use; no actionable P0/P1/P2 remains.

Browser checks: one participant displays name and avatar; chip field opens nested menu; typing Maria filters it; no Apply/Cancel; console warning/error log empty. Mounted actual-component checks cover zero/multiple navbar states, uploaded photo, chip add/remove, self switch, Clear, serialized/coalesced autosave, failure preservation/retry and owner independence. Live QA did not alter participant grants.

Implementation checklist: prior width/search corrections complete; functional and visual checks complete. No new assets or dependencies required; existing user images and Frappe UI controls retained.

final result: passed
