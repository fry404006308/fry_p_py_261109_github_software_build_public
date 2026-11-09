# -*- coding: utf-8 -*-
r"""fry_ci_target.py —— 在 GitHub 的一台目标机上，按版本目录 manifest.json 里的「验收单」验收本平台的包（通用、数据驱动）。

【为什么是数据驱动】上一版（RIP 461）的验收脚本按产品写死了路由（加网一套、仿真一套）。通用打包项目要服务任意软件，
  所以「怎么验」写在每个版本的 manifest.json 里，本脚本只负责：①核对输入没被改 ②平台闸 ③解包 ④照单执行命令
  ⑤检查期望文件 / 输出关键字 / 计数 ⑥把结论落成 verdict.json、把交付件放进 deliverable/。

【manifest.json 的 targets[平台] 字段】
  input         inputs/ 下的压缩包（.zip / .tar.gz）——库的验收包、应用的便携包，或直接是一个 .exe
  kind          "kit"（库）｜ "app"（应用）—— 只用于报告，不改变执行逻辑
  steps         [{name, cmd:[...], cwd, timeout_s, expect_rc, expect_files:[glob], expect_out:[子串], env:{}}]
                占位：{root} = 解包后的顶层目录，{out} = 本机输出目录，{exe} = 包里的主程序（由 exe 字段指出），{python} = CI 的 python，
                {assets} = 版本目录下的 assets/（测试模型等数据）
  exe           主程序在包里的相对路径（应用用；单个 .exe 输入时自动 = 它）
  deliverables  验收通过后要带回的文件 glob（相对 {root} 或 {out}）；空 = 带回输入包本身
只用 Python 标准库。退出码：0 通过 ｜ 1 没过 ｜ 2 输入有问题 / 平台不对。
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
TARGET_LIST = ["win32-x64", "linux-x64", "linux-arm64", "darwin-arm64", "darwin-x64"]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def host_target() -> str:
    s, m = platform.system(), platform.machine().lower()
    if s == "Darwin":
        try:   # Rosetta 里的 python 会谎报 x86_64 ⇒ 以硬件为准
            if subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True).stdout.strip() == "1":
                m = "arm64"
        except OSError:
            pass
    arch = "arm64" if m in ("arm64", "aarch64") else "x64"
    return {"Windows": "win32", "Linux": "linux", "Darwin": "darwin"}.get(s, s.lower()) + "-" + arch


def machine_info() -> Dict[str, str]:
    info = {"platform_str": platform.platform(), "machine_str": platform.machine(), "python_str": sys.version.split()[0],
            "image_str": (os.environ.get("ImageOS", "") + " " + os.environ.get("ImageVersion", "")).strip()}
    if platform.system() == "Linux":
        info["libc_str"] = " ".join(platform.libc_ver())
    if platform.system() == "Darwin":
        info["macos_str"] = platform.mac_ver()[0]
    return info


def extract(archive: Path, dst: Path) -> Path:
    """解包并返回顶层目录；zip 不保存可执行位 ⇒ 解完给 bin / 无后缀文件补 +x。单个 .exe 直接复制。"""
    dst.mkdir(parents=True, exist_ok=True)
    n = archive.name.lower()
    if n.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dst)
            for zi in z.infolist():                       # 还原权限位与符号链接（zipfile 不管这两样；便携包的解释器里有符号链接）
                full = (zi.external_attr >> 16) & 0xFFFF
                p = dst / zi.filename
                if stat.S_ISLNK(full) and os.name != "nt":
                    target = z.read(zi).decode("utf-8")
                    p.unlink()
                    os.symlink(target, p)
                elif full & 0o777:
                    try:
                        os.chmod(p, full & 0o777)
                    except OSError:
                        pass
    elif n.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(archive, "r:*") as t:
            if hasattr(tarfile, "tar_filter"):
                t.extractall(dst, filter="tar")
            else:
                t.extractall(dst)
    else:                                                 # 单个可执行文件：去掉 inputs/ 里的「<平台>__」前缀，恢复成品原名
        shutil.copy2(archive, dst / archive.name.split("__", 1)[-1])
        return dst
    kids = [p for p in dst.iterdir()]
    return kids[0] if len(kids) == 1 and kids[0].is_dir() else dst


def fill(x: str, ctx: Dict[str, str]) -> str:
    for k, v in ctx.items():
        x = x.replace("{" + k + "}", v)
    return x


def diag(exe: str, log: Path) -> None:
    """一步没过且主程序是个文件：把「它依赖谁、怎么找依赖」记进日志（macOS otool / Linux ldd），远程排错只能靠这些。"""
    cmds = []
    if platform.system() == "Darwin":
        cmds = [["otool", "-L", exe], ["otool", "-l", exe], ["codesign", "-dv", exe]]
        cmds += [["otool", "-L", str(p)] for p in Path(exe).parent.glob("*.dylib")]
    elif platform.system() == "Linux":
        cmds = [["ldd", exe], ["file", exe]]
    with open(log, "a", encoding="utf-8", errors="replace") as f:
        for c in cmds:
            try:
                r = subprocess.run(c, capture_output=True, text=True, timeout=60)
                f.write("\n[诊断] $ %s\n%s%s" % (" ".join(c), r.stdout[-6000:], r.stderr[-2000:]))
            except (OSError, subprocess.TimeoutExpired) as exc:
                f.write("\n[诊断] $ %s → %r\n" % (" ".join(c), exc))


def run_step(step: Dict[str, Any], ctx: Dict[str, str], log: Path) -> Dict[str, Any]:
    cmd = [fill(str(c), ctx) for c in step["cmd"]]
    cwd = fill(step.get("cwd", "{root}"), ctx)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.update({k: fill(str(v), ctx) for k, v in (step.get("env") or {}).items()})
    if os.name != "nt" and cmd and os.path.isfile(cmd[0]) and not os.access(cmd[0], os.X_OK):
        try:                                              # 只给「本来不可执行」的补 +x（macOS 上动系统 Python 会 PermissionError）
            os.chmod(cmd[0], os.stat(cmd[0]).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=step.get("timeout_s", 1200), env=env)
        rc, out = p.returncode, (p.stdout + p.stderr).decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        rc, out = -9, "TIMEOUT"
    except OSError as exc:
        rc, out = -8, repr(exc)
    with open(log, "a", encoding="utf-8", errors="replace") as f:
        f.write("\n$ %s\n%s\n[rc=%d, %.1f s]\n" % (" ".join(cmd), out, rc, time.time() - t0))
    print(out[-4000:], flush=True)
    if rc != step.get("expect_rc", 0) and cmd and os.path.isfile(cmd[0]):
        diag(cmd[0], log)
    problems = []
    if rc != step.get("expect_rc", 0):
        problems.append("rc=%d（期望 %d）" % (rc, step.get("expect_rc", 0)))
    for pat in step.get("expect_files", []):
        if not glob.glob(fill(pat, ctx), recursive=True):
            problems.append("缺文件 %s" % pat)
    for sub in step.get("expect_out", []):
        if sub not in out:
            problems.append("输出里没有「%s」" % sub)
    return {"key_str": step.get("name", cmd[0]), "ok_bool": not problems, "detail_str": "；".join(problems) or "rc=%d %.1f s" % (rc, time.time() - t0)}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--version-dir", required=True, help="versions/<软件>/<版本目录>")
    ap.add_argument("--target", required=True, choices=TARGET_LIST)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args(argv)
    vdir = (REPO / ns.version_dir).resolve()
    out = Path(ns.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "deliverable").mkdir(parents=True)
    (out / "logs").mkdir()
    (out / "run").mkdir()
    man = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
    t0 = time.time()
    verdict = {"schema_str": "fry-gh-verdict/2", "software_str": man.get("software_str"), "version_str": man.get("version_str"),
               "version_dir_str": vdir.name, "target_str": ns.target, "host_target_str": host_target(), "machine_dict": machine_info(),
               "started_at_str": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "fingerprint_str": man.get("fingerprint_str", ""),
               "checks_list": [], "ok_bool": False}
    checks = verdict["checks_list"]

    def finish(ok: bool, code: int) -> int:
        # 解包目录不进 artifact：几万个文件、大小写同名（terminfo）、超长路径，Windows 上下载解压会失败；
        # 输入包本身已在 deliverable/，软件跑出来的结果（run/out，截图 / json）留着当证据
        shutil.rmtree(out / "run" / "pkg", ignore_errors=True)
        verdict["ok_bool"] = ok
        verdict["seconds_float"] = round(time.time() - t0, 1)
        verdict["deliverable_dict"] = {p.name: sha256_file(p) for p in sorted((out / "deliverable").iterdir()) if p.is_file()}
        (out / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("\n%s %s ｜ %s %s ｜ %d 项检查 ｜ %.1f s" % ("✓ 验收通过" if ok else "✗ 验收没过", ns.target, man.get("software_str"),
              man.get("version_str"), len(checks), verdict["seconds_float"]))
        for c in checks:
            print("  %s %-24s %s" % ("✓" if c["ok_bool"] else "✗", c["key_str"], c["detail_str"][:200]))
        return code

    host_ok = verdict["host_target_str"] == ns.target
    checks.append({"key_str": "平台闸", "ok_bool": host_ok, "detail_str": "本机 %s ｜ 要验 %s" % (verdict["host_target_str"], ns.target)})
    row = (man.get("targets") or {}).get(ns.target)
    if not host_ok or not row:
        if not row:
            checks.append({"key_str": "manifest 含本平台", "ok_bool": False, "detail_str": "manifest 没登记 %s" % ns.target})
        return finish(False, 2)
    inp = vdir / row["input"]
    if not inp.is_file() and row.get("input_release_str"):        # 大文件（>90 MB）不在 git 里：从临时传输 release 下载
        inp.parent.mkdir(parents=True, exist_ok=True)
        asset = row.get("input_asset_str") or inp.name           # 资产名是 ASCII 的（GitHub 会改写中文资产名），下载后改回 inputs/ 里的原名
        for k in range(3):
            r = subprocess.run(["gh", "release", "download", row["input_release_str"], "-p", asset, "-D", str(inp.parent), "--clobber"],
                               capture_output=True, text=True, cwd=str(REPO))
            if r.returncode == 0 and (inp.parent / asset).is_file():
                if asset != inp.name:
                    os.replace(inp.parent / asset, inp)
                break
            print("下载 %s 第 %d 次失败：%s" % (inp.name, k + 1, (r.stdout + r.stderr)[-300:]), flush=True)
            time.sleep(10)
        checks.append({"key_str": "大文件下载", "ok_bool": inp.is_file(), "detail_str": "%s ← release %s" % (inp.name, row["input_release_str"])})
    want = row.get("sha256_str", "")
    good = inp.is_file() and (not want or sha256_file(inp) == want)
    checks.append({"key_str": "输入闸 sha256", "ok_bool": good, "detail_str": row["input"] if good else "缺输入或 sha256 不符"})
    if not good:
        return finish(False, 2)
    root = extract(inp, out / "run" / "pkg")
    exe = row.get("exe", "")
    ctx = {"root": str(root), "out": str(out / "run" / "out"), "python": sys.executable, "assets": str(vdir / "assets"),
           "exe": str(root / exe) if exe else (str(root / inp.name.split("__", 1)[-1]) if not inp.name.lower().endswith((".zip", ".tar.gz", ".tgz", ".tar")) else "")}
    Path(ctx["out"]).mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        xattr = shutil.which("xattr")
        if xattr:                                         # 下载隔离属性会让 Gatekeeper 拦 dylib / 可执行文件
            subprocess.run([xattr, "-dr", "com.apple.quarantine", str(root)], capture_output=True)
    for step in row.get("steps", []):
        try:                                              # 验收脚本自己出错也要落成一条失败检查，verdict.json 必须写出来
            checks.append(run_step(step, ctx, out / "logs" / "verify.log"))
        except Exception as exc:                          # noqa: BLE001
            checks.append({"key_str": step.get("name", "?"), "ok_bool": False, "detail_str": "验收脚本异常：%r" % exc})
    ok = all(c["ok_bool"] for c in checks) and bool(row.get("steps"))
    if not row.get("steps"):
        checks.append({"key_str": "验收单", "ok_bool": False, "detail_str": "steps 为空 = 什么都没验"})
    if ok:
        pats = row.get("deliverables") or []
        files = [Path(f) for pat in pats for f in glob.glob(fill(pat, ctx), recursive=True) if os.path.isfile(f)] if pats else [inp]
        for f in files:
            shutil.copy2(f, out / "deliverable" / f.name)
        if not files:
            checks.append({"key_str": "交付件", "ok_bool": False, "detail_str": "deliverables 一个都没匹配到"})
            ok = False
    return finish(ok, 0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
