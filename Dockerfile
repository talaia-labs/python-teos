# Use the official Ubuntu 16.04 as a parent image.
FROM ubuntu:16.04

# Update the package list and install software properties common.
RUN apt-get update && apt-get install -y software-properties-common autoconf automake build-essential git libtool \
libgmp-dev libsqlite3-dev python python3 net-tools zlib1g-dev vim wget curl iputils-ping

# Install pip
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
RUN python3 get-pip.py

# Add pisa files
ADD pisa /root/pisa_btc
WORKDIR /root/pisa_btc

# Export pythonpath
RUN echo export PYTHONPATH="$PYTHONPATH:/root/pisa_btc/" >> /root/.bashrc

# Install dependencies
RUN pip3 install -r requirements.txt
