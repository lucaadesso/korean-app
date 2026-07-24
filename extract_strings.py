import glob
import json
import re

texts_to_translate = {}

for filepath in glob.glob("app/templates/*.html"):
    with open(filepath, "r") as f:
        content = f.read()
    
    # We look for text nodes between > and <
    # We also have to be careful with jinja {{ ... }} and {% ... %}
    # Let's extract lines that have text
    
    # A safer way to find strings:
    # Just split by '>' and '<'
    parts = re.split(r'(>|<)', content)
    # parts: ['<', 'div class="foo"', '>', '  Hello  ', '<', '/div', '>']
    # Text nodes are the parts after '>' and before '<'
    
    for i in range(len(parts)):
        if parts[i] == '>' and i + 2 < len(parts) and parts[i+2] == '<':
            text = parts[i+1].strip()
            if text and not text.startswith('{{') and not text.startswith('{%') and not text.startswith('&'):
                # it's a visible string!
                key = text
                if key not in texts_to_translate:
                    texts_to_translate[key] = {
                        "file": filepath.split("/")[-1].split(".")[0],
                        "text": text
                    }

# Save to a json to inspect
with open("strings_extracted.json", "w") as f:
    json.dump(texts_to_translate, f, indent=2, ensure_ascii=False)
