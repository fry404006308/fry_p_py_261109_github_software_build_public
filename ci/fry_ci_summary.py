# -*- coding: utf-8 -*-
r"""fry_ci_summary.py —— 汇总各平台 verdict：manifest 登记的平台一个都不能少、每个都 ✓ 才算通过（少一台 = 红）。
用法：python ci/fry_ci_summary.py --version-dir versions/<软件>/<目录> --verdicts <目录> --out summary.json"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def summarize(man: dict, verdicts: list) -> dict:
    by = {v["target_str"]: v for v in verdicts}
    rows = []
    for t in sorted((man.get("targets") or {})):
        v = by.get(t)
        rows.append({"target_str": t, "ok_bool": bool(v and v["ok_bool"]), "present_bool": v is not None,
                     "machine_str": (v or {}).get("machine_dict", {}).get("platform_str", ""),
                     "checks_int": len((v or {}).get("checks_list", [])),
                     "failed_list": [c["key_str"] for c in (v or {}).get("checks_list", []) if not c["ok_bool"]],
                     "seconds_float": (v or {}).get("seconds_float")})
    return {"schema_str": "fry-gh-summary/2", "software_str": man.get("software_str"), "version_str": man.get("version_str"),
            "version_dir_str": man.get("dir_str"), "ok_bool": bool(rows) and all(r["ok_bool"] for r in rows),
            "passed_int": sum(r["ok_bool"] for r in rows), "expected_int": len(rows), "rows_list": rows,
            "summarized_at_str": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def markdown(s: dict) -> str:
    out = ["## %s %s v%s ｜ %s" % ("✅" if s["ok_bool"] else "❌", s["software_str"], s["version_str"], s["version_dir_str"]), "",
           "通过 %d / %d" % (s["passed_int"], s["expected_int"]), "", "| 平台 | 结论 | 检查 | 没过的 | 机器 | 秒 |", "|---|---|---|---|---|---|"]
    for r in s["rows_list"]:
        out.append("| %s | %s | %d | %s | %s | %s |" % (r["target_str"], "✅" if r["ok_bool"] else ("❌" if r["present_bool"] else "⚪ 没跑"),
                   r["checks_int"], "、".join(r["failed_list"]) or "—", r["machine_str"], r["seconds_float"]))
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--version-dir", required=True)
    ap.add_argument("--verdicts", required=True)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args(argv)
    man = json.loads((REPO / ns.version_dir / "manifest.json").read_text(encoding="utf-8"))
    s = summarize(man, [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(ns.verdicts).rglob("verdict.json"))])
    Path(ns.out).write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = markdown(s)
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    return 0 if s["ok_bool"] else 1


if __name__ == "__main__":
    sys.exit(main())
