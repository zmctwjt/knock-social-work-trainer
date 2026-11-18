"""本地规则库：162 词表、危机硬拦截、语境豁免、8 步判定。"""

from __future__ import annotations

from app.domain.enums import Intent, RiskLevel
from app.domain.rules import (
    count_rule_words,
    describe_rule_tables,
    find_crisis_hits,
    is_toxic_positivity,
    is_vague_empathy,
    match_local_rules,
)


def test_rule_tables_cover_162_words():
    tables = describe_rule_tables()
    assert len(tables) == 9
    assert count_rule_words() == 162
    assert all(item["count"] > 0 for item in tables)


def test_crisis_wording_is_hard_blocked():
    result = match_local_rules("我真的不想活了，死了算了")
    assert result.risk_level is RiskLevel.SUICIDAL
    assert result.intent is Intent.CRISIS
    assert result.should_call_ai is False
    assert result.hit_words


def test_crisis_detection_survives_pronoun_normalization():
    # normalize() 会把「您」归一成「你」，但不得影响危机词命中
    assert find_crisis_hits("您想死吗") == ["想死"]
    assert find_crisis_hits("我想死") == ["想死"]
    assert not find_crisis_hits("今天天气不错")


def test_dialing_context_is_not_a_crisis():
    # 「打我」在致电语境下不是被害陈述，这是原实现里最容易被误判的一条
    assert find_crisis_hits("你可以打我电话，随时联系") == []
    assert match_local_rules("你可以打我电话").risk_level is RiskLevel.NONE


def test_cutting_context_is_not_a_crisis():
    assert find_crisis_hits("我拿刀切菜的时候手抖") == []
    assert find_crisis_hits("他拿刀威胁我") != []


def test_hopelessness_is_attention_level_not_hard_block():
    result = match_local_rules("活着没意思，每天就是熬日子")
    assert result.risk_level is RiskLevel.HOPELESSNESS
    assert result.should_call_ai is True


def test_local_intent_classification():
    assert match_local_rules("你怎么看这件事？").intent is Intent.OPEN_QUESTION
    assert match_local_rules("你是不是不想上学了？").intent is Intent.CLOSED_QUESTION
    assert match_local_rules("我觉得你应该马上去找份工作").intent is Intent.JUDGEMENT
    assert match_local_rules("我建议你去社区中心看看").intent is Intent.PREMATURE_ADVICE


def test_uncovered_text_should_ask_ai():
    result = match_local_rules("嗯。")
    assert result.should_call_ai is True


def test_vague_empathy_detection():
    # 第二个参数是命中的共情词：空泛与否看它后面 15 字内有没有具体内容
    assert is_vague_empathy("我理解你", "理解") is True
    assert is_vague_empathy("我理解你一个人撑着这个家的那种累", "理解") is False


def test_toxic_positivity_detection():
    assert is_toxic_positivity("别想太多，想开点") is True
    assert is_toxic_positivity("你说说看，最难受的是哪一刻") is False


def test_intent_effect_table_is_the_single_source_of_truth():
    from app.domain.rules import effects_for_intent

    assert effects_for_intent(Intent.CRISIS).score_deltas
    assert effects_for_intent(Intent.JUDGEMENT).score_deltas
    assert effects_for_intent(Intent.OFF_TOPIC).score_deltas == {}
