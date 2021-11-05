#!/bin/python3

import logging
import os
import time
from configparser import ConfigParser

import sqlalchemy
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient
from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from tgtg import TgtgClient

# Log info to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

Base = declarative_base()


class Cache(Base):
    __tablename__ = "cache"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, nullable=False, unique=True)
    n_bags = Column(Integer, nullable=False)


# class User(Base):
#     __tablename__ = "users"
#
#     id = Column(Integer, primary_key=True)
#     username = Column(String, nullable=False)
#
#
# class Subscription(Base):
#     __tablename__ = "subscriptions"
#
#     id = Column(Integer, primary_key=True)
#     user = Column(Integer, ForeignKey("user.id"))
#     item_id = Column(Integer, nullable=False)

def subscribe_to_item(session, user, item_id)


def main():
    logging.info("Starting main")
    script_dir = os.path.dirname(os.path.realpath(__file__))
    project_dir = os.path.dirname(script_dir)
    db_file = f"{project_dir}/state.sqlite"
    engine = sqlalchemy.create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    config_file = f"{project_dir}/config.ini"

    config = ConfigParser()
    config.read(config_file)

    tgtg_client = TgtgClient(
        email=config["tgtg"]["email"], password=config["tgtg"]["password"]
    )

    web_client = None
    if "slack" in config:
        web_token = config["slack"]["web_token"]
        socket_token = config["slack"]["socket_token"]
        web_client = WebClient(token=web_token)
        web_client.conversations_join(channel=config["slack"]["channel"])
        # Initialize SocketModeClient with an app-level token + WebClient
        socket_client = SocketModeClient(
            # This app-level token will be used only for establishing a connection
            app_token=socket_token,  # xapp-A111-222-xyz
            # You will be using this WebClient for performing Web API calls in listeners
            web_client=web_client,  # xoxb-111-222-xyz
        )

        def process(client: SocketModeClient, req: SocketModeRequest):
            print("HELLO", flush=True)
            print(req, flush=True)
            print(req.type, flush=True)
            print(req.payload, flush=True)
            if req.type == "slash_commands":
                command = req.payload["command"]
                if command == "/subscribe":
                    response = SocketModeResponse(envelope_id=req.envelope_id)
                    client.send_socket_mode_response(response)
                    subscription = req.payload["text"]
                    message = ""
                    try:
                        subscription = int(subscription)
                        # TODO: Actually subscribe
                        message = f"Subscribed to item {subscription}"
                    except ValueError:
                        message = "Failed to subscribe to item"
                    web_client.chat_postEphemeral(
                        channel=config["slack"]["channel"],
                        user=req.payload["user_id"],
                        text=message,
                    )

            elif req.type == "events_api":
                # Acknowledge the request anyway
                response = SocketModeResponse(envelope_id=req.envelope_id)
                client.send_socket_mode_response(response)

                # Add a reaction to the message if it's a new message
                if (
                    req.payload["event"]["type"] == "message"
                    and req.payload["event"].get("subtype") is None
                ):
                    client.web_client.reactions_add(
                        name="eyes",
                        channel=req.payload["event"]["channel"],
                        timestamp=req.payload["event"]["ts"],
                    )

        socket_client.socket_mode_request_listeners.append(process)
        logging.info(socket_client.socket_mode_request_listeners)
        logging.info("About to connect")
        socket_client.connect()
        logging.info("Connected")

    with Session(engine) as session:
        while True:
            try:
                with session.begin():
                    new_items = tgtg_client.get_items(
                        page_size=100, with_stock_only=True
                    )
                    cached_items = session.query(Cache).filter(Cache.n_bags > 0).count()
                    logging.info(
                        f"updating with {len(new_items)} items (cache: {cached_items})"
                    )
                    new_cache = []
                    for item in new_items:
                        item_id = item["item"]["item_id"]
                        items_available = item["items_available"]

                        cached = (
                            session.query(Cache)
                            .filter(Cache.item_id == item_id)
                            .one_or_none()
                        )
                        if items_available > 0 and (
                            cached is None or cached.n_bags == 0
                        ):
                            display_name = item["display_name"]
                            logging.info(
                                f"notifying {display_name} of {items_available} bags"
                            )
                            if web_client:
                                web_client.chat_postMessage(
                                    channel=config["slack"]["channel"],
                                    text=f"{display_name} has {items_available} bags",
                                )

                        new_cache.append(Cache(item_id=item_id, n_bags=items_available))

                    session.query(Cache).delete()
                    for cache_item in new_cache:
                        session.add(cache_item)
            except Exception as e:
                logging.error(f"Failed with {e}")
            time.sleep(15)


if __name__ == "__main__":
    main()
