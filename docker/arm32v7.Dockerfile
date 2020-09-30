FROM rycus86/armhf-debian-qemu
ENV APP_PATH=/srv/python-teos
VOLUME ["~/.teos"]
WORKDIR /srv
ADD . /srv/python-teos
RUN apt-get update && apt-get -y install python3 python3-pip libffi-dev libssl-dev pkg-config libleveldb-dev
RUN mkdir ~/.teos && cd python-teos && python3 setup.py install
ENV PYTHONPATH=$APP_PATH
WORKDIR /srv/python-teos
EXPOSE 9814/tcp
ENTRYPOINT [ "/srv/python-teos/docker/entrypoint.sh" ]