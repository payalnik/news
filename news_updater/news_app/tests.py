"""Tests for news deduplication and the persist-after-send guarantee.

Run with the local .env workaround (see project memory). Note PYTHONPATH must be
/var/www/news (the repo root has its own __init__.py named news_updater, same as
the settings package, so the inner path causes import ambiguity), and pass the
test label as news_app.tests:

    SECRET_KEY=stub GOOGLE_API_KEY=stub DJANGO_SETTINGS_MODULE=news_updater.settings \
    PYTHONPATH=/var/www/news /var/www/news/venv/bin/python3 -c "
    import os; os.chdir('/var/www/news/news_updater')
    import dotenv; dotenv.load_dotenv=lambda *a,**k:False
    import sys; sys.argv=['manage.py','test','news_app.tests','-v','2']
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)"
"""
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

from news_app import dedup
from news_app.models import UserProfile, NewsSection, NewsItem


class DedupUnitTests(TestCase):
    """Pure-function tests for the dedup signals (no DB, no network)."""

    def test_normalize_url_collapses_variants(self):
        a = dedup.normalize_url('https://www.example.com/news/story-1/?utm_source=x&id=5')
        b = dedup.normalize_url('http://example.com/news/story-1?id=5')
        self.assertEqual(a, b)
        self.assertEqual(dedup.normalize_url(''), '')
        self.assertEqual(dedup.normalize_url(None), '')

    def test_content_hash_is_whitespace_and_case_insensitive(self):
        self.assertEqual(
            dedup.content_hash_for('Hello World', 'x'),
            dedup.content_hash_for('  hello   world ', 'x'),
        )
        self.assertNotEqual(
            dedup.content_hash_for('Hello World', 'x'),
            dedup.content_hash_for('Goodbye World', 'x'),
        )

    def test_cosine(self):
        self.assertAlmostEqual(dedup.cosine([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertAlmostEqual(dedup.cosine([1, 0], [0, 1]), 0.0)
        self.assertEqual(dedup.cosine([], [1]), 0.0)

    def test_lexical_exact_and_distinct(self):
        self.assertTrue(dedup.lexical_similar('Big News Today', 'd', 'big news today', 'd', 0.5))
        self.assertFalse(dedup.lexical_similar(
            'Local Bakery Wins Award', 'cake contest',
            'Stock Market Falls Sharply', 'dow jones', 0.5))

    def test_find_duplicate_by_shared_url(self):
        cand = {'headline': 'A', 'details': 'b', 'urls': {'cnn.com/x'},
                'hash': 'h1', 'embedding': None}
        prev = [{'headline': 'Completely Different', 'details': 'zzz',
                 'urls': {'cnn.com/x'}, 'hash': 'h2', 'embedding': None}]
        match, reason = dedup.find_duplicate(
            cand, prev, semantic_threshold=0.86, headline_threshold=0.5)
        self.assertIsNotNone(match)
        self.assertTrue(reason.startswith('shared-url'))

    def test_find_duplicate_by_semantic_embedding(self):
        cand = {'headline': 'Rewritten headline', 'details': 'x', 'urls': set(),
                'hash': 'h1', 'embedding': [1.0, 0.0, 0.0]}
        prev = [{'headline': 'Original wording', 'details': 'y', 'urls': set(),
                 'hash': 'h2', 'embedding': [0.99, 0.01, 0.0]}]
        match, reason = dedup.find_duplicate(
            cand, prev, semantic_threshold=0.86, headline_threshold=0.5)
        self.assertIsNotNone(match)
        self.assertTrue(reason.startswith('semantic'))

    def test_find_duplicate_returns_none_for_unrelated(self):
        cand = {'headline': 'Quarterly earnings beat estimates', 'details': 'x',
                'urls': {'a.com/1'}, 'hash': 'h1', 'embedding': [1.0, 0.0]}
        prev = [{'headline': 'Volcano erupts in Iceland', 'details': 'y',
                 'urls': {'b.com/2'}, 'hash': 'h2', 'embedding': [0.0, 1.0]}]
        match, _ = dedup.find_duplicate(
            cand, prev, semantic_threshold=0.86, headline_threshold=0.5)
        self.assertIsNone(match)


def _fake_gemini_client(items):
    """A mock google-genai client: generate_content returns `items` as JSON,
    embed_content returns benign zero vectors (so semantic dedup never fires)."""
    import json
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=json.dumps(items))

    def fake_embed(model, contents, config):
        n = len(contents) if isinstance(contents, list) else 1
        return MagicMock(embeddings=[MagicMock(values=[0.0] * 8) for _ in range(n)])

    client.models.embed_content.side_effect = fake_embed
    return client


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='test@example.com',
)
class SendNewsUpdateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', 'pw')
        self.profile = UserProfile.objects.create(user=self.user, email_verified=True)
        self.section = NewsSection.objects.create(
            user_profile=self.profile, name='World', sources='https://news.example.com',
            prompt='Summarize world news', order=0)

    def _run(self, gemini_items, email_should_fail=False):
        from news_app import tasks
        cm = patch.object(tasks, 'fetch_url_content', return_value='Some article body')
        cm2 = patch.object(tasks.genai, 'configure', return_value=None)
        cm3 = patch.object(tasks.google_genai, 'Client',
                           return_value=_fake_gemini_client(gemini_items))
        with cm, cm2, cm3:
            if email_should_fail:
                with patch.object(
                        tasks.EmailMultiAlternatives, 'send',
                        side_effect=Exception('SMTP down')):
                    return tasks.send_news_update(self.profile.id)
            return tasks.send_news_update(self.profile.id)

    def test_fresh_item_is_emailed_and_saved(self):
        result = self._run([{
            'headline': 'Volcano erupts in Iceland',
            'details': 'A volcano erupted near the capital.',
            'sources': [{'url': 'https://news.example.com/volcano', 'title': 'Example'}],
        }])
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(NewsItem.objects.filter(news_section=self.section).count(), 1)
        saved = NewsItem.objects.get(news_section=self.section)
        self.assertTrue(saved.content_hash)  # auto-filled on save

    def test_duplicate_by_shared_url_is_filtered(self):
        # An item citing this URL was already reported earlier.
        existing = NewsItem(
            user_profile=self.profile, news_section=self.section,
            headline='Old phrasing of the volcano story',
            details='Earlier coverage.')
        existing.set_sources_list([{'url': 'https://news.example.com/volcano', 'title': 'X'}])
        existing.save()

        result = self._run([{
            'headline': 'Totally different new headline about the eruption',
            'details': 'Reworded coverage of the same article.',
            'sources': [{'url': 'https://news.example.com/volcano?utm_source=tw', 'title': 'Y'}],
        }])
        self.assertTrue(result)
        # Still only the original item; the reworded duplicate was dropped.
        self.assertEqual(NewsItem.objects.filter(news_section=self.section).count(), 1)

    def test_items_not_persisted_when_email_fails(self):
        result = self._run([{
            'headline': 'Breaking news that should not persist',
            'details': 'Because the email send fails.',
            'sources': [{'url': 'https://news.example.com/x', 'title': 'X'}],
        }], email_should_fail=True)
        self.assertFalse(result)
        self.assertEqual(len(mail.outbox), 0)
        # Critical: nothing saved, so it will be regenerated (not silently lost).
        self.assertEqual(NewsItem.objects.filter(news_section=self.section).count(), 0)
