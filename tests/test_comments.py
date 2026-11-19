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
        self.patches = [patch.object(frappe, 'get_roles', side_effect=lambda user=None: ['Management'] if (user or frappe.session.user) in {'owner','creator','mentioned','Administrator'} else []), patch.object(frappe, 'session', self.session), patch.object(frappe, 'db', self.db),
                        patch.object(frappe, 'get_doc', return_value=self.doc),
                        patch.object(frappe, 'throw', side_effect=self.throw),
                        patch.object(api, '_output', side_effect=lambda doc: doc), patch.object(api, '_notify_mentions'),
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

    def test_replies_to_comment_and_communication_preserve_state_and_grant_access(self):
        for kind in ('Comment', 'Communication'):
            with self.subTest(kind=kind):
                root = SimpleNamespace(name='root-' + kind, kind=kind, reply_to=None)
                self.doc.timeline.append(root)
                before = (self.doc.status, self.doc.next_action, self.doc.next_action_date)
                api.add_comment('issue', '<p>Hi <span data-type="mention" data-id="mentioned">@Mentioned</span></p>', reply_to=root.name)
                reply = self.doc.timeline[-1]
                self.assertEqual((reply.kind, reply.reply_to, reply.actor), ('Comment', root.name, 'owner'))
                self.assertEqual(before, (self.doc.status, self.doc.next_action, self.doc.next_action_date))
                self.assertTrue(api.issue_permission(self.doc, user='mentioned', ptype='read'))
                self.assertIn(root, self.doc.timeline)

    def test_invalid_cross_issue_system_and_nested_targets_are_rejected(self):
        self.doc.timeline.extend([SimpleNamespace(name='created', kind='Created', reply_to=None),
                                  SimpleNamespace(name='reply', kind='Comment', reply_to='some-root')])
        for target in ('other-issue-event', 'created', 'reply'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                api.add_comment('issue', '<p>Reply</p>', reply_to=target)
        self.assertFalse(self.doc.saved)
        self.assertEqual(len(self.doc.timeline), 2)

    def test_outsider_cannot_reply(self):
        self.doc.timeline.append(SimpleNamespace(name='root', kind='Comment', reply_to=None))
        self.session.user = 'outsider'
        with self.assertRaises(frappe.PermissionError): api.add_comment('issue', '<p>Reply</p>', reply_to='root')
        self.assertFalse(self.doc.saved)

    def test_resolved_issue_allows_reply_and_keeps_resolution(self):
        self.doc.status, self.doc.resolution_note = 'Resolved', 'Done'
        self.doc.next_action, self.doc.next_action_date = '', None
        self.doc.timeline.append(SimpleNamespace(name='root', kind='Communication', reply_to=None))
        api.add_comment('issue', '<p>Thanks</p>', reply_to='root')
        self.assertEqual(self.doc.timeline[-1].reply_to, 'root')
        self.assertEqual((self.doc.status, self.doc.resolution_note, self.doc.next_action, self.doc.next_action_date), ('Resolved', 'Done', '', None))

    def test_old_root_without_reply_field_and_new_top_level_comment(self):
        self.doc.timeline.append(SimpleNamespace(name='old', kind='Comment'))
        api.add_comment('issue', '<p>Reply</p>', reply_to='old')
        api.add_comment('issue', '<p>Independent comment</p>')
        self.assertEqual(self.doc.timeline[-2].reply_to, 'old')
        self.assertIsNone(self.doc.timeline[-1].reply_to)

    def test_active_issue_allows_comment_without_action(self):
        self.doc.next_action = ''
        self.doc.next_action_date = None
        api.add_comment('issue', '<p>Discussion</p>')
        self.assertTrue(self.doc.saved)


if __name__ == '__main__': unittest.main()
