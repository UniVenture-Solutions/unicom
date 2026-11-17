# UniCom

UniCom is a standalone Frappe app for coordinating issues and their next actions. An issue has one accountable owner; participants and follow-up assignees are separate. A communication may mention users, granting them continuing access to the issue history. Mentions, participants, and assignees grant access; creator and owner also have access. Next actions and dates are optional; resolving requires a resolution note. Overdue is calculated against the site date.

Install on a bench with Frappe v16: install the Python app in the bench environment, build the frontend with `cd frontend && npm ci && npm run build`, add/install the app on the target site using normal bench commands, then rebuild/link bench assets and restart services. Open `/unicom`. The build copies the generated HTML into the Frappe website route; regenerate it whenever frontend assets change. Email and WhatsApp are manual timeline channels; no integrations are included.

All issue writes go through `unicom.api`; generic issue saves and deletion are blocked by the controller. The app adds query and document permission hooks and keeps attachment bytes outside the served file directory. Every attachment download checks current issue access, including after a participant is removed. Include the site private/unicom directory in backups. Frappe administrators are trusted and can bypass standard permissions. The timeline is stored as a child table and ordinary users have no direct write permission.

Focused local tests (with a Frappe environment on PYTHONPATH): `python -m unittest discover -s tests -v`. These are unit tests, not installed-site integration tests. Before release verify list, direct document API, child rows, private file downloads (including removal), mentions, concurrent updates, and the full UI with separate users on a test site.

If the site proxy does not serve `/assets`, build with `UNICOM_ASSET_BASE=/files/unicom/frontend/ npm run build` from `frontend`, then run `node scripts/publish-site-assets.mjs /absolute/path/to/site` from `frontend`. This copies the compiled public JS and CSS under that site's `/files/unicom/frontend/assets/`; retain the generated website HTML from the same build. Run the helper again after each frontend build. The default build continues to use bench `/assets`.

Issues have an immutable public `ISU-####` ID, allocated from the `ISU-` naming series; the original internal name remains the route and link identifier. The post-model-sync patch backfills existing issues in creation/name order and advances the series beyond existing valid IDs. Run the migration in maintenance mode after a backup. The patch stops on invalid, noncanonical, or duplicate existing IDs; investigate conflicts rather than resetting the series. Verify new allocations and existing links on the site after migration.

### Desk issue panel

Desk loads a UniCom launcher from the app's standard `/assets/unicom/` files. It lists only issues returned by the existing permission-filtered API and links to the UniCom app. The panel supports search, views, refresh and incremental loading; it does not post messages.

The standard Desktop Icon record opens `/unicom`. On a site where UniCom was installed before this record was added, import only `unicom/desktop_icon/unicom.json` and clear the affected Desk boot/icon caches as part of deployment. Check for an existing icon with that name before importing. Frappe's saved per-user desktop layouts may need the user to add the icon; do not overwrite those layouts.

A source document can have one active issue at a time. Users who can read the source but cannot access its issue see only that an active issue exists. Resolving the issue permits a new one; reopening is rejected while another active issue exists.
