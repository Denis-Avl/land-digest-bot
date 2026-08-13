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

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID   = os.getenv("CHAT_ID", "").strip()
AI_KEY    = os.getenv("AI_KEY", "").strip()

AI_URL = "https://openrouter.ai/api/v1/chat/completions"

# Список бесплатных моделей: бот переберёт их по очереди,
# пока не найдёт рабочую. Если какая-то "умрёт" — он просто возьмёт следующую.
AI_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "deepseek/deepseek-chat-v3-0324:free",
]

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
        time_a   = block.select_one("time")
        if text_div and time_a:
            posts.append((time_a.get("datetime"), text_div.get_text(" ", strip=True)))
    return posts

def ask_ai(text):
    """Перебирает бесплатные модели, пока одна не ответит."""
    for model in AI_MODELS:
        r = requests.post(
            AI_URL,
            headers={"Authorization": f"Bearer {AI_KEY}"},
            json={"model": model, "temperature": 0.4,
                  "messages": [{"role": "user", "content": text}]})
        if r.status_code == 200:
            print("✅ Сработала модель:", model)
            return r.json()["choices"][0]["message"]["content"]
        print("⚠️ Модель недоступна:", model, r.status_code)
    return None

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

    digest = ask_ai(PROMPT + "\n---\n".join(new_posts))
    if digest is None:
        print("❌ Ни одна бесплатная модель не сработала. Проверь список на openrouter.ai/models")
        return

    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  json={"chat_id": CHAT_ID,
                        "text": f"🗞️ Земельный дайджест · {datetime.now():%d.%m}\n\n{digest}"})

    open(SEEN_FILE, "a").write("\n".join(new_ids) + "\n")
    print("Дайджест отправлен ✅")

if __name__ == "__main__":
    main()
