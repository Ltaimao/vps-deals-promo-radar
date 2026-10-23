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

    def test_disclosures_follow_current_configuration(self):
        text = (self.site / 'privacy/index.html').read_text()
        cfg = build.load_cfg()
        for p in build.load_data()['providers']:
            if build.provider_affiliate(p, cfg):
                self.assertIn(p['name'], text)
        self.assertIn('Bitlaunch', text)
        self.assertIn('Hostinger', text)
        self.assertIn('InterServer', text)
        self.assertNotIn('seven provider', text)
        self.assertNotIn('no affiliate tracking', (self.site / 'methodology/index.html').read_text())

    def test_non_usd_machine_data_is_not_labeled_dollars(self):
        data = json.loads((self.site / 'data/deals.json').read_text())
        for offer in data['offers']:
            if offer['currency'] != 'USD' or offer['billing_period'] != 'month':
                self.assertIsNone(offer['price_usd'])
        self.assertEqual(build.price_ranges([{'price': 5, 'currency': 'EUR'}, {'price': 10, 'currency': 'USD'}]),
                         '€5.00 – €5.00 EUR; $10.00 – $10.00 USD')

    def test_directory_schema_and_updated_sitemap(self):
        text = (self.site / 'articles/index.html').read_text()
        self.assertIn('"@type": "CollectionPage"', text)
        import xml.etree.ElementTree as ET
        root = ET.fromstring((self.site / 'sitemap.xml').read_text())
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        mods = {row.find('s:loc', ns).text: row.find('s:lastmod', ns).text for row in root}
        self.assertEqual(mods['https://www.vpsdealswire.com/articles/cheap-vps-sizing-guide/'], '2026-09-29')

    def test_article_metadata_is_concise(self):
        for a in build.load_articles():
            with self.subTest(article=a['slug']):
                self.assertLessEqual(len(a['title']), 60)
                self.assertLessEqual(len(a['description']), 160)

    def test_empty_listing_still_has_valid_schema(self):
        graph = json.loads(build.jsonld_with_crumbs('', [('/', 'Home')], 'https://host.test'))
        self.assertEqual(graph['@graph'][0]['@type'], 'BreadcrumbList')

    def test_expired_offers_excluded_from_service_schema(self):
        data = json.loads(build.jsonld_service({'name': 'Host', 'url': 'https://host.test'},
            [{'price': 5, 'currency': 'USD', 'valid_until': '2000-01-01'}], 'https://host.test'))
        self.assertEqual(data['offers'], [])

    def test_ilang_provider_change_affects_rendered_page(self):
        cfg = build.load_cfg()
        cfg['PROVIDERS'][0]['url'] = 'https://www.hetzner.com/?configuration-check=1'
        variant = Path(self.temp.name) / 'variant'
        history = Path(self.temp.name) / 'variant-history.json'
        shutil.copy2(build.HISTORY_JSON, history)
        with patch.object(build, 'SITE', variant), patch.object(build, 'HISTORY_JSON', history), patch.object(build, 'load_cfg', return_value=cfg):
            with contextlib.redirect_stdout(io.StringIO()):
                build.main()
        self.assertIn('https://www.hetzner.com/?configuration-check=1', (variant / 'providers/hetzner-cloud/index.html').read_text())

    def test_unknown_and_hourly_prices_not_advertised_as_monthly_offers(self):
        priced = [{'price': 0.01, 'currency': 'USD', 'billing_period': 'hour'},
                  {'price': 5, 'currency': 'EUR'},
                  {'price': 8, 'currency': 'EUR', 'billing_period': 'month'}]
        data = json.loads(build.jsonld_service({'name': 'Host', 'url': 'https://host.test'}, priced, 'https://host.test'))
        self.assertEqual([(d['price'], d['priceCurrency']) for d in data['offers']], [(8, 'EUR')])

    def test_monthly_history_keeps_legacy_points_and_currency_separate(self):
        history = {'deal_series': {}, 'provider_min': {}}
        legacy = {'price': 3, 'currency': 'USD', 'provider_slug': 'host'}
        build._append_points(history, {'id': ('one', 3, legacy)}, 'one')
        self.assertNotIn('monthly_points_by_currency', history['deal_series']['id'])
        monthly = dict(legacy, billing_period='month')
        build._append_points(history, {'id': ('two', 5, monthly)}, 'two')
        build._append_points(history, {'id': ('two', 5, monthly)}, 'two')
        self.assertEqual(history['deal_series']['id']['monthly_points_by_currency']['USD'], [['two', 5]])
        self.assertEqual(history['deal_series']['id']['points'], [['one', 3], ['two', 5]])


if __name__ == '__main__':
    unittest.main()
