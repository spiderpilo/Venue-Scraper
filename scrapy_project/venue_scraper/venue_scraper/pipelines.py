# ─────────────────────────────────────────────────────────────────────────────
# pipelines.py — Post-processing for scraped items
#
# In Scrapy, every item yielded by a spider passes through the pipeline
# before being saved. Pipelines are where you clean, validate, enrich,
# or store items (e.g. write to a database).
#
# Pipeline classes are activated in settings.py under ITEM_PIPELINES.
# The number (e.g. 300) is the execution order — lower runs first.
#
# Currently: the active pipeline is a passthrough (returns items unchanged).
# The commented-out version below it showed how to strip extra whitespace.
# ─────────────────────────────────────────────────────────────────────────────
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