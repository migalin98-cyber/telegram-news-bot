import os
import telebot
import feedparser
import schedule
import time
import threading
import re

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
SENT_ARTICLES_FILE = '/var/data/sent_articles.txt'
# --------------------

RSS_FEEDS = {
    'РИА Новости': 'https://ria.ru/export/rss2/index.xml',
    'Коммерсантъ': 'https://www.kommersant.ru/RSS/news.xml',
    'Известия': 'https://iz.ru/xml/rss/all.xml',
    'Ведомости': 'https://www.vedomosti.ru/rss/news',
    'Lenta.ru (Главное)': 'https://lenta.ru/rss/top7',
    'ТАСС': 'https://tass.ru/rss/v2.xml',
    'RT на русском': 'https://russian.rt.com/rss',
}

bot = telebot.TeleBot(TOKEN)

# --- НОВЫЙ, СУПЕР-УМНЫЙ "ОХОТНИК" ---
def get_media_from_entry(entry):
    """
    Ищет URL видео или изображения в записи RSS.
    Возвращает кортеж (тип_медиа, url). Например: ('video', 'http://...')
    Видео в приоритете.
    """
    # Сначала ищем в стандартном теге <enclosure>
    if 'links' in entry:
        # Приоритет видео
        for link in entry.links:
            if link.get('type', '').startswith('video/'):
                return 'video', link.href
        # Если видео нет, ищем фото
        for link in entry.links:
            if link.get('rel') == 'enclosure' and link.get('type', '').startswith('image/'):
                return 'image', link.href
                
    # Потом ищем в теге <media:content>
    if 'media_content' in entry and entry.media_content:
        # Приоритет видео
        for media in entry.media_content:
            if media.get('medium') == 'video' and 'url' in media:
                return 'video', media.url
        # Если видео нет, ищем фото
        for media in entry.media_content:
            if media.get('medium') == 'image' and 'url' in media:
                return 'image', media.url
                
    # В крайнем случае ищем <img> в тексте описания (только для фото)
    if 'summary' in entry:
        match = re.search(r'<img[^>]+src="([^">]+)"', entry.summary)
        if match:
            return 'image', match.group(1)
            
    return None, None # Если ничего не нашли

def load_sent_articles():
    try:
        with open(SENT_ARTICLES_FILE, 'r') as file:
            return set(line.strip() for line in file)
    except FileNotFoundError:
        return set()

sent_articles = load_sent_articles()

def send_news_job():
    print("Проверяю новости...")
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    
    for source_name, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url, agent=user_agent)
            
            new_articles_from_source = []
            for entry in feed.entries:
                article_id = entry.get('id', entry.link)
                if article_id not in sent_articles:
                    new_articles_from_source.append(entry)

            if new_articles_from_source:
                latest_entry = new_articles_from_source[0]
                article_id = latest_entry.get('id', latest_entry.link)
                
                message_text = f"*{source_name}*\n\n[{latest_entry.title}]({latest_entry.link})"
                media_type, media_url = get_media_from_entry(latest_entry)
                
                try:
                    # --- НОВАЯ ЛОГИКА ОТПРАВКИ ---
                    if media_type == 'video':
                        bot.send_video(CHANNEL_ID, video=media_url, caption=message_text, parse_mode='Markdown')
                    elif media_type == 'image':
                        bot.send_photo(CHANNEL_ID, photo=media_url, caption=message_text, parse_mode='Markdown')
                    else:
                        bot.send_message(CHANNEL_ID, message_text, parse_mode='Markdown', disable_web_page_preview=True)
                    # ----------------------------

                    printable_title = latest_entry.title.encode('utf-8', 'ignore').decode('utf-8')
                    print(f"Отправлена самая горячая новость от '{source_name}': {printable_title}")

                    for article in new_articles_from_source:
                        sent_articles.add(article.get('id', article.link))
                        with open(SENT_ARTICLES_FILE, 'a', encoding='utf-8') as file:
                            file.write(article.get('id', article.link) + '\n')
                    
                    time.sleep(1)
                except Exception as e:
                    print(f"Не удалось отправить статью '{latest_entry.title}'. Ошибка: {e}")

        except Exception as e:
            print(f"Ошибка при обработке {source_name}: {e}")
            
    print("Проверка завершена.")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- ЗАПУСК ---
if __name__ == "__main__":
    print("Новостной бот для канала запущен в 'медиа' режиме.")
    schedule.every(15).minutes.do(send_news_job)
    send_news_job()

    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Бот остановлен вручную.")

