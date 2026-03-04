import os
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import anthropic

# ─────────────────────────────────────────────
# EASY TO EDIT SETTINGS
# ─────────────────────────────────────────────

RECIPIENT_EMAIL = "Jonathan.antor242@gmail.com"

SCHEDULE_TIME = "08:00 UTC"  # For your reference — actual schedule is in the GitHub Actions YAML

STOCKS = [
    {"name": "DSV",              "ticker": "DSV.CO",     "search": "DSV logistics shipping"},
    {"name": "Maersk",           "ticker": "MAERSK-B.CO","search": "Maersk shipping container"},
    {"name": "DHL",              "ticker": "DHL.DE",     "search": "DHL Group logistics"},
    {"name": "Hapag-Lloyd",      "ticker": "HLAG.DE",    "search": "Hapag-Lloyd shipping"},
    {"name": "CMA CGM",          "ticker": None,         "search": "CMA CGM shipping container"},
    {"name": "COSCO Shipping",   "ticker": "1919.HK",    "search": "COSCO shipping China"},
    {"name": "Evergreen",        "ticker": "2603.TW",    "search": "Evergreen Marine shipping"},
]

# ─────────────────────────────────────────────
# LOAD SECRETS FROM .env FILE
# ─────────────────────────────────────────────

load_dotenv()

NEWSAPI_KEY       = os.getenv("NEWSAPI_KEY")
ALPHAVANTAGE_KEY  = os.getenv("ALPHAVANTAGE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GMAIL_USER        = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD= os.getenv("GMAIL_APP_PASSWORD")

# ─────────────────────────────────────────────
# FETCH NEWS FOR A STOCK
# ─────────────────────────────────────────────

def fetch_news(stock):
    """Fetch top news headlines for a stock using NewsAPI."""
    from_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": stock["search"],
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 5,
        "apiKey": NEWSAPI_KEY,
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        articles = data.get("articles", [])
        if not articles:
            return []
        headlines = []
        for a in articles:
            headlines.append({
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "source": a.get("source", {}).get("name", ""),
                "url": a.get("url", ""),
                "publishedAt": a.get("publishedAt", "")[:10],
            })
        return headlines
    except Exception as e:
        print(f"  ⚠ News fetch error for {stock['name']}: {e}")
        return []

# ─────────────────────────────────────────────
# FETCH STOCK PRICE FROM ALPHA VANTAGE
# ─────────────────────────────────────────────

def fetch_price(stock):
    """Fetch latest price and % change from Alpha Vantage."""
    if not stock["ticker"]:
        return None  # CMA CGM is private, no ticker

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": stock["ticker"],
        "apikey": ALPHAVANTAGE_KEY,
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        quote = data.get("Global Quote", {})
        if not quote or not quote.get("05. price"):
            return None
        return {
            "price": float(quote["05. price"]),
            "change_pct": float(quote["10. change percent"].replace("%", "")),
            "currency": "–",
        }
    except Exception as e:
        print(f"  ⚠ Price fetch error for {stock['name']}: {e}")
        return None

# ─────────────────────────────────────────────
# SUMMARISE WITH CLAUDE AI
# ─────────────────────────────────────────────

def summarise_with_ai(stock_name, headlines):
    """Use Claude to summarise the top headlines into bullet points."""
    if not headlines:
        return ["No recent news found for this stock."]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    headlines_text = "\n".join([
        f"- [{a['publishedAt']}] {a['title']} ({a['source']}): {a['description']}"
        for a in headlines
    ])

    prompt = f"""You are a financial analyst assistant. Below are recent news headlines about {stock_name}.

Summarise the key developments into exactly 3 concise bullet points.
Each bullet should be one sentence, focused on what matters most to an investor.
Be factual, neutral, and clear. Do not add any intro or conclusion text — just the 3 bullets.

Headlines:
{headlines_text}"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text.strip()
        bullets = [line.strip("•-– ").strip() for line in text.split("\n") if line.strip()]
        return bullets[:3]
    except Exception as e:
        print(f"  ⚠ AI summarise error for {stock_name}: {e}")
        return [h["title"] for h in headlines[:3]]

# ─────────────────────────────────────────────
# BUILD HTML EMAIL
# ─────────────────────────────────────────────

def build_email_html(results):
    """Format all stock summaries into a clean HTML email."""
    today = datetime.now().strftime("%A, %d %B %Y")

    stock_blocks = ""
    for r in results:
        price_html = ""
        if r["price"]:
            arrow = "▲" if r["price"]["change_pct"] >= 0 else "▼"
            color = "#2e7d32" if r["price"]["change_pct"] >= 0 else "#c62828"
            price_html = f"""
            <div style="margin-bottom:10px;">
                <span style="font-size:20px;font-weight:bold;color:#111;">{r['price']['price']:.2f}</span>
                <span style="font-size:14px;color:{color};margin-left:8px;">{arrow} {abs(r['price']['change_pct']):.2f}%</span>
            </div>"""
        else:
            price_html = '<p style="color:#888;font-size:13px;margin-bottom:10px;">Price data unavailable (private company or API limit)</p>'

        bullets_html = "".join([
            f'<li style="margin-bottom:6px;line-height:1.5;">{b}</li>'
            for b in r["bullets"]
        ])

        stock_blocks += f"""
        <div style="background:#ffffff;border:1px solid #e0e0e0;border-radius:8px;padding:20px;margin-bottom:16px;">
            <h2 style="margin:0 0 8px;font-size:18px;color:#0f1923;">{r['name']}
                {"" if not r["ticker"] else f'<span style="font-size:12px;color:#888;font-weight:normal;margin-left:8px;">{r["ticker"]}</span>'}
            </h2>
            {price_html}
            <ul style="margin:0;padding-left:18px;color:#333;font-size:14px;">
                {bullets_html}
            </ul>
        </div>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Georgia,serif;background:#f5f5f0;margin:0;padding:20px;">
        <div style="max-width:620px;margin:0 auto;">

            <div style="background:#0f1923;color:white;padding:24px;border-radius:8px 8px 0 0;border-bottom:3px solid #e8a800;">
                <h1 style="margin:0;font-size:22px;">📈 Morning Stock Digest</h1>
                <p style="margin:6px 0 0;color:#9ab;font-size:13px;">{today}</p>
            </div>

            <div style="background:#fffbea;padding:12px 20px;border:1px solid #f0d060;border-top:none;">
                <p style="margin:0;font-size:13px;color:#7a5800;">
                    AI-summarised news for your shipping & logistics portfolio.
                </p>
            </div>

            <div style="padding:16px 0;">
                {stock_blocks}
            </div>

            <div style="text-align:center;padding:16px;color:#aaa;font-size:11px;">
                Generated automatically · Not financial advice · Powered by NewsAPI, Alpha Vantage & Claude AI
            </div>
        </div>
    </body>
    </html>"""
    return html

# ─────────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────────

def send_email(html_body):
    """Send the digest email via Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 Morning Stock Digest — {datetime.now().strftime('%d %b %Y')}"
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())

# ─────────────────────────────────────────────
# MAIN — runs everything
# ─────────────────────────────────────────────

def main():
    print(f"\n📈 Stock Digest — {datetime.now().strftime('%d %B %Y %H:%M')}\n")

    results = []
    for stock in STOCKS:
        print(f"→ Processing {stock['name']}...")
        news    = fetch_news(stock)
        price   = fetch_price(stock)
        bullets = summarise_with_ai(stock["name"], news)
        results.append({
            "name":    stock["name"],
            "ticker":  stock["ticker"],
            "price":   price,
            "bullets": bullets,
        })
        print(f"  ✓ Done ({len(news)} articles found)")

    print("\n✉ Building and sending email...")
    html = build_email_html(results)
    send_email(html)
    print(f"✓ Email sent to {RECIPIENT_EMAIL}\n")

if __name__ == "__main__":
    main()