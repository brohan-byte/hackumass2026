"""Serial device execution, validation and readback confirmation."""
from concurrent.futures import ThreadPoolExecutor
import time
from .registry import create_adapter
from .contracts import numeric_limits, validate_command

class DeviceWorker:
    def __init__(self, address=None, simulated=False, device='marshall', binding=None):
        self.integration_id = device
        self.pool = ThreadPoolExecutor(max_workers=1)
        try:
            self.adapter = self.pool.submit(create_adapter, device, address, simulated, binding).result()
            self.capabilities = self.adapter.capabilities
            self.limits = numeric_limits(self.capabilities)
            self.simulated = self.adapter.simulated
        except BaseException:
            self.pool.shutdown()
            raise

    def discover(self):
        self.pool.submit(self.adapter.discover).result()

    def request(self, change=None):
        if change is not None: validate_command(self.limits, change)
        def work():
            state = self.adapter.request(change)
            if change:
                field, expected = change
                deadline = time.monotonic() + 2.0
                while state.get(field) != expected and time.monotonic() < deadline:
                    time.sleep(0.1)
                    state = self.adapter.request()
                if state.get(field) != expected:
                    raise ValueError(f'{field}: requested {expected}, but device reports '
                                     f'{state.get(field)} after confirmation checks')
            return state
        return self.pool.submit(work).result()

    def close(self):
        try: self.pool.submit(self.adapter.close).result()
        finally: self.pool.shutdown()
