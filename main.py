from dotenv import load_dotenv
load_dotenv()

import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!!", intents=intents)

participants = []
participant_message = None
current_part = None


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


@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 완료!")


@bot.event
async def on_message(message):
    global participants
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

            # 기존 명단 삭제
            if participant_message:
                try:
                    await participant_message.delete()
                except:
                    pass

                participant_message = None

            # 새 부 시작
            current_part = part_text
            participants.clear()

            try:
                await message.delete()
            except:
                pass

            await update_participant_message(message.channel)
            return

    # 참여
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

        if any(user["id"] == user_id for user in participants):
            try:
                await message.delete()
            except:
                pass

            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 이미 참여했습니다."
            )
            await notice.delete(delay=3)
            return

        participants.append({
            "id": user_id,
            "name": message.author.display_name
        })

        try:
            await message.delete()
        except:
            pass

        await update_participant_message(message.channel)
        return

    # 취소
    if content == "취소":

        user_id = message.author.id
        found = None

        for user in participants:
            if user["id"] == user_id:
                found = user
                break

        try:
            await message.delete()
        except:
            pass

        if found is None:
            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 참여하지 않았습니다."
            )
            await notice.delete(delay=3)
            return

        participants.remove(found)

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
            try:
                await message.delete()
            except:
                pass

            notice = await message.channel.send(
                "⚠️ 현재 모집 중인 대내가 없습니다."
            )
            await notice.delete(delay=3)
            return

        if not participants:
            try:
                await message.delete()
            except:
                pass

            notice = await message.channel.send(
                "⚠️ 현재 참여자가 없습니다."
            )
            await notice.delete(delay=3)
            return

        # "집합" 뒤에 적은 시간 가져오기
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
        current_part = None
        participant_message = None

        # 고정 메시지는 남기고 나머지 전부 삭제
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
