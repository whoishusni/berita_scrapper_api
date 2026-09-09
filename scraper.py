import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from bs4 import BeautifulSoup

# Siapkan logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scraper")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


def fetch_response(url: str) -> requests.Response:
    """Ambil response HTTP dengan konfigurasi scraper yang konsisten."""
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=12)
    response.raise_for_status()
    return response


def append_article(
    items: List[Dict[str, Any]], article: Optional[Dict[str, Any]], limit: int
) -> bool:
    """Tambahkan artikel valid dan kembalikan apakah batas sudah tercapai."""
    if article:
        items.append(article)
    return len(items) >= limit


def clean_text(text: Optional[str]) -> Optional[str]:
    """Bersihkan spasi dan dekode entitas HTML."""
    if not text:
        return None
    return " ".join(unescape(text).strip().split())


def build_article(
    source: str,
    title: Optional[str],
    url: Optional[str],
    image_url: Optional[str],
    category: Optional[str],
    published_at: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Buat payload artikel standar dari semua sumber scraper."""
    if not title or not url:
        return None
    return {
        "source": source,
        "title": title,
        "url": url,
        "image": image_url,
        "category": category or "News",
        "published_at": published_at,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


def scrape_kompas(limit: int = 6) -> List[Dict[str, Any]]:
    """Scrape berita terpopuler dari Kompas.com."""
    url = "https://indeks.kompas.com/terpopuler"
    logger.info(f"Mengambil berita dari Kompas: {url}")
    items: List[Dict[str, Any]] = []

    try:
        response = fetch_response(url)
        soup = BeautifulSoup(response.text, "html.parser")

        article_nodes = soup.select(".articleItem")
        for node in article_nodes:
            link_tag = node.select_one("a.article-link") or node.select_one("a")
            if not link_tag:
                continue

            article_url = link_tag.get("href", "").strip()
            title_tag = node.select_one(".articleTitle") or node.select_one("h2") or node.select_one("h3")
            title = clean_text(title_tag.get_text()) if title_tag else None

            if not article_url or not title:
                continue

            # Gambar
            img_tag = node.select_one("img")
            img_url = None
            if img_tag:
                img_url = img_tag.get("src") or img_tag.get("data-src")

            # Kategori & Tanggal
            cat_tag = node.select_one(".articlePost-subtitle")
            category = clean_text(cat_tag.get_text()) if cat_tag else "News"

            date_tag = node.select_one(".articlePost-date")
            published_at = clean_text(date_tag.get_text()) if date_tag else None

            article = build_article("kompas", title, article_url, img_url, category, published_at)
            if append_article(items, article, limit):
                break

    except Exception as e:
        logger.error(f"Gagal scrape Kompas: {e}")

    logger.info(f"Kompas: Berhasil mendapatkan {len(items)} berita.")
    return items


def scrape_detik(limit: int = 6) -> List[Dict[str, Any]]:
    """Scrape berita paling populer dari Detik.com."""
    url = "https://www.detik.com/terpopuler"
    logger.info(f"Mengambil berita dari Detik: {url}")
    items: List[Dict[str, Any]] = []

    try:
        response = fetch_response(url)
        soup = BeautifulSoup(response.text, "html.parser")

        articles = soup.select("article.list-content__item")
        if not articles:
            articles = soup.select(".media__title")

        for art in articles:
            link_tag = art.select_one(".media__title a") or art.select_one("a.media__link") or art.select_one("a")
            if not link_tag:
                continue

            article_url = link_tag.get("href", "").strip()
            title = clean_text(link_tag.get_text())

            if not article_url or not title:
                continue

            # Gambar
            img_tag = art.select_one(".media__image img") or art.select_one("img")
            img_url = None
            if img_tag:
                img_url = img_tag.get("src") or img_tag.get("data-src")

            # Tanggal / Kanal
            date_tag = art.select_one(".media__date")
            published_at = None
            category = "Detik"
            if date_tag:
                span_date = date_tag.select_one("span")
                if span_date and span_date.get("title"):
                    published_at = span_date["title"].strip()
                else:
                    published_at = clean_text(date_tag.get_text())

                # Jika teks mengandung pipe '|' misalnya "detikNews | 3 jam yang lalu"
                full_text = clean_text(date_tag.get_text()) or ""
                if "|" in full_text:
                    parts = [p.strip() for p in full_text.split("|")]
                    category = parts[0]
                    if not published_at or published_at == full_text:
                        published_at = parts[1]

            article = build_article("detik", title, article_url, img_url, category, published_at)
            if append_article(items, article, limit):
                break

    except Exception as e:
        logger.error(f"Gagal scrape Detik: {e}")

    logger.info(f"Detik: Berhasil mendapatkan {len(items)} berita.")
    return items


def scrape_kumparan(limit: int = 6) -> List[Dict[str, Any]]:
    """Scrape cerita trending dari Kumparan.com menggunakan state awal."""
    url = "https://kumparan.com/trending"
    logger.info(f"Mengambil berita dari Kumparan: {url}")
    items: List[Dict[str, Any]] = []

    try:
        response = fetch_response(url)

        match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*</script>", response.text, re.DOTALL)
        if match:
            state_data = json.loads(match.group(1))
            for key, val in state_data.items():
                if key.startswith("Story:") and isinstance(val, dict) and val.get("title"):
                    title = clean_text(val.get("title"))
                    slug = val.get("slug")
                    if not title or not slug:
                        continue

                    article_url = f"https://kumparan.com/{slug}"
                    published_at = val.get("publishedAt") or val.get("createdAt")

                    # Ekstraksi gambar melalui referensi leadMedia
                    image_url = None
                    lead_media = val.get("leadMedia")
                    if isinstance(lead_media, list) and len(lead_media) > 0:
                        ref = lead_media[0].get("__ref")
                        if ref and ref in state_data and isinstance(state_data[ref], dict):
                            image_url = state_data[ref].get("externalURL")

                    # Kanal atau topik
                    category = "Trending"
                    channel_ref = val.get("channel", {}).get("__ref") if isinstance(val.get("channel"), dict) else None
                    if channel_ref and channel_ref in state_data:
                        category = state_data[channel_ref].get("name", "Trending")

                    article = build_article("kumparan", title, article_url, image_url, category, published_at)
                    if append_article(items, article, limit):
                        break

    except Exception as e:
        logger.error(f"Gagal scrape Kumparan: {e}")

    logger.info(f"Kumparan: Berhasil mendapatkan {len(items)} berita.")
    return items


def scrape_narasi(limit: int = 6) -> List[Dict[str, Any]]:
    """Scrape berita hot terbaru dari Narasi.tv."""
    url = f"https://gateway.narasi.tv/core/api/articles/navbar/news?sort=publishDate&dir=DESC&limit={limit}"
    logger.info(f"Mengambil berita dari Narasi TV: {url}")
    items: List[Dict[str, Any]] = []

    try:
        response = fetch_response(url)
        data = response.json()

        articles = data.get("data", [])
        for art in articles[:limit]:
            title = clean_text(art.get("title"))
            slug = art.get("slug")
            if not title or not slug:
                continue

            article_url = f"https://narasi.tv/read/{slug}"
            published_at = art.get("publishDate") or art.get("createdAt")

            # Thumbnail
            thumb = art.get("thumbnail") or {}
            image_url = (
                thumb.get("large")
                or thumb.get("medium")
                or thumb.get("small")
                or thumb.get("portrait")
            )

            # Kategori
            cat_obj = art.get("category")
            category = cat_obj.get("title", "News") if isinstance(cat_obj, dict) else "News"

            article = build_article("narasi", title, article_url, image_url, category, published_at)
            append_article(items, article, limit)

    except Exception as e:
        logger.error(f"Gagal scrape Narasi TV: {e}")

    logger.info(f"Narasi: Berhasil mendapatkan {len(items)} berita.")
    return items


SCRAPER_MAPPING = {
    "kompas": scrape_kompas,
    "detik": scrape_detik,
    "kumparan": scrape_kumparan,
    "narasi": scrape_narasi,
}


def scrape_all(limit_per_source: int = 6, sources: Optional[List[str]] = None) -> Dict[str, Any]:
    """Jalankan scraping untuk sumber yang diminta dan gabungkan ke dalam satu payload."""
    if not sources:
        sources = list(SCRAPER_MAPPING.keys())

    all_data: List[Dict[str, Any]] = []
    summary: Dict[str, int] = {}

    for src in sources:
        scraper_fn = SCRAPER_MAPPING.get(src.lower())
        if scraper_fn:
            results = scraper_fn(limit=limit_per_source)
            all_data.extend(results)
            summary[src] = len(results)
        else:
            logger.warning(f"Sumber berita '{src}' tidak dikenal. Tersedia: {list(SCRAPER_MAPPING.keys())}")

    payload = {
        "status": "success",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(all_data),
        "sources": sources,
        "summary": summary,
        "data": all_data,
    }
    return payload


def build_excel_filename() -> str:
    """Buat nama file Excel otomatis dengan format tgl_bulan_tahun_jam-menit.xlsx."""
    now = datetime.now()
    return f"{now.day:02d}_{now.month:02d}_{now.year}_{now.hour:02d}-{now.minute:02d}.xlsx"


def save_to_excel(payload: Dict[str, Any], file_path: Optional[str] = None) -> Path:
    """Simpan data artikel ke file Excel (.xlsx)."""
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("Paket 'openpyxl' belum terinstal. Jalankan: pip install openpyxl") from exc

    target = Path(file_path).resolve() if file_path else Path(build_excel_filename()).resolve()
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Berita"

    headers = ["source", "title", "url", "image", "category", "published_at", "scraped_at"]
    sheet.append(headers)

    for item in payload.get("data", []):
        sheet.append([item.get(header) for header in headers])

    workbook.save(target)
    logger.info(f"Data Excel tersimpan di: {target}")
    return target


def save_to_json(payload: Dict[str, Any], file_path: str = "news.json") -> Path:
    """Simpan data payload ke file JSON."""
    path = Path(file_path).resolve()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Data tersimpan rapi di: {path}")
    return path


def load_from_json(file_path: str = "news.json") -> Optional[Dict[str, Any]]:
    """Muat data payload dari file JSON."""
    path = Path(file_path).resolve()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Gagal membaca file JSON {path}: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI Scraper Berita Terkini/Hot (Kompas, Detik, Kumparan, Narasi TV)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  python scraper.py                      # Ambil 6 berita dari semua sumber
  python scraper.py --limit 10           # Ambil 10 berita dari setiap sumber
  python scraper.py --source detik       # Hanya ambil dari Detik
  python scraper.py -s kompas -s narasi  # Ambil dari Kompas dan Narasi
    python scraper.py --output berita.json # Simpan JSON dan Excel otomatis
    python scraper.py --excel-output berita.xlsx # Tentukan nama file Excel
        """,
    )

    parser.add_argument(
        "-s",
        "--source",
        action="append",
        choices=["all", "kompas", "detik", "kumparan", "narasi"],
        help="Sumber berita yang ingin di-scrape (dapat ditentukan lebih dari satu kali)",
    )
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=6,
        help="Batas jumlah berita per sumber (default: 6)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="news.json",
        help="Nama/path file output JSON (default: news.json)",
    )
    parser.add_argument(
        "--excel",
        action="store_true",
        help="Kompatibilitas lama; hasil scrape sekarang selalu disimpan ke Excel",
    )
    parser.add_argument(
        "--excel-output",
        type=str,
        default=None,
        help="Nama/path file Excel khusus. Default: otomatis dengan format tanggal-waktu.",
    )

    args = parser.parse_args()

    selected_sources = args.source
    if not selected_sources or "all" in selected_sources:
        selected_sources = list(SCRAPER_MAPPING.keys())
    else:
        selected_sources = list(dict.fromkeys(selected_sources))

    print("\n" + "=" * 60)
    print(" CLI NEWS SCRAPER (Kompas | Detik | Kumparan | Narasi)")
    print("=" * 60)
    print(f"Target sumber   : {', '.join(selected_sources)}")
    print(f"Batas per portal: {args.limit} berita")
    print(f"Target output   : {args.output}")
    print("-" * 60)

    payload = scrape_all(limit_per_source=args.limit, sources=selected_sources)
    saved_path = save_to_json(payload, args.output)

    excel_path = save_to_excel(payload, args.excel_output or build_excel_filename())

    print("\n" + "=" * 60)
    print(f"[OK] Scraping selesai! Total berita terkumpul: {payload['total_items']}")
    for src, count in payload["summary"].items():
        print(f"  * {src.upper():<10}: {count} berita")
    print(f"\nDisimpan di: {saved_path}")
    if excel_path:
        print(f"Disimpan di Excel: {excel_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
