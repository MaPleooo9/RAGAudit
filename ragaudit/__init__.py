# -*- coding: utf-8 -*-
"""RAGAudit —— 检索评测审计工具。

不产出「又一个分数」，而是回答这个分数能不能信：

    1. 双口径  —— 同一份结果按宽/严两套规则各算一遍，差值即虚高
    2. 归因    —— 关掉某个策略再跑，量化它到底贡献了多少
    3. 难度画像 —— 自动判定每道题的信息泄漏程度，拆穿「自己出题自己考」
    4. case diff —— 改代码前后逐条比对，定位是哪几条退化

模块：
    schema    评估集与检索结果的数据结构
    matchers  判定口径（可组合，不写死）
    metrics   Hit@K / MRR / 层准确率
    audit     跑分主流程
    ablate    消融矩阵与归因
    profile   难度画像与评估集自检
    diff      两次运行的逐条对比
    report    报告渲染
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
