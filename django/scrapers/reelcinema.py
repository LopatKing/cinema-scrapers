import time
import requests
import json
import logging
import re
import urllib.parse
from datetime import datetime
from random import randint
from typing import List, Optional
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from requests_html import AsyncHTMLSession
from datetime import date

from cinemas.models import Cinema, ScraperTask, ShowtimeSeats
from cinemas.models import Movie as DjangoMovie
from common.models import Country

session = AsyncHTMLSession()


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("./novocinemas.log"),
        logging.StreamHandler()
    ]
)
MAIN_PAGE = "https://reelcinemas.com/en-ae/"
TCPCONNECTOR_LIMIT = 50
SESSION_TIMEOUT_SEC = 5200

SLEEP_BEFORE_REQUESTS_SEC = 1
# get movies for this day
DAY = date.today().strftime('%Y-%m-%d')
'''{
    movie : 
        {mall_name : 
            {
            exp : [1,2,3] - sold/empty
            }
        }
}'''
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
}


async def post_request(session: aiohttp.ClientSession, url: str,
                       params: dict = None,
                       data: dict = None,
                       json: dict = None) -> Optional[str]:
    for i in range(3):
        try:
            async with session.post(url, params=params, data=data, json=json, timeout=120) as resp:
                logging.debug(f"Loading data from {url}, params - {params}, data - {data}, json - {json}")
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
    return None


async def get_html(session: aiohttp.ClientSession, url: str, params: dict = None):
    if params is None:
        params = {}

    while True:
        async with session.get(url, params=params) as resp:
            logging.debug(f"Loading page {url}, params - {params}")
            try:
                if resp.ok:
                    return await resp.text()
                else:
                    logging.error(f"Page failed to load. Url - {resp.url}. Status code - {resp.status}. Trying again")
                    st_loop = asyncio.new_event_loop()
                    await st_loop.sleep(randint(5, 60))
            except Exception as e:
                print("Insdie get_html execption..")


def get_asp_net_cookie():
    url = "https://reelcinemas.com/en-ae/"
    time.sleep(SLEEP_BEFORE_REQUESTS_SEC)
    response = requests.get(url, headers=HEADERS, verify=False)
    asp_net_cookie = response.cookies['ASP.NET_SessionId']
    return asp_net_cookie


def extract_url_parts(onclick):  ##get the movie id and title
    pattern = r'MovieDetailsPage\("(.*?)","(.*?)"\)'
    match = re.search(pattern, onclick)
    if match:
        return match.group(1), match.group(2)
    return None, None


async def get_movies(session: aiohttp.ClientSession):  ##get movie name and url
    url = "https://reelcinemas.com/en-ae/"
    time.sleep(SLEEP_BEFORE_REQUESTS_SEC)
    response = await get_html(session, url)
    # if response.status_code == 200:
    # Save the response content to a file
    #     with open('/Users/n.purushottam.lagad/Downloads/reel.txt','wb') as file:
    #         file.write(response.content)
    # print(f"Downloaded the response content")
    soup = BeautifulSoup(response, 'html.parser')
    movie_items = soup.find_all('div', {'class': 'movie-item'})
    movies = []
    for movie_item in movie_items:
        try:
            movie_title = movie_item['id']
            language = soup.find('div', class_='duration-language').find_all('span')[-1].get_text(strip=True)
            movie_id, title_dashed = extract_url_parts(
                str(movie_item))  ## movie_id = group(1) and title_dashed = group(2)
            movie_url = f"https://reelcinemas.com/en-ae/movie-details/{movie_id}/{title_dashed}"  ##movie_id = HO00003413 & title_dashed = Fast-X-
            movies.append((movie_title, movie_url, movie_id, language))
        except:
            pass
    print(f"movies_len : {len(movies)}")
    return movies


def get_movie_session(asp_net_cookie, magic_string):
    url = "https://reelcinemas.com/WebApi/api/UserAPI/CreateMovieCookie"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "ASP.NET_SessionId": asp_net_cookie
    }
    # time.sleep(SLEEP_BEFORE_REQUESTS_SEC)
    response = requests.post(url=url, headers=headers, data='"' + magic_string + '"', verify=False)
    movie_session = response.cookies['movieSession']
    return movie_session


def extract_num_empty(input_str):
    pattern = r'status:empty'
    matches = re.findall(pattern, input_str)
    return len(matches)


def extract_num_sold(input_str):
    pattern = r'status:sold'
    matches = re.findall(pattern, input_str)
    return len(matches)


def extract_experience(input_str):
    return input_str['Experience']
    # exp = input_str['cinemaConfig']
    # experience = exp['ComboSeatSelection']['Experiences'][0]
    # return experience


async def get_seating_info(session: aiohttp.ClientSession):
    url = "https://reelcinemas.com/WebApi/api/SeatLayourAPI/GetSeatLayout"
    # cookies = {
    #     "ASP.NET_SessionId": asp_net_cookie,
    #     "movieSession": movie_session,
    # }
    response = await get_html(session, url)
    t = json.loads(response)
    experience = extract_experience(t)
    area_entity_list = t["Sourcedata"]["AreaEntityList"]
    ticket_list = t.get("Sourcedata").get("TicketList", [])
    seats_list = []
    if area_entity_list:
        for area_entity in area_entity_list:
            area_code = area_entity["AreaCode"]
            area_description = area_entity["AreaDescription"]
            row_entity_list = area_entity["rowEntityList"]

            empty_count = sum(1 for row_entity in row_entity_list for seat_entity in row_entity["seatEntityList"] if
                              seat_entity["Status"] == "Empty")
            sold_count = sum(1 for row_entity in row_entity_list for seat_entity in row_entity["seatEntityList"] if
                             seat_entity["Status"] == "Sold")
            for ticket in ticket_list:
                if ticket["AreaCode"] == area_code:
                    price_in_aed = ticket["PriceInAed"]
            print(f"AreaCode: {area_code}, AreaDescription: {area_description}")
            print(f"Empty Count: {empty_count}, Sold Count: {sold_count}, {price_in_aed}")
            seats_price = [area_description, empty_count, sold_count, experience, price_in_aed]
            print(seats_price)
            seats_list.append(seats_price)
        return seats_list


# async def get_seating_info(session: aiohttp.ClientSession):
#     try:
#         url = "https://reelcinemas.com/WebApi/api/SeatLayourAPI/GetSeatLayout"
#         response = await get_html(session, url)
#         t = json.loads(response)
#         experience = extract_experience(t)
#         s = response.replace('"', '').lower()
#         num_empty = extract_num_empty(s)
#         num_sold = extract_num_sold(s)
#         ticket_list = t.get("Sourcedata").get("TicketList", [])
#         ticket_descriptions = [ticket["TicketDescription"] for ticket in ticket_list]
#         ticket_prices = [ticket["PriceInAed"] for ticket in ticket_list]
#         return num_empty, num_sold, experience, ticket_descriptions, ticket_prices
#     except Exception as e:
#         print("Inside get_seating_info exception")
#         print(e)


async def get_seats(showtimes):
    seats = []
    try:
        magic_string = showtimes[-2]
        connector = aiohttp.TCPConnector(force_close=True, limit=TCPCONNECTOR_LIMIT)
        timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SEC)

        # In order not to work with cookies manually, we start a new session.
        # Session cookies persist throughout the session. Same functionality in the requests.Session class
        async with aiohttp.ClientSession(connector=connector, headers=HEADERS, timeout=timeout) as new_session:
            url = "https://reelcinemas.com/en-ae/"
            await get_html(new_session, url)

            url = "https://reelcinemas.com/WebApi/api/UserAPI/CreateMovieCookie"
            await post_request(new_session, url, json=magic_string)
            seating_info = await get_seating_info(new_session)

        try:
            if seating_info:
                for sp in seating_info:
                    num_empty = sp[1]
                    num_sold = sp[2]
                    seats_area = sp[0]
                    num_total = num_empty + num_sold
                    print(f"{showtimes[1]}--{showtimes[2]}--{showtimes[3]}--{num_total}")
                    country = showtimes[0]
                    movie_name = showtimes[1]
                    cinema_title = showtimes[2]
                    showtime = showtimes[3]
                    scraping_date = showtimes[4]
                    processing_date = showtimes[5]
                    movie_language = showtimes[7]
                    experience = sp[3]
                    ticket_prices = sp[4]

                    print(f"{showtimes[1]}--{showtimes[2]}--{showtimes[3]}--{num_total}--{experience}--{ticket_prices}")
                    total = [country, movie_name, cinema_title, showtime, seats_area, num_total, num_sold, experience,
                             ticket_prices, scraping_date, processing_date, movie_language]
                    print(total)
                    seats.append(total)
                return seats
        except Exception as e:
            print("INSIDE INSIDE INSIDE...")
            print(e)
            pass
    except ConnectionError:
        print("Connection error...")
        print("break...")
        pass


async def get_showtimes_by_date(session: aiohttp.ClientSession, movie, date: datetime.date, code) -> List:
    showtimes = []
    params = {
        "movieId": movie[2],
        "date": date.strftime("%Y-%m-%d"),
        "cinemas": code
    }
    url = urllib.parse.urljoin(MAIN_PAGE, "MovieDetails/GetMovieShowTimes")
    response = await post_request(session, url, params=params)
    #                 with open('/Users/n.purushottam.lagad/Downloads/reel_show.txt','w') as file:
    #                         file.write(html)
    response_json = json.loads(response)
    soup = BeautifulSoup(response_json, "lxml")
    if "No Schedules found" in response:
        return []

    a = soup.find_all('a')
    for a_tag in a:
        if a_tag.get("onclick"):
            magic_string = re.search(r'"([^"]*)"', a_tag.get("onclick")).group(1)
        elif a_tag.get("href"):
            magic_string = a_tag.get("href").split("','")[6]
        else:
            raise ValueError("Showtime parsing error. Unexpected html")

        showtime = a_tag.find('div', class_='showtime').text
        print('magic_string:', magic_string)
        print('showtime:', showtime)
        print('---')
        # time_obj = datetime.strptime(time_a, "%I:%M %p").time()
        # url = urllib.parse.urljoin(MAIN_PAGE, time_a.get("href"))
        # datetime_obj = datetime.combine(date, time_obj)
        movie_name = movie[0]
        movie_language = movie[3]
        if params['cinemas'] == '0001':
            cinema_title = 'The Dubai Mall'
        if params['cinemas'] == '0002':
            cinema_title = 'Dubai Marina Mall'
        if params['cinemas'] == '0006':
            cinema_title = 'The Springs Souk'
        print(f"{movie_name}--{cinema_title}--{showtime}")
        country = MAIN_PAGE.split("/")[3]
        current_date = date.today()
        scraping_date = datetime.now().strftime('%Y%m%d %H:%M')
        processing_date = current_date.strftime("%Y%m%d")

        total = [country, movie_name, cinema_title, showtime, scraping_date, processing_date,
                 magic_string, movie_language]
        print(total)
        showtimes.append(total)
    return showtimes


async def get_movie_showtimes(session: aiohttp.ClientSession, movie, query_date_str: str):
    movie_html = await get_html(session, movie[1])
    # with open('/Users/n.purushottam.lagad/Downloads/reel_movie_show.txt','w') as file:
    #         file.write(movie_html)
    soup = BeautifulSoup(movie_html, "lxml")
    # language_id = soup.find("input", {"id": "SelectedLanguageId"}).get("value")
    # movie = movie._replace(language_id=language_id)

    available_date_items = soup.findAll("div", class_="dboxelement")
    showtimes = []
    cinema_code = ['0001', '0002', '0006']
    for date_item in available_date_items:
        date_str = date_item.get('id')
        if date_str != query_date_str:
            continue
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        for code in cinema_code:
            showtimes += await get_showtimes_by_date(session, movie, date_obj, code)
    logging.info(f"Received {len(showtimes)} showtimes for {movie[0]}")
    return showtimes


async def get_all_showtimes(session: aiohttp.ClientSession,
                            movies,
                            date_str: str):  ## create separate task for each movie to get showtimes
    tasks = []
    st_loop = asyncio.new_event_loop()
    for movie in movies:
        task = st_loop.create_task(get_movie_showtimes(session, movie, date_str))
        tasks.append(task)
    showtimes = await asyncio.gather(*tasks)
    results = []
    for showtime in showtimes:
        results += showtime
    logging.info(f"Summary received {len(results)} showtimes.")
    return results


async def get_all_seats(movie_showtimes):
    tasks = []
    st_loop = asyncio.new_event_loop()
    for show in movie_showtimes:
        task = st_loop.create_task(get_seats(show))
        tasks.append(task)
    showtimes = await asyncio.gather(*tasks)
    results = []
    for showtime in showtimes:
        results += showtime
    logging.info(f"Summary received {len(results)} showtimes in final layer.")
    return results


async def main(date_str):
    connector = aiohttp.TCPConnector(force_close=True, limit=TCPCONNECTOR_LIMIT)
    timeout = aiohttp.ClientTimeout(total=SESSION_TIMEOUT_SEC)
    async with aiohttp.ClientSession(connector=connector, headers=HEADERS, timeout=timeout) as session:
        # total_movies = []
        # start_time = time.time()
        # asp_net_cookie = get_asp_net_cookie()
        movies = await get_movies(session)
        movie_showtimes = await get_all_showtimes(session, movies, date_str)
        movie_seats = await get_all_seats(movie_showtimes)

        return movie_seats
        # df1 = pd.DataFrame(data=movie_seats,
        #                    columns=['country', 'movie_name', 'cinema_title', 'show_time', 'seats_area', 'seats_total',
        #                             'seats_sold', 'experience', 'ticket_prices', 'scraping_date',
        #                             'processing_date', 'movie_language'])
        # df1.to_csv("reel_final5.csv")


def calling_main(date_str):
    showtimes = asyncio.new_event_loop()
    showtimes = showtimes.run_until_complete(main(date_str))


def save_to_django_db(task: ScraperTask):
    logging.info(f"Start task for {task.cinema_provider.name} {task.id}")
    search_date_str = task.date_query.strftime("%Y-%m-%d")
    showtimes = asyncio.run(main(search_date_str))

    for showtime in showtimes:
        country, created = Country.objects.get_or_create(name=showtime[0])
        cinema, created = Cinema.objects.get_or_create(name=showtime[2], country=country)
        movie, created = DjangoMovie.objects.get_or_create(name=showtime[1], language=showtime[11])

        showtime_time_obj = datetime.strptime(showtime[3], '%I:%M %p')
        showtime_datetime_obj = datetime.combine(task.date_query, showtime_time_obj.time())
        ShowtimeSeats.objects.create(
            task=task,
            cinema=cinema,
            movie=movie,
            datetime=showtime_datetime_obj,
            experience=showtime[7],
            all=showtime[5],
            sold=showtime[6],
            price=showtime[8],
            area=showtime[4],
        )
