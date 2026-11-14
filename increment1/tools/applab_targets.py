"""Expose the App Lab board commands as PlatformIO custom targets.

PlatformIO shows every AddCustomTarget() under PROJECT TASKS > Custom in the
VS Code sidebar, which puts the App Lab actions one click away without leaving
the editor. The work itself is done by tools/applab.py.

Wired up from firmware/platformio.ini via extra_scripts; see
../README.md for the two lines to add.
"""

import os

Import("env")  # noqa: F821  - injected by PlatformIO

APPLAB = os.path.join(env.subst("$PROJECT_DIR"), "..", "increment1", "tools", "applab.py")  # noqa: F821

# (target name, menu title, description, applab.py arguments)
TARGETS = [
    ("board-resources", "Board: Resources", "CPU, RAM and disk on the board",      ["resources"]),
    ("apps-list",       "Apps: List",       "Apps installed on the board",         ["apps"]),
    ("models-list",     "Models: List",     "AI models, and which are installed",  ["models"]),
    ("bricks-list",     "Bricks: List",     "Bricks available on the board",       ["bricks"]),
    ("board-config",    "Board: Config",    "Where the board keeps apps and data", ["config"]),
]

for name, title, description, args in TARGETS:
    env.AddCustomTarget(  # noqa: F821
        name=name,
        dependencies=None,
        actions=['"$PYTHONEXE" "{}" {}'.format(APPLAB, " ".join(args))],
        title=title,
        description=description,
        always_build=True,
    )
