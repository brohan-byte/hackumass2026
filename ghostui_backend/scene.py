"""Camera-wide recognition of saved objects; no device connection or writes."""
from collections import defaultdict
import threading

from .recognition import RecognitionService, VisionBusy


def overlap(a, b):
    x, y, w, h = a
    xx, yy, ww, hh = b
    intersection = max(0, min(x+w, xx+ww)-max(x, xx)) * max(0, min(y+h, yy+hh)-max(y, yy))
    return intersection / max(1e-9, w*h+ww*hh-intersection)


def unambiguous_matches(detections):
    """Merge different views of one object; suppress uncertain physical identity."""
    groups = defaultdict(list)
    for detection in sorted(detections, key=lambda d: d['score'], reverse=True):
        same = groups[detection['deviceId']]
        if not any(overlap(detection['box'], old['box']) > 0.5 for old in same):
            same.append(detection)
    # Two distinct copies matching one enrollment cannot be resolved by appearance.
    candidates = [items[0] for items in groups.values() if len(items) == 1]
    return [item for item in candidates if not any(
        other['deviceId'] != item['deviceId'] and overlap(item['box'], other['box']) > 0.5
        for other in detections)]


class SceneRecognitionService(RecognitionService):
    def __init__(self, manager, model_path=None):
        super().__init__('scene', storage=manager.root / 'vision', model_path=model_path)
        self.manager = manager
        self.scene_lock = threading.Lock()
        self.entries = []
        self.signature = None

    def _refresh(self):
        with self.manager.lock:
            records = list(self.manager.records.values())
        entries = []
        for record in records:
            if record['simulated']:
                continue
            service = RecognitionService(record['enrollmentId'], storage=self.manager.root / 'vision')
            for path in service.files():
                if path.with_suffix('.jpg').is_file():
                    entries.append((path, record['id'], record['name']))
        signature = tuple((str(p), p.stat().st_mtime_ns, p.with_suffix('.jpg').stat().st_mtime_ns, id_, name)
                          for p, id_, name in entries)
        if signature != self.signature:
            self.prompted = False
            self.signature = signature
        self.entries = entries

    def files(self):
        return [entry[0] for entry in self.entries]

    def identity_for_class(self, index):
        _, id_, name = self.entries[index]
        return {'deviceId': id_, 'name': name}

    def status(self):
        with self.scene_lock:
            self._refresh()
            return {**super().status(), 'objects': len({entry[1] for entry in self.entries})}

    def detect(self, encoded):
        if not self.scene_lock.acquire(False):
            raise VisionBusy('Recognition is busy; retry shortly')
        try:
            self._refresh()
            result = super().detect(encoded)
            result['detections'] = unambiguous_matches(result['detections'])
            return result
        finally:
            self.scene_lock.release()
