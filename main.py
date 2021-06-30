import requests
import yaml
import os
import datetime
import concurrent.futures
import sys
import telegram.constants
import time
from random import randint
from telegram.ext import Updater
from telegram.ext import CommandHandler
from telegram.ext.dispatcher import run_async
from bs4 import BeautifulSoup, Comment
import re

## General functions

# Save current state
def save_config():
    config["chats"] = chats

    # Write to config file
    with open(config_path, "w") as config_file:
        yaml.dump(config, config_file, default_flow_style=False)

# Get information
def get_info(zip_code, birthdate=None):
    if not birthdate:
        birthdate = randint(-631155600, -599619600)
    URL = f'https://www.impfportal-niedersachsen.de/portal/rest/appointments/findVaccinationCenterListFree/{zip_code}?stiko=&count=1&birthdate={birthdate}'
    return requests.get(url = URL).json()

# Set varibales and start monitoring
def init_chat(chat):
    available[chat] = False

    if chats[chat]["zip_code"] not in monitoring:
        monitoring.append(chats[chat]["zip_code"])
        deploy_agent(chats[chat]["zip_code"])

def update_vaccines(interval):
    global vaccines
    while(True):
        time.sleep(interval)
        vaccines = get_vaccines()

# Vaccine list
def get_vaccines():
    vaccines_age = get_vaccine_min_age()
    vaccines = {
        'Moderna': {
            "type": "mRNA", 
            "min_age": vaccines_age['Moderna Biotech Spain, S.L.'] if 'Moderna Biotech Spain, S.L.' in vaccines_age and vaccines_age['Moderna Biotech Spain, S.L.'] else 18},
        'BioNtech': {
            "type": "mRNA",
            "min_age":vaccines_age['BioNTech Manufacturing GmbH'] if 'BioNTech Manufacturing GmbH' in vaccines_age and vaccines_age['BioNTech Manufacturing GmbH'] else 12},
        'Johnson&Johnson': {
            "type": "Vector",
            "min_age": vaccines_age['Janssen-Cilag International NV'] if 'Janssen-Cilag International NV' in vaccines_age and vaccines_age['Janssen-Cilag International NV'] else 18},
        'AstraZeneca': {
            "type": "Vector",
            "min_age": vaccines_age['AstraZeneca AB, Schweden'] if 'AstraZeneca AB, Schweden' in vaccines_age and vaccines_age['AstraZeneca AB, Schweden'] else 18}
        }

    return vaccines

# Get vaccine min age from pei.de
def get_vaccine_min_age():
    soup = BeautifulSoup(requests.get("https://www.pei.de/DE/arzneimittel/impfstoffe/covid-19/covid-19-node.html").content, features="html.parser")
    table = [i.findAll("td") for i in soup.select("tbody > tr")]

    vaccines = {}
    for row in table:
        row_text = []
        for text in row:
            # Remove comments
            text = " ".join(text.find_all(text=lambda t: not isinstance(t, Comment)))
            # Remove whitespace
            text = " ".join(text.split())
            # Remove soft-hyphen characters
            text = text.replace("\xad", "")
            row_text.append(text)

        if (match := re.search("(?<=Verwendung ab einem Lebensalter von )\d{1,3}(?= Jahren)", row_text[1], re.IGNORECASE)):
            vaccines[row_text[2]] = int(match.group(0))
        else:
            vaccines[row_text[2]] = None
    
    return vaccines


## Chat command functions

# Inform new users
def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Dieser Bot benachrichtigt dich, wenn in deinem Impfzentrum ein Termin frei wird.")
    context.bot.send_message(chat_id=update.effective_chat.id, text="Bitte lege deine Postleitzzahl mit /plz Postleitzahl fest, um die Impfterminsuche zu starten")
    context.bot.send_message(chat_id=update.effective_chat.id, 
    text="Um nur über für deine Altersgruppe verfügbare Impftermine benachrichtigt zu werden, kannst du dein Geburtsdatum mit /birthdate DD.MM.YYYY festlegen.\n\nWeitere Befehle und Infos findest du [hier](https://github.com/Trigus42/Impftermin-TelegramBot/).",
    parse_mode=telegram.constants.PARSEMODE_MARKDOWN, disable_web_page_preview=True, disable_notification=True)

# Check if zip code is valid, inform user and start monitoring
def set_zip_code(update, context):
    chat = update.effective_chat.id
    if context.args:
        zip_code = context.args[0]
        result = get_info(zip_code)

        if result['resultList']:
            vaccination_center = result['resultList'][0]['name']
            if chat not in chats:
                chats[chat] = {"zip_code": zip_code}
                context.bot.send_message(chat_id=chat, text=f'Dein Impfzentrum ist: "{vaccination_center}"')
                save_config()
            elif chats[chat]["zip_code"]:
                chats[chat]["zip_code"] = zip_code
                context.bot.send_message(chat_id=chat, text=f'Deine Postleitzahl wurde aktualisiert. Dein Impfzentrum ist: "{vaccination_center}"')
                save_config()
            else:
                chats[chat]["zip_code"] = zip_code
                context.bot.send_message(chat_id=chat, text=f'Dein Impfzentrum ist: "{vaccination_center}"')
                save_config()

            # With the zip code set, monitoring can be started
            init_chat(chat)
        else:
            context.bot.send_message(chat_id=chat, text=f'Fehlerhafte Postleitzahl: "{context.args[0]}"')
    else:
        context.bot.send_message(chat_id=chat, text=f"Fehler: Keine Postleitzahl angegeben.")

# Fetch current state of the vaccination center and send detailed info to user
def status_update(update, context):
    chat = update.effective_chat.id
    if chat in chats and chats[chat]["zip_code"]:
        result = get_info(chats[chat]["zip_code"])
        message = f'Impfzentrum: {result["resultList"][0]["name"]}\nImpfstoff: {result["resultList"][0]["vaccineName"]} ({result["resultList"][0]["vaccineType"]})\n'
        message += f'Freie Impftermine (alle): {result["resultList"][0]["freeSlotSizeOnline"] if not result["resultList"][0]["outOfStock"] else "0"}'
        context.bot.send_message(chat_id=chat, text=message)
    else:
        context.bot.send_message(chat_id=chat, text="Lege bitte zuerst deine Postleitzahl fest.")

def set_birthdate(update, context):
    chat = update.effective_chat.id
    if context.args:
        birthdate = context.args[0]
        try:
            birthdate_unixtime = int(datetime.datetime.strptime(birthdate, '%d.%m.%Y').timestamp())
            if chat in chats:
                chats[chat]["birthdate"] = birthdate_unixtime
                context.bot.send_message(chat_id=chat, text=f'Dein Geburtsdatum wurde aktualisiert.')
                save_config()
            else:
                chats[chat] = {"zip_code": None, "birthdate": birthdate_unixtime}
                context.bot.send_message(chat_id=chat, text=f'Dein Geburtsdatum wurde erfolgreich festgelegt. Bitte lege deine Postleitzahl fest, um die Impfterminsuche zu starten')
                save_config()
        except ValueError:
            context.bot.send_message(chat_id=chat, text=f'Fehlerhaftes Datumsformat: {birthdate}\nErwartet: DD.MM.YYYY')
    else:
        context.bot.send_message(chat_id=chat, text=f"Fehler: Kein Datum angegeben.")

# Add vaccine to exclusion list
def exclude_vaccine(update, context):
    chat = update.effective_chat.id
    if not "vaccines" in chats[chat]:
        chats[chat]["vaccines"] = {}
    if context.args:
        user_vaccine = context.args[0]
        vaccine_list = list(vaccines.keys())
        for vaccine in vaccine_list:
            if vaccine.upper()[0] == user_vaccine.upper()[0]:
                chats[chat]["vaccines"][vaccine] = False
                context.bot.send_message(chat_id=chat, text=f'Der Impfstoff "{vaccine}" wurde der Ausschlussliste hinzugefügt.')
                temp = True
                save_config()
        if not temp:
            context.bot.send_message(chat_id=chat, text=f'Der Impfstoff "{user_vaccine}" ist unbekannt.')
    else:
        context.bot.send_message(chat_id=chat, text=f"Fehler: Kein Impfstoff angegeben")

# Remove vaccine from exclusion list
def include_vaccine(update, context):
    chat = update.effective_chat.id
    if not "vaccines" in chats[chat]:
        chats[chat]["vaccines"] = {}
    if context.args:
        user_vaccine = context.args[0]
        vaccine_list = list(vaccines.keys())
        for vaccine in vaccine_list:
            if vaccine.upper()[0] == user_vaccine.upper()[0]:
                chats[chat]["vaccines"][vaccine] = True
                context.bot.send_message(chat_id=chat, text=f'Der Impfstoff "{vaccine}" wurde von der Ausschlussliste entfernt.')
                temp = True
                save_config()
        if not temp:
            context.bot.send_message(chat_id=chat, text=f'Der Impfstoff "{user_vaccine}" ist unbekannt.')
    else:
        context.bot.send_message(chat_id=chat, text=f"Fehler: Kein Impfstoff angegeben")

def vaccine_info(update, context):
    chat = update.effective_chat.id
    message = ""

    if chat in chats:
        for vaccine in vaccines.keys():
            message += f"{vaccine}: {'Ausgeschlossen' if not check_vaccine_not_excluded(chat, vaccine) else ('Ab '+ str(vaccines[vaccine]['min_age']) + ' Jahren') if not check_vaccine_age_match(chat, vaccine) else 'Überwacht'}\n"
    else:
        for vaccine in vaccines.keys():
            message += f"{vaccine}\n"

    updater.bot.send_message(chat_id=chat, text=message)


## Monitoring functions

# Create a process monitoring the state of the vaccination center
def deploy_agent(zip_code, interval=1):
    print(zip_code, "- Chats (on initialization):", [chat for chat in chats if chats[chat]["zip_code"] == zip_code])
    while(True):
        try:
            result = get_info(zip_code)
            time0 = time.time()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                for chat in [chat for chat in chats if chats[chat]["zip_code"] == zip_code]:
                    executor.submit(analyze_result, result, chat)
            # substract time taken from sleep interval
            time.sleep(interval-period) if (period := time.time()-time0) < interval else None
        except Exception as e:
            print("Exception of agent:", e)

def analyze_result(result, chat):
    if (not result["resultList"][0]["outOfStock"]) and (not available[chat]) and check_vaccine(chat, result["resultList"][0]["vaccineName"]):
        updater.bot.send_message(chat_id=chat, text="[Freier Impftermin gefunden!](https://www.impfportal-niedersachsen.de/)", parse_mode=telegram.constants.PARSEMODE_MARKDOWN)
        # Can't differentiate between vaccines here
        # updater.bot.send_message(chat_id=chat, text=f"Insgesamt {result['resultList'][0]['freeSlotSizeOnline']} {'Termin' if result['resultList'][0]['freeSlotSizeOnline'] == 1 else 'Termine'} offen.")
        available[chat] = True
    elif available[chat] and (result["resultList"][0]["outOfStock"] or not check_vaccine(chat, result["resultList"][0]["vaccineName"])):
        updater.bot.send_message(chat_id=chat, text="Kein Impftermin mehr frei.")
        available[chat] = False

def check_vaccine(chat, vaccine):
    ret = check_vaccine_not_excluded(chat, vaccine)
    if not ret:
        return ret
    else:
        return check_vaccine_age_match(chat, vaccine)
    
# Check if vaccine is suited for given age
def check_vaccine_age_match(chat, vaccine):
    if "birthdate" in chats[chat]:
        birthdate = [int(i) for i in datetime.datetime.fromtimestamp(chats[chat]["birthdate"]).strftime('%d.%m.%Y').split(".")]
        date = [int(i) for i in datetime.datetime.fromtimestamp(time.time()).strftime('%d.%m.%Y').split(".")]
        age = {"years": date[2]-birthdate[2], "months": date[1]-birthdate[1], "days": date[0]-birthdate[0]}
        if age["years"] > vaccines[vaccine]["min_age"]:
            return True
        elif age["years"] == vaccines[vaccine]["min_age"]:
            if age["months"] > 0:
                return True
            elif age["months"] == 0 and age["days"] >= 0:
                return True
        else:
            return False
    else:
        return True

# Check if vaccine is on exclude list
def check_vaccine_not_excluded(chat, vaccine_name):
    if "vaccines" in chats[chat] and vaccine_name in chats[chat]["vaccines"] and not chats[chat]["vaccines"][vaccine_name]:
        return False
    else:
        return True

## Main program

if __name__ == "__main__":
    telegram_bot_token = ""

    if len(sys.argv) > 1:
        telegram_bot_token = sys.argv[1]
    elif not telegram_bot_token:
        print("Bot token required")
        sys.exit(1)

    # Locate config file
    config_path = os.path.join(os.path.dirname(__file__), "config.yml")
    try:
        with open(config_path, "r") as config_file:
            config = yaml.load(config_file, Loader=yaml.FullLoader)
            chats = config["chats"]
    except:
        config = {}
        chats = {}

    # Create telegram bot updater
    updater = Updater(token=telegram_bot_token)
    dispatcher = updater.dispatcher

    # Define bot commands
    dispatcher.add_handler(CommandHandler('start', start, run_async = True))
    dispatcher.add_handler(CommandHandler('plz', set_zip_code, run_async = True))
    dispatcher.add_handler(CommandHandler('status', status_update, run_async = True))
    dispatcher.add_handler(CommandHandler('birthdate', set_birthdate, run_async = True))
    dispatcher.add_handler(CommandHandler('exclude', exclude_vaccine, run_async = True))
    dispatcher.add_handler(CommandHandler('include', include_vaccine, run_async = True))
    dispatcher.add_handler(CommandHandler('vaccines', vaccine_info, run_async = True))

    with concurrent.futures.ThreadPoolExecutor() as executor:
        available = {}
        for chat in chats:
            available[chat] = False

        # Resume monitoring processes
        monitoring = []
        # Set comprehension because each zip code should only have one agent
        for zip_code in {chats[chat]["zip_code"] for chat in chats}:
            monitoring.append(zip_code)
            executor.submit(deploy_agent, zip_code)

        # Get vaccine list and update every hour
        vaccines = get_vaccines()
        executor.submit(update_vaccines, 3600)

        # Start listening
        updater.start_polling()