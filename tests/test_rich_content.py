import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from PIL import Image
from unicom import api


class RichContentTests(unittest.TestCase):
    def setUp(self):
        self.doc = SimpleNamespace(name='issue', attachments=[SimpleNamespace(name='image', storage_key='a' * 64)])
        self.translate = patch.object(api, '_', side_effect=lambda message: message)
        self.translate.start()
        self.addCleanup(self.translate.stop)
        self.path = patch.object(api, '_attachment_path', return_value='/test/image')
        self.path.start()
        self.addCleanup(self.path.stop)
        self.throw = patch.object(frappe, 'throw', side_effect=lambda message, *args: (_ for _ in ()).throw(ValueError(message)))
        self.throw.start()
        self.addCleanup(self.throw.stop)
        self.data = io.BytesIO()
        Image.new('RGB', (2, 2), 'red').save(self.data, format='PNG')

    def test_formatting_and_issue_image_survive(self):
        url = api._image_url(self.doc, 'image')
        with patch('builtins.open', return_value=io.BytesIO(self.data.getvalue())):
            result = api._rich_html(f'<p><strong>Bold</strong><span style="color: red">Red</span></p><ul><li>One</li></ul><img src="{url.replace("&", "&amp;")}">', self.doc)
        self.assertIn('<strong>Bold</strong>', result)
        self.assertIn('color:red', result)
        self.assertIn('<li>One</li>', result)
        self.assertIn('inline_image?', result)

    def test_forged_external_data_and_cross_issue_images_rejected(self):
        for src in ('https://evil.example/a.png', 'data:image/png;base64,AA==', api._image_url(SimpleNamespace(name='other'), 'image'), api._image_url(self.doc, 'other')):
            with self.subTest(src=src), self.assertRaises(ValueError):
                api._rich_html(f'<img src="{src.replace("&", "&amp;")}">', self.doc)

    def test_other_resource_loading_content_is_rejected(self):
        for body in ('<video poster="https://evil.example/a.png"></video>', '<picture><source srcset="https://evil.example/a.png"></picture>', '<p style="background-image:url(https://evil.example/a)">x</p>'):
            with self.subTest(body=body), self.assertRaises(ValueError): api._rich_html(body, self.doc)

    def test_unchanged_legacy_description_does_not_block_other_edits(self):
        doc = SimpleNamespace(description='<img src="https://old.example/image.png">', status='Open', flags=SimpleNamespace())
        doc.set = lambda key, value: setattr(doc, key, value)
        doc.save = lambda **kwargs: None
        with patch.object(api, '_doc', return_value=doc), patch.object(api, '_snapshot', return_value={'status': 'Open'}), patch.object(api, '_validate'), patch.object(api, '_event'), patch.object(api, '_output', return_value=doc):
            api.update_issue('issue', {'description': doc.description, 'title': 'New title'})
        self.assertEqual(doc.title, 'New title')
        self.assertIn('old.example', doc.description)

    def test_image_decoder_rejects_nonimage_and_reencodes_polyglot(self):
        with self.assertRaises(ValueError): api._decoded_image(b'<svg onload="alert(1)"></svg>')
        output = api._decoded_image(self.data.getvalue() + b'<script>alert(1)</script>')
        self.assertNotIn(b'<script>', output)
        self.assertEqual(Image.open(io.BytesIO(output)).format, 'PNG')

    def test_inline_image_checks_issue_access_and_has_safe_headers(self):
        with patch.object(api, '_doc', return_value=self.doc) as get_doc, patch('builtins.open', return_value=io.BytesIO(self.data.getvalue())):
            response = api.inline_image('issue', 'image')
        get_doc.assert_called_once_with('issue')
        self.assertEqual(response.content_type, 'image/png')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        with patch.object(api, '_doc', side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError): api.inline_image('issue', 'image')
