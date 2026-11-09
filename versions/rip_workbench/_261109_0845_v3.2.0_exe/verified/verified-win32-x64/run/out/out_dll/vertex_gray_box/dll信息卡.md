# dll 信息卡（★393 自动生成）

> 这一页是**这次出片真正用的那个 dll** 自己报的 —— 同事要资料时直接把它发过去。

| 项 | 值 |
| --- | --- |
| 动态库 | C:\Users\runneradmin\AppData\Local\Temp\_MEI62282\fry_project_components\HS200_halftone_dll\_bin\win32-x64\fry_halftone.dll |
| 版本 | 0.0.0-dev |
| 算法 / 引擎 | ? / cpp |
| 算法指纹 | aabd5ff0065d2d11d2bebfcc57d6cbf1599b627f9872c634744a17609961338d |
| dll 的 sha256 | 0b04cba741bc44d631e890ade1cd50e3d2627cd4d5e3b957ed5d9511cb39cf68 |
| 平台 | win32-x64 |
| 构建时间 | 2026-09-23T01:05:44-0700 |
| 构建机器 | Windows AMD64 |
| 源码提交 | 18cb9bf5021e7b8fc2d05a013062c2d28f1f7d0e |
| 编译器 | MSVC 19.50.35728.0 |
| 运行库 | MSVC C++ 运行库静态链接；UCRT 动态链接系统 ucrtbase.dll ⇒ **不需要装 VC++ Redistributable** |
| 调用约定 / ABI | C ABI；Windows 调用约定 __stdcall，其它平台默认 |
| 最低系统 | Windows 10 x64 及以上 |
| 线程模型 | 同一时刻只跑一个作业（并发调用返回 6 BUSY）；Cancel 可从其它线程调；进度回调在调用线程上同步触发 |
| 参数个数 / schema | 18 / fry-halftone-params/3 |
| 交付清单 | 查了 6 项, 全齐 |

## 想自己验证 / 集成

- 自检（包完整吗、能加载吗、版本一致吗）：`python verify_delivery.py`（在 dll 所在目录）
- 接口声明：`fry_halftone.h` ｜ 参数：`SDK_参数说明.md`（机读版 `params_schema.json`）
- 完整包（含导入库 .lib、C/C# /Python 示例、许可、变更历史）：向维护方要「交付给业务」的 zip，
  里面 17 项按 `delivery_manifest.json` 可逐项核对。
