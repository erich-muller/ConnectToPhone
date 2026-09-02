"""
ConnectToPhone Desktop Package.
Auto-injects system site-packages so PyGObject / Libadwaita / PyCairo
are always discoverable inside virtual environments on Linux.
"""

import sys
import os
import glob

for site_pkg in glob.glob('/usr/lib*/python3*/site-packages'):
    if site_pkg not in sys.path:
        sys.path.append(site_pkg)

