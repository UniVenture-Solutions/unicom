import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from unicom import issue_ids
from unicom.patches import backfill_issue_ids
from unicom.unicom.doctype.unicom_issue.unicom_issue import UniComIssue


class FakeDB:
    def __init__(self, rows, current=0):
        self.rows, self.current = rows, current
    def sql(self, query, params=None, as_dict=False):
        if query.startswith('SELECT name, issue_id'):
            return self.rows
        if query.startswith('UPDATE `tabSeries`'):
            self.current = max(self.current, params[0])
        return []
    def set_value(self, doctype, name, field, value, update_modified=True):
        assert doctype == 'UniCom Issue' and field == 'issue_id' and not update_modified
        next(row for row in self.rows if row.name == name).issue_id = value
    def next_id(self):
        self.current += 1
        return f'ISU-{self.current:04d}'


class IssueIdTests(unittest.TestCase):
    def test_allocation_locks_and_uses_frappe_series(self):
        with patch.object(issue_ids, 'lock_series') as lock, patch.object(issue_ids, 'make_autoname', return_value='ISU-0001') as generate:
            self.assertEqual(issue_ids.next_issue_id(), 'ISU-0001')
            lock.assert_called_once()
            generate.assert_called_once_with('ISU-.####')

    def test_backfill_preserves_existing_and_is_idempotent(self):
        rows = [SimpleNamespace(name='old-a', issue_id=None), SimpleNamespace(name='existing', issue_id='ISU-0017'), SimpleNamespace(name='old-b', issue_id=None)]
        db = FakeDB(rows, current=5)
        with patch.object(frappe, 'db', db), patch.object(backfill_issue_ids, 'lock_series'), patch.object(backfill_issue_ids, 'next_issue_id', side_effect=db.next_id):
            backfill_issue_ids.execute()
            self.assertEqual([x.issue_id for x in rows], ['ISU-0018', 'ISU-0017', 'ISU-0019'])
            backfill_issue_ids.execute()
            self.assertEqual(db.current, 19)
            self.assertEqual([x.name for x in rows], ['old-a', 'existing', 'old-b'])

    def test_backfill_rejects_invalid_or_duplicate_existing_ids(self):
        for ids in [('bad-id', None), ('ISU-0001', 'ISU-0001'), ('ISU-00001', None), ('ISU-0000', None)]:
            db = FakeDB([SimpleNamespace(name=str(i), issue_id=value) for i, value in enumerate(ids)])
            def throw(message, *args): raise ValueError(message)
            with self.subTest(ids=ids), patch.object(frappe, 'db', db), patch.object(frappe, 'throw', side_effect=throw), patch.object(backfill_issue_ids, 'lock_series'), patch.object(backfill_issue_ids, 'next_issue_id', side_effect=db.next_id):
                with self.assertRaises(ValueError): backfill_issue_ids.execute()
                self.assertEqual(db.current, 0)

    def test_series_continues_beyond_four_digits(self):
        rows = [SimpleNamespace(name='old', issue_id=None)]
        db = FakeDB(rows, current=9999)
        with patch.object(frappe, 'db', db), patch.object(backfill_issue_ids, 'lock_series'), patch.object(backfill_issue_ids, 'next_issue_id', side_effect=db.next_id):
            backfill_issue_ids.execute()
            self.assertEqual(rows[0].issue_id, 'ISU-10000')

    def test_preassigned_and_changed_ids_are_rejected(self):
        def throw(message, exception=None): raise (exception or ValueError)(message)
        doc = SimpleNamespace(issue_id='ISU-0020', flags=SimpleNamespace(unicom_api=True), get_doc_before_save=lambda: SimpleNamespace(issue_id='ISU-0019'))
        with patch.object(frappe, 'throw', side_effect=throw):
            with self.assertRaises(frappe.ValidationError): UniComIssue.before_insert(doc)
            with self.assertRaises(frappe.ValidationError): UniComIssue.validate(doc)

if __name__ == '__main__': unittest.main()
