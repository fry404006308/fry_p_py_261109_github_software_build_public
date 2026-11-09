# -*- coding: utf-8 -*-
"""验收脚本自测：照单执行、各项闸（sha256 / 平台 / 空验收单 / 期望文件 / 期望输出）两个方向都验；汇总少一台即红。
python -m pytest -q tests"""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ci"))
import fry_ci_summary  # noqa: E402
import fry_ci_target  # noqa: E402

HOST = fry_ci_target.host_target()


def make_version(tmp: Path, steps, target=HOST, bad_sha=False):
    vdir = tmp / "versions" / "demo" / "_v"
    (vdir / "inputs").mkdir(parents=True)
    z = vdir / "inputs" / "kit.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("kit/data/hello.txt", "hello fry\n")
    sha = "0" * 64 if bad_sha else hashlib.sha256(z.read_bytes()).hexdigest()
    man = {"software_str": "demo", "version_str": "1.0.0", "targets": {target: {"input": "inputs/kit.zip", "sha256_str": sha, "steps": steps}}}
    (vdir / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    return vdir


def run(vdir, tmp, target=HOST):
    rc = fry_ci_target.main(["--version-dir", str(vdir), "--target", target, "--out", str(tmp / "out")])
    return rc, json.loads((tmp / "out" / "verdict.json").read_text(encoding="utf-8"))


PY_READ = ["{python}", "-c", "import sys;print(open(sys.argv[1]).read())", "{root}/data/hello.txt"]


def test_pass(tmp_path):
    rc, v = run(make_version(tmp_path, [{"name": "read", "cmd": PY_READ, "expect_out": ["hello fry"]}]), tmp_path)
    assert rc == 0 and v["ok_bool"] and (tmp_path / "out" / "deliverable" / "kit.zip").is_file()


def test_expect_out_and_files_fail(tmp_path):
    steps = [{"name": "read", "cmd": PY_READ, "expect_out": ["NOT THERE"], "expect_files": ["{out}/missing.json"]}]
    rc, v = run(make_version(tmp_path, steps), tmp_path)
    assert rc == 1 and not v["ok_bool"] and "缺文件" in v["checks_list"][-1]["detail_str"]


def test_sha_gate(tmp_path):
    rc, v = run(make_version(tmp_path, [{"name": "read", "cmd": PY_READ}], bad_sha=True), tmp_path)
    assert rc == 2 and not v["ok_bool"]


def test_platform_gate(tmp_path):
    other = "darwin-arm64" if HOST != "darwin-arm64" else "linux-x64"
    rc, v = run(make_version(tmp_path, [{"name": "read", "cmd": PY_READ}], target=other), tmp_path, target=other)
    assert rc == 2 and v["checks_list"][0]["key_str"] == "平台闸" and not v["checks_list"][0]["ok_bool"]


def test_empty_steps_is_red(tmp_path):
    rc, v = run(make_version(tmp_path, []), tmp_path)
    assert rc == 1 and not v["ok_bool"]


def test_summary_needs_every_platform():
    man = {"software_str": "d", "version_str": "1", "targets": {"linux-x64": {}, "win32-x64": {}}}
    ok = {"target_str": "linux-x64", "ok_bool": True, "checks_list": []}
    assert not fry_ci_summary.summarize(man, [ok])["ok_bool"]                       # 少一台 = 红
    assert fry_ci_summary.summarize(man, [ok, dict(ok, target_str="win32-x64")])["ok_bool"]


def test_no_source_in_repo():
    """本仓自己也不许混进软件源码：除 ci/ 与 tests/ 以外不应有 .py / .c / .h（压缩包里的由私有仓推送前核对）。"""
    bad = [p for p in REPO.rglob("*") if p.is_file() and p.suffix in (".py", ".c", ".cc", ".cpp", ".h", ".hpp")
           and p.relative_to(REPO).parts[0] not in ("ci", "tests", ".git")]
    assert bad == []


def test_single_exe_input_keeps_original_name(tmp_path):
    vdir = tmp_path / "versions" / "demo" / "_e"
    (vdir / "inputs").mkdir(parents=True)
    exe = vdir / "inputs" / ("%s__tool.py" % HOST)                                  # 用 .py 冒充单文件可执行
    exe.write_text("import sys;open(sys.argv[1],'w').write('ok')\n", encoding="utf-8")
    man = {"software_str": "demo", "version_str": "1", "targets": {HOST: {"input": "inputs/" + exe.name, "exe": "tool.py",
           "steps": [{"name": "run", "cmd": ["{python}", "{exe}", "{out}/r.txt"], "expect_files": ["{out}/r.txt"]}]}}}
    (vdir / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    rc, v = run(vdir, tmp_path)
    assert rc == 0 and v["ok_bool"]
    assert not (tmp_path / "out" / "run" / "pkg").exists() and (tmp_path / "out" / "run" / "out" / "r.txt").is_file()


def test_step_exception_still_writes_verdict(tmp_path, monkeypatch):
    """某一步让验收脚本自己抛异常（如 macOS 上 chmod 系统 Python 被拒），也必须写出 verdict 并判红，不能整个崩掉。"""
    vdir = make_version(tmp_path, [{"name": "boom", "cmd": PY_READ}])
    def boom(*a, **k):
        raise PermissionError("Operation not permitted")
    monkeypatch.setattr(fry_ci_target, "run_step", boom)
    rc, v = run(vdir, tmp_path)
    assert rc == 1 and not v["ok_bool"] and "验收脚本异常" in v["checks_list"][-1]["detail_str"]
