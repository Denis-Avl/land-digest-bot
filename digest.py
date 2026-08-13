import os, requests
from bs4 import BeautifulSoup
from datetime import datetime

# ================= НАСТРОЙКИ =================
CHANNELS = [
    "land_jurist",
    "zemlya_tvoi_kapital",
    "OzhevaProZem",
    "kameneva_law"
]

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
AI_KEY = os.getenv("AI_KEY")

AI_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "meta-llama/llama-3.1-8b-instruct:free"  # Бесплатная модель

SEEN_FILE = "seen.txt"
# =============================================

PROMPT = """Ты — помощник земельного специалиста. Из постов ниже сделай краткий
дайджест на русском: 5–8 пунктов по сути, отдельно выдели всё, что касается
ВРИ, категорий, зон, торгов, судов и рисков. Живой стиль, без воды.

ПОСТЫ:
"""

def get_posts(channel):
    r = requests.get(f"https://t.me/s/{channel}", headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for block in soup.select("div.tgme_widget_message_bubble"):
        text_div = block.select_one("div.tgme_widget_message_text")
        time_a = block.select_one("time")
        if text_div and time_a:
            posts.append((time_a.get("datetime"), text_div.get_text(" ", strip=True)))
    return posts

def main():
    seen = set(open(SEEN_FILE).read().splitlines()) if os.path.exists(SEEN_FILE) else set()
    new_posts, new_ids = [], []

    for ch in CHANNELS:
        for dt, text in get_posts(ch):
            if dt not in seen and text:
                new_posts.append(f"[{ch}] {text}")
                new_ids.append(dt)

    if not new_posts:
        print("Новых постов нет — дайджест не отправлен.")
        return

    r = requests.post(
        AI_URL,
        headers={"Authorization": f"Bearer {AI_KEY}"},
        json={
            "model": AI_MODEL,
            "temperature": 0.4,
            "messages": [{"role": "user", "content": PROMPT + "\n---\n".join(new_posts)}]
        }
    )
    digest = r.json()["choices"][0]["message"]["content"]

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  json={
                      "chat_id": CHAT_ID,
                      "text": f"🗞️ Земельный дайджест · {datetime.now():%d.%m}\n\n{digest}"
                  })

    # Сохраняем seen.txt обратно в репозиторий
    with open(SEEN_FILE, "a") as f:
        f.write("\n".join(new_ids) + "\n")
    
    print("Дайджест отправлен ✅")

if __name__ == "__main__":
    main()
