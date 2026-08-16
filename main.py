from dotenv import load_dotenv
load_dotenv()

import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!!", intents=intents)

# 참여자 목록
participants = []

# 참여 명단 메시지
participant_message = None


def make_participant_list():
    if not participants:
        return "📋 **참여 명단**\n\n현재 참여자가 없습니다."

    text = "📋 **참여 명단**\n\n"

    for i, user in enumerate(participants, 1):
        text += f"{i}. {user['name']}\n"

    return text


async def update_participant_message(channel):
    global participant_message

    text = make_participant_list()

    # 기존 명단 메시지가 있으면 수정
    if participant_message:
        try:
            await participant_message.edit(content=text)
            return
        except discord.NotFound:
            participant_message = None
        except discord.HTTPException:
            participant_message = None

    # 없으면 새로 생성
    participant_message = await channel.send(text)


@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 완료!")


@bot.event
async def on_message(message):
    global participants
    global participant_message

    # 봇 메시지는 무시
    if message.author.bot:
        return

    content = message.content.strip()

    # =========================
    # 참여
    # =========================
    if content == "참여":

        user_id = message.author.id

        # 이미 참여했는지 확인
        if any(user["id"] == user_id for user in participants):
            await message.delete()

            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 이미 참여했습니다."
            )

            await notice.delete(delay=3)
            return

        # 참여 등록
        participants.append({
            "id": user_id,
            "name": message.author.display_name
        })

        # 참여 명령어 삭제
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        # 명단 업데이트
        await update_participant_message(message.channel)

        return

    # =========================
    # 취소
    # =========================
    if content == "취소":

        user_id = message.author.id

        # 참여자 찾기
        found = None

        for user in participants:
            if user["id"] == user_id:
                found = user
                break

        # 참여하지 않은 사람
        if found is None:
            try:
                await message.delete()
            except discord.HTTPException:
                pass

            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 참여하지 않았습니다."
            )

            await notice.delete(delay=3)
            return

        # 참여자 제거
        participants.remove(found)

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        # 명단 업데이트
        await update_participant_message(message.channel)

        return

    # =========================
    # 클린
    # =========================
    if content == "클린":

        # 메시지 관리 권한 확인
        if not message.author.guild_permissions.manage_messages:
            notice = await message.channel.send(
                "❌ 메시지 관리 권한이 필요합니다."
            )

            await notice.delete(delay=3)
            return

        # 참여자 초기화
        participants.clear()

        # 명단 메시지도 삭제
        if participant_message:
            try:
                await participant_message.delete()
            except discord.HTTPException:
                pass

            participant_message = None

        # 채널의 메시지 전부 확인
        async for msg in message.channel.history(limit=None):

            # 고정 메시지는 유지
            if msg.pinned:
                continue

            try:
                await msg.delete()
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

        return

    # 기존 명령어도 사용 가능하게 유지
    await bot.process_commands(message)


@bot.command()
async def 테스트(ctx):
    await ctx.send("전사봇 정상 작동 중! 🤖")


token = os.getenv("DISCORD_TOKEN")

if not token:
    raise ValueError("DISCORD_TOKEN이 설정되지 않았습니다.")

bot.run(token)
