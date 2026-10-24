"""Publication date, duplicate, review, and embargo checks; never posts online."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import editorial
import build


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vps-editorial-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(editorial.ROOT / '.ilang', self.root / '.ilang')
        shutil.copytree(editorial.ROOT / 'content', self.root / 'content')
        shutil.copytree(editorial.ROOT / 'static/articles', self.root / 'static/articles')
        (self.root / 'articles').mkdir()
        self.first = editorial.calendar(self.root)[0][0]

    def at(self, value):
        return datetime.fromisoformat(value)

    def test_all_reviewed_articles_ready_and_non_duplicate(self):
        entries = editorial.validate()
        self.assertGreaterEqual(len(entries), 14)
        self.assertEqual(entries[0]['date'], '2026-10-24')
        self.assertGreaterEqual(entries[-1]['date'], '2026-11-06')

    def test_missing_or_changed_image_blocks_release(self):
        image = self.root / 'static/articles' / (self.first['slug'] + '.png')
        original = image.read_bytes()
        image.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing reviewed article image'):
            editorial.validate(self.root)
        image.write_bytes(original + b'changed')
        with self.assertRaisesRegex(ValueError, 'Reviewed image changed'):
            editorial.validate(self.root)
        self.assertEqual(list((self.root / 'articles').glob('*')), [])

    def test_image_requires_alt_and_dimensions(self):
        source = self.root / 'content/queue' / (self.first['slug'] + '.html')
        _, body = editorial.article(source)
        import re
        for changed in (re.sub(r'alt="[^"]*"', 'alt=""', body), body.replace('width="1200"', 'width="600"')):
            with self.assertRaisesRegex(ValueError, 'alt|dimensions'):
                editorial.checked_image(self.first, changed, self.root)

    def test_utc_midnight_is_shanghai_eight(self):
        before = editorial.release(self.root, self.at('2026-10-23T23:59:59+00:00'))
        self.assertEqual(before['status'], 'not_due')
        self.assertEqual(list((self.root / 'articles').glob('*')), [])
        due = editorial.release(self.root, self.at('2026-10-24T00:00:00+00:00'))
        self.assertEqual(due['status'], 'published')
        self.assertEqual(due['date'], '2026-10-24')

    def test_release_idempotent_and_only_one_file(self):
        at = self.at('2026-10-24T08:00:00+08:00')
        self.assertEqual(editorial.release(self.root, at)['status'], 'published')
        self.assertEqual(editorial.release(self.root, at)['status'], 'already_published')
        self.assertEqual(len(list((self.root / 'articles').glob('*.html'))), 1)
        self.assertTrue((self.root / 'content/queue' / (self.first['slug']+'.html')).exists())

    def test_dry_run_never_writes(self):
        self.assertEqual(editorial.release(self.root, self.at('2026-10-24T08:00:00+08:00'), True)['status'], 'dry_run')
        self.assertEqual(list((self.root / 'articles').glob('*')), [])

    def test_check_of_an_existing_article_cannot_trigger_deployment(self):
        at = self.at('2026-10-24T08:00:00+08:00')
        editorial.release(self.root, at)
        before = {p.name:p.read_bytes() for p in (self.root/'articles').glob('*')}
        self.assertEqual(editorial.release(self.root, at, True)['status'], 'dry_run')
        self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root/'articles').glob('*')})

    def test_changed_copy_is_not_overwritten(self):
        source = self.root / 'content/queue' / (self.first['slug']+'.html')
        target = self.root / 'articles' / source.name
        target.write_text(source.read_text()+'\n<p>Unreviewed change</p>')
        original = target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Reviewed content changed'):
            editorial.release(self.root, self.at('2026-10-24T08:00:00+08:00'))
        self.assertEqual(target.read_bytes(), original)

    def test_another_same_day_article_blocks_double_publication(self):
        source = self.root / 'content/queue' / (self.first['slug']+'.html')
        (self.root / 'articles/other-post.html').write_text(source.read_text().replace('gap: ' + self.first['gap'], 'gap: unrelated-search-intent'))
        with self.assertRaisesRegex(ValueError, 'Another article already exists'):
            editorial.release(self.root, self.at('2026-10-24T08:00:00+08:00'))

    def test_queue_exhaustion_does_not_generate_filler(self):
        with self.assertRaisesRegex(ValueError, 'No reviewed article'):
            last = editorial.calendar(self.root)[0][-1]['date']
            exhausted = self.at(last + 'T08:00:00+08:00') + timedelta(days=1)
            editorial.release(self.root, exhausted)
        self.assertEqual(list((self.root / 'articles').glob('*')), [])

    def test_early_copy_is_hidden_from_site_and_article_index(self):
        source = self.root / 'content/queue' / (self.first['slug']+'.html')
        (self.root / 'articles' / source.name).write_bytes(source.read_bytes())
        meta, _ = editorial.article(source)
        self.assertFalse(editorial.visible(self.root/'articles'/source.name, meta, self.root, self.at('2026-10-24T07:59:59+08:00')))
        with patch.object(build, 'ROOT', self.root), patch.object(editorial, 'now', return_value=self.at('2026-10-24T08:00:00+08:00')):
            self.assertEqual([a['slug'] for a in build.load_articles()], [self.first['slug']])

    def test_due_article_renders_and_enters_sitemap_without_early_publication(self):
        at = self.at('2026-10-24T08:00:00+08:00')
        editorial.release(self.root, at)
        output = self.root/'rendered-site'
        history = self.root/'history.json'
        shutil.copy2(build.HISTORY_JSON, history)
        with patch.object(build, 'ROOT', self.root), patch.object(build, 'SITE', output), patch.object(build, 'HISTORY_JSON', history), patch.object(editorial, 'now', return_value=at):
            with contextlib.redirect_stdout(io.StringIO()):
                build.main()
        url = 'https://www.vpsdealswire.com/articles/' + self.first['slug'] + '/'
        page = (output/'articles'/self.first['slug']/'index.html').read_text()
        self.assertIn(url, page)
        self.assertIn(url, (output/'sitemap.xml').read_text())
        self.assertEqual(page.count('<h1>'), 1)
        image_name = self.first['slug'] + '.png'
        self.assertIn('/articles/' + image_name, page)
        self.assertIn('"image": "https://www.vpsdealswire.com/articles/' + image_name + '"', page)
        self.assertEqual((output/'articles'/image_name).read_bytes(), (self.root/'static/articles'/image_name).read_bytes())
        self.assertIn('/articles/' + image_name, (output/'articles/index.html').read_text())
        self.assertNotIn('2026-10-25', (output/'sitemap.xml').read_text())

    def test_new_unscheduled_old_platform_post_is_not_auto_published(self):
        source = self.root / 'content/queue' / (self.first['slug']+'.html')
        unknown = self.root/'articles/unlisted-post.html'
        unknown.write_bytes(source.read_bytes())
        meta, _ = editorial.article(unknown)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(editorial.visible(unknown, meta, self.root, self.at('2026-10-24T09:00:00+08:00')))

    def test_calendar_rejects_duplicate_topic_and_date(self):
        path = self.root/'content/calendar.json'
        doc = json.loads(path.read_text())
        doc['entries'][1]['date'] = doc['entries'][0]['date']
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, 'Duplicate calendar'):
            editorial.calendar(self.root)

    def test_workflow_clock_and_price_update_have_separate_slots(self):
        root = editorial.ROOT
        workflow = (root/'.github/workflows/daily-article.yml').read_text()
        self.assertIn("cron: '0 0 * * *'", workflow)
        self.assertIn('vps-pages-production', workflow)
        self.assertIn('20 */6 * * *', (root/'.github/workflows/update.yml').read_text())


if __name__ == '__main__':
    unittest.main()
