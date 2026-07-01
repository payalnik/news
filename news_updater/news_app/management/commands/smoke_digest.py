"""Live smoke test for the OpenRouter (DeepSeek) text-generation path.

Unlike the unit tests, this calls the REAL provider with the REAL key, so it's
the only thing that actually verifies the model id resolves and returns a
parseable JSON array. Run it by hand after any provider/model change:

    python manage.py smoke_digest

It does NOT touch the database or send email — it just exercises llm.chat()
and reports what came back.
"""
import json

from django.core.management.base import BaseCommand
from django.conf import settings

from news_app import llm


SMOKE_PROMPT = """Return ONLY a JSON array of exactly 2 fictional news items.
Each item must be an object with keys "headline" (string), "details" (string),
and "sources" (array of objects with "url" and "title"). No prose, no markdown
fences — just the JSON array."""


class Command(BaseCommand):
    help = "Live smoke test of the OpenRouter/DeepSeek summarization path."

    def add_arguments(self, parser):
        parser.add_argument('--prompt', default=SMOKE_PROMPT,
                            help='Override the prompt sent to the model.')

    def handle(self, *args, **opts):
        model = getattr(settings, 'OPENROUTER_MODEL', '(unset)')
        self.stdout.write(f"Model: {model}")

        if not llm.available():
            self.stderr.write(self.style.ERROR(
                "OPENROUTER_API_KEY is not set — cannot run a live test. "
                "Put the real key in .env and retry."))
            return

        self.stdout.write("Calling OpenRouter...")
        try:
            raw = llm.chat(opts['prompt'])
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"API call FAILED: {type(e).__name__}: {e}"))
            return

        self.stdout.write(self.style.SUCCESS("API call succeeded."))
        self.stdout.write(f"--- raw response ---\n{raw}\n--------------------")

        try:
            parsed = json.loads(raw)
            self.stdout.write(self.style.SUCCESS(
                f"JSON parsed OK: {len(parsed)} item(s)."))
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.WARNING(
                f"Response did NOT parse as JSON directly: {e}. "
                "The pipeline's regex fallback may still recover it, but the "
                "model is not returning clean JSON."))
