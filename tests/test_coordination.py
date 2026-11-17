import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from unicom import api, permissions


class FakeDoc(SimpleNamespace):
    def update(self, values):
        for key, value in values.items(): setattr(self, key, value)
    def set(self, key, value): setattr(self, key, value)
    def append(self, field, value): getattr(self, field).append(SimpleNamespace(**value))
    def insert(self, **kwargs): self.saved = True
    def save(self, **kwargs): self.saved = True


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.doc = FakeDoc(name='issue', owner='creator', title='Issue', description='', accountable_owner='owner',
                           coordination_user=None, status='Open', next_action='Call', next_action_date='2026-11-20',
                           resolution_note='', access=[], timeline=[], flags=SimpleNamespace(), saved=False)
        self.db = SimpleNamespace(exists=lambda doctype, filters: filters['name'] in {'owner','coordinator','website'},
                                  get_value=lambda doctype, name, field: 'Website User' if name=='website' else 'System User')
        self.patches = [patch.object(frappe, 'db', self.db), patch.object(frappe, 'new_doc', return_value=self.doc),
                        patch.object(frappe, 'throw', side_effect=self.throw), patch.object(api, '_user', return_value='owner'),
                        patch.object(api, '_doc', return_value=self.doc), patch.object(api, '_output', side_effect=lambda x:x),
                        patch.object(api, 'now_datetime', return_value='2026-11-16 12:00:00')]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    @staticmethod
    def throw(message, exception=None): raise (exception or ValueError)(message)

    def test_create_optional_and_assigned_coordinator(self):
        api.create_issue('Issue','owner','Call','2026-11-20',coordination_user='coordinator')
        self.assertEqual(self.doc.coordination_user, 'coordinator')
        self.assertTrue(self.doc.saved)
        self.doc.saved = False
        api.create_issue('Issue','owner','Call','2026-11-20')
        self.assertIsNone(self.doc.coordination_user)

    def test_create_without_next_action_and_subsequent_updates(self):
        api.create_issue('Issue', 'owner')
        self.assertEqual(self.doc.next_action, '')
        self.assertIsNone(self.doc.next_action_date)
        api.update_issue('issue', {'title': 'Changed'})
        api.add_comment('issue', '<p>Discussion</p>')
        api.log_communication('issue', 'Call', '2026-11-16 12:00:00', '<p>Called</p>')
        api.update_issue('issue', {'status': 'In Progress'})
        with self.assertRaises(ValueError):
            api.update_issue('issue', {'status': 'Resolved'})

    def test_create_rejects_disabled_coordinator(self):
        with self.assertRaises(ValueError):
            api.create_issue('Issue', 'owner', 'Call', '2026-11-20', coordination_user='disabled')
        self.assertFalse(self.doc.saved)

    def test_update_clear_and_audit(self):
        api.update_issue('issue', {'coordination_user':'coordinator'})
        event = self.doc.timeline[-1]
        self.assertEqual(json.loads(event.changes)['coordination_user'], {'from':None,'to':'coordinator'})
        api.update_issue('issue', {'coordination_user':''})
        self.assertIsNone(self.doc.coordination_user)
        self.assertEqual(json.loads(self.doc.timeline[-1].changes)['coordination_user'], {'from':'coordinator','to':None})

    def test_reject_disabled_guest_website_and_invalid_type(self):
        for value in ('disabled', 'Guest', 'website', 123, 0, False, []):
            with self.subTest(value=value), self.assertRaises((ValueError, frappe.ValidationError)):
                api.update_issue('issue', {'coordination_user':value})
            self.assertFalse(self.doc.saved)
            self.doc.coordination_user = None

    def test_inactive_existing_coordinator_does_not_block_other_work(self):
        for inactive in ('disabled', 'website'):
            with self.subTest(inactive=inactive):
                self.doc.coordination_user = inactive
                api.update_issue('issue', {'title':'Changed', 'coordination_user':inactive})
                api.add_comment('issue', '<p>Discussion</p>')
                api.log_communication('issue', 'Call', '2026-11-16 12:00:00', '<p>Called</p>', next_action='Call again', next_action_date='2026-11-21')
                self.assertEqual(self.doc.coordination_user, inactive)
                self.assertEqual([event.kind for event in self.doc.timeline[-3:]], ['Updated','Comment','Communication'])
                with self.assertRaises(ValueError): api.update_issue('issue', {'coordination_user':'disabled' if inactive=='website' else 'website'})

    def test_create_rejects_falsey_nonstring(self):
        for value in (0, False, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                api.create_issue('Issue', 'owner', 'Call', '2026-11-20', coordination_user=value)

    def test_coordinator_alone_gets_no_access(self):
        api.update_issue('issue', {'coordination_user':'coordinator'})
        self.assertFalse(permissions.issue_permission(self.doc, user='coordinator', ptype='read'))
        self.assertTrue(permissions.issue_permission(self.doc, user='owner', ptype='read'))
        self.assertEqual(self.doc.access, [])

if __name__ == '__main__': unittest.main()
