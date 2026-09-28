import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from loguru import logger

from app import i18n, repo, timeutils
from app.auth import require_auth
from app.blocks import ALL_BLOCK_KEYS, BLOCKS
from app.config import settings
from app.db import init_db
from app.logging_setup import setup_logging

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app):
    setup_logging()
    i18n.check_sync()
    init_db()
    logger.info("{} started", settings.app.name)
    yield


app = FastAPI(lifespan=lifespan, dependencies=[Depends(require_auth)], docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@app.middleware("http")
async def language(request: Request, call_next):
    request.state.lang = i18n.resolve_lang(request.cookies.get("lang"))
    return await call_next(request)


# --- template helpers ---


def lang_of(ctx):
    return ctx["request"].state.lang


@pass_context
def t_global(ctx, key, **kwargs):
    return i18n.t(key, lang_of(ctx), **kwargs)


@pass_context
def humanize_filter(ctx, s):
    if not s:
        return ""
    return timeutils.humanize(s, lang_of(ctx)) or i18n.t("common.today", lang_of(ctx))


@pass_context
def fmt_date_filter(ctx, s):
    return timeutils.fmt_date(s, lang_of(ctx))


@pass_context
def qtext(ctx, q):
    other = "ru" if lang_of(ctx) == "en" else "en"
    return q[f"text_{lang_of(ctx)}"] or q[f"text_{other}"]


def sparkline(moods, w=100, h=24):
    moods = moods[-12:]
    if len(moods) < 2:
        return ""
    step = w / (len(moods) - 1)
    return " ".join(f"{i * step:.1f},{h - 2 - (m - 1) / 4 * (h - 4):.1f}" for i, m in enumerate(moods))


templates.env.globals.update(t=t_global, qtext=qtext, sparkline=sparkline, settings=settings, BLOCKS=BLOCKS)
templates.env.filters.update(humanize=humanize_filter, fmt_date=fmt_date_filter, days_since=timeutils.days_since)


def render(request, name, **ctx):
    return templates.TemplateResponse(request, name, ctx)


def tr(request, key, **kwargs):
    return i18n.t(key, request.state.lang, **kwargs)


def redirect(url):
    return RedirectResponse(url, status_code=303)


def get_or_404(obj, request):
    if not obj:
        raise HTTPException(404, tr(request, "error.not_found"))
    return obj


def valid_date(s, request):
    if not s:
        return None
    try:
        return timeutils.to_date(s).isoformat()
    except ValueError:
        raise HTTPException(400, tr(request, "error.bad_date")) from None


# --- dashboard ---


def card(e):
    last = next((s for s in repo.sessions_for(e["id"]) if s["status"] == "completed"), None)
    actions = repo.open_actions(e["id"])
    c = {
        "e": e,
        "last": last,
        "moods": repo.mood_history(e["id"]),
        "mine": sum(a["owner"] == "me" for a in actions),
        "theirs": sum(a["owner"] == "them" for a in actions),
        "state": "due",
        "days_since": None,
        "next_due": None,
        "days_left": None,
        "fill": 0,
    }
    if last:
        cadence = e["cadence_days"] or settings.app.default_cadence_days
        due = timeutils.next_due(last["date"], cadence)
        c["days_since"] = timeutils.days_since(last["date"])
        c["next_due"] = due.isoformat()
        c["days_left"] = (due - timeutils.today()).days
        c["state"] = (
            "overdue" if c["days_left"] < 0 else "soon" if c["days_left"] <= settings.app.due_soon_days else "ok"
        )
        # The track spans 1.25x cadence, so the due marker sits at 80% and overdue has room to show.
        c["fill"] = round(min(c["days_since"] / (cadence * 1.25), 1) * 100)
    return c


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return render(
        request,
        "dashboard.html",
        cards=[card(e) for e in repo.engineers()],
        actions=repo.open_actions(),
    )


@app.get("/lang/{code}")
def set_lang(code: str, request: Request):
    ref = urlparse(request.headers.get("referer", ""))
    # Only keep the path so a crafted Referer can't redirect off-site.
    resp = redirect((ref.path or "/") + (f"?{ref.query}" if ref.query else ""))
    if code in i18n.LANGS:
        resp.set_cookie("lang", code, max_age=365 * 24 * 3600, samesite="lax")
    return resp


# --- engineers ---


@app.get("/engineers", response_class=HTMLResponse)
def engineers_page(request: Request):
    return render(request, "engineers.html", engineers=repo.engineers(active_only=False))


@app.post("/engineers")
def engineer_create(request: Request, name: str = Form(""), role: str = Form("")):
    if not name.strip():
        raise HTTPException(400, tr(request, "error.name_required"))
    eid = repo.create_engineer(name.strip(), role.strip())
    logger.info("engineer {} created", eid)
    return redirect(f"/engineers/{eid}")


@app.post("/engineers/{eid}/active")
def engineer_active(eid: int, request: Request, active: int = Form(...)):
    get_or_404(repo.engineer(eid), request)
    repo.set_engineer_active(eid, active)
    logger.info("engineer {} active={}", eid, active)
    return redirect("/engineers")


@app.get("/engineers/{eid}", response_class=HTMLResponse)
def engineer_page(eid: int, request: Request):
    e = get_or_404(repo.engineer(eid), request)
    sessions = repo.sessions_for(eid)
    return render(
        request,
        "engineer.html",
        e=e,
        sessions=sessions,
        agenda=repo.pending_agenda(eid),
        actions=repo.open_actions(eid),
        moods=repo.mood_history(eid),
    )


@app.post("/engineers/{eid}/field", response_class=HTMLResponse)
async def engineer_field(eid: int, request: Request):
    get_or_404(repo.engineer(eid), request)
    form = await request.form()
    for field, value in form.items():
        if field not in repo.ENGINEER_FIELDS:
            raise HTTPException(400, tr(request, "error.bad_field"))
        value = value.strip()
        if field == "name" and not value:
            raise HTTPException(400, tr(request, "error.name_required"))
        if field == "cadence_days":
            if not value.isdigit() or int(value) < 1:
                raise HTTPException(400, tr(request, "error.bad_cadence"))
            value = int(value)
        if field == "start_date":
            value = valid_date(value, request)
        repo.update_engineer(eid, field, value)
    return tr(request, "common.saved")


@app.post("/engineers/{eid}/agenda", response_class=HTMLResponse)
def agenda_add(eid: int, request: Request, text: str = Form("")):
    get_or_404(repo.engineer(eid), request)
    if text.strip():
        repo.add_agenda(eid, text.strip())
    return render(request, "partials/agenda_inbox.html", e={"id": eid}, agenda=repo.pending_agenda(eid))


@app.post("/agenda/{aid}/delete", response_class=HTMLResponse)
def agenda_delete(aid: int):
    repo.delete_agenda(aid)
    return ""


@app.post("/engineers/{eid}/sessions")
def session_start(eid: int, request: Request, session_type: str = Form("regular")):
    get_or_404(repo.engineer(eid), request)
    if session_type not in BLOCKS:
        raise HTTPException(400, tr(request, "error.bad_field"))
    sid = repo.create_session(eid, session_type)
    logger.info("session {} started for engineer {} ({})", sid, eid, session_type)
    return redirect(f"/sessions/{sid}/run")


# --- meeting mode ---


def load_session(sid, request):
    s = get_or_404(repo.session(sid), request)
    return s, repo.engineer(s["engineer_id"])


def check_block(s, block, request):
    if block not in dict(BLOCKS[s["session_type"]]):
        raise HTTPException(404, tr(request, "error.not_found"))


@app.get("/sessions/{sid}/run", response_class=HTMLResponse)
def session_run(sid: int, request: Request, block: str | None = None):
    s, e = load_session(sid, request)
    blocks = BLOCKS[s["session_type"]]
    keys = [k for k, _ in blocks]
    block = block or keys[0]
    check_block(s, block, request)
    idx = keys.index(block)
    return render(
        request,
        "session_run.html",
        s=s,
        e=e,
        blocks=blocks,
        block=block,
        minutes=dict(blocks)[block],
        idx=idx,
        prev=keys[idx - 1] if idx > 0 else None,
        next=keys[idx + 1] if idx < len(keys) - 1 else None,
        note=repo.notes(sid).get(block, ""),
        questions=repo.random_questions(block),
        review=repo.review_actions(s) if block == "review" else [],
        agenda=repo.session_agenda(s) if block == "their_topics" else [],
        created=repo.session_actions(sid) if block == "wrapup" else [],
    )


@app.post("/sessions/{sid}/notes/{block}", response_class=HTMLResponse)
def session_note(sid: int, block: str, request: Request, content: str = Form("")):
    s, _ = load_session(sid, request)
    check_block(s, block, request)
    repo.save_note(sid, block, content)
    return tr(request, "common.saved")


@app.post("/sessions/{sid}/field", response_class=HTMLResponse)
async def session_field(sid: int, request: Request):
    load_session(sid, request)
    form = await request.form()
    for field, value in form.items():
        if field not in repo.SESSION_FIELDS:
            raise HTTPException(400, tr(request, "error.bad_field"))
        if field == "mood":
            if value not in ("1", "2", "3", "4", "5"):
                raise HTTPException(400, tr(request, "error.bad_field"))
            value = int(value)
        if field == "date":
            value = valid_date(value, request)
            if not value:
                raise HTTPException(400, tr(request, "error.bad_date"))
        repo.update_session(sid, field, value)
    s = repo.session(sid)
    if "mood" in form:
        return render(request, "partials/mood.html", s=s)
    return tr(request, "common.saved")


@app.get("/sessions/{sid}/questions/{block}", response_class=HTMLResponse)
def session_questions(sid: int, block: str, request: Request):
    s, _ = load_session(sid, request)
    check_block(s, block, request)
    return render(request, "partials/questions.html", s=s, block=block, questions=repo.random_questions(block))


@app.post("/sessions/{sid}/actions", response_class=HTMLResponse)
def session_action_add(
    sid: int,
    request: Request,
    text: str = Form(""),
    owner: str = Form("them"),
    due_date: str = Form(""),
):
    s, _ = load_session(sid, request)
    if not text.strip():
        raise HTTPException(400, tr(request, "error.text_required"))
    if owner not in ("me", "them"):
        raise HTTPException(400, tr(request, "error.bad_field"))
    aid = repo.create_action(s["engineer_id"], sid, text.strip(), owner, valid_date(due_date, request))
    logger.info("action {} created in session {}", aid, sid)
    return render(request, "partials/session_actions.html", s=s, created=repo.session_actions(sid))


@app.post("/agenda/{aid}/toggle", response_class=HTMLResponse)
def agenda_toggle(aid: int, request: Request, session_id: int = Form(...)):
    s, _ = load_session(session_id, request)
    repo.toggle_agenda(aid, session_id)
    return render(request, "partials/their_topics.html", s=s, agenda=repo.session_agenda(s))


@app.post("/sessions/{sid}/finish")
def session_finish(sid: int, request: Request):
    load_session(sid, request)
    repo.finish_session(sid)
    logger.info("session {} finished", sid)
    return redirect(f"/sessions/{sid}")


# --- action items ---


@app.post("/actions/{aid}/status", response_class=HTMLResponse)
def action_status(aid: int, request: Request, status: str = Form(...), review: int = Form(0)):
    get_or_404(repo.action(aid), request)
    if status not in ("open", "done", "dropped"):
        raise HTTPException(400, tr(request, "error.bad_field"))
    repo.set_action_status(aid, status)
    if review:
        return render(request, "partials/action_review.html", a=repo.action(aid), kept=status == "open")
    return ""


@app.post("/actions/{aid}/text", response_class=HTMLResponse)
def action_text(aid: int, request: Request, text: str = Form("")):
    get_or_404(repo.action(aid), request)
    if not text.strip():
        raise HTTPException(400, tr(request, "error.text_required"))
    repo.update_action_text(aid, text.strip())
    return tr(request, "common.saved")


# --- session view & export ---


def summary(sid, request):
    s, e = load_session(sid, request)
    return {
        "s": s,
        "e": e,
        "blocks": BLOCKS[s["session_type"]],
        "notes": repo.notes(sid),
        "created": repo.session_actions(sid),
        "closed": repo.closed_during(s),
        "discussed": repo.discussed_agenda(sid),
    }


@app.get("/sessions/{sid}", response_class=HTMLResponse)
def session_view(sid: int, request: Request):
    return render(request, "session_view.html", **summary(sid, request))


@app.get("/sessions/{sid}/export.md")
def session_export(sid: int, request: Request):
    ctx = summary(sid, request)
    md = templates.get_template("session.md").render(request=request, **ctx)
    filename = f"1on1-{ctx['s']['date']}-{sid}.md"
    logger.info("session {} exported", sid)
    return Response(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- question bank ---


def clean_question(request, text_en, text_ru):
    text_en, text_ru = text_en.strip(), text_ru.strip()
    if not text_en and not text_ru:
        raise HTTPException(400, tr(request, "error.question_required"))
    return text_en, text_ru


@app.get("/questions", response_class=HTMLResponse)
def questions_page(request: Request):
    qs = repo.questions()
    return render(
        request,
        "questions.html",
        groups=[(k, [q for q in qs if q["block_key"] == k]) for k in ALL_BLOCK_KEYS],
    )


@app.post("/questions")
def question_add(request: Request, block_key: str = Form(...), text_en: str = Form(""), text_ru: str = Form("")):
    if block_key not in ALL_BLOCK_KEYS:
        raise HTTPException(400, tr(request, "error.bad_field"))
    repo.add_question(block_key, *clean_question(request, text_en, text_ru))
    return redirect(f"/questions#block-{block_key}")


@app.post("/questions/{qid}", response_class=HTMLResponse)
def question_edit(qid: int, request: Request, text_en: str = Form(""), text_ru: str = Form("")):
    get_or_404(repo.question(qid), request)
    repo.update_question(qid, *clean_question(request, text_en, text_ru))
    return tr(request, "common.saved")


@app.post("/questions/{qid}/toggle", response_class=HTMLResponse)
def question_toggle(qid: int, request: Request):
    get_or_404(repo.question(qid), request)
    repo.toggle_question(qid)
    return render(request, "partials/question_row.html", q=repo.question(qid))


# --- settings / backup ---


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, imported: int = 0):
    path = Path(settings.db.path)
    return render(
        request,
        "settings.html",
        db_path=path.resolve(),
        db_size=os.path.getsize(path) if path.exists() else 0,
        imported=imported,
    )


@app.get("/settings/export")
def export_json():
    logger.info("JSON export")
    filename = f"one-on-one-{timeutils.today().isoformat()}.json"
    return Response(
        json.dumps(repo.export_all(), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/settings/import")
async def import_json(request: Request, file: UploadFile, confirm: str = Form("")):
    if confirm != "yes":
        raise HTTPException(400, tr(request, "error.confirm_required"))
    try:
        data = json.loads(await file.read())
        assert isinstance(data, dict)
        repo.import_all(data)
    except Exception:
        logger.exception("JSON import failed")
        raise HTTPException(400, tr(request, "error.import_failed")) from None
    logger.info("JSON import done")
    return redirect("/settings?imported=1")
