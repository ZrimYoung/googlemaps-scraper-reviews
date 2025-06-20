﻿#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
文件名: find_duplicates_simple.py
功能: 查找并删除重复的Google地图评论抓取数据文件

该脚本用于扫描批量输出目录下的所有JSON文件，查找具有相同place_id的重复文件，
并根据抓取成功状态和文件大小等因素确定保留哪个文件，删除其余的重复文件。

主要功能:
1. 递归扫描batch_output目录下的所有.json文件
2. 提取每个文件的place_id并分组查找重复
3. 根据数据质量评估标准选择最佳文件保留
4. 提供用户确认删除机制
"""

import json
import os
from pathlib import Path
from collections import defaultdict

def find_duplicate_place_ids():
    """
    查找重复的place_id文件
    
    该函数扫描batch_output目录下的所有JSON文件，找出具有相同place_id的重复文件，
    并根据文件质量选择保留最佳文件，删除其余重复文件。
    
    文件质量评估标准:
    1. final_success状态 (最高优先级)
    2. scrape_success状态 (次要优先级)  
    3. 文件大小 (文件越大通常包含更多数据)
    
    返回值: 无
    """
    # 定义批量输出目录路径
    batch_output = Path("batch_output")
    
    # 使用defaultdict创建place_id到文件列表的映射
    # key: place_id (字符串), value: 包含该place_id的文件信息列表
    place_files = defaultdict(list)
    
    # 排除的特殊文件列表 - 这些文件不是具体的地点数据文件
    exclude_files = {
        'progress.json',        # 进度跟踪文件
        'summary_report.json',  # 汇总报告文件
        'errors.jsonl',         # 错误日志文件
        'batch_config.json'     # 批次配置文件
    }
    
    print("正在扫描文件...")
    
    # 初始化文件计数器
    total_files = 0
    
    # 递归遍历batch_output目录下的所有.json文件
    for json_file in batch_output.rglob("*.json"):
        # 跳过特殊文件
        if json_file.name in exclude_files:
            continue
            
        total_files += 1
        try:
            # 读取JSON文件内容
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 提取place_id - Google地图中地点的唯一标识符
                place_id = data.get("place_id", "")
                if place_id:
                    # 收集文件相关信息用于后续比较和选择
                    place_files[place_id].append({
                        "file": json_file,                                           # 文件路径对象
                        "success": data.get("scrape_success", False),               # 基础抓取成功标志
                        "final_success": data.get("final_success", False),          # 最终处理成功标志
                        "name": data.get("business_info", {}).get("name", ""),      # 商家名称
                        "size": json_file.stat().st_size                            # 文件大小(字节)
                    })
        except Exception as e:
            # 捕获并输出文件读取错误
            print(f"读取文件出错 {json_file}: {e}")
    
    print(f"总共扫描了 {total_files} 个文件")
    
    # 筛选出有重复的place_id (文件数量 > 1)
    duplicates = {pid: files for pid, files in place_files.items() if len(files) > 1}
    
    print(f"发现 {len(duplicates)} 个重复的place_id:")
    
    # 存储待删除的文件列表
    files_to_delete = []
    
    # 处理每个重复的place_id
    for place_id, files in duplicates.items():
        print(f"\nPlace ID: {place_id}")
        
        # 按文件质量排序 - 使用多层排序标准
        # 1. final_success (True > False)
        # 2. success (True > False)  
        # 3. size (大 > 小)
        # reverse=True 表示降序排列，最佳文件排在第一位
        files.sort(key=lambda x: (x["final_success"], x["success"], x["size"]), reverse=True)
        
        # 选择质量最好的文件保留
        keep_file = files[0]
        # 其余文件标记为删除
        delete_files = files[1:]
        
        # 输出保留文件信息
        print(f"  保留: {keep_file['file'].name} (final_success: {keep_file['final_success']}, success: {keep_file['success']}, size: {keep_file['size']})")
        
        # 输出删除文件信息并添加到删除列表
        for f in delete_files:
            print(f"  删除: {f['file'].name} (final_success: {f['final_success']}, success: {f['success']}, size: {f['size']})")
            files_to_delete.append(f['file'])
    
    print(f"\n总计需要删除 {len(files_to_delete)} 个文件")
    
    # 如果有文件需要删除，询问用户确认
    if files_to_delete:
        response = input("是否确认删除这些文件? (y/N): ")
        
        # 只有用户明确输入'y'才执行删除操作
        if response.lower() == 'y':
            deleted = 0  # 成功删除的文件计数
            
            # 逐个删除文件
            for file_path in files_to_delete:
                try:
                    file_path.unlink()  # 删除文件
                    print(f"已删除: {file_path}")
                    deleted += 1
                except Exception as e:
                    # 捕获删除失败的情况
                    print(f"删除失败 {file_path}: {e}")
            print(f"成功删除了 {deleted} 个文件")
        else:
            print("取消删除操作")

# 脚本主入口点
if __name__ == "__main__":
    find_duplicate_place_ids()