"""Fetch ciphertext only; run existing verifiers against the authenticated local plaintext."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from ephemeral_transfer import unseal


def main():
    vdir,target=sys.argv[1:]
    if not re.fullmatch(r'glb_repair/_[0-9]{6}_[0-9]{4}_v[0-9.]+_ci_[0-9a-f]{6}',vdir):raise ValueError('Unexpected job id')
    if target not in ('darwin-arm64','darwin-x64'):raise ValueError(target)
    folder=Path('versions')/vdir;row=json.loads((folder/'manifest.json').read_text('utf8'))['targets'][target]
    dst=(folder/row['input']).resolve()
    if dst.parent!=(folder/'inputs').resolve():raise ValueError('Input outside job directory')
    dst.parent.mkdir(exist_ok=True)
    tmp=Path(os.environ['RUNNER_TEMP']);enc=tmp/(target+'.sealed');key=tmp/'fsb-runner.key'
    tag=row['input_release_str']
    if tag!='transport-glb_repair-'+folder.name.strip('_'):raise ValueError('Unexpected transport tag')
    for _ in range(110):
        r=subprocess.run(['gh','release','download',tag,'--pattern',enc.name,'--dir',str(tmp),'--clobber'],timeout=1000)
        if r.returncode==0 and enc.is_file():break
        time.sleep(12)
    else:raise RuntimeError('Timed out waiting for encrypted binary')
    try:unseal(enc,dst,key,row['sha256_str'],row['size_int'])
    finally:key.unlink(missing_ok=True)


if __name__=='__main__':main()
