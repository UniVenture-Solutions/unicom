import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from werkzeug.wrappers import Request, Response

import frappe
from unicom import access, api, hooks, notifications, permissions


class ManagementAccessTests(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace(user='member')
        self.roles = {'Administrator':['Management','System Manager'], 'member':['Management'],
                      'owner':['Management'], 'coordinator':['Management'], 'participant':['Management'],
                      'mentioned':['Management'], 'manager':['Management','System Manager'], 'outsider':['System Manager']}
        self.doc = SimpleNamespace(owner='owner',accountable_owner='owner',coordination_user='coordinator',
                                   access=[SimpleNamespace(user='participant',reason='Participant'),SimpleNamespace(user='mentioned',reason='Mention')])
        self.patches = [patch.object(frappe,'session',self.session),
                        patch.object(frappe,'get_roles',side_effect=lambda user=None:self.roles.get(user or self.session.user,[])),
                        patch.object(frappe,'throw',side_effect=self.throw),
                        patch.object(frappe,'db',SimpleNamespace(escape=lambda user:repr(user)))]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    @staticmethod
    def throw(message,exception=None):raise (exception or ValueError)(message)

    def test_management_is_required_without_system_manager_bypass(self):
        self.assertFalse(access.has_management_access('Guest'))
        self.assertFalse(access.has_management_access('outsider'))
        self.assertTrue(access.has_management_access('Administrator'))
        self.assertTrue(access.has_management_access('member'))
        self.session.user='outsider'
        with self.assertRaises(frappe.PermissionError):api._user()
        self.assertEqual(permissions.issue_query('outsider'),'1=0')
        self.assertFalse(permissions.issue_permission(self.doc,'outsider','read'))
        self.assertFalse(permissions.issue_action_permission(self.doc,'outsider'))

    def test_coordinator_and_manager_read_never_broaden_workflow_writes(self):
        with patch.object(frappe,'get_doc',return_value=self.doc):
            for user in ('coordinator','manager'):
                self.session.user=user
                self.assertIs(api._doc('issue'),self.doc)
                with self.assertRaises(frappe.PermissionError):api._doc('issue',lock=True)
                self.assertFalse(permissions.issue_permission(self.doc,user,'write'))
        self.assertTrue(permissions.issue_action_permission(self.doc,'owner'))
        self.assertTrue(permissions.issue_action_permission(self.doc,'participant'))
        self.assertTrue(permissions.issue_action_permission(self.doc,'mentioned'))
        self.assertEqual(permissions.issue_query('manager'),'')
        self.assertIn('coordination_user',permissions.issue_query('coordinator'))
        self.assertNotIn('coordination_user',permissions.issue_action_query('coordinator'))

    def test_nonmember_api_guard_runs_before_data_lookup(self):
        self.session.user='outsider'
        with patch.object(frappe,'get_doc') as get_doc,patch.object(frappe,'get_all') as get_all,patch.object(frappe,'get_list') as get_list:
            for action in (lambda:api._doc('known'),lambda:api.list_issues(),lambda:api.users(),lambda:api.dashboard_receivables(),lambda:api.dashboard_monthly(),lambda:api.list_notifications()):
                with self.assertRaises(frappe.PermissionError):action()
            get_doc.assert_not_called();get_all.assert_not_called();get_list.assert_not_called()

    def test_native_notification_query_and_doc_guards_preserve_other_apps(self):
        self.assertEqual(permissions.notification_query('member'),'')
        self.assertIn("!= 'UniCom Issue'",permissions.notification_query('outsider'))
        ours=SimpleNamespace(document_type='UniCom Issue',for_user='outsider')
        self.assertFalse(permissions.notification_permission(ours,'outsider'))
        self.assertTrue(permissions.notification_permission(SimpleNamespace(document_type='Other'),'outsider'))
        with patch.object(frappe,'new_doc') as create:
            notifications.notify_mentions(SimpleNamespace(name='issue'),['outsider'],'comment')
            create.assert_not_called()
        self.session.user='outsider'
        with self.assertRaises(frappe.PermissionError):notifications.list_for_user('outsider')
        with self.assertRaises(frappe.PermissionError):notifications.mark_read_for_user('outsider','log')

    def test_only_native_responses_with_unicom_logs_disable_browser_caching(self):
        request=Request.from_values(path='/api/method/frappe.desk.doctype.notification_log.notification_log.get_notification_logs')
        for doctype,expected in [('UniCom Issue','no-store, private'),('Other','private, max-age=60')]:
            response=Response(json.dumps({'message':{'notification_logs':[{'document_type':doctype}]}}),content_type='application/json')
            response.headers['Cache-Control']='private, max-age=60'
            access.prevent_notification_response_cache(response,request)
            self.assertEqual(response.headers['Cache-Control'],expected)

    def test_fixture_and_boot_hook_are_exact_without_user_assignments(self):
        root=Path(__file__).resolve().parents[1]
        fixture=json.loads((root/'unicom/fixtures/role.json').read_text())
        self.assertEqual(fixture,[{'doctype':'Role','name':'Management','role_name':'Management','desk_access':1,'disabled':0}])
        self.assertEqual(hooks.fixtures,[{'dt':'Role','filters':[['name','=','Management']]}])
        self.assertEqual(hooks.add_to_apps_screen[0]['has_permission'],'unicom.access.has_management_access')
        schema=json.loads((root/'unicom/unicom/doctype/unicom_issue/unicom_issue.json').read_text())
        self.assertEqual(schema['permissions'],[{'role':'Management','read':1}])
        self.assertTrue(any(row['from_route']=='/unicom-import' for row in hooks.website_route_rules))
        self.assertEqual(hooks.permission_query_conditions['Notification Log'],'unicom.permissions.notification_query')

    def test_relative_age_boundaries_are_site_local_and_preserve_raw_values(self):
        at=datetime(2026,11,20,12)
        for seconds,expected in [(0,'0m'),(59,'0m'),(60,'1m'),(3599,'59m'),(3600,'1h'),(86399,'23h'),(86400,'1d'),(30*86400-1,'29d'),(30*86400,'1M'),(365*86400-1,'12M'),(365*86400,'1Y')]:
            self.assertEqual(api._last_updated_label(at-timedelta(seconds=seconds),at),expected)
        self.assertEqual(api._last_updated_label(None,at),'—')
        self.assertEqual(api._last_updated_label(at+timedelta(minutes=1),at),'0m')

    def test_comment_aggregate_is_limited_to_permission_filtered_page(self):
        row=frappe._dict(name='visible',modified=datetime(2026,11,20,12),status='Open',next_action_date=None)
        self.session.user='manager'
        with patch.object(frappe,'get_list',return_value=[row]) as get_list,patch.object(frappe,'get_all',return_value=[frappe._dict(parent='visible',comment_count=12)]) as aggregate,patch.object(api,'now_datetime',return_value=row.modified) as clock:
            result=api.list_issues(view='mine')
        self.assertEqual(result[0].comment_count,12)
        self.assertEqual(result[0].modified,datetime(2026,11,20,12))
        clock.assert_called_once()
        self.assertNotIn('name',get_list.call_args.kwargs['filters'])
        self.assertEqual(aggregate.call_args.kwargs['filters'],{'parent':['in',['visible']],'parenttype':'UniCom Issue','parentfield':'timeline','kind':'Comment'})
