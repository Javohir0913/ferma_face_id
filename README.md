# Ferma — Hikvision Face ID (Kirish/Chiqish) event qabul qiluvchi

2 ta Hikvision Face ID terminal (biri KIRISH, biri CHIQISH eshigida) HTTP
Listening orqali shu serverga event yuboradi (ism, vaqt, rasm) — server
Telegram guruhga xabar yuboradi va SQLite'ga yozadi.

Bu `bitrix24_and_sap/v3/hikvision` moduli bilan bir xil, amalda sinovdan
o'tgan mantiqqa asoslangan (JSON push parsing, spam-oldi debounce, serialNo
orqali dublikat himoyasi).

## O'rnatish

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env faylini to'ldiring: TG_TOKEN, TG_CHATS (kerak bo'lsa ALLOWED_IPS)
```

## Lokal ishga tushirish (test)

```bash
uvicorn main:app --host 0.0.0.0 --port 84 --reload
```

## Production (systemd + gunicorn)

Server: `10.166.113.21`, ichki port `84` (nginx `api.ravnaqfarm.uz`ni shu
portga yo'naltiradi — `bitrix24_and_sap` bilan bir xil serverda, faqat
boshqa port/domen).

`/etc/systemd/system/ferma.service`:

```ini
[Unit]
Description=Ferma - Hikvision Kirish/Chiqish FastAPI
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/path/to/ferma
Environment="PATH=/path/to/ferma/.venv/bin"
ExecStart=/path/to/ferma/.venv/bin/gunicorn main:app \
    --workers 2 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:84
Restart=always

[Install]
WantedBy=multi-user.target
```

`--bind 127.0.0.1:84` (0.0.0.0 emas) — port faqat shu serverning ichida
(nginx orqali) ochiq bo'lsin, tashqi dunyodan to'g'ridan-to'g'ri kirish
mumkin bo'lmasin.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ferma
```

## Nginx (`api.ravnaqfarm.uz` → 127.0.0.1:84)

**MUHIM:** `bitrix24_and_sap`dagi tajribaga ko'ra, bu serverda (10.166.113.21)
hozircha 443/HTTPS termination yo'q — faqat 80-port to'g'ridan-to'g'ri
ochiq. Shuning uchun kamerani ham **oddiy HTTP (port 80)** bilan sozlang —
eski Hikvision firmware'lar ko'pincha HTTPS bilan (SNI/sertifikat) muammo
qiladi.

```nginx
server {
    listen 80;
    server_name api.ravnaqfarm.uz;

    location / {
        proxy_pass http://127.0.0.1:84;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Bu blokni nginx'ning `sites-enabled`ga (yoki `bitrix-sap` uchun ishlatilgan
konfiguratsiya fayliga yangi `server {}` sifatida) qo'shing — `server_name`
farqi orqali nginx bitta 80-portda ikkala domenni (`api.uzkip.com` va
`api.ravnaqfarm.uz`) alohida backend'larga yo'naltiradi.

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## Kamera sozlamasi (har bir terminal uchun alohida)

Kamera admin panelida: **Configuration → Network → Advanced → HTTP Listening**

| Kamera | Domain | Port | Protocol | URL |
|---|---|---|---|---|
| Kirish terminali | `api.ravnaqfarm.uz` | 80 | HTTP | `/event/kirish` |
| Chiqish terminali | `api.ravnaqfarm.uz` | 80 | HTTP | `/event/chiqish` |

Ikkala kamerada ham bir xil domen, faqat **URL** farq qiladi — shu orqali
server qaysi eshikdan kelganini biladi.

## Ma'lumotlar bazasi

`data/app.db` (SQLite), `events` jadvali — `gate` ustuni ("kirish"/"chiqish")
orqali ajratiladi. Birinchi ishga tushirishda jadval avtomatik yaratiladi.

## Endpointlar

- `POST /event/kirish` — kirish kamerasi uchun
- `POST /event/chiqish` — chiqish kamerasi uchun
- `GET /health` — tekshiruv uchun (`{"status": "ok"}`)

`/docs`, `/redoc`, `/openapi.json` — xavfsizlik uchun o'chirilgan.
