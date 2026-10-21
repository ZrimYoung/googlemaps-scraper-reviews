#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重试失败抓取脚本
=================

专门用于重新抓取之前失败的记录的脚本。

功能特性：
- 自动扫描batch_output目录中所有失败的JSON文件
- 提取失败记录的信息并重新组织为输入格式
- 支持按错误代码筛选重试（如只重试超时错误）
- 支持限制重试数量
- 详细的进度报告和统计信息
- 可选择性地更新重试次数

使用方法：
1. 重试所有失败记录：
   python retry_failed_scrapes.py

2. 只重试超时错误（错误代码1002）：
   python retry_failed_scrapes.py --error-codes 1002

3. 限制重试数量（测试）：
   python retry_failed_scrapes.py --max-retry 10

4. 详细模式：
   python retry_failed_scrapes.py --verbose
"""

import json
import os
import sys
import argparse
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Any, Set, Optional
from datetime import datetime
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from tqdm import tqdm

# 引入现有的批量处理器
try:
    from batch_scraper import BatchGoogleMapsScraper, DEFAULT_CONFIG, TEST_CONFIG
except ImportError:
    print("错误：无法导入batch_scraper模块。请确保batch_scraper.py在同一目录下。")
    sys.exit(1)

class FailedScrapeRetryProcessor:
    """失败抓取重试处理器"""
    
    def __init__(self, output_dir: str = "batch_output", config: Optional[Dict] = None):
        """
        初始化重试处理器
        
        Args:
            output_dir: 输出目录路径
            config: 配置参数字典
        """
        self.output_dir = Path(output_dir)
        self.config = config or DEFAULT_CONFIG.copy()
        
        # 设置日志
        self.setup_logging()
        
        # 创建批量处理器实例
        self.batch_processor = BatchGoogleMapsScraper(
            output_base_dir=str(self.output_dir),
            config=self.config
        )
        
        self.logger.info(f"失败抓取重试处理器已初始化")
        self.logger.info(f"输出目录: {self.output_dir}")
        
    def setup_logging(self):
        """设置日志系统"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def scan_failed_files(self) -> List[Dict[str, Any]]:
        """
        扫描所有失败的JSON文件
        
        Returns:
            失败记录列表
        """
        failed_records = []
        
        if not self.output_dir.exists():
            self.logger.warning(f"输出目录不存在: {self.output_dir}")
            return failed_records
        
        self.logger.info("开始扫描失败的抓取记录...")
        
        # 递归扫描所有JSON文件
        json_files = list(self.output_dir.rglob("*.json"))
        
        # 排除progress.json等系统文件
        json_files = [f for f in json_files if f.name not in ['progress.json']]
        
        self.logger.info(f"找到 {len(json_files)} 个JSON文件，正在检查失败记录...")
        
        failed_count = 0
        for json_file in tqdm(json_files, desc="扫描文件"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 检查是否为失败记录
                if ('place_id' in data and (
                    not data.get('final_success', data.get('scrape_success', False))
                    or data.get('scrape_error_code', 0) != 0
                    or data.get('reviews_complete') is False
                )):
                    # 提取路径信息来确定parent_type和sub_type
                    relative_path = json_file.relative_to(self.output_dir)
                    path_parts = relative_path.parts
                    
                    if len(path_parts) >= 2:
                        parent_type = path_parts[0]
                        sub_type = path_parts[1]
                        
                        failed_record = {
                            'place_id': data.get('place_id'),
                            'Maps_url': data.get('Maps_url'),
                            'parent_type': parent_type,
                            'sub_type': sub_type,
                            'grid_id': data.get('grid_id', ''),
                            'error_code': data.get('scrape_error_code'),
                            'error_message': data.get('scrape_error_message', ''),
                            'retry_attempt': data.get('retry_attempt', 0),
                            'scraped_at': data.get('scraped_at'),
                            'file_path': str(json_file)
                        }
                        
                        # 确保必要字段存在
                        if failed_record['place_id'] and failed_record['Maps_url']:
                            failed_records.append(failed_record)
                            failed_count += 1
                        else:
                            self.logger.warning(f"跳过格式不完整的失败记录: {json_file}")
                    else:
                        self.logger.warning(f"无法确定类型的文件路径: {json_file}")
                        
            except json.JSONDecodeError as e:
                self.logger.warning(f"JSON解析失败: {json_file} - {e}")
            except Exception as e:
                self.logger.warning(f"处理文件时出错: {json_file} - {e}")
        
        self.logger.info(f"扫描完成，找到 {failed_count} 个失败记录")
        return failed_records
    
    def filter_by_error_codes(self, failed_records: List[Dict], error_codes: List[int]) -> List[Dict]:
        """
        按错误代码筛选失败记录
        
        Args:
            failed_records: 失败记录列表
            error_codes: 要重试的错误代码列表
            
        Returns:
            筛选后的失败记录列表
        """
        if not error_codes:
            return failed_records
        
        filtered = [record for record in failed_records 
                   if record.get('error_code') in error_codes]
        
        self.logger.info(f"按错误代码筛选: {len(failed_records)} -> {len(filtered)} 条记录")
        self.logger.info(f"目标错误代码: {error_codes}")
        
        return filtered
    
    def generate_retry_statistics(self, failed_records: List[Dict]) -> Dict[str, Any]:
        """
        生成重试统计信息
        
        Args:
            failed_records: 失败记录列表
            
        Returns:
            统计信息字典
        """
        stats = {
            'total_failed': len(failed_records),
            'by_error_code': {},
            'by_parent_type': {},
            'by_sub_type': {},
            'retry_attempts': {}
        }
        
        for record in failed_records:
            # 按错误代码统计
            error_code = record.get('error_code', 'unknown')
            stats['by_error_code'][error_code] = stats['by_error_code'].get(error_code, 0) + 1
            
            # 按父类型统计
            parent_type = record.get('parent_type', 'unknown')
            stats['by_parent_type'][parent_type] = stats['by_parent_type'].get(parent_type, 0) + 1
            
            # 按子类型统计
            sub_type = record.get('sub_type', 'unknown')
            stats['by_sub_type'][sub_type] = stats['by_sub_type'].get(sub_type, 0) + 1
            
            # 按重试次数统计
            retry_count = record.get('retry_attempt', 0)
            stats['retry_attempts'][retry_count] = stats['retry_attempts'].get(retry_count, 0) + 1
        
        return stats
    
    def print_statistics(self, stats: Dict[str, Any]):
        """打印统计信息"""
        self.logger.info("\n" + "="*60)
        self.logger.info("失败记录统计信息")
        self.logger.info("="*60)
        
        self.logger.info(f"失败记录总数: {stats['total_failed']}")
        
        self.logger.info("\n按错误代码分布:")
        for error_code, count in sorted(stats['by_error_code'].items()):
            error_name = self.get_error_name(error_code)
            self.logger.info(f"  {error_code} ({error_name}): {count} 条")
        
        self.logger.info("\n按父类型分布:")
        for parent_type, count in sorted(stats['by_parent_type'].items()):
            self.logger.info(f"  {parent_type}: {count} 条")
        
        self.logger.info("\n按重试次数分布:")
        for retry_count, count in sorted(stats['retry_attempts'].items()):
            self.logger.info(f"  重试 {retry_count} 次: {count} 条")
        
        self.logger.info("="*60)
    
    def print_retry_details(self, failed_records: List[Dict], show_limit: int = 20):
        """
        打印详细的重试记录信息
        
        Args:
            failed_records: 失败记录列表
            show_limit: 显示记录数量限制，避免输出过多
        """
        self.logger.info("\n" + "="*80)
        self.logger.info("将要重试的记录详情")
        self.logger.info("="*80)
        
        if not failed_records:
            self.logger.info("没有记录需要重试")
            return
        
        # 按错误代码分组显示
        error_groups = {}
        for record in failed_records:
            error_code = record.get('error_code', 'unknown')
            if error_code not in error_groups:
                error_groups[error_code] = []
            error_groups[error_code].append(record)
        
        total_shown = 0
        for error_code, records in sorted(error_groups.items()):
            error_name = self.get_error_name(error_code)
            self.logger.info(f"\n错误代码 {error_code} ({error_name}) - {len(records)} 条记录:")
            
            for i, record in enumerate(records[:min(show_limit - total_shown, len(records))]):
                place_id = record['place_id']
                parent_type = record['parent_type']
                sub_type = record['sub_type']
                retry_count = record.get('retry_attempt', 0)
                scraped_at = record.get('scraped_at', 'Unknown')
                
                # 尝试提取商户名称（如果有的话）
                business_name = self.extract_business_name_from_path(record['file_path'])
                name_display = f" ({business_name})" if business_name else ""
                
                self.logger.info(f"  {i+1:2d}. {place_id}{name_display}")
                self.logger.info(f"      类型: {parent_type}/{sub_type}")
                self.logger.info(f"      重试次数: {retry_count}, 上次抓取: {scraped_at}")
                
                total_shown += 1
                if total_shown >= show_limit:
                    break
            
            if total_shown >= show_limit:
                remaining = len(failed_records) - total_shown
                if remaining > 0:
                    self.logger.info(f"\n  ... 还有 {remaining} 条记录未显示")
                break
        
        self.logger.info("\n" + "="*80)
        self.logger.info("文件处理说明:")
        self.logger.info("• 原失败文件将备份到 backup/retry_时间戳/ 目录")
        self.logger.info("• backup目录中保持与原output相同的目录结构")
        self.logger.info("• 重试成功的结果将覆盖原文件位置")
        self.logger.info("• 重试失败的记录将更新错误信息和重试次数")
        self.logger.info("="*80)
    
    def extract_business_name_from_path(self, file_path: str) -> Optional[str]:
        """
        从文件路径中提取商户名称
        
        Args:
            file_path: 文件路径
            
        Returns:
            商户名称（如果能提取到）
        """
        try:
            file_name = Path(file_path).stem  # 获取不含扩展名的文件名
            # 文件名格式通常是 place_id_business_name.json
            if '_' in file_name:
                parts = file_name.split('_', 1)  # 只分割第一个下划线
                if len(parts) > 1:
                    return parts[1].replace('_', ' ')  # 将下划线替换回空格
        except:
            pass
        return None
    
    def confirm_retry_operation(self, failed_records: List[Dict], show_details: bool = True) -> bool:
        """
        确认重试操作
        
        Args:
            failed_records: 失败记录列表
            show_details: 是否显示详细信息
            
        Returns:
            用户是否确认继续
        """
        if show_details:
            self.print_retry_details(failed_records)
        
        print(f"\n准备重试 {len(failed_records)} 条失败记录")
        print("注意：这个操作将：")
        print("• 将当前失败文件备份到 backup/retry_时间戳/ 目录")
        print("• 重新抓取这些页面的数据")
        print("• 用新结果覆盖原文件（如果重试成功）")
        print("• 更新错误信息（如果重试仍然失败）")
        
        # 🔥 新增：显示将要使用的配置
        print(f"\n使用的配置参数:")
        print(f"• 并发线程数: {self.config.get('max_workers', 3)}")
        print(f"• 单页超时时间: {self.config.get('timeout', 300)} 秒")
        print(f"• 单页重试次数: {self.config.get('max_retries', 3)}")
        print(f"• 详细日志: {'开启' if self.config.get('verbose_logging', False) else '关闭'}")
        
        while True:
            response = input(f"\n确认继续重试操作？[y/N]: ").strip().lower()
            if response in ['y', 'yes', '是', '确认']:
                return True
            elif response in ['n', 'no', '否', '取消', '']:
                return False
            else:
                print("请输入 y(是) 或 n(否)")
    
    def get_error_name(self, error_code) -> str:
        """获取错误代码对应的名称"""
        error_names = {
            1001: "浏览器初始化失败",
            1002: "页面加载失败/超时",
            1003: "商户信息提取失败",
            1004: "评论按钮未找到",
            1005: "评论滚动失败",
            1006: "评论提取失败",
            1007: "坐标提取失败",
            1008: "CSV保存失败",
            1009: "网络超时",
            1010: "元素未找到",
            1999: "未预期错误"
        }
        return error_names.get(error_code, "未知错误")
    
    def fix_progress_file(self, failed_records: List[Dict]):
        """
        修复进度文件中失败记录的状态
        
        确保失败的place_id在progress.json中被正确标记为失败状态
        
        Args:
            failed_records: 失败记录列表
        """
        if not failed_records:
            return
            
        # 获取所有失败的place_id
        failed_place_ids = [record['place_id'] for record in failed_records]
        
        self.logger.info(f"正在修复进度文件中 {len(failed_place_ids)} 个失败记录的状态...")
        
        # 加载当前进度
        progress = self.batch_processor.load_progress()
        
        # 确保failed列表存在
        if 'failed' not in progress:
            progress['failed'] = []
        if 'successful' not in progress:
            progress['successful'] = []
        if 'skipped' not in progress:
            progress['skipped'] = []
        
        # 将失败的place_id从successful和skipped中移除，并添加到failed中
        successful_set = set(progress['successful'])
        skipped_set = set(progress['skipped'])
        failed_set = set(progress['failed'])
        
        moved_count = 0
        for place_id in failed_place_ids:
            # 从成功列表中移除（如果存在）
            if place_id in successful_set:
                successful_set.remove(place_id)
                moved_count += 1
                
            # 从跳过列表中移除（如果存在）
            if place_id in skipped_set:
                skipped_set.remove(place_id)
                moved_count += 1
                
            # 添加到失败列表中
            failed_set.add(place_id)
        
        # 更新进度字典
        progress['successful'] = list(successful_set)
        progress['skipped'] = list(skipped_set)
        progress['failed'] = list(failed_set)
        
        # 保存更新后的进度
        self.batch_processor.save_progress(progress)
        
        self.logger.info(f"已修复 {moved_count} 个记录的状态，{len(failed_set)} 个记录现在标记为失败")
        
        # 验证修复结果
        updated_progress = self.batch_processor.load_progress()
        self.logger.info(f"修复后进度统计: 成功 {len(updated_progress.get('successful', []))}, "
                        f"失败 {len(updated_progress.get('failed', []))}, "
                        f"跳过 {len(updated_progress.get('skipped', []))}")
    
    def convert_to_input_format(self, failed_records: List[Dict]) -> List[Dict]:
        """
        将失败记录转换为输入格式
        
        Args:
            failed_records: 失败记录列表
            
        Returns:
            转换后的输入格式列表
        """
        input_format = []
        
        for record in failed_records:
            input_record = {
                'place_id': record['place_id'],
                'Maps_url': record['Maps_url'],
                'parent_type': record['parent_type'],
                'sub_type': record['sub_type'],
                'grid_id': record.get('grid_id', '')
            }
            input_format.append(input_record)
        
        return input_format
    
    def backup_failed_files(self, failed_records: List[Dict], backup_suffix: Optional[str] = None):
        """
        备份失败的文件到backup目录
        
        Args:
            failed_records: 失败记录列表
            backup_suffix: 备份后缀，默认使用时间戳
        """
        if backup_suffix is None:
            backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 创建backup根目录（与batch_output平行）
        backup_root = self.output_dir.parent / "backup" / f"retry_{backup_suffix}"
        backup_root.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"正在备份 {len(failed_records)} 个失败文件到: {backup_root}")
        
        backup_count = 0
        for record in failed_records:
            try:
                original_file = Path(record['file_path'])
                if original_file.exists():
                    # 计算相对于output_dir的路径
                    relative_path = original_file.relative_to(self.output_dir)
                    
                    # 在backup目录中创建相同的目录结构
                    backup_file = backup_root / relative_path
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 复制文件到backup目录（保持原文件不变）
                    shutil.copy2(original_file, backup_file)
                    backup_count += 1
                    
                    self.logger.debug(f"已备份: {relative_path}")
                    
            except Exception as e:
                self.logger.warning(f"备份文件失败: {record['file_path']} - {e}")
        
        self.logger.info(f"已备份 {backup_count} 个文件到: {backup_root}")
        self.logger.info(f"备份目录结构与原output目录保持一致")
        
        return backup_root
    
    def retry_failed_scrapes(self, 
                           failed_records: List[Dict],
                           max_workers: int = 3,
                           max_places: Optional[int] = None,
                           backup_files: bool = True,
                           update_retry_count: bool = True) -> Optional[Dict[str, Any]]:
        """
        重试失败的抓取
        
        Args:
            failed_records: 失败记录列表
            max_workers: 最大并发数
            max_places: 最大重试数量
            backup_files: 是否备份原失败文件
            update_retry_count: 是否更新重试次数
            
        Returns:
            重试结果统计，如果没有记录则返回None
        """
        if not failed_records:
            self.logger.warning("没有失败记录需要重试")
            return None
        
        # 限制重试数量
        if max_places and max_places > 0:
            failed_records = failed_records[:max_places]
            self.logger.info(f"限制重试数量为: {len(failed_records)} 条")
        
        # 🔥 关键修复：先修复进度文件中的失败记录状态
        self.fix_progress_file(failed_records)
        
        # 备份原失败文件
        if backup_files:
            self.backup_failed_files(failed_records)
        
        # 转换为输入格式
        retry_input = self.convert_to_input_format(failed_records)
        
        self.logger.info(f"开始重试 {len(retry_input)} 个失败记录...")
        self.logger.info(f"使用配置: max_workers={max_workers}, timeout={self.config.get('timeout', 300)}s")
        
        # 🔥 修复：更新批量处理器的配置
        self.batch_processor.config.update({
            'max_workers': max_workers,
            'timeout': self.config.get('timeout', 300),
            'max_retries': self.config.get('max_retries', 3)
        })
        
        try:
            result = self.batch_processor.process_batch(
                places=retry_input,
                max_workers=max_workers,  # 确保参数传递
                retry_failed=True,  # 关键：启用重试模式
                max_places=len(retry_input),
                resume=True,
                # 🔥 新增：传递额外的配置参数
                timeout=self.config.get('timeout', 300),
                max_retries=self.config.get('max_retries', 3),
                verbose=self.config.get('verbose_logging', False)
            )
            
            self.logger.info("重试处理完成")
            return result
            
        except Exception as e:
            self.logger.error(f"重试处理时出错: {e}")
            raise

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="重试失败的Google Maps抓取记录")
    
    parser.add_argument(
        "--output-dir",
        default="batch_output",
        help="输出目录路径 (默认: batch_output)"
    )
    
    parser.add_argument(
        "--error-codes",
        type=int,
        nargs='+',
        help="只重试指定错误代码的记录 (例如: --error-codes 1002 1009)"
    )
    
    parser.add_argument(
        "--max-retry",
        type=int,
        help="最大重试记录数量 (用于测试)"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="最大并发线程数 (默认: 3)"
    )
    
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="不备份原失败文件"
    )
    
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="只显示统计信息，不执行重试"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="启用详细日志"
    )
    
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="使用测试模式配置"
    )
    
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="不显示详细的重试记录信息"
    )
    
    parser.add_argument(
        "--show-limit",
        type=int,
        default=20,
        help="显示详细信息时的记录数量限制 (默认: 20)"
    )
    
    parser.add_argument(
        "--fix-progress-only",
        action="store_true",
        help="只修复进度文件中失败记录的状态，不执行重试"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        help="单个页面的超时时间（秒），默认使用配置文件中的值"
    )
    
    parser.add_argument(
        "--max-retries",
        type=int,
        help="单个页面的最大重试次数，默认使用配置文件中的值"
    )
    
    args = parser.parse_args()
    
    # 选择配置
    config = TEST_CONFIG if args.test_mode else DEFAULT_CONFIG.copy()
    config['verbose_logging'] = args.verbose
    
    # 🔥 新增：应用命令行参数覆盖配置
    if args.timeout:
        config['timeout'] = args.timeout
    if args.max_retries:
        config['max_retries'] = args.max_retries
    
    try:
        # 创建重试处理器
        processor = FailedScrapeRetryProcessor(
            output_dir=args.output_dir,
            config=config
        )
        
        # 扫描失败记录
        failed_records = processor.scan_failed_files()
        
        if not failed_records:
            processor.logger.info("没有找到失败记录")
            return
        
        # 按错误代码筛选
        if args.error_codes:
            failed_records = processor.filter_by_error_codes(failed_records, args.error_codes)
            if not failed_records:
                processor.logger.info("按错误代码筛选后没有匹配的失败记录")
                return
        
        # 生成和显示统计信息
        stats = processor.generate_retry_statistics(failed_records)
        processor.print_statistics(stats)
        
        # 如果只修复进度文件，则执行修复后退出
        if args.fix_progress_only:
            processor.logger.info("只修复进度文件模式")
            processor.fix_progress_file(failed_records)
            processor.logger.info("进度文件修复完成！")
            return
        
        # 如果只显示统计信息，则退出
        if args.stats_only:
            processor.logger.info("仅显示统计信息模式，不执行重试")
            return
        
        # 改进的确认机制
        show_details = not args.no_details
        if args.test_mode or args.max_retry:
            # 测试模式或限制数量时，自动显示详情但不需要确认
            if show_details:
                processor.print_retry_details(failed_records, args.show_limit)
            processor.logger.info("测试模式或限制模式，跳过用户确认")
        else:
            # 正常模式，需要用户确认
            if not processor.confirm_retry_operation(failed_records, show_details):
                processor.logger.info("用户取消重试操作")
                return
        
        # 执行重试
        result = processor.retry_failed_scrapes(
            failed_records=failed_records,
            max_workers=args.max_workers,
            max_places=args.max_retry,
            backup_files=not args.no_backup
        )
        
        processor.logger.info("重试操作完成！")
        
    except KeyboardInterrupt:
        print("\n用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"重试处理出错: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
