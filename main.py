from dotenv import load_dotenv
load_dotenv()

import os
import random
import json
from datetime import datetime

import discord
from discord.ext import commands


# ==================================================
# 기본 설정
# ==================================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True
intents.reactions = True

bot = commands.Bot(
    command_prefix="!!",
    intents=intents
)

MAX_PARTICIPANTS = 12
STAFF_ROLE_NAME = "운영진"

participants = []
waiting = []

participant_message = None
current_part = None

full_notification_sent = False
recruitment_was_full = False


# ==================================================
# 투표 설정
# ==================================================

POLL_FILE = "poll_state.json"

POLL_R = "🇷"
POLL_S = "🇸"
POLL_M = "🇲"

poll_state = {}


def load_poll_state():

    global poll_state

    try:

        with open(
            POLL_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            poll_state = json.load(f)

    except (
        FileNotFoundError,
        json.JSONDecodeError
    ):

        poll_state = {}


def save_poll_state():

    with open(
        POLL_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            poll_state,
            f,
            ensure_ascii=False,
            indent=4
        )


load_poll_state()


# ==================================================
# 투표 날짜 입력
# ==================================================

def parse_poll_datetime(text):

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


# ==================================================
# 투표 날짜 표시
#
# 예:
# 2026.08.29(토) 22:30
# ==================================================

def format_poll_datetime(dt):

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


# ==================================================
# 투표 메시지
# ==================================================

def make_poll_embed(date_text):

    embed = discord.Embed(
        description=(
            f"**{date_text} 참가자 명단**\n\n"
            f"라플 참가자 {POLL_R} / "
            f"스나 참가자 {POLL_S} / "
            f"멀티 참가자 {POLL_M} "
            f"체크 부탁드립니다\n\n"
            f"*인원제한 없습니다 3항목중 하나만 선택해주세요*\n"
            f"용병을 제외한 나머지는 본인 아이디로 참가하셔야 합니다.\n"
            f"세트 인원이 있을 시 이벤트 채널에 "
            f"세트인원 아이디 작성하여 남겨주세요!"
        ),
        color=discord.Color.red()
    )

    return embed


# ==================================================
# 참여 명단 만들기
# ==================================================

def make_participant_list():

    if current_part is None:

        return (
            "📋 **대내 모집이 시작되지 않았습니다.**"
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

    return "\n".join(lines)


# ==================================================
# 참여 명단 업데이트
# ==================================================

async def update_participant_message(channel):

    global participant_message

    text = make_participant_list()

    if participant_message:

        try:

            await participant_message.edit(
                content=text
            )

            return

        except (
            discord.NotFound,
            discord.HTTPException
        ):

            participant_message = None

    participant_message = await channel.send(
        text
    )


# ==================================================
# 운영진 역할 찾기
# ==================================================

def get_staff_role(guild):

    return discord.utils.get(
        guild.roles,
        name=STAFF_ROLE_NAME
    )


# ==================================================
# 12명 모집 상태
# ==================================================

async def check_full_status(
    channel,
    announce_drop=True
):

    global full_notification_sent
    global recruitment_was_full

    count = len(
        participants
    )

    staff_role = get_staff_role(
        channel.guild
    )

    if staff_role:

        staff_mention = (
            staff_role.mention
        )

    else:

        staff_mention = (
            "**운영진**"
        )

    # 12명 되는 순간
    if (
        count == MAX_PARTICIPANTS
        and
        not full_notification_sent
    ):

        full_notification_sent = True
        recruitment_was_full = True

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

    # 12명 → 11명
    elif (
        count == MAX_PARTICIPANTS - 1
        and
        full_notification_sent
    ):

        full_notification_sent = False

        if announce_drop:

            await channel.send(
                f"{staff_mention}\n\n"
                f"⚠️ **{current_part}부 참여자 한 명이 빠졌습니다.**\n"
                f"현재 인원: "
                f"**{count}/{MAX_PARTICIPANTS}명**",
                allowed_mentions=discord.AllowedMentions(
                    roles=True,
                    users=False,
                    everyone=False
                )
            )


# ==================================================
# 중복 참여 확인
# ==================================================

def user_exists(user_id):

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
# 기본 닉네임 추출
# ==================================================

def get_base_name(member):

    display_name = (
        member.display_name.strip()
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
                ].strip()
            )

            break

    return (
        display_name
        .split("/")[0]
        .strip()
    )


# ==================================================
# 닉네임 검색
# ==================================================

def find_member_by_name(
    guild,
    name
):

    target_name = (
        name.strip().lower()
    )

    exact_matches = []
    partial_matches = []

    for member in guild.members:

        if member.bot:
            continue

        base_name = (
            get_base_name(
                member
            ).lower()
        )

        if target_name == base_name:

            exact_matches.append(
                member
            )

        elif target_name in base_name:

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


# ==================================================
# 닉네임 검색 오류
# ==================================================

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
            for member in matches[:10]
        )

        notice = await channel.send(
            f"⚠️ `{name}`으로 여러 명이 검색됐습니다.\n\n"
            f"{names}\n\n"
            f"조금 더 구체적으로 입력해주세요."
        )

        await notice.delete(
            delay=10
        )

        return True

    return False


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

        self.items = discord.ui.TextInput(
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

        self.add_item(
            self.items
        )

    async def on_submit(
        self,
        interaction
    ):

        if not (
            interaction.user
            .guild_permissions
            .manage_messages
        ):

            await interaction.response.send_message(
                "❌ 운영진만 사용할 수 있습니다.",
                ephemeral=True
            )

            return

        values = [
            item.strip()
            for item in self.items.value.split(
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

        if not (
            interaction.user
            .guild_permissions
            .manage_messages
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
            or
            not self.right_items
        ):

            await interaction.response.send_message(
                "⚠️ 왼쪽과 오른쪽 항목을 먼저 입력해주세요.",
                ephemeral=True
            )

            return

        if (
            len(self.left_items)
            !=
            len(self.right_items)
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
# 봇 준비 완료
# ==================================================

@bot.event
async def on_ready():

    print(
        f"{bot.user} 로그인 완료!"
    )


# ==================================================
# 투표 반응
#
# R / S / M 중 하나만 선택
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

    except:
        return

    if (
        payload.message_id
        !=
        poll_message_id
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

            member = await guild.fetch_member(
                payload.user_id
            )

        except:
            return

    channel = guild.get_channel(
        payload.channel_id
    )

    if channel is None:

        try:

            channel = await bot.fetch_channel(
                payload.channel_id
            )

        except:
            return

    try:

        poll_message = (
            await channel.fetch_message(
                payload.message_id
            )
        )

    except:
        return

    # 자신이 누른 항목 제외
    # 나머지 두 개 자동 제거
    for other_emoji in valid_emojis:

        if other_emoji == emoji:
            continue

        try:

            await poll_message.remove_reaction(
                other_emoji,
                member
            )

        except:
            pass


# ==================================================
# 메시지 명령
# ==================================================

@bot.event
async def on_message(message):

    global participants
    global waiting
    global participant_message
    global current_part
    global full_notification_sent
    global recruitment_was_full
    global poll_state

    if message.author.bot:
        return

    if not message.guild:
        return

    content = (
        message.content.strip()
    )


    # ==================================================
    # 도움
    # ==================================================

    if content == "도움":

        embed = discord.Embed(
            title="📌 전사봇 사용법",
            color=discord.Color.red()
        )

        embed.add_field(
            name="👥 참여자",
            value=(
                "`참여` 또는 `참가`\n"
                "→ 대내 참여\n\n"

                "`취소`\n"
                "→ 본인 참여 취소\n\n\n"
            ),
            inline=False
        )

        embed.add_field(
            name="🛠️ 운영진",
            value=(
                "`1부`, `2부`, `3부`\n"
                "→ 해당 부 모집 시작\n\n"

                "`추가 닉네임`\n"
                "→ 해당 인원 직접 추가\n\n"

                "`불참 닉네임`\n"
                "→ 해당 인원 직접 제외\n\n"

                "`집합 20:30`\n"
                "→ 참여자 호출 + 집합 안내\n\n"

                "`사다리`\n"
                "→ 사다리타기 실행\n\n"

                "`대내투표 2026-08-29 22:30`\n"
                "→ 라플 / 스나 / 멀티 투표 생성\n\n"

                "`투표수정 2026-10-03 22:30`\n"
                "→ 투표 날짜·시간만 수정\n\n"

                "`투표초기화`\n"
                "→ 기존 투표 전부 초기화\n\n"

                "`클린`\n"
                "→ 채팅 및 모집 초기화\n\n\n"
            ),
            inline=False
        )

        embed.add_field(
            name="⏳ 자동 기능",
            value=(
                "1~12번 → 현재 부 참여\n"
                "13번부터 → 다음 부 대기\n"
                "다음 부 시작 시 대기 인원 자동 이동\n"
                "12명 모집 완료 시 운영진 자동 알림"
            ),
            inline=False
        )

        await message.channel.send(
            embed=embed
        )

        return


    # ==================================================
    # 대내투표 생성
    #
    # 예:
    # 대내투표 2026-08-29 22:30
    # ==================================================

    if content.startswith(
        "대내투표 "
    ):

        if not (
            message.author
            .guild_permissions
            .manage_messages
        ):

            notice = (
                await message.channel.send(
                    "❌ 운영진만 투표를 생성할 수 있습니다."
                )
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

            notice = (
                await message.channel.send(
                    "⚠️ 날짜와 시간을 이렇게 입력해주세요.\n"
                    "`대내투표 2026-08-29 22:30`"
                )
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
        except:
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
    #
    # 날짜/시간만 변경
    # 기존 투표 유지
    # ==================================================

    if content.startswith(
        "투표수정 "
    ):

        if not (
            message.author
            .guild_permissions
            .manage_messages
        ):

            notice = (
                await message.channel.send(
                    "❌ 운영진만 투표를 수정할 수 있습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        if not poll_state:

            notice = (
                await message.channel.send(
                    "⚠️ 수정할 대내투표가 없습니다."
                )
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

            notice = (
                await message.channel.send(
                    "⚠️ 이렇게 입력해주세요.\n"
                    "`투표수정 2026-10-03 22:30`"
                )
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

        except:

            notice = (
                await message.channel.send(
                    "⚠️ 기존 투표 메시지를 찾을 수 없습니다."
                )
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

        # 날짜/시간만 변경
        # 반응은 그대로 유지
        await poll_message.edit(
            embed=make_poll_embed(
                date_text
            )
        )

        poll_state["date"] = (
            poll_datetime.strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        save_poll_state()

        try:
            await message.delete()
        except:
            pass

        notice = (
            await message.channel.send(
                "✅ 투표 날짜와 시간을 수정했습니다."
            )
        )

        await notice.delete(
            delay=3
        )

        return


    # ==================================================
    # 투표초기화
    #
    # 날짜는 그대로
    # 기존 사람들이 누른 R/S/M만 모두 삭제
    # ==================================================

    if content == "투표초기화":

        if not (
            message.author
            .guild_permissions
            .manage_messages
        ):

            notice = (
                await message.channel.send(
                    "❌ 운영진만 투표를 초기화할 수 있습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        if not poll_state:

            notice = (
                await message.channel.send(
                    "⚠️ 초기화할 대내투표가 없습니다."
                )
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

        except:

            notice = (
                await message.channel.send(
                    "⚠️ 기존 투표 메시지를 찾을 수 없습니다."
                )
            )

            await notice.delete(
                delay=5
            )

            return

        try:
            await message.delete()
        except:
            pass

        # 기존 반응 전부 삭제
        try:

            await poll_message.clear_reactions()

        except:

            notice = (
                await message.channel.send(
                    "⚠️ 투표 반응을 삭제하지 못했습니다.\n"
                    "봇의 `메시지 관리` 권한을 확인해주세요."
                )
            )

            await notice.delete(
                delay=5
            )

            return

        # 새 R / S / M 반응 다시 생성
        await poll_message.add_reaction(
            POLL_R
        )

        await poll_message.add_reaction(
            POLL_S
        )

        await poll_message.add_reaction(
            POLL_M
        )

        notice = (
            await message.channel.send(
                "✅ 투표가 초기화되었습니다.\n"
                "🇷 라플 / 🇸 스나 / 🇲 멀티를 다시 선택해주세요."
            )
        )

        await notice.delete(
            delay=5
        )

        return


    # ==================================================
    # 사다리
    # ==================================================

    if content == "사다리":

        if not (
            message.author
            .guild_permissions
            .manage_messages
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
        except:
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
            content[:-1].strip()
        )

        if part_text.isdigit():

            if not (
                message.author
                .guild_permissions
                .manage_messages
            ):

                try:
                    await message.delete()
                except:
                    pass

                notice = (
                    await message.channel.send(
                        "❌ 운영진만 대내 모집을 시작할 수 있습니다."
                    )
                )

                await notice.delete(
                    delay=3
                )

                return

            if participant_message:

                try:

                    await participant_message.delete()

                except:
                    pass

                participant_message = None

            current_part = (
                part_text
            )

            full_notification_sent = False
            recruitment_was_full = False

            participants = (
                waiting.copy()
            )

            waiting.clear()

            if (
                len(participants)
                >
                MAX_PARTICIPANTS
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
            except:
                pass

            await update_participant_message(
                message.channel
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
            except:
                pass

            notice = (
                await message.channel.send(
                    "⚠️ 아직 대내 모집이 시작되지 않았습니다."
                )
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
            except:
                pass

            notice = (
                await message.channel.send(
                    f"⚠️ {message.author.display_name}님은 "
                    f"이미 등록되어 있습니다."
                )
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
            <
            MAX_PARTICIPANTS
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
        except:
            pass

        await update_participant_message(
            message.channel
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

            if user[
                "id"
            ] == user_id:

                participants.remove(
                    user
                )

                removed = True
                removed_from_main = True

                break

        if not removed:

            for user in waiting:

                if user[
                    "id"
                ] == user_id:

                    waiting.remove(
                        user
                    )

                    removed = True

                    break

        try:
            await message.delete()
        except:
            pass

        if not removed:

            notice = (
                await message.channel.send(
                    f"⚠️ {message.author.display_name}님은 "
                    f"등록되어 있지 않습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        if (
            removed_from_main
            and
            waiting
        ):

            participants.append(
                waiting.pop(0)
            )

        await update_participant_message(
            message.channel
        )

        if (
            recruitment_was_full
            and
            removed_from_main
        ):

            await message.channel.send(
                f"⚠️ **{removed_name}님이 참여를 취소했습니다.**\n"
                f"현재 인원: "
                f"**{len(participants)}/{MAX_PARTICIPANTS}명**"
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

        if not (
            message.author
            .guild_permissions
            .manage_messages
        ):

            notice = (
                await message.channel.send(
                    "❌ 운영진만 사용할 수 있습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        name = (
            content[3:].strip()
        )

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
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

        removed = False
        removed_from_main = False

        for user in participants:

            if user[
                "id"
            ] == target.id:

                participants.remove(
                    user
                )

                removed = True
                removed_from_main = True

                break

        if not removed:

            for user in waiting:

                if user[
                    "id"
                ] == target.id:

                    waiting.remove(
                        user
                    )

                    removed = True

                    break

        if not removed:

            notice = (
                await message.channel.send(
                    f"⚠️ {get_base_name(target)}님은 "
                    f"명단에 없습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        if (
            removed_from_main
            and
            waiting
        ):

            participants.append(
                waiting.pop(0)
            )

        await update_participant_message(
            message.channel
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

        if not (
            message.author
            .guild_permissions
            .manage_messages
        ):

            notice = (
                await message.channel.send(
                    "❌ 운영진만 사용할 수 있습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        if current_part is None:

            notice = (
                await message.channel.send(
                    "⚠️ 먼저 `1부`, `2부` 등으로 "
                    "모집을 시작해주세요."
                )
            )

            await notice.delete(
                delay=4
            )

            return

        name = (
            content[3:].strip()
        )

        target, error, matches = (
            find_member_by_name(
                message.guild,
                name
            )
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

        if user_exists(
            target.id
        ):

            notice = (
                await message.channel.send(
                    f"⚠️ {get_base_name(target)}님은 "
                    f"이미 등록되어 있습니다."
                )
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
            <
            MAX_PARTICIPANTS
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

        await check_full_status(
            message.channel
        )

        return


    # ==================================================
    # 집합
    # ==================================================

    if (
        content == "집합"
        or
        content.startswith(
            "집합 "
        )
    ):

        if not (
            message.author
            .guild_permissions
            .manage_messages
        ):

            try:
                await message.delete()
            except:
                pass

            notice = (
                await message.channel.send(
                    "❌ 운영진만 집합 알림을 보낼 수 있습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        if current_part is None:

            try:
                await message.delete()
            except:
                pass

            notice = (
                await message.channel.send(
                    "⚠️ 현재 모집 중인 대내가 없습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        if not participants:

            try:
                await message.delete()
            except:
                pass

            notice = (
                await message.channel.send(
                    "⚠️ 현재 참여자가 없습니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        gather_time = (
            content[2:].strip()
        )

        try:
            await message.delete()
        except:
            pass

        if not gather_time:

            notice = (
                await message.channel.send(
                    "⚠️ 시간을 같이 적어주세요.\n"
                    "예: `집합 20:30`"
                )
            )

            await notice.delete(
                delay=5
            )

            return

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

        if not (
            message.author
            .guild_permissions
            .manage_messages
        ):

            notice = (
                await message.channel.send(
                    "❌ 메시지 관리 권한이 필요합니다."
                )
            )

            await notice.delete(
                delay=3
            )

            return

        participants.clear()
        waiting.clear()

        current_part = None
        participant_message = None

        full_notification_sent = False
        recruitment_was_full = False

        async for msg in (
            message.channel.history(
                limit=None
            )
        ):

            if msg.pinned:
                continue

            try:
                await msg.delete()
            except:
                pass

        return


    await bot.process_commands(
        message
    )


# ==================================================
# 테스트
# ==================================================

@bot.command()
async def 테스트(ctx):

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


bot.run(token)
