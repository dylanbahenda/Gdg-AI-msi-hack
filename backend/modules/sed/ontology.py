from contracts.types import SoundClass


MACRO_TO_SOURCES: dict[SoundClass, list[str]] = {
    "clap": [
        "Clapping",
        "Slap, smack",
    ],
    "crying": [
        "Baby cry, infant cry",
        "Crying, sobbing",
        "Wail, moan",
        "Whimper",
    ],
    "broken_glass": [
        "Glass shatter",
        "Breaking",
        "Crockery breaking and smashing",
        "Smash, crash",
    ],
    "doorbell": [
        "Doorbell",
        "Ding-dong",
    ],
    "metal_sound": [
        "Clang",
        "Glass chink, clink",
        "Clatter",
        "Clunk",
        "Slam",
    ],
    "alarm": [
        "Alarm",
        "Alarm clock",
        "Fire alarm",
        "Smoke detector, smoke alarm",
        "Car alarm",
        "Beep, bleep",
        "Ambulance (siren)",
        "Police car (siren)",
        "Fire engine, fire truck (siren)",
        "Emergency vehicle",
        "Civil defense siren",
    ],
    "dog": [
        "Bark",
        "Dog",
        "Growling",
        "Howl",
        "Bow-wow",
        "Yip",
        "Whimper (dog)",
        "Pant (dog)",
    ],
    "scream": [
        "Screaming",
        "Shout",
        "Yell",
        "Bellow",
        "Children shouting",
    ],
    "knock": [
        "Knock",
        "Whack, thwack",
    ],
    "phone": [
        "Telephone bell ringing",
        "Ringtone",
        "Buzzer",
        "Cellphone buzz, vibrating alert",
    ],
}


SOURCE_THRESHOLDS: dict[str, float] = {
    # clap
    "Clapping": 0.01,
    "Slap, smack": 0.01,
    # crying
    "Baby cry, infant cry": 0.10,
    "Crying, sobbing": 0.10,
    "Wail, moan": 0.05,
    "Whimper": 0.05,
    # broken_glass
    "Glass shatter": 0.10,
    "Breaking": 0.10,
    "Crockery breaking and smashing": 0.10,
    "Smash, crash": 0.10,
    # doorbell
    "Doorbell": 0.10,
    "Ding-dong": 0.10,
    # metal_sound
    "Clang": 0.03,
    "Glass chink, clink": 0.03,
    "Clatter": 0.10,
    "Clunk": 0.10,
    "Slam": 0.20,
    # alarm
    "Alarm": 0.05,
    "Alarm clock": 0.05,
    "Fire alarm": 0.05,
    "Smoke detector, smoke alarm": 0.05,
    "Car alarm": 0.10,
    "Beep, bleep": 0.10,
    "Ambulance (siren)": 0.10,
    "Police car (siren)": 0.10,
    "Fire engine, fire truck (siren)": 0.10,
    "Emergency vehicle": 0.10,
    "Civil defense siren": 0.10,
    # dog
    "Bark": 0.10,
    "Dog": 0.10,
    "Growling": 0.10,
    "Howl": 0.10,
    "Bow-wow": 0.10,
    "Yip": 0.10,
    "Whimper (dog)": 0.10,
    "Pant (dog)": 0.10,
    # scream
    "Screaming": 0.02,
    "Shout": 0.02,
    "Yell": 0.05,
    "Bellow": 0.05,
    "Children shouting": 0.05,
    # knock
    "Knock": 0.10,
    "Whack, thwack": 0.10,
    # phone
    "Telephone bell ringing": 0.10,
    "Ringtone": 0.10,
    "Buzzer": 0.03,
    "Cellphone buzz, vibrating alert": 0.10,
}


MACRO_DETECTION_THRESHOLDS: dict[SoundClass, float] = {
    "clap": 0.09,
    "scream": 0.09,
}


ALL_SOURCES: list[str] = [
    src for sources in MACRO_TO_SOURCES.values() for src in sources
]

SOURCE_TO_MACRO: dict[str, SoundClass] = {
    src: macro for macro, sources in MACRO_TO_SOURCES.items() for src in sources
}

# Disjoint mapping invariant: each source maps to exactly one macro
assert len(SOURCE_TO_MACRO) == len(ALL_SOURCES), (
    "Duplicate source label across macros — sources must be disjoint."
)

# Threshold coverage invariant: every source has a threshold defined
assert set(SOURCE_THRESHOLDS.keys()) == set(ALL_SOURCES), (
    "SOURCE_THRESHOLDS must cover exactly ALL_SOURCES."
)
