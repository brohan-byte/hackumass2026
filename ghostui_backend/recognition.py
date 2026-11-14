"""Local YOLOE visual enrollment. Images stay on the Mac, never sent to Gemini."""
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT/'data/ultralytics'))
MODEL = ROOT / 'models/yoloe-26s-seg.pt'

class VisionBusy(Exception): pass

class RecognitionService:
    def __init__(self, device_id, storage=None, model_path=None):
        self.folder = (Path(storage) if storage else ROOT/'data/vision') / hashlib.sha256(device_id.encode()).hexdigest()[:16]
        self.model_path = Path(model_path) if model_path else MODEL
        self.lock = threading.Lock()
        self.model = None
        self.prompted = False

    def files(self): return sorted(self.folder.glob('view-*.json'))

    def status(self):
        return {'views': len(self.files()), 'modelAvailable': self.model_path.is_file(),
                'engine': 'YOLOE visual prompts', 'maxViews': 4}

    @staticmethod
    def image(value):
        from PIL import Image
        if not isinstance(value, str) or len(value)>1_500_000:
            raise ValueError('Image must be base64 JPEG under 1 MB')
        try: data=base64.b64decode(value, validate=True)
        except Exception: raise ValueError('Invalid image encoding') from None
        if len(data)>1_000_000: raise ValueError('Image exceeds 1 MB')
        image=Image.open(io.BytesIO(data))
        if image.format != 'JPEG' or image.width>1600 or image.height>1600:
            raise ValueError('Expected JPEG, at most 1600 pixels per side')
        image.load()
        return image.convert('RGB')

    @staticmethod
    def box(value):
        if not isinstance(value,list) or len(value)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in value):
            raise ValueError('Expected normalized [x,y,width,height]')
        x,y,w,h=value
        if x<0 or y<0 or w<=0.02 or h<=0.02 or x+w>1.001 or y+h>1.001:
            raise ValueError('Box is outside image')
        return value

    def enroll(self, encoded, box):
        if not self.lock.acquire(False): raise VisionBusy('Vision is busy; retry shortly')
        try:
            image=self.image(encoded);box=self.box(box)
            files=self.files()
            if len(files)>=4: raise ValueError('Four views already saved. Clear enrollment to start over.')
            self.folder.mkdir(parents=True,exist_ok=True)
            name=f'view-{len(files)}'
            image.save(self.folder/(name+'.jpg'),quality=90)
            (self.folder/(name+'.json')).write_text(json.dumps({'box':box}))
            self.prompted=False
            return self.status()
        finally:self.lock.release()

    def clear(self):
        if not self.lock.acquire(False): raise VisionBusy('Vision is busy')
        try:
            for path in self.files():
                path.with_suffix('.jpg').unlink(missing_ok=True)
                path.unlink()
            self.prompted=False
            return self.status()
        finally:self.lock.release()

    def reference(self):
        from PIL import Image
        import numpy as np
        files=self.files()
        if not files: raise ValueError('Enroll at least one boxed view first')
        # Each view gets its own temporary class embedding. All map back to
        # the same registered device; averaging views can dilute useful features.
        # These are visual prompts, not a newly trained device-specific model.
        tile=320
        mosaic=Image.new('RGB',(tile*2,tile*2),(100,100,100));boxes=[]
        for i,path in enumerate(files):
            image=Image.open(path.with_suffix('.jpg')).convert('RGB')
            x,y,w,h=json.loads(path.read_text())['box']
            # Preserve a small context margin, but dedicate most of each tile to
            # the selected object instead of shrinking the entire room photo.
            px,py,pw,ph=x*image.width,y*image.height,w*image.width,h*image.height
            margin=0.08*max(pw,ph)
            leftCrop=max(0,int(px-margin));topCrop=max(0,int(py-margin))
            rightCrop=min(image.width,int(math.ceil(px+pw+margin)))
            bottomCrop=min(image.height,int(math.ceil(py+ph+margin)))
            crop=image.crop((leftCrop,topCrop,rightCrop,bottomCrop))
            scale=min((tile-16)/crop.width,(tile-16)/crop.height)
            width,height=round(crop.width*scale),round(crop.height*scale)
            left=(i%2)*tile+(tile-width)//2;top=(i//2)*tile+(tile-height)//2
            mosaic.paste(crop.resize((width,height)),(left,top))
            sx,sy=width/crop.width,height/crop.height
            boxes.append([left+(px-leftCrop)*sx,top+(py-topCrop)*sy,
                          left+(px+pw-leftCrop)*sx,top+(py+ph-topCrop)*sy])
        return mosaic, {'bboxes':np.array(boxes,dtype=np.float32),'cls':np.arange(len(boxes),dtype=np.int32)}

    def detect(self, encoded):
        if not self.lock.acquire(False): raise VisionBusy('Vision is busy; dropping this frame')
        try:
            image=self.image(encoded)
            if not self.files(): return {'detections':[],'views':0,'latencyMs':0}
            if not self.model_path.is_file():
                raise ValueError('YOLOE weights missing. Run .venv-vision/bin/python tools/setup_vision.py')
            started=time.perf_counter()
            if self.model is None:
                from ultralytics import YOLOE
                self.model=YOLOE(str(self.model_path))
            options={'conf':0.35,'imgsz':640,'verbose':False,'device':os.environ.get('GHOSTUI_VISION_DEVICE','cpu')}
            if not self.prompted:
                from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor
                reference,prompts=self.reference()
                # Ultralytics documents refer_image as installing the visual class
                # embeddings for subsequent frames. No prompts on later calls.
                results=self.model.predict(image,refer_image=reference,visual_prompts=prompts,
                                           predictor=YOLOEVPSegPredictor,**options)
                self.prompted=True
            else: results=self.model.predict(image,**options)
            detections=[]
            for result in results:
                if result.boxes is None: continue
                for coords,score,cls in zip(result.boxes.xyxy.cpu().tolist(),result.boxes.conf.cpu().tolist(),result.boxes.cls.cpu().tolist()):
                    if int(cls) not in range(len(self.files())): continue
                    x1,y1,x2,y2=coords
                    x1=max(0,min(1,x1/image.width));x2=max(0,min(1,x2/image.width))
                    y1=max(0,min(1,y1/image.height));y2=max(0,min(1,y2/image.height))
                    if x2>x1 and y2>y1:
                        detections.append({'box':[x1,y1,x2-x1,y2-y1],'score':float(score)})
            return {'detections':sorted(detections,key=lambda d:d['score'],reverse=True)[:4],
                    'views':len(self.files()),'latencyMs':round((time.perf_counter()-started)*1000)}
        finally:self.lock.release()
