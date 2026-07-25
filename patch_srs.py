import re
import json
import os

with open("app/srs.py", "r", encoding="utf-8") as f:
    srs_content = f.read()

# Replace ZEN_VOCAB definition with JSON loading
vocab_match = re.search(r'ZEN_VOCAB\s*=\s*\[([\s\S]*?)\]\n', srs_content)
if not vocab_match:
    print("Could not find ZEN_VOCAB in srs.py")
else:
    # Actually, it's easier to just write the JSON file manually for the 30 words.
    pass

replacement_json_load = """import json
import os

ZEN_VOCAB_PATH = os.path.join(os.path.dirname(__file__), "data", "zen_vocab.json")
try:
    with open(ZEN_VOCAB_PATH, "r", encoding="utf-8") as f:
        ZEN_VOCAB = json.load(f)
    for w in ZEN_VOCAB:
        w["k"] = set(w["k"])
except FileNotFoundError:
    ZEN_VOCAB = []
"""

srs_content = re.sub(r'ZEN_VOCAB\s*=\s*\[[\s\S]*?\]\n', replacement_json_load, srs_content)

# Update get_zen_words
get_zen_words_new = """def get_zen_words(db: Session, user: User, exclude_id: Optional[int] = None) -> list[dict]:
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
"""

# Replace the original get_zen_words completely
srs_content = re.sub(
    r'def get_zen_words\(db: Session, user: User, exclude_id: Optional\[int\] = None\) -> list\[dict\]:[\s\S]*?(?=def get_zen_word_by_id)',
    get_zen_words_new + '\n',
    srs_content
)

# Replace the due cards shuffle
due_cards_new = """    cards = (
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
    return cards"""

srs_content = re.sub(
    r'return \(\s*db\.query\(UserCard\)[\s\S]*?\.all\(\)\s*\)',
    due_cards_new,
    srs_content
)

# Update chunking learn interval to datetime.now()
srs_content = srs_content.replace(
    'uc.due_date = datetime.now() + timedelta(minutes=10)',
    'uc.due_date = datetime.now() # Due immediately for the mini-review'
)

with open("app/srs.py", "w", encoding="utf-8") as f:
    f.write(srs_content)
