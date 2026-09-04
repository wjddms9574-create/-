from dotenv import load_dotenv
load_dotenv()

import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True

bot = commands.Bot(command_prefix="!!", intents=intents)

participants = []
waiting = []

participant_message = None
current_part = None

MAX_PARTICIPANTS = 12


def make_participant_list():
    if current_part is None:
        return "📋 **대내 모집이 시작되지 않았습니다.**"

    lines = [
        f"🔥 **{current_part}부 대내**",
        "",
        "📋 **참여 명단**",
        ""
    ]

    if not participants:
        lines.append("현재 참여자가 없습니다.")
    else:
        for i, user in enumerate(participants, 1):
            lines.append(f"{i}. {user['name']}")

    if waiting:
        lines.extend([
            "",
            "⏳ **다음 부 대기**",
            ""
        ])

        for i, user in enumerate(waiting, 1):
            lines.append(f"{i}. {user['name']}")

    return "\n".join(lines)


async def update_participant_message(channel):
    global participant_message

    text = make_participant_list()

    if participant_message:
        try:
            await participant_message.edit(content=text)
            return
        except (discord.NotFound, discord.HTTPException):
            participant_message = None

    participant_message = await channel.send(text)


def user_exists(user_id):
    return (
        any(user["id"] == user_id for user in participants)
        or any(user["id"] == user_id for user in waiting)
    )


def find_member_by_name(guild, name):
    target_name = name.strip().lower()

    matches = []

    for member in guild.members:
        display_name = member.display_name.lower()
        username = member.name.lower()

        if target_name == display_name or target_name == username:
            matches.append(member)

    if len(matches) == 1:
        return matches[0], None

    if len(matches) == 0:
        return None, "not_found"

    return None, "duplicate"


@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 완료!")


@bot.event
async def on_message(message):
    global participants
    global waiting
    global participant_message
    global current_part

    if message.author.bot:
        return

    content = message.content.strip()

    # 운영진: 1부 / 2부 / 3부 ...
    if content.endswith("부"):
        part_text = content[:-1].strip()

        if part_text.isdigit():

            if not message.author.guild_permissions.manage_messages:
                try:
                    await message.delete()
                except:
                    pass

                notice = await message.channel.send(
                    "❌ 운영진만 대내 모집을 시작할 수 있습니다."
                )
                await notice.delete(delay=3)
                return

            if participant_message:
                try:
                    await participant_message.delete()
                except:
                    pass

                participant_message = None

            current_part = part_text

            participants = waiting.copy()
            waiting.clear()

            if len(participants) > MAX_PARTICIPANTS:
                waiting = participants[MAX_PARTICIPANTS:]
                participants = participants[:MAX_PARTICIPANTS]

            try:
                await message.delete()
            except:
                pass

            await update_participant_message(message.channel)
            return

    # 참여 / 참가
    if content in ["참여", "참가"]:

        if current_part is None:
            try:
                await message.delete()
            except:
                pass

            notice = await message.channel.send(
                "⚠️ 아직 대내 모집이 시작되지 않았습니다."
            )
            await notice.delete(delay=3)
            return

        user_id = message.author.id

        if user_exists(user_id):
            try:
                await message.delete()
            except:
                pass

            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 이미 등록되어 있습니다."
            )
            await notice.delete(delay=3)
            return

        user_data = {
            "id": user_id,
            "name": message.author.display_name
        }

        if len(participants) < MAX_PARTICIPANTS:
            participants.append(user_data)
        else:
            waiting.append(user_data)

        try:
            await message.delete()
        except:
            pass

        await update_participant_message(message.channel)
        return

    # 본인 취소
    if content == "취소":

        user_id = message.author.id
        removed = False

        for user in participants:
            if user["id"] == user_id:
                participants.remove(user)
                removed = True
                break

        if not removed:
            for user in waiting:
                if user["id"] == user_id:
                    waiting.remove(user)
                    removed = True
                    break

        try:
            await message.delete()
        except:
            pass

        if not removed:
            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 등록되어 있지 않습니다."
            )
            await notice.delete(delay=3)
            return

        if len(participants) < MAX_PARTICIPANTS and waiting:
            participants.append(waiting.pop(0))

        await update_participant_message(message.channel)
        return

    # 운영진: 불참 닉네임
    if content.startswith("불참 "):

        if not message.author.guild_permissions.manage_messages:
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )
            await notice.delete(delay=3)
            return

        name = content[3:].strip()

        target, error = find_member_by_name(message.guild, name)

        try:
            await message.delete()
        except:
            pass

        if error == "not_found":
            notice = await message.channel.send(
                f"⚠️ `{name}` 닉네임을 찾을 수 없습니다."
            )
            await notice.delete(delay=3)
            return

        if error == "duplicate":
            notice = await message.channel.send(
                f"⚠️ `{name}`과 같은 닉네임이 여러 명 있습니다."
            )
            await notice.delete(delay=3)
            return

        removed = False

        for user in participants:
            if user["id"] == target.id:
                participants.remove(user)
                removed = True
                break

        if not removed:
            for user in waiting:
                if user["id"] == target.id:
                    waiting.remove(user)
                    removed = True
                    break

        if not removed:
            notice = await message.channel.send(
                f"⚠️ {target.display_name}님은 명단에 없습니다."
            )
            await notice.delete(delay=3)
            return

        if len(participants) < MAX_PARTICIPANTS and waiting:
            participants.append(waiting.pop(0))

        await update_participant_message(message.channel)
        return

    # 운영진: 추가 닉네임
    if content.startswith("추가 "):

        if not message.author.guild_permissions.manage_messages:
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )
            await notice.delete(delay=3)
            return

        name = content[3:].strip()

        target, error = find_member_by_name(message.guild, name)

        try:
            await message.delete()
        except:
            pass

        if error == "not_found":
            notice = await message.channel.send(
                f"⚠️ `{name}` 닉네임을 찾을 수 없습니다."
            )
            await notice.delete(delay=3)
            return

        if error == "duplicate":
            notice = await message.channel.send(
                f"⚠️ `{name}`과 같은 닉네임이 여러 명 있습니다."
            )
            await notice.delete(delay=3)
            return

        if user_exists(target.id):
            notice = await message.channel.send(
                f"⚠️ {target.display_name}님은 이미 등록되어 있습니다."
            )
            await notice.delete(delay=3)
            return

        user_data = {
            "id": target.id,
            "name": target.display_name
        }

        if len(participants) < MAX_PARTICIPANTS:
            participants.append(user_data)
        else:
            waiting.append(user_data)

        await update_participant_message(message.channel)
        return

    # 집합 + 시간
    if content.startswith("집합"):

        if not message.author.guild_permissions.manage_messages:
            try:
                await message.delete()
            except:
                pass

            notice = await message.channel.send(
                "❌ 운영진만 집합 알림을 보낼 수 있습니다."
            )
            await notice.delete(delay=3)
            return

        if current_part is None:
            notice = await message.channel.send(
                "⚠️ 현재 모집 중인 대내가 없습니다."
            )
            await notice.delete(delay=3)
            return

        if not participants:
            notice = await message.channel.send(
                "⚠️ 현재 참여자가 없습니다."
            )
            await notice.delete(delay=3)
            return

        gather_time = content[2:].strip()

        try:
            await message.delete()
        except:
            pass

        if not gather_time:
            notice = await message.channel.send(
                "⚠️ 시간을 같이 적어주세요. 예: `집합 10시 30분`"
            )
            await notice.delete(delay=5)
            return

        mentions = " ".join(
            f"<@{user['id']}>" for user in participants
        )

        await message.channel.send(
            f"{mentions}\n\n"
            f"🔔 **{current_part}부 대내 참여자분들 {gather_time}까지 집합해주세요!**"
        )
        return

    # 클린
    if content == "클린":

        if not message.author.guild_permissions.manage_messages:
            notice = await message.channel.send(
                "❌ 메시지 관리 권한이 필요합니다."
            )
            await notice.delete(delay=3)
            return

        participants.clear()
        waiting.clear()
        current_part = None
        participant_message = None

        async for msg in message.channel.history(limit=None):
            if msg.pinned:
                continue

            try:
                await msg.delete()
            except:
                pass

        return

    await bot.process_commands(message)


@bot.command()
async def 테스트(ctx):
    await ctx.send("전사봇 정상 작동 중! 🤖")


token = os.getenv("DISCORD_TOKEN")

if not token:
    raise ValueError("DISCORD_TOKEN이 설정되지 않았습니다.")

bot.run(token)
