import errno
import io
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import unittest
from unittest.mock import Mock, patch
from ghostui_backend.cli import main


class OnboardingCLITests(unittest.TestCase):
    def test_occupied_port_fails_before_generation_and_closes_manager(self):
        manager=Mock(root=Path('/private/tmp'))
        with patch('sys.argv',['app.py','--onboard','light.local','--api-docs','https://example.org/docs']), \
             patch('ghostui_backend.cli.load_environment'), \
             patch('ghostui_backend.cli.DeviceManager',return_value=manager), \
             patch('ghostui_backend.cli.ThreadingHTTPServer',side_effect=OSError(errno.EADDRINUSE,'Busy')), \
             patch('ghostui_backend.cli.DocumentedOnboarding') as onboarding, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as result: main()
        self.assertEqual(result.exception.code,1)
        self.assertIn('already in use',error.getvalue())
        onboarding.assert_not_called();manager.close.assert_called_once()

    def test_generation_failure_does_not_start_serving_existing_device(self):
        manager=Mock(root=Path('/private/tmp'));server=Mock()
        with patch('sys.argv',['app.py','--onboard','light.local','--api-docs','https://example.org/docs']), \
             patch('ghostui_backend.cli.load_environment'), \
             patch('ghostui_backend.cli.DeviceManager',return_value=manager), \
             patch('ghostui_backend.cli.ThreadingHTTPServer',return_value=server), \
             patch('ghostui_backend.cli.DocumentedOnboarding') as onboarding, \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as error:
            onboarding.return_value.run.side_effect=ValueError('API unsupported')
            with self.assertRaises(SystemExit) as result: main()
        self.assertEqual(result.exception.code,1)
        self.assertIn('No fallback adapter was selected',error.getvalue())
        manager.register.assert_not_called();manager.select.assert_not_called()
        server.serve_forever.assert_not_called();server.server_close.assert_called_once()
        manager.close.assert_called_once()
