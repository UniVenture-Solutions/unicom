# Approved UniCom transfer

This temporary importer accepts only the separately supplied, approved snapshot. It is restricted to the destination domain and the exact `Administrator` account. An ordinary account is not sufficient.

1. Use the destination site's Frappe Cloud **Administrator login**.
2. Open `https://univenturetraders.com/unicom-import`.
3. Select the approved JSON snapshot from your device and choose **Preview transfer**.
4. Review the issue IDs, counts, destination identities, and plan digest. Resolve any account or compatibility blocker before continuing.
5. Choose **Import issues** to apply that exact preview. The preview expires after 15 minutes and belongs to the current login session.

The input is sent privately in the POST body, not saved as a public File. Existing or changed records are never overwritten. Historical replay does not create notifications or email. A private, mode-0600 prepared rollback archive is retained under the site's `private/backups` directory; it includes the mapped rows, prior destination state, and original issue-series state.

If the connection fails while applying, do not assume nothing committed. Preview again: an exact completed transfer is recognized without creating duplicates. If existing records differ, stop for reconciliation.

After the transfer is verified, remove this temporary importer through the normal reviewed release process. Never add the snapshot, account data, or credentials to Git.
