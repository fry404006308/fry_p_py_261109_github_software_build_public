"""Opt-in Intel CI fixture. Do not call an Intel LTS result a Blender 5.x result."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile


def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main(addon):
    assert sys.platform=='darwin' and platform.machine()=='x86_64'
    assert digest(addon)=='1e712b640c73957ed2f4f5bab672ebda608628c233f9ab0e9103ade92482ae70'
    app=Path.home()/'Applications/Blender.app';app.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as tmp:
        root=Path(tmp);disk=root/'blender.dmg';mnt=root/'mnt';mnt.mkdir()
        subprocess.run(['curl','-fsSL','--retry','3','-o',str(disk),'https://download.blender.org/release/Blender4.5/blender-4.5.16-macos-x64.dmg'],check=True)
        assert digest(disk)=='009e437b33e5e131340b8d91eb9005d69ef6f1c67eff1402953a7d40cf94638f'
        subprocess.run(['hdiutil','attach','-readonly','-nobrowse','-quiet','-mountpoint',str(mnt),str(disk)],check=True)
        try:shutil.copytree(mnt/'Blender.app',app,symlinks=True)
        finally:subprocess.run(['hdiutil','detach','-quiet',str(mnt)],check=True)
    ext=Path.home()/'Library/Application Support/Blender/4.5/extensions/blender_org';ext.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(addon) as z:
        for member in z.namelist():
            if not (ext/member).resolve().is_relative_to(ext.resolve()):raise ValueError(member)
        z.extractall(ext)
    result=subprocess.check_output([str(app/'Contents/MacOS/Blender'),'--version'],text=True)
    assert 'Blender 4.5.16' in result
    print(result.splitlines()[0])


if __name__=='__main__':main(Path(sys.argv[1]))
