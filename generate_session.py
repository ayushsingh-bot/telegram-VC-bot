from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import os


api_id = int(input("Enter API_ID: ").strip())
api_hash = input("Enter API_HASH: ").strip()


with TelegramClient(
    StringSession(),
    api_id,
    api_hash
) as client:

    print("\nLogin successful!")

    session_string = client.session.save()

    print("\n" + "=" * 60)
    print("YOUR SESSION STRING:")
    print("=" * 60)
    print(session_string)
    print("=" * 60)

    print("\nCopy this entire string.")
