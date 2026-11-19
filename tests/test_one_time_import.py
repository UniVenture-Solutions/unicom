import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import frappe
from jinja2 import Environment
from unicom import one_time_import as web, selected_transfer as core


class Cache:
    def __init__(self): self.values = {}; self.expiry = None
    def set_value(self, key, value, expires_in_sec=None): self.values[key] = copy.deepcopy(value); self.expiry = expires_in_sec
    def get_value(self, key, **kwargs): return self.values.get(key)
    def delete_value(self, key): self.values.pop(key, None)


class OneTimeImportTests(unittest.TestCase):
    def setUp(self):
        self.request = SimpleNamespace(host='univenturetraders.com', method='POST', headers={'Origin': web.ORIGIN, 'X-Frappe-CSRF-Token': 'session-token'})
        self.local = SimpleNamespace(site='internal-production-site', request=self.request, response={})
        self.session = SimpleNamespace(user='Administrator', sid='session-one', data={'csrf_token': 'session-token'})
        self.cache = Cache()
        self.source = {'referenced_users': [{'name': 'source-user', 'full_name': 'Example Source'}], 'private_body': 'never-return-this-body'}
        self.report = {'plan_sha256': 'digest', 'applied': False, 'plan': {'issues': [{'source_issue_id': 'ISU-0014', 'action': 'create', 'event_count': 67}], 'identities': [{'source_user': 'source-user', 'target_full_name': 'Example Target', 'target_user': 'target-user'}], 'series_before': 0, 'series_after': 18}}
        self.load = Mock(return_value=self.source)
        self.run = Mock(return_value=self.report)
        self.db = SimpleNamespace(rollback=Mock())
        patches = [patch('unicom.access._', side_effect=lambda message: message), patch.object(frappe, 'get_roles', side_effect=lambda user=None: ['Management'] if (user or frappe.session.user) in {'Administrator'} else []), patch.object(frappe, 'local', self.local), patch.object(frappe, 'session', self.session), patch.object(frappe, 'cache', self.cache), patch.object(frappe, 'db', self.db), patch.object(frappe, 'throw', side_effect=self.throw), patch.object(core, 'load_source', self.load), patch.object(core, 'run', self.run)]
        for item in patches: item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])

    @staticmethod
    def throw(message, exception=None): raise (exception or ValueError)(message)

    def test_existing_admin_host_checks_also_require_management(self):
        with patch.object(frappe, 'get_roles', return_value=[]):
            with self.assertRaises(frappe.PermissionError):web.preview('payload')
        self.run.assert_not_called()
        self.request.host='wrong.invalid'
        with patch.object(web, 'require_management_access') as gate:
            with self.assertRaises(frappe.PermissionError):web.preview('payload')
            gate.assert_not_called()

    def test_only_two_public_mutation_methods_are_post_only(self):
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[web.preview], ['POST'])
        self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[web.apply], ['POST'])
        self.assertNotIn(web.preview, frappe.guest_methods)
        self.assertNotIn(core.run, frappe.whitelisted)

    def test_regular_user_and_guest_cannot_preview_or_apply(self):
        for user in ('ordinary-user', 'Guest'):
            self.session.user = user
            for action in (lambda: web.preview('payload'), lambda: web.apply('payload', 'x' * 40, 'digest')):
                with self.subTest(user=user), self.assertRaises(frappe.PermissionError): action()
        self.load.assert_not_called(); self.run.assert_not_called()

    def test_wrong_host_source_site_and_get_are_denied(self):
        for host, site, method in [('other.example', self.local.site, 'POST'), ('univenturetraders.com', core.SOURCE_SITE, 'POST'), ('univenturetraders.com', self.local.site, 'GET')]:
            self.request.host, self.local.site, self.request.method = host, site, method
            with self.subTest(host=host, site=site, method=method), self.assertRaises(frappe.PermissionError): web.preview('payload')
        self.run.assert_not_called()

    def test_origin_and_exact_session_csrf_are_required(self):
        for origin, token in [(None, 'session-token'), ('https://other.example', 'session-token'), (web.ORIGIN, ''), (web.ORIGIN, 'other-token')]:
            self.request.headers = {'Origin': origin, 'X-Frappe-CSRF-Token': token}
            with self.subTest(origin=origin, token=token), self.assertRaises(frappe.CSRFTokenError): web.preview('payload')
        self.run.assert_not_called()

    def test_preview_is_metadata_only_and_session_bound_for_fifteen_minutes(self):
        result = web.preview('payload')
        self.assertTrue(result['ok']); self.assertTrue(result['needs_apply'])
        self.run.assert_called_once_with('payload', 'internal-production-site')
        self.assertNotIn('never-return-this-body', json.dumps(result))
        self.assertEqual(result['user_mappings'][0]['source_name'], 'Example Source')
        self.assertEqual(self.cache.expiry, 900)
        self.assertNotIn('payload', json.dumps(self.cache.values))
        self.assertEqual(self.local.response['headers']['Cache-Control'], 'no-store, private')

    def test_apply_accepts_only_previewed_plan_and_consumes_preview(self):
        preview = web.preview('payload'); self.run.reset_mock()
        result = web.apply('payload', preview['preview_token'], 'digest')
        self.assertTrue(result['ok']); self.assertTrue(result['completed'])
        self.run.assert_called_once_with('payload', 'internal-production-site', apply=True, expected_plan_sha='digest')
        self.assertEqual(self.cache.values, {})
        self.run.reset_mock(); result = web.apply('payload', preview['preview_token'], 'digest')
        self.assertFalse(result['ok']); self.run.assert_not_called()

    def test_changed_session_site_plan_or_expired_token_cannot_apply(self):
        preview = web.preview('payload'); self.run.reset_mock()
        self.assertFalse(web.apply('payload', preview['preview_token'], 'tampered')['ok'])
        self.session.sid = 'different-session'
        self.assertFalse(web.apply('payload', preview['preview_token'], 'digest')['ok'])
        self.session.sid = 'session-one'; self.local.site = 'other-internal-site'
        self.assertFalse(web.apply('payload', preview['preview_token'], 'digest')['ok'])
        self.local.site = 'internal-production-site'; self.cache.values.clear()
        self.assertFalse(web.apply('payload', preview['preview_token'], 'digest')['ok'])
        self.run.assert_not_called()

    def test_unknown_errors_are_not_exposed_and_do_not_claim_no_commit(self):
        preview = web.preview('payload'); self.run.side_effect = RuntimeError('SQL secret payload traceback')
        result = web.apply('payload', preview['preview_token'], 'digest')
        self.assertFalse(result['ok']); self.assertNotIn('SQL secret', result['message'])
        self.assertIn('could not be confirmed', result['message'])
        self.db.rollback.assert_called_once()

    def test_complete_match_preview_needs_no_apply_unless_series_needs_repair(self):
        self.report['plan']['issues'][0]['action'] = 'skip_complete'
        self.report['plan']['series_before'] = 18
        self.assertFalse(web.preview('payload')['needs_apply'])
        self.report['plan']['series_before'] = 0
        self.assertTrue(web.preview('payload')['needs_apply'])

    def test_page_exposes_form_only_to_authorized_session(self):
        template = Environment(autoescape=True).from_string(Path(__file__).resolve().parents[1].joinpath('unicom/www/unicom_import.html').read_text())
        anonymous = template.render(import_authorized=False)
        self.assertIn('Administrator login is required', anonymous)
        self.assertNotIn('type="file"', anonymous); self.assertNotIn('<script>', anonymous)
        allowed = template.render(import_authorized=True, csrf_token='example-token')
        self.assertIn('type="file"', allowed); self.assertIn('credentials:', allowed)
        self.assertNotIn('innerHTML', allowed)


class SnapshotPinTests(unittest.TestCase):
    def test_unknown_payload_oversize_or_path_is_rejected_without_file_reads(self):
        for value in ('{}', '/etc/passwd', 'x' * (100 * 1024 + 1), None):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError): core.load_source(value)
