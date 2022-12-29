#!/bin/python3
import asyncio
import logging
import os
import random
import re
from configparser import ConfigParser

from helpers import get_slack_blocks_items, update_item
from models import Base, Item, Subscription, User
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tgtg import TgtgClient

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

delay = 60


def set_delay(t=60):
    global delay
    delay = t


def get_tgtg_client():
    return TgtgClient(
        access_token=config["tgtg"]["access_token"],
        refresh_token=config["tgtg"]["refresh_token"],
        user_id=config["tgtg"]["user_id"],
        user_agent=f"TGTG/22.2.1 Dalvik/2.1.0 (Linux; U; Android 9; SM-G955F Build/PPR1.180610.{int(random.random() * 1000)})",
    )


tgtg_client = get_tgtg_client()


subscribe_re = re.compile(r"subscribe_([0-9]{1,8})")


@app.action(subscribe_re)
async def subscribe(ack, body, logger):
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
        blocks=get_slack_blocks_items(
            subscriptions,
            f"You are subscribed to the folowing items",
            subscribed_all=True,
        )
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

    await say(blocks=get_slack_blocks_items(items, f"*Search results for:* {search_s}"))


catchall_re = re.compile(r".*")


@app.message(catchall_re)
async def catchall(message, say):
    await say(f"Invalid command: {message['text']}, *help* for more options")


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

    new_items = {int(item["item"]["item_id"]): item for item in new_items}

    session = Session()
    items = session.query(Item)
    # Remove empty items
    items.filter(Item.id.not_in(new_items.keys())).update({"quantity": 0})

    notify_items = []

    # Apply changes
    relevant_items = items.filter(Item.id.in_(new_items.keys())).all()
    relevant_items = {item.id: item for item in relevant_items}
    logging.info(
        f"fetched {len(new_items)} new items and {len(relevant_items)} existing items"
    )
    for item_id, new_item in new_items.items():
        new_quantity = new_item["items_available"]
        prev_quantity = 0
        if item_id not in relevant_items.keys():
            # New item
            item = Item(
                id=item_id,
                display_name=new_item["store"]["store_name"],
                quantity=new_quantity,
            )
            session.add(item)
        else:
            # Existing item
            item = session.query(Item).get(item_id)
            prev_quantity = item.quantity
            item.quantity = new_quantity
        if prev_quantity == 0:
            # Notify item
            notify_items.append(new_item)

    for item in notify_items:
        users = (
            session.query(User)
            .filter(Subscription.item_id == item["item"]["item_id"])
            .all()
        )
        user_ids = [user.slack_id for user in users]

        name = item["store"]["store_name"]
        quantity = item["items_available"]

        for user_id in user_ids:
            logging.info(f"Notifying {user_id}, ({name}, {quantity})")
            await app.client.chat_postMessage(
                channel=user_id, user=user_id, text=f"{name} has {quantity}"
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
