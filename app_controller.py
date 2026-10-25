"""Manual start/stop and quarter-hour scheduling, independent of the GUI."""

from datetime import datetime, timedelta, timezone

from quarter_schedule import next_preparation_time, target_for_preparation, CheckTimingError


def next_slot(now, after=None):
    try:
        target = target_for_preparation(now)
        prepare = now if (target - now).total_seconds() >= 45 else None
    except CheckTimingError:
        prepare = None
    if prepare is None:
        prepare = next_preparation_time(now)
        target = prepare + timedelta(seconds=60)
    while after is not None and target <= after:
        prepare = target + timedelta(minutes=14)
        target += timedelta(minutes=15)
    return prepare, target


class MonitorController:
    def __init__(self, launch, clock=None):
        self.launch = launch
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.running = False
        self.job = None
        self.prepare_at = self.target_at = self.last_started_target = None
        self.last_exit_code = None
        self.last_error = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.last_error = None
        self.prepare_at, self.target_at = next_slot(self.clock(), self.last_started_target)

    def tick(self):
        if not self.running:
            return
        now = self.clock()
        if self.job:
            result = self.job.poll()
            if result is None:
                return
            self.last_exit_code = result
            self.job.close()
            self.job = None
            self.prepare_at, self.target_at = next_slot(now, self.last_started_target)
        if now >= self.target_at:
            self.last_error = 'Se perdió el horario; se esperará al siguiente cuarto de hora.'
            self.prepare_at, self.target_at = next_slot(now, self.target_at)
        if now >= self.prepare_at:
            self.last_started_target = self.target_at
            try:
                self.job = self.launch()
            except Exception as error:
                self.last_error = 'No se pudo iniciar la consulta: ' + str(error)
                self.prepare_at, self.target_at = next_slot(now, self.last_started_target)

    def stop(self):
        self.running = False
        self.prepare_at = self.target_at = None
        if self.job:
            self.job.close()
            self.job = None
