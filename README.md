## Deploy
1. Install required packages:  
`apt install docker docker-compose git`
2. Copy the project. For example from github:  
``

## Scrapers
1. All scrapers must be stored in the "scrapers" directory with the .py extension.
2. Inside each file there must be a "save_to_django_db" function. This function should add data about movie shows 
to the database.
3. In the admin panel, you can add a cinema provider and select the necessary scraper there.
4. After scrapers changed you should rebuild docker container:
`docker-compose up -d --build django celery`

## Caching
1. Scrapers save all received data to the database.
2. CSV file is generated from the data in the database on every user call.
3. For one cinema provider, only one scraper can work at a time.
4. If too little time has passed since the last launch of the scraper, then the data is taken from the last launch of 
the scraper.
5. This time in seconds can be changed in the SCRAPERS_CACHE_TIME variable in the .env file. Docker container needs to 
be restarted after changes
