# 阶段三：追到问题根因（张诗若）

## 调查范围与前两阶段的关系

阶段一 [PR #12](https://github.com/XiaoCow666/CodeSense/pull/12) 梳理路由、认证与评测调用链；阶段二 [PR #28](https://github.com/XiaoCow666/CodeSense/pull/28) 修改评分状态判断、升级依赖并修复会话测试。本阶段选择阶段二真实出现过的 **Trace 测试返回 302** 问题，补齐可执行的根因证据。

这是已修复问题的追溯分析，不是新发现的线上故障，也不重复申报阶段二的修复。本次新增的是双向域名对照实验、请求边界观测、原会话保存验证、重新登录恢复验证和受控错误复现脚本。

基线：PR 目标仓库 `Z11zhang/CodeSense` 的 `main`，提交 `52acab2bdf99461bbd5f25cfe08e98c118bc03e6`。版本为 v1.4.0；桌面 `codesense-main-latest2/CodeSense-main/README.md` 的 Git blob `981df623157fb72e7f91dbdef792aadea00c9edf` 与该 fork 的 `main` 完全一致。实验日期 2026-09-27。

## 观察

[历史评审](https://github.com/XiaoCow666/CodeSense/pull/28#pullrequestreview-5190763367) 记录：fixture 在 `http://example.com` 登录，四个 Trace 请求使用 `http://localhost`。预期 200/403，实际全是 302。另一个在 example.com 发请求的用例通过。[后续修复记录](https://github.com/XiaoCow666/CodeSense/pull/28#issuecomment-5677613209) 改为每个请求在对应 host 登录。

302 只是现象。仅凭状态码不能确定是路由权限、数据库、登录失败还是 Cookie 问题；必须继续检查 Location、请求是否携带 Cookie、服务端会话是否存在以及路由内部是否执行。

## 两个被排除的假设与保留的解释

| 假设 | 可证伪预测 | 实测证据 | 结论 |
| --- | --- | --- | --- |
| H1：Trace 内部本地访问限制/权限判断错误 | 失败请求已进入 Trace，执行 `_request_is_local()` | 跨 host 请求的路由入口探针为 0，Location 路径为 `/login`；同 host 为 1，现有远端请求仍返回 `DEV_TRACE_DISABLED` 403 | 排除：302 出现在目标路由业务逻辑之前 |
| H2：Flask-Session 升级导致登录会话未保存或丢失 | 登录后原 host 下也无法读到 `_user_id` | 登录后和跨 host 失败后，原 host 的 `session_transaction` 均保留 `_user_id=student-1` | 排除：原会话没有丢失 |
| H3：测试客户端按 Cookie 域名隔离，跨 host 请求没有身份 | 只有跨 host 缺少 Cookie 和 `_user_id`；在请求 host 重新登录即可恢复 | 四组矩阵完全符合；两个跨 host 用例重新登录后相同请求均返回 200 | 保留：测试登录与请求 host 不一致是本次根因 |

H1/H2/H3 都是针对这个受控测试环境的解释，不能外推为所有 302 的原因。本次也没有通过旧版依赖对照证明“只有 Flask-Session 0.8.0 才有域隔离”；域名作用域是 Cookie 行为，不应简单归因于新版本缺陷。

## 调用链

```text
client.post('/login', base_url=登录 host)
  → routes/auth.py::login → login_user(user)
  → Flask-Session 保存会话，响应设置会话 Cookie
  → Werkzeug 测试客户端按登录 host 保存 Cookie
client.post('/thinking/api/stage3/forum/trace', base_url=请求 host)
  → 客户端依据域名决定是否发送 Cookie
  → Flask 打开请求会话
  → request_started 探针：只记录 Cookie / _user_id 是否存在
  → @login_required：匿名请求重定向 /login，返回 302
  → @student_required
  → stage3_forum_trace → _request_is_local → 会话归属检查 → trace JSON
```

代码定位：`routes/auth.py::login`、`routes/thinking.py::stage3_forum_trace`、`app.py::create_app` 的会话初始化。`@login_required` 位于 `@student_required` 之前。新测试包裹 `_request_is_local`，保留原函数行为，以其调用次数观测是否已经进入 Trace 函数体。

## 最小变量对照

`test_trace_cookie_scope_root_cause` 每项创建全新的 client，避免 fixture 已有的 localhost Cookie 污染实验。账号、数据库、请求路径、payload、REMOTE_ADDR 均保持一致，只改变两个 host。没有关闭登录校验，也没有跟随重定向掩盖 302。

| 登录 host | 请求 host | Cookie 到达 | `_user_id` 存在 | 路由入口次数 | HTTP |
| --- | --- | --- | --- | --- | --- |
| localhost | localhost | 是 | 是 | 1 | 200 |
| example.com | example.com | 是 | 是 | 1 | 200 |
| example.com | localhost | 否 | 否 | 0 | 302 → /login |
| localhost | example.com | 否 | 否 | 0 | 302 → /login |

两个跨域场景都额外验证：原 host 会话仍在；在目标 host 登录后，重复完全相同的 Trace 请求恢复 200。探针只保存布尔值，不输出 Cookie 值、session ID 或真实账号信息。

## 受控复现旧错误

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHON_DOTENV_DISABLED = '1'
$env:REDIS_URL = 'redis://127.0.0.1:1/15'
python experiments/session_cookie_scope/reproduce.py
```

脚本复制当前六项原有 Trace 测试到临时文件，仅把默认 fixture 登录 host 改为 example.com，保留其他请求 host，并在结束后删除该副本。它保留隔离会话配置，不修改正式测试文件。

实测：`4 failed, 2 passed, 74 warnings in 8.21s`，四项都是原本预期 200/403 而实际 302 的用例，与历史评审名单一致。内部 pytest 退出码是 1；外层脚本只有确认预期失败数后才返回 0，并输出 `CONTROLLED_MUTATION_EXPECTED_FAILURES=True`。该 0 表示成功复现错误，不能称为测试全部通过。

这是一处变量的受控变异，**不是对历史 commit 的完整 checkout/重跑**。它避免把今天的依赖环境误写成当时的环境。

## 验证环境与结果

Windows，Python 3.14.7；Flask 2.3.3、Werkzeug 2.3.7、Flask-Session 0.8.0、Flask-Login 0.6.2、pytest 9.1.1。测试运行在桌面 v1.4.0 项目源码的隔离工作副本中，代码基线与 PR 目标仓库一致。未找到可用的共享 `student-eval`，使用已有 `.venv-test` 解释器。没有复制 `.env`，没有安装/升级依赖。

Trace fixture 使用临时 SQLite 与临时文件会话；Redis ping 被替换为明确失败，确保不会连接或写入正在运行的 Redis。测试只使用合成账号，不是生产/真实账号验收；未启动人工访问的 PR 服务。

实际运行：

```text
python -m pytest tests/test_stage3_forum_trace.py -q --disable-warnings --basetemp=.stage3-v14-tmp
10 passed, 127 warnings in 14.34s

python experiments/session_cookie_scope/reproduce.py
4 failed, 2 passed, 74 warnings in 8.35s
CONTROLLED_MUTATION_EXPECTED_FAILURES=True

python -m pip check
No broken requirements found.

python -m pytest tests/test_demo_guided_learning.py tests/test_stage3_forum_trace.py tests/test_readme_setup.py -q --disable-warnings --basetemp=.stage3-v14-related-tmp
19 passed, 2 failed, 3166 warnings in 54.52s
```

两项失败在 `test_demo_guided_learning.py`：`test_public_demo_shortcuts_can_move_shared_session_through_all_stages` 与 `test_public_shortcut_rejects_regular_student_other_assignment_and_anonymous`，错误为服务端 session 读取时缺少 `demo_run_id`（`KeyError`）。它们不是 Trace 根因矩阵用例；这组相关回归不能标记为全通过。弃用警告包括 Flask-Session 文件后端、SQLAlchemy 旧 API 和 datetime。

## 取舍与边界

- 采纳：用独立 client、请求边界探针和受控变异证明因果；保留现有远端拒绝与缺失会话断言。
- 拒绝：把 302 改成通过、关闭认证、扩大 Cookie Domain、强制永久会话或强制每个响应保存 session。这些会掩盖测试配置错误或改变产品行为。
- 根因修复已在阶段二完成，本阶段只补测试和证据，未改生产认证逻辑。
- 未验证：完整测试套件、全新安装环境、其他 Python 版本、真实浏览器、生产 Redis、多进程、真实账号与 AI/g++ 路径。`pip check` 只说明现有环境依赖声明一致，不等于干净安装验证。

## 飞书任务交付摘要

观察：阶段二 Trace 用例已登录却得到 302。两个排除假设：Trace 内部权限异常、服务端会话丢失。验证：四组双向 host 对照、Cookie/身份布尔探针、路由入口计数、原 host 会话保留、目标 host 重新登录恢复，以及旧 fixture 错误的受控重现。根因：测试登录和请求 host 不一致，Cookie 未随请求发送，`login_required` 在 Trace 逻辑前重定向。交付：本报告、四项新增参数化测试与可复现脚本；PR 链接应填写到任务的「GitHub PR / Issue」。

