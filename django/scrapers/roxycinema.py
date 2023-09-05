import json
import logging
import re
import urllib.parse
from datetime import datetime
from random import randint
from typing import NamedTuple, List, Optional
import pandas as pd
import aiohttp
import asyncio
from datetime import date
import pandas
from bs4 import BeautifulSoup

from cinemas.models import Cinema, ScraperTask, ShowtimeSeats
from cinemas.models import Movie as DjangoMovie

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

TCPCONNECTOR_LIMIT = 100
REQUESTS_LIMIT = 20
SESSION_TIMEOUT_SEC = 3200
HEADERS = {
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
}
MAIN_PAGE = "https://www.theroxycinemas.com"
SEMAPHORE = None


class Movie(NamedTuple):
    id: str
    url: str
    title: str
    language: str


class Cinema(NamedTuple):
    id: str
    name: str


class Seats(NamedTuple):
    title: str
    all: int
    sold: int
    price: float


class Showtime(NamedTuple):
    movie: Movie
    cinema: Cinema
    id: str
    datetime_obj: datetime
    experience: str
    screen_name: Optional[str]
    seats: List[Seats]

    @property
    def to_string(self):
        msg = ""
        for seat in self.seats:
            msg += f"{self.movie.title} in {self.cinema.name} at {self.datetime_obj.strftime('%d %B %H:%M')} for " \
                   f"{self.experience} experience. {self.screen_name} for {seat.title}: " \
                   f"sold {seat.sold} out of {seat.all}, ticket price {seat.price}"
            msg += "\n"
        return msg


async def get_request(session: aiohttp.ClientSession, url: str, params: dict = None):
    if params is None:
        params = {}

    print(f"Loading page {url}, params - {params}")
    while True:
        try:
            async with session.get(url, params=params, timeout=30) as resp:
                if resp.ok:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "lxml")
                    title = soup.find("h2")
                    return html
                else:
                    print(f"Page failed to load. Url - {resp.url}. Status code - {resp.status}. "
                          f"Trying again after few seconds")
        except Exception as e:
            print("Inside get_request exception...")
            print(f"Page failed to load. Server not responding. Url - {url}. "
                  f"Trying again after few seconds. Error: {e}")
            print(e)


async def post_request(session: aiohttp.ClientSession,
                       url: str,
                       params: dict = None,
                       data: dict = None,
                       json: dict = None) -> str:
    logging.debug(f"Loading data from {url}, params - {params}, data - {data}, json - {json}")
    while True:
        try:
            async with session.post(url, params=params, data=data, json=json, timeout=60) as resp:
                if resp.ok:
                    return await resp.text()
                else:
                    print(f"Page failed to load. Url - {resp.url}. Status code - {resp.status}. Trying again")
        except Exception as e:
            print("Inside exception post_request...")
            print(e)
            continue


async def get_movies(session: aiohttp.ClientSession) -> List[Movie]:
    movies = []
    try:
        url = "https://www.theroxycinemas.com/Home/HomeNowShowing"
        response_text = await post_request(session, url)
        response_json = json.loads(response_text)

        for movie_data in response_json:
            movie_url = urllib.parse.urljoin(MAIN_PAGE, f"movie-details/{movie_data.get('FilterdTitle')}")
            movie = Movie(
                url=movie_url,
                title=movie_data.get("Title"),
                id=movie_data.get("ID"),
                language=movie_data.get("language")
            )
            movies.append(movie)
        logging.info(f"Found {len(movies)} movies")
        return movies
    except:
        return movies


def get_upper_string(search_string: str, full_string: str) -> str:
    full_string_lower = full_string.lower()
    first_index = full_string_lower.find(search_string)
    last_index = first_index + len(search_string)
    return full_string[first_index:last_index]


async def get_movie_showtimes(session: aiohttp.ClientSession,
                              movie: Movie,
                              date_str: str) -> List[Showtime]:
    showtimes = []
    try:
        async with SEMAPHORE:
            data = {
                'movieId': movie.id,
                'date': date_str,
                'experience': '',
            }
            url = "https://www.theroxycinemas.com/MovieDetails/GetMovieShowTimes"
            html = await post_request(session, url, data=data)
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
            sections = soup.find_all("section", class_="maccordion-group")

            for section in sections:
                cinema_title = section.find("h2").text.replace("&", "").strip()
                cinema_id = section.find("a", class_="rc-csa-more").get("data-target").replace("#", "")
                cinema = Cinema(
                    name=cinema_title,
                    id=cinema_id
                )
                experiences = section.find_all('section', class_='cinema-exp')
                # showtime_a_tags1 = section.find_all("a", class_="mshowtime")
                # showtime_a_tags = section.find_all("span", class_="rc-mstspan")
                showtimings = section.find_all('section', class_="cscreen-showtimigs")
                print(showtimings)
                for index, exp in enumerate(experiences):
                    print(".....")
                    print(index)
                    showtiming_exp = showtimings[index]
                    showtime_a_tags = showtiming_exp.find_all("span", class_="rc-mstspan")
                    li_tag = showtiming_exp.find('li')
                    # print(li_tag)
                    # onclick_value = li_tag['onclick']
                    # print(onclick_value)
                    experience = exp.find("h3").text.strip()
                    for a_tag in showtime_a_tags:
                        showtime_time_str = a_tag.text.strip()
                        showtime_datetime = datetime.strptime(f"{date_str} {showtime_time_str}", "%Y-%m-%d %H:%M")

                        # bypass html parsers bug
                        li_attrs = list(a_tag.find_parent('li').attrs.keys())
                        li_attrs.remove("onclick")
                        if len(li_attrs) != 1:
                            print(f"Getting Showtime_id failed {a_tag.find_parent('li')}")
                            raise ValueError
                        showtime_id = get_upper_string(li_attrs[0], html)

                        print(showtime_id)
                        print("printing get_movie_showtimes...")
                        print(f"{movie.title}--{cinema_title}--{experience}--{showtime_time_str}--{showtime_id}")
                        showtime = Showtime(
                            movie=movie,
                            id=showtime_id,
                            cinema=cinema,
                            datetime_obj=showtime_datetime,
                            seats=[],
                            experience=experience,
                            screen_name=None
                        )
                        showtimes.append(showtime)
            return showtimes
    except:
        return showtimes


async def get_showtimes(session: aiohttp.ClientSession, movies: List[Movie], SEARCH_DATES_LIST: List[str]) -> List[
    Showtime]:
    tasks = []
    for movie in movies:
        for date_str in SEARCH_DATES_LIST:
            task = asyncio.create_task(get_movie_showtimes(session, movie, date_str))
            tasks.append(task)
    showtimes = await asyncio.gather(*tasks)
    results = []
    for showtime in showtimes:
        results += showtime
    logging.info(f"Summary received {len(results)} showtimes.")
    return results


async def get_ticket_details(session: aiohttp.ClientSession, showtime_id: str) -> dict:
    try:
        offer_url = f"https://www.theroxycinemas.com/offer/{showtime_id}"
        html = await get_request(session, offer_url)
        soup = BeautifulSoup(html, "lxml")
        session_id = soup.find("input", id="hdn_Sessionid").get("value")
        cinema_id = soup.find("input", id="hdn_Cinemaid").get("value")

        params = {
            "sessionid": session_id,
            "cinemaid": cinema_id,
            "Type": "Normal",
            "specialshow": "0",
        }
        ticket_details_url = "https://www.theroxycinemas.com/offers/TickettypeDetails"
        response = await post_request(session, ticket_details_url, params)
        response_json = json.loads(response)
        ticket_details = ""
        tickets_total_amount = 0
        for ticket in response_json:
            if ticket["IspackageTicket"]:
                continue
            tickets_total_amount += float(ticket["Amount"])
            ticket_details += f"1|{ticket['Amount']}|{ticket['Ticketcode']}|{ticket['AreaCategorycode']}|false~"
        return {
            "tickets_total_amount": tickets_total_amount,
            "ticket_details": ticket_details
        }
    except:
        return {
            "tickets_total_amount": '',
            "ticket_details": ''
        }


async def get_seats_data(session: aiohttp.ClientSession, ticket_details: str):
    seats_list = []
    try:
        data = {
            "Ticketdetails": ticket_details,
            "SequenceNumber": "",
            "RecognitionID": "",
            "isavail": "",
            "OfferQty": "",
            "OfferName": "",
            "PointsCost": "",
            "TTypeCode": "",
            "VistaId": "",
            "specialshow": "0",
        }
        url = "https://www.theroxycinemas.com/Seats/GetSeatLayout"
        html = await post_request(session, url, data=data)
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
        sections = soup.find_all("section", class_="disabledArea")

        for section in sections:
            seats_tag = section.find("h2")
            seats_name = seats_tag.text.strip()
            seats_id = seats_tag.get("id").split("_")[-1]
            seats_price_str = soup.find("input", id=re.compile(f"{seats_id}_*.")).get("id").split("_")[-1]
            try:
                seats_price = float(seats_price_str)
            except:
                seats_price = 0

            seats_available = len(section.find_all("li", class_="rc-availableseat"))
            seats_sold = len(section.find_all("li", class_="rc-selectedseats"))
            seats_all = seats_available + seats_sold
            seats = Seats(
                title=seats_name,
                all=seats_all,
                sold=seats_sold,
                price=seats_price
            )
            seats_list.append(seats)
        return seats_list
    except:
        return seats_list


async def get_screen_name(session: aiohttp.ClientSession, showtime_id) -> str:
    params = {
        "sessionid": showtime_id,
    }
    url = f"https://www.theroxycinemas.com/seats/{showtime_id}"
    html = await get_request(session, url, params=params)
    soup = BeautifulSoup(html, "lxml")
    screen_name_tag = soup.find("h1")
    substring = "^~^ Xtreme"
    if screen_name_tag:
        screen_name = screen_name_tag.text.strip()
        if substring in screen_name:
            screen_name = screen_name.replace(substring, "")
        else:
            screen_name = screen_name_tag.text.strip()
    else:
        screen_name = ""
    return screen_name


async def get_seats(showtime: Showtime) -> Showtime:
    try:
        async with SEMAPHORE:
            logging.debug(f"Start receiving seats for {showtime.movie.title} in {showtime.cinema.name} at "
                          f"{showtime.datetime_obj.strftime('%d %B %H:%M')} showtime")
            async with aiohttp.ClientSession(headers=HEADERS) as sess:
                ticket_detail_dict = await get_ticket_details(sess, showtime.id)
                ticket_details = ticket_detail_dict["ticket_details"]
                tickets_total_amount = ticket_detail_dict["tickets_total_amount"]

                json_data = {
                    "sessionid": showtime.id,
                    "Tdetails": ticket_details,
                    "totalamount": f"AED {tickets_total_amount}",
                    "Skipseat": "False",
                    "Skipfnb": "False",
                }
                url = "https://www.theroxycinemas.com/offers/UpdateTickettypedetails"
                await sess.post(url, json=json_data)
                screen_name = await get_screen_name(sess, showtime.id)
                seats = await get_seats_data(sess, ticket_details)
            if seats:
                logging.debug(f"Received seats for {showtime.movie.title} in {showtime.cinema.name} at "
                              f"{showtime.datetime_obj.strftime('%d %B %H:%M')} showtime")

            showtime_with_seats = showtime._replace(seats=seats, screen_name=screen_name)
        return showtime_with_seats
    except:
        pass


async def collect_seats_data(showtimes: List[Showtime]) -> List[Showtime]:
    tasks = []
    for showtime in showtimes:
        task = asyncio.create_task(get_seats(showtime))
        tasks.append(task)
    showtime_with_seats = await asyncio.gather(*tasks)
    logging.info(f"Summary received {len(showtime_with_seats)} showtimes with seats data.")
    return showtime_with_seats


async def main(SEARCH_DATES_LIST: List[str]):
    global SEMAPHORE
    SEMAPHORE = asyncio.Semaphore(REQUESTS_LIMIT)
    connector = aiohttp.TCPConnector(force_close=True, limit=TCPCONNECTOR_LIMIT)
    timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SEC)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS, timeout=timeout) as session:
        movies = await get_movies(session)
        showtimes = await get_showtimes(session, movies, SEARCH_DATES_LIST)
        showtimes_with_seats = await collect_seats_data(showtimes)
    return showtimes_with_seats


def create_df(showtimes):
    df1 = pd.DataFrame(data=showtimes,
                       columns=['country', 'movie_name', 'cinema_title', 'show_time', 'seats_area', 'seats_total',
                                'seats_sold', 'seats_experience', 'seats_screen', 'ticket_price', 'scraping_date',
                                'processing_date', 'movie_language'])
    print(df1)
    # df1.to_csv('/usr/roxy_final11.csv')


def calling_main():
    SEARCH_DATES_LIST = []
    SEARCH_DATES = date.today()
    formatted_search_date = SEARCH_DATES.strftime("%Y-%m-%d")
    SEARCH_DATES_LIST.append(formatted_search_date)
    showtimes = asyncio.get_event_loop()
    showtimes = showtimes.run_until_complete(main(SEARCH_DATES_LIST))
    data = []
    for showtime in showtimes:
        for seats in showtime.seats:
            country = 'UAE'
            current_date = date.today()
            scraping_date = datetime.now().strftime('%Y%m%d %H:%M')
            processing_date = current_date.strftime("%Y%m%d")
            print("printing...")
            total = [country, showtime.movie.title, showtime.cinema.name,
                     showtime.datetime_obj.strftime("%Y-%m-%d %H:%M"), seats.title, seats.all, seats.sold,
                     showtime.experience, showtime.screen_name, seats.price, scraping_date, processing_date,
                     showtime.movie.language]
            print(total)
            data.append(total)
    create_df(data)


def save_to_django_db(task: ScraperTask):
    logging.info(f"Start task for {task.cinema_provider.name} {task.id}")
    search_date_str = task.date_query.strftime("%Y-%m-%d")
    showtimes = asyncio.get_event_loop()
    showtimes = showtimes.run_until_complete(main([search_date_str]))

    for showtime in showtimes:
        cinema, created = Cinema.objects.get_or_create(name=showtime.cinema.name)
        movie, created = DjangoMovie.objects.get_or_create(name=showtime.movie.title)

        for seats in showtime.seats:
            ShowtimeSeats.objects.create(
                task=task,
                cinema=cinema,
                movie=movie,
                datetime=showtime.datetime_obj.strftime("%Y-%m-%d %H:%M"),
                experience=showtime.experience,
                cinema_room=showtime.screen_name,
                all=seats.all,
                sold=seats.sold,
                price=seats.price,
                type=seats.title,
            )


# calling_main()

