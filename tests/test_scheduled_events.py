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

    def test_manual_schedule_is_owned_and_updates_date_only(self):
        self.schedule(contact='Customer',scheduled_time='09:30')
        event=self.doc.timeline[-1]
        self.assertEqual((event.kind,event.actor,event.follow_up_date,event.schedule_type),('Scheduled','owner','2026-11-21','Meeting'))
        self.assertEqual(event.scheduled_time,'09:30:00')
        self.assertEqual((self.doc.next_action,self.doc.next_action_date),('Call back','2026-11-21'))
        api._notify_mentions.assert_not_called()

    def test_legacy_explicit_true_still_updates_action_and_date(self):
        self.schedule(set_follow_up=True)
        self.assertEqual((self.doc.next_action,self.doc.next_action_date),('Meet customer','2026-11-21'))

    def test_explicit_false_updates_date_and_preserves_latest_action(self):
        self.doc.next_action='Latest action set by another update'
        self.schedule(set_follow_up=False)
        self.assertEqual((self.doc.next_action,self.doc.next_action_date),('Latest action set by another update','2026-11-21'))
        self.assertEqual(self.doc.timeline[-1].follow_up_action,'Meet customer')

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
            with self.assertRaises((ValueError,frappe.PermissionError)):self.schedule(source_comment='source')
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
        event.scheduled_for='other'
        with self.assertRaises(frappe.PermissionError):api.complete_scheduled_event('issue','scheduled')

    def test_today_query_is_site_date_actor_active_readable_and_incomplete(self):
        row={'name':'event','issue_name':'issue','scheduled_date':date(2026,11,19),'scheduled_time':timedelta(hours=9)}
        with patch.object(api,'today',return_value='2026-11-19'), patch.object(api,'issue_action_query',return_value='readable_only') as permission, patch.object(frappe.db,'sql',return_value=[row]) as sql:
            output=api.today_schedule()
        permission.assert_called_once_with('owner')
        query,args=sql.call_args.args
        self.assertEqual(args,('owner','2026-11-19'))
        for condition in ("e.kind = 'Scheduled'","COALESCE(NULLIF(e.scheduled_for, ''), e.actor) = %s",'e.follow_up_date = %s','e.completed_at IS NULL',"status IN ('Open','In Progress','Waiting')",'readable_only',"e.parentfield = 'timeline'"):
            self.assertIn(condition,query)
        self.assertEqual(output['date'],'2026-11-19')
        self.assertEqual(output['items'][0]['scheduled_date'],'2026-11-19')
        self.assertEqual(output['items'][0]['scheduled_time'],'09:00:00')

    def test_creator_owner_and_admin_can_confirm_for_readable_enabled_author(self):
        for confirmer in ('creator','owner','Administrator'):
            with self.subTest(confirmer=confirmer):
                self.session.user=confirmer
                source=SimpleNamespace(name='comment',kind='Comment',actor='mentioned',body='meeting will be scheduled on saturday',recorded_at='2026-11-18 10:00:00')
                self.doc.timeline=[source]
                self.doc.access=[SimpleNamespace(user='mentioned',reason='Participant')]
                self.schedule(source_comment='comment')
                event=self.doc.timeline[-1]
                self.assertEqual((event.actor,event.scheduled_for),(confirmer,'mentioned'))
                self.assertEqual((source.actor,source.recorded_at),('mentioned','2026-11-18 10:00:00'))
                self.assertEqual(self.doc.next_action_date,'2026-11-21')
                self.assertEqual(self.doc.next_action,'Call back')
                self.assertEqual(len(self.doc.access),1)
                event.name='scheduled'
                with self.assertRaises(ValueError):self.schedule(source_comment='comment')

    def test_regular_participant_cannot_delegate_but_can_schedule_own_comment(self):
        self.session.user='mentioned'
        self.doc.access=[SimpleNamespace(user='mentioned',reason='Participant')]
        source=SimpleNamespace(name='comment',kind='Comment',actor='owner')
        self.doc.timeline=[source]
        with self.assertRaises(ValueError):self.schedule(source_comment='comment')
        source.actor='mentioned'
        self.schedule(source_comment='comment')
        self.assertEqual(self.doc.timeline[-1].scheduled_for,'mentioned')

    def test_delegation_rejects_inactive_or_no_longer_readable_author(self):
        self.doc.timeline=[SimpleNamespace(name='comment',kind='Comment',actor='mentioned')]
        with self.assertRaises(frappe.PermissionError):self.schedule(source_comment='comment')
        self.doc.access=[SimpleNamespace(user='mentioned',reason='Participant')]
        with patch.object(frappe.db,'exists',return_value=False),self.assertRaises(frappe.PermissionError):self.schedule(source_comment='comment')
        self.assertFalse(self.doc.saved)

    def test_delegated_event_completion_uses_recipient_and_rechecks_issue_access(self):
        self.doc.timeline=[SimpleNamespace(name='comment',kind='Comment',actor='mentioned')]
        self.doc.access=[SimpleNamespace(user='mentioned',reason='Participant')]
        self.schedule(source_comment='comment')
        event=self.doc.timeline[-1];event.name='scheduled'
        with self.assertRaises(frappe.PermissionError):api.complete_scheduled_event('issue','scheduled')
        self.session.user='mentioned'
        self.doc.access=[]
        with self.assertRaises(frappe.PermissionError):api.complete_scheduled_event('issue','scheduled')
        self.doc.access=[SimpleNamespace(user='mentioned',reason='Participant')]
        api.complete_scheduled_event('issue','scheduled')
        self.assertTrue(event.completed_at)
        self.assertEqual(event.actor,'owner')

    def test_legacy_schedule_falls_back_to_actor_for_completion(self):
        self.doc.timeline=[SimpleNamespace(name='legacy',kind='Scheduled',actor='owner')]
        api.complete_scheduled_event('issue','legacy')
        self.assertTrue(self.doc.timeline[0].completed_at)
