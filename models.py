DEFAULT_MODEL = "htdemucs"
QUALITY_MODEL = "htdemucs_ft"
SIX_STEM_MODEL = "htdemucs_6s"
REMOVABLE_STEMS = ("guitar", "piano")
FOUR_STEMS = ("vocals", "drums", "bass", "other")

MODEL_STEMS = {
    DEFAULT_MODEL: FOUR_STEMS,
    QUALITY_MODEL: FOUR_STEMS,
    SIX_STEM_MODEL: (*FOUR_STEMS, *REMOVABLE_STEMS),
}

MODEL_WEIGHTS = {
    DEFAULT_MODEL: (
        ("955717e8-8726e21a.th", "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"),
    ),
    QUALITY_MODEL: (
        ("f7e0c4bc-ba3fe64a.th", "ba3fe64ae8ef66ac9a4857222ce48efbdc5eb3ad375cb79dd13debee5aaa4066"),
        ("d12395a8-e57c48e6.th", "e57c48e6b0e38af4f7118d7bd08c49f0a0c0edf7d09143bdd902ea0d237303e6"),
        ("92cfc3b6-ef3bcb9c.th", "ef3bcb9c8b40d14ae5d51b6db2587339cc12c6b77c0be151ce6d69002e087bf2"),
        ("04573f0d-f3cf25b2.th", "f3cf25b222c4eed7cd49dd8b2c9597d50c18bd154090f7b919cfa5f93cf22c49"),
    ),
    SIX_STEM_MODEL: (
        ("5c90dfd2-34c22ccb.th", "34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd"),
    ),
}


def mix_name(excluded):
    return "_".join(f"no_{stem}" for stem in REMOVABLE_STEMS if stem in excluded)
