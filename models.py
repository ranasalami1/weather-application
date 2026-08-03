from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(
        db.String(50),
        nullable=False,
        unique=True,
    )
    email = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
    )
    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False,
    )

    favorites = db.relationship(
        "Favorite",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    search_history = db.relationship(
        "SearchHistory",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class City(db.Model):
    __tablename__ = "cities"

    id = db.Column(db.Integer, primary_key=True)

    city_name = db.Column(
        db.String(100),
        nullable=False,
    )

    country_code = db.Column(
        db.String(10),
        nullable=False,
    )

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    favorites = db.relationship(
        "Favorite",
        back_populates="city",
        cascade="all, delete-orphan",
    )

    search_history = db.relationship(
        "SearchHistory",
        back_populates="city",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "city_name",
            "country_code",
            name="unique_city_country",
        ),
    )


class Favorite(db.Model):
    __tablename__ = "favorites"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    city_id = db.Column(
        db.Integer,
        db.ForeignKey("cities.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False,
    )

    user = db.relationship(
        "User",
        back_populates="favorites",
    )

    city = db.relationship(
        "City",
        back_populates="favorites",
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "city_id",
            name="unique_user_favorite_city",
        ),
    )


class SearchHistory(db.Model):
    __tablename__ = "search_history"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    city_id = db.Column(
        db.Integer,
        db.ForeignKey("cities.id", ondelete="CASCADE"),
        nullable=False,
    )

    searched_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False,
    )

    user = db.relationship(
        "User",
        back_populates="search_history",
    )

    city = db.relationship(
        "City",
        back_populates="search_history",
    )


class WeatherAlert(db.Model):
    __tablename__ = "weather_alerts"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title = db.Column(
        db.String(100),
        nullable=False,
    )

    message = db.Column(
        db.String(255),
        nullable=False,
    )

    alert_type = db.Column(
        db.String(50),
        nullable=False,
    )

    is_read = db.Column(
        db.Boolean,
        default=False,
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        nullable=False,
    )


class WeatherCache(db.Model):
    __tablename__ = "weather_cache"

    id = db.Column(db.Integer, primary_key=True)

    city_id = db.Column(
        db.Integer,
        db.ForeignKey("cities.id", ondelete="CASCADE"),
        nullable=False,
    )

    temperature = db.Column(
        db.Float,
        nullable=False,
    )

    humidity = db.Column(
        db.Integer,
        nullable=False,
    )

    wind_speed = db.Column(
        db.Float,
        nullable=False,
    )

    pressure = db.Column(
        db.Integer,
        nullable=False,
    )

    description = db.Column(
        db.String(100),
        nullable=False,
    )

    icon = db.Column(db.String(20))

    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False,
    )

    