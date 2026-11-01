import io

from kb.ingest.progress import ProgressBar


class _Terminal(io.StringIO):
    def isatty(self):
        return True


def _clock(times):
    values = iter(times)
    return lambda: next(values)


def test_terminal_bar_redraws_one_line_and_shows_time_left():
    out = _Terminal()
    bar = ProgressBar(out, _clock([0, 0, 60, 120]))
    bar("1/7 Reading pages", 0, 100)
    bar("1/7 Reading pages", 50, 100)
    bar("1/7 Reading pages", 100, 100)
    text = out.getvalue()
    assert text.count("\r") == 3 and "\n" not in text
    assert "50% 50/100" in text and "about 1m 00s left" in text and "100% 100/100" in text
    assert "left" not in text.rsplit("\r", 1)[1]


def test_log_file_gets_a_line_per_five_percent_not_per_update():
    out = io.StringIO()
    bar = ProgressBar(out, _clock(range(1002)))
    for done in range(1001):
        bar("1/7 Reading pages", done, 1000)
    lines = out.getvalue().splitlines()
    assert len(lines) == 21 and "\r" not in out.getvalue()


def test_a_new_step_starts_a_new_line_and_its_own_timer():
    out = _Terminal()
    bar = ProgressBar(out, _clock([0, 0, 100, 101]))
    bar("1/7 Reading pages", 1, 1)
    bar("6/7 Search vectors", 0, 10)
    bar("6/7 Search vectors", 1, 10)
    text = out.getvalue()
    assert "\n" in text and "about 0m 09s left" in text


def test_empty_step_counts_as_finished():
    out = io.StringIO()
    ProgressBar(out, _clock([0, 0]))("4/7 Document summaries", 0, 0)
    assert "100% 0/0" in out.getvalue()
