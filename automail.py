"""Point d'entrée de l'application de bureau (et de PyInstaller)."""

import multiprocessing
import sys

from desktop.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
