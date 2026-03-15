"""AV Cleaner GUI entrypoint.

Run: python app.py
"""

from utils.env_loader import env_file_load


env_file_load()

from ui.gui_app import main


if __name__ == "__main__":
    main()
