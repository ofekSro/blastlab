"""The model folder: where every file a run produces lands (OUT-1).

docs/model-folder-and-vtk-plan.md section 2 (owner decisions 8-12, 14,
2026-09-26). A run needs a runs folder and a model name before it
starts, and writes everything into `<runs_dir>\\<MODEL>\\`.

This module knows no GUI toolkit, no pyplot and no VTK. The name rule and
the folder check are pure; the GUIs and the CLI show the messages.
"""

import os

#: the longest model name accepted (plan sec. 2.1)
NAME_MAX = 100

#: characters Windows refuses in a file or folder name
FORBIDDEN_CHARS = '\\/:*?"<>|'

#: reserved device names: refused with or without an extension
#: ('con.txt' is the device CON too), in any letter case
RESERVED_NAMES = frozenset(
    ['CON', 'PRN', 'AUX', 'NUL']
    + [f'COM{i}' for i in range(1, 10)]
    + [f'LPT{i}' for i in range(1, 10)])


class ModelFolderError(Exception):
    """The model folder could not be prepared or written. The message
    carries the OS text, e.g. the file another program holds open."""


def validate_name(name):
    """None when `name` (trimmed) is a valid model folder name, else the
    reason it is not. Trimmed; non-empty; at most NAME_MAX characters; no
    `\\ / : * ? " < > |` and no control characters; no trailing dot or
    space; not a reserved device name (plan sec. 2.1)."""
    name = str(name or '').strip()
    if not name:
        return 'the name is empty'
    if len(name) > NAME_MAX:
        return (f'at most {NAME_MAX} characters (this one has '
                f'{len(name)})')
    bad = sorted({c for c in name if c in FORBIDDEN_CHARS})
    if bad:
        return ('a folder name cannot contain '
                + ' '.join(bad))
    if any(ord(c) < 32 for c in name):
        return 'a folder name cannot contain control characters'
    if name[-1] in '. ':
        return 'a folder name cannot end with a dot or a space'
    stem = name.split('.', 1)[0].rstrip(' ').upper()
    if stem in RESERVED_NAMES:
        return f'"{stem}" is a reserved Windows device name'
    return None


def _norm(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _desktop_roots():
    """The Desktop folders a runs folder must never be (CLAUDE.md 8.5):
    ~\\Desktop and the OneDrive-redirected ones."""
    roots = [os.path.join(os.path.expanduser('~'), 'Desktop')]
    for var in ('OneDrive', 'OneDriveCommercial', 'OneDriveConsumer'):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, 'Desktop'))
    return {_norm(r) for r in roots}


def check(runs_dir, model):
    """Everything wrong with (runs folder, model name), as messages that
    each name the box they are about. [] means a run may start."""
    errors = []
    runs_dir = str(runs_dir or '').strip()
    if not runs_dir:
        errors.append('Runs folder is empty')
    elif not os.path.isdir(runs_dir):
        errors.append(f'Runs folder does not exist: {runs_dir}')
    elif _norm(runs_dir) in _desktop_roots():
        # the Desktop holds the owner's thesis data; an overwrite there
        # deletes a folder of it (plan risk 1, CLAUDE.md 8.5)
        errors.append(f'Runs folder cannot be the Desktop itself: '
                      f'{runs_dir}')
    why = validate_name(model)
    if why:
        errors.append(f'Model name: {why}')
    return errors


def folder_for(runs_dir, model):
    """`<runs_dir>\\<model>` for a trimmed name. An existing folder whose
    name differs only in letter case IS this model on Windows, so its own
    spelling is returned."""
    name = str(model or '').strip()
    runs_dir = str(runs_dir or '').strip()
    try:
        entries = os.listdir(runs_dir)
    except OSError:
        entries = []
    for entry in entries:
        if entry.casefold() == name.casefold():
            return os.path.join(runs_dir, entry)
    return os.path.join(runs_dir, name)
