# Scrapy settings for general_spider project
#
# For simplicity, this file contains only the most important settings by
# default. All the other settings are documented here:
#
#     http://doc.scrapy.org/en/latest/topics/settings.html
#

import sys
import os
from os.path import dirname
path = dirname(dirname(os.path.abspath(os.path.dirname(__file__))))
sys.path.append(path)

BOT_NAME = 'site_pull_spider'

SPIDER_MODULES = ['site_pull_spider.spiders']
NEWSPIDER_MODULE = 'site_pull_spider.spiders'

LOG_LEVEL = 'INFO'
DOWNLOAD_DELAY = 1
COOKIES_ENABLED = False
ROBOTSTXT_OBEY = False
USER_AGENT = "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36"