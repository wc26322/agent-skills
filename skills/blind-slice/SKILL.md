---
name: blind-slice
description: 按「可独立验收的行为切片」开发软件：每片先起草骨架与断言、人审后把断言移到实现者看不见的地方、盲实现、外部判定只回传通过/不通过、失败整片重做。当用户要求「开发/实现一个功能或项目」「按盲切片流程做」「用这套模式写代码」时使用。防止 Agent 改测试凑绿、针对断言特化、模块拼不起来。
agent_created: true
---

# 盲切片

一句话：**断言存在，但实现者看不见。**

不靠纪律约束 Agent，靠改变它的处境 —— 拿不到断言内容、失败不许局部修补，唯一出路是读懂行为说明。

裁决器是 `scripts/gate.py`。它的输出就是结论，`PASS` / `FAIL` 之外没有别的判据。

## 三条硬约束，先看这个

**1. 起草和实现必须分开。** 起草阶段 Agent 见过自己写的断言，如果在同一个会话里继续实现，它记得断言内容，盲区不成立，整套流程退化成表演。起草完必须开新会话做实现，或者由人把断言实质改掉。

**2. 测试文件不在项目里。** `accept` 会把断言移进项目之外的保管区，项目目录里从此没有明文。不要去保管区找它。找它、读它等于自己废掉这套流程。

**3. `reveal` 是人的命令。** 它打印失败详情。Agent 不许调用。失败时你只该知道 PASS 还是 FAIL，知道得越多，越容易针对性地写。

## 流程

```bash
python <skill>/scripts/gate.py init                      # 初始化
python <skill>/scripts/gate.py new S-001 "行为名"          # 建一个切片
```

（命令里的 `python` 按你环境换成 `py` 或 `python3`。）

**① 起草（Agent 做）**，产出四样：

- `slices/S-001/contract/spec.md` —— 一条行为，不超过十行。写做什么、不做什么、边界。
- `slices/S-001/contract/interface.md` —— 可编译的签名，切片之间唯一的契约。
- `slices/S-001/impl/*.py` —— 空实现骨架，`raise NotImplementedError`。
- `slices/S-001/.draft/assertions.py` —— 断言草案，`from impl.模块 import 函数` 的形式。

断言要测**行为**，不测实现细节。一个用例一个边界，别写 `assert x is not None` 这种。

**② 自检起草**

```bash
python <skill>/scripts/gate.py draft S-001
```

它会验两件事：断言跑得起来（不是语法错），且当前**全部失败**（骨架是空实现，过了说明断言没在测东西）。

**③ 人审断言（人做）** —— 删掉不该要的，改掉写反的，补上漏掉的边界。这是全流程最重要的十分钟。

**④ 落锁**

```bash
python <skill>/scripts/gate.py accept S-001
```

断言移入保管区，项目内删除。如果人一个字没改，它会警告盲区可能不成立。

**⑤ 盲实现（换会话，Agent 只写 impl/）** —— 只读 `contract/`，写完就提交。

**⑥ 盲判**

```bash
python <skill>/scripts/gate.py judge S-001
```

只有 `PASS` 或 `FAIL (attempt n/3)`。

**⑦ 失败整片重做** —— 不要修补。不许猜断言、不许试输入、不许改骨架去适配。重读 `spec.md`，从头写 `impl/`。

三次不收敛 → 自动化停止，需要人工介入。这时人用 `reveal` 看详情，判断是断言错了还是切片本身有问题。

## 全部切片通过之后

```bash
python <skill>/scripts/gate.py system
```

系统层断言要放进保管区，具体路径用人用的 `gate.py where` 查（**Agent 不要执行 where**，它的输出会暴露断言位置）。

系统层验收测的是**切片之间拼起来是否成立**，不是单片的重复。组合场景必须人写、Agent 从未见过。

断言里取各切片的实现，用 gate 自动提供的 `load`（不要手写 sys.path 操作）：

```python
from _slices import load

def test_add_then_double(self):
    calc = load("S-001", "calc")      # 即 slices/S-001/impl/calc.py
    scale = load("S-002", "scale")
    self.assertEqual(scale.double(calc.add(1, 2)), 6)
```

跳过这一步，等于承认「每块都对，合起来不对」这种失败你不管 —— 而这是模块化开发最常见的死法。

## 禁止事项

| 不许 | 为什么 |
|---|---|
| 去保管区读断言 | 读了整套就废了，而且看得出来是谁读的 |
| 失败后修补实现 | 修补就是针对失败特化，正是要防的东西 |
| 改 spec/interface 去迁就实现 | 契约是切片之间的公共承诺，改它等于让别人替你背锅 |
| 一个切片塞多条行为 | 切片越大，盲区越容易漏，人也越难判断 |
| 用 `assert x is not None` 之类弱断言 | 抓不住任何错误，判定变成走过场 |

## 什么时候别用这套

- **需求还没成形**：写不出 spec 和断言。这时先做一版粗糙的出来看，别假装有判定。
- **没法隔离测试**：UI 观感、真实硬件交互。判定只能退回给人。
- **小于半天的改动**：整套是负收益，直接做。

硬套这三类场景，只会得到一堆形式正确、毫无作用的流程。

## 交付时怎么说话

`status` 里所有切片 `done` 且系统层通过，才算完成。没到就如实说卡在哪一片、第几次尝试、卡在哪一步。

不许用「基本完成」「主要功能已实现」结案 —— 判定器只认 PASS。
