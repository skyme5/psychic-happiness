import os
import re
import time

from flask import Flask

from slack_sdk import WebClient
import requests
from flask_apscheduler import APScheduler

from dotenv import load_dotenv

# set configuration values
class Config:
    SCHEDULER_API_ENABLED = True

load_dotenv()

lastfm_user = os.environ["LASTFM_USERNAME"]
lastfm_token = os.environ["LASTFM_TOKEN"]

client = WebClient(token=os.environ["SLACK_API_TOKEN"])
lastfm = requests.Session()

DEFAULT_STATUS = {
    "status_text": "Working on Frontend",
    "status_emoji": ":spreadd:",
    "status_expiration": 0,
}

polling_interval = 60 * 2
currently_playing = None


def format_slack_text(name: str, artist: str, max_len=100) -> str:
    artist_len = len(artist)
    new_name = name

    max_name_len = max_len - artist_len

    if max_name_len < len(name):
        parts = re.split(r"""\s+""", name)
        print(parts)
        index = 1
        new_name = parts[0]
        while index < len(parts) and len(new_name) < max_name_len:
            new_name = new_name + " " + parts[index]
            index += 1

    return f"Listening to {new_name} by {artist}"[:max_len]


def currently_listening():
    global currently_playing

    response = lastfm.get(
        f"http://ws.audioscrobbler.com/2.0/?method=user.getrecenttracks&user={lastfm_user}&api_key={lastfm_token}&limit=1&extended=1&format=json"
    )

    try:
        data = response.json()
        nowplaying = [
            track
            for track in data.get("recenttracks").get("track")
            if track.get("@attr") and track["@attr"].get("nowplaying")
        ]

        nowplaying = nowplaying[0] if len(nowplaying) > 0 else None
        if nowplaying and nowplaying is not currently_playing:
            currently_playing = nowplaying
            artist = nowplaying.get("artist").get("name")
            name = nowplaying.get("name")
            update_slack_status(
                text=format_slack_text(name=name, artist=artist),
                emoji=":listening_music:",
                expire=time.time() + 5 * 60,
            )

        if not nowplaying:
            restore_slack_status()
    except requests.ConnectionError:
        pass
    except requests.ConnectTimeout:
        pass
    except requests.JSONDecodeError:
        pass


def restore_slack_status():
    update_slack_status(
        text=DEFAULT_STATUS["status_text"],
        emoji=DEFAULT_STATUS["status_emoji"],
        expire=DEFAULT_STATUS["status_expiration"],
    )


def update_slack_status(text: str, emoji: str, expire: int):
    print(f"setting status {text}")
    client.users_profile_set(
        profile={
            "status_text": text,
            "status_emoji": emoji,
            "status_expiration": expire,
        }
    )


app = Flask(__name__)
app.config.from_object(Config())

scheduler = APScheduler()

scheduler.init_app(app)


@scheduler.task("cron", id="scrobble_slack_status", minute="*", max_instances=1)
def scrobble_slack_status():
    currently_listening()
    time.sleep(polling_interval)


scheduler.start()

if __name__ == "__main__":
    app.run()
