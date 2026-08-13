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

KOMMERSANT_URL = "https://www.kommersant.ru/realty"
KOMMERSANT_LIMIT = 5
K_KEYWORDS = ["земл", "участ", "кадастр", "ври", "категори", "аренд", "выкуп",
              "торг", "сельхоз", "ижс", "кфх", "склад", "пром", "застрой",
              "девелоп", "недвиж", "ипотек", "изъят", "межев", "дачн", "гектар",
              "жиль", "новострой", "квадратн", "строй", "коттедж", "апартамент"]

SEEN_FILE = "seen.txt"
POSTS_PER_CHANNEL = 5
FULL_POSTS_COUNT = 3
MAX_POST_CHARS = 1500
# =============================================

PROMPT = """Ты — помощник земельного специалиста. Ниже пронумерованные посты из земельных Telegram-каналов.

Сделай две вещи:

1. КРАТКАЯ ВЫЖИМКА (5–8 пунктов по сути, каждый 1–2 предложения).
   Отдельно выдели всё, что касается ВРИ, категорий, зон, торгов, судов и рисков.
   В конце добавь строку «💡 Полезно для практики:» с 1–2 выводами для земельного специалиста.

2. ТОП-ПОСТЫ: выбери {n} самых важных поста и напиши их номера в формате:
   TOP: 3, 7

ПОСТЫ:
"""

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def get_posts(channel, channel_name):
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
            posts.append({
                "channel": channel, "channel_name": channel_name,
                "dt": time_a.get("datetime", ""), "date": time_a.get("datetime", "")[:10],
                "full": full,
                "link": link_a.get("href", "") if link_a else "",
            })
    return posts[-POSTS_PER_CHANNEL:]

def get_kommersant():
    """Заголовки статей из рубрики «Недвижимость» Коммерсанта."""
    try:
        r = requests.get(KOMMERSANT_URL, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9"})
        if r.status_code != 200:
            print(f"⚠️ Коммерсантъ → {r.status_code}, пропускаю")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        items, used = [], set()
        for a in soup.select("a[href*='/doc/']"):
            title = clean_text(a.get_text(" ", strip=True))
            link = a["href"]
            link = link if link.startswith("http") else "https://www.kommersant.ru" + link
            if len(title) < 25 or link in used:
                continue
            if any(k in title.lower() for k in K_KEYWORDS):
                used.add(link)
                items.append({"link": link, "title": title})
            if len(items) >= KOMMERSANT_LIMIT:
                break
        print(f"📰 Коммерсантъ: найдено {len(items)} статей по теме")
        return items
    except Exception as e:
        print("⚠️ Коммерсантъ error:", e)
        return []

def ask_gemini(text):
    if not GEMINI_KEY:
        return None
    for model in GEMINI_MODELS:
        try:
            r = requests.post(
                GEMINI_URL,
                headers={"Authorization": f"Bearer {GEMINI_KEY}"},
                json={"model": model, "temperature": 0.3,
                      "messages": [{"role": "user", "content": text}]},
                timeout=120)
            if r.status_code == 200:
                print(f"✅ Gemini сработал: {model}")
                return r.json()["choices"][0]["message"]["content"]
            print(f"⚠️ Gemini {model} → {r.status_code}")
        except Exception as e:
            print("⚠️ Gemini error:", e)
    return None

def parse_top_numbers(ai_text, max_num):
    match = re.search(r'TOP:\s*([\d,\s]+)', ai_text, re.IGNORECASE)
    if not match:
        return []
    nums = []
    for part in match.group(1).split(','):
        try:
            n = int(part.strip())
            if 1 <= n <= max_num:
                nums.append(n)
        except ValueError:
            pass
    return nums[:FULL_POSTS_COUNT]

def send(text):
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    if r.status_code == 200:
        return 200
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      json={"chat_id": CHAT_ID, "text": text})
    return r.status_code

def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(' ', 1)[0] + "…"

def main():
    print(f"🔑 BOT_TOKEN={len(BOT_TOKEN)}, CHAT_ID={len(CHAT_ID)}, GEMINI_KEY={len(GEMINI_KEY)}")
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN пустой!")
        return

    seen = set(open(SEEN_FILE).read().splitlines()) if os.path.exists(SEEN_FILE) else set()

    new_items = []
    for channel, name in CHANNELS:
        for post in get_posts(channel, name):
            if post["dt"] not in seen:
                new_items.append(post)
                seen.add(post["dt"])

    k_items = [i for i in get_kommersant() if i["link"] not in seen]

    if not new_items and not k_items:
        print("Новых постов нет.")
        return

    # --- ИИ-выжимка по TG-каналам ---
    summary, top_posts = None, []
    if new_items:
        numbered = [f"[{i}] ({p['channel_name']}) {p['full'][:600]}" for i, p in enumerate(new_items, 1)]
        ai = ask_gemini(PROMPT.format(n=FULL_POSTS_COUNT) + "\n".join(numbered))
        if ai:
            summary = re.sub(r'\n*TOP:\s*[\d,\s]+', '', ai, flags=re.IGNORECASE).strip()
            top_nums = parse_top_numbers(ai, len(new_items))
            top_posts = [new_items[i-1] for i in top_nums]
    other_posts = [p for p in new_items if p not in top_posts]

    # --- Собираем дайджест ---
    parts = [f"🗞️ **Земельный дайджест** · {datetime.now():%d.%m.%Y}\n"]

    if summary:
        parts.append("🤖 **Коротко о главном:**\n" + summary)

    if top_posts:
        parts.append("\n━━━ 📌 **Главные посты дня** ━━━")
        for p in top_posts:
            parts.append(f"\n*📢 {p['channel_name']} · {p['date']}*\n{truncate(p['full'], MAX_POST_CHARS)}")
            if p["link"]:
                parts.append(f"🔗 {p['link']}")

    if other_posts:
        parts.append("\n📚 **Также в лентах:**")
        for p in other_posts:
            if p["link"]:
                parts.append(f"• {p['link']}")

    if k_items:
        parts.append("\n━━━ 📰 **Коммерсантъ · Недвижимость** ━━━")
        for i in k_items:
            parts.append(f"\n• {i['title']}\n🔗 {i['link']}")

    parts.append(f"\n📊 TG-постов: {len(new_items)} · Статей Ъ: {len(k_items)}")

    digest = "\n".join(parts)
    if len(digest) > 4000:
        digest = digest[:4000] + "\n\n...(сокращено)"

    if send(digest) == 200:
        for i in k_items:
            seen.add(i["link"])
        open(SEEN_FILE, "w").write("\n".join(sorted(seen)))
        print(f"✅ Дайджест отправлен! TG: {len(new_items)}, Ъ: {len(k_items)}")
    else:
        print("❌ Ошибка отправки в Telegram")

if __name__ == "__main__":
    main()
