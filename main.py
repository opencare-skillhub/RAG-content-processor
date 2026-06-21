#!/usr/bin/env python3
"""
FastGPT 内容处理器 - 主程序

功能：
1. list-datasets: 列出所有 FastGPT 知识库
2. list-collections: 列出指定知识库下的文章/集合
3. search: 在知识库中搜索内容
4. upload-file: 上传单个文件到知识库
5. upload-folder: 上传整个文件夹到知识库
6. download-wechat: 批量下载微信公众号文章
7. clean-wechat: 清理微信公众号文章（两阶段）
8. download-and-clean: 下载并清理微信文章（完整流程）

使用示例：
    python main.py list-datasets
    python main.py download-wechat --urls urls.txt
    python main.py download-and-clean --urls urls.txt --dataset-id abc123
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.logging import RichHandler

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
logger = logging.getLogger("fastgpt-processor")

# 初始化控制台
console = Console()

# 导入模块
from fastgpt_sync import FastGPTSyncer
from fetchers.wechat_mcp import WeChatMCPDownloader
from cleaners import FormatCleaner, FrontmatterDoctor


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="FastGPT 内容处理器 - 知识库管理与微信文章处理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                                              启动交互式菜单
  %(prog)s list-datasets                                列出所有知识库
  %(prog)s list-collections --dataset-id abc123         列出知识库文章
  %(prog)s search --query "关键词" --dataset-id abc     搜索知识库
  %(prog)s upload-file --file article.md                上传单个文件
  %(prog)s upload-folder --folder ./articles            上传文件夹
  %(prog)s download-wechat --urls urls.txt              下载微信文章（从文件）
  %(prog)s download-wechat --urls https://mp.weixin...  下载微信文章（直接传入 URL）
  %(prog)s download-wechat --urls url1,url2             下载多个微信文章（逗号分隔）
  %(prog)s clean-wechat --input ./wechat-downloads      清理微信文章
  %(prog)s download-and-clean --urls urls.txt           下载并清理（完整流程）
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 1. list-datasets
    subparsers.add_parser('list-datasets', help='列出所有 FastGPT 知识库')
    
    # 2. list-collections
    p_list_coll = subparsers.add_parser('list-collections', help='列出知识库下的文章/集合')
    p_list_coll.add_argument('--dataset-id', required=True, help='知识库 ID')
    p_list_coll.add_argument('--limit', type=int, default=50, help='显示数量限制（默认 50）')
    
    # 3. search
    p_search = subparsers.add_parser('search', help='在知识库中搜索')
    p_search.add_argument('--dataset-id', required=True, help='知识库 ID')
    p_search.add_argument('--query', required=True, help='搜索关键词')
    p_search.add_argument('--limit', type=int, default=5, help='结果数量（默认 5）')
    
    # 4. upload-file
    p_upload_file = subparsers.add_parser('upload-file', help='上传单个文件')
    p_upload_file.add_argument('--file', required=True, help='文件路径')
    p_upload_file.add_argument('--dataset-id', required=True, help='目标知识库 ID')
    
    # 5. upload-folder
    p_upload_folder = subparsers.add_parser('upload-folder', help='上传整个文件夹')
    p_upload_folder.add_argument('--folder', required=True, help='文件夹路径')
    p_upload_folder.add_argument('--dataset-id', required=True, help='目标知识库 ID')
    p_upload_folder.add_argument('--extensions', default='.md,.txt', help='文件扩展名（逗号分隔）')
    
    # 6. qa-ingest
    p_qa_ingest = subparsers.add_parser('qa-ingest', help='人工精选文章 QA/标签/评分/入库')
    p_qa_ingest.add_argument('--input', required=True, help='输入文件或目录')
    p_qa_ingest.add_argument('--output', default='./qa-output', help='输出目录')
    p_qa_ingest.add_argument('--report-dir', default='./qa-reports', help='报告目录')
    p_qa_ingest.add_argument('--dataset-id', help='目标知识库 ID（可选）')
    p_qa_ingest.add_argument('--rubric', default=None, help='评分配置 YAML 路径')
    p_qa_ingest.add_argument('--threshold', type=int, default=None, help='准入阈值')
    p_qa_ingest.add_argument('--extensions', default='.md,.txt', help='文件扩展名（逗号分隔）')
    p_qa_ingest.add_argument('--dry-run', action='store_true', help='只展示将处理的文件与配置，不调用 LLM')
    
    # 7. download-wechat
    p_download = subparsers.add_parser('download-wechat', help='批量下载微信公众号文章')
    p_download.add_argument('--urls', required=True, help='URL 列表（直接传入 URL，多个用逗号分隔）或 URL 文件路径')
    p_download.add_argument('--output', default='./wechat-downloads', help='输出目录')
    p_download.add_argument('--formats', default='md', help='输出格式（默认 md）')
    
    # 8. clean-wechat
    p_clean = subparsers.add_parser('clean-wechat', help='清理微信公众号文章（两阶段）')
    p_clean.add_argument('--input', required=True, help='输入目录或文件')
    p_clean.add_argument('--output', help='输出目录（默认：输入目录_cleaned）')
    
    # 9. download-and-clean
    p_full = subparsers.add_parser('download-and-clean', help='下载并清理微信文章（完整流程）')
    p_full.add_argument('--urls', required=True, help='URL 列表（直接传入 URL，多个用逗号分隔）或 URL 文件路径')
    p_full.add_argument('--dataset-id', help='上传到知识库（可选）')
    p_full.add_argument('--output', default='./wechat-downloads', help='下载目录')
    p_full.add_argument('--cleaned-output', help='清理后输出目录（默认：下载目录_cleaned）')
    p_full.add_argument('--no-enrich', action='store_true',
                        help='禁用 LLM 富化（summary/description/tags），默认开启')

    return parser.parse_args()


def load_urls_from_input(urls_input: str) -> List[str]:
    """从输入加载 URL 列表（支持文件或直接传入 URL）
    
    Args:
        urls_input: 可以是文件路径，也可以是直接的 URL（多个用逗号分隔）
    
    Returns:
        URL 列表
    """
    urls = []
    
    # 检测是否是直接的 URL（http/https 开头）
    if urls_input.startswith(('http://', 'https://')):
        # 直接传入的 URL，可能用逗号分隔
        urls = [url.strip() for url in urls_input.split(',') if url.strip()]
        return urls
    
    # 否则当作文件路径处理
    path = Path(urls_input)
    if not path.exists():
        raise FileNotFoundError(f"URL 文件不存在: {urls_input}")
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    
    return urls




def cmd_qa_ingest(args):
    """人工精选文章 QA/标签/评分/入库"""
    from agents.qa_agent import KnowledgeBaseQAAgent
    from agents.qa_ingest import load_markdown_files, process_selected_articles

    input_path = Path(args.input)
    output_dir = Path(args.output)
    report_dir = Path(args.report_dir)
    extensions = tuple(ext.strip() for ext in args.extensions.split(',') if ext.strip())

    try:
        files = load_markdown_files(input_path, extensions=extensions)
    except Exception as exc:
        console.print(f"[red]❌ 读取输入失败: {exc}[/red]")
        return

    base_url = os.getenv('FASTGPT_BASE_URL')
    api_key = os.getenv('FASTGPT_API_KEY')
    syncer = None
    if args.dataset_id and base_url and api_key:
        syncer = FastGPTSyncer(base_url, api_key, args.dataset_id)
    elif args.dataset_id:
        console.print("[yellow]⚠️  已指定 dataset-id，但未配置 FASTGPT_BASE_URL / FASTGPT_API_KEY，跳过上传，仅生成本地结果[/yellow]")

    agent = KnowledgeBaseQAAgent(threshold=args.threshold, rubric_path=args.rubric)

    console.print("\n[bold cyan]🧠 一期 QA 精选文章入库[/bold cyan]")
    console.print(f"输入: [cyan]{input_path}[/cyan]")
    console.print(f"输出: [cyan]{output_dir}[/cyan]")
    console.print(f"报告: [cyan]{report_dir}[/cyan]")
    console.print(f"准入阈值: [cyan]{agent.threshold}[/cyan]")
    console.print(f"模型: [cyan]{agent.model or '(env missing)'}[/cyan]")
    console.print(f"Rubric: [cyan]{agent.rubric_path}[/cyan]")
    console.print(f"匹配文件: [cyan]{len(files)}[/cyan]")
    if syncer:
        console.print(f"上传知识库: [cyan]{args.dataset_id}[/cyan]")
    else:
        console.print("上传知识库: [yellow]未配置[/yellow]")

    if args.dry_run:
        for fp in files:
            console.print(f" - {fp}")
        return

    results = process_selected_articles(
        input_path,
        agent,
        output_dir,
        report_dir,
        syncer=syncer,
        extensions=extensions,
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("文件", style="cyan")
    table.add_column("分数", style="yellow")
    table.add_column("等级", style="green")
    table.add_column("动作", style="white")
    table.add_column("权重", style="magenta")
    table.add_column("上传", style="blue")

    for item in results:
        table.add_row(
            Path(item.source_path).name,
            str(item.qa_score),
            item.grade,
            item.library_action,
            str(item.qa_weight),
            item.upload_result,
        )
    console.print(table)


def cmd_list_datasets():
    """列出所有 FastGPT 知识库"""
    console.print("\n[bold cyan]📚 FastGPT 知识库列表[/bold cyan]\n")
    
    base_url = os.getenv('FASTGPT_BASE_URL')
    api_key = os.getenv('FASTGPT_API_KEY')
    
    if not base_url or not api_key:
        console.print("[red]❌ 错误: 未配置 FASTGPT_BASE_URL 或 FASTGPT_API_KEY[/red]")
        return
    
    try:
        syncer = FastGPTSyncer(base_url, api_key)
        datasets = syncer.list_datasets()
        
        if not datasets:
            console.print("[yellow]⚠️  没有找到任何知识库[/yellow]")
            return
        
        # 创建表格
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("序号", style="dim", width=6)
        table.add_column("知识库 ID", style="cyan", no_wrap=True)
        table.add_column("名称", style="green")
        table.add_column("状态", style="yellow")
        
        for i, ds in enumerate(datasets, 1):
            dataset_id = ds.get('_id', 'N/A')
            name = ds.get('name', '未命名')
            status = ds.get('status', '未知')
            table.add_row(str(i), dataset_id, name, status)
        
        console.print(table)
        console.print(f"\n[green]✅ 共 {len(datasets)} 个知识库[/green]\n")
        
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("列出知识库时出错")


def cmd_list_collections(args):
    """列出知识库下的文章/集合"""
    console.print(f"\n[bold cyan]📄 知识库文章列表[/bold cyan]")
    console.print(f"知识库 ID: [cyan]{args.dataset_id}[/cyan]\n")
    
    base_url = os.getenv('FASTGPT_BASE_URL')
    api_key = os.getenv('FASTGPT_API_KEY')
    
    if not base_url or not api_key:
        console.print("[red]❌ 错误: 未配置 FASTGPT_BASE_URL 或 FASTGPT_API_KEY[/red]")
        return
    
    try:
        syncer = FastGPTSyncer(base_url, api_key, args.dataset_id)
        collections = syncer.list_collections(page_size=args.limit)
        
        if not collections:
            console.print("[yellow]⚠️  该知识库下没有找到文章[/yellow]")
            return
        
        # 创建表格
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("序号", style="dim", width=6)
        table.add_column("文章 ID", style="cyan", no_wrap=True)
        table.add_column("标题", style="green")
        table.add_column("创建时间", style="yellow", width=20)
        
        for i, coll in enumerate(collections, 1):
            coll_id = coll.get('_id', 'N/A')
            name = coll.get('name', '未命名')
            created_at = coll.get('createdAt', 'N/A')
            
            # 截断过长的标题
            if len(name) > 50:
                name = name[:47] + "..."
            
            table.add_row(str(i), coll_id, name, created_at)
        
        console.print(table)
        console.print(f"\n[green]✅ 共 {len(collections)} 篇文章[/green]\n")
        
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("列出文章时出错")


def cmd_search(args):
    """在知识库中搜索"""
    console.print(f"\n[bold cyan]🔍 知识库搜索[/bold cyan]")
    console.print(f"知识库 ID: [cyan]{args.dataset_id}[/cyan]")
    console.print(f"搜索词: [cyan]{args.query}[/cyan]\n")
    
    base_url = os.getenv('FASTGPT_BASE_URL')
    api_key = os.getenv('FASTGPT_API_KEY')
    
    if not base_url or not api_key:
        console.print("[red]❌ 错误: 未配置 FASTGPT_BASE_URL 或 FASTGPT_API_KEY[/red]")
        return
    
    try:
        syncer = FastGPTSyncer(base_url, api_key, args.dataset_id)
        raw_results = syncer.search(args.query, limit=args.limit)
        
        # 提取实际结果列表（API 返回 dict，结果在 list 字段）
        if isinstance(raw_results, dict):
            results = raw_results.get('list', [])
        else:
            results = raw_results or []
        
        if not results:
            console.print("[yellow]⚠️  未找到相关结果[/yellow]")
            return
        
        console.print(f"[green]✅ 找到 {len(results)} 个结果[/green]\n")
        
        for i, result in enumerate(results, 1):
            # 提取分数（可能是列表或数字）
            score_data = result.get('score', [])
            if isinstance(score_data, list) and score_data:
                score = score_data[0].get('value', 0)
            else:
                score = score_data
            
            content = result.get('q', result.get('content', ''))
            source = result.get('sourceName', '未知来源')
            
            # 截断过长的内容
            if len(content) > 200:
                content = content[:197] + "..."
            
            console.print(Panel(
                content,
                title=f"[bold]结果 {i}[/bold] (相关度: {score:.3f})",
                border_style="green"
            ))
        
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("搜索时出错")


def cmd_upload_file(args):
    """上传单个文件"""
    console.print(f"\n[bold cyan]📤 上传文件[/bold cyan]")
    console.print(f"文件: [cyan]{args.file}[/cyan]")
    console.print(f"知识库: [cyan]{args.dataset_id}[/cyan]\n")
    
    file_path = Path(args.file)
    if not file_path.exists():
        console.print(f"[red]❌ 错误: 文件不存在: {args.file}[/red]")
        return
    
    base_url = os.getenv('FASTGPT_BASE_URL')
    api_key = os.getenv('FASTGPT_API_KEY')
    
    if not base_url or not api_key:
        console.print("[red]❌ 错误: 未配置 FASTGPT_BASE_URL 或 FASTGPT_API_KEY[/red]")
        return
    
    try:
        syncer = FastGPTSyncer(base_url, api_key, args.dataset_id)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("上传文件...", total=1)
            result = syncer.upload_file(str(file_path))
            progress.update(task, completed=1)
        
        if result == "success":
            console.print(f"\n[green]✅ 上传成功: {file_path.name}[/green]\n")
        elif result == "skipped":
            console.print(f"\n[yellow]⏭️  跳过（内容未变化）: {file_path.name}[/yellow]\n")
        else:
            console.print(f"\n[red]❌ 上传失败[/red]\n")
    
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("上传文件时出错")


def cmd_upload_folder(args):
    """上传整个文件夹"""
    console.print(f"\n[bold cyan]📁 上传文件夹[/bold cyan]")
    console.print(f"文件夹: [cyan]{args.folder}[/cyan]")
    console.print(f"知识库: [cyan]{args.dataset_id}[/cyan]")
    console.print(f"扩展名: [cyan]{args.extensions}[/cyan]\n")
    
    folder_path = Path(args.folder)
    if not folder_path.exists() or not folder_path.is_dir():
        console.print(f"[red]❌ 错误: 文件夹不存在: {args.folder}[/red]")
        return
    
    base_url = os.getenv('FASTGPT_BASE_URL')
    api_key = os.getenv('FASTGPT_API_KEY')
    
    if not base_url or not api_key:
        console.print("[red]❌ 错误: 未配置 FASTGPT_BASE_URL 或 FASTGPT_API_KEY[/red]")
        return
    
    try:
        syncer = FastGPTSyncer(base_url, api_key, args.dataset_id)
        extensions = [ext.strip() for ext in args.extensions.split(',')]
        
        # 统计文件
        files = []
        for ext in extensions:
            files.extend(folder_path.rglob(f'*{ext}'))
        
        if not files:
            console.print(f"[yellow]⚠️  未找到匹配的文件[/yellow]")
            return
        
        console.print(f"[cyan]找到 {len(files)} 个文件[/cyan]\n")
        
        # 上传
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("上传文件...", total=len(files))
            
            success_count = 0
            skipped_count = 0
            for file_path in files:
                progress.update(task, description=f"上传: {file_path.name}")
                result = syncer.upload_file(str(file_path))
                if result == "success":
                    success_count += 1
                elif result == "skipped":
                    skipped_count += 1
                progress.advance(task)
        
        console.print(f"\n[green]✅ 上传完成: {success_count}/{len(files)} 成功, {skipped_count} 跳过（内容未变化）[/green]\n")
    
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("上传文件夹时出错")


def cmd_download_wechat(args):
    """批量下载微信公众号文章"""
    console.print(f"\n[bold cyan]📥 下载微信文章[/bold cyan]")
    console.print(f"URL 输入: [cyan]{args.urls}[/cyan]")
    console.print(f"输出根目录: [cyan]{args.output}[/cyan]\n")

    try:
        urls = load_urls_from_input(args.urls)
        console.print(f"[cyan]加载了 {len(urls)} 个 URL[/cyan]\n")

        downloader = WeChatMCPDownloader(output_dir=args.output)
        console.print(f"[dim]本次下载目录: {downloader.run_subdir}[/dim]")
        formats = tuple(args.formats.split(','))
        
        # 批量下载
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("下载文章...", total=len(urls))
            
            def progress_callback(current, total, result):
                if result and result.get('status') == 'success':
                    progress.update(task, description=f"✅ {result.get('title', '完成')}")
                progress.advance(task)
            
            result = downloader.batch_download(urls, formats=formats, progress_callback=progress_callback)
        
        # 显示结果
        console.print("\n[bold]下载结果:[/bold]")
        console.print(f"  总计: {result['total']}")
        console.print(f"  [green]成功: {result['success']}[/green]")
        console.print(f"  [red]失败: {result['failed']}[/red]")
        console.print(f"  [yellow]跳过: {result['skipped']}[/yellow]\n")
    
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("下载微信文章时出错")


def cmd_clean_wechat(args):
    """清理微信公众号文章（两阶段）"""
    console.print(f"\n[bold cyan]🧹 清理微信文章[/bold cyan]")
    console.print(f"输入: [cyan]{args.input}[/cyan]")
    
    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]❌ 错误: 路径不存在: {args.input}[/red]")
        return
    
    # 确定输出目录
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = input_path.parent / f"{input_path.stem}_cleaned"
    
    console.print(f"输出: [cyan]{output_dir}[/cyan]\n")
    
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 收集文件
        if input_path.is_file():
            files = [input_path]
        else:
            files = list(input_path.rglob('*.md'))
        
        if not files:
            console.print(f"[yellow]⚠️  未找到 Markdown 文件[/yellow]")
            return
        
        console.print(f"[cyan]找到 {len(files)} 个文件[/cyan]\n")
        
        # 两阶段清理
        format_cleaner = FormatCleaner()
        frontmatter_doctor = FrontmatterDoctor()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("清理文章...", total=len(files))
            
            success_count = 0
            for file_path in files:
                progress.update(task, description=f"清理: {file_path.name}")
                
                try:
                    # 读取内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 阶段 1: 格式清理
                    content, _ = format_cleaner.clean(content)
                    
                    # 阶段 2: Frontmatter 标准化
                    metadata = {
                        'original_url': file_path.name  # 使用文件名作为标识
                    }
                    content, _, _ = frontmatter_doctor.standardize(content, metadata)
                    
                    # 写入输出
                    output_file = output_dir / file_path.name
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    success_count += 1
                except Exception as e:
                    logger.error(f"清理 {file_path.name} 时出错: {e}")
                
                progress.advance(task)
        
        console.print(f"\n[green]✅ 清理完成: {success_count}/{len(files)} 成功[/green]\n")
    
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("清理微信文章时出错")


def _find_url_for_file(url_file_map: dict, file_path: str) -> Optional[str]:
    """在 url→files 映射中反查文件对应的真实 URL。"""
    for url, files in url_file_map.items():
        if file_path in files:
            return url
    return None


def _extract_author_from_raw(raw: str) -> Optional[str]:
    """从原始未清洗文本提取公众号名（JS void 链接文本）。

    FormatCleaner 会提前破坏 javascript:void 链接结构，因此必须在
    清洗前从原始内容提取，再传给 metadata。
    """
    import re
    m = re.search(r'\[\s*([^\]]+?)\s*\]\(javascript:void[^)]*\)', raw)
    if m:
        name = m.group(1).strip()
        if name and name not in ('作者头像',):
            return name
    return None


def _parse_frontmatter_from_file(file_path) -> dict:
    """从 Markdown 文件解析 frontmatter，返回 dict（无 frontmatter 时返回空 dict）。"""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return {}
    if not content.startswith('---'):
        return {}
    end = content.find('---', 3)
    if end == -1:
        return {}
    try:
        import yaml
        return yaml.safe_load(content[3:end].strip()) or {}
    except Exception:
        return {}


def cmd_download_and_clean(args):
    """下载并清理微信文章（完整流程）"""
    console.print(f"\n[bold cyan]🔄 下载并清理微信文章[/bold cyan]")
    console.print(f"URL 输入: [cyan]{args.urls}[/cyan]")
    console.print(f"下载根目录: [cyan]{args.output}[/cyan]")

    cleaned_output = args.cleaned_output or f"{args.output}_cleaned"

    try:
        # 阶段 1: 下载
        console.print("[bold]阶段 1/3: 下载文章[/bold]\n")

        urls = load_urls_from_input(args.urls)
        console.print(f"[cyan]加载了 {len(urls)} 个 URL[/cyan]\n")

        downloader = WeChatMCPDownloader(output_dir=args.output)

        run_subdir = downloader.run_subdir
        run_dir = str(downloader.output_dir)
        console.print(f"[dim]本次下载子目录: {run_subdir}[/dim]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("下载文章...", total=len(urls))

            def download_callback(current, total, result):
                if result and result.get('status') == 'success':
                    progress.update(task, description=f"✅ {result.get('title', '完成')}")
                progress.advance(task)

            download_result = downloader.batch_download(urls, formats=('md',), progress_callback=download_callback)

        console.print(f"\n[green]下载完成: {download_result['success']}/{download_result['total']} 成功[/green]")
        console.print(f"[dim]下载目录: {download_result.get('run_dir', run_dir)}[/dim]\n")

        # 阶段 2: 清理——使用白名单（仅本次下载的文件），不扫描全目录
        console.print("[bold]阶段 2/3: 清理文章[/bold]\n")

        # 优先用 batch_download 返回的白名单文件
        whitelist = download_result.get("files", [])
        url_file_map = download_result.get("url_file_map", {})

        if whitelist:
            files = [Path(f) for f in whitelist if Path(f).exists()]
            if len(files) < len(whitelist):
                missing = [f for f in whitelist if not Path(f).exists()]
                console.print(f"[yellow]⚠️  白名单中有 {len(missing)} 个文件不存在，已跳过[/yellow]")
        else:
            # 回退：扫描本次 run 子目录（不是根目录）
            console.print("[yellow]⚠️  未获取到下载文件清单，回退扫描本次 run 目录[/yellow]")
            files = list(Path(run_dir).rglob('*.md'))

        if not files:
            console.print("[yellow]⚠️  没有可清理的文件[/yellow]")
            return

        # 清洗输出也进对应的 run 子目录，与下载一一对应
        cleaned_dir = Path(cleaned_output) / run_subdir
        cleaned_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"清理输出: [cyan]{cleaned_dir}[/cyan]")
        console.print(f"[cyan]找到 {len(files)} 个文件[/cyan]\n")

        format_cleaner = FormatCleaner()
        frontmatter_doctor = FrontmatterDoctor()

        # 富化器默认开启（--no-enrich 时禁用）
        enricher = None
        if not args.no_enrich:
            from agents.frontmatter_enricher import FrontmatterEnricher
            enricher = FrontmatterEnricher()
            console.print(f"[cyan]富化模型: {enricher.config.model or '(env missing)'}[/cyan]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("清理文章...", total=len(files))

            cleaned_files = []
            for file_path in files:
                progress.update(task, description=f"清理: {file_path.name}")

                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        raw_content = f.read()

                    # 预提取 author（原始文本，链接结构在清洗前保留）
                    author = _extract_author_from_raw(raw_content)

                    # 阶段 1: 格式清理
                    content, _ = format_cleaner.clean(raw_content)

                    # 阶段 1.5: 可选 LLM 富化（生成 summary/description/tags）
                    metadata = {}
                    if author:
                        metadata['author'] = author
                    if enricher:
                        progress.update(task, description=f"富化: {file_path.name}")
                        enriched = enricher.enrich(content)
                        metadata.update({k: v for k, v in enriched.items() if v})

                    # 阶段 2: Frontmatter 标准化——用真实 URL 回填 original_url
                    original_url = _find_url_for_file(url_file_map, str(file_path))
                    metadata['original_url'] = original_url or file_path.name
                    content, _, _ = frontmatter_doctor.standardize(content, metadata)

                    # 写入输出
                    output_file = cleaned_dir / file_path.name
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(content)

                    cleaned_files.append(output_file)
                except Exception as e:
                    logger.error(f"清理 {file_path.name} 时出错: {e}")

                progress.advance(task)

        console.print(f"\n[green]清理完成: {len(cleaned_files)}/{len(files)} 成功[/green]")
        console.print(f"[dim]清洗结果: {cleaned_dir}[/dim]\n")
        
        # 阶段 3: 上传（可选）
        if args.dataset_id and cleaned_files:
            console.print("[bold]阶段 3/3: 上传到知识库[/bold]\n")
            
            base_url = os.getenv('FASTGPT_BASE_URL')
            api_key = os.getenv('FASTGPT_API_KEY')
            
            if not base_url or not api_key:
                console.print("[yellow]⚠️  未配置 FastGPT，跳过上传[/yellow]\n")
            else:
                syncer = FastGPTSyncer(base_url, api_key, args.dataset_id)
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("上传文件...", total=len(cleaned_files))
                    
                    upload_success = 0
                    upload_skipped = 0
                    for file_path in cleaned_files:
                        progress.update(task, description=f"上传: {file_path.name}")
                        # 解析 frontmatter 中的 tags/summary/author 作为 FastGPT metadata
                        fm = _parse_frontmatter_from_file(file_path)
                        upload_meta = {
                            "title": fm.get("title", file_path.name),
                            "author": fm.get("author", ""),
                            "tags": ",".join(fm.get("tags", [])),
                            "summary": fm.get("summary", ""),
                            "original_url": fm.get("original_url", ""),
                        }
                        result = syncer.upload_file(str(file_path), metadata=upload_meta)
                        if result == "success":
                            upload_success += 1
                        elif result == "skipped":
                            upload_skipped += 1
                        progress.advance(task)
                
                console.print(f"\n[green]上传完成: {upload_success}/{len(cleaned_files)} 成功, {upload_skipped} 跳过（内容未变化）[/green]\n")
        
        console.print("[bold green]✅ 全部完成！[/bold green]\n")
    
    except Exception as e:
        console.print(f"[red]❌ 错误: {e}[/red]")
        logger.exception("下载并清理时出错")


def interactive_menu():
    """交互式菜单"""
    console.print("\n[bold cyan]🎯 FastGPT 内容处理器 - 交互式菜单[/bold cyan]\n")
    
    console.print("[bold]可用功能：[/bold]")
    console.print("  1. 列出所有 FastGPT 知识库")
    console.print("  2. 列出指定知识库的文章")
    console.print("  3. 搜索知识库内容")
    console.print("  4. 上传单个文件")
    console.print("  5. 上传整个文件夹")
    console.print("  6. 下载微信文章（支持单个或多个 URL）")
    console.print("  7. 清理已下载的微信文章")
    console.print("  8. 下载并清理微信文章（完整流程）")
    console.print("  0. 退出\n")
    
    while True:
        try:
            choice = console.input("[bold green]请选择功能 (0-8): [/bold green]").strip()
            
            if choice == '0':
                console.print("[yellow]👋 再见！[/yellow]\n")
                break
            elif choice == '1':
                cmd_list_datasets()
            elif choice == '2':
                dataset_id = console.input("[cyan]请输入知识库 ID: [/cyan]").strip()
                limit = int(console.input("[cyan]显示数量限制 (默认 50): [/cyan]").strip() or 50)
                
                # 创建模拟的 args 对象
                class Args:
                    def __init__(self, dataset_id, limit):
                        self.dataset_id = dataset_id
                        self.limit = limit
                
                cmd_list_collections(Args(dataset_id, limit))
            elif choice == '3':
                dataset_id = console.input("[cyan]请输入知识库 ID: [/cyan]").strip()
                query = console.input("[cyan]请输入搜索关键词: [/cyan]").strip()
                limit = int(console.input("[cyan]结果数量限制 (默认 5): [/cyan]").strip() or 5)
                
                class Args:
                    def __init__(self, dataset_id, query, limit):
                        self.dataset_id = dataset_id
                        self.query = query
                        self.limit = limit
                
                cmd_search(Args(dataset_id, query, limit))
            elif choice == '4':
                file_path = console.input("[cyan]请输入文件路径: [/cyan]").strip()
                dataset_id = console.input("[cyan]请输入目标知识库 ID: [/cyan]").strip()
                
                class Args:
                    def __init__(self, file_path, dataset_id):
                        self.file = file_path
                        self.dataset_id = dataset_id
                
                cmd_upload_file(Args(file_path, dataset_id))
            elif choice == '5':
                folder_path = console.input("[cyan]请输入文件夹路径: [/cyan]").strip()
                dataset_id = console.input("[cyan]请输入目标知识库 ID: [/cyan]").strip()
                extensions = console.input("[cyan]文件扩展名 (默认 .md,.txt): [/cyan]").strip() or ".md,.txt"
                
                class Args:
                    def __init__(self, folder_path, dataset_id, extensions):
                        self.folder = folder_path
                        self.dataset_id = dataset_id
                        self.extensions = extensions
                
                cmd_upload_folder(Args(folder_path, dataset_id, extensions))
            elif choice == '6':
                urls = console.input("[cyan]请输入 URL（多个用逗号分隔）或 URL 文件路径: [/cyan]").strip()
                output = console.input("[cyan]输出目录 (默认 ./wechat-downloads): [/cyan]").strip() or "./wechat-downloads"
                formats = console.input("[cyan]输出格式 (默认 md): [/cyan]").strip() or "md"
                
                class Args:
                    def __init__(self, urls, output, formats):
                        self.urls = urls
                        self.output = output
                        self.formats = formats
                
                cmd_download_wechat(Args(urls, output, formats))
            elif choice == '7':
                input_path = console.input("[cyan]请输入输入目录或文件路径: [/cyan]").strip()
                output = console.input("[cyan]输出目录 (留空使用默认): [/cyan]").strip() or None
                
                class Args:
                    def __init__(self, input_path, output):
                        self.input = input_path
                        self.output = output
                
                cmd_clean_wechat(Args(input_path, output))
            elif choice == '8':
                urls = console.input("[cyan]请输入 URL（多个用逗号分隔）或 URL 文件路径: [/cyan]").strip()
                output = console.input("[cyan]下载目录 (默认 ./wechat-downloads): [/cyan]").strip() or "./wechat-downloads"
                cleaned_output = console.input("[cyan]清理后输出目录 (留空使用默认): [/cyan]").strip() or None
                dataset_id = console.input("[cyan]上传到知识库 ID (留空跳过): [/cyan]").strip() or None
                
                class Args:
                    def __init__(self, urls, output, cleaned_output, dataset_id):
                        self.urls = urls
                        self.output = output
                        self.cleaned_output = cleaned_output
                        self.dataset_id = dataset_id
                
                cmd_download_and_clean(Args(urls, output, cleaned_output, dataset_id))
            else:
                console.print("[red]❌ 无效选择，请重新输入[/red]\n")
            
            # 执行完成后等待用户确认
            if choice in ['1', '2', '3', '4', '5', '6', '7', '8']:
                console.input("\n[dim]按 Enter 继续...[/dim]")
                console.print("\n" + "="*60 + "\n")
        
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 再见！[/yellow]\n")
            break
        except Exception as e:
            console.print(f"[red]❌ 错误: {e}[/red]\n")
            logger.exception("交互式菜单出错")


def main():
    """主函数"""
    args = parse_args()
    
    if not args.command:
        # 没有指定命令，显示交互式菜单
        interactive_menu()
        return
    
    # 命令映射
    commands = {
        'list-datasets': lambda: cmd_list_datasets(),
        'list-collections': lambda: cmd_list_collections(args),
        'search': lambda: cmd_search(args),
        'upload-file': lambda: cmd_upload_file(args),
        'upload-folder': lambda: cmd_upload_folder(args),
        'qa-ingest': lambda: cmd_qa_ingest(args),
        'download-wechat': lambda: cmd_download_wechat(args),
        'clean-wechat': lambda: cmd_clean_wechat(args),
        'download-and-clean': lambda: cmd_download_and_clean(args),
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func()
    else:
        console.print(f"[red]❌ 未知命令: {args.command}[/red]")


if __name__ == '__main__':
    main()
