import scrapy
import os 
from scrapy.crawler import CrawlerProcess
import os
from urllib.parse import urlparse

class AsicSpider(scrapy.Spider):
    name = 'asic'
    allowed_domains = ['asic.gov.au']
    start_urls = ['https://asic.gov.au/for-business/innovation-hub/enhanced-regulatory-sandbox/']
    custom_settings = {
        'DEPTH_LIMIT': 2,
        'ROBOTSTXT_OBEY': True,
        'DOWNLOAD_FAIL_ON_DATALOSS': False
    }

    def parse(self, response):
        # Extract the body text of the page and save it as .rtf
        text_content = response.xpath("//body//text()").getall()
        text_content = ' '.join(text_content).strip()
        self.save_text_content(response.url, text_content)

        # Follow all links that are not to images or scripts and are documents of interest
        all_links = response.css('a::attr(href)').getall()
        for link in all_links:
            if not link.endswith(('.png', '.jpg', '.jpeg', '.gif', '.js', '.css')) and link.endswith(('.docx', '.xlsx', '.pdf')):
                absolute_url = response.urljoin(link)
                yield scrapy.Request(absolute_url, callback=self.save_file)
            elif not link.endswith(('.png', '.jpg', '.jpeg', '.gif', '.js', '.css')):
                absolute_url = response.urljoin(link)
                yield response.follow(absolute_url, self.parse)

    def save_text_content(self, url, text):
        # Directory where the script resides
        base_dir = '/Users/pranay/Documents/GitHub/personal-repos/scrappy'

        # File name handling
        filename = os.path.basename(urlparse(url).path)
        if not filename:
            filename = "index"
        safe_filename = ''.join([c for c in filename if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        rtf_filename = f"{safe_filename}.rtf"
        
        file_path = os.path.join(base_dir, rtf_filename)

        # Save the RTF content
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write("{\\rtf1\\ansi\\ansicpg1252\\cocoartf1671\\cocoasubrtf600\n")
            file.write(text.replace('\n', '\\line '))
            file.write("\n}")


# Assuming this snippet is part of your Scrapy spider's method
    def save_file(self, response):
        # Directory where the script resides, directly use base_dir
        base_dir = '/Users/pranay/Documents/GitHub/personal-repos/scrappy/content'

        # Ensure the base directory exists (it should, but this is just in case)
        os.makedirs(base_dir, exist_ok=True)

        # Construct the file path
        filename = os.path.basename(response.url)
        file_path = os.path.join(base_dir, filename)

        # Save the file
        with open(file_path, 'wb') as file:
            file.write(response.body)



if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(AsicSpider)
    process.start()
