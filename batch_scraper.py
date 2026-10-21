#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
大规模批量Google Maps数据爬取工具 - 增强版
=============================================================================

专为处理数万级地点数据设计的高可靠性批量爬虫工具

主要特性：
- 支持数万个地点的批量处理
- 强大的断点恢复机制，支持意外中断后继续处理
- 智能重试模式，可选择性重试失败的地点
- 按 parent_type/sub_type/place_id_名称.json 组织输出文件
- 多线程并发处理，内存优化
- 详细的进度跟踪和错误处理
- 处理数量限制，便于测试和分批处理

异常处理机制：
1. 每个地点独立处理，单点失败不影响整体
2. 自动重试机制，网络超时等临时问题可重试
3. 详细错误分类和记录，便于问题诊断
4. 实时进度保存，每10个地点自动保存状态
5. 支持验证码等服务器异常的重试处理

断点恢复机制：
1. progress.json 精确记录每个place_id的处理状态
2. 重新运行时自动跳过已成功处理的地点
3. 可选择重试失败的地点（--retry-failed）
4. 支持分批处理，便于监控大规模数据处理

=============================================================================
"""

# =============================================================================
# 配置区域 - 所有可调参数
# =============================================================================

# 默认处理参数配置
DEFAULT_CONFIG = {
    # === 基础处理参数 ===
    'max_workers': 3,           # 默认最大并发线程数（建议2-5，过高可能被限制）
    'max_retries': 3,           # 默认最大重试次数（单个地点的重试次数）
    'timeout': 300,             # 默认单个地点超时时间（秒）
    'max_places': None,         # 默认每次最大处理地点数量（None=无限制，建议测试时设置为5-10）
    
    # === 进度管理参数 ===
    'auto_save_interval': 10,   # 自动保存进度的间隔（每处理N个地点保存一次）
    'resume_by_default': True,  # 默认是否启用断点恢复
    'retry_failed_by_default': False,  # 默认是否重试失败地点
    
    # === 并发控制参数 ===
    'queue_size_multiplier': 2, # 并发队列大小倍数（max_workers * multiplier）
    'batch_submit_size': None,  # 批量提交任务的大小（None=使用队列大小）
    
    # === 文件和日志参数 ===
    'log_level': 'INFO',        # 日志级别 (DEBUG, INFO, WARNING, ERROR)
    'filename_max_length': 50,  # 文件名中商户名称的最大长度
    'output_encoding': 'utf-8', # 输出文件编码
    
    # === 爬虫脚本参数 ===
    'scraper_script': 'main.py', # 单点爬虫脚本路径
    'headless_mode': True,      # 是否使用无界面模式
    'verbose_logging': False,   # 是否启用详细日志
}

# 测试模式配置（便于快速测试）
TEST_CONFIG = {
    'max_workers': 1,           # 测试时使用单线程
    'max_retries': 2,           # 测试时减少重试次数
    'timeout': 60,              # 测试时缩短超时时间
    'max_places': 5,            # 测试时只处理5个地点
    'verbose_logging': True,    # 测试时启用详细日志
}

# 生产环境配置（用于大规模数据处理）
PRODUCTION_CONFIG = {
    'max_workers': 5,           # 生产环境使用更多线程
    'max_retries': 5,           # 生产环境增加重试次数
    'timeout': 600,             # 生产环境延长超时时间
    'max_places': 1000,         # 生产环境每次处理1000个地点
    'auto_save_interval': 5,    # 生产环境更频繁保存进度
}

# 无人值守模式配置（适合长期自动运行）
UNATTENDED_CONFIG = {
    'max_workers': 6,           # 稳定的并发数
    'max_places': 120,         # 每批处理2000个地点
    'max_retries': 5,           # 增加重试次数
    'timeout': 120,             # 长超时时间
    'auto_save_interval': 12,   # 更频繁保存进度
    'auto_retry_failed': True,  # 自动重试失败地点
    'continuous_mode': True,    # 连续处理模式
    'max_continuous_rounds': 5, # 最大连续处理轮数（-1表示无限制）
    'rest_between_rounds': 60, # 轮次间休息时间（秒）
    'infinite_mode': False,     # 无限模式（忽略max_continuous_rounds）
    'max_idle_rounds': 3,       # 最大空闲轮数（没有新地点处理时停止）
    'checkpoint_interval': 60,  # 检查点间隔时间（分钟）
    'enable_keyboard_interrupt': True,  # 允许Ctrl+C优雅退出
}

# 🆕 无限运行模式配置
INFINITE_CONFIG = {
    'max_workers': 6,           # 降低并发以稳定运行
    'max_places': 300,         # 每批处理300个地点
    'max_retries': 3,           # 适中的重试次数
    'timeout': 150,             # 适中的超时时间
    'auto_save_interval': 6,    # 更频繁保存进度
    'auto_retry_failed': True,  # 自动重试失败地点
    'continuous_mode': True,    # 连续处理模式
    'max_continuous_rounds': -1, # 无限轮数
    'rest_between_rounds': 60, # 轮次间休息3分钟
    'infinite_mode': True,      # 🔥 开启无限模式
    'max_idle_rounds': 5,       # 连续5轮无新地点时停止
    'checkpoint_interval': 30,  # 每30分钟输出检查点信息
    'enable_keyboard_interrupt': True,  # 允许Ctrl+C优雅退出
}

# 🆕 快速模式配置（适合测试或小规模数据）
FAST_CONFIG = {
    'max_workers': 5,           # 更高的并发数
    'max_places': 500,          # 每批处理500个地点
    'max_retries': 2,           # 较少的重试次数
    'timeout': 200,             # 较短的超时时间
    'auto_save_interval': 20,   # 适中的保存间隔
    'auto_retry_failed': False, # 不自动重试，提高速度
    'continuous_mode': True,    # 连续处理模式
    'max_continuous_rounds': 10, # 最多10轮
    'rest_between_rounds': 60,  # 轮次间休息1分钟
    'infinite_mode': False,     # 非无限模式
}

# =============================================================================
# 导入依赖模块
# =============================================================================

import json
import os
import time
import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from tqdm import tqdm
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from url_utils import english_maps_url

# =============================================================================
# 主要类定义
# =============================================================================

class BatchGoogleMapsScraper:
    """
    大规模批量Google Maps数据爬取器
    
    专为处理数万级地点数据设计，具备完善的异常处理和恢复机制
    """
    
    def __init__(self, script_path: Optional[str] = None, output_base_dir: str = "batch_output", config: Optional[Dict] = None):
        """
        初始化批量爬虫
        
        Args:
            script_path: 单点爬虫脚本路径
            output_base_dir: 输出根目录
            config: 配置参数字典，覆盖默认配置
        """
        # 合并配置参数
        self.config = DEFAULT_CONFIG.copy()
        if config:
            self.config.update(config)
        
        # 核心路径设置
        self.script_path = script_path or str(Path(__file__).resolve().parent / self.config['scraper_script'])
        self.output_base_dir = Path(output_base_dir)
        
        # 状态文件路径
        self.progress_file = self.output_base_dir / "progress.json"      # 进度文件
        self.error_log_file = self.output_base_dir / "errors.jsonl"     # 错误日志
        self.success_log_file = self.output_base_dir / "success.jsonl"  # 成功日志
        
        # 线程安全锁（用于文件写入保护）
        self.lock = threading.Lock()
        
        # 创建输出目录
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志系统
        self.setup_logging()
        
        # 输出初始化信息
        self.logger.info(f"批量爬虫初始化完成")
        self.logger.info(f"输出目录: {self.output_base_dir}")
        self.logger.info(f"当前配置: 并发={self.config['max_workers']}, 重试={self.config['max_retries']}, 超时={self.config['timeout']}s")
        if self.config['max_places']:
            self.logger.info(f"处理数量限制: {self.config['max_places']} 个地点")
        
    def setup_logging(self):
        """
        设置日志系统
        
        创建文件和控制台双重日志输出，便于调试和监控
        """
        log_file = self.output_base_dir / "batch_scraper.log"
        
        # 根据配置设置日志级别
        log_level = getattr(logging, self.config['log_level'].upper())
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),  # 文件日志
                logging.StreamHandler(sys.stdout)                # 控制台日志
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_jsonl_input(self, input_file: str) -> List[Dict[str, Any]]:
        """
        加载JSONL格式的输入文件
        
        支持包含place_id, Maps_url, parent_type, sub_type等字段的地点数据
        
        Args:
            input_file: JSONL文件路径
            
        Returns:
            地点数据列表
        """
        places = []
        try:
            # 🔥 改进编码处理，尝试多种编码方式
            encodings_to_try = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']
            file_content = None
            used_encoding = None
            
            for encoding in encodings_to_try:
                try:
                    with open(input_file, 'r', encoding=encoding) as f:
                        file_content = f.read()
                        used_encoding = encoding
                        break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if file_content is None:
                # 如果所有编码都失败，使用UTF-8并忽略错误
                with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
                    used_encoding = 'utf-8 (with errors ignored)'
            
            self.logger.info(f"使用编码 {used_encoding} 读取输入文件")
            
            # 逐行解析JSONL
            for line_num, line in enumerate(file_content.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    place_data = json.loads(line)
                    if not isinstance(place_data, dict):
                        raise ValueError('每行必须是 JSON 对象')
                    place_data['Maps_url'] = english_maps_url(place_data.get('Maps_url') or place_data.get('url'))
                    # 验证必需字段
                    required_fields = ['place_id', 'Maps_url', 'parent_type', 'sub_type']
                    if all(field in place_data for field in required_fields):
                        places.append(place_data)
                    else:
                        missing_fields = [f for f in required_fields if f not in place_data]
                        self.logger.warning(f"第{line_num}行缺少必需字段 {missing_fields}: {line[:100]}...")
                except (json.JSONDecodeError, ValueError) as e:
                    self.logger.error(f"第{line_num}行JSON解析失败: {e}")
        except FileNotFoundError:
            self.logger.error(f"输入文件不存在: {input_file}")
            return []
        except Exception as e:
            self.logger.error(f"读取输入文件时发生错误: {e}")
            return []
        
        self.logger.info(f"成功加载 {len(places)} 个地点数据")
        return places
    
    def load_progress(self) -> Dict[str, Any]:
        """
        加载处理进度
        
        从progress.json读取之前的处理状态，支持断点恢复
        
        Returns:
            包含处理进度的字典
        """
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                    
                    # 确保包含所有必需字段（向后兼容）
                    default_progress = {
                        "total": 0,                 # 总地点数
                        "current_index": 0,         # 当前处理索引
                        "successful": [],           # 成功处理的place_id列表
                        "failed": [],               # 失败的place_id列表
                        "skipped": [],              # 跳过的place_id列表
                        "success_count": 0,         # 成功计数
                        "failed_count": 0,          # 失败计数
                        "skipped_count": 0,         # 跳过计数
                        "last_updated": "",         # 最后更新时间
                        "start_time": "",           # 开始时间
                        "session_info": {}          # 会话信息
                    }
                    
                    # 合并加载的数据和默认数据（确保字段完整）
                    for key, value in default_progress.items():
                        if key not in progress:
                            progress[key] = value
                    
                    self.logger.info(f"加载进度: 成功 {len(progress['successful'])}, 失败 {len(progress['failed'])}")
                    return progress
                    
            except Exception as e:
                self.logger.warning(f"加载进度文件失败: {e}，将重新开始")
        
        # 返回空进度（首次运行或进度文件损坏）
        return {
            "total": 0,
            "current_index": 0,
            "successful": [],
            "failed": [],
            "skipped": [],
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "last_updated": "",
            "start_time": "",
            "session_info": {}
        }
    
    def save_progress(self, progress: Dict[str, Any]):
        """
        保存处理进度
        
        线程安全地保存当前处理状态到progress.json
        
        Args:
            progress: 进度信息字典
        """
        progress["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        with self.lock:  # 确保文件写入的线程安全
            try:
                with open(self.progress_file, 'w', encoding='utf-8') as f:
                    json.dump(progress, f, ensure_ascii=False, indent=2)
                self.logger.debug("进度已保存")
            except Exception as e:
                self.logger.error(f"保存进度失败: {e}")
    
    def get_processed_place_ids(self) -> Set[str]:
        """
        获取所有已处理（成功+失败+跳过）的place_id集合
        
        用于判断哪些地点已经处理过，避免重复处理
        
        Returns:
            已处理的place_id集合
        """
        progress = self.load_progress()
        processed = set(progress.get("successful", []))
        processed.update(progress.get("failed", []))
        processed.update(progress.get("skipped", []))
        return processed
    
    def get_failed_place_ids(self) -> Set[str]:
        """
        获取失败的place_id集合
        
        用于重试模式，只重试失败的地点
        
        Returns:
            失败的place_id集合
        """
        progress = self.load_progress()
        return set(progress.get("failed", []))
    
    def filter_places_to_process(self, places: List[Dict[str, Any]], 
                                retry_failed: bool = False, 
                                max_places: Optional[int] = None) -> tuple[List[Dict[str, Any]], Set[str]]:
        """
        过滤需要处理的地点
        
        根据已处理状态和配置参数，确定实际需要处理的地点列表
        
        Args:
            places: 所有地点列表
            retry_failed: 是否重试失败的地点
            max_places: 最大处理数量限制
            
        Returns:
            tuple: (需要处理的地点列表, 失败的place_id集合)
        """
        # 🔥 优化：只加载一次进度信息，避免重复日志
        progress = self.load_progress()
        processed_ids = set(progress.get("successful", []))
        processed_ids.update(progress.get("failed", []))
        processed_ids.update(progress.get("skipped", []))
        failed_ids = set(progress.get("failed", []))
        
        to_process = []
        skipped_already_processed = 0
        skipped_not_retry = 0
        
        for place in places:
            place_id = place["place_id"]
            
            if place_id not in processed_ids:
                # 未处理过的地点 - 添加到处理列表
                to_process.append(place)
            elif retry_failed and place_id in failed_ids:
                # 重试模式下的失败地点 - 添加到处理列表
                to_process.append(place)
            elif place_id in failed_ids:
                # 非重试模式下的失败地点 - 跳过
                skipped_not_retry += 1
            else:
                # 已成功处理的地点 - 跳过
                skipped_already_processed += 1
        
        original_count = len(to_process)
        
        # 🔥 新增：详细统计信息
        total_input = len(places)
        self.logger.info(f"地点过滤统计:")
        self.logger.info(f"  输入总数: {total_input}")
        self.logger.info(f"  已成功处理: {len(progress.get('successful', []))}")
        self.logger.info(f"  已失败: {len(failed_ids)}")
        self.logger.info(f"  需要处理: {original_count}")
        if skipped_already_processed > 0:
            self.logger.info(f"  跳过(已处理): {skipped_already_processed}")
        if skipped_not_retry > 0:
            self.logger.info(f"  跳过(失败但非重试): {skipped_not_retry}")
        
        # 应用数量限制
        max_places = max_places or self.config['max_places']
        if max_places and max_places > 0:
            to_process = to_process[:max_places]
            if len(to_process) < original_count:
                self.logger.info(f"应用数量限制: {original_count} -> {len(to_process)} 个地点")
        
        self.logger.info(f"最终待处理地点: {len(to_process)} 个")
        if retry_failed:
            retry_count = sum(1 for place in to_process if place["place_id"] in failed_ids)
            self.logger.info(f"其中重试失败地点: {retry_count} 个")
        
        return to_process, failed_ids
    
    def get_output_path(self, parent_type: str, sub_type: str) -> Path:
        """
        获取输出目录路径
        
        根据地点类型创建对应的目录结构
        
        Args:
            parent_type: 父类别（如：entertainment_and_recreation）
            sub_type: 子类别（如：cycling_park）
            
        Returns:
            输出目录路径
        """
        type_dir = self.output_base_dir / parent_type / sub_type
        type_dir.mkdir(parents=True, exist_ok=True)
        return type_dir
    
    def generate_filename(self, place_id: str, business_name: str = "") -> str:
        """
        生成安全的文件名
        
        清理商户名称中的特殊字符，确保文件名在各操作系统下都可用
        
        Args:
            place_id: 地点ID
            business_name: 商户名称
            
        Returns:
            安全的文件名
        """
        import re
        
        # 清理商户名称中的特殊字符
        if business_name:
            # 替换所有非字母数字的字符为下划线，包括空格和标点符号
            safe_name = re.sub(r'[<>:"/\\|?*\s&/().,;!\[\]{}]', '_', business_name)
            # 移除多个连续的下划线
            safe_name = re.sub(r'_+', '_', safe_name)
            # 移除开头和结尾的下划线
            safe_name = safe_name.strip('_')
            # 限制长度避免文件名过长
            safe_name = safe_name[:self.config['filename_max_length']] if len(safe_name) > self.config['filename_max_length'] else safe_name
            filename = f"{place_id}_{safe_name}.json"
        else:
            filename = f"{place_id}.json"
        
        return filename
    
    def scrape_single_place(self, place_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        爬取单个地点数据
        
        调用单点爬虫脚本，处理各种异常情况，确保单点失败不影响整体处理
        
        Args:
            place_data: 地点信息字典
            **kwargs: 传递给爬虫的额外参数
            
        Returns:
            包含爬取结果的字典
            
        异常处理机制：
        1. 脚本执行失败 - 记录错误信息，返回失败状态
        2. JSON解析失败 - 记录解析错误，返回失败状态
        3. 超时异常 - 记录超时信息，可重试
        4. 其他异常 - 统一捕获并记录
        """
        url = place_data["Maps_url"]
        place_id = place_data["place_id"]
        
        # 构建爬虫命令
        cmd = [
            sys.executable, self.script_path,
            "--url", url,
            "--output-dir", str(self.output_base_dir),  # 添加输出目录参数
            "--json-output",
        ]
        
        # 根据配置添加无界面模式
        if self.config['headless_mode']:
            cmd.append("--headless")
        
        # 添加其他参数
        if kwargs.get("max_retries"):
            cmd.extend(["--max-retries", str(kwargs["max_retries"])])
        for option in ('max_scrolls', 'scroll_wait'):
            if kwargs.get(option) is not None:
                cmd.extend(['--' + option.replace('_', '-'), str(kwargs[option])])
        if kwargs.get("verbose") or self.config['verbose_logging']:
            cmd.append("--verbose")
        
        try:
            # 执行爬虫脚本
            # 使用subprocess确保进程隔离，单个地点失败不影响其他地点
            
            # 🔥 关键修改：设置环境变量确保正确的编码
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            env['PYTHONLEGACYWINDOWSSTDIO'] = '0'  # Windows下强制使用UTF-8
            if sys.platform.startswith('win'):
                env['CHCP'] = '65001'  # Windows代码页设置为UTF-8
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',  # 明确使用UTF-8编码
                errors='ignore',   # 🔥 关键修改：忽略无法解码的字符，而不是替换
                timeout=kwargs.get("timeout", self.config['timeout']),
                env=env  # 🔥 传递环境变量
            )
            
            if result.returncode == 0:
                # 脚本执行成功，解析结果
                try:
                    # 🆕 改进JSON解析，处理编码问题
                    output_text = result.stdout.strip()
                    
                    # 如果输出为空，记录详细信息
                    if not output_text:
                        self.logger.warning(f"脚本输出为空 {place_id}")
                        scrape_result = {"success": False, "error_code": 1999, "error_message": "脚本输出为空"}
                    else:
                        # 🔥 改进的JSON解析逻辑 - 寻找JSON开始位置
                        try:
                            # 寻找JSON数组开始位置
                            json_start = output_text.find('[')
                            if json_start != -1:
                                # 提取从JSON开始的部分
                                json_part = output_text[json_start:].strip()
                                output_data = json.loads(json_part)
                                scrape_result = output_data[0] if output_data else {}
                                
                                self.logger.debug(f"JSON解析成功 {place_id}: {scrape_result.get('business_info', {}).get('name', '未知')}")
                                
                            elif output_text.startswith('{'):
                                # 处理单个JSON对象的情况
                                output_data = json.loads(output_text)
                                scrape_result = output_data
                            else:
                                # 没有找到有效的JSON标记
                                self.logger.error(f"未找到有效JSON {place_id}")
                                self.logger.error(f"原始输出: {output_text[:200]}...")
                                scrape_result = {"success": False, "error_code": 1999, "error_message": "输出中未找到有效的JSON"}
                                
                        except json.JSONDecodeError as e:
                            # JSON解析失败时，记录详细信息
                            self.logger.error(f"JSON解析失败 {place_id}: {e}")
                            
                            # 如果找到了JSON开始位置，记录尝试解析的内容
                            json_start = output_text.find('[')
                            if json_start != -1:
                                json_part = output_text[json_start:]
                                self.logger.error(f"尝试解析的JSON前200字符: {json_part[:200]}")
                            else:
                                self.logger.error(f"原始输出前200字符: {output_text[:200]}")
                            
                            # 尝试提取可能的错误信息
                            error_msg = f"JSON解析失败: {e}"
                            if "encoding" in str(e).lower() or "codec" in str(e).lower():
                                error_msg += " (可能是编码问题)"
                            
                            scrape_result = {"success": False, "error_code": 1999, "error_message": error_msg}
                
                except Exception as e:
                    # 其他解析异常
                    self.logger.error(f"输出解析异常 {place_id}: {e}")
                    scrape_result = {"success": False, "error_code": 1999, "error_message": f"输出解析异常: {e}"}
                
                # 合并原始数据和爬取结果
                combined_result = {
                    **place_data,  # 保留原始的place_id, parent_type等信息
                    "scrape_success": scrape_result.get("success", False),
                    "scrape_error_code": scrape_result.get("error_code", 0),
                    "scrape_error_message": scrape_result.get("error_message", ""),
                    "business_info": scrape_result.get("business_info", {}),
                    "reviews_count": scrape_result.get("reviews_count", 0),
                    "reviews": scrape_result.get("reviews", []),
                    "expected_review_count": scrape_result.get("expected_review_count"),
                    "reviews_complete": scrape_result.get("reviews_complete", False),
                    "review_stop_reason": scrape_result.get("review_stop_reason", "unknown"),
                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "retry_attempt": kwargs.get("retry_attempt", 0)
                }
                
                # Finding some reviews, or missing the tab, is not proof of success.
                success = (combined_result["scrape_success"]
                           and combined_result["scrape_error_code"] == 0
                           and combined_result["reviews_complete"] is True)
                combined_result["final_success"] = bool(success)
                combined_result["has_reviews"] = combined_result["reviews_count"] > 0
                combined_result["review_status"] = (
                    ("有评论" if combined_result["has_reviews"] else "暂无评论")
                    if success else ("评论不完整" if combined_result["has_reviews"] else "评论抓取失败")
                )
                
                return combined_result
            else:
                # 脚本执行失败 - 可能是浏览器启动失败、页面加载失败等
                error_msg = result.stderr[:500] if result.stderr else "未知错误"
                failed_result = {
                    **place_data,
                    "scrape_success": False,
                    "scrape_error_code": 1999,
                    "scrape_error_message": f"脚本执行失败: {error_msg}",
                    "business_info": {},
                    "reviews_count": 0,
                    "reviews": [],
                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "retry_attempt": kwargs.get("retry_attempt", 0),
                    "has_reviews": None,
                    "review_status": "抓取失败",
                    "final_success": False
                }
                return failed_result
                
        except subprocess.TimeoutExpired:
            # 超时异常 - 网络慢或页面加载时间过长，这种情况可以重试
            timeout_result = {
                **place_data,
                "scrape_success": False,
                "scrape_error_code": 1009,
                "scrape_error_message": "爬取超时",
                "business_info": {},
                "reviews_count": 0,
                "reviews": [],
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "retry_attempt": kwargs.get("retry_attempt", 0),
                "has_reviews": None,
                "review_status": "超时失败",
                "final_success": False
            }
            return timeout_result
        except Exception as e:
            # 其他未预期的异常
            exception_result = {
                **place_data,
                "scrape_success": False,
                "scrape_error_code": 1999,
                "scrape_error_message": f"执行异常: {str(e)}",
                "business_info": {},
                "reviews_count": 0,
                "reviews": [],
                "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "retry_attempt": kwargs.get("retry_attempt", 0),
                "has_reviews": None,
                "review_status": "执行异常",
                "final_success": False
            }
            return exception_result
    
    def _cleanup_csv_file(self, result: Dict[str, Any], business_name: str):
        """
        清理main.py生成的CSV文件
        
        在JSON文件成功保存后，删除对应的CSV文件以保持目录整洁
        尝试多种方式确定可能的CSV文件名
        
        Args:
            result: 处理结果字典
            business_name: 从business_info获取的商户名称
        """
        import re
        
        # 收集可能的商户名称
        possible_names = []
        place_id = result.get("place_id", "")
        maps_url = result.get("Maps_url", "")
        
        self.logger.debug(f"开始清理CSV文件，place_id: {place_id}")
        
        # 1. 从business_info获取的名称
        if business_name:
            possible_names.append(business_name)
            self.logger.debug(f"添加商户名称: {business_name}")
        
        # 2. 检查现有CSV文件，看是否有匹配的place_id
        if place_id and maps_url:
            # 从URL中提取cid
            cid_match = re.search(r'cid=(\d+)', maps_url)
            if cid_match:
                cid = cid_match.group(1)
                self.logger.debug(f"提取到CID: {cid}")
                
                # 遍历输出目录中的所有CSV文件
                for csv_file in self.output_base_dir.glob("*.csv"):
                    try:
                        # 检查CSV文件是否包含这个cid
                        # 🔥 改进编码处理，尝试多种编码方式
                        encodings_to_try = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin-1']
                        content = None
                        
                        for encoding in encodings_to_try:
                            try:
                                with open(csv_file, 'r', encoding=encoding, errors='ignore') as f:
                                    content = f.read(500)  # 读取前500字符
                                    break
                            except (UnicodeDecodeError, UnicodeError):
                                continue
                        
                        if content and cid in content:
                            csv_name = csv_file.stem  # 文件名（不含扩展名）
                            possible_names.append(csv_name)
                            self.logger.debug(f"通过CID匹配到CSV文件: {csv_name}")
                            break
                    except Exception as e:
                        self.logger.debug(f"读取CSV文件 {csv_file.name} 失败: {e}")
                        continue
        
        # 3. 尝试清理所有可能的CSV文件
        cleaned = False
        for name in possible_names:
            if name:
                try:
                    # 复制main.py中的文件名生成逻辑
                    safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
                    csv_filename = f"{safe_name}.csv"
                    csv_file_path = self.output_base_dir / csv_filename
                    
                    self.logger.debug(f"尝试清理CSV文件: {csv_filename}")
                    
                    # 检查CSV文件是否存在并删除
                    if csv_file_path.exists():
                        try:
                            csv_file_path.unlink()  # 删除文件
                            self.logger.debug(f"已清理CSV文件: {csv_filename}")
                            cleaned = True
                            return  # 成功清理一个就够了
                        except Exception as e:
                            self.logger.warning(f"清理CSV文件失败 {csv_filename}: {e}")
                    else:
                        self.logger.debug(f"CSV文件不存在: {csv_filename}")
                    
                except Exception as e:
                    self.logger.debug(f"CSV文件清理过程出错 {name}: {e}")
                    continue
        
        if not cleaned:
            self.logger.debug(f"未找到需要清理的CSV文件，place_id: {place_id}")
    
    def save_result(self, result: Dict[str, Any]):
        """
        保存单个结果到独立的JSON文件
        
        为每个地点创建独立的JSON文件，避免大文件问题，支持高并发
        同时清理main.py生成的CSV文件，保持输出目录整洁
        🔥 增强版：确保立即刷新到磁盘，防止意外中断丢失数据
        
        Args:
            result: 包含地点信息和爬取结果的字典
        """
        parent_type = result.get("parent_type", "unknown")
        sub_type = result.get("sub_type", "unknown")
        place_id = result.get("place_id", "unknown")
        
        # 获取商户名称用于文件命名
        business_name = result.get("business_info", {}).get("name", "")
        
        # 获取输出目录
        output_dir = self.get_output_path(parent_type, sub_type)
        
        # 生成安全的文件名
        filename = self.generate_filename(place_id, business_name)
        output_file = output_dir / filename
        
        # 保存为独立的JSON文件（无需锁，因为每个文件都是独立的）
        try:
            with open(output_file, 'w', encoding='utf-8') as f:  # 🔥 明确使用UTF-8编码
                json.dump(result, f, ensure_ascii=False, indent=2)
                f.flush()  # 🔥 强制刷新缓冲区到磁盘
                import os
                os.fsync(f.fileno())  # 🔥 强制操作系统立即写入磁盘
            
            self.logger.debug(f"结果已实时保存到: {output_file}")
            
            # 🆕 清理对应的CSV文件（如果存在的话）
            # 尝试多种方式获取商户名称以便清理CSV文件
            self._cleanup_csv_file(result, business_name)
            
        except Exception as e:
            self.logger.error(f"保存文件失败 {output_file}: {e}")
            # 🔥 尝试备用保存方式
            try:
                backup_dir = self.output_base_dir / "backup_results"
                backup_dir.mkdir(exist_ok=True)
                backup_file = backup_dir / f"backup_{place_id}.json"
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                    f.flush()
                    import os
                    os.fsync(f.fileno())
                self.logger.warning(f"结果已保存到备用文件: {backup_file}")
            except Exception as backup_e:
                self.logger.error(f"备用保存也失败: {backup_e}")
    
    def log_result(self, result: Dict[str, Any], is_success: bool):
        """
        记录处理结果到相应的日志文件
        
        分别记录成功和失败的结果，便于后续分析和问题排查
        🔥 增强版：确保立即刷新到磁盘，防止意外中断丢失数据
        
        Args:
            result: 处理结果字典
            is_success: 是否成功
        """
        log_file = self.success_log_file if is_success else self.error_log_file
        
        # 提取关键信息用于日志记录
        log_record = {
            "place_id": result.get("place_id"),
            "Maps_url": result.get("Maps_url"),
            "parent_type": result.get("parent_type"),
            "sub_type": result.get("sub_type"),
            "scrape_success": result.get("scrape_success"),
            "scrape_error_code": result.get("scrape_error_code"),
            "scrape_error_message": result.get("scrape_error_message"),
            "reviews_count": result.get("reviews_count", 0),
            "business_name": result.get("business_info", {}).get("name"),
            "retry_attempt": result.get("retry_attempt", 0),
            "timestamp": result.get("scraped_at"),
            "final_success": result.get("final_success", False)  # 🆕 添加final_success状态
        }
        
        # 线程安全地写入日志文件，并立即刷新到磁盘
        with self.lock:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:  # 🔥 明确使用UTF-8编码
                    f.write(json.dumps(log_record, ensure_ascii=False) + '\n')
                    f.flush()  # 🔥 强制刷新缓冲区到磁盘
                    import os
                    os.fsync(f.fileno())  # 🔥 强制操作系统立即写入磁盘
                self.logger.debug(f"日志已实时保存: {result.get('place_id')} -> {log_file.name}")
            except Exception as e:
                self.logger.error(f"记录日志失败: {e}")
                # 🔥 尝试备用保存方式
                try:
                    backup_file = self.output_base_dir / f"backup_{log_file.name}"
                    with open(backup_file, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_record, ensure_ascii=False) + '\n')
                        f.flush()
                        import os
                        os.fsync(f.fileno())
                    self.logger.warning(f"日志已保存到备用文件: {backup_file}")
                except Exception as backup_e:
                    self.logger.error(f"备用保存也失败: {backup_e}")
    
    def process_batch(self, places: List[Dict[str, Any]], 
                     max_workers: int = 3, 
                     retry_failed: bool = False,
                     max_places: Optional[int] = None,
                     resume: bool = True, 
                     **kwargs):
        """
        批量处理地点数据
        
        Args:
            places: 地点数据列表
            max_workers: 最大并发数
            retry_failed: 是否重试失败的地点
            max_places: 每次最大处理数量（None表示无限制）
            resume: 是否启用断点恢复
            **kwargs: 传递给爬虫的参数
        """
        # 加载进度
        progress = self.load_progress()
        
        # 过滤需要处理的地点
        if resume:
            places_to_process, failed_place_ids = self.filter_places_to_process(places, retry_failed, max_places)
        else:
            limit = max_places or self.config['max_places']
            places_to_process = list(places[:limit] if limit else places)
            failed_place_ids = set()
            # Reset only this run's selected places; preserve other saved work.
            selected_ids = {place['place_id'] for place in places_to_process}
            for status in ('successful', 'failed', 'skipped'):
                progress[status] = [place_id for place_id in progress.get(status, [])
                                    if place_id not in selected_ids]
        
        if not places_to_process:
            self.logger.info("没有需要处理的地点")
            return
        
        # 初始化或更新进度信息
        if not resume or progress["total"] == 0:
            progress = {
                "total": len(places_to_process),
                "current_index": 0,
                "successful": progress.get("successful", []),
                "failed": progress.get("failed", []),
                "skipped": progress.get("skipped", []),
                "success_count": len(progress.get("successful", [])),
                "failed_count": len(progress.get("failed", [])),
                "skipped_count": len(progress.get("skipped", [])),
                "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "session_info": {
                    "retry_mode": retry_failed,
                    "max_places": max_places,
                    "max_workers": max_workers
                }
            }
        else:
            # 更新会话信息
            progress["session_info"].update({
                "retry_mode": retry_failed,
                "max_places": max_places,
                "max_workers": max_workers
            })
        
        # 统计信息
        stats = {
            "total": len(places_to_process),
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "start_time": time.time()
        }
        
        self.logger.info(f"开始处理 {len(places_to_process)} 个地点")
        self.logger.info(f"重试模式: {'开启' if retry_failed else '关闭'}")
        if max_places:
            self.logger.info(f"处理数量限制: {max_places}")
        
        # 使用进度条
        with tqdm(total=len(places_to_process), 
                 desc="批量爬取进度", unit="地点") as pbar:
            
            # 🔥 重新设计的并发处理逻辑
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                
                # 🔥 方法1：简化的并发处理 - 一次性提交所有任务
                if len(places_to_process) <= 500:  # 🔥 修改条件，500个以下都使用简单模式
                    
                    # 一次性提交所有任务
                    future_to_place = {}
                    for i, place_data in enumerate(places_to_process):
                        place_id = place_data["place_id"]
                        
                        # 设置重试参数
                        is_retry = place_id in failed_place_ids
                        task_kwargs = kwargs.copy()
                        task_kwargs["retry_attempt"] = 1 if is_retry else 0
                        
                        future = executor.submit(self.scrape_single_place, place_data, **task_kwargs)
                        future_to_place[future] = (i, place_data)
                    
                    # 处理完成的任务
                    for future in as_completed(future_to_place):
                        index, place_data = future_to_place[future]
                        place_id = place_data["place_id"]
                        
                        try:
                            result = future.result()
                            
                            # 立即保存结果
                            self.save_result(result)
                            
                            # 判断成功失败并记录
                            if result.get("final_success", False):
                                stats["success"] += 1
                                if place_id not in progress["successful"]:
                                    progress["successful"].append(place_id)
                                # 从失败列表中移除（如果是重试成功）
                                if place_id in progress["failed"]:
                                    progress["failed"].remove(place_id)
                                self.log_result(result, True)
                            else:
                                stats["failed"] += 1
                                if place_id not in progress["failed"]:
                                    progress["failed"].append(place_id)
                                self.log_result(result, False)
                            
                            stats["processed"] += 1
                            progress["current_index"] = index + 1
                            
                            # 更新进度条
                            pbar.update(1)
                            pbar.set_postfix({
                                "成功": stats["success"],
                                "失败": stats["failed"],
                                "成功率": f"{stats['success']/(stats['success']+stats['failed'])*100:.1f}%" if (stats['success']+stats['failed']) > 0 else "0%"
                            })
                            
                            # 定期保存进度
                            if stats["processed"] % self.config['auto_save_interval'] == 0:
                                progress["success_count"] = len(progress["successful"])
                                progress["failed_count"] = len(progress["failed"])
                                self.save_progress(progress)
                            
                        except Exception as e:
                            self.logger.error(f"处理地点 {place_id} 时出错: {e}")
                            stats["failed"] += 1
                            if place_id not in progress["failed"]:
                                progress["failed"].append(place_id)
                            
                            # 记录异常到日志
                            try:
                                exception_result = {
                                    **place_data,
                                    "scrape_success": False,
                                    "scrape_error_code": 1999,
                                    "scrape_error_message": f"处理异常: {str(e)}",
                                    "business_info": {},
                                    "reviews_count": 0,
                                    "reviews": [],
                                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "retry_attempt": 0,
                                    "has_reviews": None,
                                    "review_status": "处理异常",
                                    "final_success": False
                                }
                                self.log_result(exception_result, False)
                            except Exception as log_e:
                                self.logger.error(f"记录异常日志也失败了: {log_e}")
                            
                            stats["processed"] += 1
                            pbar.update(1)
                            pbar.set_postfix({
                                "成功": stats["success"],
                                "失败": stats["failed"],
                                "成功率": f"{stats['success']/(stats['success']+stats['failed'])*100:.1f}%" if (stats['success']+stats['failed']) > 0 else "0%"
                            })
                
                else:
                    # 🔥 方法2：流式处理 - 适合大批量数据
                    
                    # 使用队列管理任务
                    from collections import deque
                    remaining_places = deque(enumerate(places_to_process))
                    active_futures = {}
                    
                    # 提交初始批次任务
                    while len(active_futures) < max_workers and remaining_places:
                        index, place_data = remaining_places.popleft()
                        place_id = place_data["place_id"]
                        
                        is_retry = place_id in failed_place_ids
                        task_kwargs = kwargs.copy()
                        task_kwargs["retry_attempt"] = 1 if is_retry else 0
                        
                        future = executor.submit(self.scrape_single_place, place_data, **task_kwargs)
                        active_futures[future] = (index, place_data)
                    
                    # 持续处理直到所有任务完成
                    while active_futures:
                        # 等待至少一个任务完成
                        completed_futures = []
                        try:
                            # 🔥 修复：移除超时限制，等待任务自然完成
                            for future in as_completed(active_futures.keys()):
                                completed_futures.append(future)
                                break  # 只处理一个，保持流式处理
                        except Exception as e:
                            self.logger.error(f"等待任务完成时出错: {e}")
                            # 如果出错，等待所有剩余任务完成
                            for future in list(active_futures.keys()):
                                try:
                                    future.result(timeout=self.config.get('timeout', 300))
                                except Exception as future_e:
                                    self.logger.error(f"强制等待任务完成失败: {future_e}")
                            break
                        
                        # 处理完成的任务
                        for future in completed_futures:
                            index, place_data = active_futures.pop(future)
                            place_id = place_data["place_id"]
                            
                            try:
                                result = future.result()
                                
                                # 立即保存结果
                                self.save_result(result)
                                
                                # 判断成功失败并记录
                                if result.get("final_success", False):
                                    stats["success"] += 1
                                    if place_id not in progress["successful"]:
                                        progress["successful"].append(place_id)
                                    if place_id in progress["failed"]:
                                        progress["failed"].remove(place_id)
                                    self.log_result(result, True)
                                else:
                                    stats["failed"] += 1
                                    if place_id not in progress["failed"]:
                                        progress["failed"].append(place_id)
                                    self.log_result(result, False)
                                
                                stats["processed"] += 1
                                progress["current_index"] = index + 1
                                
                                # 更新进度条
                                pbar.update(1)
                                pbar.set_postfix({
                                    "成功": stats["success"],
                                    "失败": stats["failed"],
                                    "成功率": f"{stats['success']/(stats['success']+stats['failed'])*100:.1f}%" if (stats['success']+stats['failed']) > 0 else "0%"
                                })
                                
                                # 定期保存进度
                                if stats["processed"] % self.config['auto_save_interval'] == 0:
                                    progress["success_count"] = len(progress["successful"])
                                    progress["failed_count"] = len(progress["failed"])
                                    self.save_progress(progress)
                                
                            except Exception as e:
                                self.logger.error(f"处理地点 {place_id} 时出错: {e}")
                                stats["failed"] += 1
                                if place_id not in progress["failed"]:
                                    progress["failed"].append(place_id)
                                
                                # 记录异常到日志
                                try:
                                    exception_result = {
                                        **place_data,
                                        "scrape_success": False,
                                        "scrape_error_code": 1999,
                                        "scrape_error_message": f"处理异常: {str(e)}",
                                        "business_info": {},
                                        "reviews_count": 0,
                                        "reviews": [],
                                        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "retry_attempt": 0,
                                        "has_reviews": None,
                                        "review_status": "处理异常",
                                        "final_success": False
                                    }
                                    self.log_result(exception_result, False)
                                except Exception as log_e:
                                    self.logger.error(f"记录异常日志也失败了: {log_e}")
                                
                                stats["processed"] += 1
                                pbar.update(1)
                                pbar.set_postfix({
                                    "成功": stats["success"],
                                    "失败": stats["failed"],
                                    "成功率": f"{stats['success']/(stats['success']+stats['failed'])*100:.1f}%" if (stats['success']+stats['failed']) > 0 else "0%"
                                })
                        
                        # 提交新任务以保持并发数
                        while len(active_futures) < max_workers and remaining_places:
                            index, place_data = remaining_places.popleft()
                            place_id = place_data["place_id"]
                            
                            is_retry = place_id in failed_place_ids
                            task_kwargs = kwargs.copy()
                            task_kwargs["retry_attempt"] = 1 if is_retry else 0
                            
                            future = executor.submit(self.scrape_single_place, place_data, **task_kwargs)
                            active_futures[future] = (index, place_data)
        
        # 保存最终进度
        self.save_progress(progress)
        
        # 输出最终统计
        duration = time.time() - stats["start_time"]
        total_successful = len(progress["successful"])
        total_failed = len(progress["failed"])
        total_processed = total_successful + total_failed + len(progress["skipped"])
        
        self.logger.info(f"""
========================================
本次处理完成！
========================================
本次处理地点: {stats['total']}
本次成功: {stats['success']}
本次失败: {stats['failed']}
本次跳过: {stats['skipped']}
本次成功率: {stats['success']/(stats['success']+stats['failed'])*100:.2f}% (如果有处理的话)

累计统计:
累计成功: {total_successful}
累计失败: {total_failed}  
累计处理: {total_processed}
累计成功率: {total_successful/(total_successful+total_failed)*100:.2f}% (如果有处理的话)

性能统计:
总耗时: {duration/3600:.2f} 小时
平均速度: {stats['processed']/duration*60:.1f} 地点/分钟 (如果有处理的话)
========================================
        """)
    
    def generate_summary_report(self):
        """生成汇总报告"""
        summary = {
            "total_places": 0,
            "successful_scrapes": 0,
            "failed_scrapes": 0,
            "by_type": {},
            "error_statistics": {},
            "review_statistics": {                    # 🆕 评论状态统计
                "has_reviews": 0,                     # 有评论的地点数
                "no_reviews": 0,                      # 无评论的地点数
                "no_review_function": 0,              # 无评论功能的地点数
                "failed_scrapes": 0,                  # 抓取失败的地点数
                "total_reviews_collected": 0          # 收集到的总评论数
            },
            "progress_info": self.load_progress(),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 遍历所有输出目录
        for parent_dir in self.output_base_dir.iterdir():
            if not parent_dir.is_dir() or parent_dir.name in ['progress.json', 'errors.jsonl', 'success.jsonl', 'batch_scraper.log']:
                continue
                
            parent_type = parent_dir.name
            if parent_type not in summary["by_type"]:
                summary["by_type"][parent_type] = {}
            
            for sub_dir in parent_dir.iterdir():
                if not sub_dir.is_dir():
                    continue
                    
                sub_type = sub_dir.name
                
                # 统计该类型下的所有JSON文件
                type_stats = {"total": 0, "success": 0, "failed": 0, "reviews_total": 0}
                
                # 遍历所有JSON文件
                for json_file in sub_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            result = json.load(f)
                            
                        type_stats["total"] += 1
                        
                        # 🔥 关键修改：使用final_success而不是scrape_success进行真正的成功判断
                        if result.get("final_success", False):
                            type_stats["success"] += 1
                            type_stats["reviews_total"] += result.get("reviews_count", 0)
                            
                            # 🆕 统计评论状态
                            review_status = result.get("review_status", "")
                            if result.get("has_reviews"):
                                summary["review_statistics"]["has_reviews"] += 1
                                summary["review_statistics"]["total_reviews_collected"] += result.get("reviews_count", 0)
                            elif review_status == "无评论功能":
                                summary["review_statistics"]["no_review_function"] += 1
                            elif review_status == "暂无评论":
                                summary["review_statistics"]["no_reviews"] += 1
                        else:
                            type_stats["failed"] += 1
                            summary["review_statistics"]["failed_scrapes"] += 1
                            error_code = result.get("scrape_error_code", "unknown")
                            summary["error_statistics"][error_code] = summary["error_statistics"].get(error_code, 0) + 1
                                
                    except (json.JSONDecodeError, FileNotFoundError) as e:
                        self.logger.warning(f"读取文件失败 {json_file}: {e}")
                        continue
                
                if type_stats["total"] > 0:
                    summary["by_type"][parent_type][sub_type] = type_stats
                    summary["total_places"] += type_stats["total"]
                    summary["successful_scrapes"] += type_stats["success"]
                    summary["failed_scrapes"] += type_stats["failed"]
        
        # 保存汇总报告
        summary_file = self.output_base_dir / "summary_report.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"汇总报告已生成: {summary_file}")
        
        # 输出汇总信息到日志
        self.logger.info(f"""
文件结构汇总:
========================================
总地点数: {summary['total_places']}
成功处理: {summary['successful_scrapes']}
失败处理: {summary['failed_scrapes']}
成功率: {summary['successful_scrapes']/(summary['successful_scrapes']+summary['failed_scrapes'])*100:.2f}% (如果有处理的话)

评论统计:
有评论地点: {summary['review_statistics']['has_reviews']}
无评论地点: {summary['review_statistics']['no_reviews']}
无评论功能: {summary['review_statistics']['no_review_function']}
抓取失败: {summary['review_statistics']['failed_scrapes']}
总评论数: {summary['review_statistics']['total_reviews_collected']}

按类型分布:""")
        
        for parent_type, sub_types in summary["by_type"].items():
            self.logger.info(f"{parent_type}:")
            for sub_type, stats in sub_types.items():
                self.logger.info(f"  {sub_type}: {stats['success']}/{stats['total']} 成功，{stats['reviews_total']} 条评论")
        
        return summary

    def unattended_processing(self, places: List[Dict[str, Any]], **kwargs):
        """
        无人值守处理模式
        
        适合大规模数据的长时间自动处理，包含自动重试和持续监控
        支持无限运行模式（直到手动停止）
        
        Args:
            places: 地点数据列表
            **kwargs: 其他处理参数
        """
        max_rounds = self.config.get('max_continuous_rounds', 5)
        rest_time = self.config.get('rest_between_rounds', 300)
        auto_retry = self.config.get('auto_retry_failed', True)
        infinite_mode = self.config.get('infinite_mode', False)
        max_idle_rounds = self.config.get('max_idle_rounds', 3)
        checkpoint_interval = self.config.get('checkpoint_interval', 60) * 60  # 转换为秒
        
        self.logger.info(f"开始无人值守处理模式")
        if infinite_mode:
            self.logger.info(f"🔄 无限运行模式已启用 - 将持续运行直到手动停止或数据处理完成")
            self.logger.info(f"💡 使用 Ctrl+C 优雅停止")
        else:
            self.logger.info(f"最大处理轮数: {max_rounds}")
        self.logger.info(f"轮次间休息: {rest_time}秒")
        self.logger.info(f"自动重试失败: {auto_retry}")
        self.logger.info(f"最大空闲轮数: {max_idle_rounds}")
        
        round_num = 0
        idle_rounds = 0
        last_checkpoint = time.time()
        
        try:
            # 🔥 无限模式或指定轮数模式
            while infinite_mode or round_num < max_rounds:
                round_num += 1
                self.logger.info(f"\n=== 第 {round_num} 轮处理开始 ===")
                
                # 检查还有多少地点需要处理
                remaining_places = self.filter_places_to_process(
                    places, 
                    retry_failed=False, 
                    max_places=self.config.get('max_places')
                )
                
                if not remaining_places:
                    idle_rounds += 1
                    self.logger.info(f"无新地点需要处理（空闲轮数: {idle_rounds}/{max_idle_rounds}）")
                    
                    if idle_rounds >= max_idle_rounds:
                        self.logger.info("达到最大空闲轮数，所有地点已处理完成！")
                        break
                    
                    # 空闲时休息更短时间
                    idle_rest_time = min(rest_time, 60)
                    self.logger.info(f"等待 {idle_rest_time} 秒后继续检查...")
                    time.sleep(idle_rest_time)
                    continue
                else:
                    # 有新地点处理，重置空闲计数
                    idle_rounds = 0
                
                # 处理当前批次
                try:
                    batch_start_time = time.time()
                    
                    self.process_batch(
                        places,
                        max_workers=self.config['max_workers'],
                        retry_failed=False,
                        max_places=self.config.get('max_places'),
                        resume=True,
                        **kwargs
                    )
                    
                    batch_duration = time.time() - batch_start_time
                    
                    # 处理完成后，检查是否需要自动重试失败地点
                    if auto_retry:
                        progress = self.load_progress()
                        failed_count = len(progress.get('failed', []))
                        
                        if failed_count > 0:
                            self.logger.info(f"开始自动重试 {failed_count} 个失败地点")
                            # 创建重试参数，避免参数冲突
                            retry_kwargs = kwargs.copy()
                            retry_kwargs.update({
                                'max_retries': self.config['max_retries'],
                                'timeout': self.config['timeout'] * 1.5,
                            })
                            self.process_batch(
                                places,
                                max_workers=max(1, self.config['max_workers'] - 1),  # 降低并发
                                retry_failed=True,
                                resume=True,
                                **retry_kwargs
                            )
                    
                    # 生成当前轮次报告
                    summary = self.generate_summary_report()
                    success_rate = summary['successful_scrapes'] / (summary['successful_scrapes'] + summary['failed_scrapes']) * 100 if (summary['successful_scrapes'] + summary['failed_scrapes']) > 0 else 0
                    
                    self.logger.info(f"第 {round_num} 轮完成，成功率: {success_rate:.1f}%，耗时: {batch_duration/60:.1f}分钟")
                    
                    # 检查点信息输出
                    current_time = time.time()
                    if current_time - last_checkpoint >= checkpoint_interval:
                        self.logger.info(f"""
📊 检查点报告 (第 {round_num} 轮):
========================================
总成功: {summary['successful_scrapes']}
总失败: {summary['failed_scrapes']}
当前成功率: {success_rate:.1f}%
总评论数: {summary['review_statistics']['total_reviews_collected']}
运行模式: {'无限模式' if infinite_mode else f'{max_rounds}轮模式'}
空闲轮数: {idle_rounds}/{max_idle_rounds}
========================================
                        """)
                        last_checkpoint = current_time
                    
                    # 检查是否还有失败需要处理（仅在非无限模式下检查）
                    if not infinite_mode:
                        progress = self.load_progress()
                        remaining_failed = len(progress.get('failed', []))
                        
                        if remaining_failed == 0:
                            self.logger.info("所有地点处理成功，无人值守模式完成！")
                            break
                    
                    # 轮次间休息（除了最后一轮或无限模式）
                    if (not infinite_mode and round_num < max_rounds) or infinite_mode:
                        self.logger.info(f"第 {round_num} 轮完成，休息 {rest_time} 秒后继续...")
                        time.sleep(rest_time)
                        
                except Exception as e:
                    self.logger.error(f"第 {round_num} 轮处理出错: {e}")
                    if infinite_mode or round_num < max_rounds:
                        self.logger.info(f"休息 {rest_time} 秒后重试...")
                        time.sleep(rest_time)
                    else:
                        self.logger.error("已达到最大轮数，无人值守模式结束")
                        break
                
        except KeyboardInterrupt:
            self.logger.info("\n🛑 接收到中断信号，正在优雅停止...")
            self.logger.info(f"✅ 已完成 {round_num} 轮处理")
        
        # 生成最终报告
        final_summary = self.generate_summary_report()
        self.logger.info(f"""
========================================
无人值守处理完成！
========================================
运行模式: {'无限模式' if infinite_mode else f'{max_rounds}轮模式'}
实际处理轮数: {round_num}
最终成功: {final_summary['successful_scrapes']}
最终失败: {final_summary['failed_scrapes']}
最终成功率: {final_summary['successful_scrapes']/(final_summary['successful_scrapes']+final_summary['failed_scrapes'])*100:.2f}% (如果有处理的话)
总评论数: {final_summary['review_statistics']['total_reviews_collected']}
========================================
        """)
        
        return final_summary

def main():
    parser = argparse.ArgumentParser(description='大规模批量Google Maps数据爬取')
    parser.add_argument('input_file', nargs='?', help='JSONL格式的输入文件')
    parser.add_argument('--output-dir', default='batch_output', help='输出目录')
    parser.add_argument('--max-workers', type=int, help='最大并发数')
    parser.add_argument('--max-retries', type=int, help='最大重试次数')
    parser.add_argument('--timeout', type=int, help='单个地点超时时间(秒)')
    resume_mode = parser.add_mutually_exclusive_group()
    resume_mode.add_argument('--resume', dest='resume', action='store_true', help='从上次中断处继续（默认）')
    resume_mode.add_argument('--no-resume', dest='resume', action='store_false', help='不从上次中断处继续')
    parser.set_defaults(resume=True)
    parser.add_argument('--max-scrolls', type=int, default=30, help='每个地点的评论滚动次数上限')
    parser.add_argument('--scroll-wait', type=float, default=3, help='每次滚动等待新评论的秒数')
    parser.add_argument('--retry-failed', action='store_true', help='重试失败的地点')
    parser.add_argument('--max-places', type=int, help='每次最大处理地点数量')
    parser.add_argument('--verbose', action='store_true', help='详细日志')
    parser.add_argument('--generate-report', action='store_true', help='只生成汇总报告')
    parser.add_argument('--show-status', action='store_true', help='显示当前处理状态')
    
    # 🆕 无人值守模式参数
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--test', action='store_true', help='测试配置：1 个并发，最多 5 个地点')
    modes.add_argument('--production', action='store_true', help='生产配置')
    modes.add_argument('--unattended', action='store_true', help='无人值守模式（适合大规模数据长时间处理）')
    modes.add_argument('--infinite', action='store_true', help='🔄 无限运行模式（持续运行直到手动停止）')
    modes.add_argument('--fast', action='store_true', help='⚡ 快速模式（适合测试或小规模数据）')
    parser.add_argument('--max-rounds', type=int, help='无人值守模式的最大处理轮数')
    parser.add_argument('--rest-time', type=int, help='轮次间休息时间（秒）')
    parser.add_argument('--checkpoint-interval', type=int, help='检查点间隔时间（分钟）')
    
    args = parser.parse_args()
    
    config = DEFAULT_CONFIG.copy()
    for enabled, preset in (
        (args.test, TEST_CONFIG), (args.production, PRODUCTION_CONFIG),
        (args.infinite, INFINITE_CONFIG), (args.fast, FAST_CONFIG),
        (args.unattended, UNATTENDED_CONFIG),
    ):
        if enabled:
            config.update(preset)
    for key in ('max_places', 'max_workers', 'max_retries', 'timeout'):
        value = getattr(args, key)
        if value is not None:
            if value < 1:
                parser.error('--' + key.replace('_', '-') + ' 必须大于 0')
            config[key] = value
    for argument, key in (('max_rounds', 'max_continuous_rounds'),
                          ('rest_time', 'rest_between_rounds'),
                          ('checkpoint_interval', 'checkpoint_interval')):
        value = getattr(args, argument)
        if value is not None:
            config[key] = value
    if args.max_scrolls < 1 or args.scroll_wait <= 0:
        parser.error('--max-scrolls 和 --scroll-wait 必须大于 0')

    scraper = BatchGoogleMapsScraper(output_base_dir=args.output_dir, config=config)
    
    if args.generate_report:
        # 只生成报告
        summary = scraper.generate_summary_report()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    
    if args.show_status:
        # 显示状态
        progress = scraper.load_progress()
        print(json.dumps(progress, ensure_ascii=False, indent=2))
        return
    
    if not args.input_file:
        parser.print_help()
        return
    
    # 加载输入数据
    places = scraper.load_jsonl_input(args.input_file)
    if not places:
        print("没有加载到有效的地点数据")
        return
    
    # 🆕 根据模式选择处理方式
    if args.infinite or args.unattended:
        # 无人值守模式（包括无限模式）
        mode_name = "无限运行" if args.infinite else "无人值守"
        print(f"开始{mode_name}处理 {len(places)} 个地点...")
        if args.infinite:
            print("💡 使用 Ctrl+C 优雅停止")
        else:
            max_rounds = config.get('max_continuous_rounds', 5) if config else 5
            print(f"最多运行 {max_rounds} 轮")
        
        scraper.unattended_processing(
            places,
            max_retries=config["max_retries"],
            timeout=config["timeout"],
            max_scrolls=args.max_scrolls,
            scroll_wait=args.scroll_wait,
            verbose=args.verbose
        )
    else:
        # 标准批量处理模式
        # 🔥 使用配置中的max_workers，如果用户没有指定的话
        max_workers = config["max_workers"]
        scraper.process_batch(
            places,
            max_workers=max_workers,
            retry_failed=args.retry_failed,
            max_places=config["max_places"],
            resume=args.resume,
            max_retries=config["max_retries"],
            timeout=config["timeout"],
            max_scrolls=args.max_scrolls,
            scroll_wait=args.scroll_wait,
            verbose=args.verbose
        )
    
    # 生成汇总报告
    scraper.generate_summary_report()

if __name__ == "__main__":
    main()
