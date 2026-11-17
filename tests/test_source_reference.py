import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from unicom import api
from unicom.unicom.doctype.unicom_issue.unicom_issue import UniComIssue


class SourceReferenceTests(unittest.TestCase):
    def setUp(self):
        self.source = SimpleNamespace(name='DOC-1')
        self.meta = SimpleNamespace(istable=0, issingle=0)
        self.allowed = True
        self.existing = True
        patches = [
            patch.object(frappe, 'db', SimpleNamespace(exists=lambda doctype, name: doctype == 'DocType' and name in ('Invoice', 'Child', 'Single', 'UniCom Issue') or doctype == 'Invoice' and name == 'DOC-1' and self.existing)),
            patch.object(frappe, 'get_meta', side_effect=lambda dt: SimpleNamespace(istable=dt == 'Child', issingle=dt == 'Single')),
            patch.object(frappe, 'get_doc', return_value=self.source),
            patch.object(frappe, 'has_permission', side_effect=lambda *a, **k: self.allowed),
            patch.object(frappe, 'throw', side_effect=lambda message, exc=None: (_ for _ in ()).throw((exc or ValueError)(message))),
        ]
        for item in patches: item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

    def test_valid_pair_and_optional_pair(self):
        self.assertEqual(api._source_pair('Invoice', 'DOC-1'), ('Invoice', 'DOC-1'))
        self.assertEqual(api._source_pair(None, None), (None, None))

    def test_invalid_or_inaccessible_pair_rejected_without_disclosure(self):
        for doctype, name in [('Invoice', None), (None, 'DOC-1'), ('Invoice', ''), ('Unknown', 'DOC-1'), ('Invoice', 'missing'), ('Child', 'DOC-1'), ('Single', 'DOC-1'), ('UniCom Issue', 'DOC-1'), ([], 'DOC-1')]:
            with self.subTest(doctype=doctype, name=name), self.assertRaises(frappe.PermissionError):
                api._source_pair(doctype, name)
        self.allowed = False
        with self.assertRaises(frappe.PermissionError): api._source_pair('Invoice', 'DOC-1')

    def test_detail_redacts_on_revocation_or_deletion(self):
        doc = SimpleNamespace(owner='creator', accountable_owner='owner', coordination_user=None, status='Resolved', next_action_date=None, timeline=[], attachments=[], as_dict=lambda: {'reference_doctype':'Invoice','reference_name':'DOC-1'})
        with patch.object(frappe, 'get_all', return_value=[]):
            self.assertEqual(api._output(doc)['reference_name'], 'DOC-1')
            self.allowed = False
            denied = api._output(doc)
            self.assertNotIn('reference_doctype', denied)
            self.assertNotIn('reference_name', denied)
            self.allowed = True
            self.existing = False
            self.assertNotIn('reference_name', api._output(doc))

    def test_create_persists_verified_pair(self):
        doc = SimpleNamespace(update=lambda values: doc.__dict__.update(values), flags=SimpleNamespace(), insert=lambda **kwargs: None)
        with patch.object(api, '_user'), patch.object(api, '_lock_source') as lock, patch.object(api, '_ensure_no_active_source') as ensure, patch.object(frappe, 'new_doc', return_value=doc), patch.object(api, '_rich_html', return_value=''), patch.object(api, '_coordination_selection', return_value=None), patch.object(api, '_set_users'), patch.object(api, '_validate'), patch.object(api, '_event'), patch.object(api, '_output', side_effect=lambda value: value):
            result = api.create_issue('Title', 'owner', 'Call', '2026-11-20', reference_doctype='Invoice', reference_name='DOC-1')
        self.assertEqual((result.reference_doctype, result.reference_name), ('Invoice', 'DOC-1'))
        lock.assert_called_once_with('Invoice', 'DOC-1')
        ensure.assert_called_once_with('Invoice', 'DOC-1')

    def test_source_lookup_redacts_issue_identity_when_not_accessible(self):
        with patch.object(api, '_user', return_value='viewer'), patch.object(api, '_active_source_issue', return_value='hidden'), patch.object(frappe, 'get_doc', return_value=self.source), patch.object(api, 'issue_permission', return_value=False):
            self.assertEqual(api.source_issue('Invoice', 'DOC-1'), {'exists': True})
        with patch.object(api, '_user', return_value='viewer'), patch.object(api, '_active_source_issue', return_value='visible'), patch.object(frappe, 'get_doc', return_value=self.source), patch.object(api, 'issue_permission', return_value=True):
            self.assertEqual(api.source_issue('Invoice', 'DOC-1'), {'exists': True, 'name': 'visible'})
        self.allowed = False
        with patch.object(api, '_user', return_value='viewer'):
            with self.assertRaises(frappe.PermissionError): api.source_issue('Invoice', 'DOC-1')

    def test_source_and_active_issue_reads_are_locking_and_parameterized(self):
        queries = []
        db = SimpleNamespace(exists=lambda dt, name: True, sql=lambda query, args: queries.append((query, args)) or [('name',)])
        with patch.object(frappe, 'db', db):
            api._lock_source('Invoice', 'DOC-1')
            api._active_source_issue('Invoice', 'DOC-1', exclude='current', lock=True)
        self.assertTrue(all(query.endswith('FOR UPDATE') for query, args in queries))
        self.assertEqual(queries[0][1], ('DOC-1',))
        self.assertEqual(queries[1][1], ('Invoice', 'DOC-1', 'current'))

    def test_conflict_is_generic_and_uses_current_read(self):
        with patch.object(api, '_active_source_issue', return_value='hidden') as lookup:
            with self.assertRaises(ValueError) as error: api._ensure_no_active_source('Invoice', 'DOC-1', exclude='self')
        self.assertNotIn('hidden', str(error.exception))
        lookup.assert_called_once_with('Invoice', 'DOC-1', exclude='self', lock=True)

    def test_active_status_locks_source_before_issue(self):
        doc = SimpleNamespace(reference_doctype='Invoice', reference_name='DOC-1', status='Resolved')
        events = []
        def get_issue(name, lock=False):
            events.append('issue lock' if lock else 'issue read')
            return doc
        def lock_source(*args): events.append('source lock')
        def conflict(*args, **kwargs): events.append('conflict check'); raise ValueError('conflict')
        with patch.object(api, '_doc', side_effect=get_issue), patch.object(api, '_lock_source', side_effect=lock_source), patch.object(api, '_ensure_no_active_source', side_effect=conflict):
            with self.assertRaises(ValueError): api.update_issue('issue', {'status': 'Open'})
        self.assertEqual(events, ['issue read', 'source lock', 'issue lock', 'conflict check'])

    def test_source_lookup_without_pair_is_rejected(self):
        with patch.object(api, '_user'):
            with self.assertRaises(frappe.PermissionError): api.source_issue(None, None)

    def test_update_api_rejects_reference_fields(self):
        with patch.object(api, '_doc', return_value=SimpleNamespace()), patch.object(api, '_snapshot', return_value={}):
            with self.assertRaises(ValueError):
                api.update_issue('issue', {'reference_name':'other'})

    def test_controller_rejects_reference_changes(self):
        old = SimpleNamespace(issue_id='ISU-1', reference_doctype='Invoice', reference_name='DOC-1')
        doc = SimpleNamespace(flags=SimpleNamespace(unicom_api=True), issue_id='ISU-1', reference_doctype='Invoice', reference_name='OTHER', get_doc_before_save=lambda:old)
        with self.assertRaises(frappe.ValidationError): UniComIssue.validate(doc)

if __name__ == '__main__': unittest.main()
