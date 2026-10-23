"""Robots and extraction regressions. These tests never contact providers."""
import unittest
from unittest.mock import patch
import scraper


class RobotsTests(unittest.TestCase):
    def client(self, responses):
        calls = []
        def read(url, timeout):
            calls.append(url)
            return responses[url]
        return scraper.RobotsClient(), calls, patch.object(scraper, 'read_http', side_effect=read)

    def test_disallowed_page_is_not_requested(self):
        c, calls, mocked = self.client({'https://host.test/robots.txt': (200, b'User-agent: *\nDisallow: /private', {})})
        with mocked:
            self.assertEqual(c.fetch('https://host.test/private/pricing'), (0, None))
        self.assertEqual(calls, ['https://host.test/robots.txt'])
        self.assertEqual(c.last_reason, 'robots_disallowed')

    def test_redirect_target_checked_before_request(self):
        c, calls, mocked = self.client({
            'https://host.test/robots.txt': (404, None, {}),
            'https://host.test/pricing': (302, None, {'Location': 'https://other.test/pricing'}),
            'https://other.test/robots.txt': (200, b'User-agent: *\nDisallow: /', {}),
        })
        with mocked:
            self.assertEqual(c.fetch('https://host.test/pricing'), (0, None))
        self.assertNotIn('https://other.test/pricing', calls)

    def test_missing_rules_allow_and_cache(self):
        c, calls, mocked = self.client({'https://host.test/robots.txt': (404, None, {}),
                                       'https://host.test/pricing': (200, b'$5/month', {})})
        with mocked:
            self.assertEqual(c.fetch('https://host.test/pricing'), (200, b'$5/month'))
            c.fetch('https://host.test/pricing')
        self.assertEqual(calls.count('https://host.test/robots.txt'), 1)

    def test_server_denial_or_challenge_is_fail_closed(self):
        for response in [(403, None, {}), (429, None, {}), (503, None, {}), (0, None, {}),
                         (200, b'<html>Challenge</html>', {})]:
            with self.subTest(response=response):
                c, calls, mocked = self.client({'https://host.test/robots.txt': response})
                with mocked:
                    self.assertEqual(c.fetch('https://host.test/pricing'), (0, None))
                self.assertEqual(len(calls), 1)

    def test_declared_agent_specific_rules_and_crawl_delay(self):
        c, calls, mocked = self.client({'https://host.test/robots.txt':
            (200, b'User-agent: vps-deals-bot\nAllow: /pricing\nCrawl-delay: 3\n\nUser-agent: *\nDisallow: /', {}),
            'https://host.test/pricing': (200, b'price', {})})
        with mocked, patch.object(scraper.time, 'monotonic', return_value=10), patch.object(scraper.time, 'sleep') as sleep:
            c.fetch('https://host.test/pricing')
            c.fetch('https://host.test/pricing')
            sleep.assert_called_once_with(3)

    def test_allowed_same_site_redirect(self):
        c, calls, mocked = self.client({'https://host.test/robots.txt': (200, b'User-agent: *\nAllow: /', {}),
            'https://host.test/pricing': (301, None, {'Location': '/plans'}),
            'https://host.test/plans': (200, b'plans', {})})
        with mocked:
            self.assertEqual(c.fetch('https://host.test/pricing'), (200, b'plans'))
        self.assertEqual(calls.count('https://host.test/robots.txt'), 1)

    def test_longest_path_wins_not_first_rule(self):
        policy = scraper.RobotsRules('User-agent: *\nAllow: /\nDisallow: /private\nAllow: /private/public')
        self.assertFalse(policy.allows('https://host.test/private/secret'))
        self.assertTrue(policy.allows('https://host.test/private/public/info'))

    def test_wildcard_end_anchor_and_allow_tie(self):
        policy = scraper.RobotsRules('User-agent: *\nDisallow: /*.json$\nAllow: /public.json$\nDisallow: /same\nAllow: /same')
        self.assertFalse(policy.allows('https://host.test/private.json'))
        self.assertTrue(policy.allows('https://host.test/private.json/info'))
        self.assertTrue(policy.allows('https://host.test/public.json'))
        self.assertTrue(policy.allows('https://host.test/same'))

    def test_matching_agent_groups_are_combined(self):
        policy = scraper.RobotsRules('User-agent: vps-deals-bot\nDisallow: /one\nUser-agent: vps-deals-bot\nDisallow: /two')
        self.assertFalse(policy.allows('https://host.test/one'))
        self.assertFalse(policy.allows('https://host.test/two'))


class ExtractionTests(unittest.TestCase):
    def test_period_must_belong_to_amount(self):
        html = '<h2>VPS</h2><p>Free $100 credit. Compute $6/month, yearly €60/year, hourly $0.01/hour. Storage $0.10/GB/month.</p>'
        deals = scraper.extract_offers(html, 'https://host.test/plans', 'Host')
        self.assertEqual([(d['price'], d['currency'], d['billing_period']) for d in deals],
                         [(6, 'USD', 'month'), (60, 'EUR', 'year'), (0.01, 'USD', 'hour')])
        self.assertTrue(all(d['price_evidence'] for d in deals))

    def test_nearby_promotional_language_is_not_price_evidence(self):
        self.assertEqual(scraper.extract_offers('Save $50 on a promo. Monthly VPS plans are available.', 'https://host.test/', 'Host'), [])


if __name__ == '__main__':
    unittest.main()
