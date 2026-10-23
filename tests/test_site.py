"""Integration checks for the generated site; uses only the Python standard library.

Run: python3 -m unittest discover -s tests -v
Build outputs and price history are redirected to a temporary directory.
"""
import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import build


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.headings = 0
        self.ids = []
        self.links = []
        self.cards = []
        self.sponsored = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1':
            self.headings += 1
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            self.links.append(attrs.get('href', ''))
            classes = attrs.get('class', '').split()
            if 'deal-card' in classes:
                self.cards.append(attrs)
            if 'sponsored-card' in classes:
                self.sponsored.append(attrs)


class GeneratedSiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='vps-site-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.site = Path(cls.temp.name) / 'site'
        history = Path(cls.temp.name) / 'history.json'
        shutil.copy2(build.HISTORY_JSON, history)
        with patch.object(build, 'SITE', cls.site), patch.object(build, 'HISTORY_JSON', history):
            with contextlib.redirect_stdout(io.StringIO()):
                build.main()

    def test_all_pages_have_shared_accessible_layout(self):
        pages = list(self.site.rglob('*.html'))
        self.assertGreaterEqual(len(pages), 69)
        for path in pages:
            # Static ownership verification and extension policy files aren't templates.
            text = path.read_text()
            if 'primary-navigation' not in text:
                continue
            with self.subTest(page=str(path.relative_to(self.site))):
                doc = Document(text)
                self.assertEqual(doc.headings, 1)
                self.assertEqual(len(doc.ids), len(set(doc.ids)))
                self.assertIn('href="#main-content"', text)
                self.assertIn('aria-controls="primary-navigation"', text)
                self.assertNotRegex(text, r'\{\{[A-Z_]+\}\}')
                for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
                    json.loads(raw)

    def test_navigation_current_pages(self):
        for path in ['', 'compare', 'articles', 'black-friday', 'methodology']:
            text = (self.site / path / 'index.html').read_text()
            href = '/' + path + '/' if path else '/'
            self.assertIn('href="' + href + '" class="active" aria-current="page"', text)

    def test_deal_currency_metadata_and_sponsored_links(self):
        text = (self.site / 'index.html').read_text()
        doc = Document(text)
        data = json.loads(build.DATA.read_text())
        self.assertEqual(len(doc.cards), len(data['deals']))
        for card, deal in zip(doc.cards, data['deals']):
            self.assertEqual(card['data-currency'], deal['currency'])
            self.assertEqual(card['href'], '/providers/' + deal['provider_slug'] + '/')
        self.assertEqual(len(doc.sponsored), 3)
        cfg = build.load_cfg()
        expected = {a['url'] for a in cfg['AFFILIATE'] if a['name'] in ('Contabo VPS', 'Namecheap VPS', 'Bitlaunch')}
        self.assertEqual({a['href'] for a in doc.sponsored}, expected)
        for a in doc.sponsored:
            self.assertEqual(set(a['rel'].split()), {'sponsored', 'nofollow', 'noopener'})
        usd = min(d['price'] for d in data['deals'] if d.get('price') and d['currency'] == 'USD')
        self.assertIn(build.money(usd, 'USD'), text)

    def test_guide_cards_and_outline_destinations(self):
        index = Document((self.site / 'articles/index.html').read_text())
        self.assertEqual(len([a for a in index.links if a.startswith('/articles/') and a != '/articles/']), len(build.load_articles()))
        for article in build.load_articles():
            doc = Document((self.site / 'articles' / article['slug'] / 'index.html').read_text())
            for link in doc.links:
                if link.startswith('#guide-section-'):
                    self.assertIn(link[1:], doc.ids)


if __name__ == '__main__':
    unittest.main()
