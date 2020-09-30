FROM python:3
ENV APP_PATH=/srv/python-teos
VOLUME ["~/.teos"]
WORKDIR /srv
ADD . /srv/python-teos
RUN apt-get update && apt-get -y install libffi-dev libssl-dev pkg-config libleveldb-dev
RUN mkdir ~/.teos && cd python-teos &&  pip install -r requirements.txt
ENV PYTHONPATH=$APP_PATH
WORKDIR /srv/python-teos 
EXPOSE 9814/tcp
ENTRYPOINT [ "/srv/python-teos/docker/entrypoint.sh" ]
