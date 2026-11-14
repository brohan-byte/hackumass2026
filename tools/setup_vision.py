"""Download official YOLOE weights into the project, never into the home folder."""
from pathlib import Path
from urllib.request import urlopen
import os
root=Path(__file__).resolve().parent.parent
os.environ.setdefault('YOLO_CONFIG_DIR',str(root/'data/ultralytics'))
folder=root/'models';folder.mkdir(exist_ok=True)
path=folder/'yoloe-26s-seg.pt'
if not path.exists():
    url='https://github.com/ultralytics/assets/releases/download/v8.4.0/yoloe-26s-seg.pt'
    print('Downloading official YOLOE model…',flush=True)
    with urlopen(url,timeout=60) as response:
        data=response.read()
    if len(data)<1_000_000:raise RuntimeError('Unexpected model download size')
    path.write_bytes(data)
from ultralytics import YOLOE
YOLOE(str(path))
print('YOLOE weights loaded:',path)
