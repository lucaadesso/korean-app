"""
srs.py – Adaptive Spaced-Repetition System (SM-2) + Learn Mode logic for Korean

Key features:
- SM-2 ease-factor scheduling
- Daily cap: max 25 review cards / max 5 new learn cards per day
- Study-time cap: 15 min soft / 20 min hard → Zen Mode
- Learn Mode: present → quiz → mark srs_stage=1 → enters SRS queue
- Unlock progression: vowels → consonants → syllables-basic → syllables-advanced
- Per-group progress API for dashboard grid
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Card, DailyStudy, User, UserCard

# ─── Constants ───────────────────────────────────────────────────────────────
DAILY_CARD_CAP      = 25          # max review cards shown per day
NEW_LEARN_PER_DAY   = 5           # max NEW cards introduced via Learn per day
SOFT_LIMIT_SECONDS  = 15 * 60     # 15 min → warn
HARD_LIMIT_SECONDS  = 20 * 60     # 20 min → Zen Mode redirect
MIN_EASE            = 1.3         # SM-2 minimum ease factor

# Unlock threshold: fraction of a phase that must be learned before next phase
UNLOCK_THRESHOLD    = 0.80        # 80%

# ─── Group ordering (sequential unlock within phase) ─────────────────────────
JAMO_GROUP_ORDER = [
    "vowels",      # 모음: ㅏ ㅑ ㅓ ㅕ ㅗ ㅛ ㅜ ㅠ ㅡ ㅣ
    "consonants",  # 자음: ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ
]
SYLLABLE_GROUP_ORDER = [
    "basic",       # Sillabe semplici: 가 나 다 라 마 바 사
    "advanced",    # Sillabe avanzate: 자 차 카 타 파 하
]

# ─── Jamo vowels seed data: (front, back, romanji, group, mnemonic note) ──────
JAMO_VOWELS_DATA = [
    ("ㅏ", "a",  "a",  "vowels", "La freccia punta a destra come 'a' aperta"),
    ("ㅑ", "ya", "ya", "vowels", "Due frecce a destra: raddoppia la 'a' → 'ya'"),
    ("ㅓ", "eo", "eo", "vowels", "La freccia punta a sinistra come 'eo' aperto"),
    ("ㅕ", "yeo","yeo","vowels", "Due frecce a sinistra: 'yeo'"),
    ("ㅗ", "o",  "o",  "vowels", "La freccia punta su: 'o' come OH!"),
    ("ㅛ", "yo", "yo", "vowels", "Due frecce su: 'yo'"),
    ("ㅜ", "u",  "u",  "vowels", "La freccia punta giù: 'u' come in UNO"),
    ("ㅠ", "yu", "yu", "vowels", "Due frecce giù: 'yu'"),
    ("ㅡ", "eu", "eu", "vowels", "Linea orizzontale: suono neutro 'eu'"),
    ("ㅣ", "i",  "i",  "vowels", "Linea verticale diritta come la 'i'"),
]

# ─── Jamo consonants seed data ────────────────────────────────────────────────
JAMO_CONSONANTS_DATA = [
    ("ㄱ", "g/k", "g",  "consonants", "Come un angolo retto: 'ㄱ' suono G/K"),
    ("ㄴ", "n",   "n",  "consonants", "Come una L al contrario: suono N"),
    ("ㄷ", "d/t", "d",  "consonants", "Come una C quadrata: suono D/T"),
    ("ㄹ", "r/l", "r",  "consonants", "Come una scala: suono R/L"),
    ("ㅁ", "m",   "m",  "consonants", "Come una bocca (mouth): suono M"),
    ("ㅂ", "b/p", "b",  "consonants", "Come una vasca: suono B/P"),
    ("ㅅ", "s",   "s",  "consonants", "Come un albero con due rami: suono S"),
    ("ㅇ", "ng/∅","ng", "consonants", "Cerchio vuoto: silenzioso all'inizio, NG alla fine"),
    ("ㅈ", "j",   "j",  "consonants", "Come ㅅ con un cappello: suono J"),
    ("ㅊ", "ch",  "ch", "consonants", "Come ㅈ con un tratto extra: suono CH"),
    ("ㅋ", "k",   "k",  "consonants", "Come ㄱ aspirato: suono K forte"),
    ("ㅌ", "t",   "t",  "consonants", "Come ㄷ aspirato: suono T forte"),
    ("ㅍ", "p",   "p",  "consonants", "Come ㅂ aspirato: suono P forte"),
    ("ㅎ", "h",   "h",  "consonants", "Come un ombrello: suono H"),
]

# ─── Basic syllables (가-type: consonant + ㅏ) ─────────────────────────────
SYLLABLE_BASIC_DATA = [
    ("가", "ga",  "ga",  "basic", "ㄱ + ㅏ = ga (come in 'garage')"),
    ("나", "na",  "na",  "basic", "ㄴ + ㅏ = na (come in 'navi')"),
    ("다", "da",  "da",  "basic", "ㄷ + ㅏ = da (come in 'dado')"),
    ("라", "ra",  "ra",  "basic", "ㄹ + ㅏ = ra (come in 'radio')"),
    ("마", "ma",  "ma",  "basic", "ㅁ + ㅏ = ma (come 'mamma')"),
    ("바", "ba",  "ba",  "basic", "ㅂ + ㅏ = ba (come in 'banana')"),
    ("사", "sa",  "sa",  "basic", "ㅅ + ㅏ = sa (come in 'sale')"),
    ("아", "a",   "a",   "basic", "ㅇ + ㅏ = a (ㅇ silenzioso all'inizio)"),
    ("자", "ja",  "ja",  "basic", "ㅈ + ㅏ = ja (come 'jazz')"),
    ("차", "cha", "cha", "basic", "ㅊ + ㅏ = cha (come 'chat')"),
    ("카", "ka",  "ka",  "basic", "ㅋ + ㅏ = ka (K aspirato)"),
    ("타", "ta",  "ta",  "basic", "ㅌ + ㅏ = ta (T aspirato)"),
    ("파", "pa",  "pa",  "basic", "ㅍ + ㅏ = pa (P aspirato)"),
    ("하", "ha",  "ha",  "basic", "ㅎ + ㅏ = ha (come 'ha ha ha!')"),
]

# ─── Advanced syllables (고, 구, 기, etc.) ────────────────────────────────
SYLLABLE_ADVANCED_DATA = [
    ("고", "go",  "go",  "advanced", "ㄱ + ㅗ = go (come 'goal')"),
    ("구", "gu",  "gu",  "advanced", "ㄱ + ㅜ = gu (come 'guru')"),
    ("기", "gi",  "gi",  "advanced", "ㄱ + ㅣ = gi (come 'gin')"),
    ("노", "no",  "no",  "advanced", "ㄴ + ㅗ = no (come 'no!')"),
    ("누", "nu",  "nu",  "advanced", "ㄴ + ㅜ = nu (come 'nuovo')"),
    ("니", "ni",  "ni",  "advanced", "ㄴ + ㅣ = ni (come 'nido')"),
    ("도", "do",  "do",  "advanced", "ㄷ + ㅗ = do (come 'domino')"),
    ("두", "du",  "du",  "advanced", "ㄷ + ㅜ = du (come 'duetto')"),
    ("모", "mo",  "mo",  "advanced", "ㅁ + ㅗ = mo (come 'moda')"),
    ("무", "mu",  "mu",  "advanced", "ㅁ + ㅜ = mu (come 'musica')"),
    ("미", "mi",  "mi",  "advanced", "ㅁ + ㅣ = mi (nota musicale)"),
    ("보", "bo",  "bo",  "advanced", "ㅂ + ㅗ = bo (come 'bonsai')"),
    ("소", "so",  "so",  "advanced", "ㅅ + ㅗ = so (come 'sole')"),
    ("시", "si",  "si",  "advanced", "ㅅ + ㅣ = si (come 'sì!')"),
]


# ─── SM-2 Core ───────────────────────────────────────────────────────────────

def sm2_update(uc: UserCard, quality: int) -> UserCard:
    """Apply SM-2: quality 0-5 (0=blackout, 5=perfect)."""
    q = max(0, min(5, quality))
    if q < 3:
        uc.repetitions = 0
        uc.interval    = 1
    else:
        if uc.repetitions == 0:
            uc.interval = 1
        elif uc.repetitions == 1:
            uc.interval = 6
        else:
            uc.interval = math.ceil(uc.interval * uc.ease_factor)
        uc.repetitions += 1

    uc.ease_factor = max(
        MIN_EASE,
        uc.ease_factor + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02),
    )
    uc.due_date      = date.today() + timedelta(days=uc.interval)
    uc.last_reviewed = date.today()
    uc.is_new        = False
    if uc.srs_stage < 2:
        uc.srs_stage = 2   # graduated from Learn → SRS
    return uc


# ─── Learn Mode helpers ───────────────────────────────────────────────────────

def get_current_learn_group(db: Session, user: User) -> Optional[dict]:
    """
    Returns the next group the user should learn, following unlock rules.
    Returns None if all groups are completed.

    Unlock order:
      Jamo vowels → Jamo consonants
      Syllables (basic) unlocks when Jamo >= UNLOCK_THRESHOLD
      Syllables (advanced) unlocks when basic syllables >= UNLOCK_THRESHOLD
    """
    # Check jamo groups first
    for group in JAMO_GROUP_ORDER:
        progress = get_group_progress(db, user, "jamo", group)
        if progress["pct_learned"] < 100:
            return {"phase": "jamo", "group": group, "progress": progress}

    # All Jamo done → check if syllables are unlocked
    jamo_total = get_phase_progress(db, user, "jamo")
    if jamo_total["pct_learned"] >= int(UNLOCK_THRESHOLD * 100):
        for group in SYLLABLE_GROUP_ORDER:
            progress = get_group_progress(db, user, "syllable", group)
            if progress["pct_learned"] < 100:
                return {"phase": "syllable", "group": group, "progress": progress}

    return None   # everything complete


def get_learn_cards_for_session(db: Session, user: User, limit: Optional[int] = None) -> list[UserCard]:
    """
    Get up to `limit` unseen UserCards (srs_stage=0) from the current group,
    respecting the user's personal daily new-card target.
    """
    cap = limit if limit is not None else (user.target_daily_new_cards or NEW_LEARN_PER_DAY)
    current = get_current_learn_group(db, user)
    if not current:
        return []

    phase = current["phase"]
    group = current["group"]

    already_today = count_new_learned_today(db, user)
    remaining_slots = max(0, cap - already_today)
    if remaining_slots == 0:
        return []

    unseen = (
        db.query(UserCard)
        .join(Card, UserCard.card_id == Card.id)
        .filter(
            UserCard.user_id    == user.id,
            UserCard.srs_stage  == 0,
            Card.phase          == phase,
            Card.group_name     == group,
        )
        .order_by(Card.id)
        .limit(remaining_slots)
        .all()
    )
    return unseen


def count_new_learned_today(db: Session, user: User) -> int:
    """Count cards introduced via Learn TODAY (uses introduced_date, not last_reviewed)."""
    from datetime import date as _date
    today = _date.today()
    return (
        db.query(UserCard)
        .filter(
            UserCard.user_id       == user.id,
            UserCard.introduced_date == today,    # set only by mark_card_learned()
        )
        .count()
    )


def mark_card_learned(db: Session, uc: UserCard) -> UserCard:
    """Mark a UserCard as introduced via Learn (srs_stage=1, is_new=False)."""
    today = date.today()
    uc.srs_stage      = 1
    uc.is_new         = False
    uc.last_reviewed  = today
    uc.introduced_date = today          # ← track when this card was first introduced
    uc.due_date       = today + timedelta(days=1)
    db.commit()
    db.refresh(uc)
    return uc


# ─── Daily card queue (Review) ────────────────────────────────────────────────

def get_due_cards(db: Session, user: User, limit: int = DAILY_CARD_CAP) -> list[UserCard]:
    """Returns up to `limit` UserCards due today (srs_stage >= 1, due today or overdue)."""
    today = date.today()
    return (
        db.query(UserCard)
        .filter(
            UserCard.user_id == user.id,
            UserCard.srs_stage >= 1,
            UserCard.due_date <= today,
        )
        .order_by(UserCard.due_date)
        .limit(limit)
        .all()
    )


# ─── Progress helpers ─────────────────────────────────────────────────────────

def get_group_progress(db: Session, user: User, phase: str, group: str) -> dict:
    """Per-group progress stats."""
    total_cards = (
        db.query(Card)
        .filter(Card.phase == phase, Card.group_name == group)
        .count()
    )
    learned = (
        db.query(UserCard)
        .join(Card, UserCard.card_id == Card.id)
        .filter(
            UserCard.user_id == user.id,
            UserCard.srs_stage >= 1,
            Card.phase == phase,
            Card.group_name == group,
        )
        .count()
    )
    mastered = (
        db.query(UserCard)
        .join(Card, UserCard.card_id == Card.id)
        .filter(
            UserCard.user_id == user.id,
            UserCard.repetitions >= 3,
            Card.phase == phase,
            Card.group_name == group,
        )
        .count()
    )
    pct = int(learned / total_cards * 100) if total_cards else 0
    return {
        "phase": phase,
        "group": group,
        "total": total_cards,
        "learned": learned,
        "mastered": mastered,
        "pct_learned": pct,
        "complete": pct >= 100,
    }


def get_phase_progress(db: Session, user: User, phase: str) -> dict:
    """Aggregate progress for an entire phase."""
    total = db.query(Card).filter(Card.phase == phase).count()
    learned = (
        db.query(UserCard)
        .join(Card, UserCard.card_id == Card.id)
        .filter(UserCard.user_id == user.id, UserCard.srs_stage >= 1, Card.phase == phase)
        .count()
    )
    pct = int(learned / total * 100) if total else 0
    return {"phase": phase, "total": total, "learned": learned, "pct_learned": pct}


def get_dashboard_progress(db: Session, user: User) -> dict:
    """Full progress data for the dashboard: per-group + phase totals + unlock status."""
    jamo_groups = [
        get_group_progress(db, user, "jamo", g) for g in JAMO_GROUP_ORDER
    ]
    syllable_groups = [
        get_group_progress(db, user, "syllable", g) for g in SYLLABLE_GROUP_ORDER
    ]
    jamo_phase     = get_phase_progress(db, user, "jamo")
    syllable_phase = get_phase_progress(db, user, "syllable")

    syllable_unlocked = jamo_phase["pct_learned"] >= int(UNLOCK_THRESHOLD * 100)
    vocab_unlocked    = syllable_phase["pct_learned"] >= 100

    # Determine which group is currently being unlocked
    current = get_current_learn_group(db, user)

    return {
        "jamo":     {"phase": jamo_phase,     "groups": jamo_groups},
        "syllable": {"phase": syllable_phase,  "groups": syllable_groups, "unlocked": syllable_unlocked},
        "vocab":    {"unlocked": vocab_unlocked},
        "current_learn": current,
    }


# ─── Study-time helpers ───────────────────────────────────────────────────────

def get_today_seconds(db: Session, user: User) -> int:
    today = date.today()
    record = db.query(DailyStudy).filter(
        DailyStudy.user_id == user.id, DailyStudy.study_date == today
    ).first()
    return record.seconds_studied if record else 0


def add_study_seconds(db: Session, user: User, seconds: int) -> DailyStudy:
    today = date.today()
    record = db.query(DailyStudy).filter(
        DailyStudy.user_id == user.id, DailyStudy.study_date == today
    ).first()
    if not record:
        record = DailyStudy(user_id=user.id, study_date=today, seconds_studied=0)
        db.add(record)
    record.seconds_studied += seconds
    db.commit()
    db.refresh(record)
    return record


def is_over_soft_limit(db: Session, user: User) -> bool:
    return get_today_seconds(db, user) >= SOFT_LIMIT_SECONDS


def is_over_hard_limit(db: Session, user: User) -> bool:
    return get_today_seconds(db, user) >= HARD_LIMIT_SECONDS


def time_status(db: Session, user: User) -> dict:
    """Return time status using the user's personal daily target."""
    seconds      = get_today_seconds(db, user)
    target_secs  = (user.target_daily_minutes or 20) * 60
    soft_secs    = int(target_secs * 0.75)  # soft warn at 75% of target
    pct_target   = min(100, int(seconds / target_secs * 100))
    pct_soft     = min(100, int(seconds / soft_secs   * 100))
    return {
        "seconds_studied":      seconds,
        "target_seconds":       target_secs,
        "soft_limit":           SOFT_LIMIT_SECONDS,    # kept for compatibility
        "hard_limit":           HARD_LIMIT_SECONDS,
        "target_daily_minutes": user.target_daily_minutes or 20,
        "strict_mode":          bool(user.strict_mode),
        "pct_soft":             pct_soft,
        "pct_hard":             pct_target,            # rename alias kept for templates
        "pct_target":           pct_target,
        "over_soft":            seconds >= soft_secs,
        "over_hard":            seconds >= target_secs,
        "over_target":          seconds >= target_secs,
        "minutes_studied":      round(seconds / 60, 1),
    }


# ─── Active Days ──────────────────────────────────────────────────────────────

def update_active_days(db: Session, user: User) -> None:
    today = date.today()
    if user.last_active_date is None or user.last_active_date.month != today.month:
        user.active_days_this_month = 1
    elif user.last_active_date != today:
        user.active_days_this_month += 1
    user.last_active_date = today
    db.commit()


# ─── Seed ─────────────────────────────────────────────────────────────────────

def seed_cards(db: Session) -> None:
    """Insert/update Jamo and Syllable cards with groups and mnemonic notes."""
    # Check if already seeded with group_name populated
    existing = db.query(Card).filter(Card.group_name.isnot(None)).count()

    if existing == 0:
        existing_total = db.query(Card).count()
        if existing_total == 0:
            # Fresh seed
            cards = []
            for front, back, romanji, group, note in JAMO_VOWELS_DATA:
                cards.append(Card(phase="jamo", group_name=group,
                                  front=front, back=back, romanji=romanji, notes=note))
            for front, back, romanji, group, note in JAMO_CONSONANTS_DATA:
                cards.append(Card(phase="jamo", group_name=group,
                                  front=front, back=back, romanji=romanji, notes=note))
            for front, back, romanji, group, note in SYLLABLE_BASIC_DATA:
                cards.append(Card(phase="syllable", group_name=group,
                                  front=front, back=back, romanji=romanji, notes=note))
            for front, back, romanji, group, note in SYLLABLE_ADVANCED_DATA:
                cards.append(Card(phase="syllable", group_name=group,
                                  front=front, back=back, romanji=romanji, notes=note))
            db.add_all(cards)
            db.commit()
        else:
            # Update existing cards with group_name and notes
            all_data = (
                [(row, "jamo")     for row in JAMO_VOWELS_DATA] +
                [(row, "jamo")     for row in JAMO_CONSONANTS_DATA] +
                [(row, "syllable") for row in SYLLABLE_BASIC_DATA] +
                [(row, "syllable") for row in SYLLABLE_ADVANCED_DATA]
            )
            front_map = {row[0]: (row, phase) for row, phase in all_data}
            for card in db.query(Card).all():
                entry = front_map.get(card.front)
                if entry and card.group_name is None:
                    row, phase = entry
                    card.group_name = row[3]
                    card.notes      = row[4]
            db.commit()


def ensure_user_cards(db: Session, user: User) -> None:
    """Create UserCard rows for any Card not yet assigned to this user."""
    all_cards    = db.query(Card).all()
    existing_ids = {uc.card_id for uc in
                    db.query(UserCard).filter(UserCard.user_id == user.id).all()}
    new_ucs = [
        UserCard(user_id=user.id, card_id=c.id)
        for c in all_cards if c.id not in existing_ids
    ]
    if new_ucs:
        db.add_all(new_ucs)
        db.commit()


# ─── Zen Mode: Word Discovery ─────────────────────────────────────────────────

# Vocab list: Korean words composed only of characters the user has learned.
# (id, korean, romaja, meaning_it, chars)
# chars = set of Hangul characters/jamo composing the word.
ZEN_VOCAB: list[dict] = [
    # ── From basic syllables ──────────────────────────────────────────────
    {"id":  1, "j": "나",    "r": "na",    "m": "Io / Io stesso",         "k": {"나"}},
    {"id":  2, "j": "가다",  "r": "gada",  "m": "Andare",                 "k": {"가", "다"}},
    {"id":  3, "j": "나라",  "r": "nara",  "m": "Paese / Nazione",        "k": {"나", "라"}},
    {"id":  4, "j": "바다",  "r": "bada",  "m": "Mare",                   "k": {"바", "다"}},
    {"id":  5, "j": "마다",  "r": "mada",  "m": "Ogni / Tutto",           "k": {"마", "다"}},
    {"id":  6, "j": "차",    "r": "cha",   "m": "Tè / Auto",              "k": {"차"}},
    {"id":  7, "j": "나타나다","r":"natanada","m": "Apparire",             "k": {"나", "타"}},
    {"id":  8, "j": "하다",  "r": "hada",  "m": "Fare",                   "k": {"하", "다"}},
    {"id":  9, "j": "사다",  "r": "sada",  "m": "Comprare",               "k": {"사", "다"}},
    {"id": 10, "j": "자다",  "r": "jada",  "m": "Dormire",                "k": {"자", "다"}},
    {"id": 11, "j": "타다",  "r": "tada",  "m": "Salire / Bruciare",      "k": {"타", "다"}},
    {"id": 12, "j": "파다",  "r": "pada",  "m": "Scavare",                "k": {"파", "다"}},
    {"id": 13, "j": "가나",  "r": "gana",  "m": "Alfabeto / Ghana",       "k": {"가", "나"}},
    {"id": 14, "j": "마차",  "r": "macha", "m": "Carrozza",               "k": {"마", "차"}},
    # ── From advanced syllables ───────────────────────────────────────────
    {"id": 15, "j": "고기",  "r": "gogi",  "m": "Carne",                  "k": {"고", "기"}},
    {"id": 16, "j": "소고기","r": "sogogi","m": "Carne di manzo",         "k": {"소", "고", "기"}},
    {"id": 17, "j": "미소",  "r": "miso",  "m": "Sorriso",                "k": {"미", "소"}},
    {"id": 18, "j": "노래",  "r": "norae", "m": "Canzone",                "k": {"노"}},
    {"id": 19, "j": "도시",  "r": "dosi",  "m": "Città",                  "k": {"도", "시"}},
    {"id": 20, "j": "모기",  "r": "mogi",  "m": "Zanzara",                "k": {"모", "기"}},
    {"id": 21, "j": "고도",  "r": "godo",  "m": "Altitudine",             "k": {"고", "도"}},
    {"id": 22, "j": "보고",  "r": "bogo",  "m": "Rapporto / Guardare",    "k": {"보", "고"}},
    {"id": 23, "j": "가수",  "r": "gasu",  "m": "Cantante",               "k": {"가"}},
    {"id": 24, "j": "미미",  "r": "mimi",  "m": "Insignificante",         "k": {"미"}},
    {"id": 25, "j": "누나",  "r": "nuna",  "m": "Sorella maggiore (di un maschio)", "k": {"누", "나"}},
    {"id": 26, "j": "두부",  "r": "dubu",  "m": "Tofu",                   "k": {"두", "부"}},
    {"id": 27, "j": "소시",  "r": "sosi",  "m": "Salsiccia (abbrev.)",    "k": {"소", "시"}},
    {"id": 28, "j": "나무",  "r": "namu",  "m": "Albero",                 "k": {"나", "무"}},
    {"id": 29, "j": "무기",  "r": "mugi",  "m": "Arma",                   "k": {"무", "기"}},
    {"id": 30, "j": "보도",  "r": "bodo",  "m": "Notizie / Marciapiede",  "k": {"보", "도"}},
]


def get_user_learned_syllables(db: Session, user: User) -> frozenset[str]:
    """Return frozenset of Hangul characters (front) the user has learned (srs_stage>=1)."""
    rows = (
        db.query(Card.front)
        .join(UserCard, Card.id == UserCard.card_id)
        .filter(
            UserCard.user_id == user.id,
            UserCard.srs_stage >= 1,
            Card.phase.in_(["jamo", "syllable"]),
        )
        .all()
    )
    return frozenset(r[0] for r in rows)


def get_zen_words(db: Session, user: User, exclude_id: Optional[int] = None) -> list[dict]:
    """
    Return vocab words whose characters are ALL in the user's learned set.
    Optionally exclude a word id (to avoid showing the same word twice).
    Words are randomised.
    """
    import random
    learned = get_user_learned_syllables(db, user)
    if not learned:
        return []

    available = [
        w for w in ZEN_VOCAB
        if w["k"].issubset(learned) and w["id"] != exclude_id
    ]
    random.shuffle(available)
    return available


def get_zen_word_by_id(word_id: int) -> Optional[dict]:
    """Look up a single vocab word from the in-memory list."""
    for w in ZEN_VOCAB:
        if w["id"] == word_id:
            return w
    return None
