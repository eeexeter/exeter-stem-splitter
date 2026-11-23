DEFAULT_MODEL = "htdemucs"
SIX_STEM_MODEL = "htdemucs_6s"
REMOVABLE_STEMS = ("guitar", "piano")

MODEL_STEMS = {
    DEFAULT_MODEL: ("vocals", "drums", "bass", "other"),
    SIX_STEM_MODEL: ("vocals", "drums", "bass", "other", *REMOVABLE_STEMS),
}

MODEL_WEIGHTS = {
    DEFAULT_MODEL: (
        "955717e8-8726e21a.th",
        "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4",
    ),
    SIX_STEM_MODEL: (
        "5c90dfd2-34c22ccb.th",
        "34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd",
    ),
}


def mix_name(excluded):
    return "_".join(f"no_{stem}" for stem in REMOVABLE_STEMS if stem in excluded)
