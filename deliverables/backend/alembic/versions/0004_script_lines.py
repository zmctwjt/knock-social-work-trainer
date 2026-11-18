"""台词节点表

任务书"内容维护：维护台词节点"要求台词可维护。与词表同思路：基线台词
（`session_service.FALLBACK_REPLIES` 三档常量）继续留在代码里保证库不可用
时对话照常推进，本表只存管理端新增的台词。

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "script_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.String(length=16), nullable=True),
        sa.Column("emotion_bucket", sa.String(length=8), nullable=False, server_default="mid"),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_script_lines_bucket_order", "script_lines", ["emotion_bucket", "order_index"])
    op.create_index("ix_script_lines_scenario", "script_lines", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_script_lines_scenario", table_name="script_lines")
    op.drop_index("ix_script_lines_bucket_order", table_name="script_lines")
    op.drop_table("script_lines")
