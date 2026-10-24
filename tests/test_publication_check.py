"""A committed article is not considered live until public SEO checks pass."""
import unittest
from unittest.mock import patch
import urllib.error
import publication_check as check


class PublicationCheckTests(unittest.TestCase):
    slug = 'shared-vcpu-vps-fair-use'

    def setUp(self):
        self.url = check.ORIGIN + '/articles/' + self.slug + '/'
        self.page = '<link rel="canonical" href="' + self.url + '"><h1>Shared vCPU</h1>'
        self.sitemap = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>' + self.url + '</loc></url></urlset>'

    def verify(self, page=None, sitemap=None):
        with patch.object(check, 'fetch', side_effect=[self.page if page is None else page, self.sitemap if sitemap is None else sitemap]):
            return check.verify(self.slug)

    def test_live_page_and_sitemap(self):
        self.assertEqual(self.verify(), self.url)

    def test_wrong_canonical_even_when_url_appears_in_body(self):
        with self.assertRaisesRegex(ValueError, 'canonical'):
            self.verify('<link rel="canonical" href="https://example.com/"><h1>Guide</h1>' + self.url)

    def test_noindex_is_not_success(self):
        with self.assertRaisesRegex(ValueError, 'indexing'):
            self.verify(self.page + '<meta name="robots" content="follow, noindex">')

    def test_missing_sitemap_entry_is_not_success(self):
        with self.assertRaisesRegex(ValueError, 'sitemap'):
            self.verify(sitemap='<urlset/>')

    def test_missing_public_page_is_not_success(self):
        with patch.object(check, 'fetch', side_effect=urllib.error.HTTPError(self.url, 404, 'Not found', {}, None)):
            with self.assertRaises(urllib.error.HTTPError):
                check.verify(self.slug)

    def test_duplicate_h1_is_not_success(self):
        with self.assertRaisesRegex(ValueError, 'H1'):
            self.verify(self.page + '<h1>Second heading</h1>')
