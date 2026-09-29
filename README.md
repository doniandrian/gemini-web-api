# Gemini WebAPI to OpenAI Bridge (Hermes / OpenAI-Compatible)

Proyek ini menjembatani sesi web **Google Gemini (khususnya akun langganan Gemini Pro / Advanced)** menjadi endpoint API lokal yang kompatibel dengan format OpenAI (`/v1/chat/completions` dan `/v1/models`).

---

## 1. Persiapan Dependensi

Virtual environment (`.venv`) dan semua dependensi sudah berhasil diinstall:
- `gemini_webapi` (v2.1+)
- `fastapi`
- `uvicorn`
- `python-dotenv`

Jika ingin mengaktifkan virtual environment di terminal:
```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 2. Cara Mengambil Cookie Gemini Pro

Library ini menggunakan cookie sesi dari akun Google Anda:

1. Buka browser (disarankan **Google Chrome** atau **Firefox**) dan login ke [gemini.google.com](https://gemini.google.com).
2. Pastikan Anda sudah memilih atau berada di akun yang memiliki langganan **Gemini Advanced / Pro**.
3. Tekan `F12` untuk membuka **Developer Tools**.
4. Buka tab **Application** (atau **Storage** di Firefox) -> pilih menu **Cookies** -> `https://gemini.google.com`.
5. Cari dan salin nilai dari dua cookie berikut:
   - `__Secure-1PSID`
   - `__Secure-1PSIDTS`
6. Buka file [`.env`](file:///C:/Users/LGSM036/Desktop/gemini%20web%20api/.env) dan tempel nilainya:

```env
GEMINI_SECURE_1PSID=paste_nilai___Secure-1PSID_disini
GEMINI_SECURE_1PSIDTS=paste_nilai___Secure-1PSIDTS_disini
DEFAULT_MODEL=gemini-pro
PORT=8000
HOST=127.0.0.1
```

> **Tips:** Jangan bagikan file `.env` atau nilai cookie ini ke orang lain karena merupakan sesi login akun Google Anda.

---

## 3. Menjalankan Server

Jalankan perintah berikut di folder proyek:

Menggunakan virtual environment `.venv`:
```powershell
.\.venv\Scripts\python.exe geminiwebapi.py
```
Atau langsung:
```powershell
python geminiwebapi.py
```

Server akan aktif di: `http://127.0.0.1:8000`

---

## 4. Konfigurasi di Hermes / OpenAI Client

Pada aplikasi klien Anda (seperti Hermes, SillyTavern, NextChat, Open WebUI):

- **OpenAI Base URL:** `http://127.0.0.1:8000/v1`
- **API Key:** `sk-dummy` (bebas diisi apa saja)
- **Model:** `gemini-pro` (atau model lain yang terdaftar di akun Anda)
