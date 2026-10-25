import json
import os
import unittest
from unittest.mock import patch

import monitor
from publish_local_status import public_status


class LocalMonitorTests(unittest.TestCase):
    def test_local_browser_is_visible_and_has_its_own_profile(self):
        with patch.dict(os.environ, {'ICP_HEADLESS': '0', 'ICP_BROWSER_PROFILE': '.local/test-profile'}), \
             patch.object(monitor.webdriver, 'Chrome') as create:
            monitor.build_driver()
        arguments = create.call_args.kwargs['options'].arguments
        self.assertFalse(any(argument.startswith('--headless') for argument in arguments))
        self.assertIn('--user-data-dir=' + os.path.abspath('.local/test-profile'), arguments)

    def test_publication_excludes_applicant_data_and_session_urls(self):
        status = {'last_run': '2026-10-25T01:50:14Z', 'profiles': {'madrid_huellas': {
            'status': 'unavailable', 'last_check': '2026-10-25T01:50:14Z',
            'name': 'PRIVATE_NAME', 'logs': ['PRIVATE_DOCUMENT'],
            'url': 'https://example.org/?session=SECRET',
        }}}
        result = json.dumps(public_status(status))
        for secret in ('PRIVATE_NAME', 'PRIVATE_DOCUMENT', 'SECRET'):
            self.assertNotIn(secret, result)
        self.assertIn('unavailable', result)


if __name__ == '__main__':
    unittest.main()
