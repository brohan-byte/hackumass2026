"""Stable GhostUI entry point: python app.py --lan."""
from ghostui_backend.cli import main
from ghostui_backend.service import DeviceWorker
from ghostui_backend.server import handler_for

if __name__ == '__main__':
    main()
