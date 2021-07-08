FROM python:3
VOLUME ["/root/.teos"]
WORKDIR /srv
ADD . /srv/python-teos
RUN apt-get update && \
    apt-get -y --no-install-recommends install libffi-dev libssl-dev pkg-config libleveldb-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN mkdir /root/.teos && cd python-teos && pip install .
WORKDIR /srv/python-teos 
EXPOSE 9814/tcp
ENTRYPOINT [ "/srv/python-teos/docker/entrypoint.sh" ]
