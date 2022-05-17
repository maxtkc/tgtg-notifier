## config

- slack bot token
- slack app token

- tgtg access token
- tgtg refresh token

- tgtg user id

## state (preserved, db)

- table of items (item id, latest quantity, item name, possible other data values)
- table of users (user id, possible other metadata)
- table of subscriptions <-> users (item id, user id)

## poll every 15 seconds

- state = get_items
- changes = newstate - state
- save newstate
- for each change
    - find members subscribed
    - notify members

## slack: search

- @tgtg-bot search foo
- uses list items 
- returns stores and items with item ids

## slack: subscribe

- @tgtg-bot subscribe 123
- call set favorite
- add or get item to table of items
- add subscription to user
- returns success or failure

## slack: unsubscribe

- @tgtg-bot unsubscribe 123
- remove subscription to user
- (optional) check if any subscriptions still exist and if not, remove favorite
- returns success or failure

## slack: list

- @tgtg-bot list
- get subscribed items and their attributes
- return items and attributes

## TODO

- add locations to names
- dockerize properly
- working unsubscribe button on list
- figure out how to handle bon chon
- more options for search
- add map (for subscribing or something)
- add badges

## DONE
- set up with dm
- subscribe button on search
- nicer looking items in chat (with picture, etc)
