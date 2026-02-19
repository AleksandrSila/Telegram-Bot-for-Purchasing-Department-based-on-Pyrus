# config.py
import os
from dotenv import load_dotenv

load_dotenv()  # загружает .env из корня проекта

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

PYRUS_LOGIN = os.getenv("PYRUS_LOGIN")
PYRUS_SECURITY_KEY = os.getenv("PYRUS_SECURITY_KEY")

PYRUS_FORM_ID = int(os.getenv("PYRUS_FORM_ID", "1500167"))
PYRUS_FIELD_TITLE = int(os.getenv("PYRUS_FIELD_TITLE", "49"))
PYRUS_FIELD_COUNTERPARTY = int(os.getenv("PYRUS_FIELD_COUNTERPARTY", "22"))
PYRUS_FIELD_AMOUNT = int(os.getenv("PYRUS_FIELD_AMOUNT", "61"))
