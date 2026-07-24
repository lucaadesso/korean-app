import re

with open("app/main.py", "r") as f:
    content = f.read()

# Add import
content = content.replace("from app import srs", "from app import srs\nfrom app.i18n import get_translator")

# Helper to inject t = get_translator(user.language) and t=t
def inject_t(match):
    prefix = match.group(1)
    return f"{prefix}t = get_translator(user.language if user else 'it')\n    return templates.TemplateResponse"

def inject_t_context(match):
    before = match.group(1)
    return before + ', "t": t'

# We'll just do it manually for each route to be safe.
