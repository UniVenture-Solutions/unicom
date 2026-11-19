import unittest
from types import SimpleNamespace
from unittest.mock import patch
import frappe
from unicom.www import unicom


class DateFormatContextTests(unittest.TestCase):
    def test_context_uses_only_system_setting_with_safe_fallback(self):
        for configured,expected in [('dd/mm/yyyy','dd/mm/yyyy'),('mm-dd-yyyy','mm-dd-yyyy'),(None,'yyyy-mm-dd'),('unexpected','yyyy-mm-dd')]:
            with self.subTest(configured=configured),patch.object(frappe,'get_roles',return_value=['Management']),patch.object(frappe,'session',SimpleNamespace(user='user')),patch.object(frappe,'db',SimpleNamespace(get_single_value=lambda doctype,field: configured)),patch.object(frappe,'sessions',SimpleNamespace(get_csrf_token=lambda: 'token'),create=True):
                context=SimpleNamespace()
                unicom.get_context(context)
                self.assertEqual(context.date_format,expected)
                self.assertEqual(context.no_cache,1)
