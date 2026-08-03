from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from models import City, Favorite, SearchHistory, User, db


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "New York")
CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
AIR_QUALITY_URL = "https://api.openweathermap.org/data/2.5/air_pollution"

app = Flask(__name__)
app.config.from_object(Config)
app.permanent_session_lifetime = timedelta(days=30)

db.init_app(app)


def login_required():
    return "user_id" in session


def api_get(url, params):
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def format_local_time(unix_timestamp, offset_seconds, format_string):
    zone = timezone(timedelta(seconds=offset_seconds))
    return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc).astimezone(zone).strftime(format_string)


def current_weather_from_data(data):
    timezone_offset = data.get("timezone", 0)
    weather_entry = (data.get("weather") or [{}])[0]
    wind_mps = data.get("wind", {}).get("speed", 0)

    return {
        "city": data.get("name", "Unknown"),
        "country": data.get("sys", {}).get("country", ""),
        "temperature": round(data.get("main", {}).get("temp", 0)),
        "feels_like": round(data.get("main", {}).get("feels_like", 0)),
        "humidity": data.get("main", {}).get("humidity", 0),
        "pressure": data.get("main", {}).get("pressure", 0),
        "description": weather_entry.get("description", "Unknown").title(),
        "icon": weather_entry.get("icon", "01d"),
        "wind_speed": round(wind_mps * 3.6),
        "visibility": round(data.get("visibility", 0) / 1000, 1),
        "latitude": data.get("coord", {}).get("lat"),
        "longitude": data.get("coord", {}).get("lon"),
        "local_time": format_local_time(
            data.get("dt", int(datetime.now(tz=timezone.utc).timestamp())),
            timezone_offset,
            "%A, %B %d · %I:%M %p",
        ),
        "sunrise": format_local_time(
            data.get("sys", {}).get("sunrise", 0),
            timezone_offset,
            "%I:%M %p",
        ),
        "sunset": format_local_time(
            data.get("sys", {}).get("sunset", 0),
            timezone_offset,
            "%I:%M %p",
        ),
        "timezone_offset": timezone_offset,
    }


def build_five_day_forecast(data):
    timezone_offset = data.get("city", {}).get("timezone", 0)
    city_zone = timezone(timedelta(seconds=timezone_offset))
    grouped = defaultdict(list)

    for item in data.get("list", []):
        local_dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc).astimezone(city_zone)
        grouped[local_dt.date()].append((local_dt, item))

    today_local = datetime.now(tz=timezone.utc).astimezone(city_zone).date()
    forecast = []

    for date_value in sorted(grouped):
        if date_value <= today_local:
            continue

        entries = grouped[date_value]
        representative_dt, representative = min(entries, key=lambda pair: abs(pair[0].hour - 12))
        temperatures = [entry["main"]["temp"] for _, entry in entries]
        weather_entry = representative.get("weather", [{}])[0]

        forecast.append(
            {
                "day": date_value.strftime("%a"),
                "date": date_value.strftime("%b %d"),
                "high": round(max(temperatures)),
                "low": round(min(temperatures)),
                "description": weather_entry.get("description", "Unknown").title(),
                "icon": weather_entry.get("icon", "01d"),
            }
        )

        if len(forecast) == 5:
            break

    return forecast


def air_quality_label(index):
    labels = {
        1: "Good",
        2: "Fair",
        3: "Moderate",
        4: "Poor",
        5: "Very Poor",
    }
    return labels.get(index, "Unavailable")



def build_weather_alerts(weather, air_quality):
    """Create simple safety alerts from the current weather data."""
    if not weather:
        return []

    alerts = []
    temperature = weather.get("temperature", 0)
    wind_speed = weather.get("wind_speed", 0)
    visibility = weather.get("visibility", 0)
    description = weather.get("description", "").lower()

    if temperature >= 35:
        alerts.append({
            "type": "danger",
            "icon": "fa-temperature-high",
            "title": "Extreme heat",
            "message": "Stay hydrated, avoid long sun exposure, and check on vulnerable people.",
        })
    elif temperature >= 30:
        alerts.append({
            "type": "warning",
            "icon": "fa-sun",
            "title": "Hot conditions",
            "message": "Use sunscreen, drink water, and limit strenuous outdoor activity.",
        })

    if temperature <= 3:
        alerts.append({
            "type": "warning",
            "icon": "fa-snowflake",
            "title": "Cold conditions",
            "message": "Wear warm layers and watch for icy surfaces.",
        })

    if wind_speed >= 50:
        alerts.append({
            "type": "danger",
            "icon": "fa-wind",
            "title": "Strong wind",
            "message": "Secure loose objects and use extra care while driving.",
        })
    elif wind_speed >= 30:
        alerts.append({
            "type": "warning",
            "icon": "fa-wind",
            "title": "Breezy weather",
            "message": "Outdoor objects may move. Take care in exposed areas.",
        })

    if any(word in description for word in ("thunderstorm", "storm")):
        alerts.append({
            "type": "danger",
            "icon": "fa-cloud-bolt",
            "title": "Thunderstorm risk",
            "message": "Move indoors and avoid open fields, tall trees, and flooded roads.",
        })
    elif any(word in description for word in ("rain", "drizzle")):
        alerts.append({
            "type": "info",
            "icon": "fa-cloud-rain",
            "title": "Rain expected",
            "message": "Carry an umbrella and allow extra travel time.",
        })
    elif "snow" in description:
        alerts.append({
            "type": "warning",
            "icon": "fa-snowflake",
            "title": "Snow conditions",
            "message": "Roads may be slippery. Drive slowly and keep extra distance.",
        })

    if visibility and visibility < 3:
        alerts.append({
            "type": "warning",
            "icon": "fa-eye-slash",
            "title": "Low visibility",
            "message": "Use headlights and reduce speed while travelling.",
        })

    if air_quality in {"Poor", "Very Poor"}:
        alerts.append({
            "type": "danger",
            "icon": "fa-smog",
            "title": f"{air_quality} air quality",
            "message": "Reduce prolonged outdoor activity, especially if you are sensitive to pollution.",
        })
    elif air_quality == "Moderate":
        alerts.append({
            "type": "info",
            "icon": "fa-leaf",
            "title": "Moderate air quality",
            "message": "Sensitive people may prefer shorter periods of heavy outdoor activity.",
        })

    if not alerts:
        alerts.append({
            "type": "success",
            "icon": "fa-circle-check",
            "title": "No active weather alerts",
            "message": "Current conditions look comfortable. Enjoy your day and check back for updates.",
        })

    return alerts[:4]


def find_or_create_city(weather):
    city = City.query.filter_by(
        city_name=weather["city"],
        country_code=weather["country"],
    ).first()

    if city is None:
        city = City(
            city_name=weather["city"],
            country_code=weather["country"],
            latitude=weather["latitude"],
            longitude=weather["longitude"],
        )
        db.session.add(city)
        db.session.flush()
    else:
        city.latitude = weather["latitude"]
        city.longitude = weather["longitude"]

    return city


def load_favorite_cards(user_id):
    favorites = (
        Favorite.query.filter_by(user_id=user_id)
        .order_by(Favorite.created_at.desc())
        .limit(4)
        .all()
    )

    cards = []
    if not OPENWEATHER_API_KEY:
        return favorites, cards

    for favorite in favorites:
        try:
            data = api_get(
                CURRENT_WEATHER_URL,
                {
                    "q": f"{favorite.city.city_name},{favorite.city.country_code}",
                    "appid": OPENWEATHER_API_KEY,
                    "units": "metric",
                },
            )
            weather_entry = (data.get("weather") or [{}])[0]
            cards.append(
                {
                    "favorite": favorite,
                    "temperature": round(data.get("main", {}).get("temp", 0)),
                    "description": weather_entry.get("description", "Unknown").title(),
                    "icon": weather_entry.get("icon", "01d"),
                }
            )
        except requests.RequestException:
            cards.append(
                {
                    "favorite": favorite,
                    "temperature": None,
                    "description": "Unavailable",
                    "icon": "01d",
                }
            )

    return favorites, cards


@app.route("/")
def home():
    if login_required():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/signup", methods=["POST"])
def signup():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not username or not email or not password or not confirm_password:
        flash("Please complete all fields.", "error")
        return redirect(url_for("home"))

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("home"))

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("home"))

    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash("Username or email already exists.", "error")
        return redirect(url_for("home"))

    try:
        db.session.add(
            User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Unable to create user account.")
        flash("Unable to create your account. Please try again.", "error")
        return redirect(url_for("home"))

    flash("Account created successfully. You can now log in.", "success")
    return redirect(url_for("home"))


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not email or not password or user is None or not check_password_hash(user.password_hash, password):
        flash("Invalid email or password.", "error")
        return redirect(url_for("home"))

    session.clear()
    session["user_id"] = user.id
    session["username"] = user.username
    session.permanent = bool(request.form.get("remember"))
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if not login_required():
        flash("Please log in first.", "error")
        return redirect(url_for("home"))

    requested_city = request.args.get("city", "").strip()
    city = requested_city or session.get("last_city") or DEFAULT_CITY
    weather = None
    forecast = []
    error = None
    air_quality = "Unavailable"
    weather_alerts = []

    if not OPENWEATHER_API_KEY:
        error = "The weather service is not configured. Add OPENWEATHER_API_KEY to your .env file."
    else:
        params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
        try:
            current_data = api_get(CURRENT_WEATHER_URL, params)
            weather = current_weather_from_data(current_data)
            session["last_city"] = weather["city"]

            forecast_data = api_get(FORECAST_URL, params)
            forecast = build_five_day_forecast(forecast_data)

            try:
                air_data = api_get(
                    AIR_QUALITY_URL,
                    {
                        "lat": weather["latitude"],
                        "lon": weather["longitude"],
                        "appid": OPENWEATHER_API_KEY,
                    },
                )
                air_index = air_data.get("list", [{}])[0].get("main", {}).get("aqi")
                air_quality = air_quality_label(air_index)
            except (requests.RequestException, KeyError, IndexError, TypeError):
                app.logger.info("Air quality data unavailable for %s", city)

            city_record = find_or_create_city(weather)
            if requested_city:
                db.session.add(SearchHistory(user_id=session["user_id"], city=city_record))
            db.session.commit()

            favorite = Favorite.query.filter_by(user_id=session["user_id"], city_id=city_record.id).first()
            weather["is_favorite"] = favorite is not None
            weather["favorite_id"] = favorite.id if favorite else None

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 404:
                error = "City not found. Please check the spelling and try again."
            elif status == 401:
                error = "Your OpenWeather API key is invalid or not active yet."
            elif status == 429:
                error = "Too many weather requests. Please try again later."
            else:
                error = "Unable to retrieve weather information right now."
            app.logger.exception("OpenWeather HTTP error")
        except requests.Timeout:
            error = "The weather service took too long to respond."
        except requests.RequestException:
            error = "Unable to connect to the weather service."
            app.logger.exception("OpenWeather connection error")
        except (KeyError, TypeError, ValueError):
            error = "The weather service returned unexpected data."
            app.logger.exception("Unexpected OpenWeather response")
        except Exception:
            db.session.rollback()
            error = "Something went wrong while loading your dashboard."
            app.logger.exception("Dashboard error")

    weather_alerts = build_weather_alerts(weather, air_quality)

    favorites, favorite_cards = load_favorite_cards(session["user_id"])
    recent_searches = (
        SearchHistory.query.filter_by(user_id=session["user_id"])
        .order_by(SearchHistory.searched_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard.html",
        username=session.get("username", "User"),
        city=city,
        weather=weather,
        forecast=forecast,
        favorites=favorites,
        favorite_cards=favorite_cards,
        recent_searches=recent_searches,
        air_quality=air_quality,
        weather_alerts=weather_alerts,
        alert_count=sum(1 for item in weather_alerts if item["type"] != "success"),
        error=error,
    )


@app.route("/favorites/add", methods=["POST"])
def add_favorite():
    if not login_required():
        return redirect(url_for("home"))

    city_name = request.form.get("city_name", "").strip()
    country_code = request.form.get("country_code", "").strip()
    latitude = request.form.get("latitude", type=float)
    longitude = request.form.get("longitude", type=float)

    if not city_name or not country_code:
        flash("Unable to save this city.", "error")
        return redirect(url_for("dashboard"))

    city = City.query.filter_by(city_name=city_name, country_code=country_code).first()
    if city is None:
        city = City(
            city_name=city_name,
            country_code=country_code,
            latitude=latitude,
            longitude=longitude,
        )
        db.session.add(city)
        db.session.flush()

    if Favorite.query.filter_by(user_id=session["user_id"], city_id=city.id).first():
        flash(f"{city_name} is already in your favorites.", "success")
        return redirect(url_for("dashboard", city=city_name))

    try:
        db.session.add(Favorite(user_id=session["user_id"], city_id=city.id))
        db.session.commit()
        flash(f"{city_name} added to favorites.", "success")
    except IntegrityError:
        db.session.rollback()
        flash(f"{city_name} is already in your favorites.", "success")

    return redirect(url_for("dashboard", city=city_name))


@app.route("/favorites/<int:favorite_id>/remove", methods=["POST"])
def remove_favorite(favorite_id):
    if not login_required():
        return redirect(url_for("home"))

    favorite = Favorite.query.filter_by(id=favorite_id, user_id=session["user_id"]).first_or_404()
    city_name = favorite.city.city_name
    db.session.delete(favorite)
    db.session.commit()
    flash(f"{city_name} removed from favorites.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)