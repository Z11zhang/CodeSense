# 阶段四：把修复变成回归验证（张诗若）

## 目标

阶段二的 Trace 测试曾在跨主机请求时返回 302。阶段三已找到并验证根因：登录 host 与请求 host 不一致，测试客户端不会将登录 Cookie 发送给另一个 host，因而在 Trace 路由执行前被 `login_required` 重定向。阶段四把“修复前失败、修复后通过”整理成单条可重复运行的命令，避免以后调整 fixture 时悄悄带回该问题。

## 自动验证

从仓库根目录运行：

```powershell
python experiments/session_cookie_scope/regression.py
```

脚本分两步，且仅在两步均得到预期结果时返回成功：

1. **修复前对照：** 在临时测试副本中把历史错误的 fixture 登录 host 改为 `example.com`，Trace 请求仍使用 `localhost`。四项依赖本地登录态的既有用例应失败为 302，另两项应通过（`4 failed, 2 passed`）。脚本结束时删除临时副本，不改正式测试文件。
2. **修复后验证：** 对未修改的测试模块运行完整 Trace 测试，10 项应通过。该模块包含主机 Cookie 对照矩阵、路由入口观测、原会话保留、目标 host 重新登录恢复以及既有安全断言。

## 前后结果

| 场景 | 操作 | 结果 |
| --- | --- | --- |
| 修复前对照 | 受控恢复错误 fixture，运行六项既有测试 | `4 failed, 2 passed`；四个失败均是预期 200/403 被 302 登录重定向 |
| 修复后 | 运行 `tests/test_stage3_forum_trace.py` | `10 passed` |

上述两组结果分别于 2026-09-27 在桌面 v1.4.0 源码的隔离副本中实测。此 PR 新增的配对脚本把相同两步封装成一个命令；本次编辑环境没有 Python/pytest 解释器，故未在当前环境重新执行配对脚本。修复前步骤是受控变异，不是对历史 commit 的完整 checkout 或重跑；报告不将它描述成历史 commit 验证。

## 修改范围与边界

新增 `experiments/session_cookie_scope/regression.py`。它只创建、执行并清理临时测试副本，然后运行正式测试模块；不修改认证逻辑、测试数据库、Redis 或用户数据。根因分析、测试矩阵和 v1.4.0 版本核对见[阶段三报告](https://github.com/Z11zhang/CodeSense/blob/codex/stage3-cookie-root-cause-v2/docs/stage3-session-cookie-root-cause.md)。

## 验收对应

PR 应同时展示修复前的预期失败与修复后的通过结果；本报告给出旧问题如何复现、通过标准、执行命令和证据边界。