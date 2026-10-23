#!/usr/bin/env python3
"""Deterministic, reviewed-article queue. No AI API, scraping, or credentials."""
import argparse
import hashlib
import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from scraper import parse_ilang

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(ZoneInfo('Asia/Shanghai'))


def settings(root=ROOT):
    cfg = parse_ilang(root / '.ilang/site.ilang')['RENDER']
    return (root / cfg['editorial_calendar'], ZoneInfo(cfg['editorial_timezone']),
            time.fromisoformat(cfg['editorial_publish_time']))


def calendar(root=ROOT):
    path, timezone, publish_time = settings(root)
    doc = json.loads(path.read_text())
    if doc.get('timezone') != timezone.key or doc.get('publish_time') != publish_time.strftime('%H:%M'):
        raise ValueError('Calendar time differs from I-Lang publishing settings')
    dates, slugs, gaps = set(), set(), set()
    for entry in doc['entries']:
        day = datetime.strptime(entry['date'], '%Y-%m-%d').date()
        slug = entry['slug']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
            raise ValueError('Invalid calendar slug: ' + slug)
        if day in dates or slug in slugs or entry['gap'] in gaps:
            raise ValueError('Duplicate calendar date, slug, or search intent')
        if entry['status'] != 'ready' or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']):
            raise ValueError('Calendar requires a reviewed ready article and checksum')
        dates.add(day); slugs.add(slug); gaps.add(entry['gap'])
    if not doc['entries']:
        raise ValueError('Empty editorial calendar')
    ordered = sorted(dates)
    if ordered != [ordered[0] + timedelta(days=i) for i in range(len(ordered))]:
        raise ValueError('Daily calendar contains a missing day')
    return sorted(doc['entries'], key=lambda e: e['date']), timezone, publish_time


def article(path):
    text = path.read_text()
    head, sep, body = text.partition('\n\n')
    meta = dict(line.split(': ', 1) for line in head.splitlines() if ': ' in line)
    if not sep or not body.strip() or any(not meta.get(k) for k in ('title','date','description','gap')):
        raise ValueError('Incomplete article: ' + path.name)
    return meta, body


def checked_source(entry, root=ROOT):
    published = root / 'articles' / (entry['slug'] + '.html')
    queued = root / 'content/queue' / (entry['slug'] + '.html')
    path = published if published.exists() else queued
    if not path.is_file():
        raise ValueError('Missing reviewed article: ' + entry['slug'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Reviewed content changed; review and update checksum: ' + entry['slug'])
    meta, body = article(path)
    if meta['date'] != entry['date'] or meta['gap'] != entry['gap']:
        raise ValueError('Article date/intent does not match calendar: ' + entry['slug'])
    if len(meta['title']) > 60 or len(meta['description']) > 160:
        raise ValueError('Overlong search metadata: ' + entry['slug'])
    plain = re.sub(r'<[^>]+>', ' ', body)
    if len(plain.split()) < 350 or len(re.findall(r'<h1(?:\s[^>]*)?>',body)) != 1:
        raise ValueError('Article requires a complete original guide and one H1: ' + entry['slug'])
    if len(re.findall(r'href="/(?:articles|providers|compare|methodology)[^\"]*"',body)) < 2:
        raise ValueError('Article lacks relevant site links: ' + entry['slug'])
    return path


def validate(root=ROOT):
    entries, _, _ = calendar(root)
    historical_gaps = {}
    for path in (root / 'articles').glob('*.html'):
        meta, _ = article(path)
        historical_gaps.setdefault(meta['gap'], set()).add(path.stem)
    for entry in entries:
        checked_source(entry, root)
        if historical_gaps.get(entry['gap'], set()) - {entry['slug']}:
            raise ValueError('Search intent already used by another article: ' + entry['gap'])
    return entries


def visible(path, meta, root=ROOT, at=None):
    """Old published URLs stay available; new dates require a reviewed slot + embargo."""
    entries, tz, publish_time = calendar(root)
    local = (at or now()).astimezone(tz)
    release_at = datetime.combine(datetime.strptime(meta['date'],'%Y-%m-%d').date(), publish_time, tz)
    if meta['date'] < entries[0]['date']:
        return release_at.date() <= local.date()
    entry = next((e for e in entries if e['slug'] == path.stem and e['date'] == meta['date']), None)
    if entry is None:
        print('Unscheduled article excluded from publication: ' + path.name)
        return False
    checked_source(entry, root)
    return local >= release_at


def release(root=ROOT, at=None, dry_run=False):
    entries = validate(root)
    _, tz, publish_time = settings(root)
    local = (at or now()).astimezone(tz)
    if local.time().replace(tzinfo=None) < publish_time:
        return {'status':'not_due', 'date':local.date().isoformat()}
    day = local.date().isoformat()
    entry = next((e for e in entries if e['date'] == day), None)
    if entry is None:
        if day < entries[0]['date']:
            return {'status':'not_due','first_release':entries[0]['date']}
        raise ValueError('No reviewed article for '+day+'; replenish/reschedule the queue. Nothing published.')
    target = root / 'articles' / (entry['slug']+'.html')
    if target.exists():
        checked_source(entry, root)
        return {'status':'already_published','date':day,'slug':entry['slug']}
    for path in (root / 'articles').glob('*.html'):
        meta, _ = article(path)
        if meta['date'] == day:
            raise ValueError('Another article already exists for '+day+'; no duplicate publication')
    source = checked_source(entry, root)
    if not dry_run:
        target.parent.mkdir(exist_ok=True)
        with target.open('xb') as output:
            output.write(source.read_bytes())
    return {'status':'dry_run' if dry_run else 'published','date':day,'slug':entry['slug']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('validate','release'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--at', help='Offset-aware time for dry-run verification only')
    args = parser.parse_args()
    if args.at and not args.dry_run:
        parser.error('--at is allowed only with --dry-run; production dates cannot be forged')
    at = datetime.fromisoformat(args.at) if args.at else None
    if at and at.tzinfo is None:
        parser.error('--at requires an explicit timezone offset')
    if args.operation == 'validate':
        entries = validate()
        print(json.dumps({'ready':len(entries),'first':entries[0]['date'],'last':entries[-1]['date']}))
    else:
        print(json.dumps(release(at=at,dry_run=args.dry_run)))


if __name__ == '__main__':
    main()
