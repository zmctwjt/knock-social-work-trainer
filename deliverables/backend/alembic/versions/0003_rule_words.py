"""判定词表运行时覆盖表

任务书"内容维护：维护台词节点、技巧卡与判定词表"要求词表可维护。
但危机拦截必须不依赖数据库可用性，因此基线 162 条仍留在代码里
（`app/domain/rules.py`），本表只存增量与禁用记录，启动时加载进内存快照
（见 `app/services/rule_word_service.py`）。

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_words",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group", sa.String(length=32), nullable=False),
        sa.Column("word", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group", "word", name="uq_rule_words_group_word"),
    )
    op.create_index("ix_rule_words_group_enabled", "rule_words", ["group", "enabled"])


def downgrade() -> None:
    op.drop_index("ix_rule_words_group_enabled", table_name="rule_words")
    op.drop_table("rule_words")
