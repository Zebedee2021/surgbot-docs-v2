# 文档编写规范

> 统一的文档结构让团队成员打开任何一个页面都能快速找到所需信息。

---

## 模块概述页模板

每个模块的 `index.md` 必须包含以下六个部分，顺序固定：

```markdown
# 模块名称

<span class="status-wip">进行中</span>   <!-- 状态徽章，见下方说明 -->
**负责人：** 姓名

---

## 模块目标
<!-- 一两句话说清楚这个模块做什么、对外承诺什么 -->
<!-- 必须包含：对外输出的接口引用链接 -->

---

## 上下游接口
<!-- 用 tabs 分"输入"和"输出"，表格格式 -->
<!-- 必须链接到 design/module_interfaces.md 的对应定义 -->

---

## 当前状态
<!-- 子功能列表 + 状态徽章，一行一项 -->

---

## 待决策问题
<!-- 用 !!! question 块，每个问题独立 -->
<!-- 若无，写"无当前待决策事项" -->

---

## 已知瓶颈
<!-- 用 !!! failure（P0）或 !!! warning（P1）块 -->
<!-- 若无，写"无当前阻塞瓶颈" -->

---

## 本周行动
<!-- 任务列表，用 - [ ] 格式，每项前缀负责人姓名 -->
<!-- 周会后更新，完成的改为 - [x] -->

---

## 技术子页
<!-- 链接列表，每项附一句说明 -->
```

---

## 状态徽章

在 Markdown 中直接使用 HTML span，CSS 已在 `extra.css` 定义：

```html
<span class="status-done">已完成</span>
<span class="status-wip">进行中</span>
<span class="status-todo">待完成</span>
<span class="status-blocked">阻塞中</span>
```

渲染效果：<span class="status-done">已完成</span> <span class="status-wip">进行中</span> <span class="status-todo">待完成</span> <span class="status-blocked">阻塞中</span>

---

## 任务列表格式

```markdown
- [x] 姓名：已完成的任务描述
- [ ] 姓名：待完成的任务描述（截止时间）
```

**规则：**

- 每项必须有负责人前缀
- 每次周会后更新本周行动，将上周完成项改为 `[x]`，添加本周新任务
- 超过两周未更新的任务视为被遗忘，需在周会中确认状态

---

## Admonition 使用规范

| 类型 | 语法 | 用途 |
|------|------|------|
| 注意 | `!!! warning` | P1 问题、需要关注的信息 |
| 阻塞 | `!!! failure` | P0 问题、阻塞推进的问题 |
| 决策 | `!!! question` | 待决策事项 |
| 提示 | `!!! tip` | 有用的背景信息 |
| 危险 | `!!! danger` | 安全红线，不得违反 |

---

## 文档更新频率

| 文档类型 | 更新频率 | 谁来更新 |
|----------|----------|----------|
| 模块 `index.md` → 本周行动 | 每次周会后 | 模块负责人 |
| 模块 `index.md` → 当前状态 | 有实质进展时 | 模块负责人 |
| [Sim2Real 状态面板](../sim2real/status.md) | 每周 | 谭文韬 / 任松 |
| [全局问题追踪](../tracker/issues.md) | 每次周会后 | 全员 |
| [模块接口定义](../design/module_interfaces.md) | 接口变更时 | 接口双方协商后更新 |
| 技术子页（YOLO、SFT 等） | 有实质内容更新时 | 模块负责人 |
| 项目背景类（简介、团队等） | 人员/硬件变化时 | 项目负责人 |

---

## Git 提交规范

```
feat(perception): 添加夹取点修正算法初版
fix(nlp): 修复词库匹配大小写问题
docs(sim2real): 更新第二级验证 checklist
chore: 更新环境依赖版本
```

格式：`类型(模块): 简短描述`

类型：`feat` 新功能 · `fix` 修复 · `docs` 文档 · `refactor` 重构 · `chore` 杂项

<div class="doc-footer">
  <span>SurgBot Team</span>
  <span>最近更新 2026-03-18</span>
</div>
