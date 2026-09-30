"""QualityJudge.diagnose/assess robustness against malformed VLM output."""
from open_video.core.judge import QualityJudge


def _judge(result):
    j = QualityJudge(vision_fn=lambda frames, prompt: result)
    j.extract_frames = lambda *a, **k: ["f.png"]
    return j


def test_diagnose_none_missing_elements():
    assert QualityJudge().diagnose({"missing_elements": None}, "x") == []


def test_diagnose_string_missing_elements_is_one_issue():
    issues = QualityJudge().diagnose({"missing_elements": "a dog"}, "x")
    assert len(issues) == 1
    assert issues[0].type == "dropped_element" and "'a dog'" in issues[0].detail


def test_diagnose_ignores_non_str_items():
    issues = QualityJudge().diagnose({"missing_elements": ["cat", None, 3, {"a": 1}]}, "x")
    assert [i.detail for i in issues] == ["'cat' from prompt not visible"]


def test_assess_null_missing_elements_passes():
    v = _judge({"score": 0.9, "missing_elements": None}).assess("v.mp4", "p")
    assert v.verdict == "PASS"


def test_assess_diagnose_exception_yields_judge_error(monkeypatch):
    j = _judge({"score": 0.9})

    def boom(*a, **k):
        raise TypeError("x")

    monkeypatch.setattr(j, "diagnose", boom)
    v = j.assess("v.mp4", "p")
    assert v.verdict == "FAIL" and v.score == 0.0 and v.issues[0].type == "judge_error"
