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

BOT_TOKEN  = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID    = os.getenv("CHAT_ID", "").strip()
GEMINI_KEY = os.getenv("GEMINI_KEY", "").strip()

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]

SEEN_FILE = "seen.txt"
POSTS_PER_CHANNEL = 3
SUMMARY_ONLY = False  # True = только ИИ-выжимка; False = выжимка + подробный список
# =============================================

PROMPT = """Ты — помощник земельного специалиста. Ниже посты из земельных Telegram-каналов.
Сделай краткий дайджест на русском: 5–8 пунктов по сути, каждый пункт — 1–2 предложения.
Отдельно выдели всё, что касается ВРИ, категорий, зон, торгов, судов и рисков.
В конце добавь строку «💡 Полезно для практики:» с 1–2 выводами для земельного специалиста.
Живой стиль, без воды.

ПОСТЫ:
"""

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def get_posts(channel):
    r = requests.get(f"https://t.me/s/{channel}", headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for block in soup.select("div.tgme_widget_message_bubble"):
        text_div = block.select_one("div.tgme_widget_message_text")
        time_a   = block.select_one("time")
        link_a   = block.select_one("a.tgme_widget_message_date")
        if text_div and time_a:
            full = clean_text(text_div.get_text(" ", strip=True))
            if not full:
                continue
            snippet = full[:250]
            if len(full) > 250:
                snippet = snippet.rsplit(' ', 1)[0] + "…"
            dt = time_a.get("datetime", "")
            link = link_a.get("href", "") if link_a else ""
            posts.append((dt, dt[:10], snippet, full[:600], link))
    return posts[-POSTS_PER_CHANNEL:]

def ask_gemini(text):
    if not GEMINI_KEY:
        print("⚠️ GEMINI_KEY не задан — работаю без ИИ")
        return None
    for model in GEMINI_MODELS:
        try:
            r = requests.post(
                GEMINI_URL,
                headers={"Authorization": f"Bearer {GEMINI_KEY}"},
                json={"model": model, "temperature": 0.4,
                      "messages": [{"role": "user", "content": text}]},
                timeout=120)
            if r.status_code == 200:
                print(f"✅ Gemini сработал: {model}")
                return r.json()["choices"][0]["message"]["content"]
            print(f"⚠️ Gemini {model} → {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print("⚠️ Gemini error:", e)
    return None

def extract_keywords(text):
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
    return " ".join([e for t, e in terms.items() if t in lower][:3]) or "📌"

def send(text):
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    if r.status_code != 200:  # если Markdown сломался — шлём без форматирования
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": text})
    return r.status_code

def main():
    print(f"🔑 BOT_TOKEN={len(BOT_TOKEN)}, CHAT_ID={len(CHAT_ID)}, GEMINI_KEY={len(GEMINI_KEY)}")
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN пустой!")
        return

    seen = set(open(SEEN_FILE).read().splitlines()) if os.path.exists(SEEN_FILE) else set()
    new_items = []

    for channel, name in CHANNELS:
        for dt, date, snippet, full, link in get_posts(channel):
            if dt not in seen:
                new_items.append((channel, name, dt, date, snippet, full, link))
                seen.add(dt)

    if not new_items:
        print("Новых постов нет.")
        return

    # --- ИИ-выжимка ---
    summary = ask_gemini(PROMPT + "\n---\n".join(f"[{n}] {f}" for _, n, _, _, _, f, _ in new_items))

    sent_ok = False
    if summary:
        links = "\n".join(f"• {l}" for _, _, _, _, _, _, l in new_items if l)
        msg = (f"🗞️ Земельный дайджест · {datetime.now():%d.%m.%Y}\n\n"
               f"🤖 Коротко о главном:\n\n{summary}\n\n🔗 Источники:\n{links}")
        sent_ok = send(msg) == 200
        if sent_ok and SUMMARY_ONLY:
            print(f"✅ ИИ-дайджест отправлен! {len(new_items)} постов")
            open(SEEN_FILE, "w").write("\n".join(sorted(seen)))
            return

    # --- Подробный список (если нет ИИ или SUMMARY_ONLY=False) ---
    parts = [f"🗞️ Земельный дайджест · {datetime.now():%d.%m.%Y}\n"]
    for channel, name in CHANNELS:
        items = [i for i in new_items if i[0] == channel]
        if not items:
            continue
        parts.append(f"\n📢 {name}")
        for _, _, _, date, snippet, _, link in items:
            parts.append(f"\n{extract_keywords(snippet)} {date}\n{snippet}")
            if link:
                parts.append(link)
    parts.append(f"\n\n📊 Итого: {len(new_items)} новых постов")
    digest = "\n".join(parts)
    if len(digest) > 4000:
        digest = digest[:4000] + "\n\n...(сокращено)"

    if send(digest) == 200:
        open(SEEN_FILE, "w").write("\n".join(sorted(seen)))
        print(f"✅ Дайджест отправлен! {len(new_items)} постов")
    else:
        print("❌ Ошибка отправки в Telegram")

if __name__ == "__main__":
    main()
