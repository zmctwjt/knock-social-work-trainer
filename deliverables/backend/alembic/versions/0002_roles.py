"""多角色能力：账号归属教师字段

教师端需要"名下学员"归属关系。本期用 `accounts.teacher_id` 自引用实现简易归属，
二期引入独立班级实体时迁移到此列的 `class_id`（见 05 章 5.4 节非目标说明）。

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch:
        batch.add_column(sa.Column("teacher_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_accounts_teacher_id",
            "accounts",
            ["teacher_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_accounts_teacher", ["teacher_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch:
        batch.drop_index("ix_accounts_teacher")
        batch.drop_constraint("fk_accounts_teacher_id", type_="foreignkey")
        batch.drop_column("teacher_id")
