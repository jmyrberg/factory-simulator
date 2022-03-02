# Fibre availability crawler

This repository contains code for crawling fibre availability data from [Oikotie apartment listings](https://asunnot.oikotie.fi).

Steps

1) Fetch listing links to be fetched later on, and save them into a SQLite database
2) Crawl listing details from unvisited links that were fetched in step 1)


## Structure

```
/crawler: Scrapy spiders, settings, etc.
/notebooks: Jupyter notebooks
/scripts: Helper scripts
/tests: Test cases
```

## Usage

Run step 1. at the root of the repo, i.e. fetch listing links:

```shell
scrapy crawl listing-link -L INFO  --logfile ./results/listing-link.log
```

Run step 2. at the root of the repo, i.e. fetch listing details based on listing links:

```shell
scrapy crawl listing -L INFO --logfile ./results/listing.log
```

It is recommended to automate these steps, e.g. by using cron. The collected data can be analyzed and processed further with the help of [notebooks/](notebooks/).


## Project contacts

* Jesse Myrberg
* Antti-Jussi Salmenpohja
* Jari Nikko
