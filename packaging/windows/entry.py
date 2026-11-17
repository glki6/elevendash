"""Eleven Dashboard.exe: the packaged app for Windows (built by .github/workflows/release.yml with PyInstaller).

Opened with no arguments it starts the app (`elevendash app`); with arguments it is the elevendash command line, so
the shortcut it makes can pass --dir. It has no console window, so command-line output is not shown.
"""
import sys

from elevendash.cli import main

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or ['app']))
