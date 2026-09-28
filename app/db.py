import sqlite3
from pathlib import Path

from loguru import logger

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS engineer (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT,
  start_date TEXT,
  career_track TEXT,
  goals TEXT,
  feedback_prefs TEXT,
  communication_prefs TEXT,
  profile_notes TEXT,
  cadence_days INTEGER DEFAULT 75,
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS session (
  id INTEGER PRIMARY KEY,
  engineer_id INTEGER NOT NULL REFERENCES engineer(id),
  session_type TEXT NOT NULL DEFAULT 'regular',
  date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'planned',
  mood INTEGER,
  private_notes TEXT,
  started_at TEXT,
  ended_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS session_note (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  block_key TEXT NOT NULL,
  content TEXT DEFAULT '',
  UNIQUE(session_id, block_key)
);
CREATE TABLE IF NOT EXISTS agenda_item (
  id INTEGER PRIMARY KEY,
  engineer_id INTEGER NOT NULL REFERENCES engineer(id),
  text TEXT NOT NULL,
  session_id INTEGER REFERENCES session(id),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS action_item (
  id INTEGER PRIMARY KEY,
  engineer_id INTEGER NOT NULL REFERENCES engineer(id),
  session_id INTEGER REFERENCES session(id),
  text TEXT NOT NULL,
  owner TEXT NOT NULL,
  due_date TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  closed_at TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS question (
  id INTEGER PRIMARY KEY,
  block_key TEXT NOT NULL,
  text_en TEXT,
  text_ru TEXT,
  active INTEGER DEFAULT 1
);
"""

# Deletion order respects foreign keys; insert order is the reverse.
TABLES = ["session_note", "agenda_item", "action_item", "session", "engineer", "question"]

SEED_QUESTIONS = [
    ("checkin", "How are you doing, really?", "Как ты на самом деле?"),
    ("checkin", "What's taking most of your energy lately?", "Что в последнее время забирает больше всего сил?"),
    (
        "checkin",
        "Anything outside work affecting you that I should know about?",
        "Есть что-то вне работы, что на тебя влияет и о чём мне стоит знать?",
    ),
    ("their_topics", "What's on your mind?", "О чём сейчас думаешь?"),
    (
        "their_topics",
        "What would make this conversation most useful for you?",
        "Что сделает этот разговор максимально полезным для тебя?",
    ),
    ("work", "What's slowing you down right now?", "Что сейчас тормозит тебя больше всего?"),
    (
        "work",
        "Is there a decision you're waiting on from me or someone else?",
        "Ждёшь ли ты какого-то решения от меня или от кого-то ещё?",
    ),
    (
        "work",
        "How sustainable is your current workload, 1–10?",
        "Насколько комфортна текущая нагрузка по шкале от 1 до 10?",
    ),
    ("work", "What part of the platform worries you most?", "Какая часть платформы беспокоит тебя больше всего?"),
    ("growth", "Where do you want to be in a year?", "Где ты хочешь быть через год?"),
    ("growth", "Which skill do you want to get better at next?", "Какой навык хочешь прокачать следующим?"),
    ("growth", "What project would stretch you?", "Какой проект стал бы для тебя вызовом?"),
    (
        "growth",
        "Do you see yourself going deeper technically or toward leading people?",
        "Тебе ближе расти глубже в технике или в сторону управления людьми?",
    ),
    (
        "growth",
        "What did you learn recently that you're proud of?",
        "Чему ты недавно научился и чем гордишься?",
    ),
    (
        "team",
        "What's one thing about how we work that you'd change?",
        "Что одно ты бы изменил в том, как мы работаем?",
    ),
    ("team", "How are code reviews and on-call going for you?", "Как тебе сейчас код-ревью и дежурства?"),
    ("team", "Who on the team has helped you recently?", "Кто из команды тебе недавно помог?"),
    (
        "feedback",
        "What should I start, stop, or continue doing as your lead?",
        "Что мне как твоему лиду стоит начать, перестать или продолжать делать?",
    ),
    ("feedback", "Is there anything I did that was unhelpful?", "Было ли что-то в моих действиях, что тебе мешало?"),
    ("feedback", "How do you prefer to get feedback?", "Как тебе удобнее получать обратную связь?"),
    (
        "wrapup",
        "What's the one thing you want to focus on until our next 1:1?",
        "На чём одном хочешь сфокусироваться до нашей следующей встречи?",
    ),
    ("wrapup", "What do you need from me?", "Что тебе нужно от меня?"),
    ("motivation", "What motivates you at work?", "Что тебя мотивирует в работе?"),
    (
        "background",
        "Best manager you had, and what made them good?",
        "Каким был твой лучший руководитель и что делало его хорошим?",
    ),
    (
        "communication_prefs",
        "How do you like to communicate: async, calls, written?",
        "Как тебе удобнее общаться: асинхронно, созвоны, письменно?",
    ),
    ("feedback_prefs", "How do you like to receive feedback?", "Как ты предпочитаешь получать обратную связь?"),
    ("career_aspirations", "What are your career goals?", "Какие у тебя карьерные цели?"),
    (
        "communication_prefs",
        "Any pet peeves I should know about?",
        "Есть что-то, что тебя особенно раздражает и о чём мне стоит знать?",
    ),
]


def connect():
    conn = sqlite3.connect(settings.db.path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    Path(settings.db.path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    if not conn.execute("SELECT 1 FROM question LIMIT 1").fetchone():
        conn.executemany("INSERT INTO question (block_key, text_en, text_ru) VALUES (?, ?, ?)", SEED_QUESTIONS)
        logger.info("seeded {} questions", len(SEED_QUESTIONS))
    conn.commit()
    conn.close()
    logger.info("database ready at {}", settings.db.path)
