"""Startup wiring. Run through the root app.py entry point."""
import argparse
import errno
import os
from pathlib import Path
import secrets
from http.server import ThreadingHTTPServer
from .generation import load_environment
from .devices import DeviceManager, ROOT
from .onboarding.documented import DocumentedOnboarding
from .registry import adapter_names
from .server import handler_for


def main():
    parser = argparse.ArgumentParser(description='GhostUI interface generation app')
    parser.add_argument('address', nargs='?')
    connection = parser.add_mutually_exclusive_group()
    connection.add_argument('--device', choices=adapter_names(), help='Add/select a known device connection')
    connection.add_argument('--onboard', metavar='ADDRESS', help='Generate a new HTTP adapter mapping from API documentation')
    parser.add_argument('--api-docs', metavar='HTTPS_URL', help='API documentation URL for --onboard')
    parser.add_argument('--simulate', action='store_true')
    parser.add_argument('--name', help='Friendly device name shown during object registration')
    parser.add_argument('--lan', action='store_true', help='Enable paired phone access on trusted Wi-Fi')
    parser.add_argument('--port', type=int, default=8780)
    parser.add_argument('--data-dir', type=Path, default=ROOT, help='Device registry, visual enrollment and layout storage')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535: parser.error('Invalid port')
    if args.onboard and (not args.api_docs or args.address or args.simulate):
        parser.error('--onboard requires --api-docs and cannot be combined with a positional address or --simulate')
    if args.api_docs and not args.onboard: parser.error('--api-docs requires --onboard ADDRESS')
    if args.name and not (args.device or args.address or args.simulate or args.onboard):
        parser.error('--name requires a device connection')
    load_environment()
    print('Gemini API key: ' + ('configured' if os.environ.get('GEMINI_API_KEY', '').strip() else 'not visible to this server; export it or use hackumass/.env'), flush=True)
    manager = DeviceManager(args.data_dir)
    server = None
    try:
        mobile_token = secrets.token_urlsafe(24) if args.lan else None
        # Reserve the port before generation or BLE connection. An old server
        # must not cause a paid generation followed by a failed startup.
        try:
            server = ThreadingHTTPServer(('0.0.0.0' if args.lan else '127.0.0.1', args.port),
                handler_for(None, args.port, mobile_token, manager=manager))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                parser.exit(1, f'Port {args.port} is already in use. Stop the previous GhostUI server with Ctrl-C or use --port.\n')
            raise
        if args.onboard:
            try:
                DocumentedOnboarding(manager, log=lambda message: print(message, flush=True)).run(
                    args.onboard, args.api_docs, args.name)
            except Exception as exc:
                parser.exit(1, f'Onboarding stopped: {exc}\nNo fallback adapter was selected. Existing device records were preserved.\n')
        else:
            try:
                if args.device or args.address or args.simulate:
                    manager.register(args.device or 'marshall', args.address, args.simulate, args.name)
                elif manager.last_selected:
                    manager.select(manager.last_selected)
            except Exception as exc:
                if args.device in ('sony', 'sony-playback'):
                    parser.exit(1, f'Sony connection stopped: {exc}\nNo new Sony device was registered.\n')
                print(f'Device unavailable: {exc}', flush=True)
        if manager.active:
            print(f'Selected: {manager.active.record["name"]}', flush=True)
        else:
            print('Ready for your phone. Tap Register object to find and set up a WLED light, then register its appearance.', flush=True)
        if args.lan:
            import socket
            hostname = socket.gethostname().split('.')[0] + '.local'
            print(f'Phone server: http://{hostname}:{args.port}', flush=True)
            print(f'Phone pairing token: {mobile_token}', flush=True)
            print('Local demo uses HTTP: use trusted private Wi-Fi. Token changes on restart.', flush=True)
        print(f'GhostUI: http://127.0.0.1:{args.port}', flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        manager.close()
