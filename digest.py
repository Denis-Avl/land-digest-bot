import os, re, requests
from bs4 import BeautifulSoup
from datetime import datetime

# ================= НАСТРОЙКИ =================
CHANNELS = [
    ("land_jurist", "Про землю · Кузьменко"),
    ("zemlya_tvoi_kapital", "Земля — твой капитал"),
    ("OzhevaProZem", "ProЗемлю · Дзен Инвестиций"),
    ("kameneva_law", "Земельный юрист · Каменева"),
]

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("CHAT_ID", "").strip()

SEEN_FILE = "seen.txt"
POSTS_PER_CHANNEL = 3
# =============================================

def clean_text(text):
    """Убирает лишние пробелы и спецсимволы."""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_posts(channel):
    r = requests.get(f"https://t.me/s/{channel}", headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for block in soup.select("div.tgme_widget_message_bubble"):
        text_div = block.select_one("div.tgme_widget_message_text")
        time_a   = block.select_one("time")
        if text_div and time_a:
            full_text = clean_text(text_div.get_text(" ", strip=True))
            if not full_text:
                continue
            # Берём первые 250 символов как анонс
            snippet = full_text[:250]
            if len(full_text) > 250:
                snippet = snippet.rsplit(' ', 1)[0] + "…"
            dt = time_a.get("datetime", "")
            date_str = dt[:10] if dt else ""
            posts.append((dt, date_str, snippet))
    return posts[-POSTS_PER_CHANNEL:]

def extract_keywords(text):
    """Подсвечиваем важные земельные термины."""
    keywords = []
    lower = text.lower()
    terms = {
        "ври": "🏷", "категор": "🏷", "суд": "⚖️", "иск": "⚖️",
        "торг": "🔨", "банкрот": "🔨", "схем": "📐", "межев": "📐",
        "нспд": "📐", "арго": "📐", "кфх": "🌾", "сельхоз": "🌾",
        "ижс": "🏡", "промышлен": "🏭", "промзем": "🏭", "склад": "🏭",
        "аренд": "📋", "выкуп": "📋", "перераспределен": "🔀",
        "затоплен": "💧", "подтоплен": "💧", "крт": "🏗",
        "агротуризм": "🌿", "глэмпинг": "🌿", "кемпинг": "🌿",
    }
    for term, emoji in terms.items():
        if term in lower and emoji not in keywords:
            keywords.append(emoji)
    return " ".join(keywords[:3]) if keywords else "📌"

def main():
    print(f"🔑 BOT_TOKEN: {len(BOT_TOKEN)} символов, CHAT_ID: {len(CHAT_ID)} символов")

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN пустой!")
        return

    seen = set(open(SEEN_FILE).read().splitlines()) if os.path.exists(SEEN_FILE) else set()

    digest_parts = [f"🗞️ **Земельный дайджест** · {datetime.now():%d.%m.%Y}\n"]
    total_new = 0

    for channel, channel_name in CHANNELS:
        posts = get_posts(channel)
        new_posts = [(dt, date, txt) for dt, date, txt in posts if dt not in seen]
        if not new_posts:
            continue

        digest_parts.append(f"\n**📢 {channel_name}**")
        for dt, date, text in new_posts:
            tags = extract_keywords(text)
            digest_parts.append(f"\n{tags} _{date}_\n{text}")
            digest_parts.append(f"🔗 t.me/{channel}/{dt.split('/')[-1] if '/' in dt else ''}")
            seen.add(dt)
            total_new += 1

    if total_new == 0:
        print("Новых постов нет.")
        return

    digest_parts.append(f"\n\n📊 **Итого:** {total_new} новых постов из {len(CHANNELS)} каналов")
    digest_parts.append("\n💬 _Подробный разбор — в комментариях_")

    digest = "\n".join(digest_parts)

    # Telegram ограничивает сообщение 4096 символами
    if len(digest) > 4000:
        digest = digest[:4000] + "\n\n...(сокращено)"

    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID,
                            "text": digest,
                            "parse_mode": "Markdown"})

    if r.status_code == 200:
        with open(SEEN_FILE, "w") as f:
            f.write("\n".join(sorted(seen)))
        print(f"✅ Дайджест отправлен! {total_new} постов")
    else:
        print(f"❌ Ошибка Telegram: {r.status_code} {r.text[:300]}")

if __name__ == "__main__":
    main()
