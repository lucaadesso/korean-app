import glob, json, re, os

it_dict = {}
en_dict = {}

def slugify(text, prefix, counter):
    words = text.split()[:3]
    slug = "_".join(words).lower()
    slug = re.sub(r'[^a-z0-9_]', '', slug)
    if not slug:
        slug = "text"
    return f"{prefix}.{slug}_{counter}"

for filepath in glob.glob("app/templates/*.html"):
    with open(filepath, "r") as f:
        content = f.read()
    
    filename = os.path.basename(filepath).split('.')[0]
    it_dict[filename] = {}
    en_dict[filename] = {}
    
    # Hide scripts and styles
    scripts = []
    def hide_script(m):
        scripts.append(m.group(0))
        return f"__SCRIPT_{len(scripts)-1}__"
    content = re.sub(r'<script.*?>.*?</script>', hide_script, content, flags=re.DOTALL)
    
    styles = []
    def hide_style(m):
        styles.append(m.group(0))
        return f"__STYLE_{len(styles)-1}__"
    content = re.sub(r'<style.*?>.*?</style>', hide_style, content, flags=re.DOTALL)

    counter = 1
    def replacer(match):
        global counter
        text = match.group(1)
        stripped = text.strip()
        
        if not stripped or '{' in stripped or '}' in stripped or '&' in stripped:
            return match.group(0)
            
        if not re.search(r'[a-zA-Z]', stripped):
            return match.group(0)
            
        key_full = slugify(stripped, filename, counter)
        key_local = key_full.split('.')[1]
        counter += 1
        
        it_dict[filename][key_local] = stripped
        en_dict[filename][key_local] = stripped + " (EN)"
        
        before = text[:text.find(stripped)]
        after = text[text.find(stripped) + len(stripped):]
        return f">{before}{{{{ t('{key_full}') }}}}{after}<"
        
    content = re.sub(r'>([^<]+)<', replacer, content)
    
    # Restore scripts and styles
    for i, s in enumerate(scripts):
        content = content.replace(f"__SCRIPT_{i}__", s)
    for i, s in enumerate(styles):
        content = content.replace(f"__STYLE_{i}__", s)
        
    with open(filepath, "w") as f:
        f.write(content)

os.makedirs("app/locales", exist_ok=True)
with open("app/locales/it.json", "w") as f:
    json.dump(it_dict, f, indent=2)
with open("app/locales/en.json", "w") as f:
    json.dump(en_dict, f, indent=2)

print("Done")
