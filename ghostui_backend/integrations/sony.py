"""Sony XM5 adapter using the pinned libmdr protocol, not Mac output volume."""
import json
from pathlib import Path
import queue
import subprocess
import threading

from ..contracts import numeric_limits, validate_command

BRIDGE=Path(__file__).resolve().parents[2]/'data/sony-sdk/bin/ghostui-sony'


class SonyBridgeError(ValueError):
    pass


class SonyAdapter:
    simulated=False

    def __init__(self,address=None,simulated=False,*,bridge=BRIDGE):
        if simulated:raise SonyBridgeError('Sony simulation is not supported')
        if not Path(bridge).is_file():
            raise SonyBridgeError('Build the Sony bridge first: .venv-vision/bin/python tools/setup_sony.py')
        self.process=subprocess.Popen([str(bridge),'--serve']+([address] if address else []),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.lines=queue.Queue()
        def read():
            try:
                for line in self.process.stdout:self.lines.put(line)
            except (OSError,ValueError):
                pass
            finally:self.lines.put(None)
        threading.Thread(target=read,daemon=True).start()
        try:
            metadata=self._receive(timeout=40)
            self.address=metadata['address']
            self.model=metadata['model']
            self.firmware=metadata.get('firmware','')
            if self.model not in ('WH-1000XM5','WF-1000XM5'):
                raise SonyBridgeError('The Sony bridge did not identify an XM5')
            self.capabilities=metadata['capabilities']
            self.limits=numeric_limits(self.capabilities)
            if set(self.limits)!={'volume'}:
                raise SonyBridgeError('Unexpected Sony control capabilities')
        except BaseException:
            self.close();raise

    def _receive(self,timeout=20):
        try:line=self.lines.get(timeout=timeout)
        except queue.Empty:raise SonyBridgeError('Sony control connection timed out. Check Mac Bluetooth and close Sound Connect.') from None
        if line is None:raise SonyBridgeError('Sony bridge stopped; no command will be replayed automatically')
        try:result=json.loads(line)
        except (ValueError,TypeError):raise SonyBridgeError('Invalid response from Sony bridge') from None
        if not isinstance(result,dict):raise SonyBridgeError('Unexpected response from Sony bridge')
        if result.get('error'):raise SonyBridgeError(str(result['error']))
        return result

    def discover(self):
        pass  # The native bridge selects exactly one paired XM5 or requires its address.

    def request(self,change=None):
        if change is not None:
            validate_command(self.limits,change)
            command='volume '+str(change[1])
        else:command='state'
        try:
            self.process.stdin.write(command+'\n');self.process.stdin.flush()
        except (OSError,ValueError):raise SonyBridgeError('Sony bridge disconnected; reconnect before trying again') from None
        result=self._receive()
        state=result.get('state')
        if not isinstance(state,dict):raise SonyBridgeError('Missing Sony device readback')
        for key in self.limits:validate_command(self.limits,(key,state.get(key)))
        return state

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.write('quit\n');self.process.stdin.flush()
                self.process.wait(timeout=2)
            except (OSError,ValueError,subprocess.TimeoutExpired):
                self.process.terminate()
                try:self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        for pipe in (self.process.stdin,self.process.stdout):
            if pipe:pipe.close()
