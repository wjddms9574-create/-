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

# =========================
# 기본 설정
# =========================

MAX_PARTICIPANTS = 12

# 운영진 역할 이름
# 디스코드 역할 이름이 정확히 "운영진"이어야 함
STAFF_ROLE_NAME = "운영진"

participants = []
waiting = []

participant_message = None
current_part = None

# 12명 모집 완료 알림을 이미 보냈는지
full_notification_sent = False


# =========================
# 참여 명단 만들기
# =========================

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

    # 13번부터 다음 부 대기
    if waiting:
        lines.extend([
            "",
            "⏳ **다음 부 대기**",
            ""
        ])

        for i, user in enumerate(waiting, 1):
            lines.append(f"{i}. {user['name']}")

    return "\n".join(lines)


# =========================
# 명단 메시지 업데이트
# =========================

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


# =========================
# 운영진 역할 찾기
# =========================

def get_staff_role(guild):
    return discord.utils.get(guild.roles, name=STAFF_ROLE_NAME)


# =========================
# 12명 모집 상태 확인
# =========================

async def check_full_status(channel):
    global full_notification_sent

    count = len(participants)
    staff_role = get_staff_role(channel.guild)

    if staff_role:
        staff_mention = staff_role.mention
    else:
        staff_mention = "**운영진**"

    # 12명이 처음 된 순간
    if count == MAX_PARTICIPANTS and not full_notification_sent:

        full_notification_sent = True

        await channel.send(
            f"{staff_mention}\n\n"
            f"✅ **{current_part}부 인원 모집 완료!**\n"
            f"집합 시간을 정해주세요.",
            allowed_mentions=discord.AllowedMentions(
                roles=True,
                users=False,
                everyone=False
            )
        )

    # 12명이었다가 11명으로 줄어든 경우
    elif count == MAX_PARTICIPANTS - 1 and full_notification_sent:

        full_notification_sent = False

        await channel.send(
            f"{staff_mention}\n\n"
            f"⚠️ **{current_part}부 참여자 한 명이 빠졌습니다.**\n"
            f"현재 인원: **{count}/{MAX_PARTICIPANTS}명**",
            allowed_mentions=discord.AllowedMentions(
                roles=True,
                users=False,
                everyone=False
            )
        )


# =========================
# 이미 등록된 사람인지 확인
# =========================

def user_exists(user_id):
    return (
        any(user["id"] == user_id for user in participants)
        or
        any(user["id"] == user_id for user in waiting)
    )


# =========================
# 실제 닉네임 부분만 추출
# =========================

def get_base_name(member):
    display_name = member.display_name.strip()

    # 앞의 [M], [R], [S] 제거
    for tag in ["[M]", "[R]", "[S]"]:
        if display_name.startswith(tag):
            display_name = display_name[len(tag):].strip()
            break

    # "/" 앞부분까지만 실제 닉네임으로 사용
    base_name = display_name.split("/")[0].strip()

    return base_name


# =========================
# 닉네임 일부 검색
# =========================

def find_member_by_name(guild, name):
    target_name = name.strip().lower()

    exact_matches = []
    partial_matches = []

    for member in guild.members:
        if member.bot:
            continue

        base_name = get_base_name(member).lower()

        # 정확히 일치
        if target_name == base_name:
            exact_matches.append(member)

        # 일부 포함
        elif target_name in base_name:
            partial_matches.append(member)

    if len(exact_matches) == 1:
        return exact_matches[0], None, []

    if len(exact_matches) > 1:
        return None, "duplicate", exact_matches

    if len(partial_matches) == 1:
        return partial_matches[0], None, []

    if len(partial_matches) == 0:
        return None, "not_found", []

    return None, "duplicate", partial_matches


# =========================
# 검색 오류 안내
# =========================

async def handle_search_error(channel, name, error, matches):
    if error == "not_found":
        notice = await channel.send(
            f"⚠️ `{name}` 닉네임을 찾을 수 없습니다."
        )
        await notice.delete(delay=5)
        return True

    if error == "duplicate":
        names = "\n".join(
            f"• {member.display_name}"
            for member in matches[:10]
        )

        notice = await channel.send(
            f"⚠️ `{name}`으로 여러 명이 검색됐습니다.\n\n"
            f"{names}\n\n"
            f"조금 더 구체적으로 입력해주세요."
        )

        await notice.delete(delay=10)
        return True

    return False


# =========================
# 봇 로그인
# =========================

@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 완료!")


# =========================
# 채팅 명령 처리
# =========================

@bot.event
async def on_message(message):
    global participants
    global waiting
    global participant_message
    global current_part
    global full_notification_sent

    if message.author.bot:
        return

    if not message.guild:
        return

    content = message.content.strip()


    # =====================================
    # 운영진: 1부 / 2부 / 3부 ...
    # =====================================

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

            # 기존 명단 메시지 삭제
            if participant_message:
                try:
                    await participant_message.delete()
                except:
                    pass

                participant_message = None

            current_part = part_text

            # 새로운 부가 열렸으므로 알림 상태 초기화
            full_notification_sent = False

            # 이전 부 대기자 → 새 부 참여자로 이동
            participants = waiting.copy()
            waiting.clear()

            # 12명 초과 시 다시 대기로 분리
            if len(participants) > MAX_PARTICIPANTS:
                waiting = participants[MAX_PARTICIPANTS:]
                participants = participants[:MAX_PARTICIPANTS]

            try:
                await message.delete()
            except:
                pass

            await update_participant_message(message.channel)

            # 대기자가 넘어오면서 바로 12명이 된 경우도 확인
            await check_full_status(message.channel)

            return


    # =====================================
    # 참여 / 참가
    # =====================================

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

        # 12명까지 현재 부
        if len(participants) < MAX_PARTICIPANTS:
            participants.append(user_data)

        # 13번째부터 다음 부 대기
        else:
            waiting.append(user_data)

        try:
            await message.delete()
        except:
            pass

        await update_participant_message(message.channel)

        # 12명 모집 완료 여부 확인
        await check_full_status(message.channel)

        return


    # =====================================
    # 본인 취소
    # =====================================

    if content == "취소":

        user_id = message.author.id
        removed_from_main = False
        removed = False

        for user in participants:
            if user["id"] == user_id:
                participants.remove(user)
                removed_from_main = True
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

        # 대기자가 있으면 현재 부 빈자리로 자동 승급
        if removed_from_main and waiting:
            participants.append(waiting.pop(0))

        await update_participant_message(message.channel)

        # 인원 변동 확인
        await check_full_status(message.channel)

        return


    # =====================================
    # 운영진: 불참 닉네임
    # =====================================

    if content.startswith("불참 "):

        if not message.author.guild_permissions.manage_messages:
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )
            await notice.delete(delay=3)
            return

        name = content[3:].strip()

        target, error, matches = find_member_by_name(
            message.guild,
            name
        )

        try:
            await message.delete()
        except:
            pass

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        removed_from_main = False
        removed = False

        for user in participants:
            if user["id"] == target.id:
                participants.remove(user)
                removed_from_main = True
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
                f"⚠️ {get_base_name(target)}님은 명단에 없습니다."
            )
            await notice.delete(delay=3)
            return

        # 대기 1번이 있으면 빈자리로 자동 이동
        if removed_from_main and waiting:
            participants.append(waiting.pop(0))

        await update_participant_message(message.channel)

        # 인원 변동 확인
        await check_full_status(message.channel)

        return


    # =====================================
    # 운영진: 추가 닉네임
    # =====================================

    if content.startswith("추가 "):

        if not message.author.guild_permissions.manage_messages:
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )
            await notice.delete(delay=3)
            return

        if current_part is None:
            notice = await message.channel.send(
                "⚠️ 먼저 `1부`, `2부` 등으로 모집을 시작해주세요."
            )
            await notice.delete(delay=4)
            return

        name = content[3:].strip()

        target, error, matches = find_member_by_name(
            message.guild,
            name
        )

        try:
            await message.delete()
        except:
            pass

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        if user_exists(target.id):
            notice = await message.channel.send(
                f"⚠️ {get_base_name(target)}님은 이미 등록되어 있습니다."
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

        # 추가 명령으로 12명이 된 경우도 확인
        await check_full_status(message.channel)

        return


    # =====================================
    # 집합 + 시간
    # =====================================

    if content == "집합" or content.startswith("집합 "):

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

        gather_time = content[2:].strip()

        try:
            await message.delete()
        except:
            pass

        if not gather_time:
            notice = await message.channel.send(
                "⚠️ 시간을 같이 적어주세요.\n"
                "예: `집합 20:30`"
            )
            await notice.delete(delay=5)
            return

        mentions = " ".join(
            f"<@{user['id']}>"
            for user in participants
        )

        await message.channel.send(
    f"{mentions}\n\n"
    f"🔔 **{current_part}부 대내**\n"
    f"      **{gather_time}까지**\n"
    f"      **대내 대기방에 집합해주세요!**"
)
        )

        return


    # =====================================
    # 클린
    # =====================================

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
        full_notification_sent = False

        # 고정 메시지는 유지
        async for msg in message.channel.history(limit=None):

            if msg.pinned:
                continue

            try:
                await msg.delete()
            except:
                pass

        return


    await bot.process_commands(message)


# =========================
# 테스트 명령
# =========================

@bot.command()
async def 테스트(ctx):
    await ctx.send("전사봇 정상 작동 중! 🤖")


# =========================
# 토큰
# =========================

token = os.getenv("DISCORD_TOKEN")

if not token:
    raise ValueError("DISCORD_TOKEN이 설정되지 않았습니다.")

bot.run(token)
