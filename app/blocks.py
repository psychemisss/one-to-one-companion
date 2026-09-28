# (key, default minutes). Titles and purposes live in i18n as block.<key>.title / .purpose
BLOCKS = {
    "regular": [
        ("checkin", 5),
        ("review", 5),
        ("their_topics", 15),
        ("work", 10),
        ("growth", 10),
        ("team", 5),
        ("feedback", 5),
        ("wrapup", 5),
    ],
    "first": [
        ("background", 10),
        ("motivation", 10),
        ("communication_prefs", 10),
        ("feedback_prefs", 10),
        ("career_aspirations", 15),
        ("wrapup", 5),
    ],
}

ALL_BLOCK_KEYS = list(dict.fromkeys(k for blocks in BLOCKS.values() for k, _ in blocks))

# First-session notes copied into empty engineer profile fields when the session finishes
FIRST_SESSION_PREFILL = {
    "communication_prefs": "communication_prefs",
    "feedback_prefs": "feedback_prefs",
    "career_aspirations": "goals",
    "motivation": "profile_notes",
}
