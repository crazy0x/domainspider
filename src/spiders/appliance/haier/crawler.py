"""
海尔产品爬虫（混合模式）
支持列表+详情一体化爬取，自动去重和增量更新
"""
import scrapy
from datetime import datetime
from scrapy_playwright.page import PageMethod
from src.spiders.base import BaseSpider, URLHelperMixin
from .config import HAIER_BASE_URL


class HaierCrawler(BaseSpider, URLHelperMixin):
    """
    海尔产品爬虫（混合模式）
    
    支持三种爬取模式：
    1. list_only: 只爬列表，收集产品URL和基础信息
    2. detail_only: 只爬详情（需要提供product_urls）
    3. full: 完整爬取（列表+详情，默认模式）
    
    特性：
    - 自动去重（基于URL fingerprint）
    - 支持增量爬取
    - 列表和详情数据分别存储
    """
    
    name = 'haier'
    domain = 'appliance'
    allowed_domains = ['haier.com', 'www.haier.com']
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,  # 合理的延迟
        'CONCURRENT_REQUESTS': 16,  # 合理的总并发
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,  # 合理的每域名并发
        
        # Playwright 设置（关键！）
        'DOWNLOAD_HANDLERS': {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_LAUNCH_OPTIONS': {
            'headless': True,
            'args': ['--disable-blink-features=AutomationControlled']
        },
        # 'PLAYWRIGHT_MAX_CONTEXTS': 16,  # 这个配置可能不存在，先注释掉
        # 'PLAYWRIGHT_MAX_PAGES_PER_CONTEXT': 1,
    }
    
    def __init__(self, crawl_mode='full', level_1=None, level_2=None, 
                 page_start=1, page_end=10, product_urls=None, 
                 task_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 爬取模式
        self.crawl_mode = crawl_mode
        if self.crawl_mode not in ('list_only', 'detail_only', 'full'):
            raise ValueError(f"Invalid crawl_mode: {crawl_mode}. Must be 'list_only', 'detail_only', or 'full'")
        
        # 分类参数
        self.level_1 = level_1
        self.level_2 = level_2
        
        # 分页参数
        self.page_start = int(page_start)
        self.page_end = int(page_end)
        self.current_page = self.page_start
        
        # 任务ID
        self.task_id = task_id or f"{self.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 详情模式的URL列表
        if crawl_mode == 'detail_only':
            if not product_urls:
                raise ValueError("detail_only mode requires product_urls parameter")
            self.product_urls = [url.strip() for url in product_urls.split(',')]
        else:
            self.product_urls = []
        
        # 统计
        self.stats = {
            'list_items': 0,
            'detail_items': 0,
            'skipped_urls': 0,
        }
    
    def start_requests(self):
        """生成初始请求"""
        if self.crawl_mode == 'detail_only':
            # 详情模式：直接爬取提供的URLs
            for url in self.product_urls:
                yield scrapy.Request(
                    url=url,
                    callback=self.parse_detail,
                    meta={
                        'playwright': True,
                        'playwright_page_methods': [
                            PageMethod('wait_for_selector', 'div.proDetail', timeout=20000),
                            PageMethod('wait_for_timeout', 2000),
                        ],
                    },
                    errback=self.errback_playwright,
                )
        else:
            # 列表模式或完整模式：为每一页生成独立请求
            if not self.level_1:
                raise ValueError("list_only and full modes require level_1 parameter")
            
            # 构建列表页URL
            list_path = f"/{self.level_1}/"
            if self.level_2:
                list_path += f"{self.level_2}/"
            
            url = f"{HAIER_BASE_URL}{list_path}"
            
            self.logger.info(f"Starting {self.crawl_mode} mode crawl from: {url}, pages {self.page_start}-{self.page_end}")
            
            # 只请求第1页，后续页面通过递归翻页处理
            # 注意：海尔网站不支持直接访问不同页码的URL，必须通过点击"下一页"来翻页
            yield scrapy.Request(
                url=url,
                callback=self.parse_list,
                meta={
                    'playwright': True,
                    'playwright_include_page': True,  # 必须保持页面对象以支持翻页
                    'playwright_page_methods': [
                        PageMethod('wait_for_selector', 'li.proitem', timeout=20000),
                        PageMethod('wait_for_timeout', 2000),
                    ],
                    'page_num': self.page_start,
                    'current_page': self.page_start,  # 当前页码
                },
                errback=self.errback_playwright,
            )
    
    async def parse_list(self, response):
        """解析列表页（递归翻页方式）
        
        工作原理：
        1. 解析当前页的产品列表，yield 详情请求
        2. 如果还有下一页，点击"下一页"按钮
        3. 递归调用 parse_list 处理下一页
        4. Scrapy 会自动管理所有详情请求的队列和并发
        
        这样做的好处：
        - 列表页串行处理（避免翻页冲突）
        - 详情页并发处理（Scrapy 自动管理队列）
        - 即使有100个产品，也只需要合理的并发数（如8-16）
        """
        current_page = response.meta.get('current_page', 1)
        page = response.meta.get('playwright_page')
        
        self.logger.info(f"Parsing list page {current_page}")
        
        # 提取产品列表
        products = response.css('li.proitem')
        self.logger.info(f"Found {len(products)} products on page {current_page}")
        
        for product in products:
            # 提取基础信息
            title_tag = product.css('a.tit1')
            model_tag = product.css('p.t2')
            
            if not title_tag or not model_tag:
                continue
            
            product_name = title_tag.css('::text').get()
            product_model = model_tag.css('::text').get()
            product_url = title_tag.css('::attr(href)').get()
            
            if not product_url:
                continue
            
            # 构建完整URL
            detail_url = self.build_absolute_url(response, product_url)
            
            # 准备列表数据
            list_data = {
                'product_name': product_name.strip() if product_name else '',
                'product_model': product_model.strip() if product_model else '',
                'category': self.level_1,
                'sub_category': self.level_2,
            }
            
            # 根据爬取模式决定是否输出列表 item
            if self.crawl_mode == 'list_only':
                # 只爬列表：直接输出列表 item
                list_item = self.create_item(
                    url=detail_url,
                    title=product_name.strip() if product_name else '',
                    content=list_data,
                    item_type='product_list'
                )
                yield list_item
                self.stats['list_items'] += 1
            
            elif self.crawl_mode == 'full':
                # 完整模式：不输出列表 item，等详情爬取成功后再输出
                self.logger.info(f"Yielding detail request for: {detail_url}")
                yield scrapy.Request(
                    url=detail_url,
                    callback=self.parse_detail,
                    meta={
                        'playwright': True,
                        'playwright_include_page': True,  # 需要访问 page 对象来点击 tab
                        'playwright_page_methods': [
                            PageMethod('wait_for_selector', 'div.detail_top_content_right_centent', timeout=15000),
                        ],
                        'list_data': list_data,  # 传递列表数据
                        'download_timeout': 30,  # 30秒超时
                    },
                    errback=self.errback_playwright,
                    dont_filter=True,
                )
        
        # 递归翻页逻辑
        if current_page < self.page_end and page:
            try:
                # 点击"下一页"按钮
                next_button = await page.query_selector('a.next')
                if next_button:
                    self.logger.info(f"Clicking next page button (current: {current_page}, target: {current_page + 1})")
                    await next_button.click(timeout=5000)
                    await page.wait_for_selector('li.proitem', timeout=10000)
                    await page.wait_for_timeout(1000)
                    
                    # 获取新页面内容
                    html_content = await page.content()
                    new_response = response.replace(body=html_content.encode('utf-8'))
                    
                    # 更新 meta 中的当前页码
                    new_response.meta['current_page'] = current_page + 1
                    
                    # 递归处理下一页
                    async for item in self.parse_list(new_response):
                        yield item
                else:
                    self.logger.warning(f"Next button not found on page {current_page}")
            except Exception as e:
                self.logger.error(f"Failed to navigate to next page from {current_page}: {e}")
        else:
            # 已经是最后一页，关闭列表页的页面对象
            if page and not page.is_closed():
                try:
                    await page.close()
                    self.logger.info(f"Closed list page {current_page} (final page)")
                except Exception as e:
                    self.logger.warning(f"Failed to close list page: {e}")
    
    async def parse_detail(self, response):
        """解析详情页"""
        list_data = response.meta.get('list_data', {})
        
        self.logger.info(f"Parsing detail page: {response.url}")
        
        # 点击规格参数 tab（可选，失败不影响主流程）
        page = response.meta.get('playwright_page')
        if page:
            try:
                specs_tab = await page.query_selector("#specificationTab")
                if specs_tab:
                    self.logger.info("Clicking '规格参数' tab...")
                    await specs_tab.click(timeout=2000)
                    await page.wait_for_selector(
                        "div.classify_content[sd_key='specifications'] .params",
                        timeout=3000
                    )
                    await page.wait_for_timeout(300)
                    
                    # 更新 response
                    html_content = await page.content()
                    response = response.replace(body=html_content.encode('utf-8'))
                    self.logger.info("Specs tab loaded successfully")
            except Exception as e:
                self.logger.warning(f"Specs tab not available: {str(e)[:100]}. Continuing without specs.")
        
        try:
            # 提取基础信息（使用正确的选择器）
            pname = response.css('div.detail_top_content_right_centent h1[sd_key="pname"]::text').get()
            if not pname:
                pname = response.css('div.detail_top_content_right_centent h1::text').get()
            
            modelno = response.css('div.detail_top_content_right_centent span[sd_key="modelno"]::text').get()
            
            # 组合标题
            if pname and modelno:
                title = f"{pname} {modelno}".strip()
            elif pname:
                title = pname.strip()
            else:
                title = f"{list_data.get('product_name', '')} {list_data.get('product_model', '')}".strip()
            
            # 提取价格
            price_text = response.css('div.detail_top_content_right_centent .price em::text').get()
            price = None
            if price_text:
                import re
                price_match = re.search(r'[\d,]+\.?\d*', price_text)
                if price_match:
                    price = float(price_match.group().replace(',', ''))
            
            # 提取产品描述
            description = response.css('#product-intro .content-box::text').get()
            
            # 提取规格参数（使用正确的选择器）
            specifications = []
            specs_container = response.css("div.classify_content[sd_key='specifications']")
            
            if specs_container:
                for params_section in specs_container.css('.params'):
                    category_title = params_section.css('.title_text::text').get('Specifications').strip()
                    
                    specs = {}
                    for item in params_section.css('.item_tr .item'):
                        key = item.css('.name .name_text::text').get()
                        value = item.css('.value::text').get()
                        
                        if key and value:
                            specs[key.strip()] = value.strip()
                    
                    if specs:
                        specifications.append({
                            'category': category_title,
                            'specs': specs
                        })
            
            # 提取封面图片（使用正确的选择器）
            cover_images = []
            gallery_images = response.css('ul.o_g img::attr(zoomimg)').getall()
            for img_url in gallery_images:
                if img_url:
                    cover_images.append(self.build_absolute_url(response, img_url.strip()))
            
            # 提取详情图片
            detail_images = []
            for img in response.css('#product-intro .content-box img'):
                img_url = img.css('::attr(src)').get()
                if img_url:
                    detail_images.append(self.build_absolute_url(response, img_url.strip()))
            
            # 创建详情Item（合并列表信息）
            content = {
                'product_name': pname or list_data.get('product_name'),
                'product_model': modelno or list_data.get('product_model'),
                'category': list_data.get('category'),
                'sub_category': list_data.get('sub_category'),
                'price': price,
                'description': description.strip() if description else '',
                'specifications': specifications,
                'cover_images': cover_images,
                'detail_images': detail_images,
            }
            
            detail_item = self.create_item(
                url=response.url,
                title=title,
                content=content,
                item_type='product_detail'
            )
            
            yield detail_item
            self.stats['detail_items'] += 1
            
        except Exception as e:
            self.logger.error(f"Error parsing detail page {response.url}: {e}", exc_info=True)
        finally:
            # 显式关闭页面，释放浏览器资源
            # 虽然 scrapy-playwright 会自动关闭，但显式关闭可以更快释放资源
            if page and not page.is_closed():
                try:
                    await page.close()
                    self.logger.debug(f"Closed page for {response.url}")
                except Exception as e:
                    self.logger.warning(f"Failed to close page: {e}")
    
    async def errback_playwright(self, failure):
        """Playwright 请求失败处理"""
        self.logger.error(f"Playwright request failed: {failure.request.url}")
        self.logger.error(f"Error: {failure.value}")
    
    def closed(self, reason):
        """爬虫关闭时的统计"""
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"Statistics:")
        self.logger.info(f"  - List items: {self.stats['list_items']}")
        self.logger.info(f"  - Detail items: {self.stats['detail_items']}")
        self.logger.info(f"  - Skipped URLs: {self.stats['skipped_urls']}")


# 使用示例
"""
# 1. 完整爬取（列表+详情）
scrapy crawl haier -a crawl_mode=full -a level_1=kitchen_appliances -a page_start=1 -a page_end=3

# 2. 只爬列表（快速收集URL）
scrapy crawl haier -a crawl_mode=list_only -a level_1=kitchen_appliances -a page_start=1 -a page_end=5

# 3. 只爬详情（补充已有产品）
scrapy crawl haier -a crawl_mode=detail_only -a product_urls="https://www.haier.com/kitchen_appliances/xwj/20241106_252178.shtml,https://www.haier.com/kitchen_appliances/xyyj/20241031_252062.shtml"

# 4. 通过 Scrapyd
curl http://localhost:6800/schedule.json \
  -d project=domainspider \
  -d spider=haier \
  -d crawl_mode=full \
  -d level_1=kitchen_appliances \
  -d page_start=1 \
  -d page_end=3 \
  -d task_id=haier_20231125_001
"""
