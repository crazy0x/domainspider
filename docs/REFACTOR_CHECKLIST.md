# 爬虫重构检查清单

> 完成重构后，请逐项检查并打勾 ✅

## 📝 基本信息

- **爬虫名称**：`_____________`
- **品牌/网站**：`_____________`
- **负责人**：`_____________`
- **完成日期**：`____年__月__日`

---

## ✅ 代码实现（必须完成）

### 1. 文件结构
- [ ] 创建了正确的目录结构 `src/spiders/{domain}/{brand}/`
- [ ] 包含 `__init__.py`
- [ ] 包含 `config.py`（配置文件）
- [ ] 包含 `crawler.py`（混合爬虫）或 `list.py` + `detail.py`（分离爬虫）
- [ ] 更新了 `__init__.py` 导出爬虫类

### 2. 爬虫类
- [ ] 继承了 `BaseSpider` 和 `URLHelperMixin`（根据需要）
- [ ] 设置了正确的 `name` 和 `domain`
- [ ] 实现了 `start_requests()` 方法
- [ ] 实现了 `parse_list()` 方法（如果需要）
- [ ] 实现了 `parse_detail()` 方法
- [ ] 实现了 `errback()` 错误处理

### 3. 爬虫参数
- [ ] 支持 `page_start`, `page_end` 参数（**必须**，控制爬取范围，有其他控制粒度的参数，可以讨论）
- [ ] 支持 `task_id` 参数（**必须**，用于数据库关联和 Airflow 调度）
- [ ] 支持分类参数（**可选**，如 `level_1`, `level_2`，根据业务需求）
- [ ] 支持 `crawl_mode` 参数（**可选**，混合爬虫需要：full/list_only/detail_only）

### 4. 数据提取
- [ ] 使用 `self.create_item()` 创建 Item
- [ ] 提取了**标题/名称**（必须）
- [ ] 提取了**唯一标识**（如型号、ID、编号等，如果有）
- [ ] 提取了**分类/标签**信息
- [ ] 提取了**关键业务字段**（如价格、时间、作者等，根据领域需求）
- [ ] 提取了**媒体资源**（图片、视频等），使用绝对 URL
- [ ] 提取了**结构化数据**（如规格参数、属性等，存储为 JSON）
- [ ] 所有 URL 使用 `self.build_absolute_url()` 转换为绝对路径
- [ ] 数据类型正确（数字字段为 `float/int`，列表字段为 `[]` 而非 `None`）

### 5. 技术选型
- [ ] 根据网站特点选择了合适的技术（Scrapy/Playwright/API）
- [ ] 如使用 Playwright，配置了 `DOWNLOAD_HANDLERS`
- [ ] 如使用 Playwright，正确设置了 `playwright_page_methods`
- [ ] 如使用 Playwright，在使用完后关闭了页面 (`page.close()`)

### 6. 性能配置
- [ ] 设置了合理的并发数 (`CONCURRENT_REQUESTS`)
- [ ] 设置了合理的延迟 (`DOWNLOAD_DELAY`)
- [ ] 如有翻页，使用了递归方式（避免并发冲突）

### 7. 错误处理
- [ ] 实现了 `errback` 方法
- [ ] 关键代码使用了 `try-except` 包裹
- [ ] 字段缺失时不会崩溃（使用默认值）
- [ ] 添加了适当的日志记录

### 8. 日志规范
- [ ] 在关键节点添加了日志（开始、找到产品、翻页、错误等）
- [ ] 使用了正确的日志级别（info/warning/error）
- [ ] 在 `closed()` 方法中输出统计信息

---

## ✅ 测试验证（必须通过）

### 1. 单元测试
```bash
# 测试命令
scrapy crawl {spider_name} -a crawl_mode=full -a category=test -a page_end=1
```

- [ ] 爬虫能成功启动
- [ ] 无语法错误
- [ ] 能提取到产品数据
- [ ] 日志输出正常

**测试结果**：
```
成功提取 ____ 个产品
耗时 ____ 秒
```

### 2. 多页测试
```bash
# 测试命令
scrapy crawl {spider_name} -a crawl_mode=full -a category=test -a page_end=3
```

- [ ] 能正确翻页
- [ ] 提取的产品数量正确（如：18个/页 × 3页 = 54个）
- [ ] 无重复数据

**测试结果**：
```
预期产品数：____ 个
实际提取：____ 个
匹配度：_____%
```

### 3. 数据质量检查
```bash
# 查看输出文件
cat /tmp/scrapy_output/{spider_name}_*.jsonl | jq '.'
```

- [ ] 所有必填字段都有值（不为 null）
- [ ] 价格是数字类型（`float` 或 `None`）
- [ ] URL 是完整的绝对路径（以 `http://` 或 `https://` 开头）
- [ ] 图片 URL 可访问（随机抽查 5 个）
- [ ] 规格参数结构正确（如果有）

**数据质量评分**：
```
产品名称完整率：_____%
价格完整率：_____%
图片完整率：_____%
规格参数完整率：_____%
```

### 4. 性能测试
```bash
# 测试命令
time scrapy crawl {spider_name} -a page_end=10
```

- [ ] 单页处理时间 < 30秒
- [ ] 10页总耗时 < 5分钟
- [ ] 内存使用稳定（观察 `top` 或 `htop`）

**性能数据**：
```
单页平均耗时：____ 秒
10页总耗时：____ 秒
内存峰值：____ MB
```

### 5. 稳定性测试
```bash
# 连续运行 3 次
for i in {1..3}; do
    scrapy crawl {spider_name} -a page_end=5
    sleep 10
done
```

- [ ] 3次运行结果一致（误差 < 5%）
- [ ] 无随机崩溃
- [ ] 错误率 < 5%

**稳定性评分**：
```
第1次：____ 个产品
第2次：____ 个产品
第3次：____ 个产品
平均：____ 个产品
```

---

## ✅ 集成测试（必须通过）

### 1. Scrapyd 部署
```bash
./deploy.sh
```

- [ ] 部署成功（无错误）
- [ ] 爬虫出现在 Scrapyd 列表中

```bash
# 查看爬虫列表
curl http://localhost:6800/listspiders.json?project=domainspider
```

### 2. Scrapyd 调度
```bash
curl http://localhost:6800/schedule.json \
  -d project=domainspider \
  -d spider={spider_name} \
  -d crawl_mode=full \
  -d category=test \
  -d page_end=3
```

- [ ] 调度成功（返回 job_id）
- [ ] 爬虫正常运行
- [ ] 日志正常输出

### 3. Airflow 工作流
```bash
# 修改 scripts/simulate_airflow.py 中的 SPIDER_NAME
./scripts/simulate_airflow.py
```

- [ ] 任务创建成功
- [ ] 爬虫调度成功
- [ ] 数据写入 PostgreSQL
- [ ] 任务状态更新正确（pending → running → completed）

**Airflow 测试结果**：
```
任务 ID：____________
爬取数据：____ 条
耗时：____ 秒
状态：completed ✅
```

### 4. 数据库验证
```sql
-- 检查数据量
SELECT COUNT(*) FROM crawl_data WHERE spider_name = '{spider_name}';

-- 检查数据质量
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN content->>'price' IS NOT NULL THEN 1 END) as has_price,
    COUNT(CASE WHEN content->>'product_name' IS NOT NULL THEN 1 END) as has_name
FROM crawl_data 
WHERE spider_name = '{spider_name}';
```

- [ ] 数据量与爬取数量一致
- [ ] 必填字段完整率 > 95%
- [ ] 无重复数据（检查 URL）

---

## 📋 文档清单（必须提供）

### 1. README.md
- [ ] 爬虫功能描述
- [ ] 使用方法和示例
- [ ] 参数说明
- [ ] 注意事项（如需要代理、登录等）

### 2. 测试报告
- [ ] 包含所有测试结果
- [ ] 包含数据质量评分
- [ ] 包含性能数据
- [ ] 包含截图（可选）

### 3. 代码注释
- [ ] 关键方法有注释说明
- [ ] 复杂逻辑有解释
- [ ] 选择器有说明（如 `.product-item` 是什么）

---

## 🚀 提交准备

### 1. 代码规范
- [ ] 代码符合 PEP8 规范
- [ ] 无明显的代码异味（重复代码、过长函数等）
- [ ] 变量命名清晰易懂

### 2. Git 提交
```bash
git add src/spiders/{domain}/{brand}/
git commit -m "feat(spider): 重构 {品牌名称} 爬虫"
```

- [ ] 提交信息清晰
- [ ] 只包含相关文件
- [ ] 无敏感信息（API Key、密码等）

### 3. 提交信息模板
```
feat(spider): 重构 {品牌名称} 爬虫

- 实现混合模式爬虫
- 支持列表和详情爬取
- 添加 {技术栈} 支持
- 优化性能和错误处理
- 测试通过：{数量}/{总数} 产品成功爬取

测试结果：
- 单页耗时：{时间}秒
- 数据完整率：{百分比}%
- 稳定性：3次运行一致
```

---

## ✍️ 签名确认

我确认已完成上述所有检查项，爬虫符合项目标准，可以提交审核。

**负责人签名**：________________  
**日期**：____年__月__日

---

## 📊 评分标准

| 项目 | 权重 | 得分 | 说明 |
|-----|------|------|------|
| 代码实现 | 40% | __/40 | 代码结构、规范、完整性 |
| 测试验证 | 30% | __/30 | 功能、性能、稳定性 |
| 数据质量 | 20% | __/20 | 完整性、准确性 |
| 文档规范 | 10% | __/10 | README、注释、测试报告 |
| **总分** | **100%** | **__/100** | **≥ 90分通过** |

---

## 🔗 相关文档

- [爬虫重构指南](./REFACTOR_GUIDE.md) - 详细的重构指南和模板
- [项目目录结构](../DIRECTORY_STRUCTURE.md) - 项目文件组织
- [海尔爬虫示例](../src/spiders/appliance/haier/crawler.py) - 参考实现

**如有疑问，请参考重构指南或联系项目负责人。**
