"""Planner.plan_from_concept / plan_from_shots: shot counts, durations, modes, seeds."""
import pytest

from open_video.core.planner import Planner


@pytest.mark.parametrize("target,expected", [
    (15, [15.0]), (20, [15.0, 5.0]), (30, [15.0, 15.0]), (45, [15.0, 15.0, 15.0]),
])
def test_shot_counts_and_durations(target, expected):
    plan = Planner().plan_from_concept("c", target)
    assert [s.duration_s for s in plan.shots] == expected
    assert sum(s.duration_s for s in plan.shots) == pytest.approx(target)
    assert plan.target_duration_s == target
    assert plan.metadata["n_shots"] == len(expected)
    assert len(plan.transitions) == len(expected) - 1


def test_modes_and_seeds():
    plan = Planner().plan_from_concept("c", 45)
    assert [s.mode for s in plan.shots] == ["t2v", "i2v", "i2v"]
    assert [s.seed for s in plan.shots] == [42, 43, 44]
    assert [s.scene_id for s in plan.shots] == [1, 2, 3]


@pytest.mark.parametrize("target", [0, -5])
def test_non_positive_duration_gives_empty_plan(target):
    plan = Planner().plan_from_concept("c", target)
    assert plan.shots == [] and plan.transitions == []


def test_plan_from_shots_defaults():
    plan = Planner().plan_from_shots([{"prompt": "a"}, {"prompt": "b", "duration": 5, "mode": "flf2v", "seed": 7}])
    a, b = plan.shots
    assert (a.mode, a.duration_s, a.seed, a.scene_id) == ("t2v", 10.0, 42, 1)
    assert (b.mode, b.duration_s, b.seed, b.scene_id) == ("flf2v", 5, 7, 2)
    assert plan.target_duration_s == 15 and len(plan.transitions) == 1
    assert plan.concept == "(manual plan)"
