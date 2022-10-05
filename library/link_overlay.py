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
from shutil import rmtree

MODULE_ARGS = {
    "base_dir": {
        "description": [
            "The directory on the managed node where the overlay will be "
            + "applied.",

            "All symlinks pointing into overlay_dir will be created in this "
            + "directory."
        ],
        "type": "str",
        "required": True
    },
    "overlay_dir": {
        "description": [
            "The directory on the managed node where the overlay files "
            + "reside.",

            "All created symlinks will point into this directory."
        ],
        "type": "str",
        "required": True
    },
    # "state": {
    #     "description": [
    #         "All created symlinks will point into this directory."
    #     ],
    #     "type": "str",
    #     "required": False,
    #     "default": "linked",
    #     "choices": ["linked", "unlinked"]
    # },
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

            "ignore: Will ignore overlay files and keep the base files.",

            "warning: Like ignore, but will print a warning.",

            "replace: Will replace original file with symlink to overlay.",

            "Symlinks pointing into overlay_dir are always replaced."
        ],
        "type": "str",
        "required": False,
        "default": "error",
        "choices": ["error", "warning", "ignore", "replace"]
    },
    "backup_dir": {
        "description": [
            "Replaced files will be backed up to this directory.",

            "If conflict is not set to 'replace', this has not effect.",

            "If unset, no backups will be made."
        ],
        "type": "str",
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
            doc_string += lines[0] + "\n"
    return doc_string


def generate_options_doc():
    return "".join(generate_option_doc(name, attrs)
                   for name, attrs in MODULE_ARGS.items())


DOCUMENTATION = (
    r'''
---
module: link_overlay

short_description: Overlay a directory tree onto a base via symlinks

description: This module creates and manages symlinks (and directories) to overlay one directory tree onto another.

version_added: "2.3.4"

author: Eike (https://git.rcx.one/eike)

options:
'''
    + generate_options_doc()
    + r'''
# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
extends_documentation_fragment:
    - my_namespace.my_collection.my_doc_fragment_name

'''
)

EXAMPLES = r'''
# Pass in a message
- name: Test with a message
  my_namespace.my_collection.my_test:
    name: hello world

# pass in a message and have changed true
- name: Test with a message and changed output
  my_namespace.my_collection.my_test:
    name: hello world
    new: true

# fail the module
- name: Test failure of the module
  my_namespace.my_collection.my_test:
    name: fail me
'''

RETURN = r'''
# These are examples of possible return values, and in general should use other names for return values.
original_message:
    description: The original name param that was passed in.
    type: str
    returned: always
    sample: 'hello world'
message:
    description: The output message that the test module generates.
    type: str
    returned: always
    sample: 'goodbye'
'''


def exists(path: os.PathLike) -> bool:
    return osp.exists(path) or osp.islink(path)


def isdir(path: os.PathLike) -> bool:
    return osp.isdir(path) and not osp.islink(path)


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

    @property
    def name(self) -> str:
        return osp.basename(self.name)

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

    def translate(self, old_base: str, new_base: str):
        assert osp.isabs(self.path) == osp.isabs(old_base)
        assert old_base == self.path or osp.commonpath([old_base, self.path])

        def substitute(tree: Tree):
            tree.set_prop("original_path", tree.path)
            tree.path = osp.join(new_base, osp.relpath(tree.path, old_base))

        translated = deepcopy(self)
        translated.apply(substitute)
        return translated


def is_inside(inner, outer):
    inner = osp.abspath(inner)
    outer = osp.abspath(outer)
    return osp.commonpath([outer, inner]) == outer


def points_to(link, path):
    if not osp.islink(link):
        return False
    link_target = osp.join(osp.dirname(link), os.readlink(link))
    return osp.abspath(link_target) == osp.abspath(path)


def points_into(link, path):
    if not osp.islink(link):
        return False
    link_target = osp.join(osp.dirname(link), os.readlink(link))
    return is_inside(link_target, path)


def run_module():
    result = {"changed": False}

    module = AnsibleModule(
        argument_spec=MODULE_ARGS,
        supports_check_mode=True
    )

    base_dir = osp.expanduser(module.params["base_dir"])
    overlay_dir = osp.expanduser(module.params["overlay_dir"])

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

    overlay = Tree.from_path(overlay_dir)
    translation = overlay.translate(overlay_dir, base_dir)

    def mark_linked(tree: Tree) -> bool:
        if points_to(tree, tree.props["original_path"]):
            # Consider children linked, too
            tree.apply(lambda t: t.set_prop("linked", True))
            return False  # Stop recursing
        else:
            tree.set_prop("linked", False)
            return True  # Recurse into children

    def mark_broken(tree: Tree):
        tree.set_prop(
            "broken", (
                points_into(tree, overlay)
                and not tree.props.get("linked", False)
            )
        )

    def mark_conflicting(tree: Tree):
        tree.set_prop(
            "conflicting",
            exists(tree)
            and not tree.props["is_dir"]
            and not tree.props.get("linked", False)
            and not tree.props["broken"]
        )

    def mark_collapsed(tree: Tree):
        tree.set_prop(
            "collapsed",
            tree.props["is_dir"] and tree.props["linked"]
        )

    def mark_collapsible(tree: Tree) -> bool:
        replace = module.params["conflict"] == "replace"
        collapsible = (
            tree.props["is_dir"]
            and not tree.props["conflicting"] or replace
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
            tree.apply(lambda t: t.set_prop("collapsible", True))
            return False  # Stop recursing
        else:
            tree.set_prop("collapsible", False)
            return True  # Recurse into children

    def mark_removable(tree: Tree) -> bool:
        collapse = module.params["collapse"]
        replace = module.params["conflict"] == "replace"
        removable = (
            tree.props["broken"]
            or
            collapse
            and tree.props["collapsible"]
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

    # TODO: add to_remove to mark only the root path of subtrees that are removable

    def mark_linkable(tree: Tree) -> bool:
        collapse = module.params["collapse"]
        collapsible = tree.props["collapsible"]
        replace = module.params["conflict"] == "replace"
        linkable = (
            (tree.props["removable"] or not tree.props["linked"])
            and (not tree.props["conflicting"] or replace)
        )
        if linkable and (not tree.props["is_dir"] or collapse and collapsible):
            tree.set_prop("linkable", True)
            tree.apply_children(lambda t: t.set_prop("linkable", False))
            return False  # Stop recursing
        else:
            tree.set_prop("linkable", False)
            return True  # Recurse into children

    translation.apply_children(mark_linked, stopping=True)
    translation.apply_children(mark_broken)
    translation.apply_children(mark_conflicting)
    translation.apply_children(mark_collapsed)
    translation.apply_children(mark_collapsible, stopping=True)
    translation.apply_children(mark_removable, stopping=True)
    translation.apply_children(mark_linkable, stopping=True)

    print(
        "linked;broken;conflicting;collapsed;collapsible;removable;" +
        "linkable;path"
    )
    translation.apply_children(lambda t: print(
        ';'.join([
            str(t.props["linked"]),
            str(t.props["broken"]),
            str(t.props["conflicting"]),
            str(t.props["collapsed"]),
            str(t.props["collapsible"]),
            str(t.props["removable"]),
            str(t.props["linkable"]),
            str(t)
        ])
    ))

    conflicting = translation.filter_children(lambda t: t.props["conflicting"])
    # print("conflicting:")
    # for c in conflicting:
    #     print(c)
    # removable = translation.filter_children(lambda t: t.props["removable"])
    # print("removable:")
    # for r in removable:
    #     print(r)
    # linkable = translation.filter_children(lambda t: t.props["linkable"])
    # for L in linkable:
    #     print(L)

    if conflicting and module.params["conflict"] == "error":
        module.fail_json(
            msg=(
                "Found conflicts:\n"
                + '\n'.join(c.path for c in conflicting)
            ),
            **result
        )
    elif conflicting and module.params["conflict"] == "warning":
        module.warn("Found conflicts:")
        for conflict in conflicting:
            module.warn(conflict.path)

    if module.check_mode:
        module.exit_json(**result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
