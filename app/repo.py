from app import timeutils
from app.blocks import FIRST_SESSION_PREFILL
from app.config import settings
from app.db import TABLES, connect

ENGINEER_FIELDS = {
    "name",
    "role",
    "start_date",
    "career_track",
    "goals",
    "feedback_prefs",
    "communication_prefs",
    "profile_notes",
    "cadence_days",
}
SESSION_FIELDS = {"mood", "private_notes", "date"}


# ponytail: one connection per call; fine for a single user, pool if that ever changes
def query(sql, *args):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def one(sql, *args):
    rows = query(sql, *args)
    return rows[0] if rows else None


def execute(sql, *args):
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# --- engineers ---


def engineers(active_only=True):
    where = "WHERE active = 1" if active_only else ""
    return query(f"SELECT * FROM engineer {where} ORDER BY active DESC, name")


def engineer(eid):
    return one("SELECT * FROM engineer WHERE id = ?", eid)


def create_engineer(name, role):
    return execute(
        "INSERT INTO engineer (name, role, cadence_days) VALUES (?, ?, ?)",
        name,
        role,
        settings.app.default_cadence_days,
    )


def update_engineer(eid, field, value):
    assert field in ENGINEER_FIELDS
    execute(f"UPDATE engineer SET {field} = ? WHERE id = ?", value, eid)


def set_engineer_active(eid, active):
    execute("UPDATE engineer SET active = ? WHERE id = ?", int(active), eid)


# --- sessions ---


def sessions_for(eid):
    return query(
        """SELECT s.*, (SELECT content FROM session_note WHERE session_id = s.id AND block_key = 'wrapup') AS wrapup
           FROM session s WHERE engineer_id = ? ORDER BY date DESC, id DESC""",
        eid,
    )


def session(sid):
    return one("SELECT * FROM session WHERE id = ?", sid)


def create_session(eid, session_type):
    return execute(
        "INSERT INTO session (engineer_id, session_type, date, status, started_at) VALUES (?, ?, ?, 'in_progress', ?)",
        eid,
        session_type,
        timeutils.today().isoformat(),
        timeutils.now().isoformat(),
    )


def update_session(sid, field, value):
    assert field in SESSION_FIELDS
    execute(f"UPDATE session SET {field} = ? WHERE id = ?", value, sid)


def finish_session(sid):
    execute(
        "UPDATE session SET status = 'completed', ended_at = COALESCE(ended_at, ?) WHERE id = ?",
        timeutils.now().isoformat(),
        sid,
    )
    s = session(sid)
    if s["session_type"] == "first":
        n = notes(sid)
        for block, field in FIRST_SESSION_PREFILL.items():
            if n.get(block):
                execute(
                    f"UPDATE engineer SET {field} = ? WHERE id = ? AND COALESCE({field}, '') = ''",
                    n[block],
                    s["engineer_id"],
                )


def notes(sid):
    return {r["block_key"]: r["content"] for r in query("SELECT * FROM session_note WHERE session_id = ?", sid)}


def save_note(sid, block_key, content):
    execute(
        """INSERT INTO session_note (session_id, block_key, content) VALUES (?, ?, ?)
           ON CONFLICT(session_id, block_key) DO UPDATE SET content = excluded.content""",
        sid,
        block_key,
        content,
    )


def mood_history(eid):
    return [
        r["mood"]
        for r in query(
            "SELECT mood FROM session WHERE engineer_id = ? AND mood IS NOT NULL ORDER BY date, id",
            eid,
        )
    ]


# --- action items ---

ACTION_SELECT = "SELECT a.*, e.name AS engineer_name FROM action_item a JOIN engineer e ON e.id = a.engineer_id"


def open_actions(eid=None):
    # NULL due dates sort last
    where = "a.status = 'open' AND e.active = 1" + (" AND a.engineer_id = ?" if eid else "")
    args = (eid,) if eid else ()
    return query(f"{ACTION_SELECT} WHERE {where} ORDER BY a.due_date IS NULL, a.due_date, a.id", *args)


def review_actions(s):
    # Carry-over: anything still open from earlier sessions, plus items closed during this session
    # so the review block keeps showing what was just marked done/dropped.
    return query(
        f"""{ACTION_SELECT} WHERE a.engineer_id = ? AND COALESCE(a.session_id, 0) != ?
            AND (a.status = 'open' OR a.closed_at >= ?)
            ORDER BY a.due_date IS NULL, a.due_date, a.id""",
        s["engineer_id"],
        s["id"],
        s["started_at"],
    )


def closed_during(s):
    return query(
        f"{ACTION_SELECT} WHERE a.engineer_id = ? AND a.status != 'open' AND a.closed_at >= ? AND a.closed_at <= ?",
        s["engineer_id"],
        s["started_at"],
        s["ended_at"] or timeutils.now().isoformat(),
    )


def session_actions(sid):
    return query(f"{ACTION_SELECT} WHERE a.session_id = ? ORDER BY a.id", sid)


def action(aid):
    return one(f"{ACTION_SELECT} WHERE a.id = ?", aid)


def create_action(eid, sid, text, owner, due_date):
    return execute(
        "INSERT INTO action_item (engineer_id, session_id, text, owner, due_date) VALUES (?, ?, ?, ?, ?)",
        eid,
        sid,
        text,
        owner,
        due_date or None,
    )


def set_action_status(aid, status):
    closed_at = None if status == "open" else timeutils.now().isoformat()
    execute("UPDATE action_item SET status = ?, closed_at = ? WHERE id = ?", status, closed_at, aid)


def update_action_text(aid, text):
    execute("UPDATE action_item SET text = ? WHERE id = ?", text, aid)


# --- agenda inbox ---


def pending_agenda(eid):
    return query("SELECT * FROM agenda_item WHERE engineer_id = ? AND session_id IS NULL ORDER BY id", eid)


def session_agenda(s):
    return query(
        "SELECT * FROM agenda_item WHERE engineer_id = ? AND (session_id IS NULL OR session_id = ?) ORDER BY id",
        s["engineer_id"],
        s["id"],
    )


def discussed_agenda(sid):
    return query("SELECT * FROM agenda_item WHERE session_id = ? ORDER BY id", sid)


def add_agenda(eid, text):
    return execute("INSERT INTO agenda_item (engineer_id, text) VALUES (?, ?)", eid, text)


def toggle_agenda(aid, sid):
    execute(
        "UPDATE agenda_item SET session_id = CASE WHEN session_id IS NULL THEN ? ELSE NULL END WHERE id = ?",
        sid,
        aid,
    )


def delete_agenda(aid):
    execute("DELETE FROM agenda_item WHERE id = ?", aid)


# --- questions ---


def random_questions(block_key, n=3):
    return query("SELECT * FROM question WHERE block_key = ? AND active = 1 ORDER BY RANDOM() LIMIT ?", block_key, n)


def questions():
    return query("SELECT * FROM question ORDER BY block_key, id")


def question(qid):
    return one("SELECT * FROM question WHERE id = ?", qid)


def add_question(block_key, text_en, text_ru):
    return execute("INSERT INTO question (block_key, text_en, text_ru) VALUES (?, ?, ?)", block_key, text_en, text_ru)


def update_question(qid, text_en, text_ru):
    execute("UPDATE question SET text_en = ?, text_ru = ? WHERE id = ?", text_en, text_ru, qid)


def toggle_question(qid):
    execute("UPDATE question SET active = 1 - active WHERE id = ?", qid)


# --- backup ---


def export_all():
    return {table: query(f"SELECT * FROM {table}") for table in TABLES}


def import_all(data):
    conn = connect()
    try:
        columns = {t: {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")} for t in TABLES}
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        for table in reversed(TABLES):
            for row in data.get(table, []):
                cols = [c for c in row if c in columns[table]]
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [row[c] for c in cols],
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
