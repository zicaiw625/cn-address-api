# CN Address Standardization API

Parse messy Chinese shipping addresses into a clean, structured form suitable for logistics, customs, and downstream fraud / deliverability checks.

This service exposes a single `/parse` endpoint.

Input: one raw address string (can include recipient + phone).  
Output: structured fields like province / city / district, street+building, postal code, lat/lng, phone, recipient, normalized CN + naive EN representation, and a simple deliverability/confidence score.

## Features (MVP)
- Extract province / city / district from free-form Chinese address text.
- Extract phone number and potential recipient name.
- Extract postal code (6-digit).
- Return geocode centroid + postal code for known districts (demo data ships with a small subset).
- Generate:
  - `normalized_cn`: cleaned Chinese full address
  - `normalized_en`: naive pinyin/English-ish export string for customs forms
- Heuristic `deliverable` and `confidence` score so downstream systems can block obviously bad addresses.
- Single POST `/parse` endpoint (FastAPI).

This project is intentionally small and hackable: extend dictionaries and rules to cover all of mainland China, or adapt to your private warehouse routing rules.

---

## Quickstart

### 1. Environment
Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run dev server

```bash
uvicorn app.main:app --reload
```

Server will start on http://127.0.0.1:8000

### 3. Call the API

```bash
curl -X POST http://127.0.0.1:8000/parse   -H "Content-Type: application/json"   -d '{
    "raw_address": "浙江省杭州市滨江区长河街道江南大道1234号XX科技园5幢402室 张三 15900001234"
  }'
```

Example response:

```json
{
  "province": "浙江省",
  "city": "杭州市",
  "district": "滨江区",
  "street": "长河街道 江南大道1234号 XX科技园5幢402室",
  "postal_code": "310052",
  "lat": 30.1809,
  "lng": 120.2090,
  "recipient": "张三",
  "phone": "15900001234",
  "normalized_cn": "浙江省杭州市滨江区长河街道江南大道1234号XX科技园5幢402室",
  "normalized_en": "Room 402 , Building 5 , XX Keji Yuan , 1234 Jiangnan Dadao , Changhe Jiedao , Binjiang District , Hangzhou , Zhejiang 310052 China",
  "deliverable": true,
  "confidence": 0.93
}
```

### 4. Docker

```bash
docker build -t cn-address-api .
docker run -p 8000:8000 cn-address-api
```

---

## Project layout

```text
cn-address-api/
├─ README.md
├─ requirements.txt
├─ Dockerfile
├─ Makefile
├─ LICENSE
├─ app/
│  ├─ __init__.py
│  ├─ main.py                # FastAPI app + /parse route
│  ├─ models.py              # Pydantic request/response models
│  ├─ parser/
│  │   ├─ __init__.py
│  │   ├─ rules.py           # regex rules, helpers
│  │   ├─ division_loader.py # load cn divisions json
│  │   └─ address_parser.py  # core parse logic
│  └─ data/
│      └─ divisions_cn.json  # demo subset of province->city->district metadata
└─ tests/
   └─ test_parse.py
```

---

## Important notes

1. `app/data/divisions_cn.json` currently ships with **demo data for a few locations only** (e.g. 浙江省杭州市滨江区 / 上海市徐汇区).  
   You should extend this JSON using a full China administrative division dataset (省/市/区/街道, postal code, lat/lng).

2. `normalized_en` is a naive pinyin-ish transliteration using `pypinyin`. You can (and should) customize formatting rules for your customs / warehouse system.

3. `confidence` and `deliverable` are heuristics. In production, you'd likely add rules like "missing 门牌号 => deliverable=false".

4. No external paid data sources are bundled. You're responsible for ensuring your data source / usage complies with local law and carrier terms.

---

## Run tests

```bash
pytest -q
```

---

## Deployment sketch

For production you can bake this into a container image and run behind any reverse proxy / gateway. The provided Dockerfile runs Uvicorn directly.

Scale-out: put it behind nginx / load balancer, add rate limit and auth headers, then publish on RapidAPI as a paid tier.

---

## Roadmap ideas (build your paid tiers)

- Add fuzzy matching (typos in province / city / district) using Levenshtein distance or custom synonyms.
- Add a `risk_flag` field (e.g. high-return-rate districts or blacklisted pickup lockers).
- Add English export tuned for customs forms (省/市/区 in pinyin + country suffix).
- Add per-courier routing code tables for last-mile SLAs.
- Add batch `/bulk-parse` endpoint and async job polling for high volume users.

All of the above can become higher pricing tiers (Pro / Ultra / Mega) when you list this API on RapidAPI.

---

## License

MIT — see `LICENSE`.
