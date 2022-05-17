def get_price_s(minor_units: int, decimals: int):
    if not minor_units or not decimals:
        return "Unknown price"
    return f"${str(minor_units)[:decimals-1]}.{str(minor_units)[decimals-1:]}"


def get_store_display_name(store):
    return store.get("display_name", None) or (
        f"{store['store_name']} - {store['branch']}"
        if store["branch"]
        else store["store_name"]
    )


def update_item(db_item, dict_item):
    db_item.price_minor_units = int(
        dict_item["item"]["price_including_taxes"]["minor_units"]
    )
    db_item.price_decimals = int(dict_item["item"]["price_including_taxes"]["decimals"])
    db_item.description = dict_item["item"]["description"]
    db_item.logo_picture_url = dict_item["item"]["logo_picture"]["current_url"]
    # TODO add badges at some point
    # db_item.percentage = dict_item['item']['badges']['percentage']
    # db_item.user_count = dict_item['item']['badges']['user_count']
    # db_item.month_count = dict_item['item']['badges']['month_count']
    db_item.favorite_count = dict_item["item"]["favorite_count"]
    db_item.display_name = get_store_display_name(dict_item["store"])
    db_item.branch = dict_item["store"]["branch"]
    db_item.location_longitude = float(
        dict_item["pickup_location"]["location"]["longitude"]
    )
    db_item.location_latitude = float(
        dict_item["pickup_location"]["location"]["latitude"]
    )
    db_item.address = dict_item["pickup_location"]["address"]["address_line"]
    db_item.quantity = dict_item["items_available"]


def get_slack_block_item(item, subscribed=False):
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{item.display_name}* [{item.quantity}]\n{item.description}\n{get_price_s(item.price_minor_units, item.price_decimals)}",
            },
            "accessory": {
                "type": "image",
                "image_url": item.logo_picture_url,
                "alt_text": item.display_name,
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "emoji": True,
                        "text": "Unsubscribe" if subscribed else "Subscribe",
                    },
                    "value": f"unsubscribe_{item.id}"
                    if subscribed
                    else f"subscribe_{item.id}",
                    "action_id": f"unsubscribe_{item.id}"
                    if subscribed
                    else f"subscribe_{item.id}",
                }
            ],
        },
    ]


def get_slack_blocks_items(items, header_mkrdwn, subscribed_all=False):
    search_items_blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header_mkrdwn}},
        {"type": "divider"},
    ]
    for item in items:
        search_items_blocks.extend(
            get_slack_block_item(item, subscribed=subscribed_all)
        )

    search_items_blocks.append({"type": "divider"})
    return search_items_blocks
