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
from datetime import date, timedelta, datetime
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
    uc.due_date      = datetime.now() + timedelta(days=uc.interval)
    uc.last_reviewed = date.today()
    uc.is_new        = False
    if uc.srs_stage < 2:
        uc.srs_stage = 2   # graduated from Learn → SRS
    return uc


def mark_card_learned(uc: UserCard) -> UserCard:
    """Mark a card as finished Learn Mode and ready for SRS."""
    uc.srs_stage = 1
    uc.due_date = datetime.now() # Due immediately for the mini-review
    uc.fast_lane = False
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

    # First, get all fast_lane=True cards for this group (unlimited)
    fast_lane_cards = (
        db.query(UserCard)
        .join(Card, UserCard.card_id == Card.id)
        .filter(
            UserCard.user_id    == user.id,
            UserCard.srs_stage  == 0,
            UserCard.fast_lane  == True,
            Card.phase          == phase,
            Card.group_name     == group,
        )
        .order_by(Card.id)
        .all()
    )

    if fast_lane_cards:
        return fast_lane_cards

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
    return (
        db.query(UserCard)
        .filter(
            UserCard.user_id == user.id,
            UserCard.introduced_date == date.today(),
        )
        .count()
    )


def get_due_cards(db: Session, user: User, limit: int = DAILY_CARD_CAP) -> list[UserCard]:
    """Returns up to `limit` UserCards due today (srs_stage >= 1, due today or overdue)."""
    cards = (
        db.query(UserCard)
        .filter(
            UserCard.user_id == user.id,
            UserCard.srs_stage >= 1,
            UserCard.due_date <= datetime.now(),
        )
        .order_by(UserCard.due_date)
        .limit(limit)
        .all()
    )
    import random
    random.shuffle(cards)
    return cards


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
import json
import os

ZEN_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "data", "zen_vocab.json")
try:
    with open(ZEN_VOCAB_PATH, "r", encoding="utf-8") as f:
        ZEN_VOCAB = json.load(f)
    for w in ZEN_VOCAB:
        w["k"] = set(w["k"])
except FileNotFoundError:
    ZEN_VOCAB = []



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
    import random
    from app.models import ZenWordProgress
    learned = get_user_learned_syllables(db, user)
    if not learned:
        return []

    progress_records = db.query(ZenWordProgress).filter(ZenWordProgress.user_id == user.id).all()
    progress_map = {p.word_id: p for p in progress_records}

    available = []
    for w in ZEN_VOCAB:
        if not w["k"].issubset(learned) or w["id"] == exclude_id:
            continue
            
        p = progress_map.get(w["id"])
        if p:
            import json
            try:
                arr = json.loads(p.step1_progress)
                step1 = sum(arr) if arr else 0
            except:
                step1 = 0
            step2 = p.step2_correct_count
        else:
            step1 = 0
            step2 = 0
        
        if step2 >= 10:
            if random.random() < 0.9:
                continue
            step = 2
        elif step1 >= 5:
            step = 2
        else:
            step = 1
            
        word_data = dict(w)
        word_data["step"] = step
        word_data["_step1_count"] = step1
        
        if step == 2:
            correct_chars = list(word_data["j"])
            distractors = list(learned)
            random.shuffle(distractors)
            
            symbols = list(correct_chars)
            while len(symbols) < 10:
                if distractors:
                    symbols.append(distractors.pop())
                else:
                    # In Korean, we can pick random basic syllables
                    symbols.append("가") # Fallback
            
            random.shuffle(symbols)
            word_data["symbols"] = symbols
            
        available.append(word_data)

    random.shuffle(available)
    available.sort(key=lambda x: (x["step"], x["_step1_count"]))
    return available

def record_zen_word_success(db: Session, user: User, word_id: int, step: int, match_idx: int = -1, total_variants: int = 1):
    from app.models import ZenWordProgress
    from datetime import datetime
    import json
    p = db.query(ZenWordProgress).filter(ZenWordProgress.user_id == user.id, ZenWordProgress.word_id == word_id).first()
    if not p:
        p = ZenWordProgress(user_id=user.id, word_id=word_id, step1_progress="[]", step2_correct_count=0)
        db.add(p)
    
    if step == 1:
        try:
            arr = json.loads(p.step1_progress)
        except:
            arr = []
        if len(arr) != total_variants:
            arr = [0] * total_variants
        if 0 <= match_idx < total_variants:
            arr[match_idx] += 1
        p.step1_progress = json.dumps(arr)
    elif step == 2:
        p.step2_correct_count += 1
    
    p.last_reviewed = datetime.now()
    db.commit()

def get_zen_word_by_id(word_id: int) -> Optional[dict]:
    """Look up a single vocab word from the in-memory list."""
    for w in ZEN_VOCAB:
        if w["id"] == word_id:
            return w
    return None

def enable_fast_lane(db: Session, user: User, phase: str, max_group_index: int) -> None:
    """Enables fast lane for cards up to the specified group index in a given phase."""
    groups = JAMO_GROUP_ORDER if phase == "jamo" else SYLLABLE_GROUP_ORDER
    allowed_groups = groups[:max_group_index + 1]
    
    ucs = (
        db.query(UserCard)
        .join(Card, UserCard.card_id == Card.id)
        .filter(UserCard.user_id == user.id, Card.phase == phase, Card.group_name.in_(allowed_groups))
        .all()
    )
    for uc in ucs:
        if uc.srs_stage == 0:
            uc.fast_lane = True
    db.commit()

def generate_placement_quiz(phase: str, num_questions: int = 5) -> list[dict]:
    import random
    if phase == "jamo":
        data = JAMO_VOWELS_DATA + JAMO_CONSONANTS_DATA
    else:
        data = SYLLABLE_BASIC_DATA + SYLLABLE_ADVANCED_DATA
        
    if not data:
        return []
    
    questions = random.sample(data, min(num_questions, len(data)))
    quiz = []
    all_romaja = list(set([item[2] for item in data]))
    
    for i, item in enumerate(questions):
        correct = item[2]
        wrong_options = random.sample([r for r in all_romaja if r != correct], 3)
        options = [correct] + wrong_options
        random.shuffle(options)
        quiz.append({
            "id": i,
            "char": item[0],
            "answer": correct,
            "options": options
        })
    return quiz
