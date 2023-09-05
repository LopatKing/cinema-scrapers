import logging
import urllib.parse
from datetime import datetime
from random import randint
from typing import NamedTuple, List, Optional

import aiohttp
import asyncio
import pandas
from bs4 import BeautifulSoup

from cinemas.models import Cinema, ScraperTask, ShowtimeSeats
from cinemas.models import Movie as DjangoMovie

if asyncio.get_event_loop().is_running():
    import nest_asyncio
    nest_asyncio.apply()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("./output.log"),
        logging.StreamHandler()
    ]
)

TCPCONNECTOR_LIMIT = 50
SESSION_TIMEOUT_SEC = 3200
HEADERS = {
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
}
MAIN_PAGE = "https://www.cinemacity.ae/"
SEARCH_DATES = ["2023-07-13"]
SEMAPHORE = None


class Movie(NamedTuple):
    title: str
    url: str


class Showtime(NamedTuple):
    movie: Movie
    datetime_obj: datetime
    url: str
    experience_tags: List[str]


class SeatsArea(NamedTuple):
    title: str
    all: int
    sold: int
    price: float


class FullShowtime(NamedTuple):
    short: Showtime
    seats_areas: List[SeatsArea]
    cinema_name: str
    screen_name: str

async def get_request(session: aiohttp.ClientSession, url: str, params: dict = None):
    if params is None:
        params = {}

    while True:
        try:
            async with SEMAPHORE:
                logging.debug(f"Loading page {url}, params - {params}")
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.ok:
                        html = await resp.text()
                        soup = BeautifulSoup(html, "lxml")
                        title = soup.find("h2")
                        if title and title.text.strip() == "404":
                            logging.error(f"Page failed to load. Url - {resp.url}. Trying again")
                            await asyncio.sleep(randint(5, 60))
                        else:
                            return html
                    else:
                        sleep_time = randint(5, 60)
                        logging.error(f"Page failed to load. Url - {resp.url}. Status code - {resp.status}. "
                                      f"Trying again after {sleep_time} seconds")
                        await asyncio.sleep(sleep_time)
        except asyncio.exceptions.TimeoutError:
            sleep_time = randint(5, 60)
            logging.error(f"Page failed to load. Server not responding. Url - {url}. "
                          f"Trying again after {sleep_time} seconds")
            await asyncio.sleep(sleep_time)
        except Exception as e:
            sleep_time = randint(5, 60)
            logging.error(f"Page failed to load. Server not responding. Url - {url}. "
                          f"Trying again after {sleep_time} seconds. Error: {e}")
            await asyncio.sleep(sleep_time)


async def post_request(session: aiohttp.ClientSession,
                       url: str,
                       params: dict = None,
                       data: dict = None,
                       json: dict = None) -> str:

    while True:
        try:
            async with SEMAPHORE:
                logging.debug(f"Loading data from {url}, params - {params}, data - {data}, json - {json}")
                async with session.post(url, params=params, data=data, json=json, timeout=60) as resp:
                    if resp.ok:
                        return await resp.text()
                    else:
                        logging.error(f"Page failed to load. Url - {resp.url}. Status code - {resp.status}. Trying again")
                        await asyncio.sleep(randint(5, 60))
        except asyncio.TimeoutError:
            logging.error(f"Timeout Error. Url - {url}. Trying again")
            continue
        except Exception as e:
            await asyncio.sleep(randint(5, 60))
            logging.error(f"Error - {e}. Url - {url}. Trying again")
            continue


async def get_movies(session: aiohttp.ClientSession) -> List[Movie]:
    url = "https://www.cinemacity.ae/Browsing/Movies/NowShowing"
    response = await get_request(session, url)
    soup = BeautifulSoup(response, "lxml")

    movies = []
    movie_items = soup.find_all("div", class_="movie")
    for movie_item in movie_items:
        title_tag = movie_item.find("h3")
        title = title_tag.text.strip()
        url = title_tag.parent.get("href")
        full_url = urllib.parse.urljoin(MAIN_PAGE, url)
        movie = Movie(
            title=title,
            url=full_url
        )
        movies.append(movie)
    return movies


async def get_showtimes_by_movie(session: aiohttp.ClientSession, movie: Movie) -> List[Showtime]:
    response = await get_request(session, movie.url)
    soup = BeautifulSoup(response, "lxml")

    showtimes = []
    showtime_tags = soup.find_all("a", class_="session-time")
    for tag in showtime_tags:
        datetime_str = tag.find("time").get("datetime")
        datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
        full_url = urllib.parse.urljoin(MAIN_PAGE, tag.get("href"))
        showtime = Showtime(
            movie=movie,
            datetime_obj=datetime_obj,
            url=full_url,
            experience_tags=[tag.get("alt").strip() for tag in tag.find_all("img")]
        )
        showtimes.append(showtime)
    return showtimes


async def get_showtimes(session: aiohttp.ClientSession, movies: List[Movie], search_dates: List[str]) -> List[Showtime]:
    tasks = []
    for movie in movies:
        task = asyncio.create_task(get_showtimes_by_movie(session, movie))
        tasks.append(task)
    all_showtimes = await asyncio.gather(*tasks)
    result_showtime = []
    for showtimes in all_showtimes:
        for showtime in showtimes:
            if showtime.datetime_obj.strftime("%Y-%m-%d") in search_dates:
                result_showtime.append(showtime)
    return result_showtime


async def collect_seats_data_by_showtime(showtime: Showtime) -> Optional[FullShowtime]:
    connector = aiohttp.TCPConnector(force_close=True, limit=TCPCONNECTOR_LIMIT)
    timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SEC)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS, timeout=timeout) as session:
        response = await get_request(session, showtime.url)
        soup = BeautifulSoup(response, "lxml")

        cinema_screen_name_tag = soup.find("div", class_="cinema-screen-name")
        if not cinema_screen_name_tag:
            logging.warning(f"The server is returning invalid showtime data. Movie - {showtime.movie.title} at "
                            f"{showtime.datetime_obj.strftime('%Y-%m-%d %H:%M')}")
            return None
        cinema_screen_name = cinema_screen_name_tag.text
        cinema_name = "-".join(cinema_screen_name.split("-")[:-1]).strip()
        screen_name = cinema_screen_name.split("-")[-1].strip()

        data = {
            '__EVENTTARGET': soup.find("button", id="ibtnOrderTickets").get("onclick").split("'")[-4],
            '__EVENTARGUMENT': soup.find("input", id="__EVENTARGUMENT").get("value"),
            '__VIEWSTATE': soup.find("input", id="__VIEWSTATE").get("value"),
            '__VIEWSTATEGENERATOR': soup.find("input", id="__VIEWSTATEGENERATOR").get("value"),
            '__EVENTVALIDATION': soup.find("input", id="__EVENTVALIDATION").get("value"),
            'username': '',
            'password': '',
            'ctl00$ContentBody$txtTechnicalDetails': soup.find("input", {"name": "ctl00$ContentBody$txtTechnicalDetails"}).get("value", ""),
            'ctl00$ContentBody$txtDoNotRehydrate': soup.find("input", {"name": "ctl00$ContentBody$txtDoNotRehydrate"}).get("value", ""),
            'ctl00$ContentBody$txtAllocatedSeating': soup.find("input", {"name": "ctl00$ContentBody$txtAllocatedSeating"}).get("value", ""),
            'ctl00$ContentBody$txtForceSeatSelection': soup.find("input", {"name": "ctl00$ContentBody$txtForceSeatSelection"}).get("value", ""),
            'ctl00$ContentBody$txtEnableManualSeatSelection': soup.find("input", {"name": "ctl00$ContentBody$txtEnableManualSeatSelection"}).get("value", ""),
            'ctl00$ContentBody$txtHideAllVoucherRows': soup.find("input", {"name": "ctl00$ContentBody$txtHideAllVoucherRows"}).get("value", ""),
            'ctl00$ContentBody$txtEnableConcessionSales': soup.find("input", {"name": "ctl00$ContentBody$txtEnableConcessionSales"}).get("value", ""),
            'ctl00$ContentBody$txtVoucherSubmit': soup.find("input", {"name": "ctl00$ContentBody$txtVoucherSubmit"}).get("value", ""),
            'ctl00$ContentBody$txtVoucherPINSubmit': soup.find("input", {"name": "ctl00$ContentBody$txtVoucherPINSubmit"}).get("value", ""),
            'ctl00$ContentBody$txtDateOrderChanged': soup.find("input", {"name": "ctl00$ContentBody$txtDateOrderChanged"}).get("value", ""),
            'ctl00$ContentBody$txtCancelOrder': soup.find("input", {"name": "ctl00$ContentBody$txtCancelOrder"}).get("value", ""),
            'ctl00$ContentBody$txtBookingFee': soup.find("input", {"name": "ctl00$ContentBody$txtBookingFee"}).get("value", ""),
        }

        seats_areas_tags = soup.find_all("input", class_="quantity")
        for area in seats_areas_tags:
            data[area.get("name")] = 1

        await post_request(session, showtime.url, data=data)

        url = 'https://www.cinemacity.ae/Ticketing/visSelectSeats.aspx'
        response = await get_request(session, url)

        soup = BeautifulSoup(response, "lxml")
        area_short_tags = soup.find_all("li", class_="cart-ticket")
        area_names = [area.find("span", class_="name").text for area in area_short_tags]
        area_prices = [float(area.find("span", class_="price").text) for area in area_short_tags]

        seats_areas = []
        seating_area_tags = soup.find_all("table", class_="Seating-Area")

        # Some cinema halls are divided into 3 parts, but have 2 types of tickets
        for i, area in enumerate(seating_area_tags):
            seats_cells = area.find_all("p", {"role": "button"})
            seats_sold = area.find_all("p", {"role": "button", "aria-label": "unavailable"})
            if i >= len(area_names):
                if len(area_names) == 1:
                    first_seats_all = 0
                    first_seats_sold = 0
                    for seats in seats_areas:
                        first_seats_all += seats.all
                        first_seats_sold += seats.sold
                    area = SeatsArea(
                        title=area_names[0],
                        all=first_seats_all + len(seats_cells),
                        sold=first_seats_sold + len(seats_sold),
                        price=area_prices[0]
                    )
                    seats_areas = [area]
                else:
                    first_seats_all = 0
                    first_seats_sold = 0
                    for seats in seats_areas:
                        first_seats_all += seats.all
                        first_seats_sold += seats.sold

                    seats_areas = [SeatsArea(
                        title=area_names[0],
                        all=first_seats_all,
                        sold=first_seats_sold,
                        price=area_prices[0]
                    )]
                    area = SeatsArea(
                        title=area_names[-1],
                        all=len(seats_cells),
                        sold=len(seats_sold),
                        price=area_prices[-1]
                    )
                    seats_areas.append(area)
            else:
                area = SeatsArea(
                    title=area_names[i],
                    all=len(seats_cells),
                    sold=len(seats_sold),
                    price=area_prices[i]
                )
                seats_areas.append(area)

        fullshowtime = FullShowtime(
            short=showtime,
            seats_areas=seats_areas,
            cinema_name=cinema_name,
            screen_name=screen_name
        )
    return fullshowtime


async def collect_seats_data(showtimes: List[Showtime]) -> List[FullShowtime]:
    tasks = []
    for showtime in showtimes:
        task = asyncio.create_task(collect_seats_data_by_showtime(showtime))
        tasks.append(task)
    all_showtimes = await asyncio.gather(*tasks)
    return [showtime for showtime in all_showtimes if showtime]


async def main(search_dates: List[str]) -> List[FullShowtime]:
    global SEMAPHORE
    SEMAPHORE = asyncio.Semaphore(TCPCONNECTOR_LIMIT)
    connector = aiohttp.TCPConnector(force_close=True, limit=TCPCONNECTOR_LIMIT)
    timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SEC)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS, timeout=timeout) as session:
        movies = await get_movies(session)
        showtimes = await get_showtimes(session, movies, search_dates)
        full_showtimes = await collect_seats_data(showtimes)
    return full_showtimes


# if __name__ == "__main__":
#     showtimes = asyncio.run(main(SEARCH_DATES))
#
#     # showtimes to csv
#     data = []
#     for showtime in showtimes:
#         for seats in showtime.seats_areas:
#             showtime_dict = {
#                 "movie": showtime.short.movie.title,
#                 "movie_url": showtime.short.movie.url,
#                 "cinema_name": showtime.cinema_name,
#                 "showtime_datetime": showtime.short.datetime_obj.strftime('%d %B %H:%M'),
#                 "experience": ", ".join(showtime.short.experience_tags),
#                 "screen_name": showtime.screen_name,
#                 "seats_type": seats.title,
#                 "seats_price": seats.price,
#                 "seats_all": seats.all,
#                 "seats_sold": seats.sold
#             }
#             data.append(showtime_dict)
#
#     df = pandas.DataFrame(data)
#     df.to_csv("cinemacity_output.csv")

def save_to_django_db(task: ScraperTask):
    logging.info(f"Start task for {task.cinema_provider.name} {task.id}")
    search_date_str = task.date_query.strftime("%Y-%m-%d")
    showtimes = asyncio.run(main([search_date_str]))
    for showtime in showtimes:
        cinema, created = Cinema.objects.get_or_create(name=showtime.cinema_name)
        movie, created = DjangoMovie.objects.get_or_create(name=showtime.short.movie.title)

        for seats in showtime.seats_areas:
            ShowtimeSeats.objects.create(
                task=task,
                cinema=cinema,
                movie=movie,
                datetime=showtime.short.datetime_obj,
                experience=", ".join(showtime.short.experience_tags),
                all=seats.all,
                sold=seats.sold,
                price=seats.price,
                type=seats.title,
            )
