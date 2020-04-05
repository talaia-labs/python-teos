FROM python:3
ENV APP_PATH=/srv/python-teos
VOLUME ["~/.teos"]
WORKDIR /srv
RUN mkdir ~/.teos &&  git clone https://github.com/talaia-labs/python-teos && cd python-teos &&  pip install -r requirements.txt && python generate_keys.py -d ~/.teos
ENV PYTHONPATH=$APP_PATH
WORKDIR /srv/python-teos 
COPY entrypoint.sh /srv/python-teos/entrypoint.sh
RUN chmod +x /srv/python-teos/entrypoint.sh
ENTRYPOINT [ "/srv/python-teos/entrypoint.sh" ]
#CMD ["sh","-c","/usr/local/bin/python3 -m teos.teosd --btcrpcuser=$BTC_RPC_USER --btcrpcpassword=$BTC_RPC_PASSWD --btcrpcconnect=$BTC_RPC_HOST"]
