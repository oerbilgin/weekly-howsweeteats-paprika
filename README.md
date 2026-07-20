# Weekly How Sweet Eats --> Paprika Parser

Jessica posts weekly menus to her [website](https://www.howsweeteats.com), and we wanted them to be easily imported into Paprika.

## Telegram setup
1. Download Telegram App
1. Get your Telegram ID
    1. Send message to `@userinfobot`. Save this and whoever else you want to subscribe to the `TELEGRAM_IDS` envvar.
1. Create your telegram bot
    1. Send a message to `@botfather`: `/newbot`
    1. Follow instructions to name your bot
    1. Save the token the botfather gives you to the `TELEGRAM_BOT_TOKEN` envvar.

## Usage notes
- Jessica posts the weekly recipes every Sunday, so run the script as a cron job every Sunday night
- The weekly recipes follow a procedurally generated URL: (strftime) `https://www.howsweeteats.com/%Y/%m/what-to-eat-this-week-%-m-%-d-%y/` but that may change in the future

## Known Issues / TODO
- Jessica will reuse recipes in her weekly menus, and this script may create duplicate recipes in paprika... not sure yet.