import glob, re

for f in glob.glob("app/templates/*.html"):
    with open(f) as file:
        content = file.read()
    # Find text between tags
    texts = re.findall(r'>([^<]+)<', content)
    cleaned = [t.strip() for t in texts if t.strip()]
    if cleaned:
        print(f"\n--- {f} ---")
        for t in set(cleaned):
            if not t.startswith('{{') and not t.startswith('{#') and len(t) > 1:
                print(t)
