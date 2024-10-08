import os
import discord
from discord.ext import commands, tasks
from openai import OpenAI
from openai.error import AuthenticationError, APIError
import datetime
import pytz
import asyncio
import re
import logging
import traceback
import random

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# Configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

logger.info(f"Discord Token: {'Set' if DISCORD_TOKEN else 'Not Set'}")
logger.info(f"OpenAI API Key: {'Set' if OPENAI_API_KEY else 'Not Set'}")

client = OpenAI(api_key=OPENAI_API_KEY)
TIMEZONE = pytz.timezone("Europe/Rome")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

user_data = {}

MESSAGES = {
    'en': {
        'welcome': "Hello! I'm your advanced AI personal assistant. I can help you with reminders, notes, and much more. How can I assist you today?",
        'language_set': "Language set to English.",
        'reminder_set': "Reminder set for {time}: {content}",
        'no_reminders': "You don't have any reminders set.",
        'reminders_list': "Here are your reminders:\n{reminders}",
        'processing_error': "Sorry, I had a problem processing your request. Can you try again?",
        'api_key_error': "There's an issue with the AI service. Please contact the bot administrator.",
    },
    'it': {
        'welcome': "Ciao! Sono il tuo assistente personale IA avanzato. Posso aiutarti con promemoria, note e molto altro. Come posso assisterti oggi?",
        'language_set': "Lingua impostata su italiano.",
        'reminder_set': "Promemoria impostato per {time}: {content}",
        'no_reminders': "Non hai ancora nessun promemoria impostato.",
        'reminders_list': "Ecco i tuoi promemoria:\n{reminders}",
        'processing_error': "Mi dispiace, ho avuto un problema nel processare la tua richiesta. Puoi riprovare?",
        'api_key_error': "C'è un problema con il servizio AI. Si prega di contattare l'amministratore del bot.",
    }
}

def get_current_time():
    return datetime.datetime.now(TIMEZONE)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    check_reminders.start()
    keep_alive.start()

@bot.command()
async def start(ctx):
    try:
        logger.info(f"Start command received from user {ctx.author.id}")
        user_id = ctx.author.id
        user_data[user_id] = {"conversation": [], "reminders": [], "language": "en"}
        embed = discord.Embed(title="Language Selection", description="Please choose your language:")
        embed.add_field(name="English", value="React with 🇬🇧", inline=True)
        embed.add_field(name="Italiano", value="React with 🇮🇹", inline=True)
        message = await ctx.send(embed=embed)
        await message.add_reaction("🇬🇧")
        await message.add_reaction("🇮🇹")
    except Exception as e:
        logger.error(f"Error in start command: {str(e)}")
        logger.error(traceback.format_exc())

@bot.event
async def on_reaction_add(reaction, user):
    try:
        if user == bot.user:
            return

        logger.info(f"Reaction {reaction.emoji} added by user {user.id}")
        if reaction.message.author == bot.user and reaction.message.embeds and reaction.message.embeds[0].title == "Language Selection":
            user_id = user.id
            if str(reaction.emoji) == "🇬🇧":
                user_data[user_id]['language'] = 'en'
                await reaction.message.channel.send(MESSAGES['en']['language_set'])
                await reaction.message.channel.send(MESSAGES['en']['welcome'])
            elif str(reaction.emoji) == "🇮🇹":
                user_data[user_id]['language'] = 'it'
                await reaction.message.channel.send(MESSAGES['it']['language_set'])
                await reaction.message.channel.send(MESSAGES['it']['welcome'])
    except Exception as e:
        logger.error(f"Error in on_reaction_add: {str(e)}")
        logger.error(traceback.format_exc())

@bot.event
async def on_message(message):
    try:
        if message.author == bot.user:
            return

        logger.info(f"Message received from user {message.author.id}: {message.content}")
        await bot.process_commands(message)

        user_id = message.author.id
        user_message = message.content
        lang = user_data.get(user_id, {}).get('language', 'en')

        if user_id not in user_data:
            user_data[user_id] = {"conversation": [], "reminders": [], "language": lang}

        user_data[user_id]["conversation"].append({"role": "user", "content": user_message})

        system_message = {
            "role": "system",
            "content": f"""You are an intelligent personal assistant that helps with reminders, notes, and task management. 
            Carefully analyze user requests to understand if they are asking to set reminders, take notes, or just conversing. 
            For reminders, extract the content and specified time (including seconds if mentioned).
            The user's language is set to {lang}. Respond in that language."""
        }

        conversation = [system_message] + user_data[user_id]["conversation"][-10:]

        try:
            logger.info("Sending request to OpenAI API")
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=conversation
            )
            logger.info("Received response from OpenAI API")

            ai_response = response.choices[0].message.content
            user_data[user_id]["conversation"].append({"role": "assistant", "content": ai_response})

            reminders = extract_multiple_reminders(user_message)
            if reminders:
                for content, delay in reminders:
                    reminder_time = get_current_time() + datetime.timedelta(seconds=delay)
                    user_data[user_id]["reminders"].append({"content": content, "time": reminder_time})
                    await message.channel.send(MESSAGES[lang]['reminder_set'].format(
                        time=reminder_time.strftime('%d/%m/%Y at %H:%M:%S'),
                        content=content
                    ))
            
            await message.channel.send(ai_response)

        except AuthenticationError as e:
            logger.error(f"OpenAI API Authentication Error: {e}")
            await message.channel.send(MESSAGES[lang]['api_key_error'])
        except APIError as e:
            logger.error(f"OpenAI API Error: {e}")
            await message.channel.send(MESSAGES[lang]['processing_error'])
        except Exception as e:
            logger.error(f"Unexpected error in OpenAI API call: {e}")
            logger.error(traceback.format_exc())
            await message.channel.send(MESSAGES[lang]['processing_error'])
    except Exception as e:
        logger.error(f"Error in on_message: {str(e)}")
        logger.error(traceback.format_exc())

def extract_multiple_reminders(text):
    reminders = []
    lines = text.split('\n')
    for line in lines:
        reminder = extract_single_reminder(line)
        if reminder:
            reminders.append(reminder)
    return reminders

def extract_single_reminder(text):
    time_patterns = [
        (r'tra (\d+) second[oi]', 1),
        (r'tra (\d+) minut[oi]', 60),
        (r'tra (\d+) or[ae]', 3600),
        (r'in (\d+) second[s]?', 1),
        (r'in (\d+) minute[s]?', 60),
        (r'in (\d+) hour[s]?', 3600),
    ]
    
    for pattern, multiplier in time_patterns:
        match = re.search(pattern, text.lower())
        if match:
            time_value = int(match.group(1))
            delay = time_value * multiplier
            content = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()
            return content, delay
    
    return None

@bot.command()
async def viewreminders(ctx):
    try:
        logger.info(f"Viewreminders command received from user {ctx.author.id}")
        user_id = ctx.author.id
        lang = user_data.get(user_id, {}).get('language', 'en')
        if user_id in user_data and user_data[user_id]["reminders"]:
            reminders = "\n".join([f"- {reminder['content']} ({reminder['time'].strftime('%d/%m/%Y at %H:%M:%S')})" for reminder in user_data[user_id]["reminders"]])
            embed = discord.Embed(title="Your Reminders", description=reminders, color=0x00ff00)
            await ctx.send(embed=embed)
        else:
            await ctx.send(MESSAGES[lang]['no_reminders'])
    except Exception as e:
        logger.error(f"Error in viewreminders command: {str(e)}")
        logger.error(traceback.format_exc())

@tasks.loop(seconds=10)
async def check_reminders():
    try:
        logger.debug("Checking reminders")
        current_time = get_current_time()
        for user_id, data in user_data.items():
            reminders_to_remove = []
            for reminder in data["reminders"]:
                if current_time >= reminder["time"]:
                    try:
                        user = await bot.fetch_user(user_id)
                        await user.send(f"🔔 Reminder: {reminder['content']}")
                        reminders_to_remove.append(reminder)
                    except Exception as e:
                        logger.error(f"Error sending reminder to user {user_id}: {str(e)}")
                        logger.error(traceback.format_exc())
            for reminder in reminders_to_remove:
                data["reminders"].remove(reminder)
    except Exception as e:
        logger.error(f"Error in check_reminders: {str(e)}")
        logger.error(traceback.format_exc())

@tasks.loop(minutes=5)
async def keep_alive():
    try:
        logger.debug("Sending keep-alive ping")
        latency = bot.latency
        logger.info(f"Current latency: {latency}")
    except Exception as e:
        logger.error(f"Error in keep_alive: {str(e)}")
        logger.error(traceback.format_exc())

async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    logger.info("Starting bot")
    while True:
        try:
            asyncio.run(main())
        except Exception as e:
            logger.error(f"Bot crashed. Restarting in 5 seconds. Error: {str(e)}")
            logger.error(traceback.format_exc())
            asyncio.sleep(5 + random.uniform(0, 5))  # Add some randomness to avoid potential rate limits