# fry_p_py_261109_github_software_build_public

**多平台真机验收仓：只放打包好的二进制和验收脚本，不放任何源码。**
*A binaries-only verification repo: packaged builds go in, GitHub runs them on real Windows / Linux / macOS machines, verdicts come out. No source code lives here.*

## 它做什么

```
私有仓（打包）                         本仓（GitHub）                                  私有仓（结论）
fry_sbuild publish ──推送──> versions/<软件>/<版本目录>/ ──workflow_dispatch──> fry_verify ──下载──> build/<软件>/verified/
                              inputs/<平台>__<文件>          plan：manifest 登记了哪些平台
                              manifest.json（验收单）         verify：每个平台一台真机照单执行
                              history.json                   summary：登记的平台一个都不能少
```

| 平台 | GitHub 机器 | 典型输入 |
|---|---|---|
| win32-x64 | windows-2022 | 单文件 exe、dll 验收包 |
| linux-x64 | ubuntu-22.04 | 便携包 .tar.gz、so 验收包 |
| linux-arm64 | ubuntu-24.04-arm | so 验收包 |
| darwin-arm64 | macos-15（Apple 芯片） | 便携包 .zip（内含 .app）、dylib 验收包 |
| darwin-x64 | macos-15-intel | 同上 |

## 验收单（manifest.json → targets[平台]）

```json
{"input": "inputs/darwin-arm64__App_v1.0.0_darwin-arm64.zip", "sha256_str": "…", "kind": "app",
 "exe": "App.app/Contents/MacOS/App",
 "steps": [{"name": "selftest", "cmd": ["{exe}", "--selftest", "{out}/out"], "expect_files": ["{out}/out/result.json"]}]}
```

占位：`{root}` 解包后的顶层目录、`{exe}` 主程序、`{out}` 本机输出目录、`{python}` CI 的 Python。
每步可检查退出码 `expect_rc`、生成的文件 `expect_files`、输出里的关键字 `expect_out`。

## 手动触发

```bash
gh workflow run fry_verify.yml -f version_dir=hello_app/_261109_0800_v0.1.0_app
```

## 规则

- 只放二进制：推送前私有仓按内容指纹核对每个压缩包里的每个文件（换行风格不同也认得出），命中项目源码即拒推。
- 输入防篡改：每个输入的 sha256 写在 manifest 里，CI 第一步先核对。
- 平台闸：在哪台机器上验就必须是哪个平台（Rosetta 里的 Python 报 x86_64 也会按硬件改正）。
- release：只上传二进制；建好后下载核对，再删除 release（GitHub 会给 release 自动附源码压缩包）。

## 目录

```
ci/fry_ci_target.py      一台机器上的验收（只用 Python 标准库）
ci/fry_ci_summary.py     汇总：登记的平台都通过才算通过
ci/workflows/fry_verify.yml   workflow 正本（由私有仓复制到 .github/workflows/）
tests/                   验收脚本自己的测试
versions/<软件>/          各版本的输入、验收单、真机结论
```
