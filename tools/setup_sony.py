"""Fetch a pinned Sony protocol implementation and build GhostUI's macOS bridge."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SDK=ROOT/'data/sony-sdk'
REPOSITORY='https://github.com/mos9527/SonyHeadphonesClient.git'
COMMIT='3c8f3330c85d45c29e7b76f718082a8d4fe402f1'


def run(command):
    subprocess.run(command,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,help='Use an already fetched checkout of the pinned source')
    parser.add_argument('--build-dir',type=Path,help='Optional existing build directory for this source')
    args=parser.parse_args()
    if platform.system()!='Darwin':parser.error('The Sony bridge currently requires macOS')
    for command in ('git','cmake','xcrun'):
        if not shutil.which(command):parser.error('Install '+command+' before building the Sony bridge')
    SDK.mkdir(parents=True,exist_ok=True)
    source=args.source.resolve() if args.source else SDK/'source'
    if not source.exists():
        run(['git','init',str(source)])
        run(['git','-C',str(source),'remote','add','origin',REPOSITORY])
        run(['git','-C',str(source),'fetch','--depth','1','origin',COMMIT])
        run(['git','-C',str(source),'checkout','--detach',COMMIT])
    revision=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision!=COMMIT:parser.error('Source revision differs from the inspected commit; use the default pinned checkout')
    build=args.build_dir.resolve() if args.build_dir else SDK/('build-'+hashlib.sha256(str(source).encode()).hexdigest()[:8])
    run(['cmake','-S',str(ROOT/'tools/sony'),'-B',str(build),'-DSONY_SOURCE_DIR='+str(source),'-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake','--build',str(build),'--target','ghostui-sony','--parallel','2'])
    executable=SDK/'bin/ghostui-sony'
    executable.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(build/'ghostui-sony',executable)
    shutil.copy2(source/'LICENSE',SDK/'UPSTREAM-LICENSE')
    checksum=hashlib.sha256(executable.read_bytes()).hexdigest()
    (SDK/'source.json').write_text(json.dumps({'repository':REPOSITORY,'commit':COMMIT,'binarySha256':checksum},indent=2))
    print('Sony bridge ready: '+str(executable))
    print('Next: .venv-vision/bin/python tools/probe_sony.py --list')


if __name__=='__main__':main()
