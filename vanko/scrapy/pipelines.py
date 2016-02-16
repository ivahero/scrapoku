from . import CustomSettings

CustomSettings.register(
    ITEM_PIPELINES={
        'vanko.scrapy.EarlyProcessPipeline': 110,
        'scrapy.pipelines.images.ImagesPipeline': 120,
        'vanko.scrapy.ItemStorePipeline': 130,
        },
    IMAGES_STORE_tmpl='%(images_dir)s',
    )


class ItemStorePipeline(object):
    def process_item(self, item, spider):
        process = getattr(spider, '_process_store_item', None)
        if process:
            process(item)
        return item


class EarlyProcessPipeline(object):
    def process_item(self, item, spider):
        process = getattr(spider, 'process_early_item', None)
        if process:
            process(item)
        return item
