import json
import logging
import re
import time
import urllib.parse
from datetime import datetime
from random import randint
from typing import NamedTuple, List, Optional
from datetime import date
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import pandas as pd
from cinemas.models import Cinema, ScraperTask, ShowtimeSeats
from cinemas.models import Movie as DjangoMovie
from common.models import Country

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("./output.log"),
        logging.StreamHandler()
    ]
)

if asyncio.get_event_loop().is_running():
    import nest_asyncio

    nest_asyncio.apply()

REQUESTS_PER_SECOND = 25
REQUEST_TIMEOUT_SEC = 30
SESSION_TIMEOUT_SEC = 3200
HEADERS = {
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
}

MAIN_PAGE = "https://www.starcinemas.ae/"
SEARCH_DATES = ["2023-06-06"]


class Movie(NamedTuple):
    id: str
    title: str
    language: str


class Seats(NamedTuple):
    title: str
    all: int
    sold: int
    price: float


class Showtime(NamedTuple):
    movie: Movie
    datetime: datetime
    screen_id: int
    screen_name: str
    cinema: str
    movie_details_id: int
    ss_id: int
    experience: str
    show_type: int
    seats: List[Seats]

    @property
    def to_string(self):
        msg = ""
        for seat in self.seats:
            msg += f"{self.movie.title} in {self.cinema} at {self.datetime.strftime('%d %B %H:%M')} for " \
                   f"{self.experience} experience. {self.screen_name} for {seat.title}: " \
                   f"sold {seat.sold} out of {seat.all}, ticket price {seat.price}\n"
        return msg


# class RequestLimiter:
#     def __init__(self, calls_limit: int = 10, period: int = 1):
#         self.calls_limit = calls_limit
#         self.period = period
#         self.semaphore = asyncio.Semaphore(calls_limit)
#         self.requests_finish_time = []

#     async def sleep(self):
#         loop = asyncio.get_event_loop()
#         if len(self.requests_finish_time) >= self.calls_limit:
#             sleep_before = self.requests_finish_time.pop(0)
#             if sleep_before >= time.monotonic():
#                 await loop.sleep(sleep_before - time.monotonic())

#     def __call__(self, func):
#         async def wrapper(*args, **kwargs):

#             async with self.semaphore:
#                 await self.sleep()
#                 res = await func(*args, **kwargs)
#                 self.requests_finish_time.append(time.monotonic() + self.period)
#             return res
#         return wrapper


# @RequestLimiter(calls_limit=REQUESTS_PER_SECOND, period=1)
async def get_html(session: aiohttp.ClientSession, url: str, params: dict = None):
    if params is None:
        params = {}
    loop = asyncio.get_event_loop()
    print(f"Loading page {url}, params - {params}")
    while True:
        try:
            async with session.get(url, params=params) as resp:
                if resp.ok:
                    return await resp.text()
                    # html = await resp.text()
                    # soup = BeautifulSoup(html, "lxml")
                    # title = soup.find("h2")
                    # if title and title.text.strip() == "404":
                    #     print(f"Page failed to load. Url - {resp.url}. Trying again")
                    #     #await loop.sleep(randint(5, 60))
                    #     time.sleep(5)
                    # else:

                else:
                    # sleep_time = randint(5, 60)
                    print(f"Page failed to load. Url - {resp.url}. Status code - {resp.status}. "
                          f"Trying again after few seconds")
                    # await loop.sleep(sleep_time)
        except Exception as e:
            print(e)
            # sleep_time = randint(5, 60)
            print(f"Page failed to load. Server not responding. Url - {url}. "
                  f"Trying again after few seconds")
            # await loop.sleep(sleep_time)


async def get_autorization_key(session: aiohttp.ClientSession) -> str:
    html = await get_html(session, MAIN_PAGE)
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script")
    js_url = None
    for script in scripts:
        src = script.get("src")
        if src and "/static/js/main." in src:
            js_url = urllib.parse.urljoin(MAIN_PAGE, src)
    if not js_url:
        print("Not found authorization key")

    js_text = await get_html(session, js_url)
    search = re.search("\.cloudfront\.net\",s=\"([^\"]+)", js_text)
    key = search.group()[20:-3]
    return key


async def get_movies(session: aiohttp.ClientSession) -> List[Movie]:
    page_url = "https://web-api.starcinemas.ae/api/cinema/admin/now-showing-confirmed-list"
    params = {
        "limit": "1000",
        "currentPage": "1",
        "rtk": "true",
    }
    response = await get_html(session, page_url, params=params)

    movies_json = json.loads(response)
    movies = []
    for movie_item in movies_json.get("Records").get("data"):
        movie = Movie(
            id=movie_item.get("movie_id"),
            title=movie_item.get("movie_title"),
            language=movie_item.get("lang_name")
        )
        movies.append(movie)
    print(f"Found {len(movies)} movies")
    return movies


async def get_all_showtimes(session: aiohttp.ClientSession,
                            movies: List[Movie],
                            search_dates: List[str]) -> List[Showtime]:
    tasks = []
    for movie in movies:
        task = asyncio.create_task(get_movie_showtimes(session, movie, search_dates))
        tasks.append(task)
    showtimes = await asyncio.gather(*tasks)
    results = []
    for showtime in showtimes:
        results += showtime
    print(f"Summary received {len(results)} showtimes.")
    return results


async def get_movie_showtimes(session: aiohttp.ClientSession,
                              movie: Movie,
                              dates: List[str]) -> List[Showtime]:
    movie_url = f"https://web-api.starcinemas.ae/api/cinema/admin/movie-confirmed-list/{movie.id}"
    results = []
    for showtime_date_str in dates:
        params = {"fromDate": showtime_date_str}
        movie_text = await get_html(session, movie_url, params=params)
        movie_json = json.loads(movie_text)
        showtimes = movie_json["Records"]["data"]
        for showtime in showtimes:
            start_time = showtime.get("ss_start_show_time")
            showtime_datetime = datetime.strptime(f"{showtime_date_str} {start_time}", "%Y-%m-%d %H:%M")
            current_date = date.today()
            scraping_date = datetime.now().strftime('%Y%m%d %H:%M')
            processing_date = current_date.strftime("%Y%m%d")
            city = ''
            country = MAIN_PAGE.split("/")[-2].split(".")[-1]
            if country == 'ae':
                country = 'uae'
            showtime = Showtime(
                movie=movie,
                datetime=showtime_datetime,
                cinema=showtime.get("cine_name"),
                screen_id=showtime.get("screen_id"),
                screen_name=showtime.get("screen_name"),
                movie_details_id=showtime.get("movie_details_id"),
                ss_id=showtime.get("ss_id"),
                experience=showtime.get("mf_name"),
                show_type=showtime.get("showType"),
                seats=[]
            )
            seats = await get_seats(session, showtime.screen_id, showtime.ss_id, showtime.movie_details_id,
                                    showtime.show_type)
            print(seats)
            if not seats:
                continue
            else:
                seats_area = seats[0][0]
                seats_total = seats[0][1]
                seats_sold = seats[0][2]
                ticket_price = seats[0][3]
                # seats_screen= seats[0][4]
                # ticket_price= seats[0][5]
            total = [country.strip(), showtime.movie.title, showtime.cinema, showtime_datetime, seats_area, seats_total,
                     seats_sold, showtime.experience, showtime.screen_name, ticket_price, scraping_date,
                     processing_date, city, showtime.movie.language]
            print(total)
            results.append(total)
            try:
                seats_area = seats[1][0]
                seats_total = seats[1][1]
                seats_sold = seats[1][2]
                ticket_price = seats[1][3]
                total = [country.strip(), showtime.movie.title, showtime.cinema, showtime_datetime, seats_area,
                         seats_total, seats_sold, showtime.experience, showtime.screen_name, ticket_price,
                         scraping_date, processing_date, city, showtime.movie.language]
                print(total)
                results.append(total)
            except:
                continue
            try:
                seats_area = seats[2][0]
                seats_total = seats[2][1]
                seats_sold = seats[2][2]
                ticket_price = seats[2][3]
                total = [country.strip(), showtime.movie.title, showtime.cinema, showtime_datetime, seats_area,
                         seats_total, seats_sold, showtime.experience, showtime.screen_name, ticket_price,
                         scraping_date, processing_date, city, showtime.movie.language]
                print(total)
                results.append(total)
            except:
                continue
            try:
                seats_area = seats[0][0]
                seats_total = seats[0][1]
                seats_sold = seats[0][2]
                ticket_price = seats[0][3]
                total = [country.strip(), showtime.movie.title, showtime.cinema, showtime_datetime, seats_area,
                         seats_total, seats_sold, showtime.experience, showtime.screen_name, ticket_price,
                         scraping_date, processing_date, city, showtime.movie.language]
                print(total)
                results.append(total)
            except:
                continue
            try:
                seats_area = seats[0][0]
                seats_total = seats[0][1]
                seats_sold = seats[0][2]
                ticket_price = seats[0][3]
                total = [country.strip(), showtime.movie.title, showtime.cinema, showtime_datetime, seats_area,
                         seats_total, seats_sold, showtime.experience, showtime.screen_name, ticket_price,
                         scraping_date, processing_date, city, showtime.movie.language]
                print(total)
                results.append(total)
            except:
                continue
            try:
                seats_area = seats[0][0]
                seats_total = seats[0][1]
                seats_sold = seats[0][2]
                ticket_price = seats[0][3]
                total = [country.strip(), showtime.movie.title, showtime.cinema, showtime_datetime, seats_area,
                         seats_total, seats_sold, showtime.experience, showtime.screen_name, ticket_price,
                         scraping_date, processing_date, city, showtime.movie.language]
                print(total)
                results.append(total)
            except:
                continue
            try:
                seats_area = seats[0][0]
                seats_total = seats[0][1]
                seats_sold = seats[0][2]
                ticket_price = seats[0][3]
                total = [country.strip(), showtime.movie.title, showtime.cinema, showtime_datetime, seats_area,
                         seats_total, seats_sold, showtime.experience, showtime.screen_name, ticket_price,
                         scraping_date, processing_date, city, showtime.movie.language]
                print(total)
                results.append(total)
            except:
                continue
    print(f"Received {len(results)} showtimes for {movie_url}")
    return results


async def get_seats(session: aiohttp.ClientSession, screen_id, ss_id, movie_details_id, show_type) -> Showtime:
    url = "https://web-api.starcinemas.ae/api/external/seat-layout"
    data = {
        "screen_id": screen_id,
        "ss_id": ss_id,
        "md_id": movie_details_id,
        "type_seat_show": show_type
    }
    response = await session.post(url, data=data)
    seats_json = await response.json()
    seats = []
    for seats_type in seats_json["screen_seat_type"]:
        seats_type_id = seats_type["sst_id"]
        title = seats_type["sst_seat_type"]
        seats_all = 0
        seats_sold = 0
        price = 0
        for seat in seats_json["Records"]:
            if seat["screen_seat_type_id"] != seats_type_id:
                continue
            seats_all += 1
            price = seat["seat_price"]
            if seat["is_booking_done"]:
                seats_sold += 1

        seat_obj = Seats(
            title=title,
            all=seats_all,
            sold=seats_sold,
            price=price
        )
        seats.append(seat_obj)
    # showtime_with_seats = showtime._replace(seats=seats)
    return seats


# async def collect_seats_data(session: aiohttp.ClientSession, showtimes: List[Showtime]) -> List[Showtime]:
#     tasks = []
#     for showtime in showtimes:
#         task = asyncio.create_task(get_seats(session, showtime))
#         tasks.append(task)
#     showtime_with_seats = await asyncio.gather(*tasks)
#     logging.info(f"Summary received {len(showtime_with_seats)} showtimes with seats data.")
#     return showtime_with_seats


async def main(search_dates: List[str]):
    connector = aiohttp.TCPConnector(force_close=True)
    timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SEC)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS, timeout=timeout) as session:
        auth_key = await get_autorization_key(session)
        HEADERS["authorization"] = auth_key
        session.headers.update(HEADERS)
        movies = await get_movies(session)
        showtimes = await get_all_showtimes(session, movies, search_dates)
        # showtimes_with_seats = await collect_seats_data(session, showtimes)
    return showtimes


def create_df(showtimes):
    # showtimes =showtimes
    # show = []
    # current_date = date.today()
    # country = MAIN_PAGE.split("/")[-2].split(".")[-1]
    # if country == 'ae':
    #     country = 'uae'
    # print(country)
    # movie_name = showtimes[0]
    # print(movie_name)
    # cinema_title = showtimes[4]
    # print(cinema_title)
    # show_time = showtimes[1]
    # seats_experience = showtimes[7]
    # seats_screen =  showtimes[3]
    # scraping_date = datetime.now().strftime('%Y%m%d %H:%M')
    # processing_date = current_date.strftime("%Y%m%d")
    # area = [(seat[0][0], seat[0][1], seat[0][2]) for seat in showtimes[9]]
    # rows = [[movie_name, cinema_title, show_time, seats_area, seats_total, seats_sold, seats_experience, seats_screen, ticket_price, scraping_date, processing_date] for seats_area, seats_total, seats_sold, ticket_price in area]
    # for row in rows:
    #     show.append(row)
    df1 = pd.DataFrame(data=showtimes,
                       columns=['country', 'movie_name', 'cinema_title', 'show_time', 'seats_area', 'seats_total',
                                'seats_sold', 'seats_experience', 'seats_screen', 'ticket_price', 'scraping_date',
                                'processing_date', 'city', 'language'])
    print(df1)
    df1.to_csv('/Users/nb/Downloads/star_final06.csv')


def calling_main():
    SEARCH_DATES_LIST = []
    SEARCH_DATES = date.today()
    formatted_search_date = SEARCH_DATES.strftime("%Y-%m-%d")
    SEARCH_DATES_LIST.append(formatted_search_date)
    showtimes = asyncio.get_event_loop()
    showtimes = showtimes.run_until_complete(main(SEARCH_DATES_LIST))
    create_df(showtimes)

    # with open("star_output.txt", "w") as file:
    #     for showtime in showtimes:
    #         file.write(str(showtime))


def save_to_django_db(task: ScraperTask):
    logging.info(f"Start task for {task.cinema_provider.name} {task.id}")
    search_date_str = task.date_query.strftime("%Y-%m-%d")
    showtimes = asyncio.run(main([search_date_str]))
    for showtime in showtimes:
        country, created = Country.objects.get_or_create(name=showtime[0])
        cinema, created = Cinema.objects.get_or_create(name=showtime[2], country=country)
        movie, created = DjangoMovie.objects.get_or_create(name=showtime[1], language=showtime[13])

        ShowtimeSeats.objects.create(
            task=task,
            cinema=cinema,
            movie=movie,
            datetime=showtime[3],
            experience=showtime[7],
            all=showtime[5],
            sold=showtime[6],
            price=showtime[9],
            area=showtime[4],
            cinema_room=showtime[8],
        )
