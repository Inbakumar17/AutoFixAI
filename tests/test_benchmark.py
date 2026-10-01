"""Guards that keep the benchmark trustworthy (they do not assert a success rate)."""

from benchmark.cases import CASES, CONTROLS
from benchmark.run_benchmark import evaluate_control, validate_corpus


def test_corpus_is_well_formed():
    validate_corpus()  # every reference runs and is static-issue free
    ids = [c.id for c in CASES + CONTROLS]
    assert len(ids) == len(set(ids))


def test_no_false_positives_on_controls():
    assert all(evaluate_control(c)["unchanged"] for c in CONTROLS)
