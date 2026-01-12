"""
Configuration file for plot_csv_data.py remote data fetching.

Specifies SSH servers and file paths for fetching bioreactor data.
"""

# Default configuration
DEFAULT_FILENAME = "bioreactor_data.csv"
DEFAULT_REMOTE_PATH = "/Documents/GitHub/gluon/src/bioreactor_data/"

# SSH Server Configuration
# Each server entry should have:
#   - host: SSH hostname (e.g., "bioreactor00")
#   - user: SSH username (e.g., "david")
#   - remote_path: Path on remote server (default: DEFAULT_REMOTE_PATH)
#   - filename: Filename on remote server (default: DEFAULT_FILENAME)
#   - label: Optional label for this server (used in plots, defaults to host)

SSH_SERVERS = [
    {
        'host': 'bioreactor00',
        'user': 'david',
        'remote_path': DEFAULT_REMOTE_PATH,
        'filename': DEFAULT_FILENAME,
        'label': 'bioreactor00',  # Optional: custom label for plots
    },
    {
        'host': 'bioreactor01',
        'user': 'david',
        'remote_path': DEFAULT_REMOTE_PATH,
        'filename': DEFAULT_FILENAME,
        'label': 'bioreactor01',  # Optional: custom label for plots
    },
]

# SSH Configuration
SSH_TIMEOUT = 10  # Timeout in seconds for SSH connections
SSH_KEY_PATH = None  # Path to SSH private key (None = use default ~/.ssh/id_rsa)

# Local cache directory for downloaded files
CACHE_DIR = "/tmp/plot_csv_cache"  # Directory to cache remote files locally
