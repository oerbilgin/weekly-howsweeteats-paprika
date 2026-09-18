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
import argparse
from pathlib import Path

logger = logging.getLogger(__name__)

load_dotenv()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = os.getenv("TELEGRAM_IDS")


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

    recipe_url = a.get("href")
    if not isinstance(recipe_url, str):
        raise RecipeException(
            f"The 'href' attribute was a '{type(recipe_url)}' not a string: {recipe_url}"
        )

    if recipe_url:
        recipe_response = requests.get(recipe_url, headers=HEADERS)
        try:
            recipe_response.raise_for_status()
        except Exception as e:
            raise RecipeException(
                f"Got a bad response from recipe_url '{recipe_url}'!"
            ) from e

        recipe_soup = BeautifulSoup(recipe_response.text, "html.parser")
        ingredients_div = recipe_soup.find("div", class_="wprm-recipe-ingredient-group")
        if ingredients_div:
            ingredients_list = [li.text for li in ingredients_div.find_all("li")]
        else:
            raise RecipeException(
                f"recipe from element {a} had no div with class 'wprm-recipe-ingredient-group'!"
            )

        instructions_div = recipe_soup.find(
            "div", class_="wprm-recipe-instruction-group"
        )
        if instructions_div:
            instructions_list = [li.text for li in instructions_div.find_all("li")]
        else:
            raise RecipeException(
                f"recipe from element {a} had no div with class 'wprm-recipe-instruction-group'!"
            )

        return Recipe(
            name=a.text, ingredients=ingredients_list, instructions=instructions_list
        )
    else:
        raise RecipeException(f"Element {a} had no 'href' attribute!")


def _try_url(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS)
    try:
        r.raise_for_status()
    except Exception as e:
        raise RecipeException(f"Got a bad response code for url '{url}'!") from e
    return r


def get_recipes(url: str) -> list[Recipe]:
    r = _try_url(url)

    soup = BeautifulSoup(r.text, "html.parser")
    div = soup.find("div", class_="post-content")
    if div:
        all_recipes: list[Recipe] = []
        for a in div.find_all("a"):
            all_recipes.append(get_recipe_data(a))
        return all_recipes
    else:
        raise RecipeException(f"Could not find a div with class 'post-content'!")


def write_recipes_json(my_recipes: list[Recipe]) -> Path:
    """writes all the recipes for the week into json files and zips them"""
    date = datetime.now().strftime("%Y-%m-%d")

    filename = Path(f"./recipes/{date}.paprikarecipes")
    filename.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(filename.absolute(), "w", zipfile.ZIP_DEFLATED) as zipf:
        for recipe in my_recipes:
            to_save = {
                "name": recipe.name,
                "ingredients": "\n".join(recipe.ingredients),
                "directions": "\n\n".join(recipe.instructions),
            }

            # Convert the dictionary to a clean JSON string
            json_data = json.dumps(to_save, indent=2)

            # Give each internal file a unique name inside the zip
            internal_filename = f"{recipe.name}.paprikarecipe"

            # Write the JSON text straight into the zip archive
            zipf.writestr(internal_filename, json_data)

    return filename


def send_via_telegram(
    date: str, filename: Path, bot_token: str, chat_ids: list[int]
) -> None:
    """sends a file via telegram"""
    base_url = f"https://api.telegram.org/bot{bot_token}"

    for chat_id in chat_ids:
        payload = {"chat_id": chat_id}

        response = requests.post(
            base_url + "/sendMessage",
            data=payload | {"text": f"Recipes for week of {date}"},
        )
        if response.status_code >= 300:
            raise TelegramSendError(
                f"Error sending first message to chat_id '{chat_id}'"
            )

        # Telegram API endpoint for sending documents/files
        url = base_url + "/sendDocument"

        with open(filename.absolute(), "rb") as file:
            files = {"document": file}
            response = requests.post(url, data=payload, files=files)

        if response.status_code >= 300:
            raise TelegramSendError(f"Error sending recipe file to chat_id '{chat_id}'")


def parse_args():
    """Defines and parses the command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrapes HowSweetEats for a week's recipes"
    )

    # Define arguments here
    parser.add_argument(
        "--date", type=str, help="The Sunday to scrape, in format YYYY-MM-DD"
    )
    parser.add_argument("--debug", action="store_true")

    parser.add_argument("--dry", action="store_true")

    return parser.parse_args()


def get_latest_post_url_from_index(url: str) -> str:
    r = _try_url(url)
    soup = BeautifulSoup(r.text, "html.parser")
    div = soup.find("div", class_="archive-post")
    if not div:
        raise RecipeException(
            f"Could not find the div `archive-post` in the url '{url}'!"
        )

    first_a = div.find("a")
    if not first_a:
        raise RecipeException(
            f"Could not find any `a` elements in in the `archive-post` div in the url '{url}'!"
        )

    post_url = first_a.get("href")
    if not isinstance(post_url, str):
        raise RecipeException(
            f"The 'href' attribute was a '{type(post_url)}' not a string: {post_url}"
        )

    return post_url


def construct_url(dt: datetime | None) -> str:
    base_url = "https://www.howsweeteats.com/"
    if dt is not None:
        route = dt.strftime("%Y/%m/what-to-eat-this-week-%-m-%-d-%y/")
        url = base_url + route
    else:
        # infer from the what to eat this week page
        index_url = base_url + "what-to-eat-this-week/"
        url = get_latest_post_url_from_index(index_url)
    return url


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )
    logger.info("Starting a new scrape")
    try:
        args = parse_args()

        if args.debug:
            logger.setLevel(logging.DEBUG)
            logger.debug(f"Got args: {args}")

        if args.date:
            try:
                dt = datetime.strptime(args.date, "%Y-%m-%d")
            except ValueError:
                logger.error(
                    f"The input date '{args.date}' does not match the format YYYY-MM-DD"
                )
                return
            date = dt.strftime("%Y-%m-%d")
        else:
            dt = None
            # today's date
            date = datetime.now().strftime("%Y-%m-%d")

        logger.debug(f"`dt`: {dt}, `date`: {date}")

        url = construct_url(dt)

        if not CHAT_IDS:
            raise OSError(
                f"TELEGRAM_IDS parsed into an empty list: '{os.getenv('TELEGRAM_IDS')}'"
            )
        else:
            chat_id_list = [int(x) for x in CHAT_IDS.split(",")]
        if not BOT_TOKEN:
            raise OSError("BOT_TOKEN must be specified in the environment!")

        logger.info(f"Scraping recipes from url: '{url}'")
        my_recipes = get_recipes(url)
        logger.info(f"Got {len(my_recipes)} recipes.")

        filename = write_recipes_json(my_recipes)
        logger.debug(f"`filename`: {filename}")

        if args.dry:
            logger.info("Dry run, so not sending to telegram. Recipes:")
            for r in my_recipes:
                logger.info(r.name)
                logger.debug(r)
        else:
            logger.info("Sending via Telegram")
            send_via_telegram(
                date=date,
                filename=filename,
                bot_token=BOT_TOKEN,
                chat_ids=chat_id_list,
            )
        logger.info("Recipe scrape finished.")
    except Exception:
        logger.exception("Uncaught exception when running the scraper.")


if __name__ == "__main__":
    main()
