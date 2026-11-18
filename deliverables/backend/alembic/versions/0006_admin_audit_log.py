"""管理操作审计表

此前账号启停、内容增删只改了数据，没有留痕：出问题时无法回答
"谁在什么时候停了这个账号""这个词条是谁删的"。

与 ai_audit_log 的分工：
- ai_audit_log 记**模型调用**（合规、成本、降级排查）
- admin_audit_log 记**人对数据的改动**（追责、回滚依据）

刻意不记录修改前后的完整对象：账号表含口令哈希、内容表可能含
未公开素材，日志本身不应成为新的泄露面。只记关键字段摘要。

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=64), nullable=False,
                  server_default=""),
        sa.Column("actor_role", sa.String(length=16), nullable=False,
                  server_default=""),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False,
                  server_default=""),
        sa.Column("target_id", sa.String(length=64), nullable=False,
                  server_default=""),
        sa.Column("summary", sa.String(length=255), nullable=False,
                  server_default=""),
        sa.Column("request_id", sa.String(length=64), nullable=False,
                  server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_log_actor_id", "admin_audit_log", ["actor_id"])
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.create_index("ix_admin_audit_created_at", "admin_audit_log", ["created_at"])
    op.create_index(
        "ix_admin_audit_target", "admin_audit_log", ["target_type", "target_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_target", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_actor_id", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
