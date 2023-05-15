from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
import os
from os import path as osp
from functools import reduce
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from operator import add
from copy import deepcopy


def exists(path: os.PathLike) -> bool:
    """Whether path exists.
    Symlinks - broken or not - are considered existing.
    """
    return osp.exists(path) or osp.islink(path)


def isdir(path: os.PathLike) -> bool:
    """Whether path is a directory.
    Symlinks - regardless of their target - are not considered directories.
    """
    return osp.isdir(path) and not osp.islink(path)


def is_inside(inner: os.PathLike, outer: os.PathLike) -> bool:
    """Whether inner is a path inside or equal to outer.
    """
    inner = osp.abspath(inner)
    outer = osp.abspath(outer)
    return osp.commonpath([outer, inner]) == outer


def points_to(link: os.PathLike, path: os.PathLike) -> bool:
    """Whether link is a symlink that points to path.
    """
    if not osp.islink(link):
        return False
    link_target = osp.join(osp.dirname(link), os.readlink(link))
    return osp.abspath(link_target) == osp.abspath(path)


def points_into(link: os.PathLike, path: os.PathLike) -> bool:
    """Whether link is a symlink that points to or into path.
    """
    if not osp.islink(link):
        return False
    link_target = osp.join(osp.dirname(link), os.readlink(link))
    return is_inside(link_target, path)


def is_relative_link(link: os.PathLike) -> bool:
    """Whether link is a relative symlink.
    """
    return osp.islink(link) and not osp.isabs(os.readlink(link))


def equal_mode(a: os.PathLike, b: os.PathLike) -> bool:
    a_stat = os.stat(a, follow_symlinks=False)
    b_stat = os.stat(b, follow_symlinks=False)
    return a_stat.st_mode == b_stat.st_mode


def equal_owner(a: os.PathLike, b: os.PathLike) -> bool:
    a_stat = os.stat(a, follow_symlinks=False)
    b_stat = os.stat(b, follow_symlinks=False)
    return a_stat.st_uid == b_stat.st_uid and a_stat.st_gid == b_stat.st_gid


@dataclass
class Tree():
    """A class representing a filesystem directory tree.
    This tree may or may not actually exist on the filesystem.
    """
    path: str
    children: List["Tree"]
    depth: Optional[int]
    props: Dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.path

    def __fspath__(self) -> str:
        return self.path

    @staticmethod
    def from_path(path: str, depth: Optional[int] = None) -> "Tree":
        """Creates a tree recursively from an existing path.
        Symlinks are treated like files and are not recursed into.
        """
        if (
            depth is not None and depth < 0  # depth has to be positive
            or not exists(path)  # path has to exist
            or not osp.isabs(path)  # path has to be absolute
        ):
            raise AssertionError()

        is_dir = isdir(path)

        if is_dir and depth != 0:
            child_depth = None if depth is None else depth - 1
            children = [
                Tree.from_path(child, child_depth)
                for child
                in map(lambda p: osp.join(path, p), os.listdir(path))
            ]
        else:
            children = []

        return Tree(
            path=path,
            children=children,
            depth=depth,
            props={"is_dir": is_dir}
        )

    def set_prop(self, key, value) -> None:
        self.props[key] = value

    def apply(self, func: Callable, stopping: bool = False) -> None:
        """Applies a function to this tree and all its children recursively.
        If stopping is True, stops recursing once func returns False.
        """
        ret = func(self)
        if stopping and not isinstance(ret, bool):
            raise AssertionError()

        if not stopping or ret:
            for child in self.children:
                child.apply(func, stopping)

    def apply_reverse(self, func: Callable) -> None:
        """Like apply, but applies func to children first, then self.
        """
        for child in self.children:
            child.apply_reverse(func)
        func(self)

    def filter(self, func: Callable) -> List["Tree"]:
        """Returns a list of all trees in self where func returns True.
        """
        matching = []
        if func(self):
            matching.append(self)
        return matching + reduce(
            add,
            (child.filter(func) for child in self.children),
            []
        )

    def all(self, func: Callable) -> bool:
        """True, if func returns true for this tree and all of its children.
        """
        return func(self) and all(child.all(func) for child in self.children)

    def any(self, func: Callable) -> bool:
        """True, if func returns true for this tree or any of its children.
        """
        return func(self) or any(child.any(func) for child in self.children)

    def apply_children(self, func: Callable, stopping: bool = False) -> None:
        """Like apply, but only applies to children of self.
        """
        for child in self.children:
            child.apply(func, stopping)

    def apply_reverse_children(self, func: Callable) -> None:
        """Like apply_reverse, but only applies to children of self.
        """
        for child in self.children:
            child.apply_reverse(func)

    def filter_children(self, func: Callable) -> List["Tree"]:
        """Like filter, but only filters children of self.
        """
        return reduce(
            add,
            (child.filter(func) for child in self.children),
            []
        )

    def all_children(self, func: Callable) -> bool:
        """Like all, but only inspects children of self.
        """
        return all(child.all(func) for child in self.children)

    def any_children(self, func: Callable) -> bool:
        """Like any, but only inspects children self.
        """
        return any(child.any(func) for child in self.children)

    def translate_path(self, old_base: str, new_base: str) -> str:
        """Translates the path of this tree from one base directory to another.
        """
        if (
            osp.isabs(self.path) != osp.isabs(old_base)
            or not (
                old_base == self.path
                or osp.commonpath([old_base, self.path])
            )
        ):
            raise AssertionError()
        return osp.join(new_base, osp.relpath(self.path, old_base))

    def translate(self, old_base: str, new_base: str) -> "Tree":
        """Replaces the paths of this tree recursively via translate_path.
        The original path is kept in props["original_path"].
        """
        def substitute(tree: Tree):
            tree.set_prop("original_path", tree.path)
            tree.path = tree.translate_path(old_base, new_base)

        translated = deepcopy(self)
        translated.apply(substitute)
        return translated
