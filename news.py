import os
import re
import sys
import json
import time
from datetime import datetime, timezone
from urllib.parse import quote
import requests
import feedparser
from bs4 import BeautifulSoup
from google import genai

# 1. Load Gemini Secret Key
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

# 2. Configuration & Domain Settings
SITE_URL = "https://aabtak24.in"
SITE_NAME = "अबतक24.in (Aabtak24.in)"
RSS_URL = "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml"
SOURCE_NAME = "BBC News"
ARCHIVE_FILE = "articles_db.json"
NEWS_DIR = "news"

# 3. Navigation Categories & Aliases
CATEGORIES = [
    {"name": "देश-विदेश", "file": "desh-videsh.html", "aliases": ["देश-विदेश", "देश", "विदेश", "प्रमुख समाचार", "बड़ी खबर"]},
    {"name": "टेक्नोलॉजी", "file": "technology.html", "aliases": ["टेक्नोलॉजी", "विज्ञान", "AI"]},
    {"name": "अर्थव्यवस्था", "file": "economy.html", "aliases": ["अर्थव्यवस्था", "बिजनेस एवं ट्रेंड्स", "बिजनेस", "व्यापार"]},
    {"name": "राजनीति", "file": "politics.html", "aliases": ["राजनीति", "चुनाव"]},
    {"name": "मनोरंजन", "file": "entertainment.html", "aliases": ["मनोरंजन", "बॉलीवुड", "सिनेमा", "खेल"]},
]

# 4. Model Fallback List
MODELS_TO_TRY = [
    "gemma-4-31b-it",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemma-4-31b-it"
]

def clean_slug(slug_text):
    """Ensures the SEO slug only contains clean URL-safe characters."""
    slug = re.sub(r'[^a-zA-Z0-9\-]', '', slug_text.lower().replace(' ', '-'))
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug or f"news-{int(time.time())}"

def optimize_img_url(url, width=800):
    """
    Compresses & converts heavy external images into fast WebP via wsrv.nl CDN.
    Leaves local editor uploads (e.g., uploads/...) untouched.
    """
    if not url or "wsrv.nl" in url or not url.startswith("http"):
        return url
    return f"https://wsrv.nl/?url={quote(url, safe='')}&w={width}&output=webp&q=80"

def get_head_links(css_path="style.css", preload_img=None):
    """Common <head> tags: Non-blocking Google Fonts, optional LCP preload, and CSS."""
    preload_tag = f'    <link rel="preload" as="image" href="{preload_img}" fetchpriority="high">\n' if preload_img else ""
    return f"""    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 rx=%2216%22 fill=%22%23141210%22/><text x=%2250%%22 y=%2254%%22 dominant-baseline=%22central%22 text-anchor=%22middle%22 fill=%22%23FF4C00%22 font-family=%22sans-serif%22 font-weight=%22900%22 font-size=%2252%22>अ</text></svg>">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="preconnect" href="https://wsrv.nl" crossorigin>
{preload_tag}    <link rel="stylesheet" href="{css_path}">
    <link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Mukta:wght@700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap" onload="this.onload=null;this.rel='stylesheet'">
    <noscript><link href="https://fonts.googleapis.com/css2?family=Mukta:wght@700;800&family=Noto+Sans+Devanagari:wght@400;600;700&display=swap" rel="stylesheet"></noscript>"""    

def generate_with_fallback(prompt):
    for model_name in MODELS_TO_TRY:
        try:
            print(f"Attempting to write Hindi article using {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            print(f"✅ Success with {model_name}!")
            return json.loads(response.text)
        except Exception as e:
            print(f"⚠️ {model_name} busy ({e}). Switching to backup model...")
            time.sleep(2)
    raise RuntimeError("All models failed. Please try again later.")

def fetch_free_stock_image(query):
    """Fetches a royalty-free image URL & creator credit using Openverse."""
    try:
        url = "https://api.openverse.org/v1/images/"
        params = {"q": query, "page_size": 5, "aspect_ratio": "wide", "license_type": "commercial"}
        headers = {"User-Agent": "AutoHindiNewsBot/1.0"}
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            for img in res.json().get("results", []):
                img_url = img.get("url")
                creator = img.get("creator") or "Creative Commons"
                source = img.get("source") or "Openverse"
                if img_url and img_url.startswith("http"):
                    return img_url, f"फोटो साभार: {creator} / {source.capitalize()} (प्रतीकात्मक तस्वीर)"
    except Exception as e:
        print(f"Openverse stock fetch error: {e}")
    return None, None

def get_rss_image(entry):
    if "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0]["url"].replace("/240/", "/976/")
    if "media_content" in entry and len(entry.media_content) > 0:
        return entry.media_content[0]["url"]
    return None

def get_header_html(prefix="", active_file=""):
    """Generates the header with working links from both root ('') and /news/ ('../')."""
    home_cls = ' class="active"' if active_file == "index.html" else ""
    nav_links = f'<a href="{prefix}index.html"{home_cls}>मुख्य खबरें</a>\n'
    
    for cat in CATEGORIES:
        cls = ' class="active"' if active_file == cat["file"] else ""
        nav_links += f'            <a href="{prefix}{cat["file"]}"{cls}>{cat["name"]}</a>\n'
        
    about_cls = ' class="active"' if active_file == "about.html" else ""
    nav_links += f'            <a href="{prefix}about.html"{about_cls}>हमारे बारे में</a>'

    return f"""    <header>
        <a href="{prefix}index.html" class="logo">अब<span>तक24</span><span class="dot-in">.in</span></a>
        <nav class="nav-pills">
            {nav_links}
        </nav>
    </header>"""

def build_individual_article_page(art, today_str):
    """Creates a dedicated SEO-optimized HTML page for a single article inside /news/."""
    os.makedirs(NEWS_DIR, exist_ok=True)
    slug = art["slug"]
    canonical_url = f"{SITE_URL}/news/{slug}.html"
    
    # Normalize any old <h3> subheadings in existing articles to <h2> for sequential accessibility
    body_html = art["content_html"].replace("<h3>", "<h2>").replace("</h3>", "</h2>")
    plain_text = BeautifulSoup(body_html, "html.parser").get_text().strip()
    meta_desc = plain_text[:155].replace('"', "'") + "..."

    # Handle relative local image paths if uploaded via editor vs external URLs
    raw_img = art["image_url"]
    article_img_src = f"../{raw_img}" if not raw_img.startswith("http") else optimize_img_url(raw_img, width=900)
    og_img_url = f"{SITE_URL}/{raw_img}" if not raw_img.startswith("http") else raw_img

    schema_ld = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": art["title"],
        "image": [og_img_url],
        "datePublished": art.get("iso_date", datetime.now(timezone.utc).isoformat()),
        "dateModified": art.get("iso_date", datetime.now(timezone.utc).isoformat()),
        "author": [{
            "@type": "Organization",
            "name": "Aabtak24 News Desk",
            "url": SITE_URL
        }],
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": SITE_URL
        },
        "description": meta_desc,
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": canonical_url
        }
    }
    schema_json = json.dumps(schema_ld, ensure_ascii=False)

    article_html = f"""<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{art['title']} | अबतक24.in</title>
    <meta name="description" content="{meta_desc}">
    <link rel="canonical" href="{canonical_url}">
    
    <!-- OpenGraph / WhatsApp / Social Preview Tags -->
    <meta property="og:type" content="article">
    <meta property="og:title" content="{art['title']}">
    <meta property="og:description" content="{meta_desc}">
    <meta property="og:image" content="{og_img_url}">
    <meta property="og:url" content="{canonical_url}">
    <meta property="og:site_name" content="अबतक24.in">
    <meta name="twitter:card" content="summary_large_image">

    <!-- Google News JSON-LD Schema -->
    <script type="application/ld+json">{schema_json}</script>

{get_head_links(css_path="../style.css", preload_img=article_img_src)}
</head>
<body>
    <div class="top-bar">
        <span>📅 {today_str}</span>
        <span class="edition-tag">डिजिटल संस्करण • INDIA</span>
    </div>

{get_header_html(prefix="../")}

    <main class="container">
        <article class="article-box">
            <a href="../index.html" class="back-btn">← मुख्य पृष्ठ पर वापस जाएं</a>
            <div><span class="badge">{art.get('category', 'ताज़ा खबर')}</span></div>
            <h1 class="single-title">{art['title']}</h1>
            <div class="meta single-meta">प्रकाशित: {art['date']} <span class="meta-dot"></span> अबतक24 न्यूज़ डेस्क</div>
            <figure class="single-figure">
                <img src="{article_img_src}" alt="{art['title']}" width="800" height="450" fetchpriority="high" decoding="sync" />
                <figcaption class="image-credit">{art['image_courtesy']}</figcaption>
            </figure>
            <div class="article-content">
                {body_html}
            </div>
        </article>
    </main>
</body>
</html>"""

    filepath = os.path.join(NEWS_DIR, f"{slug}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(article_html)

def build_category_pages(articles, today_str):
    """Creates a dedicated HTML page for each category in the header."""
    for cat in CATEGORIES:
        cat_name = cat["name"]
        cat_file = cat["file"]
        aliases = cat["aliases"]
        
        filtered = [
            a for a in articles
            if a.get("category", "").strip() in aliases
            or any(alias in a.get("category", "") for alias in aliases)
        ]
        
        cards_html = ""
        if filtered:
            for idx, art in enumerate(filtered):
                art_link = f"news/{art['slug']}.html"
                card_img = optimize_img_url(art['image_url'], width=480)
                load_attr = 'fetchpriority="high"' if idx == 0 else 'loading="lazy"'
                cards_html += f"""
                <a href="{art_link}" class="archive-card">
                    <img src="{card_img}" alt="{art['title']}" width="400" height="200" {load_attr} decoding="async">
                    <div class="archive-card-body">
                        <span class="badge">{art.get('category', cat_name)}</span>
                        <h2 class="side-title">{art['title']}</h2>
                        <div class="meta">{art['date']}</div>
                    </div>
                </a>"""
        else:
            cards_html = f'<p style="color: var(--text-muted); font-size: 18px; padding: 20px 0;">अभी <strong>{cat_name}</strong> श्रेणी में कोई समाचार उपलब्ध नहीं है। अगली अपडेट में खबरें जोड़ी जाएंगी!</p>'

        page_html = f"""<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{cat_name} समाचार | अबतक24.in (Aabtak24.in)</title>
    <meta name="description" content="अबतक24.in पर पढ़ें {cat_name} से जुड़ी ताज़ा और प्रमुख हिंदी खबरें।">
    <link rel="canonical" href="{SITE_URL}/{cat_file}">
{get_head_links(css_path="style.css")}
</head>
<body>
    <div class="top-bar">
        <span>📅 {today_str}</span>
        <span class="edition-tag">डिजिटल संस्करण • INDIA</span>
    </div>

{get_header_html(prefix="", active_file=cat_file)}

    <main class="container">
        <div class="section-rule">
            <h1>{cat_name} / Category News</h1>
            <span>कुल {len(filtered)} समाचार</span>
        </div>
        <div class="archive-grid">{cards_html}</div>
    </main>
</body>
</html>"""

        with open(cat_file, "w", encoding="utf-8") as f:
            f.write(page_html)
    print("✅ Generated all category HTML pages!")

def build_static_pages(today_str):
    """Creates static pages like About Us (about.html) ONLY if they don't already exist."""
    if os.path.exists("about.html"):
        print("ℹ️ about.html already exists — skipping so custom edits are preserved!")
        return

    about_html = f"""<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>हमारे बारे में (About Us) | अबतक24.in</title>
    <meta name="description" content="अबतक24.in (Aabtak24.in) — भारत का आधुनिक डिजिटल हिंदी समाचार पोर्टल। जानें हमारे संपादकीय मानक और संपर्क सूत्र।">
    <link rel="canonical" href="{SITE_URL}/about.html">
{get_head_links(css_path="style.css")}
</head>
<body>
    <div class="top-bar">
        <span>📅 {today_str}</span>
        <span class="edition-tag">डिजिटल संस्करण • INDIA</span>
    </div>

{get_header_html(prefix="", active_file="about.html")}

    <main class="container">
        <article class="article-box">
            <a href="index.html" class="back-btn">← मुख्य पृष्ठ पर वापस जाएं</a>
            <div><span class="badge">हमारे बारे में / About Us</span></div>
            <h1 class="single-title">अबतक24.in (Aabtak24.in) — सटीक और निष्पक्ष डिजिटल हिंदी पत्रकारिता</h1>
            <div class="article-content">
                <p><strong>अबतक24.in (Aabtak24.in)</strong> भारत का एक आधुनिक डिजिटल हिंदी समाचार पोर्टल है। हमारा उद्देश्य देश-विदेश, टेक्नोलॉजी, अर्थव्यवस्था, राजनीति और मनोरंजन की प्रमुख खबरों को सरल, स्पष्ट और तथ्यपूर्ण हिंदी भाषा में पाठकों तक पहुँचाना है।</p>
                <h2>हमारा संपादकीय मानक (Editorial Policy)</h2>
                <p>हम विश्वसनीय राष्ट्रीय और अंतरराष्ट्रीय समाचार स्रोतों से तथ्यों का संकलन कर उन्हें पाठकों के लिए सहज और प्रवाहपूर्ण पत्रकारिता शैली में प्रस्तुत करते हैं तथा प्रत्येक रिपोर्ट के साथ उचित फोटो और स्रोत साभार (Attribution) प्रदान करते हैं।</p>
                <h2>संपर्क करें (Contact Us)</h2>
                <p>किसी भी सुझाव, प्रतिक्रिया या संपादकीय प्रश्न के लिए आप हमसे संपर्क कर सकते हैं:<br>
                <strong>वेबसाइट:</strong> <a href="{SITE_URL}" style="color: var(--accent); font-weight: 700;">aabtak24.in</a><br>
                <strong>ईमेल:</strong> contact@aabtak24.in</p>
            </div>
        </article>
    </main>
</body>
</html>"""

    with open("about.html", "w", encoding="utf-8") as f:
        f.write(about_html)
    print("✅ Generated about.html static page!")

def build_seo_files(articles):
    """Generates sitemap.xml and robots.txt for Google Search Console."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    urls_xml = f"""  <url>
    <loc>{SITE_URL}/</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>\n"""

    for cat in CATEGORIES:
        urls_xml += f"""  <url>
    <loc>{SITE_URL}/{cat['file']}</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>hourly</changefreq>
    <priority>0.9</priority>
  </url>\n"""

    urls_xml += f"""  <url>
    <loc>{SITE_URL}/about.html</loc>
    <lastmod>{now_iso}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>\n"""

    for art in articles:
        art_url = f"{SITE_URL}/news/{art['slug']}.html"
        art_iso = art.get("iso_date", now_iso)
        urls_xml += f"""  <url>
    <loc>{art_url}</loc>
    <lastmod>{art_iso}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>\n"""

    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls_xml}</urlset>"""

    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap_content)

    robots_content = f"""User-agent: *
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
"""
    with open("robots.txt", "w", encoding="utf-8") as f:
        f.write(robots_content)
    print("✅ Generated sitemap.xml and robots.txt for Google SEO!")

def build_website_html(articles):
    """Generates index.html, category pages, about page, and individual article pages."""
    today_str = datetime.now().strftime("%d %B %Y")
    if not articles:
        return

    # Delete any old HTML files in news/ that were removed from articles_db.json
    os.makedirs(NEWS_DIR, exist_ok=True)
    valid_files = {f"{art['slug']}.html" for art in articles}
    for fname in os.listdir(NEWS_DIR):
        if fname.endswith(".html") and fname not in valid_files:
            os.remove(os.path.join(NEWS_DIR, fname))

    for art in articles:
        build_individual_article_page(art, today_str)

    hero = articles[0]
    hero_link = f"news/{hero['slug']}.html"
    hero_img = optimize_img_url(hero['image_url'], width=800)

    side_html = ""
    for art in articles[1:5]:
        art_link = f"news/{art['slug']}.html"
        thumb_img = optimize_img_url(art['image_url'], width=300)
        side_html += f"""
        <a href="{art_link}" class="side-card">
            <img src="{thumb_img}" alt="{art['title']}" width="128" height="94" loading="lazy" decoding="async">
            <div>
                <span class="badge">{art.get('category', 'प्रमुख समाचार')}</span>
                <h2 class="side-title">{art['title']}</h2>
                <div class="meta">{art['date']}</div>
            </div>
        </a>"""

    more_html = ""
    if len(articles) > 5:
        cards = ""
        for art in articles[5:]:
            art_link = f"news/{art['slug']}.html"
            card_img = optimize_img_url(art['image_url'], width=480)
            cards += f"""
            <a href="{art_link}" class="archive-card">
                <img src="{card_img}" alt="{art['title']}" width="400" height="200" loading="lazy" decoding="async">
                <div class="archive-card-body">
                    <span class="badge">{art.get('category', 'समाचार')}</span>
                    <h2 class="side-title">{art['title']}</h2>
                    <div class="meta">{art['date']}</div>
                </div>
            </a>"""
        more_html = f"""
        <div class="section-rule">
            <h2>अन्य खबरें / More News</h2>
            <span>सभी समाचार</span>
        </div>
        <div class="archive-grid">{cards}</div>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>अबतक24.in (Aabtak24.in) | ताज़ा हिंदी समाचार और देश-दुनिया की खबरें</title>
    <meta name="description" content="अबतक24.in (Aabtak24.in) पर पढ़ें देश-विदेश, टेक्नोलॉजी, अर्थव्यवस्था, राजनीति और मनोरंजन की ताज़ा हिंदी खबरें।">
    <link rel="canonical" href="{SITE_URL}/">
    <meta property="og:type" content="website">
    <meta property="og:title" content="अबतक24.in | हिंदी न्यूज़ पोर्टल">
    <meta property="og:url" content="{SITE_URL}/">
{get_head_links(css_path="style.css", preload_img=hero_img)}
</head>
<body>
    <div class="top-bar">
        <span>📅 {today_str}</span>
        <span class="edition-tag">डिजिटल संस्करण • INDIA</span>
    </div>

{get_header_html(prefix="", active_file="index.html")}

    <main class="container">
        <div class="section-rule">
            <h2>प्रमुख सुर्खियां / Top Stories</h2>
            <span>ताज़ा अपडेट्स</span>
        </div>
        <div class="bento-grid">
            <a href="{hero_link}" class="hero-card">
                <div class="img-wrap"><img src="{hero_img}" alt="{hero['title']}" width="800" height="410" fetchpriority="high" loading="eager" decoding="sync"></div>
      
