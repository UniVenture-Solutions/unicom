import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import frappe
from unicom.selected_transfer import user_mapping


class TransferIdentityMappingTests(unittest.TestCase):
    def setUp(self):
        self.source = {'referenced_users': [
            {'name': 'Administrator', 'email': 'creator@example.invalid', 'full_name': 'Original Creator'},
            {'name': 'source-owner', 'email': 'owner@example.invalid', 'full_name': 'Original Owner'},
            {'name': 'source-actor', 'email': 'actor@example.invalid', 'full_name': 'Original Actor'},
            {'name': 'source-coordinator', 'email': 'coordinator@example.invalid', 'full_name': 'Original Coordinator'},
        ]}
        self.rows = {item['email']: [self.row(item['email'], item['email'])] for item in self.source['referenced_users']}
        self.pair = [self.row('Administrator', 'creator@example.invalid'), self.row('creator@example.invalid', 'creator@example.invalid')]
        self.rows['creator@example.invalid'] = self.pair
        self.sql = Mock(side_effect=lambda query, args, **kwargs: self.rows[args[0]])
        patcher = patch.object(frappe, 'db', SimpleNamespace(sql=self.sql))
        patcher.start(); self.addCleanup(patcher.stop)

    @staticmethod
    def row(name, email, enabled=1, user_type='System User'):
        return SimpleNamespace(name=name, email=email, full_name='Example Destination', enabled=enabled, user_type=user_type)

    def test_exact_administrator_and_email_pair_selects_named_account_in_either_order(self):
        for pair in (self.pair, list(reversed(self.pair))):
            self.rows['creator@example.invalid'] = pair
            mapping, identities = user_mapping(self.source, lock=True)
            self.assertEqual(mapping['Administrator'], 'creator@example.invalid')
            self.assertNotIn('Administrator', mapping.values())
            self.assertEqual(next(item for item in identities if item['source_user'] == 'Administrator')['target_user'], 'creator@example.invalid')
        self.assertTrue(all('FOR UPDATE' in call.args[0] for call in self.sql.call_args_list))

    def test_other_source_user_cannot_use_duplicate_exception(self):
        source = copy.deepcopy(self.source); source['referenced_users'][0]['name'] = 'ordinary-source-user'
        with self.assertRaises(ValueError): user_mapping(source)

    def test_other_pairs_extra_rows_and_wrong_named_id_are_rejected(self):
        cases = [
            [self.row('Administrator', 'creator@example.invalid'), self.row('different-login', 'creator@example.invalid')],
            [self.row('other-one', 'creator@example.invalid'), self.row('creator@example.invalid', 'creator@example.invalid')],
            self.pair + [self.row('third-login', 'creator@example.invalid')],
            [self.row('Administrator', 'creator@example.invalid'), self.row('CREATOR@example.invalid', 'creator@example.invalid')],
        ]
        for rows in cases:
            self.rows['creator@example.invalid'] = rows
            with self.subTest(names=[row.name for row in rows]), self.assertRaises(ValueError): user_mapping(self.source)

    def test_both_duplicate_accounts_must_be_active_system_users_with_exact_email(self):
        for index in (0, 1):
            for field, value in [('enabled', 0), ('user_type', 'Website User'), ('email', 'different@example.invalid')]:
                rows = copy.deepcopy(self.pair); setattr(rows[index], field, value)
                self.rows['creator@example.invalid'] = rows
                with self.subTest(index=index, field=field), self.assertRaises(ValueError): user_mapping(self.source)

    def test_unique_email_mapping_keeps_existing_behavior(self):
        self.rows['creator@example.invalid'] = [self.row('unique-existing-login', 'creator@example.invalid')]
        mapping, _ = user_mapping(self.source)
        self.assertEqual(mapping['Administrator'], 'unique-existing-login')
