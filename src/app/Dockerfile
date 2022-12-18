FROM python:3.10

WORKDIR /opt/app

# Python dependenices
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Source code
COPY src ./src
COPY config ./config

# Server port
EXPOSE 4840

CMD ["python3", "-m", "src.app.server"]
