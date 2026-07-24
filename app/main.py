"""
main.py – FastAPI application entry point for Korean Learning App.

Routes:
  GET  /               → landing / login page
  GET  /dashboard      → user dashboard with group progress
  GET  /learn          → Learn Mode: current group intro + session start
  GET  /learn/card     → present one new card (study phase)
  POST /learn/card/{uc_id} → submit learn quiz, advance
  GET  /review/start   → tutorial + start screen
  GET  /review         → SRS review session
  POST /review/{id}    → submit review answer
  GET  /zen            → Zen Mode
  POST /api/time       → add study seconds
  GET  /api/status     → study-time JSON
"""
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import get_current_user, require_user, router as auth_router, _LoginRequired
from app.database import Base, engine, get_db
from app.models import Card, ReviewLog, UserCard
from app import srs

# ─── App & Middleware ─────────────────────────────────────────────────────────

app = FastAPI(title="Korean Learning App", version="1.0.0")

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-please-use-a-long-random-string")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=7 * 24 * 3600)

# ─── Static & Templates ───────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="/home/ubuntu/korean-app/app/static"), name="static")
templates = Jinja2Templates(directory="/home/ubuntu/korean-app/app/templates")

# ─── Routers ─────────────────────────────────────────────────────────────────

app.include_router(auth_router)


@app.exception_handler(_LoginRequired)
async def login_required_handler(request: Request, exc: _LoginRequired):
    return RedirectResponse(url="/")


# ─── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        srs.seed_cards(db)
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Landing & Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard")
    error = request.query_params.get("error")
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    srs.update_active_days(db, user)
    srs.ensure_user_cards(db, user)
    ts = srs.time_status(db, user)

    # In soft-cap mode, don't hard-redirect from dashboard
    if ts["over_hard"] and user.strict_mode:
        return RedirectResponse(url="/zen")

    due_count  = len(srs.get_due_cards(db, user))
    progress   = srs.get_dashboard_progress(db, user)
    learn_info = srs.get_learn_cards_for_session(db, user)
    new_today  = srs.count_new_learned_today(db, user)

    # Cards introduced TODAY for the "learned today" display
    from app.models import Card as CardModel
    from datetime import date
    introduced_today_ucs = (
        db.query(UserCard)
        .filter(UserCard.user_id == user.id, UserCard.introduced_date == date.today())
        .all()
    )
    learned_today_cards = [
        db.query(CardModel).filter(CardModel.id == uc.card_id).first()
        for uc in introduced_today_ucs
    ]

    return templates.TemplateResponse("dashboard.html", {
        "request":           request,
        "user":              user,
        "ts":                ts,
        "due_count":         due_count,
        "progress":          progress,
        "learn_count":       len(learn_info),
        "new_today":         new_today,
        "max_new":           user.target_daily_new_cards or srs.NEW_LEARN_PER_DAY,
        "learned_today_cards": [c for c in learned_today_cards if c],
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Learn Mode
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/learn", response_class=HTMLResponse)
async def learn_home(request: Request, db: Session = Depends(get_db)):
    """Learn dashboard: shows current group and starts session."""
    user = require_user(request, db)
    srs.ensure_user_cards(db, user)
    ts = srs.time_status(db, user)

    # Hard redirect only in strict mode
    if ts["over_hard"] and user.strict_mode:
        return RedirectResponse(url="/zen")

    current_group = srs.get_current_learn_group(db, user)
    new_today     = srs.count_new_learned_today(db, user)
    learn_cards   = srs.get_learn_cards_for_session(db, user)
    progress      = srs.get_dashboard_progress(db, user)

    return templates.TemplateResponse("learn_home.html", {
        "request":       request,
        "user":          user,
        "ts":            ts,
        "current_group": current_group,
        "learn_cards":   learn_cards,
        "new_today":     new_today,
        "max_new":       user.target_daily_new_cards or srs.NEW_LEARN_PER_DAY,
        "progress":      progress,
        "over_target":   ts["over_target"],
        "show_soft_warning": ts["over_target"] and not user.strict_mode,
    })


@app.get("/learn/card", response_class=HTMLResponse)
async def learn_card(request: Request, db: Session = Depends(get_db)):
    """Show the next unseen card in study (presentation) phase."""
    user = require_user(request, db)
    ts   = srs.time_status(db, user)

    if ts["over_hard"] and user.strict_mode:
        return RedirectResponse(url="/zen")

    session_cards = srs.get_learn_cards_for_session(db, user)
    if not session_cards:
        return templates.TemplateResponse("learn_done.html", {
            "request": request, "user": user, "ts": ts,
            "over_limit": False, "congratulate": True,
        })

    uc   = session_cards[0]
    card = db.query(Card).filter(Card.id == uc.card_id).first()
    remaining = len(session_cards)

    return templates.TemplateResponse("learn_card.html", {
        "request":           request,
        "user":              user,
        "uc":                uc,
        "card":              card,
        "remaining":         remaining,
        "ts":                ts,
        "show_soft_warning": ts["over_target"] and not user.strict_mode,
    })


@app.post("/learn/card/{uc_id}", response_class=HTMLResponse)
async def submit_learn(uc_id: int, request: Request, db: Session = Depends(get_db)):
    """Process the Learn quiz answer and mark card as introduced."""
    user = require_user(request, db)
    form = await request.form()
    time_ms = int(form.get("time_ms", 0))
    fast_lane_failed = form.get("fast_lane_failed") == "true"

    uc = db.query(UserCard).filter(
        UserCard.id == uc_id, UserCard.user_id == user.id
    ).first()
    if not uc:
        raise HTTPException(status_code=404, detail="Card not found")

    # Mark as learned (srs_stage=1 or 2)
    srs.mark_card_learned(db, uc, fast_lane_failed=fast_lane_failed)
    seconds = max(1, time_ms // 1000)
    srs.add_study_seconds(db, user, seconds)
    db.commit()

    ts = srs.time_status(db, user)
    remaining = srs.get_learn_cards_for_session(db, user)

    if not remaining:
        return templates.TemplateResponse("learn_done.html", {
            "request":     request, "user": user, "ts": ts,
            "over_limit":  ts["over_target"],
            "congratulate": True,
        })

    # Over target but not strict mode → continue, soft warning shown by next card page
    if ts["over_target"] and user.strict_mode:
        return templates.TemplateResponse("learn_done.html", {
            "request":      request, "user": user, "ts": ts,
            "over_limit":   True, "congratulate": False,
        })

    return RedirectResponse(url="/learn/card", status_code=303)


# ═══════════════════════════════════════════════════════════════════════════════
# Review Mode
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/review/start", response_class=HTMLResponse)
async def review_start(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    srs.ensure_user_cards(db, user)
    ts = srs.time_status(db, user)
    if ts["over_hard"]:
        return RedirectResponse(url="/zen")
    due_count = len(srs.get_due_cards(db, user))
    if due_count == 0:
        return templates.TemplateResponse("review_done.html", {
            "request": request, "user": user, "ts": ts,
        })
    return templates.TemplateResponse("review_start.html", {
        "request": request, "user": user, "due_count": due_count, "ts": ts,
    })


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    ts   = srs.time_status(db, user)

    if ts["over_hard"] and user.strict_mode:
        return RedirectResponse(url="/zen")

    due_cards = srs.get_due_cards(db, user)
    if not due_cards:
        return templates.TemplateResponse("review_done.html", {
            "request": request, "user": user, "ts": ts,
        })

    first_uc  = due_cards[0]
    card      = db.query(Card).filter(Card.id == first_uc.card_id).first()
    remaining = len(due_cards)

    return templates.TemplateResponse("review.html", {
        "request":           request,
        "user":              user,
        "uc":                first_uc,
        "card":              card,
        "remaining":         remaining,
        "ts":                ts,
        "over_soft":         ts["over_soft"],
        "show_soft_warning": ts["over_target"] and not user.strict_mode,
    })


@app.post("/review/{uc_id}", response_class=HTMLResponse)
async def submit_review(uc_id: int, request: Request, db: Session = Depends(get_db)):
    user    = require_user(request, db)
    form    = await request.form()
    quality = int(form.get("quality", 3))
    time_ms = int(form.get("time_ms", 0))

    uc = db.query(UserCard).filter(
        UserCard.id == uc_id, UserCard.user_id == user.id
    ).first()
    if not uc:
        raise HTTPException(status_code=404, detail="Card not found")

    srs.sm2_update(uc, quality)
    db.commit()

    log = ReviewLog(user_id=user.id, card_id=uc.card_id, quality=quality, time_spent_ms=time_ms)
    db.add(log)

    seconds = max(1, time_ms // 1000)
    srs.add_study_seconds(db, user, seconds)
    db.commit()

    ts = srs.time_status(db, user)
    if ts["over_hard"]:
        response = HTMLResponse(content="", status_code=200)
        response.headers["HX-Redirect"] = "/zen"
        return response

    return RedirectResponse(url="/review", status_code=303)


# ═══════════════════════════════════════════════════════════════════════════════
# Zen Mode
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/zen", response_class=HTMLResponse)
async def zen_mode(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    ts   = srs.time_status(db, user)
    learned_ucs = (
        db.query(UserCard)
        .filter(UserCard.user_id == user.id, UserCard.srs_stage >= 1)
        .order_by(UserCard.last_reviewed)
        .limit(20)
        .all()
    )
    cards = [db.query(Card).filter(Card.id == uc.card_id).first() for uc in learned_ucs]

    # Pre-load first word for Word Discovery
    zen_words  = srs.get_zen_words(db, user)
    first_word = zen_words[0] if zen_words else None

    return templates.TemplateResponse("zen_mode.html", {
        "request":    request,
        "user":       user,
        "ts":         ts,
        "cards":      [c for c in cards if c],
        "first_word": first_word,
        "word_count": len(zen_words),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Zen Word Discovery — HTMX partials
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/zen/word", response_class=HTMLResponse)
async def zen_word(
    request: Request,
    db: Session = Depends(get_db),
    exclude: int = 0,
):
    """Return a random word puzzle partial (HTMX target swap)."""
    user  = require_user(request, db)
    words = srs.get_zen_words(db, user, exclude_id=exclude if exclude else None)
    word  = words[0] if words else None
    return templates.TemplateResponse("zen_word_puzzle.html", {
        "request": request,
        "word":    word,
        "total":   len(words),
    })


@app.post("/api/zen/word/check/{word_id}", response_class=HTMLResponse)
async def zen_word_check(word_id: int, request: Request, db: Session = Depends(get_db)):
    """Check the user's romaja answer. Returns reveal partial if correct, feedback if wrong."""
    user = require_user(request, db)
    form = await request.form()
    answer = (form.get("answer") or "").strip().lower().replace(" ", "")

    word = srs.get_zen_word_by_id(word_id)
    if not word:
        return HTMLResponse("<div>Parola non trovata.</div>", status_code=404)

    # Normalise: strip spaces, lowercase
    correct = word["r"].lower().replace(" ", "")
    is_correct = (answer == correct)

    # Count words still available (exclude current)
    words_left = srs.get_zen_words(db, user, exclude_id=word_id)

    return templates.TemplateResponse("zen_word_result.html", {
        "request":    request,
        "word":       word,
        "is_correct": is_correct,
        "user_answer": form.get("answer", ""),
        "has_next":   len(words_left) > 0,
        "exclude_id": word_id,
    })


@app.get("/api/zen/word/hint/{word_id}", response_class=HTMLResponse)
async def zen_word_hint(word_id: int, request: Request, db: Session = Depends(get_db)):
    """Reveal the solution immediately with no penalty."""
    user = require_user(request, db)
    word = srs.get_zen_word_by_id(word_id)
    if not word:
        return HTMLResponse("<div>Parola non trovata.</div>", status_code=404)

    words_left = srs.get_zen_words(db, user, exclude_id=word_id)

    return templates.TemplateResponse("zen_word_result.html", {
        "request":    request,
        "word":       word,
        "is_correct": None,   # None = shown via hint (no judgement)
        "user_answer": "",
        "has_next":   len(words_left) > 0,
        "exclude_id": word_id,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/api/time", response_class=JSONResponse)
async def add_time(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    body = await request.json()
    seconds = int(body.get("seconds", 0))
    if seconds > 0:
        srs.add_study_seconds(db, user, seconds)
    return srs.time_status(db, user)


@app.get("/api/status", response_class=JSONResponse)
async def get_status(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return srs.time_status(db, user)


# ═══════════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    user  = require_user(request, db)
    ts    = srs.time_status(db, user)
    saved = request.query_params.get("saved") == "1"
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user":    user,
        "ts":      ts,
        "saved":   saved,
    })


@app.post("/settings", response_class=HTMLResponse)
async def update_settings(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    form = await request.form()
    try:
        minutes = int(form.get("target_daily_minutes", 20))
        new_cards = int(form.get("target_daily_new_cards", 5))
        if minutes < 5: minutes = 5
        if minutes > 120: minutes = 120
        if new_cards < 1: new_cards = 1
        if new_cards > 50: new_cards = 50
    except ValueError:
        minutes = 20
        new_cards = 5
        
    user.target_daily_minutes   = minutes
    user.target_daily_new_cards = new_cards
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


# ─── Placement Test ──────────────────────────────────────────────────────────

@app.get("/placement", response_class=HTMLResponse)
async def placement_test(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    # Store quiz data in session so we can validate it
    jamo_quiz = srs.generate_placement_quiz("jamo", 5)
    syllable_quiz = srs.generate_placement_quiz("syllable", 5)
    
    request.session["placement_quiz"] = {
        "jamo": [{"id": q["id"], "answer": q["answer"]} for q in jamo_quiz],
        "syllable": [{"id": q["id"], "answer": q["answer"]} for q in syllable_quiz]
    }
    
    return templates.TemplateResponse("placement.html", {
        "request": request,
        "jamo_quiz": jamo_quiz,
        "syllable_quiz": syllable_quiz
    })

@app.post("/placement/submit", response_class=HTMLResponse)
async def submit_placement(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    form = await request.form()
    quiz_data = request.session.get("placement_quiz", {})
    if not quiz_data:
        return RedirectResponse(url="/dashboard", status_code=303)
    
    # Evaluate Jamo
    j_correct = 0
    for q in quiz_data.get("jamo", []):
        if form.get(f"j_{q['id']}") == q["answer"]:
            j_correct += 1
            
    # Evaluate Syllable
    s_correct = 0
    for q in quiz_data.get("syllable", []):
        if form.get(f"s_{q['id']}") == q["answer"]:
            s_correct += 1
            
    # If >= 4/5, fast track
    if j_correct >= 4:
        srs.fast_track_phase(db, user, "jamo")
    if s_correct >= 4:
        srs.fast_track_phase(db, user, "syllable")
        
    return RedirectResponse(url="/dashboard", status_code=303)
