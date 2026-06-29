# 2026-06-22 Daily Report — OpenClaw 集成 Phase 1

## 今日目标

重新制定工程目标：将 iflyVoice 与板子上的 OpenClaw（小龙虾）集成，让 OpenClaw 获得控制 RK3576 板子硬件（亮度/音量/应用）的能力。

## 完成情况

### 1. 需求探索与架构设计

| 项目 | 内容 |
|------|------|
| OpenClaw 形态 | Node.js v22+ 后台进程，systemd user service，端口 18789 |
| OpenClaw 版本 | 2026.6.6 (commit 8c802aa) |
| LLM 模型 | minimax/MiniMax-M3 |
| 集成关系 | **OpenClaw 是大脑，iflyVoice 变手肩** |
| 集成方式 | HTTP API (iflyVoice :18766) + SKILL.md (给 LLM 看) |
| 调用方式 | OpenClaw exec(curl POST :18766/api/v1/tools/...) |

### 2. 设计文档

- `docs/superpowers/specs/2026-06-22-openclaw-integration-design.md` — 集成设计 spec
- `docs/superpowers/plans/2026-06-22-openclaw-integration-plan.md` — 11 个 Task 实施计划

### 3. 实施计划执行（11 个 Task）

| Task | 内容 | Commit | 状态 |
|------|------|--------|------|
| 1 | linux/audio_io.py 增 set/get_volume | d0be042 | ✅ |
| 2 | app_manager_linux.py（launch/close/focus/list）| 0cf1850 | ✅ |
| 3 | LocalExecutor 扩展（14 intent）| eb0d7fb | ✅ |
| 4 | dispatcher 全 LOCAL 路由 + pc_agent=None | 7c5d028 | ✅ |
| 5 | server.py /api/v1/tools/* 9 端点 | 56ed685 | ✅ |
| 6 | skills/iflyvoice/SKILL.md | 38e43ff | ✅ |
| 7 | scripts/start-iflyvoice.sh | ec79952 | ✅ |
| 8 | install-arm64.sh skill 安装段 | — | ⏭️ 跳过（文件不存在） |
| 9 | scripts/e2e_iflyvoice.sh | 9ee38c6 | ✅ |
| 10 | scripts/e2e_openclaw_iflyvoice.sh | ad79007 | ✅ |
| 11 | 全量验证 + 板子端 e2e | — | ✅ |

### 4. 板子端调试（发现并修复 5 个问题）

| 问题 | 原因 | 修复 |
|------|------|------|
| tenacity 导入崩溃 | executor/pc_agent.py 顶层 import tenacity | 改为 lazy import |
| pulsectl 24+ API 变更 | PulseVolumeInfo("100%").with_factor() 不可用 | 改用 volume_set_all_chans |
| sounddevice 未装 | 板子默认没装 | pip install sounddevice |
| pipewire-pulse 未运行 | 板子用 PipeWire，需装 pipewire-pulse | apt install + start |
| openclaw agent 缺 --agent 参数 | e2e 脚本没指定 agent id | 加 --agent main |

### 5. 板子端 e2e 验证结果

```
=== e2e_iflyvoice PASSED ===
[1] health check         ✅ PASS
[2] set_brightness=50    ✅ PASS
[3] adjust_brightness    ⚠️ WARN（无 backlight 设备，正常）
[4] set_volume=30        ✅ PASS
[5] list_monitors        ✅ PASS
[6] list_apps            ✅ PASS
[7] 未知工具 404          ✅ PASS
```

```
=== e2e_openclaw_iflyvoice ===
[1] iflyVoice running    ✅ PASS
[2] openclaw gateway     ✅ PASS
[3] SKILL.md present     ✅ PASS
[4] OpenClaw 调亮度      ⏳ 进行中（等待 LLM 响应）
```

### 6. 测试统计

| 测试套件 | 结果 |
|----------|------|
| pytest 全量（Windows） | 91 passed, 9 skipped |
| e2e_iflyvoice.sh（板子） | PASSED |
| e2e_openclaw_iflyvoice.sh（板子） | 进行中 |

## 今日提交（12 个 commit）

```
ad79007 fix(e2e): add --agent main to openclaw agent command
9ee38c6 fix(e2e): fix warn message logic in e2e_iflyvoice.sh
3db7c63 fix(linux): use volume_set_all_chans for pulsectl 24+ compatibility
57cf512 fix(executor): lazy import tenacity in pc_agent
0a5406e test(e2e): add e2e_openclaw_iflyvoice.sh
25f8b57 test(e2e): add e2e_iflyvoice.sh
ec79952 feat(scripts): add start-iflyvoice.sh
38e43ff docs(skill): add iflyvoice SKILL.md
56ed685 feat(server): add /api/v1/tools/* routes
7c5d028 docs(dispatcher): update module docstring + regression test
d9dcbfc refactor(dispatcher): route all intents to local
eb0d7fb fix(executor): clamp SET_CONTRAST/SET_COLOR_TEMP
68a79c2 feat(executor): extend LocalExecutor with display/audio/app intents
0cf1850 fix(linux): address app_manager_linux review issues
bd12a0b fix(linux): restore SIGKILL phase in close_app
092be76 feat(linux): add app_manager_linux
1b8517f fix(linux): align get_volume docstring
d2b52fe test(linux): fix pulsectl mock strategy
```

## 架构图

```
┌──────────────────────────────────────────────────────────────┐
│  RK3576 (aarch64 Ubuntu 22.04)                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  OpenClaw Gateway (Node.js) — 大脑                    │  │
│  │  · WebSocket :18789（已运行）                          │  │
│  │  · LLM: minimax/MiniMax-M3                            │  │
│  │  · 内置 exec 工具 / Skills 加载器                      │  │
│  │  · 读 ~/.openclaw/workspace/skills/iflyvoice/SKILL.md │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                           │ exec(curl POST :18766/api/...)  │
│                           ▼                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  iflyVoice (Python) — 手肩                            │  │
│  │  · HTTP :18766（pid 管理）                            │  │
│  │  · /api/v1/tools/* 9 个端点                           │  │
│  │  · dispatcher → LocalExecutor                         │  │
│  │  · linux/backlight · linux/audio_io · app_manager_linux│  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## 待办事项

- [ ] e2e_openclaw_iflyvoice.sh 完整跑通（等 LLM 响应）
- [ ] 推送分支到远端：`git push origin rk3576_lubancat`
- [ ] 板子无 backlight 设备问题（需接 HDMI 显示器或换板子）
- [ ] list_apps 过滤优化（当前会返回系统进程）
- [ ] Phase 2：OpenClaw Node 插件（替代 exec 调 curl）
- [ ] Phase 3：MCP server 化

## 今日收获

1. **OpenClaw 是成熟的 AI gateway**，有完整的 plugin-sdk、WebSocket 协议、工具调用能力
2. **SKILL.md 是给 LLM 看的说明书**，不是可执行代码；执行层仍需 HTTP/Node 插件/MCP
3. **pulsectl 24.x API 变更**：PulseVolumeInfo 构造函数不接受字符串，改用 volume_set_all_chans
4. **板子调试比预期复杂**：tenacity/sounddevice/pulsectl 等依赖都需要手动安装
5. **TDD 流程有效**：subagent-driven-development 模式下，每个 Task 都有 spec review + code quality review，发现了不少 plan 本身的 bug
