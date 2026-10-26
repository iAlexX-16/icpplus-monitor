import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError

import monitor
from publish_dashboard import build_public_dashboard


class MonitorTests(unittest.TestCase):
    def test_explicit_chrome_and_driver_paths_are_used_together(self):
        with patch.dict(monitor.os.environ, {"CHROME_BINARY": "/opt/chrome", "CHROMEDRIVER_PATH": "/opt/chromedriver"}), \
             patch.object(monitor.webdriver, "Chrome") as create:
            monitor.build_driver()
        self.assertEqual(create.call_args.kwargs["options"].binary_location, "/opt/chrome")
        self.assertEqual(create.call_args.kwargs["service"].path, "/opt/chromedriver")

    def test_blocked_entry_does_not_report_no_slots(self):
        driver = Mock(title="403 Forbidden")
        driver.find_element.return_value.text = "Forbidden"
        driver.find_elements.return_value = []
        with patch.object(monitor, "human_delay"), patch.object(monitor, "ICP_NIE", ""):
            with self.assertRaises(monitor.AccessBlockedError):
                monitor.check_appointments(driver, {}, Mock())

    def test_unknown_flow_is_an_error_not_unavailable(self):
        driver = Mock(title="Cita previa", page_source="Identification required")
        driver.find_element.return_value.text = "Identification required"
        driver.find_elements.return_value = []
        profile = {"province": "Madrid", "procedure_name": "Huellas"}
        with patch.object(monitor, "wait_for", side_effect=monitor.TimeoutException()):
            with self.assertRaisesRegex(RuntimeError, "Availability could not be determined"):
                monitor.read_availability(driver, profile, Mock())

    def test_invalid_nie_stops_before_contacting_official_site(self):
        driver = Mock()
        with patch.object(monitor, "ICP_NIE", "X1234567A"):
            with self.assertRaises(monitor.ApplicantDetailsRequiredError):
                monitor.check_appointments(driver, {}, Mock())
        driver.get.assert_not_called()
        self.assertTrue(monitor.valid_nie("X1234567L"))
        self.assertFalse(monitor.valid_nie("invalid"))

    def test_network_firewall_is_reported_as_blocked(self):
        driver = Mock(title="Intrusion Prevention Violation")
        driver.find_element.return_value.text = "Your attempt is blocked by Intrusion Prevention."
        with self.assertRaises(monitor.AccessBlockedError):
            monitor.check_access(driver)

    def test_session_form_is_reloaded_once_and_access_is_checked(self):
        driver = Mock()
        driver.find_elements.return_value = [Mock()]
        with patch.object(monitor, 'human_delay'), patch.object(monitor, 'check_access') as access:
            monitor.refresh_initialized_form(driver, Mock(), 'provincia', 'selecting a procedure')
        driver.refresh.assert_called_once()
        access.assert_called_once_with(driver, 'provincia')

    def test_cookie_initialized_form_is_not_reloaded(self):
        driver = Mock()
        driver.find_elements.return_value = []
        with patch.object(monitor, 'human_delay') as delay:
            monitor.refresh_initialized_form(driver, Mock(), 'provincia', 'selecting a procedure')
        driver.refresh.assert_not_called()
        delay.assert_not_called()

    def test_procedure_session_is_initialized_before_its_selection(self):
        events = []
        driver = Mock()
        driver.find_elements.return_value = [Mock()]
        profile = {'province': 'Madrid', 'procedure_name': 'Huellas'}
        def log(message):
            if message.startswith('Selecting procedure'):
                events.append('select procedure')
        def refresh(driver, log, stage, description):
            events.append(stage)
        with patch.object(monitor, 'human_delay'), patch.object(monitor, 'check_access'), \
             patch.object(monitor, 'wait_and_click'), patch.object(monitor, 'Select'), \
             patch.object(monitor, 'wait_for'), patch.object(monitor, 'ICP_NIE', ''), \
             patch.object(monitor, 'refresh_initialized_form', side_effect=refresh):
            with self.assertRaises(monitor.ApplicantDetailsRequiredError):
                monitor.prepare_check(driver, profile, log)
        self.assertEqual(events, ['inicio', 'provincia', 'select procedure'])

    def test_rejection_support_id_is_extracted_without_page_contents(self):
        driver = Mock(title='Request Rejected')
        driver.find_element.return_value.text = ('The requested URL was rejected. '
            'Your support ID is: <14917498821336152833> PRIVATE_PAGE_CONTENT')
        with self.assertRaises(monitor.AccessBlockedError) as caught:
            monitor.check_access(driver, 'trámite')
        self.assertEqual(caught.exception.support_id, '14917498821336152833')
        self.assertNotIn('PRIVATE_PAGE_CONTENT', str(caught.exception))
        self.assertEqual(caught.exception.stage, 'trámite')

    def test_identity_configuration_disables_page_diagnostics(self):
        driver = Mock()
        with patch.object(monitor, "ICP_NIE", "PRIVATE_DOCUMENT"):
            monitor.save_debug_screenshot(driver, Mock())
        driver.save_screenshot.assert_not_called()

    def test_missing_identity_stops_before_submission(self):
        driver = Mock()
        driver.find_elements.return_value = [Mock()]
        profile = {"province": "Madrid", "procedure_name": "Huellas"}
        with patch.object(monitor, "human_delay"), patch.object(monitor, "check_access"), \
             patch.object(monitor, "wait_and_click") as click, patch.object(monitor, "Select"), \
             patch.object(monitor, "wait_for"), patch.object(monitor, "ICP_NIE", ""):
            with self.assertRaises(monitor.ApplicantDetailsRequiredError):
                monitor.check_appointments(driver, profile, Mock())
            self.assertNotIn("btnEnviar", [call.args[2] for call in click.call_args_list])

    def test_applicant_secrets_are_redacted_from_error_logs(self):
        profile = {"id": "test", "name": "Alias", "province": "Madrid", "procedure_name": "Huellas"}
        with patch.object(monitor, "ICP_NIE", "PRIVATE_DOCUMENT"), \
             patch.object(monitor, "ICP_NATIONALITY", "PRIVATE_NATION"), \
             patch.object(monitor, "build_driver", side_effect=RuntimeError("Failed: PRIVATE_DOCUMENT PRIVATE_NATION")), \
             contextlib.redirect_stdout(io.StringIO()):
            result = monitor.run_profile(profile)
        self.assertNotIn("PRIVATE_DOCUMENT", json.dumps(result))
        self.assertNotIn("PRIVATE_NATION", json.dumps(result))

    def test_telegram_failure_does_not_disclose_token(self):
        output = io.StringIO()
        with patch.object(monitor, "TELEGRAM_BOT_TOKEN", "SECRET_TOKEN"), \
             patch.object(monitor, "TELEGRAM_CHAT_ID", "123"), \
             patch.object(monitor, "urlopen", side_effect=URLError("SECRET_TOKEN")), \
             contextlib.redirect_stdout(output):
            self.assertFalse(monitor.send_telegram("test"))
        self.assertNotIn("SECRET_TOKEN", output.getvalue())

    def test_public_dashboard_omits_identity_logs_and_session_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "index.html").write_text("<html></html>")
            (root / "data/profiles.json").write_text(json.dumps([{
                "id": "private_id", "name": "Private Name", "province": "Madrid",
                "procedure_name": "Huellas", "selectors": {"sensitive": "value"}
            }]))
            (root / "data/status.json").write_text(json.dumps({"profiles": {
                "private_id": {"status": "blocked", "last_check": "2026-10-25",
                               "logs": ["PRIVATE_LOG"], "url": "https://example.org/?session=SECRET"}
            }}))
            build_public_dashboard(root, root / "public")
            result = "".join(path.read_text() for path in (root / "public/data").glob("*.json"))
            for private_value in ("private_id", "Private Name", "PRIVATE_LOG", "SECRET", "sensitive"):
                self.assertNotIn(private_value, result)
            self.assertIn("blocked", result)
            self.assertIn("Perfil 1", result)


if __name__ == "__main__":
    unittest.main()
