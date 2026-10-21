[English Version](#google-maps-review-scraper)

# Google Maps 评论爬虫

一个强大的Google Maps商户信息和用户评论数据爬取工具，专为大规模数据采集设计。

## 🌟 主要特性

- **大规模批量处理**：支持数万个地点的批量数据爬取
- **智能断点恢复**：意外中断后可自动继续处理
- **多线程并发**：支持多线程并发处理，提高效率
- **错误重试机制**：智能重试失败的地点，提高成功率
- **详细进度跟踪**：实时显示处理进度和统计信息
- **灵活输出格式**：支持JSON和CSV格式输出
- **数据提取与完整性标记**：包括商户基本信息、评论内容、评分等

## 📚 文档导航

- 📖 **[技术文档](TECHNICAL.md)** - 详细的代码功能说明和实现细节
- 📋 **[错误代码](error_codes.md)** - 完整的错误代码定义和解决方案

## 📁 项目结构

```
googlemaps-scraper-reviews/
├── main.py                    # 单点爬虫核心脚本
├── batch_scraper.py          # 批量处理脚本
├── process_urls.py           # URL预处理工具，强制英文界面
├── check_progress.py         # 进度检查工具
├── retry_failed_scrapes.py   # 失败重试工具
├── find_duplicates_simple.py # 去重工具
├── input_statistics.py       # 输入数据统计
├── error_codes.md           # 错误代码说明
├── input/                   # 输入数据目录
├── batch_output/           # 批量输出数据目录
│   ├── culture/           # 文化场所数据
│   ├── education/         # 教育场所数据
│   ├── entertainment_and_recreation/ # 娱乐休闲数据
│   ├── facilities/        # 设施数据
│   ├── food_and_drink/    # 餐饮数据
│   ├── natural_features/  # 自然景观数据
│   ├── places_of_worship/ # 宗教场所数据
│   ├── shopping/          # 购物场所数据
│   ├── sports/            # 体育场所数据
│   ├── transportation/    # 交通相关数据
│   ├── progress.json      # 处理进度记录
│   ├── errors.jsonl       # 错误日志
│   └── success.jsonl      # 成功日志
└── backup/                # 备份数据目录
```

## 🚀 快速开始

### 环境要求

- Python 3.9+
- Chrome浏览器
- ChromeDriver（会自动管理）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 准备输入数据

在 `input/` 目录下放置 JSONL 文件，每行包含一个地点对象。必需字段为 `place_id`、`parent_type`、`sub_type` 和 `Maps_url`（兼容别名 `url`）：

```json
{
    "place_id": "ChIJ...",
    "place_name": "商户名称",
    "parent_type": "food_and_drink",
    "sub_type": "restaurant",
    "Maps_url": "https://maps.google.com/..."
}
```

### URL预处理：强制英文界面

爬虫仍依赖英文页面选择器。单点入口和批量输入读取器会自动设置 `hl=en`，替换已有语言参数并保留其他参数及 fragment，因此预处理现在是可选步骤。

需要另存英文链接文件时，可以运行：

```bash
python process_urls.py input/places.jsonl input/places_en.jsonl
```

脚本同时支持 `Maps_url` 和 `url`。请优先使用完整地点链接；短链接重定向后的语言仍需现场验证。

### 单点爬取

爬取单个地点的数据：

```bash
python main.py "https://maps.google.com/..."
```

支持的参数：
- `--output-dir`：输出目录（默认：output）
- `--url`：也可通过该参数传入单个 URL
- `--headless`：无界面模式；单点命令默认显示浏览器
- `--no-headless`：显式显示浏览器界面
- `--json-output`：标准输出为 JSON 数组，日志写入标准错误；仍会保存 CSV
- `--max-retries`：最多尝试次数，含第一次（默认：3）
- `--max-scrolls`：滚动次数上限（默认：30），也支持批量入口
- `--scroll-wait`：每次滚动等待新评论的秒数（默认：3），也支持批量入口

### 批量爬取

处理大量地点数据：

```bash
# 基础批量处理
python batch_scraper.py input/places.jsonl

# 指定并发数和处理数量
python batch_scraper.py input/places.jsonl --max-workers 5 --max-places 100

# 启用断点恢复
python batch_scraper.py input/places.jsonl --resume

# 重试失败的地点
python batch_scraper.py input/places.jsonl --retry-failed

# 无人值守模式（长期运行）
python batch_scraper.py input/places.jsonl --unattended

# 无限运行模式
python batch_scraper.py input/places.jsonl --infinite
```

## 📊 监控和管理

### 检查处理进度

```bash
python check_progress.py
```

输出示例：
```
=== Progress.json 统计 ===
successful count: 1250
failed count: 45
skipped count: 0
total processed: 1295
```

### 重试失败的爬取

```bash
python retry_failed_scrapes.py
```

### 查看输入数据统计

```bash
python input_statistics.py input/places.jsonl
```

## ⚙️ 配置选项

### 预设配置模式

- **默认模式**：平衡的性能和稳定性
- **测试模式**：用于快速测试（`--test`）
- **生产模式**：高性能大规模处理（`--production`）
- **无人值守模式**：长期自动运行（`--unattended`）
- **无限模式**：持续运行直到所有数据处理完成（`--infinite`）
- **快速模式**：高速处理，较少重试（`--fast`）

### 主要参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--max-workers` | 最大并发线程数 | 3 |
| `--max-retries` | 单个地点最大重试次数 | 3 |
| `--timeout` | 单个地点超时时间（秒） | 300 |
| `--max-places` | 单次最大处理地点数 | 无限制 |
| `--resume` | 启用断点恢复 | True |
| `--retry-failed` | 重试失败的地点 | False |

## 📄 输出格式

### JSON格式

批量入口为每个地点保存独立 JSON，以下为字段示例。单点入口仅在 `--json-output` 时将结果数组写到标准输出，状态字段为 `success` / `error_code` / `error_message`，不自动保存 JSON 文件。

```json
{
  "place_id": "ChIJ...",
  "Maps_url": "https://maps.google.com/?cid=123&hl=en",
  "parent_type": "food_and_drink",
  "sub_type": "restaurant",
  "scrape_success": true,
  "scrape_error_code": 0,
  "scrape_error_message": "",
  "business_info": {
    "url": "https://maps.google.com/?cid=123&hl=en",
    "name": "商户名称",
    "rating": "4.5 stars",
    "category": "Restaurant",
    "lat": "40.7128",
    "lon": "-74.0060"
  },
  "reviews_count": 1,
  "expected_review_count": 1,
  "reviews_complete": true,
  "review_stop_reason": "expected_count_reached",
  "reviews": [
    {
      "review_id": "review-id",
      "user": "用户名",
      "user_info": "",
      "rating": "5 stars",
      "time": "a month ago",
      "content": "评论内容"
    }
  ],
  "scraped_at": "2026-10-22 10:30:00",
  "retry_attempt": 0,
  "has_reviews": true,
  "review_status": "有评论",
  "final_success": true
}
```

### CSV格式

单点入口保存 CSV，`rating` 是评论评分，`business_rating` 是商户总评分；两者均保留页面文本。批量入口保存 JSON 后会清理中间 CSV，不保留每商户 CSV。

### 数据范围与完整性

- 当前不提取地址、电话、网站、营业时间或点赞数；时间保留页面相对时间文本，不转换为绝对日期。坐标是从 URL 提取的字符串，缺失时为空。
- 每次滚动都采集当前评论，并优先用 `review_id` 去重；纯星级评价的 `content` 为空字符串。
- `reviews_complete=true` 只表示评论数量达到页面显示的总数，或页面明确显示零评论。它不保证隐藏或折叠的文字已完整展开，也不代表 Google 后端全部评论。
- 未找到评论按钮是错误 `1004`；缺失总数不等于零。达到滚动上限、加载停滞或无法验证数量时返回 `1011`，保存部分数据，批量结果进入失败列表。
- `1011` 不会在单点入口立即重复相同采集。可以增加 `--max-scrolls` / `--scroll-wait` 后使用批量 `--retry-failed`；同时保证 `--timeout` 足够长。
- 重试扫描器能识别旧文件中带错误码的“成功”记录；旧版未标注完整性的历史数据不能据此推定完整。

### 离线测试

```bash
python -m unittest discover -s tests -v
```

测试使用模拟浏览器页面，不代表已验证 Google Maps 当前页面兼容性。

## 🛠️ 故障排除

### 常见问题

1. **Chrome浏览器启动失败**
   - 确保已安装Chrome浏览器
   - 检查ChromeDriver版本兼容性

2. **网络超时**
   - 增加 `--timeout` 参数值
   - 检查网络连接稳定性

3. **验证码或反爬虫检测**
   - 降低并发数（`--max-workers 1`）
   - 增加随机延迟
   - 使用代理IP

4. **内存不足**
   - 降低 `--max-workers` 值
   - 使用 `--max-places` 分批处理

### 错误代码

详细的错误代码说明请查看 [error_codes.md](error_codes.md)

## 📈 性能优化

### 推荐配置

- **小规模测试**（<100个地点）：`--max-workers 1 --max-places 10`
- **中等规模**（100-1000个地点）：`--max-workers 3 --max-places 100`
- **大规模处理**（>1000个地点）：`--max-workers 5 --max-places 500`

### 注意事项

- 过高的并发可能触发反爬虫机制
- 建议在非高峰时段运行大规模爬取
- 定期检查和清理输出目录

## 🔧 开发说明

### 扩展功能

项目采用模块化设计，可以轻松扩展：

- 添加新的数据提取字段
- 自定义输出格式
- 集成不同的存储后端
- 添加数据清洗和验证

### 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 创建 Pull Request

## 📞 支持

如有问题或建议，请：

1. 查看错误代码文档
2. 检查日志文件
3. 提交Issue描述问题

## ⚖️ 免责声明

本工具仅用于学习和研究目的。使用者需要：

- 遵守Google Maps的服务条款
- 遵守相关法律法规
- 合理控制爬取频率
- 尊重网站的robots.txt

请负责任地使用此工具，避免对目标网站造成过大负担。

---

[中文版](#google-maps-评论爬虫)

# Google Maps Review Scraper

A powerful tool for scraping business information and user reviews from Google Maps, designed for large-scale data collection.

## 🌟 Key Features

- **Large-Scale Batch Processing**: Supports batch scraping of tens of thousands of places.
- **Intelligent Resume**: Automatically resumes processing after an unexpected interruption.
- **Multi-threaded Concurrency**: Supports multi-threaded processing to improve efficiency.
- **Error Retry Mechanism**: Intelligently retries failed places to increase success rate.
- **Detailed Progress Tracking**: Real-time display of processing progress and statistics.
- **Flexible Output Formats**: Supports JSON and CSV output formats.
- **Data Extraction and Completeness Tracking**: Includes basic business information, review content, ratings, etc.

## 📚 Documentation

- 📖 **[Technical Documentation](TECHNICAL.md)** - Detailed code function descriptions and implementation details.
- 📋 **[Error Codes](error_codes.md)** - Complete error code definitions and solutions.

## 📁 Project Structure

```
googlemaps-scraper-reviews/
├── main.py                    # Core script for single-place scraping
├── batch_scraper.py          # Batch processing script
├── process_urls.py           # URL pre-processing tool to force English interface
├── check_progress.py         # Progress checking tool
├── retry_failed_scrapes.py   # Failed scrapes retry tool
├── find_duplicates_simple.py # Duplicate removal tool
├── input_statistics.py       # Input data statistics tool
├── error_codes.md           # Error code descriptions
├── input/                   # Input data directory
├── batch_output/           # Batch output data directory
│   ├── culture/           # Data for cultural places
│   ├── education/         # Data for educational places
│   ├── entertainment_and_recreation/ # Data for entertainment and recreation
│   ├── facilities/        # Data for facilities
│   ├── food_and_drink/    # Data for food and drink
│   ├── natural_features/  # Data for natural features
│   ├── places_of_worship/ # Data for places of worship
│   ├── shopping/          # Data for shopping
│   ├── sports/            # Data for sports
│   ├── transportation/    # Data for transportation
│   ├── progress.json      # Processing progress log
│   ├── errors.jsonl       # Error log
│   └── success.jsonl      # Success log
└── backup/                # Backup data directory
```

## 🚀 Quick Start

### Requirements

- Python 3.9+
- Google Chrome Browser
- ChromeDriver (managed automatically)

### Installation

```bash
pip install -r requirements.txt
```

### Prepare Input Data

Place JSONL files in `input/`, with one place object per line. Required fields are `place_id`, `parent_type`, `sub_type`, and `Maps_url` (the alias `url` is also accepted):

```json
{
    "place_id": "ChIJ...",
    "place_name": "Business Name",
    "parent_type": "food_and_drink",
    "sub_type": "restaurant",
    "Maps_url": "https://maps.google.com/..."
}
```

### URL Pre-processing: Force English Interface

The scraper still uses English page selectors. Both single-place scraping and the batch loader set `hl=en` automatically, replacing existing language parameters while preserving other query parameters and fragments. Pre-processing is optional.

To save a separate normalized input file:

```bash
python process_urls.py input/places.jsonl input/places_en.jsonl
```

Both `Maps_url` and `url` are supported. Prefer full place URLs; language behavior after a short-link redirect still needs live verification.

### Single Place Scraping

Scrape data for a single place:

```bash
python main.py "https://maps.google.com/..."
```

Supported arguments:
- `--output-dir`: Output directory (default: output)
- `--url`: Alternative to the positional single URL
- `--headless`: Run without browser UI; the single-place CLI shows the browser by default
- `--no-headless`: Explicitly show browser UI
- `--json-output`: Write a JSON array to stdout and logs to stderr; CSV is still saved
- `--max-retries`: Maximum attempts including the first (default: 3)
- `--max-scrolls`: Scroll limit (default: 30); also available in the batch CLI
- `--scroll-wait`: Seconds to wait for new reviews per scroll (default: 3); also available in the batch CLI

### Batch Scraping

Process a large number of places:

```bash
# Basic batch processing
python batch_scraper.py input/places.jsonl

# Specify number of workers and places
python batch_scraper.py input/places.jsonl --max-workers 5 --max-places 100

# Enable resume functionality
python batch_scraper.py input/places.jsonl --resume

# Retry failed places
python batch_scraper.py input/places.jsonl --retry-failed

# Unattended mode (for long-running tasks)
python batch_scraper.py input/places.jsonl --unattended

# Infinite mode
python batch_scraper.py input/places.jsonl --infinite
```

## 📊 Monitoring and Management

### Check Progress

```bash
python check_progress.py
```

Example output:
```
=== Progress.json Statistics ===
successful count: 1250
failed count: 45
skipped count: 0
total processed: 1295
```

### Retry Failed Scrapes

```bash
python retry_failed_scrapes.py
```

### View Input Data Statistics

```bash
python input_statistics.py input/places.jsonl
```

## ⚙️ Configuration Options

### Preset Configuration Modes

- **Default Mode**: Balanced performance and stability.
- **Test Mode**: For quick testing (`--test`).
- **Production Mode**: High-performance for large-scale processing (`--production`).
- **Unattended Mode**: For long-term automatic operation (`--unattended`).
- **Infinite Mode**: Runs continuously until all data is processed (`--infinite`).
- **Fast Mode**: High-speed processing with fewer retries (`--fast`).

### Main Parameters

| Parameter | Description | Default |
|---|---|---|
| `--max-workers` | Maximum number of concurrent workers | 3 |
| `--max-retries` | Max retries for a single place | 3 |
| `--timeout` | Timeout for a single place (seconds) | 300 |
| `--max-places` | Maximum number of places to process | unlimited |
| `--resume` | Enable resume functionality | True |
| `--retry-failed` | Retry failed places | False |

## 📄 Output Format

### JSON Format

The batch CLI saves one JSON file per place; an example follows. The single-place CLI writes a result array to stdout with `--json-output`, using `success` / `error_code` / `error_message`; it does not automatically save JSON files.

```json
{
  "place_id": "ChIJ...",
  "Maps_url": "https://maps.google.com/?cid=123&hl=en",
  "parent_type": "food_and_drink",
  "sub_type": "restaurant",
  "scrape_success": true,
  "scrape_error_code": 0,
  "scrape_error_message": "",
  "business_info": {
    "url": "https://maps.google.com/?cid=123&hl=en",
    "name": "Business Name",
    "rating": "4.5 stars",
    "category": "Restaurant",
    "lat": "40.7128",
    "lon": "-74.0060"
  },
  "reviews_count": 1,
  "expected_review_count": 1,
  "reviews_complete": true,
  "review_stop_reason": "expected_count_reached",
  "reviews": [
    {
      "review_id": "review-id",
      "user": "Username",
      "user_info": "",
      "rating": "5 stars",
      "time": "a month ago",
      "content": "Review content"
    }
  ],
  "scraped_at": "2026-10-22 10:30:00",
  "retry_attempt": 0,
  "has_reviews": true,
  "review_status": "有评论",
  "final_success": true
}
```

### CSV Format

The single-place CLI saves CSV: `rating` is the review rating and `business_rating` is the overall business rating. Both retain the page text. The batch CLI saves JSON and removes intermediate CSV files.

### Data Scope and Completeness

- Address, phone, website, opening hours, and helpful counts are not extracted. Review times retain relative page text, not normalized dates. Coordinates are URL-derived strings, empty when unavailable.
- Reviews are collected on every scroll and deduplicated primarily by `review_id`. Ratings without text retain an empty `content` string.
- `reviews_complete=true` only confirms the captured count reaches the displayed total, or the page explicitly reports zero reviews. It does not guarantee expanded text or coverage of all reviews held by Google.
- A missing review button is error `1004`; an unknown total is not zero. A scroll limit, stalled loading, or unverifiable count returns `1011`, preserves partial data, and enters the batch failure list.
- The single-place scraper does not immediately repeat an identical `1011` attempt. Increase `--max-scrolls` / `--scroll-wait` and use batch `--retry-failed`; allow a sufficient `--timeout`.
- The retry scanner detects legacy “successful” records carrying error codes. Legacy records without completeness metadata cannot be assumed complete.

### Offline Tests

```bash
python -m unittest discover -s tests -v
```

Tests use simulated browser pages and do not verify compatibility with the current live Google Maps UI.

## 🛠️ Troubleshooting

### Common Issues

1. **Chrome Browser Fails to Start**
   - Ensure Google Chrome is installed.
   - Check ChromeDriver version compatibility.

2. **Network Timeout**
   - Increase the `--timeout` parameter value.
   - Check network connection stability.

3. **CAPTCHA or Anti-scraping Detection**
   - Reduce concurrency (`--max-workers 1`).
   - Increase random delays.
   - Use proxy IPs.

4. **Insufficient Memory**
   - Decrease the `--max-workers` value.
   - Use `--max-places` to process in batches.

### Error Codes

For detailed error code descriptions, please see [error_codes.md](error_codes.md).

## 📈 Performance Optimization

### Recommended Configurations

- **Small-scale testing** (<100 places): `--max-workers 1 --max-places 10`
- **Medium-scale** (100-1000 places): `--max-workers 3 --max-places 100`
- **Large-scale processing** (>1000 places): `--max-workers 5 --max-places 500`

### Notes

- High concurrency may trigger anti-scraping mechanisms.
- It's recommended to run large-scale scraping during off-peak hours.
- Periodically check and clean the output directory.

## 🔧 Development

### Extending Functionality

The project uses a modular design, making it easy to extend:

- Add new data extraction fields.
- Customize output formats.
- Integrate different storage backends.
- Add data cleaning and validation.

### Contribution Guidelines

1. Fork the project.
2. Create a feature branch.
3. Commit your changes.
4. Create a Pull Request.

## 📞 Support

If you have questions or suggestions, please:

1. Check the error code documentation.
2. Check the log files.
3. Submit an Issue describing the problem.

## ⚖️ Disclaimer

This tool is for learning and research purposes only. Users must:

- Comply with Google Maps' Terms of Service.
- Adhere to relevant laws and regulations.
- Control scraping frequency responsibly.
- Respect the website's robots.txt file.

Please use this tool responsibly and avoid placing an excessive burden on the target website.