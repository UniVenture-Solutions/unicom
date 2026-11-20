import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from unicom import api, permissions


class FakeDoc(SimpleNamespace):
    def update(self, values):
        self.__dict__.update(values)
    def set(self, key, value):
        setattr(self, key, value)
    def append(self, field, value):
        getattr(self, field).append(SimpleNamespace(**value))
    def insert(self, **kwargs):
        self.saved = True
    def save(self, **kwargs):
        self.saved = True


class DescriptionMentionTests(unittest.TestCase):
    def setUp(self):
        self.doc = FakeDoc(name='issue', owner='owner', title='Issue', description='', accountable_owner='owner',
                           coordination_user=None, status='Open', next_action='', next_action_date=None,
                           resolution_note='', access=[], timeline=[], flags=SimpleNamespace(), saved=False)
        self.session = SimpleNamespace(user='owner')
        self.db = SimpleNamespace(exists=lambda doctype, filters: filters['name'] in {'owner', 'mentioned'})
        patches = [patch.object(frappe, 'get_roles', side_effect=lambda user=None: ['Management'] if (user or frappe.session.user) in {'owner','mentioned'} else []), patch.object(frappe, 'session', self.session), patch.object(frappe, 'db', self.db),
                   patch.object(frappe, 'new_doc', return_value=self.doc), patch.object(frappe, 'get_doc', return_value=self.doc),
                   patch.object(frappe, 'throw', side_effect=self.throw),
                   patch.object(api, '_output', side_effect=lambda doc: doc), patch.object(api, '_notify_mentions'),
                   patch.object(api, 'now_datetime', return_value='2026-11-18 16:00:00')]
        for item in patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

    @staticmethod
    def throw(message, exception=None):
        raise (exception or ValueError)(message)

    def test_create_retains_formatted_mentions_and_grants_once(self):
        span = '<span data-type="mention" data-id="mentioned">@Mentioned</span>'
        api.create_issue('Issue', 'owner', description='<p><strong>Hello</strong> ' + span + span + '</p>')
        self.assertIn('<strong>Hello</strong>', self.doc.description)
        self.assertIn('data-type="mention"', self.doc.description)
        self.assertEqual([(row.user, row.reason) for row in self.doc.access], [('mentioned', 'Mention'), ('mentioned', 'Participant')])
        self.assertTrue(permissions.issue_permission(self.doc, 'mentioned', 'read'))
        self.assertTrue(self.doc.saved)

    def test_update_and_tag_removal_preserve_durable_access(self):
        api.update_issue('issue', {'description': '<p><span data-type="mention" data-id="mentioned">@Mentioned</span></p>'})
        api.update_issue('issue', {'description': '<p>Tag removed</p>', 'participants': []})
        self.assertEqual([(row.user, row.reason) for row in self.doc.access], [('mentioned', 'Mention')])
        self.assertTrue(permissions.issue_permission(self.doc, 'mentioned', 'read'))
        self.assertEqual(self.doc.accountable_owner, 'owner')
        self.assertIsNone(self.doc.coordination_user)

    def test_disabled_missing_and_guest_mentions_cannot_save(self):
        for user in ('disabled', 'missing', 'Guest'):
            with self.subTest(user=user), self.assertRaises(ValueError):
                api.update_issue('issue', {'description': '<p><span data-type="mention" data-id="' + user + '">@User</span></p>'})
            self.assertFalse(self.doc.saved)
            self.assertEqual(self.doc.access, [])
            self.assertEqual(self.doc.timeline, [])

    def test_plain_text_foreign_references_and_empty_nodes_do_not_grant(self):
        body = '<p>@mentioned <span data-type="reference" data-id="mentioned">@Foreign</span>'
        body += '<span data-type="mention" data-id="mentioned"> </span>'
        body += '<div data-type="mention" data-id="mentioned">not a mention node</div></p>'
        api.create_issue('Issue', 'owner', description=body)
        self.assertEqual(self.doc.access, [])

    def test_grants_are_derived_only_from_sanitized_retained_description(self):
        raw = '<p><span data-type="mention" data-id="disabled">@Removed</span></p>'
        with patch.object(api, '_rich_html', return_value='<p>Retained safe content</p>'):
            api.create_issue('Issue', 'owner', description=raw)
        self.assertEqual(self.doc.access, [])
        self.assertEqual(self.doc.description, '<p>Retained safe content</p>')

    def test_outsider_cannot_edit_description_or_grant_access(self):
        self.session.user = 'outsider'
        with self.assertRaises(frappe.PermissionError):
            api.update_issue('issue', {'description': '<p><span data-type="mention" data-id="mentioned">@Mentioned</span></p>'})
        self.assertFalse(self.doc.saved)
        self.assertEqual(self.doc.access, [])

    def test_unrelated_edit_does_not_revalidate_legacy_description(self):
        self.doc.description = '<p><span data-type="reference" data-id="disabled">Historical source reference</span></p>'
        api.update_issue('issue', {'description': self.doc.description, 'title': 'Changed'})
        self.assertTrue(self.doc.saved)
        self.assertEqual(self.doc.access, [])


if __name__ == '__main__':
    unittest.main()
