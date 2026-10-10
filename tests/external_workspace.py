"""Inventories of generated test files, explicitly outside the source checkout."""
import os
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]


def files(root):
    """Match ordinary recursive file enumeration without reading project inputs.

    Directory links are not traversed. A root or file resolving into the source
    checkout is an error, so this helper cannot hide a repository dependency.
    """
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or root.is_relative_to(CHECKOUT) or CHECKOUT.is_relative_to(root):
        raise ValueError('Test workspace inventory must stay outside the checkout')
    result = []
    for directory, _, names in os.walk(root, followlinks=False):
        for name in names:
            path = Path(directory) / name
            if path.is_file():
                if path.resolve(strict=True).is_relative_to(CHECKOUT):
                    raise ValueError('Test workspace file resolves into the checkout')
                result.append(path)
    return result
