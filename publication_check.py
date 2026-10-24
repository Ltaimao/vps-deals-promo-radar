"""Verify a reviewed article on the public origin; no publishing side effects."""
import argparse
from html.parser import HTMLParser
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

ORIGIN = 'https://www.vpsdealswire.com'


class ArticleHead(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonicals = []
        self.h1_count = 0
        self.noindex = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and 'canonical' in attrs.get('rel', '').split():
            self.canonicals.append(attrs.get('href'))
        if tag == 'h1':
            self.h1_count += 1
        if tag == 'meta' and attrs.get('name', '').lower() in ('robots', 'googlebot'):
            self.noindex |= bool({'noindex', 'none'} & set(re.split(r'[,\s]+', attrs.get('content', '').lower())))


def fetch(url):
    request = urllib.request.Request(url, headers={
        'User-Agent': 'VPS-Deals-Wire-publication-check', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('Expected HTTP 200 at ' + url)
        if re.search(r'\b(noindex|none)\b', response.headers.get('X-Robots-Tag', ''), re.I):
            raise ValueError('Public response blocks indexing: ' + url)
        return response.read().decode()


def verify(slug):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise ValueError('Invalid article slug')
    url = ORIGIN + '/articles/' + slug + '/'
    head = ArticleHead()
    head.feed(fetch(url))
    if head.canonicals != [url] or head.h1_count != 1 or head.noindex:
        raise ValueError('Article canonical, H1, or indexing metadata is invalid: ' + url)
    sitemap = ET.fromstring(fetch(ORIGIN + '/sitemap.xml'))
    locations = {node.text for node in sitemap.iter() if node.tag.rsplit('}', 1)[-1] == 'loc'}
    if url not in locations:
        raise ValueError('Article missing from public sitemap: ' + url)
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slug')
    parser.add_argument('--attempts', type=int, choices=range(1, 7), default=1)
    args = parser.parse_args()
    for attempt in range(args.attempts):
        try:
            print('Verified live article and sitemap:', verify(args.slug))
            return
        except (urllib.error.URLError, ValueError, ET.ParseError):
            if attempt == args.attempts - 1:
                raise
            time.sleep(5)


if __name__ == '__main__':
    main()
