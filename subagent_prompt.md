Your task is to implement internationalization (i18n) for the application located in the directory I will specify.
The i18n module `app/i18n.py` has already been created. The `User` model has already been updated with a `language` column. The DB has been migrated.

You must perform the following tasks:
1. **Update `main.py`**:
   - Import `get_translator` from `app.i18n`.
   - In EVERY route that returns a `TemplateResponse`, add `t = get_translator(user.language)` (if the user is logged in) or `t = get_translator("it")` (if not logged in, e.g., the login route).
   - Pass `t=t` in the context dictionary of EVERY `TemplateResponse`.
   - In `update_settings` (POST `/settings`), read the `language` form field and save it to `user.language`.

2. **Update Settings Template**:
   - In `app/templates/settings.html`, add a select dropdown for `language` with options `it` (Italiano) and `en` (English). Preselect `it` if `user.language == 'it'` else `en`.
   - Ensure the label for this field uses `t('settings.language')`.

3. **Extract and Replace Strings in Templates**:
   - Go through ALL `.html` files in `app/templates/`.
   - Replace every Italian text string with `{{ t('some.key') }}`. Be systematic (e.g., `dashboard.title`, `dashboard.welcome`, `learn.button_start`).
   - If there is a format string or dynamic variable, you can use something like `{{ t('dashboard.due_cards', count=due_count) }}` which the `t()` function supports via `kwargs`. But for simplicity, it's often easier to just do `{{ due_count }} {{ t('dashboard.cards') }}` if it gets too complex.

4. **Create Locales**:
   - Create the directory `app/locales/`.
   - Create `app/locales/it.json` containing a nested JSON structure for all the keys you used.
   - Create `app/locales/en.json` containing the English translation of `it.json`.

Please work thoroughly. There are ~14 templates. Do not skip any. Make sure to commit your changes with git when you are done.
