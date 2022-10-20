#!/usr/bin/python3
# -*- coding: utf-8

# Copyright: Eike <eike@zettelkiste.de>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.basic import AnsibleModule
from typing import Dict, List, Optional, Callable
import os
from os import path as osp
from dataclasses import dataclass, field
from copy import deepcopy
from operator import add
from functools import reduce
import shutil
from datetime import datetime

MODULE_ARGS = {
    "base_dir": {
        "description": [
            "The directory on the managed node where the overlay will be "
            + "applied.",

            "All symlinks pointing into overlay_dir will be created in this "
            + "directory."
        ],
        "type": "path",
        "required": True
    },
    "overlay_dir": {
        "description": [
            "The directory on the managed node where the overlay files "
            + "reside.",

            "All created symlinks will point into this directory."
        ],
        "type": "path",
        "required": True
    },
    "relative_links": {
        "description": (
            "Whether relative or absolute symlinks will be created."
        ),
        "type": "bool",
        "required": False,
        "default": True
    },
    "conflict": {
        "description": [
            "How files existing in both the base_dir tree and the overlay_dir "
            + "tree will be handled:",

            "error: Will fail on conflict.",

            "keep: Will ignore overlay files and keep the base files.",

            "replace: Will replace original file with symlink to overlay.",

            "Symlinks pointing into overlay_dir will always be replaced."
        ],
        "type": "str",
        "required": False,
        "default": "error",
        "choices": ["error", "keep", "replace"]
    },
    "warn_conflict": {
        "description": "Whether found conflicts will result in a warning.",
        "type": "bool",
        "required": False,
        "default": True
    },
    "backup_dir": {
        "description": [
            "Conflicting files will be backed up to this directory.",

            "If conflict is not set to 'replace', this has no effect.",

            "If not set, no backups will be made."
        ],
        "type": "path",
        "required": False,
        "default": ""
    },
    "collapse": {
        "description": [
            "Whether non-conflicting directory trees will be collapsed into a "
            + "single symlink.",

            "If enabled, will create symlinks to whole subtrees of the "
            + "overlay_dir if they dont conflict with the base_dir.",

            "If disabled, will only create missing directories and symlinks "
            + "to leaves of the overlay_dir tree in the base_dir."
        ],
        "type": "bool",
        "required": False,
        "default": True,
    },
}


def generate_option_doc(
    option_name: str, option_attributes: Dict, indent: str = " "*4
) -> str:
    doc_string = indent + option_name + ":\n"
    for name, val in option_attributes.items():
        doc_string += indent * 2 + str(name) + ": "

        if isinstance(val, list):
            value_string = "\n".join(str(line) for line in val)
        elif hasattr(val, "__name__"):
            value_string = val.__name__
        else:
            value_string = str(val)

        lines = [
            line.strip().replace('"', "'")
            for line in value_string.split("\n")
        ]
        if len(lines) > 1:
            doc_string += "["
            doc_string += ", ".join('"' + line + '"' for line in lines)
            doc_string += "]\n"
        else:
            if isinstance(val, (bool, int, float)):
                doc_string += lines[0] + "\n"
            else:
                doc_string += '"' + lines[0] + '"' + "\n"
    return doc_string


def generate_options_doc():
    return "".join(generate_option_doc(name, attrs)
                   for name, attrs in MODULE_ARGS.items())


DOCUMENTATION = r'''
---
module: link_overlay

short_description: Overlay a directory tree onto a base via symlinks

description: This module creates and manages symlinks (and directories) to overlay one directory tree onto another.

version_added: "2.3.4"

author: Eike (https://git.rcx.one/eike)

options:
''' + generate_options_doc()

EXAMPLES = r'''
- name: Overlay dotfiles
  link_overlay:
    base_dir: ~
    overlay_dir: ~/dotfiles
    backup_dir: ~/dotfile_backup
    conflict: replace
'''

RETURN = r'''
"backed_up":
    - "/home/user/dotfile_backup/2022-10-15_00-25-21/.gitconfig"
    - "/home/user/dotfile_backup/2022-10-15_00-25-21/.config/alacritty.yml"
"changed": true,
"created_links":
    - "/home/user/.bashrc"
    - "/home/user/.gitconfig"
    - "/home/user/.config/alacritty.yml"
"removed_trees":
    - "/home/eike/.gitconfig"
    - "/home/user/.config/alacritty.yml"
'''


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

    def __str__(self):
        return self.path

    def __fspath__(self):
        return self.path

    @staticmethod
    def from_path(path: str, depth: Optional[int] = None) -> "Tree":
        """Creates a tree recursively from an existing path.
        Symlinks are treated like files and are not recursed into.
        """
        assert depth is None or depth >= 0
        assert osp.isabs(path)
        assert exists(path)

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

    def set_prop(self, key, value):
        self.props[key] = value

    def apply(self, func: Callable, stopping: bool = False):
        """Applies a function to this tree and all its children recursively.
        If stopping is True, stops recursing once func returns False.
        """
        ret = func(self)
        assert not stopping or isinstance(ret, bool)
        if not stopping or ret:
            for child in self.children:
                child.apply(func, stopping)

    def apply_reverse(self, func: Callable):
        """Like apply, but applies func to children first, then self.
        """
        for child in self.children:
            child.apply_reverse(func)
        func(self)

    def filter(self, func: Callable):
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

    def apply_children(self, func: Callable, stopping: bool = False):
        """Like apply, but only applies to children of self.
        """
        for child in self.children:
            child.apply(func, stopping)

    def apply_reverse_children(self, func: Callable):
        """Like apply_reverse, but only applies to children of self.
        """
        for child in self.children:
            child.apply_reverse(func)

    def filter_children(self, func: Callable):
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

    def translate_path(self, old_base: str, new_base: str):
        """Translates the path of this tree from one base directory to another.
        """
        assert osp.isabs(self.path) == osp.isabs(old_base)
        assert old_base == self.path or osp.commonpath([old_base, self.path])
        return osp.join(new_base, osp.relpath(self.path, old_base))

    def translate(self, old_base: str, new_base: str):
        """Replaces the paths of this tree recursively via translate_path.
        The original path is kept in props["original_path"].
        """
        def substitute(tree: Tree):
            tree.set_prop("original_path", tree.path)
            tree.path = tree.translate_path(old_base, new_base)

        translated = deepcopy(self)
        translated.apply(substitute)
        return translated


def main():
    result = {"changed": False}

    module = AnsibleModule(
        argument_spec=MODULE_ARGS,
        supports_check_mode=True
    )

    base_dir = module.params["base_dir"]
    overlay_dir = module.params["overlay_dir"]
    backup_dir = module.params["backup_dir"]

    if backup_dir:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_dir = osp.join(backup_dir, timestamp)

    collapse = module.params["collapse"]
    replace = module.params["conflict"] == "replace"
    relative_links = module.params["relative_links"]

    if not isdir(base_dir):
        module.fail_json(
            msg="base_dir has to exist and be a directory", **result
        )
    if not isdir(overlay_dir):
        module.fail_json(
            msg="overlay_dir has to exist and be a directory", **result
        )
    if osp.samefile(base_dir, overlay_dir) or is_inside(base_dir, overlay_dir):
        module.fail_json(
            msg="base_dir must not be (inside) overlay_dir", **result
        )

    if backup_dir and exists(backup_dir) and not isdir(backup_dir):
        module.fail_json(
            msg="backup_dir has to be a directory", **result
        )
    if backup_dir and exists(backup_dir) and len(os.listdir(backup_dir)) > 0:
        module.fail_json(
            msg="backup_dir must be empty", **result
        )
    if backup_dir and is_inside(backup_dir, overlay_dir):
        module.fail_json(
            msg="backup_dir must not be (inside) overlay_dir", **result
        )

    try:
        overlay = Tree.from_path(overlay_dir)
        translation = overlay.translate(overlay_dir, base_dir)
    except PermissionError as error:
        module.fail_json(msg=f"Error occured: {str(error)}", **result)

    def mark_symlinked(tree: Tree) -> bool:
        """Marks trees if one of their parents is a symlink
        """
        tree.set_prop("symlinked", False)
        if osp.islink(tree):
            tree.apply_children(lambda t: t.set_prop("symlinked", True))
            return False  # Stop recursing
        else:
            return True  # Recurse into children

    def mark_overlaid(tree: Tree) -> bool:
        """Marks trees that are already linked to the correct overlay file
        and adhere to the specified relative_links value.
        """
        if tree.props["symlinked"]:
            tree.apply(lambda t: t.set_prop("overlaid", False))
            return False  # Stop recursing
        elif points_to(tree, tree.props["original_path"]):
            tree.set_prop("overlaid", is_relative_link(tree) == relative_links)
            # Children have to be behind symlink -> consider them not overlaid
            tree.apply_children(lambda t: t.set_prop("overlaid", False))
            return False  # Stop recursing
        else:
            tree.set_prop("overlaid", False)
            return True  # Recurse into children

    def mark_broken(tree: Tree):
        """Marks symlinks that point to an incorrect overlay file.
        """
        tree.set_prop(
            "broken", (
                not tree.props["symlinked"]
                and points_into(tree, overlay)
                and not tree.props["overlaid"]
            )
        )

    def mark_conflicting(tree: Tree):
        """Marks trees that have to be removed to create a complete overlay.
        """
        tree.set_prop(
            "conflicting",
            not tree.props["symlinked"]
            and exists(tree)
            and not tree.props["is_dir"]
            and not tree.props["overlaid"]
            and not tree.props["broken"]
        )

    def mark_collapsed(tree: Tree):
        """Marks directories that are already correctly linked.
        """
        tree.set_prop(
            "collapsed",
            tree.props["is_dir"] and tree.props["overlaid"]
        )

    def mark_collapsible(tree: Tree) -> bool:
        """Marks directories that do not contain conflicting files and could
        therefore be replaced by a symlink into the overlay.
        """
        collapsible = (
            not tree.props["symlinked"]
            and tree.props["is_dir"]
            and (not tree.props["conflicting"] or replace)
        )
        if collapsible and osp.exists(tree):
            def replaceable(dir_path, file_names):
                paths = (osp.join(dir_path, name) for name in file_names)
                return all(
                    isdir(path)
                    or points_into(path, overlay)
                    or replace and tree.any(
                        lambda t: t.path == osp.abspath(path)
                    )

                    for path in paths
                )

            collapsible = all(
                replaceable(dir_path, file_names)
                for dir_path, _, file_names in os.walk(tree)
            )

        if collapsible:
            tree.apply(
                lambda t: t.set_prop("collapsible", not t.props["symlinked"])
            )
            return False  # Stop recursing
        else:
            tree.set_prop("collapsible", False)
            return True  # Recurse into children

    def mark_removable(tree: Tree) -> bool:
        """Marks trees that are allowed to be removed.
        For linking to work, none of these files may remain in the base tree.
        """
        removable = (
            tree.props["broken"]
            or
            collapse
            and tree.props["collapsible"]
            and exists(tree)
            and not tree.props["collapsed"]
            or
            not collapse
            and tree.props["collapsed"]
            or
            replace
            and tree.props["conflicting"]
        )
        if removable:
            tree.set_prop("removable", True)
            tree.apply_children(lambda t: t.set_prop("removable", True))
            return False  # Stop recursing
        else:
            tree.set_prop("removable", False)
            return True  # Recurse into children

    def mark_remove(tree: Tree) -> bool:
        """Marks trees that will be recursively removed.
        Children of removed trees are not marked, because they are implicitly
        removed by their parents.
        """
        if tree.props["removable"]:
            tree.set_prop("remove", True)
            tree.apply_children(lambda t: t.set_prop("remove", False))
            return False  # Stop recursing
        else:
            tree.set_prop("remove", False)
            return True  # Recurse into children

    def mark_link(tree: Tree) -> bool:
        """Marks trees that are supposed to be linked to the overlay,
        but are currently missing.
        """
        collapsible = tree.props["collapsible"]
        link = (
            not tree.props["symlinked"]
            and not tree.props["overlaid"]
            and not tree.props["conflicting"]
            or
            tree.props["removable"]
        )
        if link and (not tree.props["is_dir"] or collapse and collapsible):
            tree.set_prop("link", True)
            tree.apply_children(lambda t: t.set_prop("link", False))
            return False  # Stop recursing
        else:
            tree.set_prop("link", False)
            return True  # Recurse into children

    def mark_stat(tree: Tree) -> bool:
        """Marks trees that need matching mode and owner.
        """
        matches = (
            exists(tree)
            and (
                os.chmod not in os.supports_follow_symlinks
                or equal_mode(tree.path, tree.props["original_path"])
            )
            and (
                os.chown not in os.supports_follow_symlinks
                or equal_owner(tree.path, tree.props["original_path"])
            )
        )
        if tree.props["link"] or tree.props["overlaid"]:
            tree.set_prop(
                "stat",
                tree.props["link"]  # New links are always adjusted
                or not matches
            )
            tree.apply_children(lambda t: t.set_prop("stat", False))
            return False  # Stop recursing
        else:
            tree.set_prop(
                "stat",
                not matches
                and tree.any_children(
                    lambda t: t.props["link"] or t.props["overlaid"]
                )
            )
            return True  # Recurse into children

    # Mark tree properties
    translation.apply_children(mark_symlinked, stopping=True)
    translation.apply_children(mark_overlaid, stopping=True)
    translation.apply_children(mark_broken)
    translation.apply_children(mark_conflicting)
    translation.apply_children(mark_collapsed)
    translation.apply_children(mark_collapsible, stopping=True)
    translation.apply_children(mark_removable, stopping=True)

    # Mark planned actions
    translation.apply_children(mark_remove, stopping=True)
    translation.apply_children(mark_link, stopping=True)
    translation.apply_children(mark_stat, stopping=True)

    conflicting = translation.filter_children(lambda t: t.props["conflicting"])
    if conflicting and module.params["conflict"] == "error":
        module.fail_json(
            msg=(
                "Found and replaced conflicts:\n"
                + '\n'.join(tree.path for tree in conflicting)
            ),
            **result
        )
    elif conflicting and module.params["warn_conflict"]:
        module.warn("Found conflicts:")
        for tree in conflicting:
            module.warn(tree.path)

    remove = translation.filter_children(lambda t: t.props["remove"])
    if remove:
        result["removed_trees"] = [tree.path for tree in remove]

    link = translation.filter_children(lambda t: t.props["link"])
    if link:
        result["created_links"] = [tree.path for tree in link]

    stat = translation.filter_children(lambda t: t.props["stat"])
    if stat:
        result["changed_stats"] = [tree.path for tree in stat]

    result["changed"] = not len(remove) == len(link) == len(stat) == 0

    if backup_dir:
        backup_list = [
            tree.translate_path(base_dir, backup_dir)
            for tree in remove
            if tree.props["conflicting"]
        ]
        if backup_list:
            result["backed_up"] = backup_list

    if module.check_mode:
        module.exit_json(**result)

    for tree in remove:  # type: Tree
        if tree.props["conflicting"] and backup_dir:
            backup_path = tree.translate_path(base_dir, backup_dir)
            os.makedirs(osp.dirname(backup_path), exist_ok=True)

            def cptree(tree: Tree) -> bool:
                """shutil.copytree replacement, because that breaks when it
                encounters broken symlinks.
                """
                if osp.islink(tree) or osp.isfile(tree):
                    shutil.copy2(tree, backup_path, follow_symlinks=False)
                else:
                    os.makedirs(tree, exist_ok=True)
                # Recurse into children if tree is not a symlink
                return not osp.islink(tree)
            tree.apply(cptree, stopping=True)

        if osp.islink(tree) or osp.isfile(tree):
            os.unlink(tree)
        else:
            shutil.rmtree(tree)

    for tree in link:  # type: Tree
        os.makedirs(osp.dirname(tree), exist_ok=True)
        target = tree.props["original_path"]
        if relative_links:
            target = osp.relpath(target, osp.dirname(tree))
        os.symlink(target, tree)

    for tree in stat:  # type: Tree
        stat = os.stat(tree.props["original_path"], follow_symlinks=False)
        if not osp.islink(tree):
            os.chmod(tree, stat.st_mode)
            os.chown(tree, stat.st_uid, stat.st_gid)
        else:
            if os.chmod in os.supports_follow_symlinks:
                os.chmod(tree, stat.st_mode, follow_symlinks=False)
            if os.chown in os.supports_follow_symlinks:
                os.chown(tree, stat.st_uid, stat.st_gid, follow_symlinks=False)

    module.exit_json(**result)


if __name__ == '__main__':
    main()
