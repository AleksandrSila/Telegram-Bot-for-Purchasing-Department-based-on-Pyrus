# debug_substring_search.py
import requests
from pyrus_api import PyrusAPI

p = PyrusAPI()

# 1) Забираем большой список задач формы без фильтра по полю
params = {
    "include_archived": "n",
    "item_count": 2000,
}
r = requests.get(
    f"{p.api_url}forms/{p.form_id}/register",
    headers=p.headers,
    params=params
)
r.raise_for_status()
tasks_raw = r.json().get("tasks", [])
print("Всего задач в реестре:", len(tasks_raw))

def build_short(t: dict):
    fields = {f["id"]: f for f in t.get("fields", [])}
    title = fields.get(49, {}).get("value", "")
    cnt = fields.get(22, {}).get("value", "")  # или 30, если нужно полное наименование
    return t["id"], title, cnt

# 2) Фильтр по подстроке "инструменты"
substr = "инструмент"
print(f'\nПоиск по подстроке: "{substr}"')
for t in tasks_raw:
    task_id, title, cnt = build_short(t)
    if cnt and substr.lower() in cnt.lower():
        print(f"ID={task_id} | {title} | {cnt}")

# 3) Фильтр по подстроке "все инструменты"
substr2 = "все инструменты"
print(f'\nПоиск по подстроке: "{substr2}"')
for t in tasks_raw:
    task_id, title, cnt = build_short(t)
    if cnt and substr2.lower() in cnt.lower():
        print(f"ID={task_id} | {title} | {cnt}")
