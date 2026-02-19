# pyrus_api.py
import logging
from dataclasses import dataclass
from typing import List, Optional

import requests
import re

import config

logger = logging.getLogger(__name__)


@dataclass
class PyrusTaskShort:
    id: int
    title: str
    counterpart: str
    amount: Optional[float]
    status_open: bool


class PyrusAPI:
    def __init__(self):
        self.login = config.PYRUS_LOGIN
        self.security_key = config.PYRUS_SECURITY_KEY
        self.form_id = config.PYRUS_FORM_ID

        self.access_token = None
        self.api_url = None
        self.files_url = None

        self._auth()

    def _auth(self):
        resp = requests.post(
            "https://accounts.pyrus.com/api/v4/auth",
            json={"login": self.login, "security_key": self.security_key},
            headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.api_url = data["api_url"]          # уже с /v4/
        self.files_url = data["files_url"]
        logger.info("Pyrus auth OK")

    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _ensure_auth(self):
        if not self.access_token:
            self._auth()

    def _normalize(self, s: str) -> str:
        """Нормализация строки для подстрочного поиска (убираем пробелы, точки, кавычки и т.п.)."""
        return re.sub(r"[^0-9a-zа-яё]", "", s.lower())

    def _build_task_short(self, t: dict) -> PyrusTaskShort:
        fields = {f["id"]: f for f in t.get("fields", [])}

        title = fields.get(config.PYRUS_FIELD_TITLE, {}).get("value", "")
        cnt = fields.get(config.PYRUS_FIELD_COUNTERPARTY, {}).get("value", "")

        amount = None
        amount_field = fields.get(config.PYRUS_FIELD_AMOUNT)
        if amount_field is not None:
            val = amount_field.get("value")
            if isinstance(val, dict):
                amount = val.get("amount")
            else:
                amount = val

        status_field = fields.get(35)  # Открыта / Завершена
        status_value = status_field.get("value") if status_field else None
        # Для надёжности учитываем несколько вариантов, при необходимости допишешь свои
        status_open = status_value in ("open", "opened", "Открыта")

        return PyrusTaskShort(
            id=t["id"],
            title=title,
            counterpart=cnt,
            amount=amount,
            status_open=status_open,
        )

    def _filter_open(self, tasks_raw: List[dict]) -> List[PyrusTaskShort]:
        result: List[PyrusTaskShort] = []
        for t in tasks_raw:
            short = self._build_task_short(t)
            if short.status_open:
                result.append(short)
        return result

    def get_task_brief(self, task_id: int) -> Optional[PyrusTaskShort]:
        self._ensure_auth()
        r = requests.get(f"{self.api_url}tasks/{task_id}", headers=self.headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        task = r.json()["task"]
        return self._build_task_short(task)

    def search_by_title(self, text: str) -> List[PyrusTaskShort]:
        """Поиск по названию сделки с подстрочным сопоставлением."""
        self._ensure_auth()
        params = {
            "include_archived": "n",
            "item_count": 2000,
        }
        r = requests.get(
            f"{self.api_url}forms/{self.form_id}/register",
            headers=self.headers,
            params=params,
        )
        r.raise_for_status()
        tasks_raw = r.json().get("tasks", [])

        needle = self._normalize(text)
        result: List[PyrusTaskShort] = []
        for t in tasks_raw:
            short = self._build_task_short(t)
            if not short.status_open:
                continue
            if not short.title:
                continue
            haystack = self._normalize(short.title)
            if needle in haystack:
                result.append(short)
        return result

    def search_by_counterparty(self, text: str) -> List[PyrusTaskShort]:
        """
        Поиск по контрагенту: берём весь реестр (до 2000 строк),
        сами фильтруем по подстроке с нормализацией.
        """
        self._ensure_auth()
        params = {
            "include_archived": "n",
            "item_count": 2000,
        }
        r = requests.get(
            f"{self.api_url}forms/{self.form_id}/register",
            headers=self.headers,
            params=params,
        )
        r.raise_for_status()
        tasks_raw = r.json().get("tasks", [])

        needle = self._normalize(text)
        result: List[PyrusTaskShort] = []
        for t in tasks_raw:
            short = self._build_task_short(t)
            if not short.status_open:
                continue
            if not short.counterpart:
                continue
            haystack = self._normalize(short.counterpart)
            if needle in haystack:
                result.append(short)
        return result

    def search_by_amount(self, amount: float, delta: float = 1.0) -> List[PyrusTaskShort]:
        """Поиск по сумме: через фильтр по money-полю (id из config.PYRUS_FIELD_AMOUNT)."""
        self._ensure_auth()
        low = amount - delta
        high = amount + delta
        params = {
            f"fld{config.PYRUS_FIELD_AMOUNT}": f"gt{low},lt{high}",
            "include_archived": "n",
        }
        r = requests.get(
            f"{self.api_url}forms/{self.form_id}/register",
            headers=self.headers,
            params=params,
        )
        r.raise_for_status()
        tasks_raw = r.json().get("tasks", [])
        return self._filter_open(tasks_raw)

    def upload_file(self, file_bytes: bytes, filename: str) -> str:
        self._ensure_auth()
        resp = requests.post(
            f"{self.api_url}files/upload",
            headers={"Authorization": f"Bearer {self.access_token}"},
            files={"file": (filename, file_bytes)},
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Uploaded file response: {data}")
        return data["guid"]  # guid обязателен

    def add_comment(self, task_id: int, text: str, file_guids=None):
        self._ensure_auth()
        payload = {"text": text}
        if file_guids:
            payload["attachments"] = [{"guid": g} for g in file_guids]

        resp = requests.post(
            f"{self.api_url}tasks/{task_id}/comments",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
