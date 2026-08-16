from dotenv import load_dotenv

load_dotenv()
import os
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!!", intents=intents)

@bot.event
async def on_ready():
    print(f"{bot.user} 로그인 완료!")

@bot.command()
async def 테스트(ctx):
    await ctx.send("대내봇 정상 작동 중! 🤖")

token = os.getenv("DISCORD_TOKEN")

if not token:
    raise ValueError("DISCORD_TOKEN이 설정되지 않았습니다.")

bot.run(token)
