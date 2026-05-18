"""
Hostile Benchmarks — Stress testing the scraper against malformed and dynamic content.

Targets:
  - Broken HTML (missing tags, malformed attributes)
  - Dynamic content (React-like hydration after delay)
  - Anti-bot signals (Cloudflare-like challenge pages)
  - Lazy loading (Simulated via scroll-triggered injection)
"""

import asyncio
import json
import logging
import threading
import time
from typing import List

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.models import FieldType, SchemaField
from app.scraper import scrape_url
from app.scrape_telemetry import get_scrape_telemetry
from app.config import settings

# Disable excessive logging during benchmarks
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("app.scraper").setLevel(logging.INFO)

app = FastAPI()

# ─── Hostile Endpoints ──────────────────────────────────────────────────

@app.get("/broken", response_class=HTMLResponse)
async def broken_html():
    return """
    <html><body>
    <div id="content">
        <h1 class='title'>Broken HTML Test (No closing tags or quotes)
        <div class='item'>
            <span class=name>Malformed Item 1
            <span class="price">$10.99
        </div>
        <div class='item'>
            <span class=name>Malformed Item 2
            <span class="price">$25.00
    </body>
    """

@app.get("/dynamic", response_class=HTMLResponse)
async def dynamic_html():
    return """
    <html><body>
    <div id="root">Loading records...</div>
    <script>
        setTimeout(() => {
            document.getElementById('root').innerHTML = `
                <div class="card"><span class="title">Dynamic Record A</span><span class="amt">$500</span></div>
                <div class="card"><span class="title">Dynamic Record B</span><span class="amt">$600</span></div>
                <div class="card"><span class="title">Dynamic Record C</span><span class="amt">$700</span></div>
            `;
        }, 2500);
    </script>
    </body></html>
    """

@app.get("/anti-bot", response_class=HTMLResponse)
async def anti_bot():
    return """
    <html><head><title>Just a moment...</title></head>
    <body>
    <h1>Checking your browser...</h1>
    <p>Please wait while we verify you are not a robot.</p>
    <div class="cf-browser-verification"></div>
    <script>
        // Fake challenge script
    </script>
    </body></html>
    """

@app.get("/lazy", response_class=HTMLResponse)
async def lazy_load():
    return """
    <html><body>
    <div id="list" style="height: 2000px;">
        <div class="item">Visible Item 1</div>
        <div class="item">Visible Item 2</div>
    </div>
    <script>
        window.addEventListener('scroll', () => {
            if (window.scrollY > 100) {
                const list = document.getElementById('list');
                if (!document.getElementById('lazy-1')) {
                    list.innerHTML += '<div id="lazy-1" class="item">Lazy Loaded Item 3</div>';
                    list.innerHTML += '<div class="item">Lazy Loaded Item 4</div>';
                }
            }
        });
    </script>
    </body></html>
    """

@app.get("/infinite", response_class=HTMLResponse)
async def infinite_scroll():
    return """
    <html><body style="min-height: 200vh;">
    <div id="content">
        <div class="item">Initial Item 1</div>
        <div class="item">Initial Item 2</div>
    </div>
    <script>
        let count = 2;
        window.addEventListener('scroll', () => {
            if (window.scrollY > 200) {
                const content = document.getElementById('content');
                if (count < 5) {
                    for(let i=0; i<3; i++) {
                        count++;
                        const div = document.createElement('div');
                        div.className = 'item';
                        div.textContent = 'Scrolled Item ' + count;
                        content.appendChild(div);
                    }
                }
            }
        });
    </script>
    </body></html>
    """

@app.get("/malformed", response_class=HTMLResponse)
async def malformed_dom():
    return """
    <html><body>
    <div class="container">
        <div class="item">
            <h2 class="title">Malformed Nesting 1
            <p class="desc">Description 1
        </div>
        <div class="item">
            <h2 class="title">Malformed Nesting 2
            <p class="desc">Description 2
            <div><span><span>Nested deep without closure
        </div>
    </body></html>
    """

# ─── Benchmark Runner ───────────────────────────────────────────────────

def start_server():
    uvicorn.run(app, host="127.0.0.1", port=8888, log_level="warning")

async def run_benchmarks():
    fields = [
        SchemaField(name="item_name", field_type=FieldType.STRING, required=True),
        SchemaField(name="price", field_type=FieldType.CURRENCY),
    ]
    
    base_url = "http://127.0.0.1:8888"
    tests = [
        ("Broken HTML", f"{base_url}/broken", 2),
        ("Dynamic Hydration", f"{base_url}/dynamic", 3),
        ("Anti-Bot Detection", f"{base_url}/anti-bot", 0),
        ("Lazy Loading", f"{base_url}/lazy", 4),
        ("Infinite Scroll", f"{base_url}/infinite", 5),
        ("Malformed DOM", f"{base_url}/malformed", 2),
    ]
    
    print("\n" + "="*60)
    print(" DATAFORGE SCRAPER HOSTILE BENCHMARKS")
    print("="*60 + "\n")
    
    telemetry = get_scrape_telemetry()
    
    for name, url, expected in tests:
        print(f"Testing: {name:20} ... ", end="", flush=True)
        start = time.time()
        
        try:
            results = await scrape_url(url, fields, min_record_score=0.2)
            elapsed = time.time() - start
            
            # Check telemetry for this URL
            recent = telemetry.get_recent(1)
            t_data = recent[0] if recent else {}
            
            status = "PASSED" if len(results) >= expected else "FAILED"
            if name == "Anti-Bot Detection" and t_data.get("anti_bot_score", 0) > 0.5:
                 status = "PASSED (Detected)"
            elif name == "Anti-Bot Detection" and len(results) == 0:
                 status = "PASSED (Blocked)"
            
            print(f"{status:15} | Records: {len(results):2} | Time: {elapsed:5.2f}s")
            
            if status.startswith("FAILED"):
                print(f"  -> Error/Telemetry: {t_data.get('error') or 'None'}")
                if results:
                    print(f"  -> Sample: {results[0]}")
                    
        except Exception as e:
            print(f"ERROR: {e}")

    print("\n" + "="*60)
    print(" BENCHMARKS COMPLETE")
    print("="*60 + "\n")

if __name__ == "__main__":
    # Allow rapid requests to local server
    settings.CRAWL_DEFAULT_DELAY_SECONDS = 0.0
    settings.CRAWL_PER_DOMAIN_CONCURRENCY = 10
    settings.PAGE_SETTLE_DELAY = 4.0
    
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    time.sleep(2) # Give server time to start
    
    asyncio.run(run_benchmarks())
