# UniCom

UniCom is a standalone Frappe app for coordinating issues and their next actions. An issue has one accountable owner; participants and follow-up assignees are separate. A communication may mention users, granting them continuing access to the issue history. Mentions, participants, and assignees grant access; creator and owner also have access. Every active issue needs a next action and date, and resolving requires a resolution note. Overdue is calculated against the site date.

Install on a bench with Frappe v16: install the Python app in the bench environment, build the frontend with `cd frontend && npm ci && npm run build`, add/install the app on the target site using normal bench commands, then rebuild/link bench assets and restart services. Open `/unicom`. The build copies the generated HTML into the Frappe website route; regenerate it whenever frontend assets change. Email and WhatsApp are manual timeline channels; no integrations are included.

All issue writes go through `unicom.api`; generic issue saves and deletion are blocked by the controller. The app adds query and document permission hooks and a File permission hook for private attachments. File access depends on issue access, including after a participant is removed. Frappe administrators are trusted and can bypass standard permissions. The timeline is stored as a child table and ordinary users have no direct write permission.

Focused local tests (with a Frappe environment on PYTHONPATH): `python -m unittest discover -s tests -v`. These are unit tests, not installed-site integration tests. Before release verify list, direct document API, child rows, private file downloads (including removal), mentions, concurrent updates, and the full UI with separate users on a test site.
