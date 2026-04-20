import re

def revert_terms(filepath):
    with open(filepath, "r") as f:
        text = f.read()

    # Revert SameHall to SameRoom
    text = re.sub(r"\bSameHall\b", "SameRoom", text)
    
    # Revert SameLecture to SameClass
    text = re.sub(r"\bSameLecture\b", "SameClass", text)

    # In README.md: "for each lecture-hall pair." referring to ITC 2019
    text = re.sub(r"\blecture-hall pair\b", "class-room pair", text)
    
    with open(filepath, "w") as f:
        f.write(text)

revert_terms("main.tex")
revert_terms("README.md")
