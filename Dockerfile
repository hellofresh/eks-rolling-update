FROM python:3.7.2-alpine3.9

RUN apk add --update --upgrade --no-cache bash
COPY requirements.txt /
RUN pip3 install -r requirements.txt
COPY config.py eks-rolling-update.py /
