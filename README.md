# 한국어 — Korean Learning App

Un'app gamificata per imparare il coreano (Hangul) con SRS adattivo, costruita con FastAPI + HTMX.

## Struttura

```
korean-app/
├── app/
│   ├── main.py          # FastAPI routes & app config
│   ├── auth.py          # Google OAuth2
│   ├── database.py      # SQLAlchemy / SQLite
│   ├── models.py        # ORM models
│   ├── srs.py           # SM-2 SRS logic + dati coreani
│   ├── static/
│   │   └── css/style.css
│   └── templates/       # Jinja2 templates
│       ├── base.html
│       ├── login.html
│       ├── dashboard.html
│       ├── learn_home.html / learn_card.html / learn_done.html
│       ├── review_start.html / review.html / review_done.html
│       ├── zen_mode.html / zen_word_puzzle.html / zen_word_result.html
│       └── settings.html
├── systemd/
│   ├── korean-app.service      # Systemd service (porta 8016)
│   └── nginx-korean-app.conf   # Nginx reverse proxy
├── .env                         # Variabili d'ambiente (non committare!)
├── .env.example                 # Template .env
└── requirements.txt
```

## Setup rapido

### 1. Configura `.env`

```bash
cp .env.example .env
# Modifica .env con le tue credenziali Google OAuth2 e SECRET_KEY
nano .env
```

### 2. Crea il venv (se non esiste)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Test in locale

```bash
set -a; source .env; set +a
venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8016 --reload
```

### 4. Deploy con systemd

```bash
sudo cp systemd/korean-app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable korean-app
sudo systemctl start korean-app
sudo systemctl status korean-app
```

### 5. Nginx reverse proxy

```bash
sudo cp systemd/nginx-korean-app.conf /etc/nginx/sites-available/korean-app
# Modifica il dominio nel file
sudo nano /etc/nginx/sites-available/korean-app
sudo ln -s /etc/nginx/sites-available/korean-app /etc/nginx/sites-enabled/korean-app
sudo nginx -t && sudo systemctl reload nginx
```

### 6. SSL con Certbot

```bash
sudo certbot --nginx -d korean.yourdomain.com
```

## Contenuto didattico

### Jamo (자모) — 24 carte
- **Vowels (모음)** — 10 vocali: ㅏ ㅑ ㅓ ㅕ ㅗ ㅛ ㅜ ㅠ ㅡ ㅣ
- **Consonants (자음)** — 14 consonanti: ㄱ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ

### Sillabe (음절) — 28 carte
- **Basic** — 14 sillabe con ㅏ: 가 나 다 라 마 바 사 아 자 차 카 타 파 하
- **Advanced** — 14 sillabe con ㅗ/ㅜ/ㅣ: 고 구 기 노 누 니 도 두 모 무 미 보 소 시

### Zen Mode — Parole coreane
30 parole coreane con caratteri sbloccabili progressivamente.

## Google OAuth2 Setup

1. Vai su [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuovo progetto
3. Abilita "Google People API"
4. Crea credenziali OAuth 2.0 (Web application)
5. Aggiungi URI di reindirizzamento: `https://tuodominio.com/auth/callback`
6. Copia Client ID e Client Secret in `.env`

## Differenze dalla versione giapponese

| | Japanese App | Korean App |
|---|---|---|
| Porta | 8015 | 8016 |
| Database | japanese_app.db | korean_app.db |
| Font | Noto Sans JP | Noto Sans KR |
| Colori | Violet/Sakura Pink | Taegukgi Blue/Red |
| Fase 1 | Hiragana + Katakana | Jamo (자모) |
| Fase 2 | Vocaboli | Sillabe + Vocaboli |
| TTS | ja-JP | ko-KR |
