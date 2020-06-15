FROM python:3
ENV APP_PATH=/srv/python-teos
VOLUME ["~/.teos"]
WORKDIR /srv
ADD . /srv/python-teos
RUN mkdir ~/.teos && cd python-teos &&  pip install -r requirements.txt && python generate_keys.py -d ~/.teos
ENV PYTHONPATH=$APP_PATH
WORKDIR /srv/python-teos 
EXPOSE 9814/tcp
ENTRYPOINT [ "/srv/python-teos/docker/entrypoint.sh" ]
