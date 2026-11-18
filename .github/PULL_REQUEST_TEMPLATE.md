## 改动说明

<!-- 一句话说清这个 PR 解决什么问题 -->

## 改动类型

- [ ] 新功能（feat）
- [ ] 缺陷修复（fix）
- [ ] 重构（refactor）
- [ ] 文档（docs）
- [ ] 测试（test）
- [ ] 构建/CI（chore）

## 影响范围

<!-- 涉及哪些模块？是否有数据库迁移？是否需要改配置？ -->

- 数据库迁移：
- 配置变更：
- 兼容性影响：

## 自检清单

- [ ] `pytest` 通过（`cd deliverables/backend && python -m pytest`）
- [ ] `tsc --noEmit` 通过（`cd frontend && npx tsc --noEmit`）
- [ ] `vite build` 通过
- [ ] 涉及权限的改动，已跑 `work/audit_permissions.py`
- [ ] 涉及界面的改动，已跑对应 `work/audit_*.py`
- [ ] 没有提交 `.env`、密钥或真实账号
- [ ] 新逻辑已补测试，或说明为何不适用
