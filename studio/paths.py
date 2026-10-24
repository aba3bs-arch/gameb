"""Rutas del estudio. Las credenciales no viven en la carpeta pública."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'web'
ASSET_DIR = ROOT / 'assets' / 'imported'
ASSET_DIR.mkdir(parents=True, exist_ok=True)
APPDATA = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'GAMEBStudio'
APPDATA.mkdir(parents=True, exist_ok=True)
CREDENTIALS_FILE = APPDATA / 'chatgpt_credentials.json'
HOST_FILE = APPDATA / 'host_id.txt'
