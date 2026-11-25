"""Offline tests for the generic sales bot. No Telegram or Gemini calls."""
import os
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "")
os.environ.setdefault("DEEPSEEK_MODEL", "deepseek-flash")

import bot  # noqa: E402


def test_parse_source():
    assert bot.parse_source("upwork") == "upwork"
    assert bot.parse_source("workana") == "workana"
    assert bot.parse_source("bad source!") == "direct"
    assert bot.parse_source("") == "direct"


def test_score_lead():
    assert bot.score_lead("whatsapp", "high", "asap", "a@b.com") == 10
    assert bot.score_lead("other", "unknown", "flex", "") == 1


def test_extract_contact():
    assert bot.extract_contact("mi correo es ana@example.com") == "ana@example.com"
    assert "300" in bot.extract_contact("escríbeme al +57 300 123 4567")


def test_packages():
    assert set(bot.PACKAGES) == {"esencial", "pro", "whatsapp", "custom"}
    assert "USD 150 + USD 19/mes" in bot.packages_text("es")
    assert "USD 150 + USD 19/mo" in bot.packages_text("en")


def test_lead_persists(tmp_path):
    bot.DB = tmp_path / "leads.db"
    bot.ADMIN = ""
    bot.init_db()
    user = bot.get_user(123, "tester", "Tester")
    lead_id = bot.save_lead(
        123,
        user,
        "Tester",
        "tester@example.com",
        "Quiero un bot para mi negocio",
        service="chatbot",
        package="Bot Esencial",
    )
    assert lead_id > 0
    row = bot.recent_leads(1)[0]
    assert row["package"] == "Bot Esencial"
    assert row["contact"] == "tester@example.com"
    assert "Bot Esencial" in bot.stats()
