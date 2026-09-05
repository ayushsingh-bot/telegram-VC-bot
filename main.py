import asyncio
import os
import urllib.parse
from os import getenv

from dotenv import load_dotenv
from requests import get

from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.tl.types import (
    PeerChannel,
    PeerUser,
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
)
from telethon.tl.functions.channels import GetParticipantRequest

from pytgcalls import GroupCallFactory

from sqlite import VoiceChatDatabase


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

API_ID = getenv("API_ID")
API_HASH = getenv("API_HASH")
SESSION_STRING = getenv("SESSION_STRING")

GROUP_ID = getenv("GROUP_ID")
LOG_CHANNEL_ID = getenv("LOG_CHANNEL_ID")
LOGGER_BOT_TOKEN = getenv("LOGGER_BOT_TOKEN")

DB_FILENAME = getenv("DB_FILENAME", "vc.db")


if not API_ID:
    raise RuntimeError("API_ID is missing")

if not API_HASH:
    raise RuntimeError("API_HASH is missing")

if not SESSION_STRING:
    raise RuntimeError(
        "SESSION_STRING is missing. Generate a Telethon StringSession first."
    )

if not GROUP_ID:
    raise RuntimeError("GROUP_ID is missing")

if not LOG_CHANNEL_ID:
    raise RuntimeError("LOG_CHANNEL_ID is missing")

if not LOGGER_BOT_TOKEN:
    raise RuntimeError("LOGGER_BOT_TOKEN is missing")


API_ID = int(API_ID)
GROUP_ID = int(GROUP_ID)
LOG_CHANNEL_ID = int(LOG_CHANNEL_ID)


# ============================================================
# DATABASE
# ============================================================

vc_db = VoiceChatDatabase(DB_FILENAME)


# ============================================================
# TELEGRAM CLIENT
# ============================================================

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
)


# ============================================================
# SEND LOG MESSAGE
# ============================================================

def send_msg(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{LOGGER_BOT_TOKEN}/sendMessage"

        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        response = get(url, params=params, timeout=15)

        if not response.ok:
            print("Telegram log error:", response.text)

    except Exception as e:
        print("Failed to send log:", e)


# ============================================================
# USER NAME
# ============================================================

def get_full_name(user):
    first = user.first_name or ""
    last = user.last_name or ""

    name = f"{first} {last}".strip()

    return name if name else "Unknown"


def escape_markdown(text):
    if text is None:
        return ""

    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("`", "\\`")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


# ============================================================
# VC JOIN / LEAVE MESSAGE
# ============================================================

def getFormattedMessage(user, participant):

    if participant.left:
        status = "#LEFT"
    elif participant.just_joined:
        status = "#JOINED"
    else:
        status = "#VC_UPDATE"

    name = escape_markdown(get_full_name(user))

    if user.username:
        username = "@" + escape_markdown(user.username)
    else:
        username = "`None`"

    return f"""
{status}

**ID:** `{user.id}`
**Name:** [{name}](tg://user?id={user.id})
**Username:** {username}
"""


# ============================================================
# MUTE MESSAGE
# ============================================================

def getFormattedMessageForMute(user, admin, reason, muted):

    status = "#MUTED" if muted else "#UNMUTED"

    user_name = escape_markdown(get_full_name(user))
    admin_name = escape_markdown(get_full_name(admin))

    user_username = (
        "@" + escape_markdown(user.username)
        if user.username
        else "`None`"
    )

    admin_username = (
        "@" + escape_markdown(admin.username)
        if admin.username
        else "`None`"
    )

    return f"""
{status}

**ID:** `{user.id}`
**Name:** [{user_name}](tg://user?id={user.id})
**Username:** {user_username}

**Voice Admin:** [{admin_name}](tg://user?id={admin.id}) ({admin_username})

**Reason:** {escape_markdown(reason or "No reason")}
"""


# ============================================================
# CHECK ADMIN
# ============================================================

async def is_admin(group_id, user_id):

    participant = await client(
        GetParticipantRequest(
            channel=group_id,
            participant=user_id,
        )
    )

    return isinstance(
        participant.participant,
        (ChannelParticipantAdmin, ChannelParticipantCreator),
    )


# ============================================================
# SETUP COMMAND
# ============================================================

@client.on(events.NewMessage(pattern=r"^setup$"))
async def setup_handler(event):

    try:
        await client.get_dialogs()
        await client.get_dialogs(folder=0)
        await client.get_dialogs(folder=1)

        await event.reply("✅ Setup completed.")

    except Exception as e:
        print("Setup error:", e)


# ============================================================
# VMUTE
# ============================================================

@client.on(events.NewMessage(pattern=r"^[!/]vmute (\d+)(?: (.+))?$"))
async def vmute_handler(event):

    try:

        if not event.message.from_id:
            return

        admin_id = event.message.from_id.user_id

        if not await is_admin(GROUP_ID, admin_id):
            return await event.reply(
                "Only admins can execute the commands."
            )

        target_id = int(event.pattern_match.group(1))
        reason = event.pattern_match.group(2) or "No reason"

        if vc_db.is_user_muted(target_id):
            return await event.reply("User is already muted.")

        admin_result = await client(
            functions.users.GetFullUserRequest(
                id=admin_id
            )
        )

        admin = admin_result.user

        target_result = await client(
            functions.users.GetFullUserRequest(
                id=target_id
            )
        )

        target_user = target_result.user

        muted_successfully = vc_db.mute_user(
            target_user.id,
            get_full_name(target_user),
            admin.id,
            get_full_name(admin),
            reason,
        )

        if muted_successfully:

            msg = getFormattedMessageForMute(
                target_user,
                admin,
                reason,
                True,
            )

            send_msg(LOG_CHANNEL_ID, msg)

            await event.reply(
                f"✅ {get_full_name(target_user)} has been muted."
            )

        else:

            await event.reply(
                "Something went wrong while muting the user."
            )

    except Exception as e:

        print("VMUTE error:", repr(e))

        try:
            await event.reply(
                f"Error: {str(e)}"
            )
        except Exception:
            pass


# ============================================================
# VUNMUTE
# ============================================================

@client.on(events.NewMessage(pattern=r"^[!/]vunmute (\d+)(?: (.+))?$"))
async def vunmute_handler(event):

    try:

        if not event.message.from_id:
            return

        admin_id = event.message.from_id.user_id

        if not await is_admin(GROUP_ID, admin_id):
            return await event.reply(
                "Only admins can execute the commands."
            )

        target_id = int(event.pattern_match.group(1))
        reason = event.pattern_match.group(2) or "No reason"

        if vc_db.is_user_unmuted(target_id):
            return await event.reply("User is already unmuted.")

        admin_result = await client(
            functions.users.GetFullUserRequest(
                id=admin_id
            )
        )

        admin = admin_result.user

        target_result = await client(
            functions.users.GetFullUserRequest(
                id=target_id
            )
        )

        target_user = target_result.user

        success = vc_db.unmute_user(
            target_user.id,
            get_full_name(target_user),
            admin.id,
            get_full_name(admin),
            reason,
        )

        if success:

            msg = getFormattedMessageForMute(
                target_user,
                admin,
                reason,
                False,
            )

            send_msg(LOG_CHANNEL_ID, msg)

            await event.reply(
                f"✅ {get_full_name(target_user)} has been unmuted."
            )

        else:

            await event.reply(
                "Something went wrong while unmuting the user."
            )

    except Exception as e:

        print("VUNMUTE error:", repr(e))

        try:
            await event.reply(
                f"Error: {str(e)}"
            )
        except Exception:
            pass


# ============================================================
# JOIN VC / START MONITORING
# ============================================================

@client.on(events.NewMessage(pattern=r"^\.join-vc$"))
async def join_vc_handler(event):

    try:

        print("Starting VC monitoring...")

        group_call_factory = GroupCallFactory(
            client,
            GroupCallFactory.MTPROTO_CLIENT_TYPE.TELETHON,
        )

        group_call = group_call_factory.get_file_group_call()

        try:
            await event.delete()
        except Exception:
            pass

        result = await group_call.start(GROUP_ID)

        print("Group call started:", result)

        while not group_call.is_connected:
            await asyncio.sleep(1)

        print("VC monitoring active.")

        async def participant_handler(grpcall, participants):

            try:

                if not participants:
                    return

                participant = participants[0]
                peer = participant.peer

                # --------------------------------------------
                # CHANNEL PARTICIPANT
                # --------------------------------------------

                if isinstance(peer, PeerChannel):

                    if not participant.muted:

                        try:
                            await group_call.edit_group_call_member(
                                peer,
                                muted=True,
                            )

                            print(
                                "Muted channel participant:",
                                peer.channel_id,
                            )

                        except Exception as e:
                            print(
                                "Could not mute channel participant:",
                                e,
                            )

                    return

                # --------------------------------------------
                # USER PARTICIPANT
                # --------------------------------------------

                if isinstance(peer, PeerUser):

                    result = await client(
                        functions.users.GetFullUserRequest(
                            id=peer.user_id
                        )
                    )

                    user = result.user

                    # ----------------------------------------
                    # JOIN / LEAVE LOG
                    # ----------------------------------------

                    if participant.left or participant.just_joined:

                        message = getFormattedMessage(
                            user,
                            participant,
                        )

                        print(
                            "VC event:",
                            get_full_name(user),
                            user.id,
                            "LEFT" if participant.left else "JOINED",
                        )

                        send_msg(
                            LOG_CHANNEL_ID,
                            message,
                        )

                    # ----------------------------------------
                    # AUTO MUTE / UNMUTE
                    # ----------------------------------------

                    if participant.just_joined:

                        if vc_db.is_user_muted(user.id):

                            try:
                                await group_call.edit_group_call_member(
                                    peer,
                                    muted=True,
                                )

                                print(
                                    "Auto-muted:",
                                    get_full_name(user),
                                )

                            except Exception as e:
                                print(
                                    "Auto-mute error:",
                                    e,
                                )

                        elif vc_db.is_user_unmuted(user.id):

                            try:
                                await group_call.edit_group_call_member(
                                    peer,
                                    muted=False,
                                )

                                print(
                                    "Auto-unmuted:",
                                    get_full_name(user),
                                )

                            except Exception as e:
                                print(
                                    "Auto-unmute error:",
                                    e,
                                )

            except Exception as e:

                print(
                    "Participant handler error:",
                    repr(e),
                )

        group_call.on_participant_list_updated(
            participant_handler
        )

    except Exception as e:

        print(
            "VC monitoring error:",
            repr(e),
        )

        try:
            await event.reply(
                f"VC error: {str(e)}"
            )
        except Exception:
            pass


# ============================================================
# START
# ============================================================

async def main():

    print("Starting Telegram VC Bot...")

    await client.start()

    me = await client.get_me()

    print(
        f"Logged in as: "
        f"{get_full_name(me)} "
        f"(ID: {me.id})"
    )

    print("Telegram client connected.")
    print("Send .join-vc in the target group to start VC monitoring.")

    await client.run_until_disconnected()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("Bot stopped.")

    except Exception as e:
        print(
            "Fatal error:",
            repr(e),
        )
