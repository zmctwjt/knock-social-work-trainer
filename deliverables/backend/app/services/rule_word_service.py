"""判定词表的可运行时覆盖层。

设计取舍：
- 基线词表仍是 `rules.py` 里的 9 张常量（162 条），保证"不查库也能判定"与
  "危机永不因库故障而失效"；
- 数据库只存**增量与禁用项**（`rule_words` 表），启动时加载进内存快照，
  管理端修改后重新加载，判定路径不做 IO；
- 危机词表只允许"追加"不允许"禁用"，避免误操作削弱安全边界。

这样既满足任务书"内容维护：维护判定词表"的要求，又不牺牲危机拦截的可靠性。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.domain import rules as rules_mod
from app.domain.enums import DimensionKey
from app.domain.models import RuleWord

#: 允许维护的词表分组 → 基线常量名。危机组只可追加（见 ALLOW_DISABLE）。
WORD_GROUPS: dict[str, str] = {
    "empathy": "EMPATHY_WORDS",
    "open_question": "OPEN_QUESTION_WORDS",
    "judge": "JUDGE_WORDS",
    "premature_advice": "PREMATURE_ADVICE_WORDS",
    "silence": "SILENCE_ACCOMPANY_WORDS",
    "off_topic": "OFF_TOPIC_WORDS",
    "crisis": "CRISIS_WORDS",
    "hopelessness": "HOPELESSNESS_WORDS",
    "toxic_positivity": "TOXIC_POSITIVITY_WORDS",
}

#: 危机与无望感两组承载安全边界，禁止通过接口禁用基线词
PROTECTED_GROUPS = {"crisis", "hopelessness"}

GROUP_LABELS: dict[str, str] = {
    "empathy": "同感与倾听",
    "open_question": "开放式提问",
    "judge": "评判",
    "premature_advice": "建议过早",
    "silence": "沉默陪伴",
    "off_topic": "离题",
    "crisis": "危机级",
    "hopelessness": "无望感",
    "toxic_positivity": "毒性积极",
}


def baseline(group: str) -> list[str]:
    """取基线词表（未叠加数据库增量）。"""
    attr = WORD_GROUPS.get(group)
    if attr is None:
        raise AppError.bad_request(f"未知词表分组：{group}")
    return list(getattr(rules_mod, attr))


class WordListOverlay:
    """内存快照：{group: 生效词表}。判定路径只读它，零 IO。"""

    def __init__(self) -> None:
        self._effective: dict[str, list[str]] = {}
        self._custom: list[dict[str, object]] = []
        self.loaded_at: datetime | None = None

    async def reload(self, session: AsyncSession) -> int:
        rows = (await session.execute(select(RuleWord))).scalars().all()
        disabled: dict[str, set[str]] = {}
        added: dict[str, list[str]] = {}
        custom: list[dict[str, object]] = []
        for row in rows:
            if row.enabled:
                added.setdefault(row.group, []).append(row.word)
            elif row.group in PROTECTED_GROUPS:
                # 受保护组忽略禁用，基线词继续生效
                continue
            else:
                disabled.setdefault(row.group, set()).add(row.word)
            if not row.is_baseline:
                custom.append(
                    {
                        "id": str(row.id),
                        "group": row.group,
                        "group_label": GROUP_LABELS.get(row.group, row.group),
                        "word": row.word,
                        "enabled": row.enabled,
                        "note": row.note or "",
                    }
                )
        effective: dict[str, list[str]] = {}
        for group in WORD_GROUPS:
            words = [w for w in baseline(group) if w not in disabled.get(group, set())]
            for extra in added.get(group, []):
                if extra not in words:
                    words.append(extra)
            effective[group] = words
        self._effective = effective
        self._custom = sorted(custom, key=lambda x: (str(x["group"]), str(x["word"])))
        self.loaded_at = datetime.now(UTC)
        _install(effective)
        return len(rows)

    def snapshot(self) -> dict[str, int]:
        return {g: len(w) for g, w in self._effective.items()}

    def custom_entries(self) -> list[dict[str, object]]:
        return list(self._custom)

    def effective(self, group: str) -> list[str]:
        return list(self._effective.get(group) or baseline(group))


def _install(effective: dict[str, list[str]]) -> None:
    """把生效词表替换进 `rules` 模块的常量。

    `match_local_rules` 等处直接引用模块级常量，替换列表对象是最小侵入的做法：
    判定逻辑无需改动，也不会在热路径引入查库。
    """
    for group, words in effective.items():
        attr = WORD_GROUPS[group]
        setattr(rules_mod, attr, list(words))


OVERLAY = WordListOverlay()


# ═══════════════════════════════════════════════════════════
# 管理端维护动作
# ═══════════════════════════════════════════════════════════


async def list_groups(session: AsyncSession) -> dict[str, object]:
    """列出全部分组的基线数、生效数与自定义条目。"""
    overlay_counts = OVERLAY.snapshot()
    return {
        "groups": [
            {
                "group": group,
                "label": GROUP_LABELS.get(group, group),
                "baseline": len(baseline(group)),
                "effective": overlay_counts.get(group, len(baseline(group))),
                "protected": group in PROTECTED_GROUPS,
            }
            for group in WORD_GROUPS
        ],
        "custom": OVERLAY.custom_entries(),
        "loaded_at": OVERLAY.loaded_at.isoformat() if OVERLAY.loaded_at else None,
    }


async def add_word(
    session: AsyncSession, *, group: str, word: str, note: str = ""
) -> dict[str, object]:
    if group not in WORD_GROUPS:
        raise AppError.bad_request(f"未知词表分组：{group}")
    cleaned = word.strip()
    if not cleaned:
        raise AppError.bad_request("词条不能为空")
    exists = (
        await session.execute(
            select(RuleWord).where(RuleWord.group == group, RuleWord.word == cleaned)
        )
    ).scalar_one_or_none()
    if exists is not None:
        if exists.enabled:
            raise AppError.conflict("该词条已存在")
        exists.enabled = True
        await session.commit()
    else:
        is_baseline = cleaned in baseline(group)
        session.add(
            RuleWord(
                id=uuid.uuid4(),
                group=group,
                word=cleaned,
                enabled=True,
                is_baseline=is_baseline,
                note=note.strip()[:200],
            )
        )
        await session.commit()
        if is_baseline:
            # 基线词被显式启用 → 清掉此前的禁用记录
            row = (
                await session.execute(
                    select(RuleWord).where(RuleWord.group == group, RuleWord.word == cleaned)
                )
            ).scalar_one()
            row.enabled = True
            await session.commit()
    await OVERLAY.reload(session)
    return {"group": group, "word": cleaned, "effective": len(OVERLAY.effective(group))}


async def disable_word(session: AsyncSession, *, group: str, word: str) -> dict[str, object]:
    """禁用词条。仅对非保护组生效；基线词记一条 enabled=False 覆盖。"""
    if group not in WORD_GROUPS:
        raise AppError.bad_request(f"未知词表分组：{group}")
    if group in PROTECTED_GROUPS:
        raise AppError.forbidden(f"{GROUP_LABELS.get(group, group)}组承载安全边界，禁止禁用")
    cleaned = word.strip()
    row = (
        await session.execute(
            select(RuleWord).where(RuleWord.group == group, RuleWord.word == cleaned)
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            RuleWord(
                id=uuid.uuid4(),
                group=group,
                word=cleaned,
                enabled=False,
                is_baseline=cleaned in baseline(group),
                note="管理端禁用",
            )
        )
    else:
        row.enabled = False
    await session.commit()
    await OVERLAY.reload(session)
    return {"group": group, "word": cleaned, "effective": len(OVERLAY.effective(group))}


async def remove_custom_word(session: AsyncSession, word_id: uuid.UUID) -> dict[str, object]:
    """彻底删除一条自定义词条（基线词不可删，只能禁用）。"""
    row = await session.get(RuleWord, word_id)
    if row is None:
        raise AppError.not_found("词条不存在")
    if row.is_baseline:
        raise AppError.bad_request("基线词条不能删除，可改为禁用")
    group, word = row.group, row.word
    await session.delete(row)
    await session.commit()
    await OVERLAY.reload(session)
    return {"group": group, "word": word, "deleted": True}


__all__ = [
    "GROUP_LABELS",
    "OVERLAY",
    "PROTECTED_GROUPS",
    "WORD_GROUPS",
    "WordListOverlay",
    "add_word",
    "baseline",
    "disable_word",
    "list_groups",
    "remove_custom_word",
    "DimensionKey",
]


async def public_wordbook() -> dict[str, object]:
    """公开的判定词表（学员端知识库「判定词表」用）。

    为什么单独做一个公开视图而不是复用管理端接口：
    管理端的 `list_groups` 只返回各组**数量**与自定义条目，从不返回基线词，
    因为它是给"维护者"看的。而任务书要求学员能"查阅判定词表"——
    学员要看的是**具体词条**，才知道哪些表达会被判为评判、建议过早等。

    危机 / 无望感受两组（PROTECTED_GROUPS）照常展示词条：
    识别风险表达本身就是社工训练内容（教材里也列了风险信号），
    隐藏反而与教学目标相悖；这两组只是不允许被接口禁用基线词。
    """
    groups: list[dict[str, object]] = []
    for group in WORD_GROUPS:
        words = OVERLAY.effective(group)
        groups.append(
            {
                "group": group,
                "label": GROUP_LABELS.get(group, group),
                "words": words,
                "count": len(words),
                "protected": group in PROTECTED_GROUPS,
            }
        )
    return {
        "groups": groups,
        "total": sum(int(g["count"]) for g in groups),
    }
