#!/bin/python3
import asyncio
import logging
import os
# import random
import re
from configparser import ConfigParser

from helpers import get_slack_block_item, get_slack_blocks_items, update_item
from models import Base, Credential, Item, Subscription, User
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tgtg import TgtgClient

STARTING_DELAY = 15

engine = create_engine("sqlite:///state.db", echo=True)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

# Log info to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

# Read config
script_dir = os.path.dirname(os.path.realpath(__file__))
project_dir = os.path.dirname(script_dir)
config_file = f"{project_dir}/config.ini"
config = ConfigParser()
config.read(config_file)

app = AsyncApp(token=config["slack"]["bot_token"])

delay = STARTING_DELAY


def set_delay(t=STARTING_DELAY):
    global delay
    delay = t


def get_tgtg_client():
    # agent = f"TGTG/22.2.1 Dalvik/2.1.0 (Linux; U; Android 9; SM-G955F Build/PPR1.{int(random.random() * 1000)}.{int(random.random() * 1000)})"
    # logging.info(f"get_tgtg_client: New user agent: {agent}")

    session = Session()
    credential = session.query(Credential).one_or_none()

    if credential is None:
        client = TgtgClient(email=config["tgtg"]["email"])
        new_credential = client.get_credentials()
        logging.info(f"new client new_credential: {new_credential}")

        credential = Credential(**new_credential)
        session.add(credential)
        session.commit()
    else:
        logging.info(f"fetched client credentials from state")
    return TgtgClient(
            access_token=credential.access_token,
            refresh_token=credential.refresh_token,
            user_id=credential.user_id,
            cookie=credential.cookie,
    )


tgtg_client = get_tgtg_client()


subscribe_re = re.compile(r"^subscribe_([0-9]{1,8})")


@app.action(subscribe_re)
async def subscribe(ack, body, logger):
    logger.info(f"subscribe: {subscribe_re}")
    for action in body["actions"]:
        regex_match = subscribe_re.search(action["action_id"])
        if not regex_match:
            continue
        item_id = int(regex_match.group(1))

        tgtg_client.set_favorite(item_id=item_id, is_favorite=True)

        session = Session()
        user = (
            session.query(User)
            .filter(User.slack_id == body["user"]["id"])
            .one_or_none()
        )
        if not user:
            user = User(slack_id=body["user"]["id"])
            session.add(user)
        item = session.query(Item).filter(Item.id == item_id).one_or_none()
        if not item:
            item = Item(id=item_id)
            session.add(item)
        user.items.append(item)
        session.commit()
    # await say(f"Subscribed to {item_id}")
    await ack()
    logger.info(body)


unsubscribe_re = re.compile(r"^unsubscribe_([0-9]{1,8})")


@app.action(unsubscribe_re)
async def unsubscribe(ack, say, body, logger):
    logger.info(f"unsubscribe: {unsubscribe_re}")
    for action in body["actions"]:
        regex_match = unsubscribe_re.search(action["action_id"])
        if not regex_match:
            continue
        item_id = int(regex_match.group(1))

        # tgtg_client.set_favorite(item_id=item_id, is_favorite=True)

        session = Session()
        user = (
            session.query(User)
            .filter(User.slack_id == body["user"]["id"])
            .one_or_none()
        )
        if not user:
            logger.info("unsubscribe: User doesn't exist... not unsubscribing")
            break
        subscriptions = session.query(Subscription).filter_by(
            item_id=item_id, user_id=user.id
        )
        # description = "".join([str(sub) for sub in subscriptions.all()])
        if subscriptions.first() is None:
            logger.info("unsubscribe: Subscription doesn't exist... not unsubscribing")
            break
        subscriptions.delete()
        item = session.query(Item).filter_by(id=item_id).one_or_none()
        logger.info(
            f"unsubscribe: {user.slack_id} unsubscribed from {item.display_name}"
        )
        await say(f"Unsubscribed from {item.display_name}")
        session.commit()
    await ack()
    logger.info(body)


list_re = re.compile(r"(?i)^list( all)?$")


@app.message(list_re)
async def list(message, say):
    regex_match = list_re.match(message["text"])
    if not regex_match:
        return
    list_all = regex_match.group(1) != None

    session = Session()
    user = session.query(User).filter(User.slack_id == message["user"]).one_or_none()

    subscriptions = user.items if user else []

    if not list_all and subscriptions:
        subscriptions = [item for item in subscriptions if item.quantity > 0]

    await say(
        text="You are subscribed to the following items...",
        blocks=get_slack_blocks_items(
            subscriptions,
            f"You are subscribed to the following items",
            subscribed_all=True,
        ),
    )


search_re = re.compile(r"(?i)^search (.*)$")


@app.message(search_re)
async def search(message, say):
    regex_match = search_re.search(message["text"])
    if not regex_match:
        return
    search_s = regex_match.group(1)
    update = search_s == "update"

    if update:
        search_items = tgtg_client.get_items(page_size=100)
    else:
        search_items = tgtg_client.get_items(
            page_size=10,
            discover=True,
            favorites_only=False,
            search_phrase=search_s,
            longitude=-71.06,
            latitude=42.36,
        )

    # Store items to db so names are stored
    session = Session()
    existing = session.query(Item).filter(
        Item.id.in_([item["item"]["item_id"] for item in search_items])
    )
    existing_map = {item.id: item for item in existing}
    items = []
    for item in search_items:
        db_item = existing_map.get(int(item["item"]["item_id"]), None)
        if not db_item:
            db_item = Item(id=int(item["item"]["item_id"]))
            session.add(db_item)
        update_item(db_item, item)
        items.append(db_item)
    session.commit()

    if update:
        await say(f"Updated {len(items)} items")
        return

    user = session.query(User).filter(User.slack_id == message["user"]).one_or_none()
    subscribed_items = user.items if user else []

    start_text = f"*Search results for:* {search_s}"
    await say(
        text=f"{start_text} ...",
        blocks=get_slack_blocks_items(
            items, start_text, subscribed_items=subscribed_items
        ),
    )


help_re = re.compile(r"(?i)^help$")


@app.message(help_re)
async def help(_, say):
    await say(
        text=f"List of available commands: ...",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "List of available commands:"},
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": """
`list [all]`: List subscribed items with bags available or *all* subscribed items
`search [string]`: Search for items matching *string*
Tap `Subscribe` or `Unsubscribe` to get notifications from an item
""",
                },
            },
        ],
    )


catchall_re = re.compile(r".*")


@app.message(catchall_re)
async def catchall(message, say):
    await say(f"Invalid command: {message['text']}, `help` for more options")


@app.event("team_join")
async def first_message(_, say):
    text = f"Welcome to tgtg notifications, send `help` for more information"
    say(text=text)


async def cycle():
    # Try this at the beginning of each cycle
    tgtg_client = get_tgtg_client()
    try:
        new_items = tgtg_client.get_items(page_size=100, with_stock_only=True)
    except Exception as e:
        debug_user = config["slack"]["debug_user"]
        logging.exception(f"Failed to get items, notifying {debug_user}, {e}")
        await app.client.chat_postMessage(
            channel=debug_user, user=debug_user, text=f"TgtgAPIError: {e}"
        )
        set_delay(delay * 2)
        return

    set_delay()

    # Key new items by item_id as integer
    new_items = {int(item["item"]["item_id"]): item for item in new_items}

    session = Session()
    items = session.query(Item)

    # Set empty items to quantity 0
    items.filter(Item.id.not_in(new_items.keys())).update({"quantity": 0})

    notify_items = []

    # Apply changes
    relevant_items = items.filter(Item.id.in_(new_items.keys())).all()
    # Key database items with item id
    relevant_items = {item.id: item for item in relevant_items}
    logging.info(
        f"fetched {len(new_items)} new items and {len(relevant_items)} existing items"
    )
    # Loop through the new items found
    for item_id, new_item in new_items.items():
        new_quantity = new_item["items_available"]
        prev_quantity = 0
        if item_id not in relevant_items.keys():
            # New item -> add to db
            item = Item(
                id=item_id,
                display_name=new_item["store"]["store_name"],
                quantity=new_quantity,
            )
            session.add(item)
        else:
            # Existing item -> get previous quantity and update new quantity
            item = session.query(Item).get(item_id)
            prev_quantity = item.quantity
            item.quantity = new_quantity
        if prev_quantity == 0 and new_quantity > 0:
            # Notify item if it was zero and is now nonzero
            notify_items.append(item)

    print(notify_items)
    for item in notify_items:
        # Get the users subscribed to the item
        user_query = (
            session.query(User.slack_id)
            .join(Subscription, User.id == Subscription.user_id)
            .filter(Subscription.item_id == item.id)
        )
        user_ids = session.scalars(user_query).all()

        for user_id in user_ids:
            logging.info(f"Notifying {user_id}, ({item.display_name}, {item.quantity})")
            await app.client.chat_postMessage(
                text=f"{item.display_name} has {item.quantity}",
                blocks=get_slack_block_item(item=item, subscribed=True),
                channel=user_id,
                user=user_id,
            )

    session.commit()


async def poll_loop():
    while True:
        await cycle()
        await asyncio.sleep(delay)


async def main():
    logging.info("Starting main")
    handler = AsyncSocketModeHandler(app, config["slack"]["app_token"])
    await asyncio.gather(handler.start_async(), poll_loop())


if __name__ == "__main__":
    asyncio.run(main())
