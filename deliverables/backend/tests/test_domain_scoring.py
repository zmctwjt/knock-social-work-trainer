"""评分领域逻辑：六维权重、规则底分、0.4/0.6 融合、弱点建议。"""

from __future__ import annotations

import pytest

from app.domain.enums import DimensionKey, Speaker
from app.domain.scoring import (
    BASE_SCORES,
    DIMENSION_ORDER,
    MERGE_RATIO,
    DialogMessage,
    RuleScoreInput,
    Utterance,
    collect_utterances,
    compute_rule_score,
    find_weakness,
    merge_scores,
    weighted_total,
)


def test_dimension_weights_sum_to_100():
    from app.domain.scoring import DIMENSIONS

    assert [item.key for item in DIMENSIONS] == list(DIMENSION_ORDER)
    assert sum(item.weight for item in DIMENSIONS) == 100
    assert MERGE_RATIO == {"rule": 0.4, "ai": 0.6}


def test_rule_score_covers_all_dimensions_and_range():
    scores = compute_rule_score(RuleScoreInput())
    assert set(scores) == set(DIMENSION_ORDER)
    assert all(0 <= value <= 100 for value in scores.values())
    assert set(scores) == set(BASE_SCORES)


def test_rule_score_reacts_to_judgement_utterance():
    base = compute_rule_score(RuleScoreInput())
    judged = compute_rule_score(
        RuleScoreInput(utterances=[Utterance("我觉得你应该马上去找份工作")])
    )
    assert judged[DimensionKey.EMPATHY] <= base[DimensionKey.EMPATHY]
    # 评判会同时扣伦理分并触发「见过评判」的硬封顶
    assert base[DimensionKey.ETHICS] == 70
    assert judged[DimensionKey.ETHICS] == 60


def test_weighted_total_equals_flat_score_for_uniform_values():
    scores = {key: 80 for key in DIMENSION_ORDER}
    assert weighted_total(scores) == 80


def test_weighted_total_is_weight_driven():
    high_empathy = {key: 60 for key in DIMENSION_ORDER} | {DimensionKey.EMPATHY: 100}
    assert weighted_total(high_empathy) > 60


def test_merge_uses_point_four_point_six():
    rule = {key: 60 for key in DIMENSION_ORDER}
    ai = {key: 80 for key in DIMENSION_ORDER}
    merged = merge_scores(rule, ai)
    assert merged.used_ai is True
    assert merged.missing == []
    assert all(value == 72 for value in merged.scores.values())


def test_merge_degrades_when_ai_missing_any_dimension():
    rule = {key: 60 for key in DIMENSION_ORDER}
    ai = {key: 80 for key in DIMENSION_ORDER if key is not DimensionKey.RISK}
    merged = merge_scores(rule, ai)
    assert merged.used_ai is False
    assert merged.missing == [DimensionKey.RISK]
    assert merged.scores == rule


def test_merge_without_ai_returns_rule_scores():
    rule = {key: 55 for key in DIMENSION_ORDER}
    merged = merge_scores(rule, None)
    assert merged.used_ai is False
    assert merged.scores == rule


def test_collect_utterances_skips_crisis_turns():
    messages = [
        DialogMessage(speaker=Speaker.CLIENT, text="我最近总失眠"),
        DialogMessage(speaker=Speaker.WORKER, text="听起来你很久没睡好了？"),
        DialogMessage(speaker=Speaker.WORKER, text="我想死", is_crisis=True),
    ]
    collected = collect_utterances(messages)
    assert collected.crisis_seen is True
    assert collected.worker_turns == 1
    assert len(collected.utterances) == 1


def test_collect_utterances_marks_hopelessness_recognized():
    messages = [
        DialogMessage(speaker=Speaker.CLIENT, text="活着没意思"),
        DialogMessage(speaker=Speaker.WORKER, text="你说活着没意思，是从什么时候开始的？"),
    ]
    collected = collect_utterances(messages)
    assert collected.hopeless_seen is True
    assert collected.hopeless_recognized is True


def test_find_weakness_points_to_lowest_dimension():
    scores = {key: 85 for key in DIMENSION_ORDER}
    scores[DimensionKey.QUESTION] = 40
    weakness = find_weakness(scores)
    assert weakness.dimension is DimensionKey.QUESTION
    assert weakness.score == 40
    assert weakness.name
    assert weakness.advice
    assert weakness.recommend_card


@pytest.mark.parametrize("value", [-20, 130])
def test_safe_scores_are_clamped(value):
    from app.domain.scoring import safe_score

    assert 0 <= safe_score(value, 60) <= 100
