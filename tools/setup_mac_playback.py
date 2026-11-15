"""Build the macOS CoreAudio XM5 playback-volume fallback (no Sony SDK needed)."""
from pathlib import Path
import platform
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    if platform.system()!='Darwin':raise SystemExit('Mac playback requires macOS')
    binary=ROOT/'data/sony-sdk/bin/ghostui-mac-playback'
    binary.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['xcrun','clang++','-std=c++17','-fobjc-arc',str(ROOT/'tools/sony/MacPlayback.mm'),
        '-framework','Foundation','-framework','CoreAudio','-framework','AudioToolbox','-o',str(binary)],check=True)
    print('Mac playback bridge ready: '+str(binary))

if __name__=='__main__':main()
