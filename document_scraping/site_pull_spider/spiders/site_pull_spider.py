from scrapy.spiders import Spider
from scrapy.linkextractors import LinkExtractor
from scrapy import Item, Field, signals, Request
import urllib
import regex as re
import os
import dateparser
import datetime
import json 

class UrlItem(Item):
    url = Field()
    
class SitePullSpider(Spider):
    name = 'site_pull'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize 
        self.redirects = {}
        
        self.link_extractor = LinkExtractor(
            tags = "a",
            deny_extensions = ["css","png","jpg","xml","gif","ico","pdf"]
        )
        
        # Get the set of allowed domains from the start urls
        allowed = set() 

        for url in self.start_urls:
            parts = urllib.parse.urlparse(url)
            allowed.add(parts.netloc)

        self.allowed_domains = list(allowed)
        
        super().__init__(*args, **kwargs)
    
    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(SitePullSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider
    
    def create_filepath(self, url):
        """
        Creates a local filepath from a url
        """
        url = re.sub('http://|https://','',url)
        path = os.path.join(self.out_dir,*url.split('/')) + '.html'
        path = re.sub('\?','-',path)
        return path
        
    def parse(self, response):
        """
        Save a url to file, if the modified date is more recent than local file
        """
        if not any([response.url.startswith(start_url) for start_url in self.start_urls]):
            # only allow child pages of start urls
            print(f"Not visiting {response.url}")
            return
        
        if 'redirect_times' in response.meta and response.meta['redirect_times'] > 0:
            # URL was redirected, add to list
            original_url = response.meta['redirect_urls'][0]
            self.redirects[original_url] = response.url
            
        filename = self.create_filepath(response.url)
        should_download = True
        
        if os.path.exists(filename):
            site_modified = dateparser.parse(str(response.headers.get("last-modified"), encoding='utf-8'))
            file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(filename)).astimezone()
            
            if site_modified < file_modified: 
                # Site hasn't been modified since last download, skip
                print(f"Skipping download of {response.url}")
                should_download = False
        else:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Write page to file
        if should_download:
            with open(filename, 'w+b') as f:
                f.write(response.body)
        
        # Visit all urls from this page
        for link in self.link_extractor.extract_links(response):
            yield Request(link.url, callback=self.parse)
            
    def spider_closed(self, spider):
        # Save the redirects.txt to file
        redirect_path = os.path.join(self.out_dir,'redirects.txt')
        with open(redirect_path,'w') as f: 
            json.dump(self.redirects,f)