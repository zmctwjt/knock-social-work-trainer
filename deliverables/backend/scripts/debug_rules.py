import sys

sys.path.insert(0, "deliverables/backend")

from app.domain.rules import is_vague_empathy, match_local_rules
from app.domain.scoring import RuleScoreInput, Utterance, compute_rule_score

cases = [
    "你就是太懒了",
    "我觉得你应该马上去找份工作",
    "你怎么看这件事？",
    "你是不是不想上学了？",
    "嗯。",
    "我理解你",
    "我理解你一个人撑着这个家的那种累",
    "今天天气不错",
]
for text in cases:
    m = match_local_rules(text)
    print(repr(text), "->", m.intent.value, m.risk_level.value, "call_ai=", m.should_call_ai,
          "deltas=", {k.value: v for k, v in m.effects.score_deltas.items()})
print("vague 1:", is_vague_empathy("我理解你", "理解"))
print("vague 2:", is_vague_empathy("我理解你一个人撑着这个家的那种累", "理解"))
print("base:", compute_rule_score(RuleScoreInput()))
print("judged:", compute_rule_score(RuleScoreInput(utterances=[Utterance("你就是太懒了")])))
print("advice:", compute_rule_score(RuleScoreInput(utterances=[Utterance("我觉得你应该马上去找份工作")])))
