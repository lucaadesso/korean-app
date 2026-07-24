import json

with open("app/locales/it.json", "r") as f:
    it_dict = json.load(f)

with open("app/locales/en.json", "r") as f:
    en_dict = json.load(f)

if "settings" not in it_dict:
    it_dict["settings"] = {}
if "settings" not in en_dict:
    en_dict["settings"] = {}

it_dict["settings"]["language"] = "Lingua"
en_dict["settings"]["language"] = "Language"

with open("app/locales/it.json", "w") as f:
    json.dump(it_dict, f, indent=2)

with open("app/locales/en.json", "w") as f:
    json.dump(en_dict, f, indent=2)

