# -*- coding: utf-8 -*-
"""GLB修复软件真机验收的准备步骤（只在 GitHub runner 上跑，不进软件包）。

GitHub 的 runner 和用户的电脑差两样东西，GLB修复软件的自检都要用：
  ① OpenGL 3.3：六视图 / 白模细节 / 3D 预览靠 pyrender + pyglet 离屏渲染。Windows runner 只有 GDI 的 OpenGL 1.1
     （首次验收：glGenVertexArrays 未定义）→ 放 Mesa（llvmpipe 软件渲染）的 opengl32.dll 到 exe 旁边；
     Linux runner 缺 GLU / Mesa → 由 apt 步骤装（这里只做检查）。
  ② Blender 5.2 + 3D Print Toolbox：交付清单要 Blender 原生导入对象数与十项（首次验收 mac arm64 只差这一项）。
     Windows / Linux / Apple 芯片 mac 装官方包；Intel mac 没有 Blender 5（官方 5.0 起不出 Intel 版）→ 跳过，
     自检用 FRY_SELFTEST_ALLOW_NO_BLENDER=1 只放过「仅因没有 Blender」而缺的那几项（selftest.py 里写明）。
用法：python ci_prepare.py <主程序路径> <assets 目录> <Blender 版本，如 5.2.2>
Blender 装在 GLB修复软件自己会找的标准位置（HA400._find_blender）：Windows「Program Files\\Blender Foundation\\Blender 5.2」、
Linux「~/blender-<版本>-linux-x64」、mac「~/Applications/Blender.app」—— 不用设环境变量，也不会被打进验收产物上传。
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

EXE, ASSETS, BV = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
MAJOR = '.'.join(BV.split('.')[:2])
SYS, ARCH = platform.system(), platform.machine().lower()
BLENDER_HOME = Path(os.environ.get('RUNNER_TEMP') or '/tmp') / 'ci_blender'      # 只放下载的安装包，不放装好的 Blender


def say(t):
    print(t, flush=True)


def fetch(url, dst):
    say('下载 %s' % url)
    req = urllib.request.Request(url, headers={'User-Agent': 'fry-ci'})
    with urllib.request.urlopen(req, timeout=600) as r, open(dst, 'wb') as f:
        shutil.copyfileobj(r, f, 1 << 20)
    return dst


def toolbox(ext_root: Path):
    z = ASSETS / 'print3d_toolbox.zip'
    ext_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(ext_root)
    say('3D Print Toolbox → %s（%s）' % (ext_root, sorted(p.name for p in ext_root.iterdir())))


def mesa_windows():
    api = 'https://api.github.com/repos/pal1000/mesa-dist-win/releases/latest'
    req = urllib.request.Request(api, headers={'User-Agent': 'fry-ci', 'Authorization': 'Bearer ' + os.environ.get('GH_TOKEN', '')}
                                 if os.environ.get('GH_TOKEN') else {'User-Agent': 'fry-ci'})
    rel = json.loads(urllib.request.urlopen(req, timeout=120).read())
    # ★ 第 4 次验收：Mesa 26 的 msvc 包里已经没有 OpenGL（opengl32.dll / libgallium_wgl.dll），只剩 Vulkan / D3D12 那几样；
    #   mingw 包里还有（实测 26.2.6：x64/opengl32.dll + libgallium_wgl.dll + libEGL / libGLESv2）
    asset = next(a for a in rel['assets'] if a['name'].endswith('release-mingw.7z'))
    tmp = BLENDER_HOME.parent / 'ci_mesa'
    tmp.mkdir(parents=True, exist_ok=True)
    arc = fetch(asset['browser_download_url'], tmp / asset['name'])
    sz = shutil.which('7z') or r'C:\Program Files\7-Zip\7z.exe'
    subprocess.run([sz, 'x', '-y', '-o' + str(tmp / 'x'), str(arc)], check=True, capture_output=True)
    # ★ 第 3 ~ 5 次验收的结论：
    #   · Mesa 26 的 msvc 包已不带 OpenGL，要用 mingw 包；
    #   · 把 opengl32.dll 放到 exe 旁边：进程确实加载了它（诊断：opengl32 = …\\pkg\\opengl32.DLL），但 pyglet 建上下文仍失败；
    #   · 交互式 systemwidedeploy.cmd 会等输入（5 分钟超时）。
    # 第 6 次：照 GitHub 上常用的 setup-mesa-dist-win 的做法，非交互 `systemwidedeploy.cmd 1`（桌面 OpenGL 驱动，系统级），
    #   不再往 exe 旁边放 dll（避免两份 opengl32 混用）。
    dep = tmp / 'x' / 'systemwidedeploy.cmd'
    r = subprocess.run(['cmd', '/c', str(dep), '1'], text=True, capture_output=True, cwd=str(dep.parent), timeout=300,
                       stdin=subprocess.DEVNULL)
    say('systemwidedeploy 1 rc=%d：%s' % (r.returncode, (r.stdout + r.stderr)[-800:].replace('\n', ' | ')))


def main():
    BLENDER_HOME.mkdir(parents=True, exist_ok=True)
    say('平台 %s %s ｜ 主程序 %s ｜ Blender 目录 %s' % (SYS, ARCH, EXE, BLENDER_HOME))
    if SYS == 'Windows':
        try:                                                      # Mesa 没装上也继续装 Blender（两件事互不相干）
            mesa_windows()
        except Exception as exc:                                  # noqa: BLE001
            say('Mesa 没装上：%r' % exc)
        z = fetch('https://download.blender.org/release/Blender%s/blender-%s-windows-x64.zip' % (MAJOR, BV), BLENDER_HOME / 'b.zip')
        with zipfile.ZipFile(z) as zf:
            zf.extractall(BLENDER_HOME)
        dst = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Blender Foundation' / ('Blender ' + MAJOR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(BLENDER_HOME / ('blender-%s-windows-x64' % BV)), str(dst))
        exe = dst / 'blender.exe'
        toolbox(Path(os.environ['APPDATA']) / 'Blender Foundation' / 'Blender' / MAJOR / 'extensions' / 'blender_org')
    elif SYS == 'Linux':
        t = fetch('https://download.blender.org/release/Blender%s/blender-%s-linux-x64.tar.xz' % (MAJOR, BV), BLENDER_HOME / 'b.tar.xz')
        with tarfile.open(t) as tf:
            tf.extractall(Path.home())
        exe = Path.home() / ('blender-%s-linux-x64' % BV) / 'blender'
        toolbox(Path.home() / '.config' / 'blender' / MAJOR / 'extensions' / 'blender_org')
    elif SYS == 'Darwin' and ARCH == 'arm64':
        d = fetch('https://download.blender.org/release/Blender%s/blender-%s-macos-arm64.dmg' % (MAJOR, BV), BLENDER_HOME / 'b.dmg')
        mnt = BLENDER_HOME / 'mnt'
        subprocess.run(['hdiutil', 'attach', '-nobrowse', '-quiet', '-mountpoint', str(mnt), str(d)], check=True)
        app = Path.home() / 'Applications' / 'Blender.app'
        app.parent.mkdir(parents=True, exist_ok=True)             # ★172：目录不存在时 cp 会把 Blender.app 复制成 ~/Applications 本身
        shutil.copytree(mnt / 'Blender.app', app, symlinks=True)
        subprocess.run(['hdiutil', 'detach', '-quiet', str(mnt)])
        subprocess.run(['xattr', '-dr', 'com.apple.quarantine', str(app)])
        exe = app / 'Contents' / 'MacOS' / 'Blender'
        toolbox(Path.home() / 'Library' / 'Application Support' / 'Blender' / MAJOR / 'extensions' / 'blender_org')
    else:
        say('跳过 Blender：Blender %s 没有 %s %s 的官方包（Intel mac）—— 自检按 FRY_SELFTEST_ALLOW_NO_BLENDER 处理' % (BV, SYS, ARCH))
        say('ci-prepare-ok')
        return 0
    r = subprocess.run([str(exe), '--version'], capture_output=True, text=True, timeout=300)
    say('Blender：%s' % (r.stdout.strip().splitlines() or ['?'])[0])
    say('ci-prepare-ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
