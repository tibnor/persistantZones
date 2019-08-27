FROM python:3.7

ADD requirements.txt .
ADD libsoundtouch/requirements.txt libsoundtouch/
RUN pip install -r requirements.txt
COPY . .
CMD python libsoundtouch/persistantGroup.py