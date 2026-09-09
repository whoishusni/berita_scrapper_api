# berita_scrapper_api (Scrapper dan API)

Aplikasi Python CLI untuk scraping berita hot / terpopuler dari 4 portal berita Indonesia:
- **Kompas.com** (`https://indeks.kompas.com/terpopuler`)
- **Detik.com** (`https://www.detik.com/terpopuler`)
- **Kumparan.com** (`https://kumparan.com/trending`)
- **Narasi.tv** (`https://gateway.narasi.tv/core/api/articles/navbar/news`)

Dilengkapi dengan server **FastAPI** untuk menyajikan data berita dari file JSON sebagai REST API publik


## 1. Instalasi Dependensi

Pastikan Python 3.10+ sudah terpasang, lalu jalankan:

```bash
pip install -r requirements.txt
```

---

## 2. Penggunaan CLI Scraper (`scraper.py`)

### A. Scrape 6 Berita dari Semua Portal (Default)
```bash
python scraper.py
```

### B. Mengatur Jumlah Berita per Portal
```bash
python scraper.py --limit 10
```

### C. Scrape Portal Tertentu Saja
```bash
python scraper.py --source detik
python scraper.py -s kompas -s narasi
```

### D. Mengubah Nama File Output
```bash
python scraper.py --output berita_hari_ini.json
```

Setiap proses scraping juga otomatis menyimpan hasil ke file Excel `.xlsx` dengan
nama berdasarkan tanggal dan waktu. Nama file Excel dapat ditentukan sendiri:

```bash
python scraper.py --excel-output berita_hari_ini.xlsx
```

---

## 3. Menjalankan Server FastAPI (`api.py`)

Jalankan server API menggunakan perintah berikut:

```bash
python api.py
```
atau menggunakan `uvicorn`:
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Server akan aktif di: **http://localhost:8000**  
Dokumentasi interaktif (Swagger UI): **http://localhost:8000/docs**

---

## 4. Daftar Endpoint API

| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Info API, metadata, status, dan ringkasan |
| `GET` | `/api/sources` | Daftar portal berita dan jumlah artikel ter-cache |
| `GET` | `/api/news` | Ambil semua berita (mendukung filter `source`, `category`, `search`, `limit`) |
| `GET` | `/api/news/{source}` | Ambil berita dari sumber tertentu (`kompas`, `detik`, `kumparan`, `narasi`) |
| `POST` | `/api/scrape` | Trigger scraping ulang on-demand langsung lewat request API |

### Contoh Pemanggilan Endpoint

- Mengambil semua berita Kompas:
  ```http
  GET http://localhost:8000/api/news/kompas
  ```
- Mengambil 5 berita Detik:
  ```http
  GET http://localhost:8000/api/news?source=detik&limit=5
  ```
- Mencari berita berdasarkan kata kunci:
  ```http
  GET http://localhost:8000/api/news?search=krakatau
  ```

