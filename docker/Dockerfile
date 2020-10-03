FROM python:3
VOLUME ["~/.teos"]
WORKDIR /srv
ADD . /srv/python-teos
RUN apt-get update && apt-get -y install libffi-dev libssl-dev pkg-config libleveldb-dev
RUN mkdir ~/.teos && cd python-teos &&  pip install .
WORKDIR /srv/python-teos 
EXPOSE 9814/tcp
ENTRYPOINT [ "/srv/python-teos/docker/entrypoint.sh" ]
