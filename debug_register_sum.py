# debug_register_sum.py
import requests
import config
from pyrus_api import PyrusAPI

p = PyrusAPI()

params = {
    f"fld{config.PYRUS_FIELD_COUNTERPARTY}": "всеинструменты",
    "include_archived": "n",
    "item_count": 200,
}
r = requests.get(
    f"{p.api_url}forms/{p.form_id}/register",
    headers=p.headers,
    params=params
)
r.raise_for_status()
data = r.json()

print("Всего задач:", len(data.get("tasks", [])))
for t in data.get("tasks", []):
    print("TASK ID:", t["id"])
    for f in t["fields"]:
        print(f"  id={f['id']} name={f['name']} type={f['type']} value={f.get('value')}")
    print("-" * 40)
