from flask import Flask, jsonify, request
from flask_cors import CORS
import cloudscraper
import requests
import time

start = Flask(__name__)
CORS(start)

scraper = cloudscraper.create_scraper()

# ==========================
# Настройки кеша
# ==========================
CACHE_TTL = 15  # кеш на 15 секунд
cache = {}      # кеш по username и платформе


# ==========================
# W.TV функции
# ==========================
def get_user_id(username):
    try:
        url = f"https://profiles-service.w.tv/api/v1/profiles/by-nickname/{username}?user_lang=ru"
        r = scraper.get(url, timeout=5)
        if r.status_code != 200:
            print("Статус код профиля WTV:", r.status_code)
            return None
        data = r.json()
        user_id = data.get("profile", {}).get("userId")
        return user_id
    except Exception as e:
        print("Ошибка получения userId WTV:", e)
        return None


def get_viewers_by_id(user_id):
    try:
        url = f"https://streams-search-service.w.tv/api/v1/channels/{user_id}?user_lang=ru"
        r = scraper.get(url, timeout=5)
        if r.status_code != 200:
            print("Статус код канала WTV:", r.status_code)
            return 0
        data = r.json()
        viewers = data.get("channel", {}).get("liveStream", {}).get("viewers", 0)
        return viewers
    except Exception as e:
        print("Ошибка получения viewers WTV:", e)
        return 0


# ==========================
# Twitch функции
# ==========================
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_TOKEN = None
TWITCH_TOKEN_EXPIRES = 0


def get_twitch_token():
    global TWITCH_TOKEN, TWITCH_TOKEN_EXPIRES
    if time.time() < TWITCH_TOKEN_EXPIRES and TWITCH_TOKEN:
        return TWITCH_TOKEN

    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }

    r = requests.post(url, params=params)
    data = r.json()

    TWITCH_TOKEN = data.get("access_token")
    TWITCH_TOKEN_EXPIRES = time.time() + data.get("expires_in", 0) - 60
    return TWITCH_TOKEN


def get_twitch_viewers(username):
    try:
        token = get_twitch_token()
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}"
        }
        url = f"https://api.twitch.tv/helix/streams?user_login={username}"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200:
            print("Twitch статус:", r.status_code)
            return 0

        data = r.json().get("data", [])
        if not data:
            return 0

        return data[0].get("viewer_count", 0)
    except Exception as e:
        print("Ошибка Twitch:", e)
        return 0


# ==========================
# Kick функции
# ==========================
KICK_IDENTIFIER = os.getenv("KICK_IDENTIFIER")
KICK_API_KEY = os.getenv("KICK_API_KEY")


def get_kick_viewers(username):
    try:
        url = f"https://api.kick.com/public/v1/channels/{username}"

        headers = {
            "Authorization": f"Bearer {KICK_IDENTIFIER}",
            "X-Api-Key": KICK_API_KEY,
            "Accept": "application/json"
        }

        r = requests.get(url, headers=headers, timeout=5)

        if r.status_code != 200:
            print("Kick статус:", r.status_code)
            return 0

        data = r.json()
        livestream = data.get("data", {}).get("livestream")

        if not livestream:
            return 0

        return livestream.get("viewer_count", 0)

    except Exception as e:
        print("Ошибка Kick:", e)
        return 0


# ==========================
# Универсальный API маршрут
# ==========================
@app.route("/viewers")
def viewers():
    username = request.args.get("username")
    platform = request.args.get("platform", "wtv")

    if not username:
        return jsonify({"error": "username parameter required"})

    now = time.time()
    cache_key = f"{platform}:{username}"

    if cache_key in cache:
        cached_time, cached_value = cache[cache_key]
        if now - cached_time < CACHE_TTL:
            return jsonify({platform: cached_value})

    # ======================
    # W.TV
    # ======================
    if platform == "wtv":
        user_id = get_user_id(username)
        if not user_id:
            cache[cache_key] = (now, 0)
            return jsonify({"wtv": 0})

        viewers_count = get_viewers_by_id(user_id)
        cache[cache_key] = (now, viewers_count)
        return jsonify({"wtv": viewers_count})

    # ======================
    # Twitch
    # ======================
    elif platform == "twitch":
        viewers_count = get_twitch_viewers(username)
        cache[cache_key] = (now, viewers_count)
        return jsonify({"twitch": viewers_count})

    # ======================
    # Kick
    # ======================
    elif platform == "kick":
        viewers_count = get_kick_viewers(username)
        cache[cache_key] = (now, viewers_count)
        return jsonify({"kick": viewers_count})

    else:
        return jsonify({"error": "unknown platform"})


# ==========================
# Запуск сервера
# ==========================
if __name__ == "__main__":
    start.run()
