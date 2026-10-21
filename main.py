#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Maps评论爬虫
从Google Maps商户页面提取商户信息和客户评论
"""

import os
import sys
import json
import time
import re
import logging
import argparse
from url_utils import english_maps_url
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# 🔥 关键修改：确保标准输出使用UTF-8编码
if sys.platform.startswith('win'):
    # Windows系统需要特殊处理
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)

# 设置环境变量确保子进程也使用UTF-8
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 错误代码定义
class ErrorCodes:
    SUCCESS = 0
    BROWSER_INIT_FAILED = 1001
    URL_LOAD_FAILED = 1002
    BUSINESS_INFO_EXTRACTION_FAILED = 1003
    REVIEWS_BUTTON_NOT_FOUND = 1004
    REVIEWS_SCROLL_FAILED = 1005
    REVIEWS_EXTRACTION_FAILED = 1006
    COORDINATES_EXTRACTION_FAILED = 1007
    CSV_SAVE_FAILED = 1008
    NETWORK_TIMEOUT = 1009
    ELEMENT_NOT_FOUND = 1010
    REVIEWS_INCOMPLETE = 1011
    UNEXPECTED_ERROR = 1999

def setup_logging():
    """设置日志系统"""
    # 🔥 关键修改：检查是否为JSON输出模式，如果是，则将所有日志输出到stderr
    # 这样stdout就只有纯JSON数据，不会被日志信息污染
    json_mode = '--json-output' in sys.argv
    
    logger = logging.getLogger('google_maps_scraper')
    
    # 清除任何现有的handler
    logger.handlers.clear()
    
    # 设置日志级别
    logger.setLevel(logging.INFO)
    
    # 创建formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # 🔥 在JSON模式下，所有日志都输出到stderr，否则输出到stdout
    log_stream = sys.stderr if json_mode else sys.stdout
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger

def safe_find_element(driver, by, value, timeout=10, required=False):
    """
    安全查找元素
    
    Args:
        driver: WebDriver实例
        by: 查找方式
        value: 查找值
        timeout: 超时时间
        required: 是否必需找到
        
    Returns:
        element或None
    """
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except TimeoutException:
        if required:
            raise
        return None

def safe_get_text(element, default=""):
    """安全获取元素文本"""
    try:
        return element.text.strip() if element else default
    except:
        return default

def safe_get_attribute(element, attr, default=""):
    """安全获取元素属性"""
    try:
        result = element.get_attribute(attr) if element else None
        return result.strip() if result else default
    except:
        return default

def expected_review_count(driver):
    """Read the English overview count; a missing count is unknown, never zero."""
    counts = []
    for element in driver.find_elements(By.CSS_SELECTOR, 'button[aria-label]'):
        label = safe_get_attribute(element, 'aria-label')
        match = re.search(r'\b([\d,]+)\s+reviews?\b', label, re.IGNORECASE)
        if match:
            counts.append(int(match.group(1).replace(',', '')))
    if counts:
        return max(counts)
    empty = driver.find_elements(
        By.XPATH, "//*[normalize-space(text())='No reviews' or normalize-space(text())='No reviews yet']"
    )
    return 0 if any(element.is_displayed() for element in empty) else None


def extract_review(element):
    """Text is optional: Google Maps also has ratings without written reviews."""
    def optional_text(selector):
        matches = element.find_elements(By.CSS_SELECTOR, selector)
        return safe_get_text(matches[0]) if matches else ''

    rating = safe_get_attribute(element.find_element(By.CSS_SELECTOR, 'span.kvMYJc'), 'aria-label')
    if not rating:
        raise ValueError('评论评分缺失')
    return {
        'review_id': safe_get_attribute(element, 'data-review-id'),
        'user': safe_get_attribute(element, 'aria-label', '匿名用户'),
        'user_info': optional_text('div.RfnDt'),
        'rating': rating,
        'time': optional_text('span.rsqaWe'),
        'content': optional_text('span.wiI7pd'),
    }


def collect_reviews(driver, container, expected_count, max_scrolls=30, scroll_wait=3):
    """Collect each loaded page before it disappears from a virtualized list.

    Neither a fixed scroll height nor a timeout proves that all reviews loaded.
    Only reaching the advertised count confirms count completeness.
    """
    collected = {}
    failed = set()

    def read_visible(browser):
        before = len(collected)
        for element in browser.find_elements(By.CSS_SELECTOR, 'div.jftiEf.fontBodyMedium'):
            identity = safe_get_attribute(element, 'data-review-id')
            failure_key = identity or safe_get_attribute(element, 'outerHTML', 'unknown')
            try:
                data = extract_review(element)
                key = identity or json.dumps(data, sort_keys=True, ensure_ascii=False)
                collected[key] = data
                failed.discard(failure_key)
            except (NoSuchElementException, WebDriverException, ValueError):
                failed.add(failure_key)
        return len(collected) > before

    def outcome(complete, reason):
        return list(collected.values()), complete, reason

    def reached_count():
        return expected_count is not None and len(collected) >= expected_count and not failed

    try:
        read_visible(driver)
        if reached_count():
            return outcome(True, 'expected_count_reached')
        unchanged = 0
        for _ in range(max_scrolls):
            before = len(collected)
            driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', container)
            try:
                WebDriverWait(driver, scroll_wait).until(read_visible)
            except TimeoutException:
                pass
            if reached_count():
                return outcome(True, 'expected_count_reached')
            unchanged = unchanged + 1 if len(collected) == before else 0
            if unchanged >= 3:
                return outcome(False, 'extraction_failed' if failed else 'stalled')
        return outcome(False, 'extraction_failed' if failed else 'max_scrolls')
    except WebDriverException:
        return outcome(False, 'scroll_failed')


def scrape_single_url(url, output_dir="output", headless=True, max_retries=3,
                      max_scrolls=30, scroll_wait=3):
    """
    爬取单个URL的数据
    返回结果字典和状态信息
    """
    logger = logging.getLogger('google_maps_scraper')
    if max_retries < 1 or max_scrolls < 1 or scroll_wait <= 0:
        raise ValueError('max_retries、max_scrolls 和 scroll_wait 必须大于 0')
    url = english_maps_url(url)
    
    # 滚动参数
    coordinate_retries = 10

    empty_result = {
        "success": False,
        "error_code": ErrorCodes.SUCCESS,
        "error_message": "",
        "business_info": {},
        "reviews_count": 0,
        "reviews": [],
        "csv_file": None,
        "expected_review_count": None,
        "reviews_complete": False,
        "review_stop_reason": "not_started",
        "url": url
    }

    result = empty_result.copy()
    driver = None
    
    for attempt in range(max_retries):
        # A successful retry must not inherit an earlier attempt's error.
        result = empty_result.copy()
        try:
            logger.info(f"尝试第 {attempt + 1} 次爬取: {url}")
            
            # 设置Chrome选项
            options = Options()
            if headless:
                options.add_argument("--headless")
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            
            # 🔥 在JSON输出模式下添加额外的静默参数
            json_mode = '--json-output' in sys.argv
            if json_mode:
                options.add_argument("--disable-logging")
                options.add_argument("--disable-gpu-logging")
                options.add_argument("--disable-chromium-logging")
                options.add_argument("--log-level=3")  # 只显示FATAL级别
                options.add_argument("--silent")
                options.add_argument("--disable-background-timer-throttling")
                options.add_argument("--disable-renderer-backgrounding")
                options.add_argument("--disable-backgrounding-occluded-windows")
                options.add_argument("--disable-extensions-http-throttling")
                
                # 禁用各种服务和功能的日志输出
                options.add_experimental_option('excludeSwitches', ['enable-logging'])
                options.add_experimental_option('useAutomationExtension', False)
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                
                # 设置日志首选项
                prefs = {
                    "profile.default_content_setting_values": {
                        "notifications": 2
                    }
                }
                options.add_experimental_option("prefs", prefs)

            # 创建 WebDriver 实例
            try:
                driver = webdriver.Chrome(options=options)
                driver.set_page_load_timeout(30)
                logger.info("Chrome浏览器启动成功")
            except Exception as e:
                result["error_code"] = ErrorCodes.BROWSER_INIT_FAILED
                result["error_message"] = f"无法启动Chrome浏览器: {str(e)}"
                logger.error(result["error_message"])
                if attempt == max_retries - 1:
                    return result
                continue

            # 加载页面
            try:
                logger.info(f"正在加载页面: {url}")
                driver.get(url)
                time.sleep(3)
            except Exception as e:
                result["error_code"] = ErrorCodes.URL_LOAD_FAILED
                result["error_message"] = f"页面加载失败: {str(e)}"
                logger.error(result["error_message"])
                if attempt == max_retries - 1:
                    return result
                continue

            info = {"url": url}
            
            # 提取商户基本信息
            try:
                logger.info("正在提取商户基本信息...")
                
                # 商户名称
                name_elem = safe_find_element(driver, By.CSS_SELECTOR, 'h1.DUwDvf.lfPIob', timeout=15, required=True)
                info['name'] = safe_get_text(name_elem)
                if not info['name']:
                    raise ValueError("商户名称为空，无法确认地点页面已加载")
                
                # 评分
                rating_elem = safe_find_element(driver, By.CSS_SELECTOR, 'span.ceNzKf', timeout=10)
                info['rating'] = safe_get_attribute(rating_elem, 'aria-label') or "无评分"
                
                # 类别
                category_elem = safe_find_element(driver, By.CSS_SELECTOR, 'button.DkEaL', timeout=10)
                info['category'] = safe_get_text(category_elem) or "未知类别"
                
                logger.info(f"商户信息提取成功: {info['name']}")
                
            except Exception as e:
                result["error_code"] = ErrorCodes.BUSINESS_INFO_EXTRACTION_FAILED
                result["error_message"] = f"商户信息提取失败: {str(e)}"
                logger.warning(result["error_message"])
                info.update({'name': '未知商户', 'rating': '无评分', 'category': '未知类别'})
                continue

            all_reviews = []
            try:
                expected = expected_review_count(driver)
                result["expected_review_count"] = expected
                if expected == 0:
                    result.update(reviews_complete=True, review_stop_reason="no_reviews")
                else:
                    selectors = [
                        "//button[@role='tab'][contains(@aria-label, 'Reviews')]",
                        "//div[@class='LRkQ2']//div[text()='Reviews']",
                        "//button[contains(text(), 'Reviews')]",
                        "//div[text()='Reviews']",
                        "//span[text()='Reviews']",
                    ]

                    def find_reviews_button(browser):
                        for selector in selectors:
                            for element in browser.find_elements(By.XPATH, selector):
                                if element.is_displayed():
                                    return element
                        return False

                    try:
                        reviews_button = WebDriverWait(driver, 10).until(find_reviews_button)
                    except TimeoutException:
                        result.update(error_code=ErrorCodes.REVIEWS_BUTTON_NOT_FOUND,
                                      error_message="未找到 Reviews 按钮，无法确认评论状态",
                                      review_stop_reason="button_not_found")
                    else:
                        driver.execute_script("arguments[0].click();", reviews_button)
                        try:
                            container = safe_find_element(
                                driver, By.CSS_SELECTOR,
                                'div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde',
                                timeout=10, required=True,
                            )
                        except TimeoutException:
                            result.update(error_code=ErrorCodes.REVIEWS_SCROLL_FAILED,
                                          error_message="未找到评论滚动容器",
                                          review_stop_reason="scroll_failed")
                        else:
                            all_reviews, complete, reason = collect_reviews(
                                driver, container, expected, max_scrolls, scroll_wait
                            )
                            result.update(reviews_complete=complete, review_stop_reason=reason)
                            if not complete:
                                code = {
                                    "scroll_failed": ErrorCodes.REVIEWS_SCROLL_FAILED,
                                    "extraction_failed": ErrorCodes.REVIEWS_EXTRACTION_FAILED,
                                }.get(reason, ErrorCodes.REVIEWS_INCOMPLETE)
                                result.update(error_code=code, error_message=(
                                    f"评论采集未完成: {reason}; 已采集 {len(all_reviews)}, 页面总数 {expected}"
                                ))
            except Exception as e:
                result.update(error_code=ErrorCodes.REVIEWS_EXTRACTION_FAILED,
                              error_message=f"评论提取过程失败: {e}",
                              review_stop_reason="extraction_failed")
                logger.warning(result["error_message"])

            # 提取坐标
            lat, lon = None, None
            try:
                logger.info("正在提取坐标信息...")
                
                for attempt_coord in range(coordinate_retries):
                    try:
                        current_url = driver.current_url
                        
                        # 尝试多种坐标提取方式
                        patterns = [
                            r'!3d([0-9\.\-]+)!4d([0-9\.\-]+)',
                            r'/@([0-9\.\-]+),([0-9\.\-]+)',
                            r'@([0-9\.\-]+),([0-9\.\-]+)',
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, current_url)
                            if match:
                                lat, lon = match.group(1), match.group(2)
                                logger.info(f"坐标提取成功: {lat}, {lon}")
                                break
                        
                        if lat and lon:
                            break
                        else:
                            time.sleep(1)
                            
                    except Exception as e:
                        if attempt_coord == coordinate_retries - 1:
                            logger.warning(f"坐标提取失败: {str(e)}")
                        continue
                        
            except Exception as e:
                result["error_code"] = ErrorCodes.COORDINATES_EXTRACTION_FAILED
                result["error_message"] = f"坐标提取失败: {str(e)}"
                logger.warning(result["error_message"])

            info['lat'] = lat or ''
            info['lon'] = lon or ''
            
            # 保存数据
            try:
                os.makedirs(output_dir, exist_ok=True)
                csv_info = {
                    ('business_rating' if key == 'rating' else key): value
                    for key, value in info.items()
                }
                if len(all_reviews) == 0:
                    df = pd.DataFrame([csv_info])
                else:
                    df = pd.DataFrame(all_reviews)
                    for key, value in csv_info.items():
                        df[key] = value
                
                # 保存CSV文件
                if info['name'] and info['name'] != '未知商户':
                    # 清理文件名中的非法字符
                    safe_name = re.sub(r'[<>:"/\\|?*]', '_', info['name'])
                    filename = f"{output_dir}/{safe_name}.csv"
                    df.to_csv(filename, index=False, encoding='utf-8-sig')
                    result["csv_file"] = filename
                    logger.info(f"数据已保存到: {filename}")
                
            except Exception as e:
                result["error_code"] = ErrorCodes.CSV_SAVE_FAILED
                result["error_message"] = f"CSV文件保存失败: {str(e)}"
                logger.error(result["error_message"])

            # 成功完成
            # 🔥 关键修改：保留原有的错误代码，特别是Reviews相关的错误代码
            final_error_code = result.get("error_code", ErrorCodes.SUCCESS)
            final_error_message = result.get("error_message", "")
            
            result.update({
                "success": final_error_code == ErrorCodes.SUCCESS,
                "error_code": final_error_code,  # 保留原有错误代码
                "error_message": final_error_message,  # 保留原有错误信息
                "business_info": info,
                "reviews_count": len(all_reviews),
                "reviews": all_reviews
            })
            
            if (not result['success'] and final_error_code != ErrorCodes.REVIEWS_INCOMPLETE
                    and attempt < max_retries - 1):
                continue
            logger.info(f"爬取结束: {info['name']}, {len(all_reviews)} 条评论, 成功={result['success']}")
            return result
            
        except Exception as e:
            result["error_code"] = ErrorCodes.UNEXPECTED_ERROR
            result["error_message"] = f"意外错误: {str(e)}"
            logger.error(f"第 {attempt + 1} 次尝试失败: {result['error_message']}")
            
            if attempt < max_retries - 1:
                logger.info("等待重试...")
                time.sleep(5)
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
                driver = None

    # 所有重试都失败了
    if not result["error_message"]:
        result["error_message"] = f"经过 {max_retries} 次重试仍然失败"
    
    logger.error(f"爬取最终失败: {result['error_message']}")
    return result

def main():
    parser = argparse.ArgumentParser(description='Google Maps评论爬虫')
    parser.add_argument('positional_url', nargs='?', help='Google Maps URL（也可使用 --url）')
    parser.add_argument('--url', type=str, help='要爬取的Google Maps URL')
    parser.add_argument('--urls-file', type=str, default='input/urls.txt', help='包含URL列表的文件路径')
    parser.add_argument('--output-dir', type=str, default='output', help='输出目录')
    browser_mode = parser.add_mutually_exclusive_group()
    browser_mode.add_argument('--headless', dest='headless', action='store_true', help='无界面模式运行')
    browser_mode.add_argument('--no-headless', dest='headless', action='store_false', help='显示浏览器界面')
    parser.set_defaults(headless=False)
    parser.add_argument('--json-output', action='store_true', help='以JSON格式输出结果')
    parser.add_argument('--max-retries', type=int, default=3, help='最大重试次数')
    parser.add_argument('--max-scrolls', type=int, default=30, help='评论滚动次数上限（到达上限可能不完整）')
    parser.add_argument('--scroll-wait', type=float, default=3, help='每次滚动等待新评论的秒数')
    parser.add_argument('--verbose', action='store_true', help='详细日志输出')
    
    args = parser.parse_args()
    if args.url and args.positional_url:
        parser.error('URL 只能通过位置参数或 --url 指定一次')
    if args.max_retries < 1 or args.max_scrolls < 1 or args.scroll_wait <= 0:
        parser.error('--max-retries、--max-scrolls 和 --scroll-wait 必须大于 0')
    args.url = args.url or args.positional_url
    
    # 设置日志级别
    logger = setup_logging()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    urls = []
    
    # 如果指定了单个URL
    if args.url:
        urls = [args.url]
    else:
        # 从文件读取URL列表
        try:
            with open(args.urls_file, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            error_result = {
                "success": False,
                "error_code": ErrorCodes.ELEMENT_NOT_FOUND,
                "error_message": f"文件 {args.urls_file} 不存在"
            }
            if args.json_output:
                print(json.dumps([error_result], ensure_ascii=False))
            else:
                print(f"错误: {error_result['error_message']}", file=sys.stderr)
            sys.exit(1)
    
    if not urls:
        error_result = {
            "success": False,
            "error_code": ErrorCodes.ELEMENT_NOT_FOUND,
            "error_message": "没有找到要处理的URL"
        }
        if args.json_output:
            print(json.dumps([error_result], ensure_ascii=False))
        else:
            print(f"错误: {error_result['error_message']}", file=sys.stderr)
        sys.exit(1)
    
    results = []
    
    for i, url in enumerate(urls, 1):
        if not args.json_output:
            print(f"[{i}/{len(urls)}] 正在处理: {url}")
        
        result = scrape_single_url(url, args.output_dir, args.headless, args.max_retries,
                                   max_scrolls=args.max_scrolls, scroll_wait=args.scroll_wait)
        results.append(result)
        
        if not args.json_output:
            if result["success"]:
                business_name = result['business_info'].get('name', '未知')
                reviews_count = result['reviews_count']
                print(f"✓ {business_name}: 成功提取 {reviews_count} 条评论")
            else:
                print(f"✗ 失败 (错误代码: {result['error_code']}): {result['error_message']}")
    
    if args.json_output:
        # 🔥 关键修改：在输出JSON前，确保标准输出正确配置
        import locale
        
        # 尝试设置locale为UTF-8
        try:
            if sys.platform.startswith('win'):
                locale.setlocale(locale.LC_ALL, '')
        except:
            pass
            
        # 强制刷新标准输出缓冲区
        sys.stdout.flush()
        
        # 输出JSON，明确指定编码选项
        json_output = json.dumps(results, ensure_ascii=False, indent=2)
        
        # 在Windows下，确保正确输出
        if sys.platform.startswith('win'):
            try:
                # 尝试直接输出字节
                sys.stdout.buffer.write(json_output.encode('utf-8'))
                sys.stdout.buffer.write(b'\n')
                sys.stdout.buffer.flush()
            except (AttributeError, UnicodeEncodeError):
                # 备用方案：普通输出
                print(json_output)
        else:
            print(json_output)
    else:
        success_count = sum(1 for r in results if r["success"])
        print(f"\n处理完成！成功: {success_count}/{len(urls)}")
        
        # 显示失败的URL和错误
        failed_results = [r for r in results if not r["success"]]
        if failed_results:
            print("\n失败的URL:")
            for result in failed_results:
                print(f"  {result['url']} - 错误代码: {result['error_code']} - {result['error_message']}")

if __name__ == "__main__":
    main()
