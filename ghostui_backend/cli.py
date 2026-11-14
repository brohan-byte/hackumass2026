"""Startup wiring. Run through the root app.py entry point."""
import argparse
import os
import secrets
from http.server import ThreadingHTTPServer
from .generation import load_environment
from .service import DeviceWorker
from .registry import adapter_names
from .server import handler_for

def main():
    parser = argparse.ArgumentParser(description='GhostUI interface generation app')
    parser.add_argument('address', nargs='?')
    parser.add_argument('--device', choices=adapter_names(), default='marshall', help='Registered device adapter')
    parser.add_argument('--simulate', action='store_true')
    parser.add_argument('--lan', action='store_true', help='Enable paired phone access on trusted Wi-Fi')
    parser.add_argument('--port', type=int, default=8780)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535: parser.error('Invalid port')
    load_environment()
    print('Gemini API key: ' + ('configured' if os.environ.get('GEMINI_API_KEY', '').strip() else 'not visible to this server; export it or use hackumass/.env'), flush=True)
    worker = DeviceWorker(args.address, args.simulate, args.device)
    try:
        if not args.simulate and not args.address: worker.discover()
        mobile_token = secrets.token_urlsafe(24) if args.lan else None
        server = ThreadingHTTPServer(('0.0.0.0' if args.lan else '127.0.0.1', args.port), handler_for(worker, args.port, mobile_token))
        if args.lan:
            import socket
            hostname = socket.gethostname().split('.')[0] + '.local'
            print(f'Phone server: http://{hostname}:{args.port}', flush=True)
            print(f'Phone pairing token: {mobile_token}', flush=True)
            print('Local demo uses HTTP: use trusted private Wi-Fi. Token changes on restart.', flush=True)
        print(f'GhostUI: http://127.0.0.1:{args.port}', flush=True)
        try: server.serve_forever()
        finally: server.server_close()
    except KeyboardInterrupt: pass
    finally: worker.close()
