#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blind-slice gate —— 盲切片的裁决器。

核心只有一条：断言存在，但实现者看不见。判定结果只回传一个比特。

用法:
  python gate.py init                          建 .blindslice/ 与 slices/
  python gate.py new S-001 "行为名"              新建切片骨架
  python gate.py draft S-001                    检查起草齐备，且断言当前必须全红
  python gate.py accept S-001                   人审后落锁：断言移入保管区，项目内删除明文
  python gate.py judge S-001                    盲判：只输出 PASS / FAIL
  python gate.py reveal S-001                   人工介入时才看失败详情
  python gate.py system                         系统层组合场景验收
  python gate.py status                         总览

退出码: 0 通过 / 1 不通过 / 2 用法或环境错误
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

DEV = ".blindslice"
STATE = "state.json"
MAX_ATTEMPTS = 3

SPEC_TEMPLATE = """# 行为：{name}

<!-- 只写这一条行为，不超过十行。每多一句，解释空间就多一层。 -->

**做什么**
-

**不做什么**
-

**边界**
-
"""

IFACE_TEMPLATE = """# 接口：{name}

<!-- 可编译的签名，切片之间唯一的契约。实现层不得新增跨切片接口。 -->

```python
# impl 包内的公开签名
```
"""


# ---------------------------------------------------------------- 路径与状态

def vault_root() -> Path:
    """断言保管区，刻意放在项目之外。项目目录里永远不存在断言明文。"""
    p = Path(__file__).resolve().parent.parent / "vault"
    try:
        p.mkdir(parents=True, exist_ok=True)
        (p / ".write_test").write_text("1", encoding="utf-8")
        return p
    except Exception:
        alt = Path.home() / ".workbuddy" / "blind-slice-vault"
        alt.mkdir(parents=True, exist_ok=True)
        return alt


def project_key(root: Path) -> str:
    return hashlib.sha1(str(root).lower().encode("utf-8")).hexdigest()[:12]


def vault_dir(root: Path, sid: str = "") -> Path:
    d = vault_root() / project_key(root)
    return d / sid if sid else d


def slice_dir(root: Path, sid: str) -> Path:
    return root / "slices" / sid


def load_state(root: Path) -> dict:
    f = root / DEV / STATE
    if not f.exists():
        return {"project": root.name, "slices": {}, "system_done": False}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"project": root.name, "slices": {}, "system_done": False}


def save_state(root: Path, st: dict) -> None:
    d = root / DEV
    d.mkdir(parents=True, exist_ok=True)
    (d / STATE).write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 执行断言

LOADER_SRC = '''# 自动生成，请勿修改。系统层断言用 load(sid, module) 取切片的实现。
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(r"{root}")


def load(sid, module):
    p = ROOT / "slices" / sid / "impl" / (module + ".py")
    name = "bs_" + sid.replace("-", "_") + "_" + module
    spec = importlib.util.spec_from_file_location(name, str(p))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m
'''


def run_assertions(assert_file: Path, work_path: Path, with_loader: bool = False):
    """把断言复制到系统临时目录执行，跑完即删。项目目录从不出现断言明文。"""
    with tempfile.TemporaryDirectory() as td:
        shutil.copy(assert_file, Path(td) / "test_assertions.py")
        if with_loader:
            (Path(td) / "_slices.py").write_text(
                LOADER_SRC.format(root=str(work_path)), encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(work_path) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            r = subprocess.run(
                [sys.executable, "-m", "unittest", "test_assertions", "-v"],
                cwd=td, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=900,
            )
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except subprocess.TimeoutExpired:
            return 124, "(断言执行超时)"


def count_tests(assert_file: Path) -> int:
    text = assert_file.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"^\s*def test_", text, re.MULTILINE))


def parse_executed(out: str) -> int:
    ran = [int(x) for x in re.findall(r"Ran (\d+) tests?", out)]
    passed = [int(x) for x in re.findall(r"(\d+) passed", out)]
    failed = [int(x) for x in re.findall(r"(\d+) failed", out)]
    vals = list(ran)
    if passed or failed:
        vals.append(sum(passed) + sum(failed))
    return max(vals) if vals else 0


# ---------------------------------------------------------------- 命令

def cmd_init(root, args):
    (root / "slices").mkdir(parents=True, exist_ok=True)
    (root / DEV).mkdir(parents=True, exist_ok=True)
    if not (root / DEV / STATE).exists():
        save_state(root, {"project": root.name, "slices": {}, "system_done": False})
    vault_dir(root).mkdir(parents=True, exist_ok=True)
    print(f"初始化完成。切片放 slices/<ID>/，断言保管区在项目之外。")
    print("下一步：gate.py new S-001 \"行为名\"")
    return 0


def cmd_new(root, args):
    sid, name = args.sid, args.name
    d = slice_dir(root, sid)
    if d.exists():
        print(f"{sid} 已存在")
        return 2
    (d / "contract").mkdir(parents=True)
    (d / "impl").mkdir(parents=True)
    (d / ".draft").mkdir(parents=True)
    (d / "impl" / "__init__.py").write_text("", encoding="utf-8")
    (d / "contract" / "spec.md").write_text(SPEC_TEMPLATE.format(name=name), encoding="utf-8")
    (d / "contract" / "interface.md").write_text(IFACE_TEMPLATE.format(name=name), encoding="utf-8")
    st = load_state(root)
    st["slices"][sid] = {
        "name": name, "stage": "draft", "attempts": 0,
        "created_at": now(), "draft_hash": None, "human_edited": None,
    }
    save_state(root, st)
    print(f"{sid} 已建。接下来起草三样：contract/spec.md、contract/interface.md、.draft/assertions.py")
    print("impl/ 里只放能编译的空实现（raise NotImplementedError）。")
    return 0


def _draft_paths(d: Path):
    return (d / "contract" / "spec.md", d / "contract" / "interface.md",
            d / ".draft" / "assertions.py")


def _check_draft(root, sid, st):
    """起草是否齐备，且断言当前必须全部失败。返回 (ok, 消息列表, 执行输出)。"""
    msgs, fails = [], []
    d = slice_dir(root, sid)
    spec, iface, asserts = _draft_paths(d)
    for f, label in ((spec, "contract/spec.md"), (iface, "contract/interface.md"),
                     (asserts, ".draft/assertions.py")):
        if not f.exists():
            fails.append(f"缺 {label}")
        elif f.stat().st_size < 30:
            fails.append(f"{label} 是空的或只有标题")
    impls = [p for p in (d / "impl").rglob("*.py") if p.name != "__init__.py"]
    if not impls:
        fails.append("impl/ 里没有空实现骨架（先写签名 + raise NotImplementedError）")
    if fails:
        return False, msgs + [f"[x] {m}" for m in fails], ""

    n = count_tests(asserts)
    if n == 0:
        return False, ["[x] .draft/assertions.py 里没有 def test_ 用例"], ""
    code, out = run_assertions(asserts, d)
    executed = parse_executed(out)
    if executed < n:
        return False, [f"[x] 只执行到 {executed}/{n} 个用例：断言本身没跑起来（导入错或语法错），这不是红"], out
    if code == 0:
        return False, ["[x] 断言当前已全部通过。骨架还是空实现，它怎么会过？说明断言没在测行为"], out
    return True, [f"[v] 起草齐备：{n} 个用例，当前全部失败（先红成立）"], out


def cmd_draft(root, args):
    st = load_state(root)
    sid = args.sid
    if sid not in st["slices"]:
        print(f"没有切片 {sid}")
        return 2
    ok, msgs, _ = _check_draft(root, sid, st)
    for m in msgs:
        print(m)
    if ok:
        d = slice_dir(root, sid)
        h = sha(d / ".draft" / "assertions.py")
        rec = st["slices"][sid]
        if rec.get("draft_hash") is None:
            rec["draft_hash"] = h
            save_state(root, st)
            print("已记录断言草案指纹。接下来由人审：删掉不该要的、改掉写反的。")
        elif rec["draft_hash"] != h:
            print("断言草案已变更（人改过或 Agent 又改过）。accept 时会再比对一次。")
            save_state(root, st)
    return 0 if ok else 1


def cmd_accept(root, args):
    st = load_state(root)
    sid = args.sid
    rec = st["slices"].get(sid)
    if not rec:
        print(f"没有切片 {sid}")
        return 2
    d = slice_dir(root, sid)
    src = d / ".draft" / "assertions.py"
    if not src.exists():
        print("这个切片已经落锁过了（.draft 已移出项目）。要改断言只能新建一个切片重做。")
        return 2

    ok, msgs, _ = _check_draft(root, sid, st)
    for m in msgs:
        print(m)
    if not ok:
        print("起草没过，不能落锁。")
        return 1

    h = sha(src)
    edited = rec.get("draft_hash") is not None and rec["draft_hash"] != h
    vd = vault_dir(root, sid)
    vd.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, vd / "assertions.py")
    meta = {
        "sid": sid, "name": rec["name"], "accepted_at": now(),
        "human_edited": edited, "assert_sha": h,
    }
    (vd / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    shutil.rmtree(d / ".draft", ignore_errors=True)
    rec.update({"stage": "locked", "accepted_at": now(), "human_edited": edited,
                "attempts": 0, "assert_sha": h})
    save_state(root, st)

    print(f"[v] {sid} 已落锁。断言已移出项目目录，项目里不再有明文。")
    if not edited:
        print("[!] 人一个字没改。如果实现和起草是同一个会话，Agent 记得自己写的断言，盲区不成立。")
        print("    两个选一个：要么人现在改断言重跑 accept，要么实现必须换一个新会话。")
    else:
        print("人已实质修改断言，最终版本 Agent 未见全貌。")
    return 0


def cmd_judge(root, args):
    st = load_state(root)
    sid = args.sid
    rec = st["slices"].get(sid)
    if not rec:
        print(f"没有切片 {sid}")
        return 2
    if rec["stage"] == "draft":
        print("还没 accept，断言仍未落锁。先起草、人审、accept。")
        return 2
    if rec["stage"] == "done":
        print("PASS (已完成)")
        return 0
    if rec.get("attempts", 0) >= MAX_ATTEMPTS:
        print("已达重试上限，自动化到此为止。需要人工介入。")
        return 1

    vd = vault_dir(root, sid)
    af = vd / "assertions.py"
    if not af.exists():
        print("保管区里找不到断言，保管区可能被清理了。需要重新 accept。")
        return 2

    code, out = run_assertions(af, slice_dir(root, sid))
    rec["attempts"] = rec.get("attempts", 0) + 1
    ok = code == 0
    (vd / "last_result.json").write_text(json.dumps({
        "at": now(), "ok": ok, "exit": code, "attempt": rec["attempts"],
        "output": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if ok:
        rec["stage"] = "done"
        save_state(root, st)
        print(f"PASS ({sid} 已验收)")
        return 0

    save_state(root, st)
    # 只回传一个比特，不透露哪条挂了、断言写了什么，也不提示查看详情的位置
    print(f"FAIL (attempt {rec['attempts']}/{MAX_ATTEMPTS})")
    if rec["attempts"] >= MAX_ATTEMPTS:
        print("已达重试上限，自动化到此为止。需要人工介入。")
    else:
        print("不要修补，整片重做。失败详情不可见。")
    return 1


def cmd_reveal(root, args):
    vd = vault_dir(root, args.sid)
    f = vd / "last_result.json"
    if not f.exists():
        print("没有判定记录")
        return 2
    r = json.loads(f.read_text(encoding="utf-8"))
    print(f"时间 {r['at']}  结果 {'PASS' if r['ok'] else 'FAIL'}  第 {r['attempt']} 次")
    print("-" * 60)
    print(r["output"][-3000:])
    return 0


def cmd_system(root, args):
    st = load_state(root)
    pending = [k for k, v in st["slices"].items() if v["stage"] != "done"]
    if pending:
        print("还有切片没验收：" + ", ".join(pending))
        print("系统层验收必须在所有切片通过之后。")
        return 1
    vd = vault_dir(root) / "_system"
    af = vd / "assertions.py"
    if not af.exists():
        print("系统层断言未准备。")
        print("需要人写一组组合场景（测切片之间拼起来是否成立），放进保管区的 _system/。")
        return 2
    code, out = run_assertions(af, root, with_loader=True)
    ok = code == 0
    (vd / "last_result.json").write_text(json.dumps({
        "at": now(), "ok": ok, "exit": code, "output": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    if ok:
        st["system_done"] = True
        save_state(root, st)
        print("PASS (系统层验收通过)")
        return 0
    print("FAIL (系统层)。详情：在保管区 _system/last_result.json")
    return 1


def cmd_where(root, args):
    """打印保管区路径。给人用的，Agent 不该执行这个命令。"""
    base = vault_dir(root)
    print(f"项目保管区：{base}")
    for sid in load_state(root).get("slices", {}):
        f = vault_dir(root, sid) / "assertions.py"
        if f.exists():
            print(f"  {sid}: {f}")
    sysf = base / "_system" / "assertions.py"
    print(f"系统层：{sysf}" + ("" if sysf.exists() else "（尚未创建）"))
    return 0


def cmd_status(root, args):
    st = load_state(root)
    if not st["slices"]:
        print("还没有切片")
        return 0
    print(f"项目 {st['project']}    切片 {len(st['slices'])} 个    "
          f"系统层 {'已通过' if st.get('system_done') else '未验收'}")
    print("-" * 60)
    for sid, r in st["slices"].items():
        he = {True: "人改过", False: "人未改", None: "未审"}.get(r.get("human_edited"), "未审")
        print(f"  {sid}  [{r['stage']}]  尝试 {r.get('attempts', 0)}  {he}  {r['name']}")
    done = sum(1 for v in st["slices"].values() if v["stage"] == "done")
    print("-" * 60)
    print(f"完成 {done}/{len(st['slices'])}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="盲切片裁决器")
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    n = sub.add_parser("new")
    n.add_argument("sid")
    n.add_argument("name")
    for name in ("draft", "accept", "judge", "reveal"):
        p = sub.add_parser(name)
        p.add_argument("sid")
    sub.add_parser("system")
    sub.add_parser("status")
    sub.add_parser("where")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
    fn = {
        "init": cmd_init, "new": cmd_new, "draft": cmd_draft, "accept": cmd_accept,
        "judge": cmd_judge, "reveal": cmd_reveal, "system": cmd_system,
        "status": cmd_status, "where": cmd_where,
    }[args.cmd]
    return fn(root, args)


if __name__ == "__main__":
    sys.exit(main())
