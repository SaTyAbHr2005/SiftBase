"""Indexing progress: a live bar on a terminal, one line per 5% when the output goes to a log file."""
import sys
import time

WIDTH = 30


def no_progress(step: str, done: int, total: int) -> None:
    """The default for callers that show nothing, such as the API."""


def _clock(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {seconds:02d}s"


class ProgressBar:
    """Time left is for the current step only: it assumes the rest of the step runs at the speed so far."""

    def __init__(self, stream=None, clock=time.perf_counter):
        self._stream = stream or sys.stderr
        self._clock = clock
        self._live = self._stream.isatty()
        self._started = clock()
        self._step = None
        self._step_started = 0.0
        self._logged = -1

    def __call__(self, step: str, done: int, total: int) -> None:
        now = self._clock()
        if step != self._step:
            if self._live and self._step is not None:
                self._stream.write("\n")
            self._step, self._step_started, self._logged = step, now, -1
        share = min(done / total, 1.0) if total else 1.0
        percent = int(share * 100)
        if not self._live and percent // 5 == self._logged:
            return
        self._logged = percent // 5
        filled = int(share * WIDTH)
        spent = now - self._step_started
        left = _clock(spent / done * (total - done)) + " left" if 0 < done < total else ""
        line = (f"{step} [{'#' * filled}{'-' * (WIDTH - filled)}] {percent:3d}% {done:,}/{total:,}"
                f" | {_clock(now - self._started)} so far" + (f" | about {left}" if left else ""))
        self._stream.write(f"\r{line:<110}" if self._live else line + "\n")
        self._stream.flush()

    def finish(self) -> None:
        if self._live:
            self._stream.write("\n")
        self._stream.write(f"Indexing finished in {_clock(self._clock() - self._started)}\n")
        self._stream.flush()
