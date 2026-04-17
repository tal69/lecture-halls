import re

def replace_terminology(filepath):
    with open(filepath, "r") as f:
        text = f.read()

    # Introduction explanation
    intro_orig = r"Universities and colleges often determine the courses timetable well before they assign lectures to specific halls\."
    intro_new = (
        "Universities and colleges often determine the course timetable well before they assign lectures to specific halls. "
        "Throughout this paper, we use the term \\emph{hall} (or \\emph{lecture hall}) to refer generically to any space used for academic activity, whether it is a traditional lecture theater, a seminar room, or a laboratory. "
        "Similarly, we use the term \\emph{lecture} to refer to any scheduled academic activity, encompassing regular lectures, tutorials, or practical sessions."
    )
    if "Throughout this paper, we use the term" not in text:
        text = text.replace(
            "Universities and colleges often determine the courses timetable well before they assign lectures to specific halls.",
            intro_new
        )

    # We need to do replacements carefully.
    
    # 1. Classes / Class -> Lectures / Lecture
    # Case-sensitive function
    def repl_class(m):
        word = m.group(1)
        if word == "class": return "lecture"
        if word == "Class": return "Lecture"
        if word == "classes": return "lectures"
        if word == "Classes": return "Lectures"
        if word == "class-room": return "lecture-hall"
        if word == "Class-room": return "Lecture-hall"
        if word == "SameClass": return "SameLecture"
        return word

    text = re.sub(r"\b(class|Class|classes|Classes|class-room|Class-room|SameClass)\b", repl_class, text)
    
    # 2. Classrooms / Classroom -> Lecture halls / Lecture hall
    def repl_classroom(m):
        word = m.group(1)
        if word == "classroom": return "lecture hall"
        if word == "Classroom": return "Lecture hall"
        if word == "classrooms": return "lecture halls"
        if word == "Classrooms": return "Lecture halls"
        return word

    text = re.sub(r"\b(classroom|Classroom|classrooms|Classrooms)\b", repl_classroom, text)
    
    # 3. Rooms / Room -> Halls / Hall
    def repl_room(m):
        word = m.group(1)
        if word == "room": return "hall"
        if word == "Room": return "Hall"
        if word == "rooms": return "halls"
        if word == "Rooms": return "Halls"
        if word == "SameRoom": return "SameHall"
        return word
        
    text = re.sub(r"\b(room|Room|rooms|Rooms|SameRoom)\b", repl_room, text)

    with open(filepath, "w") as f:
        f.write(text)

replace_terminology("main.tex")
replace_terminology("README.md")
