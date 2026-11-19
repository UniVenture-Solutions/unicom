import unittest
from types import SimpleNamespace
from datetime import date, timedelta
from unittest.mock import patch
import frappe
from unicom import api
import test_comments


class ScheduledEventTests(unittest.TestCase):
    setUp = test_comments.CommentTests.setUp
    throw = staticmethod(test_comments.CommentTests.throw)

    def schedule(self, **kwargs):
        values=dict(name='issue',schedule_type='Meeting',scheduled_date='2026-11-21',title='Meet customer')
        values.update(kwargs)
        return api.schedule_event(**values)

    def test_manual_schedule_is_owned_and_default_does_not_change_issue(self):
        self.schedule(contact='Customer',scheduled_time='09:30')
        event=self.doc.timeline[-1]
        self.assertEqual((event.kind,event.actor,event.follow_up_date,event.schedule_type),('Scheduled','owner','2026-11-21','Meeting'))
        self.assertEqual(event.scheduled_time,'09:30:00')
        self.assertEqual((self.doc.next_action,self.doc.next_action_date),('Call back','2026-11-20'))
        api._notify_mentions.assert_not_called()

    def test_confirmed_opt_in_updates_action_and_date(self):
        self.schedule(set_follow_up=True)
        self.assertEqual((self.doc.next_action,self.doc.next_action_date),('Meet customer','2026-11-21'))

    def test_invalid_required_values_do_not_save(self):
        for values in ({'title':''},{'title':' '*3},{'scheduled_date':''},{'scheduled_date':'2026-02-30'},
                       {'scheduled_date':'tomorrow'},{'scheduled_time':'25:00'},{'scheduled_time':[]},
                       {'schedule_type':'Call'},{'set_follow_up':'false'}):
            with self.subTest(values=values),self.assertRaises(ValueError):self.schedule(**values)
        self.assertFalse(self.doc.saved)
        self.assertEqual(self.doc.timeline,[])

    def test_source_own_comment_and_separate_communication_dedup(self):
        source=SimpleNamespace(name='comment',kind='Comment',actor='owner',reply_to='root')
        communication=SimpleNamespace(name='communication',kind='Communication',source_comment='comment')
        self.doc.timeline=[source,communication]
        self.schedule(source_comment='comment')
        self.doc.timeline[-1].name='schedule'
        with self.assertRaises(ValueError):self.schedule(source_comment='comment')
        self.assertIs(self.doc.timeline[0],source)
        self.assertEqual(len(self.doc.timeline),3)

    def test_communication_is_allowed_after_schedule_for_same_comment(self):
        self.doc.timeline=[SimpleNamespace(name='comment',kind='Comment',actor='owner'),
                           SimpleNamespace(name='scheduled',kind='Scheduled',source_comment='comment')]
        api.log_communication('issue','Call','2026-11-19 10:00:00','<p>Called customer</p>',source_comment='comment',set_follow_up=False)
        self.assertEqual(self.doc.timeline[-1].kind,'Communication')

    def test_invalid_source_and_unreadable_issue_rejected(self):
        for event in (None,SimpleNamespace(name='source',kind='Comment',actor='other'),SimpleNamespace(name='source',kind='Communication',actor='owner')):
            self.doc.timeline=[event] if event else []
            with self.assertRaises(ValueError):self.schedule(source_comment='source')
        self.session.user='outsider'
        with self.assertRaises(frappe.PermissionError):self.schedule()
        self.assertFalse(self.doc.saved)

    def test_resolved_issue_rejects_schedule(self):
        self.doc.status='Resolved'
        with self.assertRaises(ValueError):self.schedule()
        self.assertFalse(self.doc.saved)

    def test_completion_is_owned_and_idempotent(self):
        self.schedule()
        event=self.doc.timeline[-1];event.name='scheduled'
        with patch.object(self.doc,'save',wraps=self.doc.save) as save:
            api.complete_scheduled_event('issue','scheduled')
            first=event.completed_at
            api.complete_scheduled_event('issue','scheduled')
            self.assertEqual(event.completed_at,first)
            self.assertEqual(save.call_count,1)
        self.assertEqual(len(self.doc.timeline),1)
        event.actor='other'
        with self.assertRaises(frappe.PermissionError):api.complete_scheduled_event('issue','scheduled')

    def test_today_query_is_site_date_actor_active_readable_and_incomplete(self):
        row={'name':'event','issue_name':'issue','scheduled_date':date(2026,11,19),'scheduled_time':timedelta(hours=9)}
        with patch.object(api,'today',return_value='2026-11-19'), patch.object(api,'issue_query',return_value='readable_only') as permission, patch.object(frappe.db,'sql',return_value=[row]) as sql:
            output=api.today_schedule()
        permission.assert_called_once_with('owner')
        query,args=sql.call_args.args
        self.assertEqual(args,('owner','2026-11-19'))
        for condition in ("e.kind = 'Scheduled'",'e.actor = %s','e.follow_up_date = %s','e.completed_at IS NULL',"status IN ('Open','In Progress','Waiting')",'readable_only',"e.parentfield = 'timeline'"):
            self.assertIn(condition,query)
        self.assertEqual(output['date'],'2026-11-19')
        self.assertEqual(output['items'][0]['scheduled_date'],'2026-11-19')
        self.assertEqual(output['items'][0]['scheduled_time'],'09:00:00')
