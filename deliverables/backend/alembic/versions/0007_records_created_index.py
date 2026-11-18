"""训练记录的时间索引

起因：平台级统计（管理端热力图、平台趋势）按 `created_at` 做范围扫描，
不涉及 owner_id。现有复合索引 `ix_records_owner_created(owner_id, created_at)`
最左列是 owner_id，无法服务纯时间范围查询——EXPLAIN 显示 MySQL 退化为
全索引扫描（type=index + Using where），数据量上来后是性能隐患。

因此单独为 created_at 建索引，让平台级查询能走 range 扫描。

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_records_created_at", "training_records", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_records_created_at", table_name="training_records")
