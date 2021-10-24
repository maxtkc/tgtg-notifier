#!/bin/python3

from configparser import ConfigParser
from slack_sdk.web.client import WebClient
from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from tgtg import TgtgClient
import logging
import os
import sqlalchemy
import time

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

    slack_client = None
    if "slack" in config:
        token = config["slack"]["token"]
        slack_client = WebClient(token=token)
        slack_client.conversations_join(channel=config["slack"]["channel"])

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
                            # if slack_client:
                            #     slack_client.chat_postMessage(
                            #         channel=config["slack"]["channel"],
                            #         text=f"{display_name} has {items_available} bags",
                            #     )

                        new_cache.append(Cache(item_id=item_id, n_bags=items_available))

                    session.query(Cache).delete()
                    for cache_item in new_cache:
                        session.add(cache_item)
            except Exception as e:
                logging.error(f"Failed with {e}")
            time.sleep(15)


if __name__ == "__main__":
    main()
