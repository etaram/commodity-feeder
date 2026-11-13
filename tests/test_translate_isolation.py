"""A crash in the Argos child process must not kill the merge (13 Nov: SIGFPE in Stanza stopped publication)."""
import leads.translate as t


def crash(lang, to, texts):
    import os
    os._exit(136)                          # what a floating point exception looks like to the parent


def echo(lang, to, texts):
    return [x.upper() for x in texts]


def test_child_crash_is_contained():
    t._BROKEN.clear()
    assert t._argos_isolated("xx", "en", ["a", "b"], timeout=60, fn=echo) == ["A", "B"]
    out = t._argos_isolated("es", "en", ["uno", "dos"], timeout=60, fn=crash)
    assert out == ["", ""] and ("es", "en") in t._BROKEN
    assert t._argos_isolated("es", "en", ["tres"], fn=echo) == [""]      # not retried in the same run
