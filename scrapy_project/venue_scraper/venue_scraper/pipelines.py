# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
"""
class VenueScraperPipeline:
    def process_item(self, item, spider=None):
        for key, value in list(item.items()):
            if isinstance(value, str):
                item[key] = " ".join(value.split())
        return item
# class VenueScraperPipeline:
#     def process_item(self, item, spider):
#         for key, value in list(item.items()):
#             if isinstance(value, str):
#                 item[key] = " ".join(value.split())
#         return item
"""
# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class VenueScraperPipeline:
    def process_item(self, item, spider):
        return item