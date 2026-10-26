from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch
import contextlib
import io

import monitor
from quarter_schedule import CheckTimingError, next_preparation_time, target_for_preparation, wait_until


def utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class QuarterScheduleTests(unittest.TestCase):
    def test_installer_aligns_to_minute_before_next_quarter(self):
        self.assertEqual(next_preparation_time(utc('2026-10-25T11:58:10')), utc('2026-10-25T11:59:00'))
        self.assertEqual(next_preparation_time(utc('2026-10-25T11:59:10')), utc('2026-10-25T12:14:00'))
        self.assertEqual(next_preparation_time(utc('2026-10-25T23:59:40')), utc('2026-10-26T00:14:00'))

    def test_preparation_targets_next_quarter_and_rejects_late_start(self):
        self.assertEqual(target_for_preparation(utc('2026-10-25T11:59:03')), utc('2026-10-25T12:00:00'))
        self.assertEqual(target_for_preparation(utc('2026-10-25T12:14:59')), utc('2026-10-25T12:15:00'))
        with self.assertRaises(CheckTimingError):
            target_for_preparation(utc('2026-10-25T12:00:03'))

    def test_gate_waits_and_does_not_send_late_requests(self):
        target = utc('2026-10-25T12:00:00')
        now = [target - timedelta(seconds=0.25)]
        def sleep(seconds):
            now[0] += timedelta(seconds=seconds)
        result = wait_until(target, clock=lambda: now[0], sleeper=sleep)
        self.assertEqual(result, target)
        with self.assertRaises(CheckTimingError):
            wait_until(target, clock=lambda: target + timedelta(seconds=2), sleeper=Mock())

    def test_check_is_submitted_only_after_timing_gate(self):
        target = utc('2026-10-25T12:00:00')
        events = []
        button = Mock()
        button.click.side_effect = lambda: events.append('submit')
        driver = Mock()
        driver.find_elements.return_value = []
        timing = {}
        with patch.object(monitor, 'prepare_check', return_value=(button, True)), \
             patch.object(monitor, 'wait_until', side_effect=lambda t: events.append('gate') or t), \
             patch.object(monitor, 'check_access'), \
             patch.object(monitor, 'read_availability', return_value=(False, monitor.BASE_URL)):
            monitor.check_appointments(driver, {}, Mock(), check_at=target, timing=timing)
        self.assertEqual(events, ['gate', 'submit'])
        self.assertEqual(timing['dispatch_lateness_ms'], 0)

    def test_late_preparation_never_submits(self):
        button = Mock()
        with patch.object(monitor, 'prepare_check', return_value=(button, True)), \
             patch.object(monitor, 'wait_until', side_effect=CheckTimingError('late')):
            with self.assertRaises(CheckTimingError):
                monitor.check_appointments(Mock(), {}, Mock(), check_at=utc('2026-10-25T12:00:00'))
        button.click.assert_not_called()

    def test_rejected_preparation_has_only_one_session_retry(self):
        driver = Mock()
        error = monitor.AccessBlockedError('Rejected', 'request_rejected', 'provincia')
        with patch.object(monitor, 'prepare_check', side_effect=error) as prepare, \
             patch.object(monitor, 'human_delay'), patch.dict(monitor.os.environ, {'ICP_BROWSER_PROFILE': '.local/profile'}):
            with self.assertRaises(monitor.AccessBlockedError):
                monitor.check_appointments(driver, {}, Mock())
        self.assertEqual(prepare.call_count, 2)
        driver.delete_all_cookies.assert_called_once()

    def test_rejection_with_thirty_seconds_left_does_not_retry_or_submit(self):
        now = utc('2026-10-26T00:59:30')
        target = utc('2026-10-26T01:00:00')
        error = monitor.AccessBlockedError('Rejected', 'request_rejected', 'trámite')
        driver, log = Mock(), Mock()
        with patch.object(monitor, 'prepare_check', side_effect=error) as prepare, \
             patch.object(monitor, 'datetime') as clock, patch.object(monitor, 'wait_until') as gate:
            clock.now.return_value = now
            with self.assertRaises(monitor.AccessBlockedError):
                monitor.check_appointments(driver, {}, log, check_at=target)
        self.assertEqual(prepare.call_count, 1)
        gate.assert_not_called()
        driver.delete_all_cookies.assert_not_called()
        self.assertIn('30.0s remain', log.call_args.args[0])

    def test_captcha_is_not_retried(self):
        error = monitor.AccessBlockedError('CAPTCHA', 'captcha', 'identificación')
        with patch.object(monitor, 'prepare_check', side_effect=error) as prepare:
            with self.assertRaises(monitor.AccessBlockedError):
                monitor.check_appointments(Mock(), {}, Mock())
        self.assertEqual(prepare.call_count, 1)

    def test_failed_check_is_not_reported_as_successful_process(self):
        profile = {'id': 'test', 'name': 'Alias'}
        for status, expected in (('blocked', 2), ('error', 2), ('missed', 2), ('unavailable', 0)):
            with self.subTest(status=status), patch.object(monitor, 'load_profiles', return_value=[profile]), \
                 patch.object(monitor, 'load_status', return_value={'profiles': {}}), \
                 patch.object(monitor, 'run_profile', return_value={'status': status}), \
                 patch.object(monitor, 'save_status'), patch.object(monitor, 'human_delay'), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(monitor.main(), expected)
