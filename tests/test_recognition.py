import base64
import io
import tempfile
import unittest
from unittest.mock import Mock,patch
from ghostui_backend.recognition import RecognitionService,VisionBusy
try:
    from PIL import Image
except ImportError:
    Image=None

@unittest.skipIf(Image is None,'Run with .venv-vision for enrollment tests')
class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=RecognitionService('speaker',storage=self.temp.name)
        buffer=io.BytesIO();Image.new('RGB',(640,480),'black').save(buffer,format='JPEG')
        self.image=base64.b64encode(buffer.getvalue()).decode()
    def test_enrollment_persistence_and_clear(self):
        self.assertEqual(self.service.enroll(self.image,[.2,.2,.5,.5])['views'],1)
        second=RecognitionService('speaker',storage=self.temp.name)
        self.assertEqual(second.status()['views'],1)
        self.assertEqual(second.clear()['views'],0)
    def test_device_isolation(self):
        self.service.enroll(self.image,[.2,.2,.5,.5])
        other=RecognitionService('other',storage=self.temp.name)
        self.assertEqual(other.status()['views'],0)
    def test_four_view_limit(self):
        for _ in range(4):self.service.enroll(self.image,[.2,.2,.5,.5])
        with self.assertRaises(ValueError):self.service.enroll(self.image,[.2,.2,.5,.5])
    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):self.service.enroll('not-base64',[0,0,1,1])
        for box in ([0,0,-1,1],[0,0,float('nan'),1],[.9,.9,.4,.4]):
            with self.assertRaises(ValueError):self.service.enroll(self.image,box)
    def test_reference_mosaic_preserves_each_view_embedding(self):
        self.service.enroll(self.image,[.1,.1,.5,.5]);self.service.enroll(self.image,[.2,.2,.4,.4])
        image,prompt=self.service.reference()
        self.assertEqual(image.size,(640,640));self.assertEqual(prompt['bboxes'].shape,(2,4))
        self.assertEqual(prompt['cls'].tolist(),[0,1])
        # Object boxes must occupy a useful fraction of each tile.
        widths=prompt['bboxes'][:,2]-prompt['bboxes'][:,0]
        self.assertTrue(all(widths>100))
    def test_busy_frames_drop(self):
        self.service.lock.acquire()
        try:
            with self.assertRaises(VisionBusy):self.service.detect(self.image)
        finally:self.service.lock.release()
    def test_model_missing_actionable(self):
        self.service.enroll(self.image,[.2,.2,.5,.5]);self.service.model_path=__import__('pathlib').Path(self.temp.name)/'absent.pt'
        with self.assertRaisesRegex(ValueError,'setup_vision'):self.service.detect(self.image)
