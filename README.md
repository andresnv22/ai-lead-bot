# Andrés AI — Generic AI Sales Bot for Telegram

An open-source demo of the Telegram bot that sells Andrés's services: it answers questions, shows fixed packages, qualifies leads and stores them in SQLite with source tracking.

**Live demo:** https://t.me/andresnv_ai_bot

![Andrés AI](avatar.png)

I built this bot as a sales tool and as a portfolio piece. It works for any business: clinics, bakeries, barbershops, e-commerce, real estate or local services.

## What it does

- **Bilingual (ES/EN)** with a language picker.
- **Answers with DeepSeek** using a system prompt with services, projects, pricing and guardrails.
- **Sells fixed packages** with inline buttons: “Quiero este” → business name → contact → lead saved.
- **Qualifies leads**: package, service, budget (for custom work), timeline and contact.
- **Scores leads 0–10** (HOT/WARM/COLD) and sends them to the admin with status buttons: Contactado / Cerrar / Descartar.
- **Source tracking**: `?start=upwork`, `?start=workana`, `?start=fiverr`, etc. `/stats` shows conversion by source and package.
- **Admin CRM**: `/leads`, `/lead 12`, `/stats`.
- **Privacy**: `/privacidad` explains what is stored; `/borrar` deletes the user's data.
- **Rate limiting** and a fallback message if the AI provider fails.

## Stack

Python 3.12+, `python-telegram-bot`-free (raw Bot API + `requests`), DeepSeek API (OpenAI-compatible), SQLite.

```
Telegram ── long polling ──> bot.py ──> Gemini
                                │
                                ├── SQLite (users, messages, leads)
                                └── Telegram admin notifications
```

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: bot token, admin chat id, Gemini key
python bot.py
```

`.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ADMIN_CHAT_ID=123456789
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Use `deepseek-flash` with thinking disabled; `deepseek-chat` also works. The API is OpenAI-compatible.

Create the bot with [@BotFather](https://t.me/BotFather) and send `/start` to it once, so the bot can message the admin.

## Commands

| Command | What it does |
|---|---|
| `/start` | Language + main menu |
| `/servicios` | Services |
| `/precios` | Packages + “Quiero este” buttons |
| `/proyectos` | Public demos |
| `/contacto` | Guided qualification |
| `/leads`, `/stats`, `/lead N` | Admin only |
| `/privacidad`, `/borrar` | Privacy / delete data |

## Packages (launch pricing)

| Package | Build + monthly |
|---|---|
| Bot Esencial | USD 150 + USD 19/mo |
| Bot Pro | USD 300 + USD 29/mo |
| Bot WhatsApp | USD 600 + USD 49/mo |
| A medida | from USD 800 + monthly |

The monthly fee covers hosting, monitoring and minor changes; AI usage is paid separately. Prices are launch pricing to get the first reviews.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests cover source parsing, lead scoring, contact extraction, packages and SQLite persistence. They don't call Telegram or DeepSeek.

## Limits

- This is a demo/portfolio bot, not a multi-tenant SaaS.
- Payment and scheduling are out of scope; the admin closes the sale.
- SQLite is fine for one process; a real deployment needs a durable queue and backups.
- The AI can be wrong; the prompt forbids inventing clients, prices or deadlines, but the admin should confirm.

## Other public demos

- [Clinic Bot](https://github.com/andresnv22/clinica-bot) — dental booking, 55 tests, WhatsApp Cloud API.
- [WhatsApp AI Agent](https://github.com/andresnv22/whatsapp-ai-agent) — official Meta API, 29 tests.
- [Bakery Bot](https://github.com/andresnv22/reposteria-bot) — cake orders, 80 tests.
- [n8n + WhatsApp workflows](https://github.com/andresnv22/n8n-whatsapp-workflows) — booking router, reminders, escalation.
- [FAQ Web Bot](https://github.com/andresnv22/faq-web-bot) — embeddable FAQ widget + lead capture, 4 tests.
- [Email/PDF to Excel](https://github.com/andresnv22/correos-excel-bot) — accounting automation with IMAP and PDFs, 3 tests.
- [Web Scraper](https://github.com/andresnv22/web-scraper-demo) — polite Python scraper, 10 tests.

Built by [Andrés Nuñez](https://github.com/andresnv22). Available for remote freelance work.
