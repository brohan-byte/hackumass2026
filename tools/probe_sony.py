"""List/probe paired XM5s with the online Sony implementation before using AR."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ghostui_backend.integrations.sony import BRIDGE, SonyAdapter


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address',nargs='?',help='Optional paired XM5 Bluetooth MAC address')
    parser.add_argument('--list',action='store_true',help='List paired XM5s without opening control sessions')
    parser.add_argument('--volume',type=int,help='Explicitly change volume in the reported native range, then read it back')
    args=parser.parse_args()
    if not BRIDGE.is_file():parser.exit(1,'Run .venv-vision/bin/python tools/setup_sony.py first.\n')
    if args.list:
        raise SystemExit(subprocess.call([str(BRIDGE),'--list']))
    adapter=None
    try:
        adapter=SonyAdapter(args.address)
        print(json.dumps({'model':adapter.model,'firmware':adapter.firmware,'address':adapter.address,
                          'capabilities':adapter.capabilities,'state':adapter.request()},indent=2),flush=True)
        if args.volume is not None:
            from ghostui_backend.contracts import validate_command
            validate_command(adapter.limits,('volume',args.volume))
            state=adapter.request(('volume',args.volume))
            if state['volume']!=args.volume:raise ValueError('Sony volume did not match requested value')
            print(json.dumps({'confirmedState':state}),flush=True)
    except Exception as exc:
        parser.exit(1,'Sony probe: '+str(exc)+'\n')
    finally:
        if adapter:adapter.close()


if __name__=='__main__':main()
