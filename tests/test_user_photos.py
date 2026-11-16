import unittest
from types import SimpleNamespace
from unittest.mock import patch
import frappe
from unicom import api


class UserPhotoTests(unittest.TestCase):
    def test_directory_keeps_existing_scope_and_exposes_photo(self):
        with patch.object(api, '_user'), patch.object(frappe, 'get_all', return_value=[]) as get_all:
            api.users()
        self.assertEqual(get_all.call_args.kwargs['filters']['enabled'], 1)
        self.assertEqual(get_all.call_args.kwargs['filters']['name'], ['not in', ['Guest', 'Administrator']])
        self.assertIn('user_image', get_all.call_args.kwargs['fields'])

    def test_denied_issue_never_returns_profiles(self):
        with patch.object(api, '_doc', side_effect=frappe.PermissionError), patch.object(frappe, 'get_all') as get_all:
            with self.assertRaises(frappe.PermissionError): api.get_issue('not-accessible')
            get_all.assert_not_called()

    def test_detail_profiles_only_referenced_issue_people(self):
        doc=SimpleNamespace(owner='creator', accountable_owner='owner', coordination_user='coordinator', status='Resolved', next_action_date=None,
                            timeline=[SimpleNamespace(actor='Administrator'), SimpleNamespace(actor='former'), SimpleNamespace(actor='former')],
                            attachments=[], as_dict=lambda: {})
        with patch.object(frappe, 'get_all', return_value=[]) as get_all:
            result=api._output(doc)
        self.assertEqual(result['user_profiles'], [])
        self.assertEqual(set(get_all.call_args.kwargs['filters']['name'][1]), {'creator','owner','coordinator','Administrator','former'})
        self.assertEqual(get_all.call_args.kwargs['fields'], ['name','full_name','user_image'])

if __name__ == '__main__': unittest.main()
