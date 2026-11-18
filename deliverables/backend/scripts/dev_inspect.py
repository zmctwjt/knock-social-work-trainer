"""开发期自检脚本：导入全部模块并打印关键签名，供人工核对。

不属于生产代码，放在 scripts/ 下，不参与 app 包导入。
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MODULES = [
    "app.core.config",
    "app.core.context",
    "app.core.errors",
    "app.core.logging",
    "app.core.metrics",
    "app.core.middleware",
    "app.core.ratelimit",
    "app.core.deps",
    "app.domain.enums",
    "app.domain.models",
    "app.domain.schemas",
    "app.domain.rules",
    "app.domain.scoring",
    "app.domain.crisis",
    "app.infra.db",
    "app.infra.session",
    "app.infra.redis",
    "app.infra.cache",
    "app.prompts.base",
    "app.prompts.intent",
    "app.prompts.persona",
    "app.prompts.score",
    "app.prompts.debrief",
    "app.services.llm.base",
    "app.services.llm.openai_compat",
    "app.services.llm.zhipu",
    "app.services.llm.breaker",
    "app.services.llm.quota",
    "app.services.llm.router",
    "app.services.llm.usage",
    "app.services.audit_service",
    "app.services.ai_gateway",
]

failures = 0
for name in MODULES:
    try:
        importlib.import_module(name)
        print(f"OK   {name}")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")

if failures:
    raise SystemExit(1)

targets = {
    "app.domain.scoring": ["compute_rule_score", "collect_utterances", "merge_scores", "find_weakness", "build_marks"],
    "app.domain.crisis": ["classify_risk", "build_crisis_card", "build_suggestion", "hopelessness_hint"],
    "app.domain.rules": ["match_local_rules", "find_crisis_hits"],
    "app.prompts.intent": ["build_intent_prompt", "parse_intent"],
    "app.prompts.persona": ["build_persona_prompt", "parse_persona", "is_low_quality_persona"],
    "app.prompts.score": ["build_score_prompt", "parse_score"],
    "app.prompts.debrief": ["build_debrief_prompt", "parse_debrief"],
    "app.services.llm.router": ["ModelRouter"],
}

for module_name, symbols in targets.items():
    module = importlib.import_module(module_name)
    print(f"\n== {module_name}")
    for symbol in symbols:
        obj = getattr(module, symbol)
        try:
            print(f"  {symbol}{inspect.signature(obj)}")
        except (TypeError, ValueError):
            print(f"  {symbol}: {obj}")

print("\n== dataclasses")
for module_name, symbols in targets.items():
    module = importlib.import_module(module_name)
    for symbol in symbols:
        obj = getattr(module, symbol)
        if inspect.isclass(obj) and dataclasses.is_dataclass(obj):
            print(f"  {module_name}.{symbol}: {[f.name for f in dataclasses.fields(obj)]}")

# schemas 字段
import app.domain.schemas as schemas  # noqa: E402
print("\n== schemas")
for symbol in ("AiMeta", "TurnOut", "SessionOut", "SessionDetailOut", "StatsMeOut", "HeatmapOut", "DebriefOut", "ScoringOut", "ScenarioOut"):
    obj = getattr(schemas, symbol)
    fields = getattr(obj, "model_fields", {})
    print(f"  {symbol}: {list(fields)}")
