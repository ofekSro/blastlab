"""The model folder (OUT-1): services/model_folder.py.

docs/model-folder-and-vtk-plan.md section 2; batch plan
docs/batches/2026-09-26-out-1-model-folder.md, Steps 1-4.

  A  the name rule, the folder check and `folder_for` (pure)

Everything runs in temp folders; the private settings file of
`char_common` keeps the real one untouched (CLAUDE.md 8.2).

Run:  cd blastlab/tests && python test_model_folder.py   (or under pytest)
"""
import os
import shutil
import sys
import tempfile

import char_common as cc

from blastlab.services import model_folder as mf            # noqa: E402


# ── A: the name rule, check, folder_for ──────────────────────────────────
def test_a_empty_and_whitespace():
    assert mf.validate_name('') == 'the name is empty'
    assert mf.validate_name(None) == 'the name is empty'
    assert mf.validate_name('   \t ') == 'the name is empty'


def test_a_forbidden_chars():
    for c in '\\/:*?"<>|':
        why = mf.validate_name(f'A{c}B')
        assert why and c in why, (c, why)
    assert 'control' in mf.validate_name('A\x01B')
    assert 'control' in mf.validate_name('A\tB')


def test_a_reserved_names():
    for name in ('CON', 'con', 'con.txt', 'Con.tar.gz', 'NUL', 'PRN',
                 'AUX', 'COM1', 'com9', 'LPT1', 'LPT9', 'lpt9.log'):
        why = mf.validate_name(name)
        assert why and 'reserved' in why, (name, why)
    # not device names: a longer stem, or COM0/LPT10
    for name in ('CONSOLE', 'COM0', 'LPT10', 'NULL', 'model.con'):
        assert mf.validate_name(name) is None, name


def test_a_trailing_dot_and_space():
    assert 'dot' in mf.validate_name('MODEL.')
    assert 'dot' in mf.validate_name('MODEL. ')     # trimmed, then a dot
    assert 'dot' in mf.validate_name('..')
    assert 'dot' in mf.validate_name('.')
    # a trailing space alone is trimmed away: the folder is 'MODEL'
    assert mf.validate_name('MODEL ') is None
    assert mf.validate_name(' MODEL') is None


def test_a_length():
    assert mf.validate_name('M' * 100) is None
    why = mf.validate_name('M' * 101)
    assert why and '100' in why and '101' in why, why
    # the limit applies after trimming
    assert mf.validate_name(' ' + 'M' * 100 + ' ') is None


def test_a_check_messages():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_a_')
    try:
        assert mf.check(tmp, 'MODEL') == []
        assert mf.check('', 'MODEL') == ['Runs folder is empty']
        assert mf.check('  ', 'MODEL') == ['Runs folder is empty']
        missing = os.path.join(tmp, 'nope')
        assert mf.check(missing, 'MODEL') == [
            f'Runs folder does not exist: {missing}']
        got = mf.check(tmp, 'A:B')
        assert len(got) == 1 and got[0].startswith('Model name: '), got
        # both boxes wrong: one message each, the folder first
        got = mf.check('', '')
        assert got == ['Runs folder is empty',
                       'Model name: the name is empty'], got
        desk = os.path.join(os.path.expanduser('~'), 'Desktop')
        if os.path.isdir(desk):
            got = mf.check(desk, 'MODEL')
            assert got and got[0].startswith(
                'Runs folder cannot be the Desktop'), got
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_folder_for_case_insensitive():
    tmp = tempfile.mkdtemp(prefix='blastlab_mf_a_')
    try:
        assert mf.folder_for(tmp, ' MODEL ') == os.path.join(tmp, 'MODEL')
        os.mkdir(os.path.join(tmp, 'MODEL'))
        # 'model' is the same folder on Windows: its own spelling comes back
        assert mf.folder_for(tmp, 'model') == os.path.join(tmp, 'MODEL')
        assert mf.folder_for(tmp, 'other') == os.path.join(tmp, 'other')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TESTS = [test_a_empty_and_whitespace, test_a_forbidden_chars,
         test_a_reserved_names, test_a_trailing_dot_and_space,
         test_a_length, test_a_check_messages,
         test_a_folder_for_case_insensitive]


if __name__ == '__main__':
    sys.exit(cc.run_main('MODEL FOLDER', TESTS))
