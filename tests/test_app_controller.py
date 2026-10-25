from datetime import datetime, timedelta, timezone
import unittest

from app_controller import MonitorController, next_slot


def utc(hour, minute, second=0):
    return datetime(2026, 10, 25, hour, minute, second, tzinfo=timezone.utc)


class FakeJob:
    pid = 123
    result = None
    closed = False

    def poll(self):
        return self.result

    def close(self):
        self.closed = True


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = utc(12, 5)
        self.jobs = []
        def launch():
            job = FakeJob()
            self.jobs.append(job)
            return job
        self.controller = MonitorController(launch, clock=lambda: self.now)

    def test_opening_controller_does_not_start_monitoring(self):
        self.now = utc(12, 14)
        self.controller.tick()
        self.assertFalse(self.controller.running)
        self.assertEqual(self.jobs, [])

    def test_start_waits_for_preparation_and_stop_cancels_active_check(self):
        self.controller.start()
        self.controller.start()
        self.controller.tick()
        self.assertEqual(self.controller.target_at, utc(12, 15))
        self.assertEqual(self.jobs, [])
        self.now = utc(12, 14)
        self.controller.tick()
        self.assertEqual(len(self.jobs), 1)
        self.controller.stop()
        self.assertTrue(self.jobs[0].closed)
        self.assertIsNone(self.controller.job)
        self.now = utc(13, 14)
        self.controller.tick()
        self.assertEqual(len(self.jobs), 1)

    def test_finished_or_failed_check_does_not_repeat_the_same_slot(self):
        self.controller.start()
        self.now = utc(12, 14)
        self.controller.tick()
        self.jobs[0].result = 1
        self.now += timedelta(seconds=5)
        self.controller.tick()
        self.assertTrue(self.jobs[0].closed)
        self.assertEqual(self.controller.target_at, utc(12, 30))
        self.assertEqual(len(self.jobs), 1)

    def test_resume_after_missed_slot_never_starts_a_late_check(self):
        self.controller.start()
        self.now = utc(12, 15, 5)
        self.controller.tick()
        self.assertEqual(self.jobs, [])
        self.assertEqual(self.controller.target_at, utc(12, 30))

    def test_start_in_preparation_minute_requires_enough_time(self):
        self.assertEqual(next_slot(utc(12, 14, 5))[1], utc(12, 15))
        self.assertEqual(next_slot(utc(12, 14, 40))[1], utc(12, 30))
