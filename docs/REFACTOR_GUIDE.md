# 爬虫重构指南

## 📋 目录

1. [重构目标](#重构目标)
2. [重构标准](#重构标准)
3. [实现模板](#实现模板)
4. [测试标准](#测试标准)
5. [提交清单](#提交清单)
6. [常见问题](#常见问题)

---

## 🎯 重构目标

将旧的爬虫代码重构为符合项目规范的新版本，确保：
- ✅ 代码结构清晰，易于维护
- ✅ 符合项目架构标准
- ✅ 数据提取准确完整
- ✅ 性能和稳定性达标
- ✅ 可以集成到 Airflow 工作流

---

## 📏 重构标准

### 1. 必须完成的任务

#### 1.1 代码结构 ⭐⭐⭐

- [ ] **继承基类**：必须继承 `BaseSpider` 和相关 Mixin
  ```python
  from src.spiders.base import BaseSpider, URLHelperMixin
  
  class YourSpider(BaseSpider, URLHelperMixin):
      name = 'your_spider'
      domain = 'your_domain'  # 如：appliance, ecommerce
  ```

- [ ] **文件组织**：按照项目目录结构组织
  ```
  src/spiders/{domain}/{site}/
  ├── __init__.py
  ├── config.py          # 配置文件（URL、分类映射等）
  ├── crawler.py         # 混合爬虫（推荐）或
  ├── list.py           # 列表爬虫
  └── detail.py         # 详情爬虫
  ```

- [ ] **配置分离**：将 URL、分类等配置放在 `config.py`
  ```python
  # config.py
  BASE_URL = "https://example.com"
  CATEGORIES = {
      'category1': 'Category 1',
      'category2': 'Category 2',
  }
  ```

#### 1.2 数据提取 ⭐⭐⭐

- [ ] **使用统一的 Item 结构**
  ```python
  item = self.create_item(
      url=response.url,
      title="产品标题",
      content={
          'product_name': '产品名称',
          'product_model': '型号',
          'price': 1999.0,
          'specifications': [...],
          'images': [...],
      },
      item_type='product_detail'  # 或 'product_list'
  )
  ```

- [ ] **提取核心字段**（根据领域业务需求定义）：
  - **标题/名称**：主要内容的标题（如产品名、文章标题、帖子标题）
  - **唯一标识**：型号、ID、编号等（如果有）
  - **分类/标签**：内容分类、标签、类目等
  - **关键数据**：价格、时间、作者、浏览量等业务关键字段
  - **媒体资源**：图片、视频等（使用绝对 URL）
  - **结构化数据**：规格参数、属性列表、元数据等（存储为 JSON）
  
  **不同领域示例**：
  - 电商/电器：`product_name`, `product_model`, `price`, `specifications`, `images`
  - 论坛/社区：`title`, `author`, `post_time`, `content`, `reply_count`, `attachments`
  - 新闻/资讯：`title`, `author`, `publish_time`, `content`, `tags`, `cover_image`
  - 汽车：`brand`, `series`, `model`, `year`, `price`, `specs`, `dealer_info`

- [ ] **数据验证**：确保提取的数据格式正确
  - 数字类型字段（价格、数量等）必须是 `float/int` 或 `None`
  - URL 必须是完整的绝对路径
  - 列表字段不能为 `None`（使用空列表 `[]`）
  - 时间字段使用标准格式（ISO 8601 或 Unix 时间戳）

#### 1.3 爬虫参数 ⭐⭐⭐

**所有爬虫参数必须在 `__init__` 方法中声明**：

```python
def __init__(self, page_start=1, page_end=10, task_id=None, 
             level_1=None, crawl_mode='full', *args, **kwargs):
    super().__init__(*args, **kwargs)
    
    # 必须参数
    self.page_start = int(page_start)
    self.page_end = int(page_end)
    self.task_id = task_id
    
    # 可选参数（根据业务需求）
    self.level_1 = level_1
    self.crawl_mode = crawl_mode
```

**参数说明**：
- ✅ **必须**：`page_start`, `page_end`, `task_id`
- ⚠️ **可选**：分类参数（`level_1`, `level_2`）、`crawl_mode`（混合爬虫需要）
- 📌 命令行参数会自动传递给 `__init__`：`scrapy crawl spider -a param=value`

#### 1.4 爬虫模式 ⭐⭐

支持三种爬取模式（至少实现一种，推荐混合模式）：

- [ ] **混合模式** (`crawl_mode='full'`)：一个爬虫同时爬列表和详情
  ```python
  if self.crawl_mode == 'full':
      # 爬列表 + 详情
  ```

- [ ] **分离模式**：
  - `list.py`：只爬列表，输出产品 URL
  - `detail.py`：只爬详情，接收 URL 列表

#### 1.5 爬虫配置 ⭐⭐

**使用 `custom_settings` 配置爬虫行为**（直接在爬虫类中定义）：

```python
class YourSpider(BaseSpider):
    custom_settings = {
        # 并发和延迟
        'CONCURRENT_REQUESTS': 16,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
        'DOWNLOAD_DELAY': 1,
        
        # Playwright 配置（如果需要）
        'DOWNLOAD_HANDLERS': {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_LAUNCH_OPTIONS': {
            'headless': True,
        },
    }
```

**注意**：
- ❌ 不要在 `config.py` 中定义 `SPIDER_CONFIG`（不会被使用）
- ✅ 直接在 `custom_settings` 中配置（Scrapy 标准做法）

#### 1.6 技术选型 ⭐⭐

根据网站特点选择合适的技术：

| 网站类型 | 推荐技术 | 说明 |
|---------|---------|------|
| 静态页面 | Scrapy 原生 | 性能最好 |
| 动态渲染 | Playwright | 需要 JS 渲染 |
| API 接口 | Scrapy + requests | 直接调用 API |
| 混合类型 | Playwright + Scrapy | 灵活处理 |

#### 1.7 错误处理 ⭐⭐

- [ ] **实现错误回调**
  ```python
  def errback_playwright(self, failure):
      self.logger.error(f"Request failed: {failure.request.url}")
      self.logger.error(f"Error: {failure.value}")
  ```

- [ ] **优雅降级**：关键字段缺失时不应崩溃
  ```python
  try:
      price = float(price_text)
  except (ValueError, TypeError):
      price = None
      self.logger.warning(f"Failed to parse price: {price_text}")
  ```

#### 1.8 性能优化 ⭐

- [ ] **合理的并发设置**（在 `custom_settings` 中配置）
  ```python
  'CONCURRENT_REQUESTS': 16,           # 总并发
  'CONCURRENT_REQUESTS_PER_DOMAIN': 8, # 每域名并发
  'DOWNLOAD_DELAY': 1,                 # 下载延迟
  ```

- [ ] **资源管理**：Playwright 页面使用完后关闭
  ```python
  finally:
      if page and not page.is_closed():
          await page.close()
  ```

#### 1.9 日志规范 ⭐

- [ ] **关键节点记录日志**
  ```python
  self.logger.info(f"Starting crawl: {url}")
  self.logger.info(f"Found {len(products)} products")
  self.logger.error(f"Failed to parse: {url}")
  ```

- [ ] **统计信息**
  ```python
  def closed(self, reason):
      self.logger.info(f"Spider closed: {reason}")
      self.logger.info(f"Total items: {self.stats['items']}")
  ```

### 2. 推荐完成的任务

- [ ] **增量爬取支持**：参数天然支持（例如根据时间范围筛选），或记录已爬取的 URL（TODO），避免重复
- [ ] **翻页逻辑**：支持多页爬取
- [ ] **去重机制**：使用 Scrapy 的去重或自定义去重
- [ ] **重试机制**：失败请求自动重试

### 3. 可选任务

- [ ] **代理支持**：需要时使用代理池（TODO：中间件配置）
- [ ] **验证码处理**：如果网站有验证码
- [ ] **登录功能**：需要登录的网站

---

## 📝 实现模板

### 模板 1：混合爬虫（推荐）

```python
"""
品牌名称爬虫 - 混合模式
支持列表和详情一体化爬取
"""
from scrapy_playwright.page import PageMethod
import scrapy

from src.spiders.base import BaseSpider, URLHelperMixin
from .config import BASE_URL, CATEGORIES


class BrandCrawler(BaseSpider, URLHelperMixin):
    """品牌混合爬虫"""
    
    name = 'brand_crawler'
    domain = 'your_domain'  # appliance, ecommerce 等
    allowed_domains = ['example.com']
    
    custom_settings = {
        'DOWNLOAD_DELAY': 1,
        'CONCURRENT_REQUESTS': 16,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
        
        # Playwright 配置（如果需要）
        'DOWNLOAD_HANDLERS': {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
    }
    
    def __init__(self, crawl_mode='full', category=None, 
                 page_start=1, page_end=10, task_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.crawl_mode = crawl_mode  # full, list_only, detail_only
        self.category = category
        self.page_start = int(page_start)
        self.page_end = int(page_end)
        self.task_id = task_id
        
        # 统计
        self.stats = {
            'list_items': 0,
            'detail_items': 0,
        }
    
    def start_requests(self):
        """生成初始请求"""
        if self.crawl_mode in ('full', 'list_only'):
            # 构建列表页 URL
            url = f"{BASE_URL}/{self.category}/"
            
            yield scrapy.Request(
                url=url,
                callback=self.parse_list,
                meta={
                    'playwright': True,  # 如果需要 Playwright
                    'playwright_include_page': True,
                    'playwright_page_methods': [
                        PageMethod('wait_for_selector', '.product-item', timeout=20000),
                    ],
                    'current_page': self.page_start,
                },
                errback=self.errback,
            )
    
    async def parse_list(self, response):
        """解析列表页"""
        current_page = response.meta.get('current_page', 1)
        self.logger.info(f"Parsing list page {current_page}")
        
        # 提取产品列表
        products = response.css('.product-item')
        self.logger.info(f"Found {len(products)} products")
        
        for product in products:
            # 提取基础信息
            title = product.css('.title::text').get()
            url = product.css('a::attr(href)').get()
            
            if not url:
                continue
            
            detail_url = self.build_absolute_url(response, url)
            
            # 准备列表数据
            list_data = {
                'product_name': title.strip() if title else '',
                'category': self.category,
            }
            
            if self.crawl_mode == 'list_only':
                # 只输出列表
                yield self.create_item(
                    url=detail_url,
                    title=title,
                    content=list_data,
                    item_type='product_list'
                )
            elif self.crawl_mode == 'full':
                # 请求详情页
                yield scrapy.Request(
                    url=detail_url,
                    callback=self.parse_detail,
                    meta={
                        'playwright': True,
                        'playwright_include_page': True,
                        'list_data': list_data,
                    },
                    errback=self.errback,
                )
        
        # 翻页逻辑（如果需要）
        if current_page < self.page_end:
            page = response.meta.get('playwright_page')
            if page:
                try:
                    next_button = await page.query_selector('.next-page')
                    if next_button:
                        await next_button.click()
                        await page.wait_for_selector('.product-item')
                        
                        html_content = await page.content()
                        new_response = response.replace(body=html_content.encode('utf-8'))
                        new_response.meta['current_page'] = current_page + 1
                        
                        async for item in self.parse_list(new_response):
                            yield item
                except Exception as e:
                    self.logger.error(f"Pagination failed: {e}")
    
    async def parse_detail(self, response):
        """解析详情页"""
        list_data = response.meta.get('list_data', {})
        page = response.meta.get('playwright_page')
        
        self.logger.info(f"Parsing detail: {response.url}")
        
        try:
            # 提取详情信息
            title = response.css('h1.title::text').get()
            price_text = response.css('.price::text').get()
            
            # 解析价格
            price = None
            if price_text:
                import re
                match = re.search(r'[\d,]+\.?\d*', price_text)
                if match:
                    price = float(match.group().replace(',', ''))
            
            # 提取规格参数
            specifications = []
            for spec in response.css('.spec-item'):
                key = spec.css('.key::text').get()
                value = spec.css('.value::text').get()
                if key and value:
                    specifications.append({
                        'key': key.strip(),
                        'value': value.strip()
                    })
            
            # 提取图片
            images = []
            for img in response.css('.gallery img::attr(src)').getall():
                images.append(self.build_absolute_url(response, img))
            
            # 构建 Item
            content = {
                **list_data,
                'product_name': title.strip() if title else list_data.get('product_name'),
                'price': price,
                'specifications': specifications,
                'images': images,
            }
            
            yield self.create_item(
                url=response.url,
                title=title or list_data.get('product_name'),
                content=content,
                item_type='product_detail'
            )
            
            self.stats['detail_items'] += 1
            
        except Exception as e:
            self.logger.error(f"Error parsing detail: {e}", exc_info=True)
        finally:
            # 关闭页面
            if page and not page.is_closed():
                await page.close()
    
    def errback(self, failure):
        """错误处理"""
        self.logger.error(f"Request failed: {failure.request.url}")
        self.logger.error(f"Error: {failure.value}")
    
    def closed(self, reason):
        """爬虫关闭"""
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"List items: {self.stats['list_items']}")
        self.logger.info(f"Detail items: {self.stats['detail_items']}")
```

### 模板 2：配置文件

```python
# config.py
"""
品牌爬虫配置
"""

# 基础 URL
BASE_URL = "https://www.example.com"

# 分类映射
CATEGORIES = {
    'category1': '分类1',
    'category2': '分类2',
}

# 其他配置
DEFAULT_TIMEOUT = 30
MAX_RETRY = 3
```

---

## ✅ 测试标准

### 1. 功能测试

#### 1.1 基础功能测试

```bash
# 测试列表爬取
scrapy crawl your_spider -a crawl_mode=list_only -a category=test -a page_end=1

# 测试详情爬取
scrapy crawl your_spider -a crawl_mode=full -a category=test -a page_end=1

# 测试多页爬取
scrapy crawl your_spider -a crawl_mode=full -a category=test -a page_end=3
```

**验收标准**：
- [ ] 能成功启动爬虫
- [ ] 日志中显示正确的页面数量
- [ ] 提取的产品数量正确（如：18个/页 × 3页 = 54个）

#### 1.2 数据质量测试

检查输出文件（`/tmp/scrapy_output/spider_name_*.jsonl`）：

```bash
# 查看输出文件
cat /tmp/scrapy_output/your_spider_*.jsonl | jq '.'

# 统计数量
wc -l /tmp/scrapy_output/your_spider_*.jsonl
```

**验收标准**：
- [ ] 所有必填字段都有值（不为 null）
- [ ] 价格格式正确（数字类型）
- [ ] URL 是完整的绝对路径
- [ ] 图片 URL 可访问
- [ ] 规格参数结构正确

#### 1.3 性能测试

```bash
# 记录开始时间
time scrapy crawl your_spider -a page_end=10
```

**验收标准**：
- [ ] 单页处理时间 < 30秒
- [ ] 10页总耗时 < 5分钟
- [ ] 内存使用稳定（不持续增长）
- [ ] 无内存泄漏

#### 1.4 稳定性测试

```bash
# 连续运行3次
for i in {1..3}; do
    scrapy crawl your_spider -a page_end=5
    sleep 10
done
```

**验收标准**：
- [ ] 3次运行结果一致
- [ ] 无随机崩溃
- [ ] 错误率 < 5%

### 2. 集成测试

#### 2.1 Scrapyd 部署测试

```bash
# 部署到 Scrapyd
./deploy.sh

# 通过 Scrapyd 运行
curl http://localhost:6800/schedule.json \
  -d project=domainspider \
  -d spider=your_spider \
  -d crawl_mode=full \
  -d category=test
```

**验收标准**：
- [ ] 部署成功
- [ ] 能通过 Scrapyd 启动
- [ ] 日志正常输出

#### 2.2 Airflow 工作流测试

```bash
# 运行 Airflow 模拟脚本
./scripts/simulate_airflow.py
```

**验收标准**：
- [ ] 任务创建成功
- [ ] 爬虫调度成功
- [ ] 数据写入 PostgreSQL
- [ ] 任务状态更新正确

### 3. 数据验证

#### 3.1 数据库检查

```sql
-- 检查数据量
SELECT COUNT(*) FROM crawl_data WHERE spider_name = 'your_spider';

-- 检查数据质量
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN content->>'price' IS NOT NULL THEN 1 END) as has_price,
    COUNT(CASE WHEN content->>'product_name' IS NOT NULL THEN 1 END) as has_name
FROM crawl_data 
WHERE spider_name = 'your_spider';
```

**验收标准**：
- [ ] 数据量与爬取数量一致
- [ ] 必填字段完整率 > 95%
- [ ] 无重复数据

---

## 📋 提交清单

重构完成后，请确认以下清单：

### 代码清单

- [ ] 爬虫代码（`crawler.py` 或 `list.py` + `detail.py`）
- [ ] 配置文件（`config.py`）
- [ ] `__init__.py` 更新（导出爬虫类）
- [ ] 代码符合 PEP8 规范

### 文档清单

- [ ] README.md（爬虫说明）
  - 爬虫功能描述
  - 使用方法
  - 参数说明
  - 注意事项
- [ ] 测试报告（包含测试结果截图）

### 测试清单

- [ ] 功能测试通过
- [ ] 数据质量测试通过
- [ ] 性能测试通过
- [ ] 集成测试通过

### 提交信息

```
feat(spider): 重构 {品牌名称} 爬虫

- 实现混合模式爬虫
- 支持列表和详情爬取
- 添加 Playwright 支持
- 优化性能和错误处理
- 测试通过：54/54 产品成功爬取
```

---

## ❓ 常见问题

### Q1: 我应该用 Playwright 还是原生 Scrapy？

**判断标准**：
1. 打开浏览器开发者工具（F12）
2. 查看网络请求（Network）
3. 刷新页面，看产品数据是从哪里来的

- **如果数据在 HTML 中**：用原生 Scrapy（性能更好）
- **如果数据是 JS 渲染的**：用 Playwright
- **如果有 API 接口**：直接调用 API（最优）

### Q2: 翻页逻辑应该怎么实现？

**推荐方案**：递归翻页（列表页串行，详情页并发）

```python
# 在 parse_list 中
if current_page < page_end:
    # 点击下一页
    await next_button.click()
    # 递归处理
    async for item in self.parse_list(new_response):
        yield item
```

**原因**：避免并发翻页冲突

### Q3: 如何处理动态加载的内容？

```python
# 等待元素加载
await page.wait_for_selector('.product-item', timeout=20000)

# 滚动加载更多
await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
await page.wait_for_timeout(2000)

# 点击"加载更多"按钮
load_more = await page.query_selector('.load-more')
if load_more:
    await load_more.click()
```

### Q4: 如何提高爬取速度？

1. **合理设置并发**：
   ```python
   'CONCURRENT_REQUESTS': 16,
   'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
   ```

2. **降低延迟**（如果网站允许）：
   ```python
   'DOWNLOAD_DELAY': 0.5,
   ```

3. **及时关闭页面**：
   ```python
   finally:
       if page:
           await page.close()
   ```

### Q5: 如何调试爬虫？

```bash
# 1. 使用 Scrapy Shell
scrapy shell "https://example.com"

# 2. 查看日志
tail -f logs/domainspider/your_spider/*.log

# 3. 使用 Playwright 非无头模式
'PLAYWRIGHT_LAUNCH_OPTIONS': {
    'headless': False,  # 可以看到浏览器
}

# 4. 添加断点
import pdb; pdb.set_trace()
```

---

## 📚 参考资料

- [Scrapy 官方文档](https://docs.scrapy.org/)
- [Scrapy-Playwright 文档](https://github.com/scrapy-plugins/scrapy-playwright)
- [项目 BaseSpider 文档](../src/spiders/base.py)
- [海尔爬虫示例](../src/spiders/appliance/haier/crawler.py)

---

## 🆘 获取帮助

如有问题，请：
1. 查看本文档的常见问题部分
2. 参考海尔爬虫的实现
3. 联系项目负责人

**祝重构顺利！🚀**
