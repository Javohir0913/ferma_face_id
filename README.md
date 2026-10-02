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

## Docker + PostgreSQL (tavsiya etilgan)

Uchta konteyner: `db` (PostgreSQL 17), `app` (Face ID qabul qilish + web/Mini App, gunicorn 2 worker), `bot` (Telegram bot).
Hammasi `restart: unless-stopped` — server qayta yoqilsa o'zi ko'tariladi.

```bash
cp .env.example .env        # to'ldiring: TG_TOKEN, TG_CHATS, SESSION_SECRET, SUPERADMIN_TELEGRAM_ID, POSTGRES_PASSWORD ...
docker compose up -d --build
docker compose ps           # app — healthy bo'lishi kerak
docker compose logs -f app bot
```

Kod yangilash: `git pull && docker compose up -d --build`. Ma'lumotlar `pgdata` volume'da saqlanadi.

### Eski SQLite bazani ko'chirish

```bash
docker compose up -d db
python tools/sqlite_to_postgres.py app.db "postgresql+asyncpg://ferma:<parol>@127.0.0.1:5433/ferma"
docker compose up -d --build
```

Skript manbani faqat o'qiydi, maqsad bazada ma'lumot bo'lsa to'xtaydi, oxirida har jadval soni va
`events` nazorat summasini solishtiradi. Ko'chirishdan oldin eski serverdagi `ferma-bot` to'xtatilishi shart —
bitta bot tokenini ikki joyda ishlatib bo'lmaydi (Telegram 409 xato beradi) va hisobot ikki marta ketadi.

### Zaxira

`deploy/backup.sh` — `backups/ferma_*.dump` (30 kun saqlanadi). Cron: `30 2 * * * cd /opt/ferma && ./deploy/backup.sh >> backups/backup.log 2>&1`.

### Testlar PostgreSQL'da

```bash
docker compose exec db psql -U ferma -c "CREATE DATABASE ferma_test"
TEST_DATABASE_URL="postgresql+asyncpg://ferma:<parol>@127.0.0.1:5433/ferma_test" pytest -q
```

## Production (systemd + gunicorn, eski usul)

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

## Davomat (Mini App + Web + bot)

- Sahifa: `https://api.ravnaqfarm.uz/davomat/` (Telegram Mini App ham shu manzil).
- API: `/api/davomat/...` — har bir endpoint autentifikatsiyani tekshiradi.
- Bot: `ferma-bot.service` (`deploy/ferma-bot.service`) — `/start`, biriktirish so'rovlari,
  kunlik HTML hisobot (Sozlamalar → «Kunlik xulosa vaqti», default 08:00), istisno xabarlari.
- Xom `events` jadvaliga tegilmaydi; hisob har safar qayta hisoblanadi.

`.env` qo'shimcha kalitlari:

```
SESSION_SECRET=         # uzun tasodifiy qator (majburiy)
SUPERADMIN_TELEGRAM_ID= # yagona super admin
ADMIN_TELEGRAM_IDS=     # ixtiyoriy boshlang'ich adminlar
PUBLIC_BASE_URL=https://api.ravnaqfarm.uz
BOT_USERNAME=           # masalan ravnaqfarm_bot
COOKIE_SECURE=1
DEV_LOGIN=0             # serverda doim 0
```

Huquqlar: super admin (bitta, .env dan) admin beradi; admin barcha xodimlarning
keldi-ketdisini ko'radi va tuzatadi; qolganlar faqat o'zinikini ko'radi.

Testlar: `python -m pytest tests/`
