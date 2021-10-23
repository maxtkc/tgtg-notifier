#!/bin/python3
from configparser import ConfigParser
from slack_sdk import WebClient
from tgtg import TgtgClient
import json
import os
import time
import logging

# Log info to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def main():
    logging.info("Starting main")
    script_dir = os.path.dirname(os.path.realpath(__file__))
    project_dir = os.path.dirname(script_dir)
    config_file = f"{project_dir}/config.ini"
    cache_file = f"{project_dir}/cache.json"

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

    # Load cache
    cache = {}
    try:
        with open(cache_file) as f:
            cache = json.load(f)
    except Exception:
        logging.info("Creating new cache")

    while True:
        try:
            new_cache = {}
            new_items = tgtg_client.get_items(page_size=100, with_stock_only=True)
            logging.info(
                f"updating with {len(new_items)} items (cache: {len(cache.keys())})"
            )
            for item in new_items:
                item_id = item["item"]["item_id"]
                items_available = item["items_available"]

                if items_available > cache.get(item_id, 0):
                    store_name = item["store"]["store_name"]
                    store_branch = item["store"].get("store_branch", None)
                    combined_name = (
                        f"{store_name} - {store_branch}" if store_branch else store_name
                    )
                    logging.info(
                        f"notifying {combined_name} of {items_available} bags"
                    )
                    if slack_client:
                        slack_client.chat_postMessage(
                            channel=config["slack"]["channel"],
                            text=f"{combined_name} has {items_available} bags",
                        )

                new_cache[item_id] = items_available
            cache = new_cache
            with open(cache_file, "w") as f:
                json.dump(new_cache, f)
        except Exception as e:
            logging.error(f"Failed with {e}")
        time.sleep(15)


if __name__ == "__main__":
    main()
