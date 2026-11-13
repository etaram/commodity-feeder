"""A crash or a hang in the Argos child process must not kill or block the merge (13 Nov: SIGFPE in Stanza stopped
publication; ChatGPT row 172: the time limit must bound the wait)."""
import time

import leads.translate as t


def crash(lang, to, texts):
    import os
    os._exit(136)                          # what a floating point exception looks like to the parent


def echo(lang, to, texts):
    return [x.upper() for x in texts]


def hang(lang, to, texts):
    time.sleep(30)
    return texts


def test_success_crash_and_no_retry():
    t._BROKEN.clear()
    assert t._argos_isolated("xx", "en", ["a", "b"], timeout=60, fn=echo) == ["A", "B"]
    assert t._argos_isolated("es", "en", ["uno", "dos"], timeout=20, fn=crash) == ["", ""] and ("es", "en") in t._BROKEN
    assert t._argos_isolated("es", "en", ["tres"], fn=echo) == [""]      # not retried in the same run


def test_timeout_is_bounded():
    t._BROKEN.clear()
    t0 = time.time()
    assert t._argos_isolated("uk", "en", ["x"], timeout=2, fn=hang) == [""]
    assert time.time() - t0 < 12 and ("uk", "en") in t._BROKEN
