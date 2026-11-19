import unittest
from types import SimpleNamespace
import test_comments
from unicom import api


class CommunicationFollowUpTests(unittest.TestCase):
    setUp = test_comments.CommentTests.setUp
    throw = staticmethod(test_comments.CommentTests.throw)

    def log(self, **kwargs):
        return api.log_communication('issue', 'Call', '2026-11-19 10:00:00', '<p>Spoke with someone</p>', **kwargs)

    def test_unchecked_preserves_issue_and_saves_event_follow_up(self):
        self.log(next_action='Visit', next_action_date='2026-11-21', set_follow_up=False)
        self.assertEqual((self.doc.next_action, self.doc.next_action_date), ('Call back', '2026-11-20'))
        self.assertEqual(self.doc.timeline[-1].follow_up_date, '2026-11-21')
        self.assertEqual(self.doc.timeline[-1].follow_up_action, 'Visit')

    def test_checked_updates_issue_and_requires_date(self):
        with self.assertRaises(ValueError): self.log(set_follow_up=True)
        self.assertFalse(self.doc.saved)
        self.log(next_action='Visit', next_action_date='2026-11-21', set_follow_up=True)
        self.assertEqual((self.doc.next_action, self.doc.next_action_date), ('Visit', '2026-11-21'))

    def test_checked_blank_action_only_changes_issue_date(self):
        for action in (None, '', '   '):
            with self.subTest(action=action):
                self.doc.next_action = 'Call back'
                self.log(next_action=action, next_action_date='2026-11-21', set_follow_up=True)
                self.assertEqual((self.doc.next_action, self.doc.next_action_date), ('Call back', '2026-11-21'))
                self.assertEqual(self.doc.timeline[-1].follow_up_action, action)

    def test_legacy_blank_action_still_clears_issue_action(self):
        self.log(next_action='', next_action_date='2026-11-21')
        self.assertEqual(self.doc.next_action, '')

    def test_resolution_cannot_silently_ignore_checked_follow_up(self):
        with self.assertRaises(ValueError):
            self.log(set_follow_up=True, next_action_date='2026-11-21', resolution_note='Done')
        self.assertFalse(self.doc.saved)

    def test_legacy_caller_retains_behavior(self):
        self.log(next_action='Visit', next_action_date='2026-11-21')
        self.assertEqual(self.doc.next_action_date, '2026-11-21')

    def test_link_requires_own_same_issue_comment_and_rejects_duplicate(self):
        for event in (None, SimpleNamespace(name='source', kind='Communication', actor='owner'), SimpleNamespace(name='source', kind='Comment', actor='other')):
            self.doc.timeline = [event] if event else []
            with self.assertRaises(ValueError): self.log(source_comment='source', set_follow_up=False)
        source=SimpleNamespace(name='source', kind='Comment', actor='owner', reply_to='root')
        self.doc.timeline=[source]
        self.log(source_comment='source', set_follow_up=False)
        self.assertIs(self.doc.timeline[0], source)
        self.assertEqual(self.doc.timeline[-1].source_comment, 'source')
        with self.assertRaises(ValueError): self.log(source_comment='source', set_follow_up=False)
