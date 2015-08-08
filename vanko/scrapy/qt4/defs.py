
WT_SHOW = False
WT_VERBOSE = False
WT_FORCE_QCRAWLER = False
WT_PAGE_TIMEOUT = 300
WT_SHOW_POOL_SIZE = 0
WT_HIDE_POOL_SIZE = 1
WT_VIRTUAL_DISPLAY = False

WT_COMPACT_COOKIES = True
WT_LOAD_IMAGES = False
WT_CHECK_INTERVAL = 2.0  # seconds
WT_RAISE_ON_TIMEOUT = True
WT_THREADED_DOWNLOAD = False
WT_PATCH_CRAWLER_PROCESS = True

WT_USER_AGENT = ('Mozilla/5.0 (Windows NT 6.3; WOW64; rv:38.0)'
                 ' Gecko/20100101 Firefox/38.0')

WT_USER_AGENT_LIST = [
    # --IE 9.0 --
    'Mozilla/5.0 (Windows; U; MSIE 9.0; WIndows NT 9.0; en-US))',
    'Mozilla/5.0 (Windows; U; MSIE 9.0; Windows NT 9.0; en-US)',
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 7.1; Trident/5.0)',
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64;'
     ' Trident/5.0; SLCC2; Media Center PC 6.0; InfoPath.3;'
     ' MS-RTC LM 8; Zune 4.7)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64;'
     ' Trident/5.0; SLCC2; Media Center PC 6.0; InfoPath.3;'
     ' MS-RTC LM 8; Zune 4.7'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64;'
     ' Trident/5.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729;'
     ' .NET CLR 3.0.30729; Media Center PC 6.0; Zune 4.0; InfoPath.3;'
     ' MS-RTC LM 8; .NET4.0C; .NET4.0E)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64;'
     ' Trident/5.0; chromeframe/12.0.742.112)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64;'
     ' Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729;'
     ' .NET CLR 2.0.50727; Media Center PC 6.0)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64;'
     ' x64; Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729;'
     ' .NET CLR 2.0.50727; Media Center PC 6.0)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64;'
     ' x64; Trident/5.0; .NET CLR 2.0.50727; SLCC2; .NET CLR 3.5.30729;'
     ' .NET CLR 3.0.30729; Media Center PC 6.0; Zune 4.0; Tablet PC 2.0;'
     ' InfoPath.3; .NET4.0C; .NET4.0E)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64;'
     ' x64; Trident/5.0'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0;'
     ' yie8)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0;'
     ' SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30729;'
     ' Media Center PC 6.0; InfoPath.2; .NET CLR 1.1.4322; .NET4.0C;'
     ' Tablet PC 2.0)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0;'
     ' FunWebProducts)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0;'
     ' chromeframe/13.0.782.215)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0;'
     ' chromeframe/11.0.696.57)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)'
     ' chromeframe/10.0.648.205'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/4.0;'
     ' GTB7.4; InfoPath.1; SV1; .NET CLR 2.8.52393; WOW64; en-US)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.0; Trident/5.0;'
     ' chromeframe/11.0.696.57)'),
    ('Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.0; Trident/4.0;'
     ' GTB7.4; InfoPath.3; SV1; .NET CLR 3.1.76908; WOW64; en-US)'),
    # -- IE 10.0 --
    ('Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1;'
     ' WOW64; Trident/6.0)'),
    ('Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)'),
    ('Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/5.0)'),
    ('Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/4.0;'
     ' InfoPath.2; SV1; .NET CLR 2.0.50727; WOW64)'),
    ('Mozilla/5.0 (compatible; MSIE 10.0; Macintosh; Intel Mac OS X 10_7_3;'
     ' Trident/6.0)'),
    ('Mozilla/4.0 (Compatible; MSIE 8.0; Windows NT 5.2; Trident/6.0)'),
    ('Mozilla/4.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/5.0)'),
    ('Mozilla/1.22 (compatible; MSIE 10.0; Windows 3.1)'),
    # -- Chrome 36..41 --
    ('Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2227.1 Safari/537.36'),
    ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2226.0 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 6.4; WOW64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/41.0.2224.3 Safari/537.36'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/37.0.2062.124 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 4.0; WOW64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36'),
    ('Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36'),
    ('Mozilla/5.0 (X11; OpenBSD i386) AppleWebKit/537.36 '
     '(KHTML, like Gecko) Chrome/36.0.1985.125 Safari/537.36'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36'
     ' (KHTML, like Gecko) Chrome/36.0.1944.0 Safari/537.36'),
    # -- Firefox --
    ('Mozilla/5.0 (Windows NT 6.3; WOW64; rv:38.0)'
     ' Gecko/20100101 Firefox/38.0'),
    ('Mozilla/5.0 (Windows NT 6.3; WOW64; rv:37.0)'
     ' Gecko/20100101 Firefox/37.0'),
    ('Mozilla/5.0 (Windows NT 6.3; rv:36.0) Gecko/20100101 Firefox/36.0'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10; rv:33.0)'
     ' Gecko/20100101 Firefox/33.0'),
    ('Mozilla/5.0 (X11; Linux i586; rv:31.0)'
     ' Gecko/20100101 Firefox/31.0'),
    ('Mozilla/5.0 (Windows NT 6.1; WOW64; rv:31.0)'
     ' Gecko/20130401 Firefox/31.0'),
    ('Mozilla/5.0 (Windows NT 5.1; rv:31.0) Gecko/20100101 Firefox/31.0')
]
