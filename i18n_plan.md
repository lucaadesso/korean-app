# i18n Implementation Plan

1. **Database Update**:
   - Add `language` column to `User` model (default: "it").

2. **Translation Engine**:
   - Create `app/i18n.py` that loads JSON files from `app/locales/it.json` and `app/locales/en.json`.
   - Implement a simple `get_translator(lang: str)` function that returns a callable `t(key)`.

3. **Template Context**:
   - In `main.py` and other routers, instantiate `t = get_translator(user.language)` and pass it to `TemplateResponse` context as `t`.
   - In Jinja2 templates, replace `Testo` with `{{ t('section.key') }}`.

4. **Settings Page**:
   - Update `settings.html` to include a language selector (Italian / English).
   - Update POST `/settings` route to handle language changes.

5. **Template Extraction**:
   - Manually or via script, extract Italian strings from all `.html` files in `app/templates/` and Python files (`main.py`, `srs.py`).
   - Create the corresponding `en.json` file.
