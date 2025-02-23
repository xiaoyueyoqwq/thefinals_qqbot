#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import ast
import argparse
import fnmatch
import re
import math
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import List, Dict, Optional

################################################################################
# 数据结构
################################################################################

class FunctionInfo:
    def __init__(self, name: str, lines: int, complexity: int, start_line: int, has_docstring: bool):
        self.name = name
        self.lines = lines
        self.complexity = complexity
        self.start_line = start_line
        self.has_docstring = has_docstring  # 是否拥有 docstring

class FileStats:
    def __init__(self, path: str, language: str):
        self.path = path
        self.language = language
        self.lines = 0
        self.code_lines = 0
        self.comment_lines = 0
        self.blank_lines = 0
        self.functions: List[FunctionInfo] = []

class ProjectStats:
    def __init__(self, root_dir: str, complexity_threshold: int):
        self.root_dir = os.path.abspath(root_dir)
        self.files: Dict[str, FileStats] = {}
        self.languages: Dict[str, int] = defaultdict(int)

        # 总体统计
        self.total_lines = 0
        self.total_code_lines = 0
        self.total_comment_lines = 0
        self.total_blank_lines = 0

        # 函数 & 复杂度相关
        self.total_functions = 0
        self.max_complexity = 0
        self.sum_complexity = 0
        self.over_threshold_functions: List[FunctionInfo] = []
        # 复杂度分布（示例：1-5、6-10、11-15、16-20、21+）
        self.complexity_bins = [0, 0, 0, 0, 0]

        # Python docstring 相关
        self.docstring_covered_functions = 0  # 拥有 docstring 的函数数量

        # 跳过/异常统计
        self.skipped_files = 0        # 因为大文件或检测为二进制而跳过的文件数
        self.unreadable_files = 0     # 打开或读取异常的文件数量
        self.ast_failed_files = 0     # Python AST 解析失败的文件数

        # 阈值配置
        self.complexity_threshold = complexity_threshold

        # 忽略的函数列表，格式为 (文件名, 函数名)
        self.ignored_functions = [
            ("bot.py", "_cleanup"),
            ("bot.py", "main"),
            ("test_db.py", "test_query_player"),
            ("code_quality.py", "analyze_single_file")
        ]


################################################################################
# 主流程
################################################################################

def main():
    parser = argparse.ArgumentParser(description="Code Quality Analyzer (Python)")
    parser.add_argument("--dir", type=str, default=".", help="Project root directory")
    parser.add_argument("--workers", type=int, default=8, help="Number of threads to use")
    parser.add_argument("--complexity-threshold", type=int, default=15,
                        help="Cyclomatic complexity threshold for warning")
    parser.add_argument("--exclude-dirs", nargs="*", default=None,
                        help="List of directory patterns to exclude (fnmatch). Default: .*, .venv*, venv*, node_modules*, site-packages*, vendor*")
    parser.add_argument("--max-file-size", type=int, default=5 * 1024 * 1024,
                        help="Maximum file size in bytes to analyze. Default = 5MB.")
    parser.add_argument("--json-output", type=str, default=None,
                        help="Path to output JSON report, e.g. 'report.json'. If not set, skip JSON output.")
    args = parser.parse_args()

    # 默认排除常见无关目录
    if not args.exclude_dirs:
        args.exclude_dirs = [
            ".*",             # 隐藏文件夹，如 .git, .idea 等
            ".venv*", "venv*",
            "node_modules*",
            "site-packages*",
            "vendor*"
        ]

    stats = ProjectStats(args.dir, args.complexity_threshold)

    # 收集所有文件
    file_list = collect_files(stats.root_dir, args.exclude_dirs)

    # 并发分析
    analyze_files_concurrently(stats, file_list, args.workers, args.max_file_size)

    # 打印报告
    print_summary(stats)
    print_language_stats(stats)
    print_largest_files(stats, top_n=15)
    print_function_complexity_analysis(stats)
    print_top_n_complex_functions(stats, top_n=15)
    print_top_n_function_by_lines(stats, top_n=15)

    # 如果指定了 JSON 输出，写出结果
    if args.json_output:
        report_data = generate_json_report(stats)
        try:
            with open(args.json_output, "w", encoding="utf-8") as jf:
                json.dump(report_data, jf, ensure_ascii=False, indent=2)
            print(f"\n[Info] JSON report generated at: {args.json_output}")
        except Exception as e:
            print(f"[Error] Failed to write JSON report: {e}")


################################################################################
# 文件收集
################################################################################

def collect_files(root_dir: str, exclude_dirs: List[str]) -> List[str]:
    """遍历目录，收集所有待分析的文件。"""
    result = []
    for root, dirs, files in os.walk(root_dir):
        # 先根据 exclude_dirs 过滤目录
        new_dirs = []
        for d in dirs:
            full_dir_path = os.path.join(root, d)
            if should_exclude_dir(full_dir_path, exclude_dirs):
                continue
            new_dirs.append(d)
        dirs[:] = new_dirs

        for f in files:
            # 跳过隐藏文件，如 .DS_Store 等
            if f.startswith("."):
                continue
            full_path = os.path.join(root, f)
            result.append(full_path)
    return result

def should_exclude_dir(dir_path: str, exclude_patterns: List[str]) -> bool:
    """根据 fnmatch 模式判断是否要排除某目录。"""
    dir_name = os.path.basename(dir_path)
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(dir_name, pattern):
            return True
    return False


################################################################################
# 并发分析
################################################################################

def analyze_files_concurrently(stats: ProjectStats, files: List[str], workers: int, max_file_size: int):
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for f in files:
            future = executor.submit(analyze_single_file, stats, f, max_file_size)
            futures[future] = f

        for future in as_completed(futures):
            fpath = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[Error] Unexpected error on file {fpath}: {e}")

def analyze_single_file(stats: ProjectStats, path: str, max_file_size: int):
    # 跳过大文件
    if os.path.getsize(path) > max_file_size:
        stats.skipped_files += 1
        return
    # 跳过疑似二进制文件
    if is_binary_file(path):
        stats.skipped_files += 1
        return

    language = guess_file_language(path)
    filestats = FileStats(path=path, language=language)

    # 读取文件
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[Warning] Cannot read file {path}: {e}")
        stats.unreadable_files += 1
        return

    # 解析行数、注释、空行
    in_multiline_comment = False
    for line in lines:
        filestats.lines += 1
        trimmed = line.strip()

        if not trimmed:
            filestats.blank_lines += 1
            continue

        if language in ["C", "C++", "Java", "Go", "JavaScript", "TypeScript"]:
            # 简易多行注释检查： /* ... */ 
            if re.search(r"/\*", trimmed) and not re.search(r"\*/", trimmed):
                in_multiline_comment = True
                filestats.comment_lines += 1
                continue
            if in_multiline_comment:
                filestats.comment_lines += 1
                if re.search(r"\*/", trimmed):
                    in_multiline_comment = False
                continue
            # 单行注释
            if trimmed.startswith("//"):
                filestats.comment_lines += 1
                continue

        if language == "Python":
            # 简易三引号检查
            if (trimmed.startswith('"""') or trimmed.startswith("'''")) and not (trimmed.endswith('"""') or trimmed.endswith("'''")):
                in_multiline_comment = True
                filestats.comment_lines += 1
                continue
            if in_multiline_comment:
                filestats.comment_lines += 1
                if (trimmed.endswith('"""') or trimmed.endswith("'''")):
                    in_multiline_comment = False
                continue
            # 单行注释
            if trimmed.startswith("#"):
                filestats.comment_lines += 1
                continue

        # 其他情况视为代码行
        filestats.code_lines += 1

    # 如果是 Python 文件，进一步用 AST 分析函数
    if language == "Python":
        analyze_python_functions(path, filestats, stats)

    # 更新到全局统计
    update_project_stats(stats, filestats)


################################################################################
# Python AST 分析
################################################################################

def analyze_python_functions(filepath: str, filestats: FileStats, stats: ProjectStats):
    """基于 AST 分析 Python 文件中的函数定义、行数、圈复杂度、docstring 等。"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        print(f"[Warning] AST parse failed for {filepath}: {e}")
        stats.ast_failed_files += 1
        return

    class FuncAnalyzer(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            _analyze_func_node(node, filestats, stats)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node):
            _analyze_func_node(node, filestats, stats)
            self.generic_visit(node)

    analyzer = FuncAnalyzer()
    analyzer.visit(tree)

def _analyze_func_node(node: ast.AST, filestats: FileStats, stats: ProjectStats):
    """提取单个函数的行数、圈复杂度、docstring 等信息。"""
    # 获取函数名
    func_name = getattr(node, "name", "<lambda>")
    
    # 检查是否在忽略列表中
    file_name = os.path.basename(filestats.path)
    if (file_name, func_name) in stats.ignored_functions:
        return
        
    start_line = getattr(node, "lineno", 0)
    end_line = getattr(node, "end_lineno", start_line)
    lines = end_line - start_line + 1 if end_line >= start_line else 0

    complexity = calc_cyclomatic_complexity(node)
    has_docstring = check_docstring(node)

    fi = FunctionInfo(
        name=func_name,
        lines=lines,
        complexity=complexity,
        start_line=start_line,
        has_docstring=has_docstring
    )
    filestats.functions.append(fi)

    # 如果函数有 docstring，则计数
    if has_docstring:
        stats.docstring_covered_functions += 1

def calc_cyclomatic_complexity(func_node: ast.AST) -> int:
    """
    极简版圈复杂度统计：
      每出现 if / for / while / and / or / except / with / async with / comprehension 等结构时+1
    可按需扩展或使用第三方库 radon 做更精确的统计。
    """
    complexity = 1

    class ComplexityVisitor(ast.NodeVisitor):
        def generic_visit(self, node):
            nonlocal complexity
            if isinstance(node, (ast.If, ast.For, ast.While, ast.And, ast.Or,
                                 ast.ExceptHandler, ast.With, ast.AsyncWith,
                                 ast.comprehension)):
                complexity += 1
            super().generic_visit(node)

    ComplexityVisitor().visit(func_node)
    return complexity

def check_docstring(node: ast.AST) -> bool:
    """
    判断函数是否有 docstring：
      如果函数体非空，且第一个语句是 Expression 且其值为 Str，就视为 docstring。
    """
    if not getattr(node, "body", []):
        return False
    first_stmt = node.body[0]
    if isinstance(first_stmt, ast.Expr) and isinstance(first_stmt.value, ast.Str):
        # Python 3.8 以后：ast.Constant
        return True
    return False


################################################################################
# 工具函数
################################################################################

def is_binary_file(path: str, chunk_size: int = 1024) -> bool:
    """
    检测文件是否为二进制：
      读取首段数据，若不可见字符比例 > 30% 则视为二进制文件。
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(chunk_size)
            if not chunk:
                return False
            non_text_count = sum(byte < 9 or (byte > 13 and byte < 32) for byte in chunk)
            if float(non_text_count) / len(chunk) > 0.3:
                return True
            else:
                return False
    except:
        # 读取异常时，默认视为二进制以避免干扰分析
        return True

def guess_file_language(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        return "Python"
    elif ext == ".go":
        return "Go"
    elif ext in [".c", ".h"]:
        return "C"
    elif ext in [".cpp", ".cc", ".cxx", ".hpp"]:
        return "C++"
    elif ext in [".java"]:
        return "Java"
    elif ext in [".js"]:
        return "JavaScript"
    elif ext in [".ts"]:
        return "TypeScript"
    elif ext in [".cs"]:
        return "C#"
    elif ext in [".php"]:
        return "PHP"
    elif ext in [".rb"]:
        return "Ruby"
    elif ext in [".md"]:
        return "Markdown"
    elif ext in [".json"]:
        return "JSON"
    else:
        return "Other"

def update_project_stats(stats: ProjectStats, filestats: FileStats):
    """将单个文件的统计信息纳入全局统计。"""
    stats.files[filestats.path] = filestats
    stats.languages[filestats.language] += 1

    stats.total_lines += filestats.lines
    stats.total_code_lines += filestats.code_lines
    stats.total_comment_lines += filestats.comment_lines
    stats.total_blank_lines += filestats.blank_lines

    for fn in filestats.functions:
        stats.total_functions += 1
        stats.sum_complexity += fn.complexity
        # 更新最大复杂度
        if fn.complexity > stats.max_complexity:
            stats.max_complexity = fn.complexity
        # 超出阈值则纳入超标函数
        if fn.complexity >= stats.complexity_threshold:
            stats.over_threshold_functions.append(fn)
        # 记录复杂度分布
        if fn.complexity <= 5:
            stats.complexity_bins[0] += 1
        elif fn.complexity <= 10:
            stats.complexity_bins[1] += 1
        elif fn.complexity <= 15:
            stats.complexity_bins[2] += 1
        elif fn.complexity <= 20:
            stats.complexity_bins[3] += 1
        else:
            stats.complexity_bins[4] += 1


################################################################################
# 打印报告
################################################################################

def print_summary(stats: ProjectStats):
    print("\n=== Project Summary ===")
    print(f"Root Directory      : {stats.root_dir}")
    print(f"Total Files Analyzed: {len(stats.files)}")
    print(f"Total Lines         : {stats.total_lines}")
    print(f"Code Lines          : {stats.total_code_lines}")
    print(f"Comment Lines       : {stats.total_comment_lines}")
    print(f"Blank Lines         : {stats.total_blank_lines}")
    print(f"Skipped Files (size/bin) : {stats.skipped_files}")
    print(f"Unreadable Files    : {stats.unreadable_files}")
    print(f"AST Failed Files    : {stats.ast_failed_files}")

def print_language_stats(stats: ProjectStats):
    print("\n=== Language Statistics ===")
    # 语言 -> (文件数, 行数, 代码行数)
    lang_file_stats = defaultdict(lambda: [0, 0, 0])
    for f in stats.files.values():
        lang = f.language
        lang_file_stats[lang][0] += 1  # file count
        lang_file_stats[lang][1] += f.lines
        lang_file_stats[lang][2] += f.code_lines

    # 按文件数降序
    print(f"{'Language':<15}{'Files':>8}{'Lines':>10}{'Code%':>10}")
    sorted_langs = sorted(lang_file_stats.items(), key=lambda x: x[1][0], reverse=True)
    for lang, (count, lines, codelines) in sorted_langs:
        code_percent = (float(codelines) / lines * 100) if lines else 0
        print(f"{lang:<15}{count:>8}{lines:>10}{code_percent:>9.1f}%")

def print_largest_files(stats: ProjectStats, top_n: int = 15):
    print(f"\n=== Largest {top_n} Python Files by Lines ===")
    # 只筛选 Python 文件
    python_files = [fs for fs in stats.files.values() if fs.language == "Python"]

    # 按行数排序
    sorted_files = sorted(python_files, key=lambda fs: fs.lines, reverse=True)

    print(f"{'File':<70}{'Lines':>10}{'CodeLines':>12}{'Functions':>10}")
    for fs in sorted_files[:top_n]:
        print(f"{fs.path:<70}{fs.lines:>10}{fs.code_lines:>12}{len(fs.functions):>10}")

def print_function_complexity_analysis(stats: ProjectStats):
    print("\n=== Function Complexity Analysis ===")
    if stats.total_functions > 0:
        avg_complexity = float(stats.sum_complexity) / stats.total_functions
    else:
        avg_complexity = 0.0

    print(f"Total Functions    : {stats.total_functions}")
    print(f"Max Complexity     : {stats.max_complexity}")
    print(f"Avg Complexity     : {avg_complexity:.2f}")
    print(f"Threshold          : {stats.complexity_threshold}")
    print(f"Over Threshold     : {len(stats.over_threshold_functions)}")

    # 打印复杂度分布
    bin_labels = ["1-5", "6-10", "11-15", "16-20", "21+"]
    print("\nComplexity Distribution:")
    for label, count in zip(bin_labels, stats.complexity_bins):
        print(f"  {label}: {count}")

    # docstring 覆盖率
    doc_cov_ratio = 0.0
    if stats.total_functions > 0:
        doc_cov_ratio = stats.docstring_covered_functions / stats.total_functions * 100
    print(f"\nDocstring Coverage : {stats.docstring_covered_functions}/{stats.total_functions} "
          f"({doc_cov_ratio:.2f}%)")

    if stats.over_threshold_functions:
        print("\nFunctions over complexity threshold:")
        for fn in stats.over_threshold_functions:
            print(f"  - {fn.name} (Lines={fn.lines}, Complexity={fn.complexity}, StartLine={fn.start_line})")

def print_top_n_complex_functions(stats: ProjectStats, top_n: int = 15):
    print(f"\n=== Top {top_n} Most Complex Functions ===")
    all_funcs = []
    for fs in stats.files.values():
        for fn in fs.functions:
            all_funcs.append((fs.path, fn))
    # 按复杂度降序
    all_funcs.sort(key=lambda x: x[1].complexity, reverse=True)

    print(f"{'File':<70}{'Function':<30}{'Complx':>7}{'Lines':>7}{'Doc?':>6}")
    for fpath, fn in all_funcs[:top_n]:
        doc_flag = "Y" if fn.has_docstring else "N"
        print(f"{fpath:<70}{fn.name:<30}{fn.complexity:>7}{fn.lines:>7}{doc_flag:>6}")

def print_top_n_function_by_lines(stats: ProjectStats, top_n: int = 15):
    print(f"\n=== Top {top_n} Functions by Lines ===")
    all_funcs = []
    for fs in stats.files.values():
        for fn in fs.functions:
            all_funcs.append((fs.path, fn))
    # 按行数降序
    all_funcs.sort(key=lambda x: x[1].lines, reverse=True)

    print(f"{'File':<70}{'Function':<30}{'Lines':>7}{'Complx':>7}{'Doc?':>6}")
    for fpath, fn in all_funcs[:top_n]:
        doc_flag = "Y" if fn.has_docstring else "N"
        print(f"{fpath:<70}{fn.name:<30}{fn.lines:>7}{fn.complexity:>7}{doc_flag:>6}")


################################################################################
# JSON 报告
################################################################################

def generate_json_report(stats: ProjectStats) -> dict:
    """
    生成可序列化为 JSON 的报告数据结构。
    您可根据需要添加更多统计或调整层级结构。
    """
    # 语言维度
    lang_summary = defaultdict(lambda: {"files": 0, "lines": 0, "code_lines": 0})
    for fs in stats.files.values():
        lang_summary[fs.language]["files"] += 1
        lang_summary[fs.language]["lines"] += fs.lines
        lang_summary[fs.language]["code_lines"] += fs.code_lines

    # 构建 JSON
    report = {
        "project_summary": {
            "root_dir": stats.root_dir,
            "files_analyzed": len(stats.files),
            "total_lines": stats.total_lines,
            "code_lines": stats.total_code_lines,
            "comment_lines": stats.total_comment_lines,
            "blank_lines": stats.total_blank_lines,
            "skipped_files": stats.skipped_files,
            "unreadable_files": stats.unreadable_files,
            "ast_failed_files": stats.ast_failed_files,
        },
        "language_statistics": {
            lang: {
                "files": data["files"],
                "lines": data["lines"],
                "code_lines": data["code_lines"],
                "code_percent": f"{(data['code_lines']/data['lines']*100):.1f}"
                                if data["lines"] else "0.0"
            } for lang, data in sorted(lang_summary.items(),
                                       key=lambda x: x[1]["files"],
                                       reverse=True)
        },
        "function_complexity": {
            "total_functions": stats.total_functions,
            "max_complexity": stats.max_complexity,
            "avg_complexity": (stats.sum_complexity / stats.total_functions
                               if stats.total_functions else 0.0),
            "threshold": stats.complexity_threshold,
            "over_threshold": len(stats.over_threshold_functions),
            "complexity_distribution": {
                "1-5": stats.complexity_bins[0],
                "6-10": stats.complexity_bins[1],
                "11-15": stats.complexity_bins[2],
                "16-20": stats.complexity_bins[3],
                "21+": stats.complexity_bins[4],
            },
            "docstring_coverage": {
                "covered": stats.docstring_covered_functions,
                "total": stats.total_functions,
                "percent": (stats.docstring_covered_functions / stats.total_functions * 100
                            if stats.total_functions else 0.0),
            },
            "over_threshold_functions": [
                {
                    "name": fn.name,
                    "lines": fn.lines,
                    "complexity": fn.complexity,
                    "start_line": fn.start_line
                }
                for fn in stats.over_threshold_functions
            ],
        },
        "files": {}
    }

    # 记录每个文件的行数、函数等
    for path, fstats in stats.files.items():
        report["files"][path] = {
            "language": fstats.language,
            "lines": fstats.lines,
            "code_lines": fstats.code_lines,
            "comment_lines": fstats.comment_lines,
            "blank_lines": fstats.blank_lines,
            "functions": [
                {
                    "name": fn.name,
                    "lines": fn.lines,
                    "complexity": fn.complexity,
                    "start_line": fn.start_line,
                    "has_docstring": fn.has_docstring,
                }
                for fn in fstats.functions
            ]
        }

    return report


if __name__ == "__main__":
    main()
