#!/usr/bin/env python3
"""Andrés AI v2 — asistente comercial y captador de leads por Telegram.

- ES/EN, fuente por deep link (?start=upwork), calificación guiada.
- Leads persistidos en SQLite, notificación al admin con botones de estado.
- Métricas por fuente/servicio y comandos de CRM para el admin.
- DeepSeek (texto plano) con fallback y límites de uso.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
DB = BASE / "leads.db"
LOG = logging.getLogger("andres-ai-bot")
EMAIL = "andresnvz3456@gmail.com"


def load_env() -> None:
    path = BASE / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash"
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
if not TOKEN:
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN")
if not DEEPSEEK_KEY:
    raise SystemExit("Falta DEEPSEEK_API_KEY")

# ---------- textos ----------
LINK_GITHUB = "https://github.com/andresnv22"
PROJECTS_ES = """Proyectos (demos públicas, no trabajos de clientes):
• Clinic Bot — agente de IA para agendar/consultar/cancelar citas; reglas en código, sin doble reserva, 55 tests.
  https://github.com/andresnv22/clinica-bot
• WhatsApp AI Agent — citas con la API oficial de Meta; webhooks firmados, deduplicación, tests.
  https://github.com/andresnv22/whatsapp-ai-agent
• Web Scraper — paginación, robots.txt, reintentos, Excel/CSV; 9 tests.
  https://github.com/andresnv22/web-scraper-demo
• Repostería Bot — pedidos de pasteles por chat, CSV/Sheets y handoff humano.
  https://github.com/andresnv22/reposteria-bot
• n8n + WhatsApp — router de reservas, recordatorios 24 h y escalamiento a Telegram.
  https://github.com/andresnv22/n8n-whatsapp-workflows
• Bot de captación Andrés AI — este mismo bot, código abierto.
  https://github.com/andresnv22/ai-lead-bot
• FAQ Web Bot — widget de preguntas frecuentes + captura de leads para cualquier web.
  https://github.com/andresnv22/faq-web-bot
• Correos/PDF a Excel — automatización contable: IMAP, PDFs, dedupe y Excel/CSV.
  https://github.com/andresnv22/correos-excel-bot
• Radar de ofertas — Playwright + Telegram; más de 600 ofertas/día, filtros y deduplicación."""
PROJECTS_EN = """Projects (public demos, not client work):
• Clinic Bot — AI agent that books/checks/cancels appointments; rules in code, no double-booking, 55 tests.
  https://github.com/andresnv22/clinica-bot
• WhatsApp AI Agent — bookings on Meta's official API; signed webhooks, deduplication, tests.
  https://github.com/andresnv22/whatsapp-ai-agent
• Web Scraper — pagination, robots.txt, retries, Excel/CSV; 9 tests.
  https://github.com/andresnv22/web-scraper-demo
• Bakery Bot — cake orders over chat, CSV/Sheets and human handoff.
  https://github.com/andresnv22/reposteria-bot
• n8n + WhatsApp — booking router, 24h reminders and Telegram escalation.
  https://github.com/andresnv22/n8n-whatsapp-workflows
• Andrés AI sales bot — this same bot, open source.
  https://github.com/andresnv22/ai-lead-bot
• FAQ Web Bot — embeddable FAQ widget + lead capture for any website.
  https://github.com/andresnv22/faq-web-bot
• Email/PDF to Excel — accounting automation: IMAP, PDFs, dedupe and Excel/CSV.
  https://github.com/andresnv22/correos-excel-bot
• Deals radar — Playwright + Telegram; 600+ offers/day, filters and deduplication."""
PRICES_ES = """Tarifas de referencia:
• Piloto de automatización o chatbot: desde USD 80–150.
• Chatbot / automatización a medida: USD 150–350.
• WhatsApp Cloud API con agenda: USD 300–700.
• Scraping / monitoreo: desde USD 80.
• Backend / API: USD 200–500.
• Hora: USD 15–18.
Precios de lanzamiento: suben después de 3 reseñas.
El precio final depende del alcance. Incluye brief, propuesta y demo semanal."""
PRICES_EN = """Reference pricing:
• Automation/chatbot pilot: from USD 80–150.
• Custom chatbot/automation: USD 150–350.
• WhatsApp Cloud API with booking: USD 300–700.
• Scraping/monitoring: from USD 80.
• Backend/API: USD 200–500.
• Hourly: USD 15–18.
Launch pricing: goes up after 3 reviews.
Final price depends on scope. Includes brief, proposal and weekly demo."""
PACKAGES = {
    "esencial": {
        "name": {"es": "Bot Esencial", "en": "Essential Bot"},
        "price": {"es": "USD 150 + USD 19/mes", "en": "USD 150 + USD 19/mo"},
        "desc": {
            "es": "Chatbot FAQ + captación, 1 canal (Telegram o web), 3–5 días, 1 revisión, 7 días de soporte.",
            "en": "FAQ + lead-capture chatbot, 1 channel (Telegram or web), 3–5 days, 1 revision, 7 days support.",
        },
        "service": "chatbot",
    },
    "pro": {
        "name": {"es": "Bot Pro", "en": "Pro Bot"},
        "price": {"es": "USD 300 + USD 29/mes", "en": "USD 300 + USD 29/mo"},
        "desc": {
            "es": "Agenda/CRM, 2 canales, tests, 7–10 días, 2 revisiones, 14 días de soporte.",
            "en": "Booking/CRM, 2 channels, tests, 7–10 days, 2 revisions, 14 days support.",
        },
        "service": "chatbot",
    },
    "whatsapp": {
        "name": {"es": "Bot WhatsApp", "en": "WhatsApp Bot"},
        "price": {"es": "USD 600 + USD 49/mes", "en": "USD 600 + USD 49/mo"},
        "desc": {
            "es": "WhatsApp Cloud API, agenda, webhooks firmados, tests, 14 días, 30 días de soporte.",
            "en": "WhatsApp Cloud API, booking, signed webhooks, tests, 14 days, 30 days support.",
        },
        "service": "whatsapp",
    },
    "custom": {
        "name": {"es": "A medida", "en": "Custom"},
        "price": {"es": "desde USD 800 + mensualidad", "en": "from USD 800 + monthly"},
        "desc": {
            "es": "Integraciones/CRM/multicanal a medida; cotización tras brief.",
            "en": "Custom integrations/CRM/multi-channel; quote after a brief.",
        },
        "service": "backend",
    },
}

FAQ_ES = """Preguntas frecuentes:
• ¿Cuánto tarda? Un piloto, 3–7 días; un chatbot con agenda, 1–2 semanas; scraping, 3–10 días.
• ¿Quién paga la IA? El proveedor cobra por uso; para un negocio pequeño suele ser unos pocos dólares al mes. Te lo estimo antes.
• ¿Necesito cuenta de Meta? Para WhatsApp Cloud API sí, es gratis; te guío.
• ¿Trabajas con mi stack? Sí: Python/FastAPI, Node/TypeScript, APIs, SQLite/Postgres, AWS.
• ¿Cómo empezamos? Brief de 15 min → propuesta → 50% para arrancar → demos semanales."""
FAQ_EN = """FAQ:
• How long? Pilot 3–7 days; booking chatbot 1–2 weeks; scraping 3–10 days.
• Who pays for AI? The provider charges per use; usually a few dollars/month for a small business. I estimate it upfront.
• Do I need a Meta account? Yes for WhatsApp Cloud API; it's free and I guide you.
• Can you work with my stack? Yes: Python/FastAPI, Node/TypeScript, APIs, SQLite/Postgres, AWS.
• How do we start? 15-min brief → proposal → 50% to start → weekly demos."""
SERVICES_ES = """Servicios:
1. Chatbot/agente de IA para atención, FAQs y captación de leads.
2. Agente de citas por WhatsApp Cloud API (API oficial de Meta).
3. Scraping y monitoreo de precios/ofertas/datos.
4. Backend/API y automatizaciones entre tus herramientas.
5. Piloto de automatización con IA (3–7 días).
Proceso: brief → propuesta → 50% → demos semanales → entrega con documentación y 2 semanas de soporte."""
SERVICES_EN = """Services:
1. AI chatbot/agent for support, FAQs and lead capture.
2. WhatsApp Cloud API booking agent (Meta's official API).
3. Web scraping and price/deal/data monitoring.
4. Backend/API and automations between your tools.
5. AI automation pilot (3–7 days).
Process: brief → proposal → 50% → weekly demos → delivery with docs and 2 weeks of support."""
SYSTEM = """Eres "Andrés AI", el asistente comercial de Andrés Nuñez, AI Automation Developer en Bucaramanga, Colombia (UTC-5), disponible para trabajo remoto/freelance.

Objetivo: responder dudas, mostrar proyectos y calificar leads. No eres el bot de una empresa; eres el asistente de Andrés.

Datos:
- Servicios: agentes de IA/chatbots (web, WhatsApp Cloud API, Telegram), backends Python/FastAPI, integraciones de APIs/webhooks, scraping/automatización (Python, Playwright), AWS/Terraform y tests.
- Proyectos (demos, no clientes): Clinic Bot (55 tests, sin doble reserva), WhatsApp AI Agent (Cloud API oficial, webhooks firmados, tests), Web Scraper (9 tests), Radar de ofertas (600+/día).
- Links: https://github.com/andresnv22/clinica-bot · https://github.com/andresnv22/whatsapp-ai-agent · https://github.com/andresnv22/web-scraper-demo · https://github.com/andresnv22/reposteria-bot · https://github.com/andresnv22/n8n-whatsapp-workflows · https://github.com/andresnv22/ai-lead-bot · https://github.com/andresnv22/faq-web-bot · https://github.com/andresnv22/correos-excel-bot · https://github.com/andresnv22
- Ejemplos de negocios: clínicas, reposterías, barberías, e-commerce, inmobiliarias y servicios locales.
- Paquetes de lanzamiento: Esencial USD 150 + 19/mes; Pro USD 300 + 29/mes; WhatsApp USD 600 + 49/mes; a medida desde USD 800 + mensualidad. La mensualidad cubre hosting, monitoreo y cambios menores; la IA se paga aparte. Suben después de 3 reseñas.
- Este bot es una demo de lo que Andrés construye; si el usuario pregunta, ofrece un paquete y pide negocio y contacto.
- Si preguntan por descuentos, no inventes: Andrés lo confirma por email.
- Disponibilidad: remoto, UTC-5, horas de EE. UU.; freelance/part-time. Es estudiante de Ingeniería de Sistemas (6.º semestre); no lo lideres con eso.
- Contacto: andresnvz3456@gmail.com.

Reglas:
- Responde en el idioma del usuario (español o inglés), en texto plano, sin Markdown, breve (máximo 5–6 líneas).
- No inventes clientes, casos, precios exactos ni plazos; no prometas resultados ni trabajo gratis.
- Si el usuario muestra interés, pide nombre, email/WhatsApp y qué necesita; invítalo a /contacto para calificar.
- No pidas datos sensibles (tarjetas, contraseñas, cédula).
- No digas que eres Andrés: eres su asistente. Si no sabes algo, que Andrés lo confirma por email."""

T = {
    "es": {
        "choose_lang": "¿En qué idioma prefieres hablar? / Choose your language:",
        "welcome": "Hola {name}. Soy el asistente de Andrés, AI Automation Developer.\n\nSoy una demo de lo que puedo construir para tu negocio. Puedo mostrarte paquetes, proyectos o calificar tu necesidad para pasársela a Andrés.",
        "menu": "¿Qué quieres hacer?",
        "btn_services": "Servicios",
        "btn_prices": "Precios",
        "btn_projects": "Proyectos",
        "btn_talk": "Hablar con Andrés",
        "btn_faq": "Preguntas frecuentes",
        "btn_privacy": "Privacidad",
        "services": SERVICES_ES,
        "prices": PRICES_ES,
        "packages_intro": "Paquetes de lanzamiento (setup + mensualidad). Elige uno y te pido los datos:",
        "packages_note": "La mensualidad cubre hosting, monitoreo y cambios menores. La IA se paga aparte (unos USD 5–20/mes).",
        "btn_want": "Quiero este",
        "pkg_business": "Perfecto: {package} ({price}). ¿Cómo se llama tu negocio y qué debe hacer el bot?",
        "pkg_contact": "Gracias. Ahora déjame tu email o WhatsApp y Andrés te contacta.",
        "pkg_saved": "Listo. Guardé tu solicitud de {package}; Andrés te contacta. Si quieres adelantar, escribe a {email}.",
        "projects": PROJECTS_ES,
        "faq": FAQ_ES,
        "contact_intro": "Perfecto. Para calificar tu necesidad y pasársela a Andrés, elige el servicio:",
        "qual_service": "¿Qué necesitas?",
        "qual_budget": "¿Qué presupuesto tienes en mente?",
        "qual_timeline": "¿Para cuándo lo necesitas?",
        "qual_contact": "Último paso: mándame en un solo mensaje tu nombre, email o WhatsApp, y una línea de qué necesitas. Andrés te contacta.",
        "b_chatbot": "Chatbot / agente de IA",
        "b_whatsapp": "WhatsApp con agenda",
        "b_scraping": "Scraping / monitoreo",
        "b_backend": "Backend / API",
        "b_other": "Otro / no sé",
        "b_low": "Menos de USD 200",
        "b_mid": "USD 200–500",
        "b_high": "Más de USD 500",
        "b_unknown": "No sé todavía",
        "b_asap": "Lo antes posible",
        "b_2_4w": "En 2–4 semanas",
        "b_1_2m": "En 1–2 meses",
        "b_flex": "Flexible",
        "lead_saved": "Gracias. Guardé tu necesidad; Andrés te contacta con esos datos. Si quieres adelantar, escribe a {email}.",
        "fallback": "Ahora no puedo responder con IA. Escríbele a Andrés: {email} o usa /contacto.",
        "privacy": "Guardo tu chat, nombre/contacto y necesidad para que Andrés te responda. No comparto tus datos con terceros. Escribe /borrar para eliminarlos.",
        "deleted": "Listo, borré tus datos de este bot. Si quieres volver a empezar, usa /start.",
        "reset": "Listo, empezamos de cero.",
        "cancel": "Cancelado. Usa /start para volver al menú.",
        "too_many": "Vas muy rápido. Espera un momento y vuelve a escribir.",
        "no_admin": "Ese comando es solo para Andrés.",
        "menu_hint": "Usa los botones o /start para ver el menú.",
        "lead_status": "Lead #{id} marcado como {status}.",
        "unknown_cmd": "No conozco ese comando. Usa /start para empezar.",
    },
    "en": {
        "choose_lang": "Choose your language:",
        "welcome": "Hi {name}. I'm Andrés's assistant, an AI Automation Developer.\n\nI'm a demo of what I can build for your business. I can show you packages, projects, or qualify your needs and pass them to Andrés.",
        "menu": "What would you like to do?",
        "btn_services": "Services",
        "btn_prices": "Pricing",
        "btn_projects": "Projects",
        "btn_talk": "Talk to Andrés",
        "btn_faq": "FAQ",
        "btn_privacy": "Privacy",
        "services": SERVICES_EN,
        "prices": PRICES_EN,
        "packages_intro": "Launch packages (setup + monthly). Pick one and I will ask for your details:",
        "packages_note": "The monthly fee covers hosting, monitoring and minor changes. AI usage is paid separately (around USD 5–20/mo).",
        "btn_want": "I want this",
        "pkg_business": "Great: {package} ({price}). What is your business name and what should the bot do?",
        "pkg_contact": "Thanks. Now send me your email or WhatsApp and Andrés will contact you.",
        "pkg_saved": "Done. I saved your request for {package}; Andrés will contact you. You can also email {email}.",
        "projects": PROJECTS_EN,
        "faq": FAQ_EN,
        "contact_intro": "Great. To qualify your needs and pass them to Andrés, choose a service:",
        "qual_service": "What do you need?",
        "qual_budget": "What budget do you have in mind?",
        "qual_timeline": "When do you need it?",
        "qual_contact": "Last step: send me your name, email or WhatsApp, and one line about what you need. Andrés will contact you.",
        "b_chatbot": "Chatbot / AI agent",
        "b_whatsapp": "WhatsApp with booking",
        "b_scraping": "Scraping / monitoring",
        "b_backend": "Backend / API",
        "b_other": "Other / not sure",
        "b_low": "Under USD 200",
        "b_mid": "USD 200–500",
        "b_high": "Over USD 500",
        "b_unknown": "Not sure yet",
        "b_asap": "ASAP",
        "b_2_4w": "In 2–4 weeks",
        "b_1_2m": "In 1–2 months",
        "b_flex": "Flexible",
        "lead_saved": "Thanks. I saved your needs; Andrés will contact you. You can also email {email}.",
        "fallback": "I can't answer with AI right now. Email Andrés: {email} or use /contacto.",
        "privacy": "I store your chat, name/contact and need so Andrés can reply. I don't share your data with third parties. Type /borrar to delete it.",
        "deleted": "Done, I deleted your data from this bot. Use /start to begin again.",
        "reset": "Done, starting over.",
        "cancel": "Cancelled. Use /start for the menu.",
        "too_many": "You're going too fast. Wait a moment and try again.",
        "no_admin": "That command is only for Andrés.",
        "menu_hint": "Use the buttons or /start to see the menu.",
        "lead_status": "Lead #{id} marked as {status}.",
        "unknown_cmd": "Unknown command. Use /start to begin.",
    },
}


def text(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in T else "es"
    value = T[lang].get(key, T["es"].get(key, key))
    try:
        return value.format(**kwargs)
    except (KeyError, ValueError):
        return value


# ---------- base de datos ----------
def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    con = connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            lang TEXT DEFAULT '',
            source TEXT,
            state TEXT DEFAULT 'idle',
            context TEXT DEFAULT '{}',
            created_at TEXT,
            last_seen TEXT,
            msg_count INTEGER DEFAULT 0
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            ts TEXT NOT NULL
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            username TEXT,
            name TEXT,
            contact TEXT,
            need TEXT,
            transcript TEXT
        )"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_leads_chat ON leads(chat_id)")
    existing = {row["name"] for row in con.execute("PRAGMA table_info(leads)")}
    migrations = {
        "service": "TEXT",
        "budget": "TEXT",
        "timeline": "TEXT",
        "source": "TEXT",
        "score": "INTEGER DEFAULT 0",
        "status": "TEXT DEFAULT 'nuevo'",
        "package": "TEXT",
    }
    for name, ddl in migrations.items():
        if name not in existing:
            con.execute(f"ALTER TABLE leads ADD COLUMN {name} {ddl}")
    con.commit()
    con.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_user(chat_id: int, username: str = "", first_name: str = "") -> dict:
    con = connect()
    row = con.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    if row is None:
        con.execute(
            "INSERT INTO users (chat_id, username, first_name, created_at, last_seen) VALUES (?,?,?,?,?)",
            (chat_id, username, first_name, now(), now()),
        )
        con.commit()
        row = con.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    else:
        con.execute(
            "UPDATE users SET username=COALESCE(NULLIF(?, ''), username), first_name=COALESCE(NULLIF(?, ''), first_name), last_seen=? WHERE chat_id=?",
            (username, first_name, now(), chat_id),
        )
        con.commit()
        row = con.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    data = dict(row)
    try:
        data["context"] = json.loads(data.get("context") or "{}")
    except ValueError:
        data["context"] = {}
    con.close()
    return data


def update_user(chat_id: int, **fields) -> None:
    allowed = {"lang", "source", "state", "context", "msg_count"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    if "context" in updates and not isinstance(updates["context"], str):
        updates["context"] = json.dumps(updates["context"], ensure_ascii=False)
    con = connect()
    clause = ", ".join(f"{key}=?" for key in updates)
    con.execute(f"UPDATE users SET {clause} WHERE chat_id=?", (*updates.values(), chat_id))
    con.commit()
    con.close()


def add_message(chat_id: int, role: str, content: str) -> None:
    con = connect()
    con.execute(
        "INSERT INTO messages (chat_id, role, content, ts) VALUES (?,?,?,?)",
        (chat_id, role, content[:4000], now()),
    )
    con.execute(
        "DELETE FROM messages WHERE chat_id=? AND id NOT IN (SELECT id FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 12)",
        (chat_id, chat_id),
    )
    con.commit()
    con.close()


def history(chat_id: int, limit: int = 8) -> list[tuple[str, str]]:
    con = connect()
    rows = con.execute(
        "SELECT role, content FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)
    ).fetchall()
    con.close()
    return [(row["role"], row["content"]) for row in reversed(rows)]


def extract_contact(value: str) -> str:
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", value or "")
    if email:
        return email.group(0)
    phone = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", value or "")
    if phone:
        return re.sub(r"\s+", " ", phone.group(0)).strip()
    return ""


def score_lead(service: str, budget: str, timeline: str, contact: str) -> int:
    score = {"chatbot": 3, "whatsapp": 3, "scraping": 2, "backend": 2, "other": 1}.get(service, 1)
    score += {"low": 1, "mid": 2, "high": 3, "unknown": 0}.get(budget, 0)
    score += {"asap": 2, "2-4w": 2, "1-2m": 1, "flex": 0}.get(timeline, 0)
    score += 2 if contact else 0
    return min(score, 10)


def save_lead(
    chat_id: int,
    user: dict,
    name: str,
    contact: str,
    need: str,
    service: str = "",
    budget: str = "",
    timeline: str = "",
    package: str = "",
) -> int:
    score = score_lead(service, budget, timeline, contact)
    transcript = "\n".join(f"{role}: {content}" for role, content in history(chat_id, 6))
    con = connect()
    cursor = con.execute(
        """INSERT INTO leads
           (ts, chat_id, username, name, contact, need, transcript, service, budget, timeline, package, source, score, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            now(),
            chat_id,
            user.get("username") or "",
            name,
            contact,
            need[:1500],
            transcript,
            service,
            budget,
            timeline,
            package,
            user.get("source") or "direct",
            score,
            "nuevo",
        ),
    )
    lead_id = int(cursor.lastrowid)
    con.commit()
    con.close()
    if ADMIN and str(chat_id) != str(ADMIN):
        label = "HOT" if score >= 7 else "WARM" if score >= 4 else "COLD"
        message = (
            f"Nuevo lead #{lead_id} [{label} {score}/10]\n"
            f"Servicio: {service or 'no indicado'}\n"
            f"Presupuesto: {budget or 'no indicado'}\n"
            f"Plazo: {timeline or 'no indicado'}\n"
            f"Paquete: {package or 'no indicado'}\n"
            f"Nombre: {name or 'no indicado'}\n"
            f"Contacto: {contact or 'no indicado'}\n"
            f"Necesita: {need[:900]}\n"
            f"Fuente: {user.get('source') or 'direct'}\n"
            f"Chat: @{user.get('username') or 'sin username'} ({chat_id})"
        )
        markup = {
            "inline_keyboard": [
                [
                    {"text": "Contactado", "callback_data": f"lead:{lead_id}:contactado"},
                    {"text": "Cerrar", "callback_data": f"lead:{lead_id}:cerrado"},
                ],
                [{"text": "Descartar", "callback_data": f"lead:{lead_id}:descartado"}],
            ]
        }
        try:
            send(ADMIN, message, reply_markup=markup)
        except Exception:
            LOG.exception("No se pudo notificar el lead %s", lead_id)
    return lead_id


def set_lead_status(lead_id: int, status: str) -> None:
    con = connect()
    con.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
    con.commit()
    con.close()


def lead_by_id(lead_id: int) -> dict | None:
    con = connect()
    row = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def recent_leads(limit: int = 10) -> list[dict]:
    con = connect()
    rows = con.execute("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(row) for row in rows]


def stats() -> str:
    con = connect()
    users = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    leads = con.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
    by_source = con.execute(
        "SELECT COALESCE(source,'direct') AS source, COUNT(*) AS n FROM leads GROUP BY source ORDER BY n DESC"
    ).fetchall()
    by_service = con.execute(
        "SELECT COALESCE(service,'?') AS service, COUNT(*) AS n FROM leads GROUP BY service ORDER BY n DESC"
    ).fetchall()
    by_status = con.execute(
        "SELECT COALESCE(status,'nuevo') AS status, COUNT(*) AS n FROM leads GROUP BY status ORDER BY n DESC"
    ).fetchall()
    by_package = con.execute(
        "SELECT COALESCE(package,'sin paquete') AS package, COUNT(*) AS n FROM leads GROUP BY package ORDER BY n DESC"
    ).fetchall()
    con.close()
    conversion = (leads / users * 100) if users else 0
    lines = [f"Usuarios: {users} · Leads: {leads} · Conversión: {conversion:.1f}%"]
    for title, rows in (("Fuente", by_source), ("Servicio", by_service), ("Paquete", by_package), ("Estado", by_status)):
        if rows:
            lines.append(f"{title}: " + " · ".join(f"{row[0]}={row[1]}" for row in rows))
    return "\n".join(lines)


def delete_user(chat_id: int) -> None:
    con = connect()
    con.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
    con.execute("DELETE FROM leads WHERE chat_id=?", (chat_id,))
    con.execute("DELETE FROM users WHERE chat_id=?", (chat_id,))
    con.commit()
    con.close()


# ---------- Telegram ----------
def tg(method: str, payload: dict | None = None, timeout: int = 65):
    response = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/{method}",
        json=payload or {},
        timeout=timeout,
    )
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description', 'error')}")
    return data.get("result")


def split_text(value: str, limit: int = 3800) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    if len(value) <= limit:
        return [value]
    parts: list[str] = []
    current = ""
    for paragraph in value.split("\n"):
        while len(paragraph) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) > limit:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def send(chat_id: int | str, value: str, reply_markup: dict | None = None) -> None:
    for part in split_text(value):
        payload = {"chat_id": chat_id, "text": part, "disable_web_page_preview": True}
        if reply_markup:
            payload["reply_markup"] = reply_markup
            reply_markup = None
        tg("sendMessage", payload)


def typing(chat_id: int | str) -> None:
    try:
        tg("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def menu_markup(lang: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": text(lang, "btn_services"), "callback_data": "menu:services"},
                {"text": text(lang, "btn_prices"), "callback_data": "menu:pricing"},
            ],
            [
                {"text": text(lang, "btn_projects"), "callback_data": "menu:projects"},
                {"text": text(lang, "btn_talk"), "callback_data": "menu:talk"},
            ],
            [
                {"text": text(lang, "btn_faq"), "callback_data": "menu:faq"},
                {"text": text(lang, "btn_privacy"), "callback_data": "menu:privacy"},
            ],
        ]
    }


def send_menu(chat_id: int, lang: str, intro: str | None = None) -> None:
    send(chat_id, intro or text(lang, "menu"), reply_markup=menu_markup(lang))


def language_markup() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Español", "callback_data": "lang:es"}, {"text": "English", "callback_data": "lang:en"}]
        ]
    }


def ask_language(chat_id: int) -> None:
    send(chat_id, T["es"]["choose_lang"], reply_markup=language_markup())


def welcome(chat_id: int, user: dict) -> None:
    name = user.get("first_name") or user.get("username") or ""
    send(chat_id, text(user.get("lang") or "es", "welcome", name=name))
    send_menu(chat_id, user.get("lang") or "es")


def packages_text(lang: str) -> str:
    lines = [text(lang, "packages_intro"), ""]
    for item in PACKAGES.values():
        lines.append(f"• {item['name'][lang]} — {item['price'][lang]}")
        lines.append(f"  {item['desc'][lang]}")
    lines.append("")
    lines.append(text(lang, "packages_note"))
    return "\n".join(lines)


def send_packages(chat_id: int, lang: str) -> None:
    buttons = []
    for key, item in PACKAGES.items():
        buttons.append([{"text": f"{item['name'][lang]} — {text(lang, 'btn_want')}", "callback_data": f"pkg:{key}"}])
    buttons.append([{"text": text(lang, "btn_talk"), "callback_data": "menu:talk"}])
    send(chat_id, packages_text(lang), reply_markup={"inline_keyboard": buttons})


def menu_options(lang: str) -> dict[str, str]:
    return {
        "menu:services": "services",
        "menu:pricing": "prices",
        "menu:projects": "projects",
        "menu:faq": "faq",
        "menu:privacy": "privacy",
    }


def service_markup(lang: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": text(lang, "b_chatbot"), "callback_data": "q:s:chatbot"}],
            [{"text": text(lang, "b_whatsapp"), "callback_data": "q:s:whatsapp"}],
            [{"text": text(lang, "b_scraping"), "callback_data": "q:s:scraping"}],
            [{"text": text(lang, "b_backend"), "callback_data": "q:s:backend"}],
            [{"text": text(lang, "b_other"), "callback_data": "q:s:other"}],
        ]
    }


def budget_markup(lang: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": text(lang, "b_low"), "callback_data": "q:b:low"}, {"text": text(lang, "b_mid"), "callback_data": "q:b:mid"}],
            [{"text": text(lang, "b_high"), "callback_data": "q:b:high"}, {"text": text(lang, "b_unknown"), "callback_data": "q:b:unknown"}],
        ]
    }


def timeline_markup(lang: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": text(lang, "b_asap"), "callback_data": "q:t:asap"}, {"text": text(lang, "b_2_4w"), "callback_data": "q:t:2-4w"}],
            [{"text": text(lang, "b_1_2m"), "callback_data": "q:t:1-2m"}, {"text": text(lang, "b_flex"), "callback_data": "q:t:flex"}],
        ]
    }


def start_qualification(chat_id: int, user: dict) -> None:
    lang = user.get("lang") or "es"
    update_user(chat_id, state="qual_service", context={})
    send(chat_id, text(lang, "contact_intro") + "\n\n" + text(lang, "qual_service"), reply_markup=service_markup(lang))


def save_from_state(chat_id: int, user: dict, value: str) -> None:
    lang = user.get("lang") or "es"
    context = user.get("context") or {}
    contact = extract_contact(value)
    name = user.get("first_name") or user.get("username") or ""
    lead_id = save_lead(
        chat_id,
        user,
        name,
        contact,
        value,
        service=context.get("service", ""),
        budget=context.get("budget", ""),
        timeline=context.get("timeline", ""),
    )
    update_user(chat_id, state="idle", context={})
    send(chat_id, text(lang, "lead_saved", email=EMAIL) + f"\nLead #{lead_id}")


# ---------- IA ----------
def llm_reply(chat_id: int, user: dict, value: str) -> str:
    lang = user.get("lang") or "es"
    past = history(chat_id, 8)
    messages = [{"role": "system", "content": SYSTEM}]
    for role, content in past:
        messages.append({"role": "user" if role == "Usuario" else "assistant", "content": content})
    messages.append({"role": "user", "content": value})
    response = requests.post(
        f"{DEEPSEEK_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 350,
            "stream": False,
            "thinking": {"type": "disabled"},
        },
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    answer = ((data.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
    if not answer:
        raise RuntimeError("DeepSeek devolvió una respuesta vacía")
    answer = answer.replace("**", "").replace("__", "")
    return answer[:3500]


# ---------- handlers ----------
RATE: dict[int, list[float]] = {}


def rate_limited(chat_id: int) -> bool:
    if str(chat_id) == str(ADMIN):
        return False
    current = time.time()
    values = [ts for ts in RATE.get(chat_id, []) if current - ts < 60]
    values.append(current)
    RATE[chat_id] = values
    return len(values) > 18


def is_admin(chat_id: int | str) -> bool:
    return bool(ADMIN) and str(chat_id) == str(ADMIN)


def parse_source(value: str) -> str:
    value = (value or "").strip().lower()
    if re.fullmatch(r"[a-z0-9_-]{1,32}", value):
        return value
    return "direct"


def handle_start(chat_id: int, user: dict, payload: str) -> None:
    source = parse_source(payload)
    if source != "direct" and not user.get("source"):
        update_user(chat_id, source=source)
        user["source"] = source
    if not user.get("lang"):
        ask_language(chat_id)
        return
    welcome(chat_id, user)


def handle_message(message: dict) -> None:
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return
    sender = message.get("from") or {}
    user = get_user(chat_id, sender.get("username") or "", sender.get("first_name") or "")
    value = (message.get("text") or "").strip()
    if not value:
        send(chat_id, text(user.get("lang") or "es", "menu_hint"))
        return
    if rate_limited(chat_id):
        send(chat_id, text(user.get("lang") or "es", "too_many"))
        return

    if value.startswith("/"):
        command, _, payload = value.partition(" ")
        command = command.split("@")[0].lower()
        lang = user.get("lang") or "es"
        if command == "/start":
            handle_start(chat_id, user, payload)
        elif command in ("/servicios", "/services"):
            send(chat_id, text(lang, "services"))
        elif command in ("/precios", "/pricing"):
            send_packages(chat_id, lang)
        elif command in ("/proyectos", "/portfolio"):
            send(chat_id, text(lang, "projects"))
        elif command in ("/contacto", "/contact"):
            start_qualification(chat_id, get_user(chat_id))
        elif command in ("/ayuda", "/help"):
            send_menu(chat_id, lang)
        elif command in ("/privacidad", "/privacy"):
            send(chat_id, text(lang, "privacy"))
        elif command == "/borrar":
            delete_user(chat_id)
            send(chat_id, text(lang, "deleted"))
        elif command == "/reset":
            update_user(chat_id, state="idle", context={})
            send(chat_id, text(lang, "reset"))
            send_menu(chat_id, lang)
        elif command == "/cancelar":
            update_user(chat_id, state="idle", context={})
            send(chat_id, text(lang, "cancel"))
        elif command == "/leads":
            if not is_admin(chat_id):
                send(chat_id, text(lang, "no_admin"))
                return
            rows = recent_leads()
            if not rows:
                send(chat_id, "No hay leads todavía.")
                return
            lines = ["Últimos leads:"]
            for row in rows:
                lines.append(
                    f"#{row['id']} · {row.get('status')} · {row.get('score')}/10 · "
                    f"{row.get('package') or row.get('service')} · {row.get('contact') or 'sin contacto'} · {row.get('source')}"
                )
            send(chat_id, "\n".join(lines))
        elif command == "/stats":
            if not is_admin(chat_id):
                send(chat_id, text(lang, "no_admin"))
                return
            send(chat_id, stats())
        elif command == "/lead":
            if not is_admin(chat_id):
                send(chat_id, text(lang, "no_admin"))
                return
            try:
                lead_id = int(payload.strip())
            except ValueError:
                send(chat_id, "Uso: /lead 12")
                return
            row = lead_by_id(lead_id)
            if not row:
                send(chat_id, "No existe ese lead.")
                return
            send(
                chat_id,
                f"#{row['id']} · {row['status']} · {row['score']}/10\n"
                f"Servicio: {row.get('service')}\nPaquete: {row.get('package') or 'no indicado'}\n"
                f"Presupuesto: {row.get('budget')}\n"
                f"Plazo: {row.get('timeline')}\nNombre: {row.get('name')}\n"
                f"Contacto: {row.get('contact')}\nFuente: {row.get('source')}\n"
                f"Necesita: {row.get('need')}\nChat: {row.get('chat_id')}",
            )
        else:
            send(chat_id, text(lang, "unknown_cmd"))
        return

    # texto libre
    lang = user.get("lang") or "es"
    state = user.get("state") or "idle"
    if state == "pkg_business":
        context = user.get("context") or {}
        context["need"] = value
        add_message(chat_id, "Usuario", value)
        update_user(chat_id, state="pkg_contact", context=context)
        send(chat_id, text(lang, "pkg_contact"))
        return

    if state == "pkg_contact":
        context = user.get("context") or {}
        package_name = context.get("package_name", "")
        package_key = context.get("package", "")
        service = PACKAGES.get(package_key, {}).get("service", "")
        add_message(chat_id, "Usuario", value)
        lead_id = save_lead(
            chat_id,
            user,
            user.get("first_name") or user.get("username") or "",
            extract_contact(value),
            context.get("need", ""),
            service=service,
            package=package_name,
        )
        update_user(chat_id, state="idle", context={})
        send(chat_id, text(lang, "pkg_saved", package=package_name, email=EMAIL) + f"\nLead #{lead_id}")
        return

    if state == "qual_contact":
        add_message(chat_id, "Usuario", value)
        save_from_state(chat_id, user, value)
        return
    if state != "idle":
        update_user(chat_id, state="idle", context={})

    add_message(chat_id, "Usuario", value)
    typing(chat_id)
    try:
        answer = llm_reply(chat_id, user, value)
    except Exception:
        LOG.exception("DeepSeek falló")
        send(chat_id, text(lang, "fallback", email=EMAIL))
        return
    add_message(chat_id, "Asistente", answer)
    send(chat_id, answer)

    contact = extract_contact(value)
    if contact:
        lead_id = save_lead(chat_id, user, user.get("first_name") or user.get("username") or "", contact, value)
        send(chat_id, text(lang, "lead_saved", email=EMAIL) + f"\nLead #{lead_id}")


def handle_callback(callback: dict) -> None:
    callback_id = callback.get("id")
    data = callback.get("data") or ""
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    try:
        tg("answerCallbackQuery", {"callback_query_id": callback_id})
    except Exception:
        pass
    if not chat_id:
        return
    user = get_user(chat_id)
    lang = user.get("lang") or "es"

    if data.startswith("lang:"):
        lang = data.split(":", 1)[1]
        if lang not in ("es", "en"):
            lang = "es"
        update_user(chat_id, lang=lang, state="idle", context={})
        user = get_user(chat_id)
        send(chat_id, "Listo." if lang == "es" else "Done.")
        welcome(chat_id, user)
        return

    if data.startswith("pkg:"):
        key = data.split(":", 1)[1]
        item = PACKAGES.get(key)
        if not item:
            return
        context = {
            "package": key,
            "package_name": item["name"][lang],
            "package_price": item["price"][lang],
        }
        update_user(chat_id, state="pkg_business", context=context)
        send(chat_id, text(lang, "pkg_business", package=item["name"][lang], price=item["price"][lang]))
        return

    if data.startswith("menu:"):
        key = data.split(":", 1)[1]
        if key == "pricing":
            send_packages(chat_id, lang)
        elif key == "talk":
            start_qualification(chat_id, user)
        else:
            mapping = menu_options(lang)
            text_key = mapping.get(f"menu:{key}")
            if text_key:
                send(chat_id, text(lang, text_key))
            else:
                send_menu(chat_id, lang)
        return

    if data.startswith("q:s:"):
        service = data.split(":", 2)[2]
        context = user.get("context") or {}
        context["service"] = service
        update_user(chat_id, state="qual_budget", context=context)
        send(chat_id, text(lang, "qual_budget"), reply_markup=budget_markup(lang))
        return

    if data.startswith("q:b:"):
        budget = data.split(":", 2)[2]
        context = user.get("context") or {}
        context["budget"] = budget
        update_user(chat_id, state="qual_timeline", context=context)
        send(chat_id, text(lang, "qual_timeline"), reply_markup=timeline_markup(lang))
        return

    if data.startswith("q:t:"):
        timeline = data.split(":", 2)[2]
        context = user.get("context") or {}
        context["timeline"] = timeline
        update_user(chat_id, state="qual_contact", context=context)
        send(chat_id, text(lang, "qual_contact"))
        return

    if data.startswith("lead:"):
        if not is_admin(chat_id):
            send(chat_id, text(lang, "no_admin"))
            return
        parts = data.split(":")
        if len(parts) != 3:
            return
        try:
            lead_id = int(parts[1])
        except ValueError:
            return
        status = parts[2]
        if status not in {"contactado", "cerrado", "descartado"}:
            return
        set_lead_status(lead_id, status)
        send(chat_id, text(lang, "lead_status", id=lead_id, status=status))
        return

    send_menu(chat_id, lang)


# ---------- loop ----------
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    LOG.info("Andrés AI v2 iniciado con DeepSeek %s", MODEL)
    offset = 0
    while True:
        try:
            updates = tg(
                "getUpdates",
                {"offset": offset, "timeout": 50, "allowed_updates": ["message", "callback_query"]},
                timeout=65,
            )
        except Exception:
            LOG.exception("getUpdates falló; reintento en 5 s")
            time.sleep(5)
            continue
        for update in updates or []:
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            try:
                if "message" in update:
                    handle_message(update["message"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
            except Exception:
                LOG.exception("Error procesando update")


if __name__ == "__main__":
    main()
