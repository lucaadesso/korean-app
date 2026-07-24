import re

def main():
    with open("app/main.py", "r") as f:
        content = f.read()

    # Add import
    if "get_translator" not in content:
        content = content.replace("from app import srs", "from app import srs\nfrom app.i18n import get_translator")

    # update_settings reading language
    old_update = """    user.target_daily_minutes   = minutes
    user.target_daily_new_cards = new_cards
    db.commit()"""
    new_update = """    user.target_daily_minutes   = minutes
    user.target_daily_new_cards = new_cards
    language = form.get("language")
    if language in ["it", "en"]:
        user.language = language
    db.commit()"""
    content = content.replace(old_update, new_update)

    # Replace TemplateResponse calls
    lines = content.split('\n')
    out = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        if "return templates.TemplateResponse" in line:
            indent = line[:len(line) - len(line.lstrip())]
            # insert t = ...
            out.append(f"{indent}t = get_translator(user.language if user else 'it')")
            
            # if context is on the same line
            if "{" in line:
                line = line.replace("{", '{"t": t, ', 1)
                out.append(line)
            else:
                out.append(line)
                # Next line should contain {
                i += 1
                next_line = lines[i]
                if "{" in next_line:
                    next_line = next_line.replace("{", '{"t": t, ', 1)
                out.append(next_line)
        else:
            out.append(line)
            
        i += 1

    with open("app/main.py", "w") as f:
        f.write('\n'.join(out))

if __name__ == "__main__":
    main()
