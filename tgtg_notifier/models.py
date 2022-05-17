from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Item(Base):
    __tablename__ = "item"
    id = Column(Integer, primary_key=True)
    quantity = Column(Integer)
    price_minor_units = Column(Integer)
    price_decimals = Column(Integer)
    description = Column(String)
    logo_picture_url = Column(String)
    # TODO add badges at some point
    # percentage = Column(String)
    # user_count = Column(String)
    # month_count = Column(String)
    favorite_count = Column(String)
    display_name = Column(String)
    branch = Column(String)
    location_longitude = Column(Float)
    location_latitude = Column(Float)
    address = Column(String)
    users = relationship("User", secondary="subscription")


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    slack_id = Column(String)
    items = relationship("Item", secondary="subscription")


class Subscription(Base):
    __tablename__ = "subscription"
    item_id = Column(Integer, ForeignKey("item.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
