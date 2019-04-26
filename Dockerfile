FROM python:3.7.2-alpine3.9

COPY requirements.txt /
RUN pip3 install -r requirements.txt
COPY config.py eks-rolling-update.py /
