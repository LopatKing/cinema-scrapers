import logging
import re
import urllib.parse
from datetime import datetime
from random import randint
from typing import NamedTuple, List, Optional

import aiohttp
import asyncio
from bs4 import BeautifulSoup

from cinemas.models import Cinema, ScraperTask, ShowtimeSeats
from cinemas.models import Movie as DjangoMovie
from common.models import Country

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("./novocinemas.log"),
        logging.StreamHandler()
    ]
)

TCPCONNECTOR_LIMIT = 100
SESSION_TIMEOUT_SEC = 3200
HEADERS = {
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
}
MAIN_PAGE = "https://uae.novocinemas.com/"


class Movie(NamedTuple):
    id: str
    title: str
    url: str
    language_id: Optional[str]


class Seats(NamedTuple):
    area: str
    all: int
    sold: int
    experience: str
    screen_num: str
    price: float


class Showtime(NamedTuple):
    movie: Movie
    datetime: datetime
    cinema: str
    url: str
    seats: List[Seats]

    @property
    def to_string(self):
        result = ""
        for seats_item in self.seats:
            result += f"{self.movie.title} in {self.cinema} at {self.datetime.strftime('%d %B %H:%M')} for " \
                      f"{seats_item.experience} experience. Screen {seats_item.screen_num} for " \
                      f"{seats_item.area}: sold {seats_item.sold} out of {seats_item.all}, " \
                      f"ticket price {seats_item.price} \n"
        return result


async def get_html(session: aiohttp.ClientSession, url: str, params: dict = None):
    if params is None:
        params = {}

    logging.debug(f"Loading page {url}, params - {params}")
    while True:
        async with session.get(url, params=params) as resp:
            logging.debug(resp.url)
            if resp.ok:
                return await resp.text()
            else:
                logging.error(f"Page failed to load. Url - {resp.url}. Status code - {resp.status}. Trying again")
                await asyncio.sleep(randint(5, 60))


async def get_all_movies(session: aiohttp.ClientSession) -> List[Movie]:
    params = {
        'experienceId': '0',
        'cinemaId': '0',
        'genereId': '0',
        'languageId': '0',
    }
    movies_url = urllib.parse.urljoin(MAIN_PAGE, "/Common/GetNowShowingMovies")
    movie_list_html = await get_html(session, movies_url, params)

    soup = BeautifulSoup(movie_list_html, "lxml")
    movie_divs = soup.findAll("div", class_="n-movie-poster")
    logging.info(f"Received {len(movie_divs)} movies")

    movies = []
    for movie_div in movie_divs:
        a = movie_div.find("a")
        title = a.get("title")
        url = urllib.parse.urljoin(MAIN_PAGE, a.get("href"))
        movie_id = url.split("/")[5]
        movies.append(Movie(
            id=movie_id,
            title=title,
            url=url,
            language_id=None,
        ))
    return movies


async def parse_seats_html(html: str) -> List[Seats]:
    unicode_dict = {
        "\\u003c": "<",
        "\\u0027": '"',
        "\\u003e": ">",
        "nbsp;": " ",
        "\\u0026": "&",
        '\\"': '"',
    }
    for key in unicode_dict.keys():
        html = html.replace(key, unicode_dict[key])
    soup = BeautifulSoup(html, "lxml")

    results = []
    all_tags = [tag for tag in soup.find_all()]
    all_seats = 0
    sold_seats = 0
    for tag in all_tags:
        if tag.name == "h2":
            area_span = tag.find("span")
            area_title = area_span.text
        elif tag.name == "input" and "hdnOverAllTicketTypeCodeAmount" in tag.get("id"):
            price = float(tag.get("value").strip().split("_")[1])
            results.append(Seats(
                area=area_title,
                all=all_seats,
                sold=sold_seats,
                experience="",
                screen_num="",
                price=price
            ))
            all_seats = 0
            sold_seats = 0
        elif tag.name == "li" and "novo-availableseats" in tag.get("class"):
            all_seats += 1
        elif tag.name == "li" and "novo-occupied" in tag.get("class"):
            all_seats += 1
            sold_seats += 1
    return results


async def get_seats_info(session: aiohttp.ClientSession, info_token: str) -> dict:
    url = "https://uae.novocinemas.com/seats/Index"
    params = {"info": info_token}
    html = await get_html(session, url, params)
    soup = BeautifulSoup(html, "lxml")
    experience = soup.find("input", {"id": "hdnmovieexp"}).get("value")
    screen_num = soup.find("section", {"class": "novo-seatarea"}).find("h3").text.split()[-1]
    return {
        "experience": experience,
        "screen_num": screen_num
    }


async def get_seats(session: aiohttp.ClientSession, url: str) -> List[Seats]:
    parsed_url = urllib.parse.urlparse(url)
    parsed_url_params = urllib.parse.parse_qs(parsed_url.query)

    # get hdnkey
    order_params = {
        "info": parsed_url_params["info"][0],
        "offers": 2
    }
    order_url = "https://uae.novocinemas.com/tickets/Index"
    order_html = await get_html(session, order_url, order_params)
    soup = BeautifulSoup(order_html, "lxml")
    hdnkey = soup.find("input", {"id": "hdnkey"}).get("value")

    # get all ticket types
    params = {"key": hdnkey}
    all_ticket_type_url = "https://uae.novocinemas.com/tickets/GetAllTicketTypes"
    response = await session.post(all_ticket_type_url, params=params, headers=HEADERS)
    ticket_types = await response.json()

    selected_types = ""
    for tt in ticket_types:
        selected_types += f"{tt.get('TicketTypeCode')}x1x{tt.get('TicketPrice')}x{tt.get('HeadOfficeGroupingCode')}|"

    info_token_response = await session.post(
        f'https://uae.novocinemas.com/tickets/SaveUserSelectedTickets?selectedtickettypes={selected_types}&key={hdnkey}',
        headers=HEADERS,
    )
    info_token_raw = await info_token_response.text()
    info_token = info_token_raw.replace('"', "")

    data = {"info": info_token}
    seats_response = await session.post('https://uae.novocinemas.com/Seats/LoadSeatLayout', data=data)
    seats_html = await seats_response.json()
    seats_list = await parse_seats_html(seats_html)
    seats_info = await get_seats_info(session, info_token)
    updated_seats_list = []
    for seats in seats_list:
        updated_seats = seats._replace(
            experience=seats_info.get("experience"),
            screen_num=seats_info.get("screen_num")
        )
        updated_seats_list.append(updated_seats)
    return updated_seats_list


async def get_showtimes_by_date(session: aiohttp.ClientSession, movie: Movie, date: datetime.date) -> List[Showtime]:
    params = {
        "movieId": movie.id,
        "selectedDate": date.strftime("%Y-%m-%d"),
        "languageId": movie.language_id,
        "locationIds": ""
    }
    url = urllib.parse.urljoin(MAIN_PAGE, "/moviedetails/GetAllShowsByMovie")
    html = await get_html(session, url, params)
    soup = BeautifulSoup(html, "lxml")

    showtimes = []
    cinema_items = soup.find("div", class_="accordion").findAll("div", class_="n-cinema-desc")
    for cinema_item in cinema_items:
        cinema_title = cinema_item.find("a", class_="n-cinema").get("title")
        time_items = cinema_item.find("ul", class_="n-time").findAll("li")

        for time_item in time_items:
            time_a = time_item.find("a", class_="n-time")
            time_str = time_a.text.strip()
            time_obj = datetime.strptime(time_str, "%I:%M %p").time()
            url = urllib.parse.urljoin(MAIN_PAGE, time_a.get("href"))
            datetime_obj = datetime.combine(date, time_obj)
            seats = await get_seats(session, url)
            showtime = Showtime(
                movie=movie,
                datetime=datetime_obj,
                cinema=cinema_title,
                url=url,
                seats=seats
            )
            showtimes.append(showtime)
    return showtimes


async def get_movie_showtimes(session: aiohttp.ClientSession, movie: Movie, search_date_str: str) -> List[Showtime]:
    movie_html = await get_html(session, movie.url)
    soup = BeautifulSoup(movie_html, "lxml")
    language_id = soup.find("input", {"id": "SelectedLanguageId"}).get("value")
    movie = movie._replace(language_id=language_id)

    available_date_items = soup.findAll("li", class_="dateselected")
    showtimes = []
    for date_item in available_date_items:
        date_str = re.search(r"\d\d\d\d-\d\d-\d\d", date_item.get("onclick")).group()
        if date_str != search_date_str:
            continue
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        showtimes += await get_showtimes_by_date(session, movie, date_obj)
    logging.info(f"Received {len(showtimes)} showtimes for {movie.title}")
    return showtimes


async def get_all_showtimes(session: aiohttp.ClientSession, movies: List[Movie], date_str: str) -> List[Showtime]:
    tasks = []
    for movie in movies:
        task = asyncio.create_task(get_movie_showtimes(session, movie, date_str))
        tasks.append(task)
    showtimes = await asyncio.gather(*tasks)
    results = []
    for showtime in showtimes:
        results += showtime
    logging.info(f"Summary received {len(results)} showtimes.")
    return results


async def main(date_str: str) -> List[Showtime]:
    connector = aiohttp.TCPConnector(force_close=True, limit=TCPCONNECTOR_LIMIT)
    timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SEC)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS, timeout=timeout) as session:
        movies = await get_all_movies(session)
        showtimes = await get_all_showtimes(session, movies, date_str)
    return showtimes


def save_to_django_db(task: ScraperTask):
    logging.info(f"Start task for {task.cinema_provider.name} {task.id}")
    search_date_str = task.date_query.strftime("%Y-%m-%d")
    showtimes = asyncio.run(main(search_date_str))


    for showtime in showtimes:
        country, created = Country.objects.get_or_create(name="UAE")
        cinema, created = Cinema.objects.get_or_create(name=showtime.cinema, country=country)
        movie, created = DjangoMovie.objects.get_or_create(name=showtime.movie.title)

        for seats in showtime.seats:
            ShowtimeSeats.objects.create(
                task=task,
                cinema=cinema,
                movie=movie,
                datetime=showtime.datetime,
                experience=seats.experience,
                all=seats.all,
                sold=seats.sold,
                price=seats.price,
                cinema_room=seats.screen_num,
                area=seats.area,
                url=showtime.url
            )
