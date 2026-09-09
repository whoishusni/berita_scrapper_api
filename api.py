import argparse
import os
from typing import Annotated, Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from scraper import SCRAPER_MAPPING, load_from_json, save_to_json, scrape_all

JSON_FILE_PATH = os.environ.get("NEWS_JSON_PATH", "news.json")

app = FastAPI(
    title="Indonesian Hot News API",
    description="API Publik untuk menyajikan berita hot/terkini dari Kompas, Detik, Kumparan, dan Narasi TV.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Aktifkan CORS untuk konsumsi publik dari web/frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def normalize_source(source: Optional[str]) -> Optional[str]:
    """Normalisasi nama sumber agar bersifat case-insensitive."""
    if source is None:
        return None
    value = source.strip().lower()
    return value or None


def get_valid_sources(source: Optional[str]) -> List[str]:
    """Validasi nama sumber dan kembalikan daftar sumber yang valid."""
    if source is None:
        return list(SCRAPER_MAPPING.keys())

    normalized = normalize_source(source)
    if normalized not in SCRAPER_MAPPING:
        raise HTTPException(
            status_code=400,
            detail=f"Sumber '{source}' tidak valid. Pilihan: {list(SCRAPER_MAPPING.keys())}",
        )
    return [normalized]


def filter_articles(
    articles: List[Dict[str, Any]],
    source: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Filter artikel berdasarkan sumber, kategori, pencarian, dan batas jumlah."""
    filtered = list(articles)

    if source:
        src_lower = normalize_source(source)
        filtered = [a for a in filtered if normalize_source(a.get("source")) == src_lower]

    if category:
        cat_lower = category.strip().lower()
        filtered = [a for a in filtered if cat_lower in (a.get("category") or "").lower()]

    if search:
        kw = search.strip().lower()
        filtered = [
            a for a in filtered
            if kw in (a.get("title") or "").lower() or kw in (a.get("category") or "").lower()
        ]

    if limit is not None:
        filtered = filtered[:limit]

    return filtered


def get_cached_news() -> Dict[str, Any]:
    """Ambil berita dari file JSON, auto-scrape jika file belum ada."""
    data = load_from_json(JSON_FILE_PATH)
    if not data or not data.get("data"):
        # Auto-scrape jika cache belum ada
        payload = scrape_all(limit_per_source=6)
        save_to_json(payload, JSON_FILE_PATH)
        return payload
    return data


@app.get("/", tags=["Info"])
def root() -> Dict[str, Any]:
    """Endpoint root: info API dan status."""
    cache = get_cached_news()
    return {
        "name": "Indonesian Hot News API",
        "version": "1.0.0",
        "description": "API Berita Hot & Terpopuler dari Kompas, Detik, Kumparan, dan Narasi TV",
        "documentation": "/docs",
        "status": "online",
        "last_updated": cache.get("updated_at"),
        "total_news_cached": cache.get("total_items", 0),
        "available_sources": list(SCRAPER_MAPPING.keys()),
        "endpoints": {
            "all_news": "/api/news",
            "by_source": "/api/news/{source}",
            "sources_summary": "/api/sources",
            "trigger_scrape": "/api/scrape (POST)",
        },
    }


@app.get("/api/sources", tags=["News"])
def list_sources() -> Dict[str, Any]:
    """Dapatkan daftar portal berita yang didukung beserta jumlah artikelnya."""
    cache = get_cached_news()
    summary = cache.get("summary", {})
    return {
        "status": "success",
        "updated_at": cache.get("updated_at"),
        "supported_sources": list(SCRAPER_MAPPING.keys()),
        "cached_summary": summary,
        "total_items": cache.get("total_items", 0),
    }


@app.get("/api/news", tags=["News"])
def get_all_news(
    source: Annotated[
        Optional[str],
        Query(description="Filter berdasarkan sumber berita (kompas, detik, kumparan, narasi)"),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(description="Cari kata kunci pada judul berita atau kategori"),
    ] = None,
    category: Annotated[
        Optional[str],
        Query(description="Filter berdasarkan kategori berita"),
    ] = None,
    limit: Annotated[
        Optional[int],
        Query(ge=1, le=200, description="Batas jumlah berita yang dikembalikan"),
    ] = None,
) -> Dict[str, Any]:
    """Mengambil daftar berita dengan berbagai filter (sumber, pencarian, kategori, limit)."""
    cache = get_cached_news()
    articles = filter_articles(cache.get("data", []), source=source, category=category, search=search, limit=limit)

    return {
        "status": "success",
        "updated_at": cache.get("updated_at"),
        "total_returned": len(articles),
        "total_cached": cache.get("total_items", 0),
        "data": articles,
    }


@app.get("/api/news/{source}", tags=["News"])
def get_news_by_source(
    source: str,
    limit: Annotated[
        Optional[int],
        Query(ge=1, le=100, description="Batas jumlah berita yang dikembalikan"),
    ] = None,
) -> Dict[str, Any]:
    """Mengambil berita khusus dari satu sumber tertentu (kompas, detik, kumparan, narasi)."""
    src_lower = normalize_source(source)
    if src_lower not in SCRAPER_MAPPING:
        raise HTTPException(
            status_code=404,
            detail=f"Sumber '{source}' tidak ditemukan. Pilihan: {list(SCRAPER_MAPPING.keys())}",
        )

    cache = get_cached_news()
    articles = filter_articles(cache.get("data", []), source=src_lower, limit=limit)

    return {
        "status": "success",
        "source": src_lower,
        "updated_at": cache.get("updated_at"),
        "total": len(articles),
        "data": articles,
    }


@app.post("/api/scrape", tags=["Scraper"])
def trigger_scrape(
    limit: Annotated[int, Query(ge=1, le=30, description="Jumlah berita per portal")] = 6,
    source: Annotated[
        Optional[str],
        Query(description="Portal spesifik yang ingin di-scrape ulang (default: semua)"),
    ] = None,
) -> Dict[str, Any]:
    """Memicu proses scraping ulang dan langsung perbarui file news.json."""
    sources = get_valid_sources(source)
    new_payload = scrape_all(limit_per_source=limit, sources=sources)
    save_to_json(new_payload, JSON_FILE_PATH)

    return {
        "status": "success",
        "message": f"Berhasil memperbarui data berita untuk sumber: {', '.join(sources)}",
        "summary": new_payload.get("summary"),
        "total_items": new_payload.get("total_items"),
        "updated_at": new_payload.get("updated_at"),
    }


def run() -> None:
    parser = argparse.ArgumentParser(description="Jalankan Server FastAPI Berita Hot")
    parser.add_argument("--host", default="0.0.0.0", help="Host IP (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port server (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code change")
    args = parser.parse_args()

    print(f"Memulai FastAPI Server di http://{args.host}:{args.port}")
    uvicorn.run("api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    run()
