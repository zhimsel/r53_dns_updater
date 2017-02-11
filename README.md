# r53-dns-updater

[![Build Status](https://travis-ci.org/zhimsel/r53-dns-updater.svg?branch=master)](https://travis-ci.org/zhimsel/r53-dns-updater)

`r53-updater` will keep an AWS Route53 DNS record up-to-date against the actual public IP of the host it's run on.

This means it can be used as a cheap and easy way to keep a DNS record pointed towards your non-static home network IP.

## Usage

Please see the [`r53-dns-updater`'s docstring](https://github.com/zhimsel/r53-dns-updater/blob/master/r53-dns-updater.py#L2) for information on how to use this script (or simply run `r53-dns-updater --help`).

`r53-dns-updater` is intended to be run via a scheduler (like `cron`). Simply run it however often you want, and it'll do the rest.

## Installation

`r53-dns-updater` requires only python3 and a few pip modules. Simply run `pip install -r requirements.txt` and run the script!

### Configuration

This script uses boto3, which assumes your AWS credentials are in at least one of a few locations. The easiest way is to set environment variables, but there are a number of other configuration methods. For further instruction on setting up your AWS credentials, see this documentation: http://boto3.readthedocs.io/en/latest/guide/configuration.html
