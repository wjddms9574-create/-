from dotenv import load_dotenv
load_dotenv()

import os
import re
import random
import json

from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks


# ==================================================
# 기본 설정
# ==================================================

KST = ZoneInfo("Asia/Seoul")

MAX_PARTICIPANTS = 12

CLAN_ROLE_NAME = "클랜원"
MERCENARY_ROLE_NAME = "용병"

# 채널 ID
GUILD_ID = 898149239538982932

CLAN_ROLE_CHANNEL_ID = 1517498787533164645
MERCENARY_REGISTER_CHANNEL_ID = 1550069637755183164

ADMIN_ROLE_NAMES = [
    "운영자",
    "운영진",
    "부마스터",
    "마스터"
]

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True
intents.reactions = True

bot = commands.Bot(
    command_prefix="!!",
    intents=intents
)


# ==================================================
# JSON
# ==================================================

def load_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )


# ==================================================
# 대내 모집 상태
# ==================================================

participants = []
waiting = []

participant_message = None
current_part = None

full_notification_sent = False
recruitment_was_full = False


# ==================================================
# 모집 상태 저장
# ==================================================

RECRUITMENT_FILE = "recruitment_state.json"
recruitment_state = {}


def load_recruitment_state():
    global recruitment_state
    global participants
    global waiting
    global current_part
    global full_notification_sent
    global recruitment_was_full

    recruitment_state = load_json_file(
        RECRUITMENT_FILE,
        {}
    )

    participants = recruitment_state.get(
        "participants",
        []
    )

    waiting = recruitment_state.get(
        "waiting",
        []
    )

    current_part = recruitment_state.get(
        "current_part"
    )

    full_notification_sent = recruitment_state.get(
        "full_notification_sent",
        False
    )

    recruitment_was_full = recruitment_state.get(
        "recruitment_was_full",
        False
    )


def save_recruitment_state(guild=None):
    global recruitment_state

    guild_id = recruitment_state.get(
        "guild_id"
    )

    channel_id = recruitment_state.get(
        "channel_id"
    )

    message_id = recruitment_state.get(
        "message_id"
    )

    if guild is not None:
        guild_id = guild.id

    if participant_message is not None:
        channel_id = (
            participant_message.channel.id
        )

        message_id = (
            participant_message.id
        )

    recruitment_state = {
        "guild_id": guild_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "current_part": current_part,
        "participants": participants,
        "waiting": waiting,
        "full_notification_sent":
            full_notification_sent,
        "recruitment_was_full":
            recruitment_was_full
    }

    save_json_file(
        RECRUITMENT_FILE,
        recruitment_state
    )


def clear_recruitment_state():
    global recruitment_state

    recruitment_state = {
        "guild_id": None,
        "channel_id": None,
        "message_id": None,
        "current_part": None,
        "participants": [],
        "waiting": [],
        "full_notification_sent": False,
        "recruitment_was_full": False
    }

    save_json_file(
        RECRUITMENT_FILE,
        recruitment_state
    )


load_recruitment_state()


# ==================================================
# 운영진
# ==================================================

def is_admin(member):
    if member.guild_permissions.administrator:
        return True

    member_role_names = [
        role.name
        for role in member.roles
    ]

    return any(
        role_name in member_role_names
        for role_name in ADMIN_ROLE_NAMES
    )


def get_admin_mentions(guild):
    role = discord.utils.get(
        guild.roles,
        name="운영진"
    )

    if role:
        return role.mention

    return "**운영진**"


# ==================================================
# 용병 / 클랜원 역할 가져오기
# ==================================================

def get_role_by_name(
    guild,
    role_name
):
    return discord.utils.get(
        guild.roles,
        name=role_name
    )


# ==================================================
# 클랜원 역할 받기 버튼
# ==================================================

class ClanRoleView(
    discord.ui.View
):
    def __init__(self):
        # timeout=None:
        # 봇 재시작 후에도 사용할 수 있는
        # 영구 버튼으로 등록
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="클랜원 역할 받기",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="jeonsa_clan_role_button"
    )
    async def clan_role_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        guild = interaction.guild
        member = interaction.user

        if guild is None:
            await interaction.response.send_message(
                "❌ 서버에서만 사용할 수 있습니다.",
                ephemeral=True
            )
            return

        clan_role = get_role_by_name(
            guild,
            CLAN_ROLE_NAME
        )

        mercenary_role = get_role_by_name(
            guild,
            MERCENARY_ROLE_NAME
        )

        if clan_role is None:
            await interaction.response.send_message(
                f"❌ `{CLAN_ROLE_NAME}` 역할을 "
                f"찾을 수 없습니다.\n"
                f"운영진에게 문의해주세요.",
                ephemeral=True
            )
            return

        # 이미 클랜원인 경우
        if clan_role in member.roles:
            await interaction.response.send_message(
                "✅ 이미 클랜원 역할을 "
                "가지고 있습니다.",
                ephemeral=True
            )
            return

        try:
            # 용병이었다가 정식 가입하는 경우
            # 용병 역할만 제거
            # 닉네임은 변경하지 않음
            if (
                mercenary_role is not None
                and mercenary_role in member.roles
            ):
                await member.remove_roles(
                    mercenary_role,
                    reason="용병에서 클랜원으로 전환"
                )

            # 클랜원 역할 지급
            await member.add_roles(
                clan_role,
                reason="클랜원 역할 받기 버튼"
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 전사봇이 역할을 변경할 "
                "권한이 없습니다.\n"
                "전사봇 역할이 `용병`, `클랜원` "
                "역할보다 위에 있는지 확인해주세요.",
                ephemeral=True
            )
            return

        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ 역할 변경 중 오류가 발생했습니다.\n"
                "잠시 후 다시 눌러주세요.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "✅ **클랜원 역할을 받았습니다!**",
            ephemeral=True
        )


# ==================================================
# 클랜원 역할 버튼 메시지 생성
# ==================================================

async def send_clan_role_button(
    guild
):
    channel = guild.get_channel(
        CLAN_ROLE_CHANNEL_ID
    )

    if channel is None:
        print(
            f"{guild.name}: "
            f"클랜원 역할받기 채널을 찾을 수 없습니다."
        )
        return

    # 같은 안내 메시지가 이미 있으면
    # 봇을 재시작해도 새로 만들지 않음
    try:
        async for msg in channel.history(
            limit=50
        ):
            if (
                bot.user is not None
                and msg.author.id == bot.user.id
                and msg.embeds
                and msg.embeds[0].title
                == "⚔️ 전사 클랜원 역할"
            ):
                return

    except (
        discord.Forbidden,
        discord.HTTPException
    ):
        pass

    embed = discord.Embed(
        title="⚔️ 전사 클랜원 역할",
        description=(
            "**본인인증 및 클랜 가입이 완료된 분만 "
            "아래 버튼을 눌러주세요.**\n\n"
            "버튼을 누르면 `클랜원` 역할이 "
            "자동으로 지급됩니다.\n\n"
            "※ 용병으로 활동 중이던 분이 "
            "클랜에 가입하는 경우\n"
            "`용병` 역할은 자동으로 제거됩니다."
        ),
        color=discord.Color.red()
    )

    try:
        await channel.send(
            embed=embed,
            view=ClanRoleView()
        )

    except discord.Forbidden:
        print(
            f"{guild.name}: "
            f"클랜원 역할받기 채널에 "
            f"메시지를 보낼 권한이 없습니다."
        )

    except discord.HTTPException as e:
        print(
            f"{guild.name}: "
            f"클랜원 역할 버튼 생성 오류: {e}"
        )
    except discord.HTTPException as e:
        print(
            f"{guild.name}: "
            f"클랜원 역할 버튼 생성 오류: {e}"
        )


# ==================================================
# 용병 등록 처리
# ==================================================

async def handle_mercenary_registration(
    message
):
    # 지정한 용병 등록 채널에서만 작동
    if (
        message.channel.id
        != MERCENARY_REGISTER_CHANNEL_ID
    ):
        return False

    # 운영진 / 부마스터 / 마스터가 작성한 글은
    # 공지 등으로 간주하고 용병 등록 처리하지 않음
    if is_admin(
        message.author
    ):
        return False

    content = (
        message.content
        .strip()
    )

    # "/"를 기준으로 나누고
    # 각 항목 앞뒤 공백 자동 제거
    #
    # 아래 형식을 모두 동일하게 인식:
    #
    # 감자/용병/치
    # 감자 / 용병 / 치
    # 감자/ 용병 /치
    # 감자 /용병/ 치
    parts = [
        part.strip()
        for part in content.split("/")
    ]

    # 정확히 3부분이어야 하고
    # 가운데에는 반드시 "용병"이 들어가야 함
    if (
        len(parts) != 3
        or not parts[0]
        or parts[1] != "용병"
        or not parts[2]
    ):
        try:
            await message.delete()
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        notice = await message.channel.send(
            f"{message.author.mention}\n"
            f"⚠️ **용병 등록 형식이 "
            f"올바르지 않습니다.**\n\n"
            f"`본인닉네임 / 용병 / 지인닉네임`\n\n"
            f"예: `감자 / 용병 / 치`\n"
            f"※ `/` 앞뒤 띄어쓰기는 "
            f"상관없습니다."
        )

        await notice.delete(
            delay=8
        )

        return True

    mercenary_name = (
        parts[0]
        .strip()
    )

    acquaintance_name = (
        parts[2]
        .strip()
    )

    # 최종 닉네임은 띄어쓰기 없이 통일
    new_nickname = (
        f"{mercenary_name}"
        f"/용병/"
        f"{acquaintance_name}"
    )

    # Discord 서버 닉네임 길이 제한 보호
    if len(new_nickname) > 32:
        try:
            await message.delete()
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        notice = await message.channel.send(
            f"{message.author.mention}\n"
            f"⚠️ 닉네임이 너무 깁니다.\n"
            f"본인 닉네임이나 지인 닉네임을 "
            f"조금 줄여서 다시 입력해주세요."
        )

        await notice.delete(
            delay=8
        )

        return True

    mercenary_role = get_role_by_name(
        message.guild,
        MERCENARY_ROLE_NAME
    )

    if mercenary_role is None:
        notice = await message.channel.send(
            f"❌ `{MERCENARY_ROLE_NAME}` 역할을 "
            f"찾을 수 없습니다.\n"
            f"운영진에게 문의해주세요."
        )

        await notice.delete(
            delay=8
        )

        return True

    clan_role = get_role_by_name(
        message.guild,
        CLAN_ROLE_NAME
    )

    # 이미 클랜원인 사람이
    # 실수로 용병 등록하는 것 방지
    if (
        clan_role is not None
        and clan_role in message.author.roles
    ):
        try:
            await message.delete()
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        notice = await message.channel.send(
            f"{message.author.mention}\n"
            f"⚠️ 이미 클랜원 역할을 가지고 있어 "
            f"용병으로 등록할 수 없습니다."
        )

        await notice.delete(
            delay=6
        )

        return True

    try:
        # 닉네임 자동 변경
        await message.author.edit(
            nick=new_nickname,
            reason="전사봇 용병 자동 등록"
        )

        # 용병 역할 자동 지급
        await message.author.add_roles(
            mercenary_role,
            reason="전사봇 용병 자동 등록"
        )

    except discord.Forbidden:
        notice = await message.channel.send(
            f"{message.author.mention}\n"
            f"❌ 전사봇이 닉네임 또는 역할을 "
            f"변경할 권한이 없습니다.\n"
            f"전사봇의 역할 위치와 권한을 "
            f"확인해주세요."
        )

        await notice.delete(
            delay=8
        )

        return True

    except discord.HTTPException:
        notice = await message.channel.send(
            f"{message.author.mention}\n"
            f"❌ 용병 등록 중 오류가 발생했습니다.\n"
            f"잠시 후 다시 입력해주세요."
        )

        await notice.delete(
            delay=8
        )

        return True

    # 등록에 성공하면
    # 용병이 작성했던 메시지 삭제
    try:
        await message.delete()
    except (
        discord.Forbidden,
        discord.NotFound,
        discord.HTTPException
    ):
        pass

    # 용병 역할을 받은 순간
    # Discord에서 설정해둔 채널 권한에 따라
    # 용병-등록 채널은 자동으로 사라지고
    # 용병용 채널들이 열림
    return True


# ==================================================
# 출석
# ==================================================

ATTENDANCE_FILE = "attendance.json"

attendance_data = load_json_file(
    ATTENDANCE_FILE,
    {}
)


def save_attendance():
    save_json_file(
        ATTENDANCE_FILE,
        attendance_data
    )


# ==================================================
# 부별 명단
# ==================================================

PART_HISTORY_FILE = "part_history.json"

part_history = load_json_file(
    PART_HISTORY_FILE,
    {}
)


def save_part_history():
    save_json_file(
        PART_HISTORY_FILE,
        part_history
    )


# ==================================================
# 클랜 관리
# ==================================================

MANAGEMENT_FILE = "clan_management.json"

management_data = load_json_file(
    MANAGEMENT_FILE,
    {}
)


def save_management():
    save_json_file(
        MANAGEMENT_FILE,
        management_data
    )


def get_guild_management(
    guild_id
):
    guild_key = str(
        guild_id
    )

    if guild_key not in management_data:
        management_data[
            guild_key
        ] = {
            "management_channel_id": None,
            "absence_reason_channel_id": None,
            "warnings": {},
            "inactivity": {},
            "reasons": {},
            "weekly_processed": []
        }

    data = management_data[
        guild_key
    ]

    data.setdefault(
        "management_channel_id",
        None
    )

    data.setdefault(
        "absence_reason_channel_id",
        None
    )

    data.setdefault(
        "warnings",
        {}
    )

    data.setdefault(
        "inactivity",
        {}
    )

    data.setdefault(
        "reasons",
        {}
    )

    data.setdefault(
        "weekly_processed",
        []
    )

    return data


# ==================================================
# 주차
# ==================================================

def get_week_info(
    target_date=None
):
    if target_date is None:
        target_date = datetime.now(
            KST
        ).date()

    monday = (
        target_date
        - timedelta(
            days=target_date.weekday()
        )
    )

    sunday = (
        monday
        + timedelta(
            days=6
        )
    )

    week_key = monday.strftime(
        "%Y-%m-%d"
    )

    return (
        week_key,
        monday,
        sunday
    )


def get_current_attendance():
    (
        week_key,
        monday,
        sunday
    ) = get_week_info()

    week_data = attendance_data.get(
        week_key,
        {}
    )

    return (
        week_key,
        monday,
        sunday,
        week_data
    )


# ==================================================
# 부별 명단 저장
# ==================================================

def save_current_part_history(
    guild
):
    if current_part is None:
        return

    (
        week_key,
        monday,
        sunday
    ) = get_week_info()

    guild_id = str(
        guild.id
    )

    if guild_id not in part_history:
        part_history[
            guild_id
        ] = {}

    if (
        week_key
        not in part_history[
            guild_id
        ]
    ):
        part_history[
            guild_id
        ][week_key] = {}

    part_key = (
        f"{current_part}부"
    )

    part_history[
        guild_id
    ][week_key][part_key] = [
        {
            "id": user["id"],
            "name": user["name"]
        }
        for user in participants
    ]

    save_part_history()


def get_saved_part_history(
    guild,
    part_number
):
    (
        week_key,
        monday,
        sunday
    ) = get_week_info()

    guild_id = str(
        guild.id
    )

    part_key = (
        f"{part_number}부"
    )

    return (
        part_history
        .get(
            guild_id,
            {}
        )
        .get(
            week_key,
            {}
        )
        .get(
            part_key
        )
    )


# ==================================================
# 클랜원
# ==================================================

def get_clan_members(
    guild
):
    clan_role = discord.utils.get(
        guild.roles,
        name=CLAN_ROLE_NAME
    )

    if clan_role is None:
        return None

    members = []

    for member in guild.members:
        if member.bot:
            continue

        if clan_role in member.roles:
            members.append(
                member
            )

    return members


# ==================================================
# 긴 명단
# ==================================================

def split_lines(
    lines,
    max_length=1800
):
    if not lines:
        return [
            "없음"
        ]

    chunks = []
    current = ""

    for line in lines:
        add_text = (
            line
            if not current
            else "\n" + line
        )

        if (
            len(current)
            + len(add_text)
            > max_length
        ):
            chunks.append(
                current
            )

            current = line

        else:
            current += add_text

    if current:
        chunks.append(
            current
        )

    return chunks


# ==================================================
# 닉네임
# ==================================================

def get_base_name(
    member
):
    display_name = (
        member.display_name
        .strip()
    )

    for tag in [
        "[M]",
        "[R]",
        "[S]"
    ]:
        if display_name.startswith(
            tag
        ):
            display_name = (
                display_name[
                    len(tag):
                ]
                .strip()
            )

            break

    return (
        display_name
        .split("/")[0]
        .strip()
    )


def find_member_by_name(
    guild,
    name
):
    target_name = (
        name.strip()
        .lower()
    )

    exact_matches = []
    partial_matches = []

    for member in guild.members:
        if member.bot:
            continue

        base_name = (
            get_base_name(
                member
            )
            .lower()
        )

        if (
            target_name
            == base_name
        ):
            exact_matches.append(
                member
            )

        elif (
            target_name
            in base_name
        ):
            partial_matches.append(
                member
            )

    if len(exact_matches) == 1:
        return (
            exact_matches[0],
            None,
            []
        )

    if len(exact_matches) > 1:
        return (
            None,
            "duplicate",
            exact_matches
        )

    if len(partial_matches) == 1:
        return (
            partial_matches[0],
            None,
            []
        )

    if len(partial_matches) == 0:
        return (
            None,
            "not_found",
            []
        )

    return (
        None,
        "duplicate",
        partial_matches
    )


async def handle_search_error(
    channel,
    name,
    error,
    matches
):
    if error == "not_found":
        notice = await channel.send(
            f"⚠️ `{name}` 닉네임을 "
            f"찾을 수 없습니다."
        )

        await notice.delete(
            delay=5
        )

        return True

    if error == "duplicate":
        names = "\n".join(
            f"• {member.display_name}"
            for member
            in matches[:10]
        )

        notice = await channel.send(
            f"⚠️ `{name}`으로 여러 명이 "
            f"검색됐습니다.\n\n"
            f"{names}\n\n"
            f"조금 더 구체적으로 입력해주세요."
        )

        await notice.delete(
            delay=10
        )

        return True

    return False


# ==================================================
# 참여 중복
# ==================================================

def user_exists(
    user_id
):
    return (
        any(
            user["id"] == user_id
            for user in participants
        )
        or
        any(
            user["id"] == user_id
            for user in waiting
        )
    )


# ==================================================
# 참여 명단
# ==================================================

def make_participant_list():
    if current_part is None:
        return (
            "📋 **대내 모집이 "
            "시작되지 않았습니다.**"
        )

    lines = [
        f"🔥 **{current_part}부 대내**",
        "",
        "📋 **참여 명단**",
        ""
    ]

    if not participants:
        lines.append(
            "현재 참여자가 없습니다."
        )

    else:
        for i, user in enumerate(
            participants,
            1
        ):
            lines.append(
                f"{i}. {user['name']}"
            )

    if waiting:
        lines.extend([
            "",
            "⏳ **다음 부 대기**",
            ""
        ])

        for i, user in enumerate(
            waiting,
            1
        ):
            lines.append(
                f"{i}. {user['name']}"
            )

    return "\n".join(
        lines
    )
async def restore_participant_message():
    global participant_message

    if participant_message is not None:
        return

    if current_part is None:
        return

    channel_id = recruitment_state.get(
        "channel_id"
    )

    message_id = recruitment_state.get(
        "message_id"
    )

    if not channel_id or not message_id:
        return

    try:
        channel = bot.get_channel(
            int(channel_id)
        )

        if channel is None:
            channel = await bot.fetch_channel(
                int(channel_id)
            )

        participant_message = (
            await channel.fetch_message(
                int(message_id)
            )
        )

    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException,
        ValueError,
        TypeError
    ):
        participant_message = None


async def update_participant_message(
    channel
):
    global participant_message

    if participant_message is None:
        await restore_participant_message()

    text = make_participant_list()

    if participant_message:
        try:
            await participant_message.edit(
                content=text
            )

            save_recruitment_state(
                channel.guild
            )

            return

        except (
            discord.NotFound,
            discord.HTTPException
        ):
            participant_message = None

    participant_message = (
        await channel.send(
            text
        )
    )

    save_recruitment_state(
        channel.guild
    )


async def check_full_status(
    channel,
    announce_drop=True
):
    global full_notification_sent
    global recruitment_was_full

    count = len(
        participants
    )

    admin_mentions = (
        get_admin_mentions(
            channel.guild
        )
    )

    if (
        count == MAX_PARTICIPANTS
        and not full_notification_sent
    ):
        full_notification_sent = True
        recruitment_was_full = True

        save_recruitment_state(
            channel.guild
        )

        await channel.send(
            f"{admin_mentions}\n\n"
            f"✅ **{current_part}부 인원 모집 완료!**\n"
            f"집합 시간을 정해주세요.",
            allowed_mentions=discord.AllowedMentions(
                roles=True,
                users=False,
                everyone=False
            )
        )

    elif (
        count == MAX_PARTICIPANTS - 1
        and full_notification_sent
    ):
        full_notification_sent = False

        save_recruitment_state(
            channel.guild
        )

        if announce_drop:
            await channel.send(
                f"{admin_mentions}\n\n"
                f"⚠️ **{current_part}부 참여자 "
                f"한 명이 빠졌습니다.**\n"
                f"현재 인원: "
                f"**{count}/{MAX_PARTICIPANTS}명**",
                allowed_mentions=discord.AllowedMentions(
                    roles=True,
                    users=False,
                    everyone=False
                )
            )


# ==================================================
# 투표
# ==================================================

POLL_FILE = "poll_state.json"

POLL_R = "🇷"
POLL_S = "🇸"
POLL_M = "🇲"

poll_state = load_json_file(
    POLL_FILE,
    {}
)


def save_poll_state():
    save_json_file(
        POLL_FILE,
        poll_state
    )


def parse_poll_datetime(
    text
):
    formats = [
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y/%m/%d %H:%M"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(
                text,
                fmt
            )

        except ValueError:
            pass

    return None


def format_poll_datetime(
    dt
):
    korean_days = [
        "월",
        "화",
        "수",
        "목",
        "금",
        "토",
        "일"
    ]

    day_name = korean_days[
        dt.weekday()
    ]

    return (
        f"{dt.year}."
        f"{dt.month:02d}."
        f"{dt.day:02d}"
        f"({day_name}) "
        f"{dt.hour:02d}:"
        f"{dt.minute:02d}"
    )


def make_poll_embed(
    date_text
):
    return discord.Embed(
        description=(
            f"**{date_text} 참가자 명단**\n\n"
            f"라플 참가자 {POLL_R} / "
            f"스나 참가자 {POLL_S} / "
            f"멀티 참가자 {POLL_M}\n"
            f"체크 부탁드립니다\n\n"
            f"*인원제한 없습니다 "
            f"3항목중 하나만 선택해주세요*\n"
            f"용병을 제외한 나머지는 "
            f"본인 아이디로 참가하셔야 합니다.\n"
            f"세트 인원이 있을 시 이벤트 채널에 "
            f"세트인원 아이디 작성하여 남겨주세요!"
        ),
        color=discord.Color.red()
    )


# ==================================================
# 관리 날짜
# ==================================================

def parse_simple_date(
    text,
    reference_date=None,
    future=True
):
    if reference_date is None:
        reference_date = datetime.now(
            KST
        ).date()

    patterns = [
        (
            r"(?P<year>\d{4})[-./]"
            r"(?P<month>\d{1,2})[-./]"
            r"(?P<day>\d{1,2})"
        ),
        (
            r"(?P<year>\d{4})년\s*"
            r"(?P<month>\d{1,2})월\s*"
            r"(?P<day>\d{1,2})일?"
        ),
        (
            r"(?P<month>\d{1,2})[-./]"
            r"(?P<day>\d{1,2})"
        ),
        (
            r"(?P<month>\d{1,2})월\s*"
            r"(?P<day>\d{1,2})일?"
        )
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text
        )

        if not match:
            continue

        groups = (
            match.groupdict()
        )

        year_text = groups.get(
            "year"
        )

        year = (
            int(year_text)
            if year_text
            else reference_date.year
        )

        month = int(
            groups["month"]
        )

        day = int(
            groups["day"]
        )

        try:
            parsed = date(
                year,
                month,
                day
            )

        except ValueError:
            continue

        if not year_text:
            if future:
                if parsed < reference_date:
                    try:
                        parsed = date(
                            year + 1,
                            month,
                            day
                        )

                    except ValueError:
                        pass

            else:
                if parsed > reference_date:
                    try:
                        parsed = date(
                            year - 1,
                            month,
                            day
                        )

                    except ValueError:
                        pass

        return parsed

    return None


def get_reason_record(
    guild_id,
    user_id
):
    data = get_guild_management(
        guild_id
    )

    return data[
        "reasons"
    ].get(
        str(user_id)
    )


def is_reason_active(
    guild_id,
    user_id,
    target_date=None
):
    if target_date is None:
        target_date = datetime.now(
            KST
        ).date()

    record = get_reason_record(
        guild_id,
        user_id
    )

    if not record:
        return False

    if not record.get(
        "active",
        False
    ):
        return False

    expires = record.get(
        "expires"
    )

    if not expires:
        return True

    try:
        expires_date = (
            datetime.strptime(
                expires,
                "%Y-%m-%d"
            ).date()
        )

    except ValueError:
        return True

    return (
        target_date
        <= expires_date
    )


def cleanup_expired_reasons(
    guild_id
):
    data = get_guild_management(
        guild_id
    )

    changed = False

    today = datetime.now(
        KST
    ).date()

    for record in data[
        "reasons"
    ].values():
        if not record.get(
            "active",
            False
        ):
            continue

        expires = record.get(
            "expires"
        )

        if not expires:
            continue

        try:
            expires_date = (
                datetime.strptime(
                    expires,
                    "%Y-%m-%d"
                ).date()
            )

        except ValueError:
            continue

        if today > expires_date:
            record[
                "active"
            ] = False

            record[
                "closed_at"
            ] = today.isoformat()

            changed = True

    if changed:
        save_management()


# ==================================================
# 경고 기록
# ==================================================

def get_warning_record(
    guild_id,
    user_id
):
    data = get_guild_management(
        guild_id
    )

    user_key = str(
        user_id
    )

    if (
        user_key
        not in data["warnings"]
    ):
        data[
            "warnings"
        ][user_key] = {
            "count": 0,
            "events": [],
            "history": []
        }

    record = data[
        "warnings"
    ][user_key]

    record.setdefault(
        "count",
        0
    )

    record.setdefault(
        "events",
        []
    )

    record.setdefault(
        "history",
        []
    )

    return record


def add_warning_once(
    guild_id,
    user_id,
    event_key,
    reason
):
    record = get_warning_record(
        guild_id,
        user_id
    )

    if (
        event_key
        in record["events"]
    ):
        return False

    record[
        "events"
    ].append(
        event_key
    )

    record[
        "count"
    ] += 1

    record[
        "history"
    ].append({
        "event": event_key,
        "reason": reason,
        "date": datetime.now(
            KST
        ).date().isoformat()
    })

    save_management()

    return True


def get_warning_count(
    guild_id,
    user_id
):
    data = get_guild_management(
        guild_id
    )

    record = data[
        "warnings"
    ].get(
        str(user_id),
        {}
    )

    return int(
        record.get(
            "count",
            0
        )
    )


# ==================================================
# 관리 채널 가져오기
# ==================================================

def get_management_channel(
    guild
):
    data = get_guild_management(
        guild.id
    )

    channel_id = data.get(
        "management_channel_id"
    )

    if channel_id:
        channel = guild.get_channel(
            int(channel_id)
        )

        if channel is not None:
            return channel

    for channel in guild.text_channels:
        clean_name = (
            channel.name
            .replace(
                "📋",
                ""
            )
            .replace(
                "・",
                ""
            )
            .replace(
                "-",
                ""
            )
            .replace(
                "_",
                ""
            )
            .replace(
                " ",
                ""
            )
        )

        if (
            "관리현황"
            in clean_name
        ):
            return channel

    return None


def get_reason_channel(
    guild
):
    data = get_guild_management(
        guild.id
    )

    channel_id = data.get(
        "absence_reason_channel_id"
    )

    if channel_id:
        channel = guild.get_channel(
            int(channel_id)
        )

        if channel is not None:
            return channel

    for channel in guild.text_channels:
        clean_name = (
            channel.name
            .replace(
                "📝",
                ""
            )
            .replace(
                "・",
                ""
            )
            .replace(
                "-",
                ""
            )
            .replace(
                "_",
                ""
            )
            .replace(
                " ",
                ""
            )
        )

        if (
            "미접사유"
            in clean_name
        ):
            return channel

    return None


# ==================================================
# 미접 일수
# ==================================================

def get_inactive_days(
    record,
    target_date=None
):
    if target_date is None:
        target_date = datetime.now(
            KST
        ).date()

    if not record:
        return None

    if not record.get(
        "active",
        False
    ):
        return None

    last_seen = record.get(
        "last_seen"
    )

    if not last_seen:
        return None

    try:
        last_seen_date = (
            datetime.strptime(
                last_seen,
                "%Y-%m-%d"
            ).date()
        )

    except ValueError:
        return None

    return max(
        (
            target_date
            - last_seen_date
        ).days,
        0
    )


# ==================================================
# 미접 자동 판정
# ==================================================

async def process_inactivity(
    guild,
    send_alerts=True
):
    data = get_guild_management(
        guild.id
    )

    cleanup_expired_reasons(
        guild.id
    )

    clan_members = get_clan_members(
        guild
    )

    if clan_members is None:
        return

    clan_ids = {
        str(member.id)
        for member in clan_members
    }

    management_channel = (
        get_management_channel(
            guild
        )
    )

    today = datetime.now(
        KST
    ).date()

    alert_lines = []

    for user_id, record in list(
        data["inactivity"].items()
    ):
        if user_id not in clan_ids:
            continue

        if not record.get(
            "active",
            False
        ):
            continue

        try:
            member = guild.get_member(
                int(user_id)
            )

        except (
            ValueError,
            TypeError
        ):
            member = None

        if member is None:
            continue

        days = get_inactive_days(
            record,
            today
        )

        if days is None:
            continue

        if is_reason_active(
            guild.id,
            member.id,
            today
        ):
            continue

        last_seen = record.get(
            "last_seen"
        )

        if (
            days >= 7
            and not record.get(
                "warned_7",
                False
            )
        ):
            event_key = (
                f"inactive7:"
                f"{member.id}:"
                f"{last_seen}"
            )

            added = add_warning_once(
                guild.id,
                member.id,
                event_key,
                "미접사유 없이 7일 미접"
            )

            record[
                "warned_7"
            ] = True

            if added:
                warning_count = (
                    get_warning_count(
                        guild.id,
                        member.id
                    )
                )

                alert_lines.append(
                    f"⚠️ **{member.display_name}** — "
                    f"미접 {days}일 / "
                    f"경고 {warning_count}회"
                )

        if (
            days >= 10
            and not record.get(
                "expulsion_10",
                False
            )
        ):
            record[
                "expulsion_10"
            ] = True

            alert_lines.append(
                f"🚨 **{member.display_name}** — "
                f"미접 {days}일 / "
                f"제명 대상"
            )

    save_management()

    if (
        send_alerts
        and alert_lines
        and management_channel
    ):
        admin_mentions = (
            get_admin_mentions(
                guild
            )
        )

        await management_channel.send(
            f"{admin_mentions}\n\n"
            f"📋 **클랜 관리 자동 알림**\n\n"
            + "\n".join(
                alert_lines
            ),
            allowed_mentions=discord.AllowedMentions(
                roles=True,
                users=False,
                everyone=False
            )
        )


# ==================================================
# 주간 출석 최종 처리
# ==================================================

async def process_weekly_attendance(
    guild,
    target_date=None,
    send_report=True
):
    if target_date is None:
        target_date = datetime.now(
            KST
        ).date()

    (
        week_key,
        monday,
        sunday
    ) = get_week_info(
        target_date
    )

    data = get_guild_management(
        guild.id
    )

    if (
        week_key
        in data[
            "weekly_processed"
        ]
    ):
        return False

    clan_members = get_clan_members(
        guild
    )

    if clan_members is None:
        return False

    week_data = attendance_data.get(
        week_key,
        {}
    )

    attended_ids = set(
        week_data.keys()
    )

    warning_lines = []
    expulsion_lines = []
    exempt_lines = []

    for member in clan_members:
        user_id = str(
            member.id
        )

        if user_id in attended_ids:
            continue

        if is_reason_active(
            guild.id,
            member.id,
            sunday
        ):
            reason_record = (
                get_reason_record(
                    guild.id,
                    member.id
                )
            )

            expires = (
                reason_record.get(
                    "expires"
                )
                if reason_record
                else None
            )

            if expires:
                try:
                    expires_date = (
                        datetime.strptime(
                            expires,
                            "%Y-%m-%d"
                        ).date()
                    )

                    reason_text = (
                        f"{expires_date.month}/"
                        f"{expires_date.day}까지"
                    )

                except ValueError:
                    reason_text = (
                        "미접사유 등록"
                    )

            else:
                reason_text = (
                    "미접사유 등록 / "
                    "기간 확인 필요"
                )

            exempt_lines.append(
                f"• {member.display_name} — "
                f"{reason_text}"
            )

            continue

        event_key = (
            f"attendance:"
            f"{week_key}:"
            f"{member.id}"
        )

        added = add_warning_once(
            guild.id,
            member.id,
            event_key,
            (
                f"{monday.strftime('%Y.%m.%d')}~"
                f"{sunday.strftime('%Y.%m.%d')} "
                f"대내 미참여"
            )
        )

        warning_count = (
            get_warning_count(
                guild.id,
                member.id
            )
        )

        if warning_count >= 2:
            expulsion_lines.append(
                f"• {member.display_name} — "
                f"대내 미참여 / "
                f"경고 {warning_count}회"
            )

        elif added:
            warning_lines.append(
                f"• {member.display_name} — "
                f"이번 주 대내 미참여 / "
                f"경고 {warning_count}회"
            )

    data[
        "weekly_processed"
    ].append(
        week_key
    )

    save_management()

    if send_report:
        channel = get_management_channel(
            guild
        )

        if channel:
            lines = [
                "📋 **이번 주 클랜 관리 결과**",
                (
                    f"📅 "
                    f"{monday.strftime('%Y.%m.%d')} "
                    f"~ "
                    f"{sunday.strftime('%Y.%m.%d')}"
                ),
                ""
            ]

            if expulsion_lines:
                lines.append(
                    "🚨 **제명 대상**"
                )

                lines.extend(
                    expulsion_lines
                )

                lines.append(
                    ""
                )

            if warning_lines:
                lines.append(
                    "⚠️ **경고 대상**"
                )

                lines.extend(
                    warning_lines
                )

                lines.append(
                    ""
                )

            if exempt_lines:
                lines.append(
                    "📝 **미접사유 등록 / 제외**"
                )

                lines.extend(
                    exempt_lines
                )

                lines.append(
                    ""
                )

            if (
                not expulsion_lines
                and not warning_lines
                and not exempt_lines
            ):
                lines.append(
                    "✅ 이번 주 관리 대상자가 없습니다."
                )

            admin_mentions = (
                get_admin_mentions(
                    guild
                )
            )

            await channel.send(
                f"{admin_mentions}\n\n"
                + "\n".join(
                    lines
                ),
                allowed_mentions=discord.AllowedMentions(
                    roles=True,
                    users=False,
                    everyone=False
                )
            )

    return True
# ==================================================
# 관리현황
# 보기만 하며 경고 추가 안 함
# ==================================================

async def send_management_status(
    channel,
    guild
):
    cleanup_expired_reasons(
        guild.id
    )

    data = get_guild_management(
        guild.id
    )

    clan_members = get_clan_members(
        guild
    )

    if clan_members is None:
        await channel.send(
            f"⚠️ `{CLAN_ROLE_NAME}` 역할을 찾을 수 없습니다."
        )
        return

    (
        week_key,
        monday,
        sunday,
        week_data
    ) = get_current_attendance()

    attended_ids = set(
        week_data.keys()
    )

    today = datetime.now(
        KST
    ).date()

    expulsion_lines = []
    warning_lines = []
    reason_lines = []
    normal_count = 0

    for member in sorted(
        clan_members,
        key=lambda m: m.display_name.lower()
    ):
        user_id = str(
            member.id
        )

        warning_count = (
            get_warning_count(
                guild.id,
                member.id
            )
        )

        inactivity_record = (
            data["inactivity"].get(
                user_id
            )
        )

        inactive_days = (
            get_inactive_days(
                inactivity_record,
                today
            )
        )

        reason_record = (
            data["reasons"].get(
                user_id
            )
        )

        reason_active = (
            is_reason_active(
                guild.id,
                member.id,
                today
            )
        )

        if reason_active:
            expires = (
                reason_record.get(
                    "expires"
                )
                if reason_record
                else None
            )

            if expires:
                try:
                    expires_date = (
                        datetime.strptime(
                            expires,
                            "%Y-%m-%d"
                        ).date()
                    )

                    reason_lines.append(
                        f"• {member.display_name} — "
                        f"{expires_date.month}/"
                        f"{expires_date.day}까지"
                    )

                except ValueError:
                    reason_lines.append(
                        f"• {member.display_name} — "
                        f"기간 확인 필요"
                    )

            else:
                reason_lines.append(
                    f"• {member.display_name} — "
                    f"기간 확인 필요"
                )

            continue

        if (
            inactive_days is not None
            and inactive_days >= 10
        ):
            expulsion_lines.append(
                f"• {member.display_name} — "
                f"미접 {inactive_days}일 / "
                f"경고 {warning_count}회"
            )

            continue

        if warning_count >= 2:
            expulsion_lines.append(
                f"• {member.display_name} — "
                f"경고 {warning_count}회"
            )

            continue

        reasons = []

        if warning_count > 0:
            reasons.append(
                f"경고 {warning_count}회"
            )

        if (
            inactive_days is not None
            and inactive_days >= 7
        ):
            reasons.append(
                f"미접 {inactive_days}일"
            )

        if (
            user_id not in attended_ids
        ):
            reasons.append(
                "이번 주 대내 미참여"
            )

        if reasons:
            warning_lines.append(
                f"• {member.display_name} — "
                + " / ".join(
                    reasons
                )
            )

        else:
            normal_count += 1

    lines = [
        "📋 **전사 클랜 관리 현황**",
        (
            f"📅 "
            f"{monday.strftime('%Y.%m.%d')} "
            f"~ "
            f"{sunday.strftime('%Y.%m.%d')}"
        ),
        ""
    ]

    if expulsion_lines:
        lines.append(
            "🚨 **제명 대상**"
        )

        lines.extend(
            expulsion_lines
        )

        lines.append(
            ""
        )

    if warning_lines:
        lines.append(
            "⚠️ **확인 / 경고 현황**"
        )

        lines.extend(
            warning_lines
        )

        lines.append(
            ""
        )

    if reason_lines:
        lines.append(
            "📝 **미접사유 등록**"
        )

        lines.extend(
            reason_lines
        )

        lines.append(
            ""
        )

    lines.append(
        f"✅ **이상 없음: {normal_count}명**"
    )

    chunks = split_lines(
        lines
    )

    for chunk in chunks:
        await channel.send(
            chunk
        )


# ==================================================
# 자동 관리 루프
# ==================================================

@tasks.loop(
    minutes=10
)
async def management_loop():
    now = datetime.now(
        KST
    )

    for guild in bot.guilds:
        try:
            await process_inactivity(
                guild,
                send_alerts=True
            )

            if (
                now.weekday() == 6
                and (
                    now.hour > 23
                    or (
                        now.hour == 23
                        and now.minute >= 0
                    )
                )
            ):
                await process_weekly_attendance(
                    guild,
                    now.date(),
                    send_report=True
                )

            if now.weekday() == 0:
                yesterday = (
                    now.date()
                    - timedelta(
                        days=1
                    )
                )

                previous_week_key, _, _ = (
                    get_week_info(
                        yesterday
                    )
                )

                data = (
                    get_guild_management(
                        guild.id
                    )
                )

                if (
                    previous_week_key
                    not in data[
                        "weekly_processed"
                    ]
                ):
                    await process_weekly_attendance(
                        guild,
                        yesterday,
                        send_report=True
                    )

        except Exception as e:
            print(
                f"관리 자동 처리 오류 "
                f"({guild.name}): {e}"
            )


@management_loop.before_loop
async def before_management_loop():
    await bot.wait_until_ready()


# ==================================================
# 사다리 입력창
# ==================================================

class LadderInputModal(
    discord.ui.Modal
):
    def __init__(
        self,
        ladder_view,
        side
    ):
        if side == "left":
            title = "왼쪽 항목 입력"

        else:
            title = "오른쪽 항목 입력"

        super().__init__(
            title=title
        )

        self.ladder_view = (
            ladder_view
        )

        self.side = side

        self.items = (
            discord.ui.TextInput(
                label="한 줄에 하나씩 입력해주세요",
                style=discord.TextStyle.paragraph,
                placeholder=(
                    "예:\n"
                    "치\n"
                    "또치\n"
                    "둘리\n"
                    "도우너"
                ),
                required=True,
                max_length=1000
            )
        )

        self.add_item(
            self.items
        )

    async def on_submit(
        self,
        interaction
    ):
        if not is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "❌ 운영진만 사용할 수 있습니다.",
                ephemeral=True
            )

            return

        values = [
            item.strip()
            for item
            in self.items.value.split(
                "\n"
            )
            if item.strip()
        ]

        if len(values) < 2:
            await interaction.response.send_message(
                "⚠️ 최소 2개 이상 입력해주세요.",
                ephemeral=True
            )

            return

        if self.side == "left":
            self.ladder_view.left_items = (
                values
            )

        else:
            self.ladder_view.right_items = (
                values
            )

        await interaction.response.send_message(
            f"✅ {len(values)}개 항목이 저장되었습니다.",
            ephemeral=True
        )


# ==================================================
# 사다리 버튼
# ==================================================

class LadderView(
    discord.ui.View
):
    def __init__(self):
        super().__init__(
            timeout=300
        )

        self.left_items = []
        self.right_items = []

    async def check_admin(
        self,
        interaction
    ):
        if not is_admin(
            interaction.user
        ):
            await interaction.response.send_message(
                "❌ 운영진만 사다리 기능을 사용할 수 있습니다.",
                ephemeral=True
            )

            return False

        return True

    @discord.ui.button(
        label="왼쪽 항목 입력",
        style=discord.ButtonStyle.secondary,
        emoji="⬅️"
    )
    async def left_button(
        self,
        interaction,
        button
    ):
        if not await self.check_admin(
            interaction
        ):
            return

        await interaction.response.send_modal(
            LadderInputModal(
                self,
                "left"
            )
        )

    @discord.ui.button(
        label="오른쪽 항목 입력",
        style=discord.ButtonStyle.secondary,
        emoji="➡️"
    )
    async def right_button(
        self,
        interaction,
        button
    ):
        if not await self.check_admin(
            interaction
        ):
            return

        await interaction.response.send_modal(
            LadderInputModal(
                self,
                "right"
            )
        )

    @discord.ui.button(
        label="사다리 타기",
        style=discord.ButtonStyle.success,
        emoji="🪜"
    )
    async def run_button(
        self,
        interaction,
        button
    ):
        if not await self.check_admin(
            interaction
        ):
            return

        if (
            not self.left_items
            or not self.right_items
        ):
            await interaction.response.send_message(
                "⚠️ 왼쪽과 오른쪽 항목을 먼저 입력해주세요.",
                ephemeral=True
            )

            return

        if (
            len(self.left_items)
            != len(self.right_items)
        ):
            await interaction.response.send_message(
                f"⚠️ 항목 개수가 다릅니다.\n"
                f"왼쪽: {len(self.left_items)}개\n"
                f"오른쪽: {len(self.right_items)}개",
                ephemeral=True
            )

            return

        results = (
            self.right_items.copy()
        )

        random.shuffle(
            results
        )

        result_lines = []

        for left, right in zip(
            self.left_items,
            results
        ):
            result_lines.append(
                f"**{left}** → **{right}**"
            )

        embed = discord.Embed(
            title="🪜 사다리타기 결과",
            description="\n".join(
                result_lines
            ),
            color=discord.Color.red()
        )

        await interaction.response.send_message(
            embed=embed
        )


# ==================================================
# 봇 시작
# ==================================================

@bot.event
async def on_ready():
    await restore_participant_message()

    if not management_loop.is_running():
        management_loop.start()

    # ----------------------------------------------
    # 클랜원 역할 버튼 영구 등록
    # ----------------------------------------------
    #
    # timeout=None + custom_id를 사용하는 버튼은
    # 봇이 재시작될 때 다시 View를 등록해야
    # 기존 메시지의 버튼이 계속 작동함.
    #
    bot.add_view(
        ClanRoleView()
    )

    # 역할받기 버튼은 전사 서버에서만 준비
    guild = bot.get_guild(
        GUILD_ID
    )

    if guild is None:
        print(
            "전사 서버를 찾을 수 없습니다."
        )
    else:
        try:
            await send_clan_role_button(
                guild
            )

        except Exception as e:
            print(
                f"{guild.name}: "
                f"클랜원 역할 버튼 준비 오류: {e}"
            )

    print(
        f"{bot.user} 로그인 완료!"
    )

    if current_part is not None:
        print(
            f"{current_part}부 모집 상태 복구 완료 "
            f"({len(participants)}/"
            f"{MAX_PARTICIPANTS}명)"
        )


# ==================================================
# 투표 1인 1개
# ==================================================

@bot.event
async def on_raw_reaction_add(
    payload
):
    if bot.user is None:
        return

    if payload.user_id == bot.user.id:
        return

    if not poll_state:
        return

    try:
        poll_message_id = int(
            poll_state.get(
                "message_id",
                0
            )
        )

    except (
        ValueError,
        TypeError
    ):
        return

    if (
        payload.message_id
        != poll_message_id
    ):
        return

    emoji = str(
        payload.emoji
    )

    valid_emojis = [
        POLL_R,
        POLL_S,
        POLL_M
    ]

    if emoji not in valid_emojis:
        return

    guild = bot.get_guild(
        payload.guild_id
    )

    if guild is None:
        return

    member = payload.member

    if member is None:
        try:
            member = (
                await guild.fetch_member(
                    payload.user_id
                )
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            return

    channel = guild.get_channel(
        payload.channel_id
    )

    if channel is None:
        try:
            channel = (
                await bot.fetch_channel(
                    payload.channel_id
                )
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            return

    try:
        poll_message = (
            await channel.fetch_message(
                payload.message_id
            )
        )

    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException
    ):
        return

    for other_emoji in valid_emojis:
        if other_emoji == emoji:
            continue

        try:
            await poll_message.remove_reaction(
                other_emoji,
                member
            )

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            pass


# ==================================================
# 메시지 명령어
# ==================================================

@bot.event
async def on_message(
    message
):
    global participants
    global waiting
    global participant_message
    global current_part
    global full_notification_sent
    global recruitment_was_full
    global poll_state
    global attendance_data

    if message.author.bot:
        return

    if not message.guild:
        return

    content = (
        message.content
        .strip()
    )

    # ==================================================
    # 용병 자동 등록
    # ==================================================
    #
    # ✅ㅣ용병-등록 채널에서는
    # 일반 명령어보다 먼저 용병 등록을 처리함.
    #
    # 입력:
    # 감자 / 용병 / 치
    #
    # 또는:
    # 감자/용병/치
    #
    # 성공 시:
    # 1. 감자/용병/치 로 닉네임 변경
    # 2. 용병 역할 지급
    # 3. 작성한 메시지 삭제
    #
    if (
        message.channel.id
        == MERCENARY_REGISTER_CHANNEL_ID
    ):
        handled = (
            await handle_mercenary_registration(
                message
            )
        )

        if handled:
            return
    guild_manage = (
        get_guild_management(
            message.guild.id
        )
    )

    # ==================================================
    # 미접사유 채널 자동 저장
    # ==================================================

    reason_channel = (
        get_reason_channel(
            message.guild
        )
    )

    if (
        reason_channel is not None
        and message.channel.id
        == reason_channel.id
        and content
        and content not in [
            "미접사유채널설정",
            "도움"
        ]
    ):
        clan_members = (
            get_clan_members(
                message.guild
            )
        )

        if (
            clan_members is not None
            and message.author
            in clan_members
        ):
            expires_date = (
                parse_simple_date(
                    content,
                    future=True
                )
            )

            guild_manage[
                "reasons"
            ][str(message.author.id)] = {
                "text": content,
                "expires": (
                    expires_date.isoformat()
                    if expires_date
                    else None
                ),
                "active": True,
                "message_id": message.id,
                "created_at": datetime.now(
                    KST
                ).isoformat()
            }

            save_management()

            if expires_date:
                notice = (
                    await message.channel.send(
                        f"✅ "
                        f"{message.author.display_name}님의 "
                        f"미접사유가 등록되었습니다.\n"
                        f"📅 **{expires_date.month}/"
                        f"{expires_date.day}까지** "
                        f"관리 대상에서 제외됩니다."
                    )
                )

            else:
                notice = (
                    await message.channel.send(
                        f"✅ "
                        f"{message.author.display_name}님의 "
                        f"미접사유가 등록되었습니다.\n"
                        f"⚠️ 종료 날짜가 없어 "
                        f"운영진 확인 전까지 "
                        f"경고 판정을 보류합니다."
                    )
                )

            await notice.delete(
                delay=8
            )

            return


    # ==================================================
    # 도움
    # ==================================================

    if content == "도움":
        embed = discord.Embed(
            title="📌 전사봇 명령어",
            description=(
                "필요한 명령어를 채팅에 "
                "그대로 입력해주세요."
            ),
            color=discord.Color.red()
        )

        embed.add_field(
            name="👥 참여자 명령어",
            value=(
                "`참여` / `참가`\n"
                "→ 현재 대내 참여\n\n"
                "`취소`\n"
                "→ 본인 참여 취소"
            ),
            inline=False
        )

        embed.add_field(
            name="🛠️ 운영진 · 모집",
            value=(
                "`1부` / `2부` / `3부`\n"
                "→ 해당 부 모집 시작\n"
                "→ 이전 부 명단은 그대로 유지\n\n"
                "`추가 닉네임`\n"
                "→ 인원을 현재 부에 직접 추가\n\n"
                "`불참 닉네임`\n"
                "→ 인원을 현재 명단에서 제외\n\n"
                "`집합 20:30`\n"
                "→ 현재 부 참여자 호출 + 집합 안내"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 운영진 · 출석",
            value=(
                "`출석`\n"
                "→ 현재 진행 중인 부를 출석 저장\n\n"
                "`출석 1부` / `출석 2부`\n"
                "→ 지나간 부의 최종 명단을 "
                "불러와 출석 저장\n\n"
                "`미참여`\n"
                "→ 이번 주 대내 미참여 "
                "클랜원 확인\n\n"
                "`주간출석`\n"
                "→ 이번 주 전체 참여 / "
                "미참여 현황 확인\n\n"
                "※ `출석`을 입력해도 "
                "바로 경고가 생기지 않습니다."
            ),
            inline=False
        )

        embed.add_field(
            name="📋 운영진 · 클랜 관리",
            value=(
                "`관리채널설정`\n"
                "→ 현재 채널을 관리현황/"
                "자동알림 채널로 저장\n\n"
                "`미접사유채널설정`\n"
                "→ 현재 채널을 미접사유 "
                "채널로 저장\n\n"
                "`관리현황`\n"
                "→ 현재 관리 상태 확인\n"
                "→ 확인만 하며 경고가 "
                "추가되지 않음\n\n"
                "`미접 치 9/7`\n"
                "→ 마지막 접속일 등록\n\n"
                "`복귀 치`\n"
                "→ 미접 상태 종료"
            ),
            inline=False
        )

        embed.add_field(
            name="📝 운영진 · 미접사유 관리",
            value=(
                "`사유설정 치 9/20`\n"
                "→ 미접사유 종료 날짜 직접 설정\n\n"
                "`사유종료 치`\n"
                "→ 등록된 미접사유 종료\n\n"
                "클랜원이 설정된 미접사유 채널에 "
                "자유롭게 글을 쓰면 자동 저장됩니다."
            ),
            inline=False
        )

        embed.add_field(
            name="⚠️ 경고 / 제명 기준",
            value=(
                "• 주 1회 대내 미참여 + "
                "미접사유 없음\n"
                "→ 경고 1회\n\n"
                "• 경고 총 2회 이상\n"
                "→ 제명 대상\n\n"
                "• 미접사유 없이 7일 미접\n"
                "→ 경고 1회\n\n"
                "• 미접사유 없이 10일 미접\n"
                "→ 바로 제명 대상\n\n"
                "• 유효한 미접사유 기간에는 "
                "대내/미접 판정에서 제외"
            ),
            inline=False
        )

        embed.add_field(
            name="⏰ 자동 관리",
            value=(
                "• 매주 일요일 23:00 이후 최종 집계\n"
                "• 일요일에 봇이 꺼져 있었다면 "
                "월요일 실행 시 전 주 자동 처리\n"
                "• 같은 주간 미참여로 경고 중복 없음\n"
                "• 같은 미접 기록으로 "
                "7일 경고 중복 없음\n"
                "• 미접 7일 / 10일 자동 확인"
            ),
            inline=False
        )

        embed.add_field(
            name="🎮 운영진 · 기타",
            value=(
                "`사다리`\n"
                "→ 사다리타기 실행\n\n"
                "`대내투표 2026-10-03 22:30`\n"
                "→ 라플 / 스나 / 멀티 투표 생성\n\n"
                "`투표수정 2026-10-03 23:00`\n"
                "→ 기존 투표 시간 수정\n\n"
                "`투표초기화`\n"
                "→ 기존 투표 참여 기록 초기화\n\n"
                "`클린`\n"
                "→ 현재 채널 및 모집 초기화\n"
                "→ 출석/관리 기록은 유지"
            ),
            inline=False
        )

        embed.add_field(
            name="⏳ 대내 자동 기능",
            value=(
                "• 1~12번은 현재 부 참여\n"
                "• 13번부터 다음 부 대기\n"
                "• 다음 부 시작 시 대기자 자동 이동\n"
                "• 12명 모집 완료 시 "
                "운영진 자동 알림\n"
                "• 이전 부 명단은 그대로 유지\n"
                "• 각 부 최종 명단 자동 저장\n"
                "• 봇 재시작 후 "
                "모집/대기/출석 기록 유지"
            ),
            inline=False
        )

        embed.add_field(
    name="🪖 용병 / 클랜원 자동 역할",
    value=(
        "`✅ㅣ용병-등록`\n"
        "→ `본인닉네임 / 용병 / 지인닉네임` "
        "형식으로 입력\n"
        "→ 닉네임 변경 + 용병 역할 자동 지급\n\n"
        "`✅ㅣ역할받기`\n"
        "→ 본인인증 및 가입 완료 후 "
        "`클랜원 역할 받기` 버튼 사용\n"
        "→ 용병 역할이 있다면 자동 제거 후 "
        "클랜원 역할 지급"
    ),
    inline=False
)

        await message.channel.send(
            embed=embed
        )

        return
    # ==================================================
    # 관리채널설정
    # ==================================================

    if content == "관리채널설정":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 설정할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        guild_manage[
            "management_channel_id"
        ] = message.channel.id

        save_management()

        await message.channel.send(
            "✅ 이 채널을 "
            "**관리현황 / 자동 경고 알림 채널**로 설정했습니다."
        )

        return

    # ==================================================
    # 미접사유채널설정
    # ==================================================

    if content == "미접사유채널설정":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 설정할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        guild_manage[
            "absence_reason_channel_id"
        ] = message.channel.id

        save_management()

        await message.channel.send(
            "✅ 이 채널을 **미접사유 채널**로 설정했습니다.\n"
            "이제 클랜원이 이 채널에 사유를 적으면 "
            "자동 저장됩니다."
        )

        return

    # ==================================================
    # 관리현황
    # ==================================================

    if content == "관리현황":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 확인할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        await send_management_status(
            message.channel,
            message.guild
        )

        return

    # ==================================================
    # 미접 닉네임 날짜
    # ==================================================

    if content.startswith(
        "미접 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        rest = content[
            len("미접 "):
        ].strip()

        last_space = rest.rfind(
            " "
        )

        if last_space == -1:
            notice = await message.channel.send(
                "⚠️ 이렇게 입력해주세요.\n"
                "`미접 치 9/7`"
            )

            await notice.delete(
                delay=5
            )

            return

        name = rest[
            :last_space
        ].strip()

        date_text = rest[
            last_space + 1:
        ].strip()

        parsed_date = parse_simple_date(
            date_text,
            future=False
        )

        if not parsed_date:
            notice = await message.channel.send(
                "⚠️ 날짜를 확인할 수 없습니다.\n"
                "예: `미접 치 9/7`"
            )

            await notice.delete(
                delay=5
            )

            return

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
        )

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        guild_manage[
            "inactivity"
        ][str(target.id)] = {
            "last_seen": parsed_date.isoformat(),
            "active": True,
            "warned_7": False,
            "expulsion_10": False,
            "updated_at": datetime.now(
                KST
            ).isoformat()
        }

        save_management()

        days = max(
            (
                datetime.now(
                    KST
                ).date()
                - parsed_date
            ).days,
            0
        )

        await message.channel.send(
            f"✅ **{target.display_name}** 미접 기록 저장\n"
            f"마지막 접속일: "
            f"**{parsed_date.strftime('%Y.%m.%d')}**\n"
            f"현재 미접: **{days}일**"
        )

        await process_inactivity(
            message.guild,
            send_alerts=True
        )

        return

    # ==================================================
    # 복귀 닉네임
    # ==================================================

    if content.startswith(
        "복귀 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        name = content[
            len("복귀 "):
        ].strip()

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
        )

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        record = guild_manage[
            "inactivity"
        ].get(
            str(target.id)
        )

        if not record:
            notice = await message.channel.send(
                f"⚠️ {target.display_name}님의 "
                f"미접 기록이 없습니다."
            )

            await notice.delete(
                delay=4
            )

            return

        record[
            "active"
        ] = False

        record[
            "returned_at"
        ] = (
            datetime.now(
                KST
            ).date().isoformat()
        )

        save_management()

        await message.channel.send(
            f"✅ **{target.display_name}** 복귀 처리 완료!\n"
            f"기존 경고 기록은 유지됩니다."
        )

        return

    # ==================================================
    # 사유설정 닉네임 날짜
    # ==================================================

    if content.startswith(
        "사유설정 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        rest = content[
            len("사유설정 "):
        ].strip()

        last_space = rest.rfind(
            " "
        )

        if last_space == -1:
            notice = await message.channel.send(
                "⚠️ 이렇게 입력해주세요.\n"
                "`사유설정 치 9/20`"
            )

            await notice.delete(
                delay=5
            )

            return

        name = rest[
            :last_space
        ].strip()

        date_text = rest[
            last_space + 1:
        ].strip()

        parsed_date = parse_simple_date(
            date_text,
            future=True
        )

        if not parsed_date:
            notice = await message.channel.send(
                "⚠️ 날짜를 확인할 수 없습니다.\n"
                "예: `사유설정 치 9/20`"
            )

            await notice.delete(
                delay=5
            )

            return

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
        )

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        old_record = guild_manage[
            "reasons"
        ].get(
            str(target.id),
            {}
        )

        guild_manage[
            "reasons"
        ][str(target.id)] = {
            "text": old_record.get(
                "text",
                "운영진 수동 설정"
            ),
            "expires": (
                parsed_date.isoformat()
            ),
            "active": True,
            "message_id": old_record.get(
                "message_id"
            ),
            "created_at": old_record.get(
                "created_at",
                datetime.now(
                    KST
                ).isoformat()
            ),
            "updated_at": datetime.now(
                KST
            ).isoformat()
        }

        save_management()

        await message.channel.send(
            f"✅ **{target.display_name}** "
            f"미접사유 기간 설정 완료\n"
            f"📅 **{parsed_date.month}/"
            f"{parsed_date.day}까지**"
        )

        return

    # ==================================================
    # 사유종료 닉네임
    # ==================================================

    if content.startswith(
        "사유종료 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        name = content[
            len("사유종료 "):
        ].strip()

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
        )

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        reason_record = guild_manage[
            "reasons"
        ].get(
            str(target.id)
        )

        if not reason_record:
            notice = await message.channel.send(
                f"⚠️ {target.display_name}님의 "
                f"미접사유 기록이 없습니다."
            )

            await notice.delete(
                delay=4
            )

            return

        reason_record[
            "active"
        ] = False

        reason_record[
            "closed_at"
        ] = (
            datetime.now(
                KST
            ).date().isoformat()
        )

        save_management()

        await message.channel.send(
            f"✅ **{target.display_name}** "
            f"미접사유를 종료했습니다."
        )

        return

    # ==================================================
    # 출석 / 출석 1부 / 출석 2부
    # ==================================================

    if (
        content == "출석"
        or content.startswith(
            "출석 "
        )
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영자 / 부마스터 / "
                "마스터만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        requested_part = None

        if content != "출석":
            requested_part = (
                content[
                    len("출석 "):
                ].strip()
            )

            if requested_part.endswith(
                "부"
            ):
                requested_part = (
                    requested_part[:-1]
                    .strip()
                )

            if not requested_part.isdigit():
                notice = await message.channel.send(
                    "⚠️ 이렇게 입력해주세요.\n"
                    "`출석`\n"
                    "`출석 1부`\n"
                    "`출석 2부`"
                )

                await notice.delete(
                    delay=5
                )

                return

        if requested_part is None:
            if current_part is None:
                notice = await message.channel.send(
                    "⚠️ 현재 진행 중인 대내가 없습니다."
                )

                await notice.delete(
                    delay=4
                )

                return

            target_part = (
                current_part
            )

            target_users = (
                participants.copy()
            )

        else:
            target_part = (
                requested_part
            )

            if (
                target_part
                == current_part
            ):
                target_users = (
                    participants.copy()
                )

            else:
                target_users = (
                    get_saved_part_history(
                        message.guild,
                        target_part
                    )
                )

            if target_users is None:
                notice = await message.channel.send(
                    f"⚠️ **{target_part}부 명단을 "
                    f"찾을 수 없습니다.**\n"
                    f"이번 주에 저장된 "
                    f"{target_part}부 명단이 없습니다."
                )

                await notice.delete(
                    delay=6
                )

                return

        if not target_users:
            notice = await message.channel.send(
                f"⚠️ {target_part}부 참여자가 없습니다."
            )

            await notice.delete(
                delay=4
            )

            return

        week_key, monday, sunday = (
            get_week_info()
        )

        if (
            week_key
            not in attendance_data
        ):
            attendance_data[
                week_key
            ] = {}

        new_count = 0

        for user in target_users:
            user_id = str(
                user["id"]
            )

            if (
                user_id
                not in attendance_data[
                    week_key
                ]
            ):
                new_count += 1

            attendance_data[
                week_key
            ][user_id] = (
                user["name"]
            )

        save_attendance()

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        notice = await message.channel.send(
            f"✅ **{target_part}부 출석 저장 완료!**\n"
            f"출석 처리 인원: "
            f"**{len(target_users)}명**\n"
            f"이번 주 새로 출석 처리된 인원: "
            f"**{new_count}명**"
        )

        await notice.delete(
            delay=7
        )

        return

    # ==================================================
    # 미참여
    # ==================================================

    if content == "미참여":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영자 / 부마스터 / "
                "마스터만 확인할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        clan_members = get_clan_members(
            message.guild
        )

        if clan_members is None:
            await message.channel.send(
                f"⚠️ `{CLAN_ROLE_NAME}` 역할을 "
                f"찾을 수 없습니다."
            )

            return

        (
            week_key,
            monday,
            sunday,
            week_data
        ) = get_current_attendance()

        attended_ids = set(
            week_data.keys()
        )

        absent_members = [
            member
            for member in clan_members
            if str(
                member.id
            ) not in attended_ids
        ]

        absent_members.sort(
            key=lambda m:
            m.display_name.lower()
        )

        header = (
            f"⚠️ **이번 주 대내 미참여자**\n"
            f"📅 {monday.strftime('%Y.%m.%d')} "
            f"~ {sunday.strftime('%Y.%m.%d')}\n\n"
        )

        if not absent_members:
            await message.channel.send(
                header
                + "✅ 클랜원 전원이 이번 주 "
                "대내에 참여했습니다!"
            )

            return

        lines = [
            f"{i}. {member.display_name}"
            for i, member
            in enumerate(
                absent_members,
                1
            )
        ]

        chunks = split_lines(
            lines
        )

        for index, chunk in enumerate(
            chunks
        ):
            if index == 0:
                await message.channel.send(
                    header
                    + chunk
                    + f"\n\n❌ 미참여: "
                    f"**{len(absent_members)}명**"
                )

            else:
                await message.channel.send(
                    chunk
                )

        return

    # ==================================================
    # 주간출석
    # ==================================================

    if content == "주간출석":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영자 / 부마스터 / "
                "마스터만 확인할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        clan_members = get_clan_members(
            message.guild
        )

        if clan_members is None:
            await message.channel.send(
                f"⚠️ `{CLAN_ROLE_NAME}` 역할을 "
                f"찾을 수 없습니다."
            )

            return

        (
            week_key,
            monday,
            sunday,
            week_data
        ) = get_current_attendance()

        attended_ids = set(
            week_data.keys()
        )

        attended_members = []
        absent_members = []

        for member in clan_members:
            if (
                str(member.id)
                in attended_ids
            ):
                attended_members.append(
                    member
                )

            else:
                absent_members.append(
                    member
                )

        attended_members.sort(
            key=lambda m:
            m.display_name.lower()
        )

        absent_members.sort(
            key=lambda m:
            m.display_name.lower()
        )

        embed = discord.Embed(
            title="📊 이번 주 대내 출석 현황",
            description=(
                f"📅 "
                f"{monday.strftime('%Y.%m.%d')} "
                f"~ "
                f"{sunday.strftime('%Y.%m.%d')}\n\n"
                f"👥 클랜원: "
                f"**{len(clan_members)}명**\n"
                f"✅ 참여 완료: "
                f"**{len(attended_members)}명**\n"
                f"❌ 미참여: "
                f"**{len(absent_members)}명**"
            ),
            color=discord.Color.red()
        )

        await message.channel.send(
            embed=embed
        )

        if attended_members:
            attended_lines = [
                f"{i}. {member.display_name}"
                for i, member
                in enumerate(
                    attended_members,
                    1
                )
            ]

            for index, chunk in enumerate(
                split_lines(
                    attended_lines
                )
            ):
                title = (
                    "✅ **이번 주 참여 완료**\n\n"
                    if index == 0
                    else ""
                )

                await message.channel.send(
                    title + chunk
                )

        if absent_members:
            absent_lines = [
                f"{i}. {member.display_name}"
                for i, member
                in enumerate(
                    absent_members,
                    1
                )
            ]

            for index, chunk in enumerate(
                split_lines(
                    absent_lines
                )
            ):
                title = (
                    "❌ **이번 주 미참여**\n\n"
                    if index == 0
                    else ""
                )

                await message.channel.send(
                    title + chunk
                )

        return
    # ==================================================
    # 대내투표
    # ==================================================

    if content.startswith(
        "대내투표 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 투표를 생성할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        date_input = (
            content[
                len("대내투표 "):
            ].strip()
        )

        poll_datetime = (
            parse_poll_datetime(
                date_input
            )
        )

        if poll_datetime is None:
            notice = await message.channel.send(
                "⚠️ 날짜와 시간을 이렇게 입력해주세요.\n"
                "`대내투표 2026-10-03 22:30`"
            )

            await notice.delete(
                delay=7
            )

            return

        date_text = (
            format_poll_datetime(
                poll_datetime
            )
        )

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        poll_message = (
            await message.channel.send(
                embed=make_poll_embed(
                    date_text
                )
            )
        )

        await poll_message.add_reaction(
            POLL_R
        )

        await poll_message.add_reaction(
            POLL_S
        )

        await poll_message.add_reaction(
            POLL_M
        )

        poll_state = {
            "guild_id":
                message.guild.id,
            "channel_id":
                message.channel.id,
            "message_id":
                poll_message.id,
            "date":
                poll_datetime.strftime(
                    "%Y-%m-%d %H:%M"
                )
        }

        save_poll_state()

        return

    # ==================================================
    # 투표수정
    # ==================================================

    if content.startswith(
        "투표수정 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 투표를 수정할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        if not poll_state:
            notice = await message.channel.send(
                "⚠️ 수정할 대내투표가 없습니다."
            )

            await notice.delete(
                delay=5
            )

            return

        date_input = (
            content[
                len("투표수정 "):
            ].strip()
        )

        poll_datetime = (
            parse_poll_datetime(
                date_input
            )
        )

        if poll_datetime is None:
            notice = await message.channel.send(
                "⚠️ 이렇게 입력해주세요.\n"
                "`투표수정 2026-10-03 23:00`"
            )

            await notice.delete(
                delay=7
            )

            return

        try:
            channel_id = int(
                poll_state[
                    "channel_id"
                ]
            )

            message_id = int(
                poll_state[
                    "message_id"
                ]
            )

            poll_channel = (
                bot.get_channel(
                    channel_id
                )
            )

            if poll_channel is None:
                poll_channel = (
                    await bot.fetch_channel(
                        channel_id
                    )
                )

            poll_message = (
                await poll_channel.fetch_message(
                    message_id
                )
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
            ValueError,
            TypeError,
            KeyError
        ):
            notice = await message.channel.send(
                "⚠️ 기존 투표 메시지를 찾을 수 없습니다."
            )

            await notice.delete(
                delay=5
            )

            return

        date_text = (
            format_poll_datetime(
                poll_datetime
            )
        )

        await poll_message.edit(
            embed=make_poll_embed(
                date_text
            )
        )

        poll_state[
            "date"
        ] = poll_datetime.strftime(
            "%Y-%m-%d %H:%M"
        )

        save_poll_state()

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        notice = await message.channel.send(
            "✅ 투표 날짜와 시간을 수정했습니다."
        )

        await notice.delete(
            delay=3
        )

        return

    # ==================================================
    # 투표초기화
    # ==================================================

    if content == "투표초기화":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 투표를 초기화할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        if not poll_state:
            notice = await message.channel.send(
                "⚠️ 초기화할 투표가 없습니다."
            )

            await notice.delete(
                delay=5
            )

            return

        try:
            channel_id = int(
                poll_state[
                    "channel_id"
                ]
            )

            message_id = int(
                poll_state[
                    "message_id"
                ]
            )

            poll_channel = (
                bot.get_channel(
                    channel_id
                )
            )

            if poll_channel is None:
                poll_channel = (
                    await bot.fetch_channel(
                        channel_id
                    )
                )

            poll_message = (
                await poll_channel.fetch_message(
                    message_id
                )
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
            ValueError,
            TypeError,
            KeyError
        ):
            notice = await message.channel.send(
                "⚠️ 기존 투표 메시지를 찾을 수 없습니다."
            )

            await notice.delete(
                delay=5
            )

            return

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        try:
            await poll_message.clear_reactions()

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            notice = await message.channel.send(
                "⚠️ 반응을 삭제하지 못했습니다.\n"
                "봇의 메시지 관리 권한을 확인해주세요."
            )

            await notice.delete(
                delay=5
            )

            return

        await poll_message.add_reaction(
            POLL_R
        )

        await poll_message.add_reaction(
            POLL_S
        )

        await poll_message.add_reaction(
            POLL_M
        )

        notice = await message.channel.send(
            "✅ 투표가 초기화되었습니다."
        )

        await notice.delete(
            delay=5
        )

        return

    # ==================================================
    # 사다리
    # ==================================================

    if content == "사다리":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사다리 기능을 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        embed = discord.Embed(
            title="🪜 사다리타기",
            description=(
                "왼쪽과 오른쪽 항목을 각각 입력한 뒤\n"
                "**사다리 타기** 버튼을 눌러주세요.\n\n"
                "※ 각 항목은 한 줄에 하나씩 입력"
            ),
            color=discord.Color.red()
        )

        await message.channel.send(
            embed=embed,
            view=LadderView()
        )

        return

    # ==================================================
    # 1부 / 2부 / 3부 ...
    # ==================================================

    if content.endswith(
        "부"
    ):
        part_text = (
            content[:-1]
            .strip()
        )

        if part_text.isdigit():
            if not is_admin(
                message.author
            ):
                try:
                    await message.delete()

                except (
                    discord.Forbidden,
                    discord.NotFound,
                    discord.HTTPException
                ):
                    pass

                notice = await message.channel.send(
                    "❌ 운영진만 대내 모집을 "
                    "시작할 수 있습니다."
                )

                await notice.delete(
                    delay=3
                )

                return

            # 현재 부가 있다면
            # 다음 부로 넘어가기 전에 최종 명단 저장
            if current_part is not None:
                save_current_part_history(
                    message.guild
                )

            current_part = (
                part_text
            )

            full_notification_sent = False
            recruitment_was_full = False

            # 이전 부에서 13번 이후로 들어온
            # 대기자를 새 부 참여자로 자동 이동
            participants = (
                waiting.copy()
            )

            waiting.clear()

            # 혹시 대기자가 12명보다 많으면
            # 12명까지만 현재 부로 이동
            if (
                len(participants)
                > MAX_PARTICIPANTS
            ):
                waiting = (
                    participants[
                        MAX_PARTICIPANTS:
                    ]
                )

                participants = (
                    participants[
                        :MAX_PARTICIPANTS
                    ]
                )

            try:
                await message.delete()

            except (
                discord.Forbidden,
                discord.NotFound,
                discord.HTTPException
            ):
                pass

            participant_message = (
                await message.channel.send(
                    make_participant_list()
                )
            )

            save_current_part_history(
                message.guild
            )

            save_recruitment_state(
                message.guild
            )

            await check_full_status(
                message.channel
            )

            return

    # ==================================================
    # 참여 / 참가
    # ==================================================

    if content in [
        "참여",
        "참가"
    ]:
        if current_part is None:
            try:
                await message.delete()

            except (
                discord.Forbidden,
                discord.NotFound,
                discord.HTTPException
            ):
                pass

            notice = await message.channel.send(
                "⚠️ 아직 대내 모집이 시작되지 않았습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        user_id = (
            message.author.id
        )

        if user_exists(
            user_id
        ):
            try:
                await message.delete()

            except (
                discord.Forbidden,
                discord.NotFound,
                discord.HTTPException
            ):
                pass

            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 "
                f"이미 등록되어 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        user_data = {
            "id":
                user_id,
            "name":
                message.author.display_name
        }

        if (
            len(participants)
            < MAX_PARTICIPANTS
        ):
            participants.append(
                user_data
            )

        else:
            waiting.append(
                user_data
            )

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        await update_participant_message(
            message.channel
        )

        save_current_part_history(
            message.guild
        )

        save_recruitment_state(
            message.guild
        )

        await check_full_status(
            message.channel
        )

        return

    # ==================================================
    # 취소
    # ==================================================

    if content == "취소":
        user_id = (
            message.author.id
        )

        removed = False
        removed_from_main = False

        removed_name = (
            message.author.display_name
        )

        for user in participants:
            if (
                user["id"]
                == user_id
            ):
                participants.remove(
                    user
                )

                removed = True
                removed_from_main = True

                break

        if not removed:
            for user in waiting:
                if (
                    user["id"]
                    == user_id
                ):
                    waiting.remove(
                        user
                    )

                    removed = True

                    break

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        if not removed:
            notice = await message.channel.send(
                f"⚠️ {message.author.display_name}님은 "
                f"등록되어 있지 않습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        # 현재 명단에서 사람이 빠졌고
        # 대기자가 있다면 대기 1번을 자동 승급
        if (
            removed_from_main
            and waiting
        ):
            participants.append(
                waiting.pop(
                    0
                )
            )

        await update_participant_message(
            message.channel
        )

        save_current_part_history(
            message.guild
        )

        save_recruitment_state(
            message.guild
        )

        if (
            recruitment_was_full
            and removed_from_main
        ):
            await message.channel.send(
                f"⚠️ **{removed_name}님이 "
                f"참여를 취소했습니다.**\n"
                f"현재 인원: "
                f"**{len(participants)}/"
                f"{MAX_PARTICIPANTS}명**"
            )

            await check_full_status(
                message.channel,
                announce_drop=False
            )

        else:
            await check_full_status(
                message.channel
            )

        return

    # ==================================================
    # 불참 닉네임
    # ==================================================

    if content.startswith(
        "불참 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        name = (
            content[
                len("불참 "):
            ].strip()
        )

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
        )

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        removed = False
        removed_from_main = False

        for user in participants:
            if (
                user["id"]
                == target.id
            ):
                participants.remove(
                    user
                )

                removed = True
                removed_from_main = True

                break

        if not removed:
            for user in waiting:
                if (
                    user["id"]
                    == target.id
                ):
                    waiting.remove(
                        user
                    )

                    removed = True

                    break

        if not removed:
            notice = await message.channel.send(
                f"⚠️ {get_base_name(target)}님은 "
                f"명단에 없습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        if (
            removed_from_main
            and waiting
        ):
            participants.append(
                waiting.pop(
                    0
                )
            )

        await update_participant_message(
            message.channel
        )

        save_current_part_history(
            message.guild
        )

        save_recruitment_state(
            message.guild
        )

        await check_full_status(
            message.channel
        )

        return
    # ==================================================
    # 추가 닉네임
    # ==================================================

    if content.startswith(
        "추가 "
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        if current_part is None:
            notice = await message.channel.send(
                "⚠️ 먼저 `1부`, `2부` 등으로 "
                "모집을 시작해주세요."
            )

            await notice.delete(
                delay=4
            )

            return

        name = (
            content[
                len("추가 "):
            ].strip()
        )

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
        )

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        if await handle_search_error(
            message.channel,
            name,
            error,
            matches
        ):
            return

        if user_exists(
            target.id
        ):
            notice = await message.channel.send(
                f"⚠️ {get_base_name(target)}님은 "
                f"이미 등록되어 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        user_data = {
            "id":
                target.id,
            "name":
                target.display_name
        }

        if (
            len(participants)
            < MAX_PARTICIPANTS
        ):
            participants.append(
                user_data
            )

        else:
            waiting.append(
                user_data
            )

        await update_participant_message(
            message.channel
        )

        save_current_part_history(
            message.guild
        )

        save_recruitment_state(
            message.guild
        )

        await check_full_status(
            message.channel
        )

        return

    # ==================================================
    # 집합
    # ==================================================

    if (
        content == "집합"
        or content.startswith(
            "집합 "
        )
    ):
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 집합 알림을 보낼 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        if current_part is None:
            notice = await message.channel.send(
                "⚠️ 현재 모집 중인 대내가 없습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        if not participants:
            notice = await message.channel.send(
                "⚠️ 현재 참여자가 없습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        gather_time = (
            content[
                len("집합"):
            ].strip()
        )

        if not gather_time:
            notice = await message.channel.send(
                "⚠️ 시간을 같이 적어주세요.\n"
                "예: `집합 20:30`"
            )

            await notice.delete(
                delay=5
            )

            return

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException
        ):
            pass

        mentions = " ".join(
            f"<@{user['id']}>"
            for user in participants
        )

        mention_message = (
            await message.channel.send(
                mentions,
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False
                )
            )
        )

        await mention_message.delete(
            delay=5
        )

        await message.channel.send(
            f"🔔 **{current_part}부 대내**\n"
            f"       **{gather_time}까지**\n"
            f"       **대내 대기방에 집합해주세요!**"
        )

        return

    # ==================================================
    # 클린
    # ==================================================

    if content == "클린":
        if not is_admin(
            message.author
        ):
            notice = await message.channel.send(
                "❌ 운영진만 사용할 수 있습니다."
            )

            await notice.delete(
                delay=3
            )

            return

        if current_part is not None:
            save_current_part_history(
                message.guild
            )

        participants.clear()
        waiting.clear()

        current_part = None
        participant_message = None

        full_notification_sent = False
        recruitment_was_full = False

        clear_recruitment_state()

        async for msg in (
            message.channel.history(
                limit=None
            )
        ):
            if msg.pinned:
                continue

            try:
                await msg.delete()

            except (
                discord.Forbidden,
                discord.NotFound,
                discord.HTTPException
            ):
                pass

        return

    await bot.process_commands(
        message
    )


# ==================================================
# 테스트
# ==================================================

@bot.command()
async def 테스트(
    ctx
):
    await ctx.send(
        "전사봇 정상 작동 중! 🤖"
    )


# ==================================================
# 토큰
# ==================================================

token = os.getenv(
    "DISCORD_TOKEN"
)

if not token:
    raise ValueError(
        "DISCORD_TOKEN이 설정되지 않았습니다."
    )


bot.run(
    token
)
