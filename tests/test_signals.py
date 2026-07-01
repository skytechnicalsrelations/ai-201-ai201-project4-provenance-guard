"""Independent tests for the detection signals and confidence scoring (M4).

Run with:  python -m pytest test_signals.py -v   (or: python test_signals.py)

These exercise each signal *standalone* and the combined scorer against the four
reference inputs from planning.md, asserting each lands in its intuitive band.
Signal 1 hits the live Groq API, so these are integration-style checks, not pure
unit tests -- they need GROQ_API_KEY set and may shift by a few hundredths run to
run (the borderline bands are deliberately near 0.70).
"""

from scoring import attribution_band, classify, combine_confidence
from signals import run_llm_signal, run_stylometric_signal

# (name, text, expected_band) -- the M4 calibration set from planning.md
REFERENCE_INPUTS = [
    (
        "clear-AI",
        "Artificial intelligence represents a transformative paradigm shift in modern "
        "society. It is important to note that while the benefits of AI are numerous, it "
        "is equally essential to consider the ethical implications. Furthermore, "
        "stakeholders across various sectors must collaborate to ensure responsible "
        "deployment.",
        "likely_ai",
    ),
    (
        "clear-human",
        "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
        "the broth was fine but they put WAY too much sodium in it and i was thirsty for "
        "like three hours after. my friend got the spicy version and said it was better. "
        "probably wont go back unless someone drags me there",
        "likely_human",
    ),
    (
        "formal-human",
        "The relationship between monetary policy and asset price inflation has been "
        "extensively studied in the literature. Central banks face a fundamental tension "
        "between their mandate for price stability and the unintended consequences of "
        "prolonged low interest rates on equity and real estate valuations.",
        "uncertain",
    ),
    (
        "lightly-edited-AI",
        "Ive been thinking a lot about remote work lately. There are genuine tradeoffs "
        "flexibility and no commute on one side, isolation and blurred work-life "
        "boundaries on the other. Studies show productivity varies widely by individual "
        "and role type.",
        "uncertain",
    ),
]


# --- Confidence scoring: pure, deterministic, no network ---------------------


def test_combine_formula_matches_spec():
    # confidence = 0.6*llm + 0.4*stylometric
    assert abs(combine_confidence(1.0, 0.0) - 0.6) < 1e-9
    assert abs(combine_confidence(0.0, 1.0) - 0.4) < 1e-9
    assert abs(combine_confidence(0.5, 0.5) - 0.5) < 1e-9


def test_band_thresholds_match_spec():
    # bands are NOT a 0.5 flip: human <0.35, uncertain <0.70, else AI
    assert attribution_band(0.349) == "likely_human"
    assert attribution_band(0.350) == "uncertain"
    assert attribution_band(0.510) == "uncertain"  # spec's "0.51 is not AI" case
    assert attribution_band(0.699) == "uncertain"
    assert attribution_band(0.700) == "likely_ai"


def test_short_input_guard_forces_uncertain():
    # A score that would be a confident AI call is downgraded when is_short.
    confident = classify(0.95, 0.95, is_short=False)
    guarded = classify(0.95, 0.95, is_short=True)
    assert confident.attribution == "likely_ai"
    assert guarded.attribution == "uncertain"
    # confidence number is preserved either way
    assert confident.confidence == guarded.confidence


# --- Signal 2 standalone: deterministic structural checks -------------------


def test_stylometric_signal_is_standalone_and_bounded():
    # Pure Python, no Signal 1 input; score stays in [0, 1].
    for _, text, _ in REFERENCE_INPUTS:
        result = run_stylometric_signal(text)
        assert 0.0 <= result.stylometric_score <= 1.0
        for sub in (
            result.norm_sentence_length_variance,
            result.norm_type_token_ratio,
            result.norm_punctuation,
        ):
            assert 0.0 <= sub <= 1.0


def test_stylometric_flags_short_input():
    assert run_stylometric_signal("Old pond. A frog jumps in. Splash.").is_short
    long_text = REFERENCE_INPUTS[1][1]  # the casual human paragraph
    assert not run_stylometric_signal(long_text).is_short


# --- End-to-end: both signals -> band (needs live Groq) ---------------------


def test_reference_inputs_land_in_expected_bands():
    for name, text, expected in REFERENCE_INPUTS:
        sty = run_stylometric_signal(text)
        llm = run_llm_signal(text)
        result = classify(llm.llm_score, sty.stylometric_score, is_short=sty.is_short)
        assert result.attribution == expected, (
            f"{name}: got {result.attribution} @ conf={result.confidence} "
            f"(llm={llm.llm_score}, sty={round(sty.stylometric_score, 3)})"
        )


if __name__ == "__main__":
    # Allow running without pytest: execute every test_* function and report.
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(funcs) - failures}/{len(funcs)} passed")
    raise SystemExit(1 if failures else 0)
