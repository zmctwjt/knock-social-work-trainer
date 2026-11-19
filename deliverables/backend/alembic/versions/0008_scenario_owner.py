"""案例归属：区分内置案例与教师/管理员自建案例

背景：原先只有管理员能在「内容维护」里改案例，教师无法新增自己的案例。
现在支持教师也建案例，必须解决归属问题：

- `created_by` 为空 → 内置案例（课程自带 12 位），只有管理员能改；
- `created_by` 有值 → 某位教师/管理员自建，只有创建者与管理员能改。

不建外键约束：账号只停用不删除（`active=false`），但为了将来可能
的账号合并/清理留出余地，这里用可空 UUID 而不强绑 FK；查询时
按 `created_by` 过滤不影响正确性，删除场景由业务层保证。

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("created_by", sa.Uuid(), nullable=True),
    )
    # 教师端要按归属列自己的案例，加索引避免全表扫
    op.create_index(
        "ix_scenarios_created_by", "scenarios", ["created_by"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_scenarios_created_by", table_name="scenarios")
    op.drop_column("scenarios", "created_by")
