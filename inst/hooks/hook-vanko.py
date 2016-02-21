import os
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('vanko', subdir='scrapy')
datas = filter(lambda x: os.path.basename(x[0]) != 'LICENSE', datas)

hiddenimports = [
    'vanko.scrapy.webdriver.download',
    ]
