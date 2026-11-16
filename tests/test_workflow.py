import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from unicom import api, permissions

class Doc(SimpleNamespace):
    def append(self, field, value):
        getattr(self, field).append(SimpleNamespace(**value))

class WorkflowTests(unittest.TestCase):
    def test_access_is_only_creator_owner_or_granted_user(self):
        doc = Doc(owner='creator', accountable_owner='owner', access=[Doc(user='participant')])
        for user in ('creator', 'owner', 'participant'):
            self.assertTrue(permissions.issue_permission(doc, user, 'read'))
        self.assertFalse(permissions.issue_permission(doc, 'outsider', 'read'))
        self.assertFalse(permissions.issue_permission(doc, 'participant', 'write'))

    def test_participant_removal_retains_mention_grant(self):
        doc = Doc(access=[Doc(user='person', reason='Participant'), Doc(user='person', reason='Mention')])
        with patch.object(api, '_users', return_value=[]):
            api._set_users(doc, 'Participant', [])
        self.assertEqual([(r.user, r.reason) for r in doc.access], [('person', 'Mention')])

    def test_active_requires_action_and_date_resolved_requires_note(self):
        doc = Doc(title='Issue', accountable_owner='owner', status='Open', next_action='', next_action_date=None, resolution_note='')
        def throw(message, *args): raise ValueError(message)
        with patch.object(api, '_users'), patch.object(frappe, 'throw', side_effect=throw):
            with self.assertRaises(ValueError): api._validate(doc)
            doc.next_action = 'Call'; doc.next_action_date = '2026-11-17'
            api._validate(doc)
            doc.status = 'Resolved'
            with self.assertRaises(ValueError): api._validate(doc)
            doc.resolution_note = 'Finished'; api._validate(doc)
            doc.status = 'Open'; doc.next_action = ''
            with self.assertRaises(ValueError): api._validate(doc)

    def test_revoked_uploader_cannot_download_using_old_url(self):
        issue = Doc(owner='creator', accountable_owner='owner', access=[], attachments=[Doc(name='file1', storage_key='a'*64, file_name='secret')])
        def throw(message, exception=None): raise PermissionError(message)
        with patch.object(api, '_user', return_value='former'), patch.object(frappe, 'session', Doc(user='former')), patch.object(frappe, 'get_doc', return_value=issue), patch.object(frappe, 'throw', side_effect=throw), patch('builtins.open') as opener:
            with self.assertRaises(PermissionError): api.download_attachment('issue1', 'file1')
            opener.assert_not_called()

    def test_attachment_storage_key_cannot_escape_private_directory(self):
        def throw(message, *args): raise ValueError(message)
        with patch.object(frappe, 'throw', side_effect=throw):
            with self.assertRaises(ValueError): api._attachment_path('../files/secret')

if __name__ == '__main__': unittest.main()
