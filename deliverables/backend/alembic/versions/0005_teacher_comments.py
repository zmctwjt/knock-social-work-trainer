"""教师点评表

任务书"教师查看学员训练记录"只解决了"看得到"，教学闭环还缺"给出反馈"。
本表让教师能对某次训练写点评（含关注等级），学生在复盘页能看到。

为什么不做成必填：教师日常批量大，强制每条都点评会让人干脆不用。
点评是可选增强，有则展示、无则不打扰。

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teacher_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False, server_default="good"),
        sa.Column(
            "read_by_learner", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"], ["training_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["learner_id"], ["accounts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_teacher_comments_record_id", "teacher_comments", ["record_id"]
    )
    op.create_index(
        "ix_teacher_comments_teacher_id", "teacher_comments", ["teacher_id"]
    )
    op.create_index(
        "ix_teacher_comments_learner_id", "teacher_comments", ["learner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_comments_learner_id", table_name="teacher_comments")
    op.drop_index("ix_teacher_comments_teacher_id", table_name="teacher_comments")
    op.drop_index("ix_teacher_comments_record_id", table_name="teacher_comments")
    op.drop_table("teacher_comments")
