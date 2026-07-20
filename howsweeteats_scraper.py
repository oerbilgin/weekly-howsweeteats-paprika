import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from datetime import datetime
from dataclasses import dataclass
from dotenv import load_dotenv
import os
import zipfile
import json
import logging

logger = logging.getLogger(__name__)

load_dotenv()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = [int(x) for x in os.getenv("TELEGRAM_IDS", "").split(',')]


@dataclass
class Recipe:
    name: str
    ingredients: list[str]
    instructions: list[str]

@dataclass
class RecipeList:
    recipes: list[Recipe]

class RecipeException(Exception):
    pass

class TelegramSendError(Exception):
    pass

def get_recipe_data(a: Tag) -> Recipe:

    recipe_url = a.get('href')
    if not isinstance(recipe_url, str):
        raise RecipeException(f"The 'href' attribute was a '{type(recipe_url)}' not a string: {recipe_url}")

    if recipe_url:
        recipe_response = requests.get(recipe_url, headers=HEADERS)
        try:
            recipe_response.raise_for_status()
        except Exception as e:
            raise RecipeException(f"Got a bad response from recipe_url '{recipe_url}'!") from e

        recipe_soup = BeautifulSoup(recipe_response.text, 'html.parser')
        ingredients_div = recipe_soup.find('div', class_="wprm-recipe-ingredient-group")
        if ingredients_div:
            ingredients_list = [li.text for li in ingredients_div.find_all('li')]
        else:
            raise RecipeException(f"recipe from element {a} had no div with class 'wprm-recipe-ingredient-group'!")

        instructions_div = recipe_soup.find('div', class_="wprm-recipe-instruction-group")
        if instructions_div:
            instructions_list = [li.text for li in instructions_div.find_all('li')]
        else:
            raise RecipeException(f"recipe from element {a} had no div with class 'wprm-recipe-instruction-group'!")
        
        return Recipe(
            name=a.text,
            ingredients=ingredients_list,
            instructions=instructions_list
        )
    else:
        raise RecipeException(f"Element {a} had no 'href' attribute!")

def get_recipes(url:str) -> list[Recipe]:
    r = requests.get(url, headers=HEADERS)
    try:
        r.raise_for_status()
    except Exception as e:
        raise RecipeException(f"Got a bad response code for url '{url}'!") from e
    
    soup = BeautifulSoup(r.text, 'html.parser')
    div = soup.find('div', class_="post-content")
    if div:
        all_recipes: list[Recipe] = []
        for a in div.find_all('a'):
            all_recipes.append(get_recipe_data(a))
        return all_recipes
    else:
        raise RecipeException(f"Could not find a div with class 'post-content'!")
    

def write_recipes_json(my_recipes: list[Recipe]) -> str:
    """writes all the recipes for the week into json files and zips them"""
    date = datetime.now().strftime('%Y-%m-%d')

    filename = f"./recipes/{date}.paprikarecipes"

    with zipfile.ZipFile(filename, 'w', zipfile.ZIP_DEFLATED) as zipf:

        for recipe in my_recipes:
            to_save = {
                "name": recipe.name,
                "ingredients": '\n'.join(recipe.ingredients),
                "directions": '\n\n'.join(recipe.instructions),
            }

            # Convert the dictionary to a clean JSON string
            json_data = json.dumps(to_save, indent=2)
            
            # Give each internal file a unique name inside the zip
            internal_filename = f"{recipe.name}.paprikarecipe"
            
            # Write the JSON text straight into the zip archive
            zipf.writestr(internal_filename, json_data)

    return filename

def send_via_telegram(date: str, filename:str, bot_token:str, chat_ids:list[int]) -> None:
    """sends a file via telegram"""
    base_url = f"https://api.telegram.org/bot{bot_token}"
    
    for chat_id in chat_ids:
        payload = {"chat_id": chat_id}
        

        response = requests.post(base_url + "/sendMessage", data=payload | {"text": f"Recipes for week of {date}"})
        if response.status_code >= 300:
            raise TelegramSendError(f"Error sending first message to chat_id '{chat_id}'")

        # Telegram API endpoint for sending documents/files
        url = base_url + "/sendDocument"

        with open(filename, "rb") as file:
            files = {"document": file}
            response = requests.post(url, data=payload, files=files)

        if response.status_code >= 300:
            raise TelegramSendError(f"Error sending recipe file to chat_id '{chat_id}'")
    
def main(url:str | None = None):
    if not url:
        base_url = "https://www.howsweeteats.com/"
        route = datetime.now().strftime("%Y/%m/what-to-eat-this-week-%-m-%-d-%y/")
        url = base_url + route
    date = datetime.now().strftime('%Y-%m-%d')
    if not CHAT_IDS:
        raise EnvironmentError(f"TELEGRAM_IDS parsed into an empty list: '{os.getenv("TELEGRAM_IDS")}'")
    if not BOT_TOKEN:
        raise EnvironmentError(f"BOT_TOKEN must be specified in the environment!")

    my_recipes = get_recipes(url)
    filename = write_recipes_json(my_recipes)

    send_via_telegram(date=date, filename=filename, bot_token=BOT_TOKEN, chat_ids=CHAT_IDS)

if __name__ == "__main__":
    main()