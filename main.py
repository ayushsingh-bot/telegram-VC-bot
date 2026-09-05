import asyncio
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import events
from telethon.tl.types import (
    UpdateGroupCallParticipants,
    PeerUser,
)

load_dotenv()


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

GROUP_ID = os.getenv("GROUP_ID")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
LOGGER_BOT_TOKEN = os.getenv("LOGGER_BOT_TOKEN")


if not API_ID:
    raise RuntimeError("❌ API_ID is missing")

if not API_HASH:
    raise RuntimeError("❌ API_HASH is missing")

if not SESSION_STRING:
    raise RuntimeError("❌ SESSION_STRING is missing")

if not GROUP_ID:
    raise RuntimeError("❌ GROUP_ID is missing")

if not LOG_CHANNEL_ID:
    raise RuntimeError("❌ LOG_CHANNEL_ID is missing")

if not LOGGER_BOT_TOKEN:
    raise RuntimeError("❌ LOGGER_BOT_TOKEN is missing")


API_ID = int(API_ID)
GROUP_ID = int(GROUP_ID)
LOG_CHANNEL_ID = int(LOG_CHANNEL_ID)


# ============================================================
# TELEGRAM CLIENT
# ============================================================

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
)


# ============================================================
# HELPERS
# ============================================================

def full_name(user):
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""

    name = f"{first} {last}".strip()

    return name or "Unknown"


def escape_html(text):
    if text is None:
        return ""

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def telegram_time(timestamp):
    if not timestamp:
        return datetime.now(timezone.utc).strftime(
            "%d-%m-%Y %H:%M:%S UTC"
        )

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc
    ).strftime("%d-%m-%Y %H:%M:%S UTC")


# ============================================================
# SEND LOG TO BOT CHANNEL
# ============================================================

def send_log(message):

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{LOGGER_BOT_TOKEN}/sendMessage"
        )

        data = {
            "chat_id": LOG_CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        response = requests.post(
            url,
            data=data,
            timeout=20,
        )

        if not response.ok:

            print(
                "❌ Log channel error:",
                response.text,
            )

        else:

            print("✅ Log sent successfully")

    except Exception as e:

        print(
            "❌ Failed to send log:",
            repr(e),
        )


# ============================================================
# GROUP INFORMATION
# ============================================================

group_title = "Unknown Group"


async def load_group():

    global group_title

    try:

        entity = await client.get_entity(GROUP_ID)

        group_title = getattr(
            entity,
            "title",
            None
        ) or "Unknown Group"

        print(
            f"✅ Monitoring group: "
            f"{group_title} "
            f"({GROUP_ID})"
        )

    except Exception as e:

        print(
            "❌ Could not load group:",
            repr(e),
        )


# ============================================================
# VC PARTICIPANT UPDATE
# ============================================================

@client.on(events.Raw)
async def raw_update_handler(update):

    if not isinstance(
        update,
        UpdateGroupCallParticipants
    ):
        return

    print(
        "\n📢 Group call participant update received"
    )

    print(
        "Participants in update:",
        len(update.participants)
    )

    for participant in update.participants:

        try:

            peer = participant.peer

            # We only care about normal Telegram users.
            if not isinstance(peer, PeerUser):
                continue

            user_id = peer.user_id

            # ------------------------------------------------
            # ONLY JOIN / LEAVE EVENTS
            # ------------------------------------------------

            if not participant.just_joined and not participant.left:
                continue

            # ------------------------------------------------
            # GET USER
            # ------------------------------------------------

            try:

                user = await client.get_entity(
                    user_id
                )

            except Exception as e:

                print(
                    f"❌ Could not get user {user_id}:",
                    repr(e),
                )

                continue

            name = full_name(user)

            username = getattr(
                user,
                "username",
                None
            )

            if username:

                username_text = f"@{username}"

            else:

                username_text = "No username"

            # ------------------------------------------------
            # EVENT
            # ------------------------------------------------

            if participant.just_joined:

                event_name = "JOINED"
                emoji = "🟢"

            elif participant.left:

                event_name = "LEFT"
                emoji = "🔴"

            else:

                continue

            # ------------------------------------------------
            # TIME
            # ------------------------------------------------

            event_timestamp = getattr(
                participant,
                "date",
                None
            )

            event_time = telegram_time(
                event_timestamp
            )

            # ------------------------------------------------
            # LOG MESSAGE
            # ------------------------------------------------

            message = f"""
<b>{emoji} VC {event_name}</b>

<b>Group:</b> {escape_html(group_title)}

<b>Name:</b> {escape_html(name)}
<b>Username:</b> {escape_html(username_text)}
<b>User ID:</b> <code>{user_id}</code>

<b>Time:</b> {event_time}
"""

            print(
                f"➡️ VC {event_name}: "
                f"{name} | "
                f"{username_text} | "
                f"{user_id}"
            )

            # ------------------------------------------------
            # SEND LOG
            # ------------------------------------------------

            await asyncio.to_thread(
                send_log,
                message
            )

        except Exception as e:

            print(
                "❌ Participant processing error:",
                repr(e),
            )


# ============================================================
# START BOT
# ============================================================

async def main():

    print("======================================")
    print("     TELEGRAM VC LOGGER")
    print("======================================")

    print("Starting Telegram client...")

    # Connect without allowing Telethon to open
    # an interactive login prompt on Railway.
    await client.connect()

    print("Telegram connection established.")

    # Check whether the StringSession is already authorized.
    if not await client.is_user_authorized():
        raise RuntimeError(
            "❌ SESSION_STRING is not authorized. "
            "Generate a new Telethon session string."
        )

    me = await client.get_me()

    print(
        f"✅ Logged in as: "
        f"{full_name(me)} "
        f"(@{getattr(me, 'username', None)})"
    )

    print(
        f"✅ User ID: {me.id}"
    )

    await load_group()

    print("--------------------------------------")
    print("✅ VC participant listener is ACTIVE")
    print("--------------------------------------")

    print(
        "Waiting for VC JOIN / LEFT events..."
    )

    await client.run_until_disconnected()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print("Bot stopped.")

    except Exception as e:

        print(
            "❌ Fatal error:",
            repr(e),
        )
