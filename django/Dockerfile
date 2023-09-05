# pull official base image
FROM python:3.11.5-bookworm

# set work directory
WORKDIR /srv/project

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install psycopg2 dependencies
RUN apt update
RUN apt install -y postgresql-server-dev-all gcc python3-dev musl-dev netcat-traditional libpq-dev postgresql

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY ./entrypoint.sh .

# copy project
COPY ./ ./

# run entrypoint.sh
ENTRYPOINT ["/srv/project/entrypoint.sh"]
CMD ["bash"]
