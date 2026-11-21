# agent-skills

我自己在用的 Agent Skills 集合。每个 skill 一个目录，遵循 [Agent Skills 规范](https://agentskills.io/specification)。

## 包含的 skill

| Skill | 一句话 | 解决什么 |
|---|---|---|
| [blind-slice](skills/blind-slice/) | 按可独立验收的行为切片开发软件，断言对实现者不可见 | Agent 改测试凑绿、针对断言特化、模块拼不起来 |

## 安装

### 一键（Windows PowerShell）

```powershell
git clone https://github.com/<你的用户名>/agent-skills.git
cd agent-skills
.\install.ps1
```

默认装到 `%USERPROFILE%\.workbuddy\skills\`，可以用 `-Dest` 指定别处：

```powershell
.\install.ps1 -Dest "D:\somewhere\skills"
```

### 手动

把 `skills/<name>/` 整个目录复制到 `~/.workbuddy/skills/<name>/`。

两条硬要求：

- 目录名必须和 `SKILL.md` 里的 `name` 完全一致，否则加载不到。
- 装完要开新会话，正在进行的会话读不到新 skill。

## blind-slice 在做什么

核心只有一句：**断言存在，但实现者看不见。**

不靠提示词约束 Agent，靠改它的处境 —— 拿不到断言内容、失败不许局部修补，唯一出路是读懂行为说明。

```
起草（Agent）→ 人审断言 → 落锁（断言移出项目）→ 盲实现 → 外部判定只回 PASS/FAIL → 失败整片重做
```

`scripts/gate.py` 是唯一的裁决者，纯 Python 标准库，不需要装任何依赖。

### 它挡得住的

- 改测试让它变绿（断言不在项目里）
- 针对失败用例特化（看不到断言内容）
- 每块都对、拼起来不对（系统层组合验收）

### 它挡不住的

- 人审断言时扫一眼就过
- 起草和实现没有换会话（Agent 记得自己写的断言）
- 需求还没成形就硬套流程

这三条都写在 SKILL.md 里，但写在文档里和真的被遵守是两件事。

## 设计取向

这套东西不试图让 Agent 更可信，而是让「不可信」没有用武之地 —— 不改它的动机，改它的处境。

代价是流程里必然有人的位置：定判据、验收结果。想全自动就等于放弃判定，那不如直接 vibe coding。

## 许可

MIT，见 [LICENSE](LICENSE)。
