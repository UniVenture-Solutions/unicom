import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from unicom import api, notifications, permissions


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


class MentionNotificationTests(unittest.TestCase):
    def setUp(self):
        self.doc = FakeDoc(name='issue', issue_id='ISU-0020', owner='owner', title='<b>Private & title</b>',
                           description='', accountable_owner='owner', coordination_user=None,
                           status='Open', next_action='', next_action_date=None, resolution_note='',
                           access=[], timeline=[], flags=SimpleNamespace(), saved=False, modified='2026-11-18 17:00:00')
        self.logs = []
        self.session = SimpleNamespace(user='owner')
        self.db = SimpleNamespace(exists=lambda doctype, filters: filters['name'] in {'owner', 'mentioned', 'second', 'website'})
        self.patches = [patch.object(frappe, 'get_roles', side_effect=lambda user=None: ['Management'] if (user or frappe.session.user) in {'owner','mentioned','second','website','recipient','Administrator'} else []), patch.object(frappe, 'session', self.session), patch.object(frappe, 'db', self.db),
                        patch.object(frappe, 'new_doc', side_effect=self.new_doc), patch.object(frappe, 'get_doc', return_value=self.doc),
                        patch.object(frappe, 'throw', side_effect=self.throw), patch.object(api, '_output', side_effect=lambda doc: doc),
                        patch.object(api, 'now_datetime', return_value='2026-11-18 17:00:00'),
                        patch.object(notifications, 'is_notifications_enabled', return_value=True)]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    @staticmethod
    def throw(message, exception=None):
        raise (exception or ValueError)(message)

    def new_doc(self, doctype):
        if doctype == 'UniCom Issue':
            return self.doc
        self.assertEqual(doctype, 'Notification Log')
        log = FakeDoc()
        def insert(**kwargs):
            self.assertTrue(self.doc.saved, 'Issue must save before its notification is inserted')
            self.logs.append(log)
        log.insert = insert
        return log

    @staticmethod
    def body(*users):
        return '<p>' + ''.join('<span data-type="mention" data-id="' + user + '">@User</span>' for user in users) + '</p>'

    def test_create_description_deduplicates_and_skips_self_with_safe_direct_link(self):
        self.doc.name = 'issue/name?'
        api.create_issue(self.doc.title, 'owner', description=self.body('mentioned', 'mentioned', 'owner'))
        self.assertEqual(len(self.logs), 1)
        log = self.logs[0]
        self.assertEqual((log.type, log.for_user, log.from_user), ('Alert', 'mentioned', 'owner'))
        self.assertEqual((log.document_type, log.document_name, log.link), ('UniCom Issue', 'issue/name?', '/unicom/issue%2Fname%3F'))
        self.assertIn('description', log.subject)
        self.assertNotIn('<b>', log.subject)
        self.assertIn('&lt;b&gt;Private &amp; title&lt;/b&gt;', log.subject)

    def test_description_notifies_new_presence_even_with_existing_access(self):
        self.doc.access = [SimpleNamespace(user='mentioned', reason='Mention')]
        api.update_issue('issue', {'description': self.body('mentioned')})
        self.assertEqual(len(self.logs), 1)
        api.update_issue('issue', {'title': 'Unrelated'})
        api.update_issue('issue', {'description': '<p>Changed formatting</p>' + self.body('mentioned')})
        self.assertEqual(len(self.logs), 1)
        api.update_issue('issue', {'description': self.body('mentioned', 'second')})
        self.assertEqual([log.for_user for log in self.logs], ['mentioned', 'second'])
        api.update_issue('issue', {'description': '<p>Removed</p>'})
        api.update_issue('issue', {'description': self.body('mentioned')})
        self.assertEqual([log.for_user for log in self.logs], ['mentioned', 'second', 'mentioned'])

    def test_each_comment_and_reply_notifies_existing_mentioned_user_once(self):
        self.doc.access = [SimpleNamespace(user='mentioned', reason='Mention')]
        self.doc.timeline = [SimpleNamespace(name='root', kind='Comment', reply_to=None)]
        api.add_comment('issue', self.body('mentioned', 'mentioned', 'owner'))
        api.add_comment('issue', self.body('mentioned'))
        api.add_comment('issue', self.body('mentioned'), reply_to='root')
        self.assertEqual([log.for_user for log in self.logs], ['mentioned'] * 3)
        self.assertIn('comment', self.logs[0].subject)
        self.assertIn('reply', self.logs[-1].subject)

    def test_plain_foreign_empty_or_sanitized_away_mentions_do_not_notify(self):
        api.add_comment('issue', '<p>@mentioned <span data-type="reference" data-id="mentioned">@Source</span><span data-type="mention" data-id="mentioned"> </span></p>')
        with patch.object(api, '_rich_html', return_value='<p>Retained text</p>'):
            api.update_issue('issue', {'description': self.body('mentioned')})
        self.assertEqual(self.logs, [])

    def test_validation_and_failed_issue_save_do_not_create_notification(self):
        with self.assertRaises(ValueError):
            api.add_comment('issue', self.body('disabled'))
        with patch.object(self.doc, 'save', side_effect=ValueError('Save failed')):
            with self.assertRaises(ValueError):
                api.add_comment('issue', self.body('mentioned'))
        self.assertEqual(self.logs, [])

    def test_native_opt_out_skips_log_but_does_not_remove_access(self):
        with patch.object(notifications, 'is_notifications_enabled', return_value=False):
            api.add_comment('issue', self.body('mentioned'))
        self.assertEqual(self.logs, [])
        self.assertTrue(permissions.issue_permission(self.doc, 'mentioned', 'read'))

    def test_website_user_receives_same_native_log(self):
        api.add_comment('issue', self.body('website'))
        self.assertEqual(self.logs[0].for_user, 'website')

    def test_empty_recipient_set_does_not_touch_session_or_database(self):
        with patch.object(frappe, 'session', None), patch.object(frappe, 'new_doc') as new_doc:
            notifications.notify_mentions(self.doc, [], 'description')
        new_doc.assert_not_called()

    def test_native_alert_realtime_waits_for_commit_and_cannot_email(self):
        from frappe.desk.doctype.notification_log import notification_log as native
        log = SimpleNamespace(type='Alert', for_user='mentioned')
        with patch.object(frappe, 'publish_realtime') as publish, patch.object(native, 'set_notifications_as_unseen') as unseen, patch.object(native, 'send_notification_email') as email, patch.object(frappe, 'db', SimpleNamespace(get_value=lambda *args, **kwargs: 1)):
            native.NotificationLog.after_insert(log)
        publish.assert_called_once_with('notification', after_commit=True, user='mentioned')
        unseen.assert_called_once_with('mentioned')
        email.assert_not_called()


class NotificationInboxTests(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace(user='website')
        self.db = SimpleNamespace(count=Mock(return_value=2), exists=Mock(return_value=True), set_value=Mock())
        self.patches = [patch.object(frappe, 'get_roles', side_effect=lambda user=None: ['Management'] if (user or frappe.session.user) in {'owner','mentioned','second','website','recipient','Administrator'} else []), patch.object(frappe, 'session', self.session), patch.object(frappe, 'db', self.db),
                        patch.object(frappe, 'throw', side_effect=MentionNotificationTests.throw)]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    def test_list_count_and_pagination_are_recipient_and_app_scoped(self):
        rows = [SimpleNamespace(name='log' + str(i), subject='Mention &lt;private&gt;', document_name='issue/name?', from_user='owner', creation='2026-11-18 17:00:00', read=0) for i in range(51)]
        with patch.object(frappe, 'get_all', return_value=rows) as get_all:
            result = api.list_notifications(start=-10, page_length=500)
        args = get_all.call_args.kwargs
        self.assertEqual(args['filters']['for_user'], 'website')
        self.assertEqual(args['filters']['document_type'], 'UniCom Issue')
        self.assertEqual(args['filters']['type'], 'Alert')
        self.assertEqual((args['limit_start'], args['limit_page_length']), (0, 51))
        self.assertEqual(len(result['items']), 50)
        self.assertTrue(result['has_more'])
        self.assertEqual(result['next_start'], 50)
        self.assertEqual(result['items'][0]['link'], '/unicom/issue%2Fname%3F')
        self.assertEqual(result['items'][0]['subject'], 'Mention <private>')
        self.assertEqual(self.db.count.call_args.kwargs['filters']['for_user'], 'website')
        self.assertEqual(self.db.count.call_args.kwargs['filters']['read'], 0)

    def test_mark_read_uses_current_recipient_and_scope_and_preserves_metadata(self):
        api.mark_notification_read('log')
        filters = self.db.set_value.call_args.args[1]
        self.assertEqual(filters['for_user'], 'website')
        self.assertEqual(filters['name'], 'log')
        self.assertEqual(filters['document_type'], 'UniCom Issue')
        self.assertFalse(self.db.set_value.call_args.kwargs['update_modified'])
        self.db.exists.return_value = False
        with self.assertRaises(frappe.PermissionError):
            api.mark_notification_read('other-user-log')
        self.assertEqual(self.db.set_value.call_count, 1)

    def test_guest_cannot_list_or_mark_notifications(self):
        self.session.user = 'Guest'
        for call in (lambda: api.list_notifications(), lambda: api.mark_notification_read('log')):
            with self.assertRaises(frappe.PermissionError):
                call()
        self.db.set_value.assert_not_called()
        self.db.count.assert_not_called()

    def test_direct_read_guard_is_scoped_and_does_not_grant_native_writes(self):
        ours = SimpleNamespace(document_type='UniCom Issue', for_user='recipient')
        self.assertTrue(permissions.notification_permission(ours, user='recipient', ptype='read'))
        self.assertTrue(permissions.notification_permission(ours, user='Administrator', ptype='read'))
        self.assertFalse(permissions.notification_permission(ours, user='outsider', ptype='read'))
        self.assertFalse(permissions.notification_permission(ours, user='Guest', ptype='read'))
        other = SimpleNamespace(document_type='Sales Invoice', for_user='recipient')
        self.assertTrue(permissions.notification_permission(other, user='outsider', ptype='read'))
        # Frappe controller hooks can only deny; native role permissions still apply.
