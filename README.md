# Seminar Registration & QR Check-In (prototype)

Barebones Flask + SQLite prototype. The HTML is deliberately unstyled so the UI team can replace it.

## Run

```bash
python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

| Page | What it does |
|---|---|
| `/` | Registration form |
| `/scanner` | Webcam QR scanner + manual / USB-scanner input |
| `/attendees` | Simple table of everyone and their check-in status |

## API

| Method | Endpoint | Body | Returns |
|---|---|---|---|
| POST | `/api/register` | `{full_name, email, organization, contact_number}` | `participant_id`, email status, `qr_url` (mock mode only) |
| POST | `/api/checkin` | `{participant_id}` | `status`: `success` / `already` / `invalid`, plus `message` |
| GET | `/api/participants` | – | JSON list of all participants |

## Email

By default `MOCK_EMAIL=True`: the email is printed to the console and the confirmation page shows the QR code directly.

To send real email through Gmail, create an App Password (Google Account → Security → 2-Step Verification → App passwords), then:

```bash
# macOS/Linux
export MOCK_EMAIL=False
export SMTP_USER=yourgroup@gmail.com
export SMTP_PASSWORD="your 16-char app password"
export EVENT_NAME="SIA Seminar 2026"
python app.py
```

```powershell
# Windows PowerShell
$env:MOCK_EMAIL="False"; $env:SMTP_USER="yourgroup@gmail.com"; $env:SMTP_PASSWORD="app password"
python app.py
```

Optional: `SMTP_HOST` (default smtp.gmail.com), `SMTP_PORT` (587), `SMTP_FROM`, `DB_PATH`, `PORT`.

If sending fails, the registration is still saved and the error message is shown on the confirmation page.

## Notes

- QR codes encode only the participant ID (e.g. `SEM-3F9A1C2B7D`) and are saved to `static/qrcodes/`.
- Browsers only allow the webcam on `localhost` or HTTPS. To scan with a phone on the same Wi-Fi, you'll need HTTPS (e.g. `ngrok http 5000`), or just use the manual box.
- One registration per email address (returns HTTP 409 on duplicates).
- Reset everything: delete `seminar.db` and the files in `static/qrcodes/`.
