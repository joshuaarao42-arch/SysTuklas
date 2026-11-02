"""SysTuklas - Computer Performance Diagnostic and Monitoring System."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

if not os.path.isdir(os.path.join(HERE, "systuklas", "ui")):
    sys.exit(
        "SysTuklas is incomplete: the 'systuklas' folder was not found next to main.py.\n"
        f"Looked in: {HERE}\n"
        "Right-click the downloaded .zip, choose 'Extract All...', then run main.py from the extracted SysTuklas folder."
    )

from systuklas.ui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
