# CHANGELOG

> 状态：生效 ｜ 最后更新：2026-11-01 ｜ 维护：Claude
>
> 每条四段式：做了什么 / 验证 / 遗留问题 / 规则或评测集变动。

## v0.1.0 · D1 · 骨架与鉴权（2026-11-01）

**做了什么**
- 按 CLAUDE.md §3 建立 backend 分层目录与包说明
- 核心配置（pydantic-settings 读 .env）、常量唯一来源、统一返回体与全局异常处理
- MySQL 五张表（users/clients/scripts/audits/rules）与建库脚本
- JWT（HS256）注册 / 登录 / me，bcrypt 存密码
- clients / scripts / audits / rules 四套分页 CRUD

**验证**
- 见本次汇报：DDL 预览、SHOW TABLES、pytest 结果

**遗留问题**
- 待补

**规则 / 评测集变动**
- 无（rules 表为空，锚点集仅 2 条示例案例，尚未入 Chroma）
