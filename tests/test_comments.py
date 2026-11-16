import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from unicom import api


class FakeDoc(SimpleNamespace):
    def append(self, field, value):
        getattr(self, field).append(SimpleNamespace(**value))

    def save(self, **kwargs):
        self.saved = True


class CommentTests(unittest.TestCase):
    def setUp(self):
        self.doc = FakeDoc(name='issue', owner='creator', accountable_owner='owner', title='Issue', description='',
                           status='Open', next_action='Call back', next_action_date='2026-11-20', resolution_note='',
                           access=[], timeline=[], flags=SimpleNamespace(), saved=False)
        self.session = SimpleNamespace(user='owner')
        self.db = SimpleNamespace(sql=lambda *args: None, exists=lambda doctype, filters: filters['name'] in {'owner', 'mentioned'})
        self.patches = [patch.object(frappe, 'session', self.session), patch.object(frappe, 'db', self.db),
                        patch.object(frappe, 'get_doc', return_value=self.doc),
                        patch.object(frappe, 'throw', side_effect=self.throw),
                        patch.object(api, '_output', side_effect=lambda doc: doc),
                        patch.object(api, 'now_datetime', return_value='2026-11-16 12:00:00')]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    @staticmethod
    def throw(message, exception=None):
        raise (exception or ValueError)(message)

    def test_comment_retains_action_and_history_and_sanitizes(self):
        old = SimpleNamespace(kind='Created')
        self.doc.timeline.append(old)
        before = (self.doc.status, self.doc.next_action, self.doc.next_action_date)
        api.add_comment('issue', '<p>Update <script>alert(1)</script><strong>done</strong></p>')
        event = self.doc.timeline[-1]
        self.assertEqual(event.kind, 'Comment')
        self.assertEqual(event.actor, 'owner')
        self.assertIn('<strong>done</strong>', event.body)
        self.assertNotIn('<script', event.body)
        self.assertIs(self.doc.timeline[0], old)
        self.assertEqual(before, (self.doc.status, self.doc.next_action, self.doc.next_action_date))
        self.assertTrue(self.doc.saved)

    def test_outsider_cannot_add_comment(self):
        self.session.user = 'outsider'
        with self.assertRaises(frappe.PermissionError): api.add_comment('issue', '<p>Hello</p>')
        self.assertFalse(self.doc.saved)
        self.assertEqual(self.doc.timeline, [])

    def test_empty_and_empty_rich_text_are_rejected(self):
        for body in ('', '  ', '<p><br></p>', '<p>&nbsp;\u200b</p>'):
            with self.subTest(body=body), self.assertRaises(ValueError): api.add_comment('issue', body)
        self.assertFalse(self.doc.saved)

    def test_mentions_grant_durable_access_and_validate_enabled_users(self):
        body = '<p>Hello <span data-type="mention" data-id="mentioned">@Mentioned</span></p>'
        api.add_comment('issue', body)
        self.assertTrue(api.issue_permission(self.doc, user='mentioned', ptype='read'))
        api._set_users(self.doc, 'Participant', [])
        self.assertEqual([(r.user, r.reason) for r in self.doc.access], [('mentioned', 'Mention')])
        before = len(self.doc.timeline)
        with self.assertRaises(ValueError): api.add_comment('issue', '<p><span data-type="mention" data-id="disabled">@Disabled</span></p>')
        self.assertEqual(before, len(self.doc.timeline))

    def test_resolved_comment_preserves_resolution(self):
        self.doc.status, self.doc.resolution_note = 'Resolved', 'Done'
        self.doc.next_action, self.doc.next_action_date = '', None
        api.add_comment('issue', '<p>Follow-up discussion</p>')
        self.assertEqual((self.doc.status, self.doc.resolution_note, self.doc.next_action, self.doc.next_action_date), ('Resolved', 'Done', '', None))
        self.assertEqual(self.doc.timeline[-1].kind, 'Comment')

    def test_active_issue_still_requires_action(self):
        self.doc.next_action = ''
        with self.assertRaises(ValueError): api.add_comment('issue', '<p>Discussion</p>')
        self.assertFalse(self.doc.saved)


if __name__ == '__main__': unittest.main()
