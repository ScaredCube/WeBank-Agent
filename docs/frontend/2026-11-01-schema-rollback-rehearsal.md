# 第十九批 · 隔离数据库升级与回滚演练

日期：2026-11-01
分支：`feature/ip-object-workspace`

## 交付
新增 `backend/scripts/rehearse_chat_schema.py`，可运行：

```powershell
cd backend
uv run --group dev python scripts/rehearse_chat_schema.py --json
```

该命令**不接受正式数据库路径**，自建临时 SQLite 旧版数据库和合成用户、会话、消息；运行与第十八批相同的 `apply_additive_chat_schema` 升级代码。检查旧数据、升级前备份、请求 ID 唯一约束、重复升级不产生额外备份。再把备份还原到新临时文件，精确比对升级前后备份的 schema 与数据，并执行 SQLite 完整性检查。

独立测试：`backend/tests/test_chat_schema_rehearsal.py`；覆盖全流程、覆盖已有目标文件被拒绝、无备份文件时被拒绝。

## 验证
- 隔离工具输出：`result=PASS`，九项检查通过，`production_database_modified=false`。
- 迁移、幂等相关测试：`13/13` 通过。
- 本轮不发起 TokenDance 请求、不修改真实数据库、不启动新后端，也不重启原有 8000/5189。
- 首次在本地创建的 `backend/.venv` 为 uv 临时依赖环境（Git 不跟踪），不包含用户 API Key。

## 尚未宣称完成的内容
此脚本是**两张新增表的 SQLite 离线演练**。尚未执行团队真实数据库维护、真实数据备份恢复、PostgreSQL 迁移、线上业务阻断演练、多实例故障协调或完整银行交易演示。正式数据库迁移仍要求确认维护窗口、可信备份、实际数据库产品和操作权限。

## 下一阶段
继续基于第十八批的请求恢复与第十九批的迁移演练，针对隔离进程异常、Guard 不可用及风险确认边界进行系统测试；最后完成团队版本合并前审查与比赛部署检查。
