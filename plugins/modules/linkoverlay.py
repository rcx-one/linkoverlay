#!/usr/bin/python
# -*- coding: utf-8

# Copyright: Eike <ansible@rcx.one>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
from ansible.module_utils.basic import AnsibleModule
import os
from os import path as osp
from datetime import datetime
import shutil
from typing import List, Dict

try:
    from ansible.module_utils.linkoverlay import Tree
    from ansible.module_utils import linkoverlay as util
except ImportError:
    from ..module_utils.linkoverlay import Tree
    from ..module_utils import linkoverlay as util

MODULE_ARGS = {
    "base_dir": {
        "description": [
            "The directory on the managed node where the overlay will be "
            + "applied.",

            "All symlinks pointing into C(overlay_dir) will be created in "
            + "this directory."
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
            "How files existing in both the C(base_dir) tree and the "
            + "C(overlay_dir) tree will be handled:",

            "C(error): Will fail on conflict.",

            "C(keep): Will ignore overlay files and keep the base files.",

            "C(replace): Will replace original file with symlink to overlay.",

            "Symlinks pointing into C(overlay_dir) will always be replaced."
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

            "If conflict is not set to C(replace), this has no effect.",

            "If not set, no backups will be made.",

            "This path will be postfixed with the current timestamp to avoid "
            + "overwriting existing backups."
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
            + "C(overlay_dir) if they dont conflict with the C(base_dir).",

            "If disabled, will only create missing directories and symlinks "
            + "to leaves of the C(overlay_dir) tree in the C(base_dir)."
        ],
        "type": "bool",
        "required": False,
        "default": True,
    },
}


def setup_module():
    """Creates an AnsibleModule instance from MODULE_ARGS.
    """
    return AnsibleModule(
        argument_spec={
            argument: {
                key: val
                for key, val in spec.items()
                if key != "description"
            }
            for argument, spec in MODULE_ARGS.items()
        },
        supports_check_mode=True
    )


def validate_params(module: AnsibleModule, result: Dict):
    """Checks if paths exist and are not nested in unexpected ways.
    """
    base_dir = module.params["base_dir"]
    overlay_dir = module.params["overlay_dir"]
    backup_dir = module.params["backup_dir"]

    if not util.isdir(base_dir):
        module.fail_json(
            msg="base_dir has to exist and be a directory", **result
        )

    if not util.isdir(overlay_dir):
        module.fail_json(
            msg="overlay_dir has to exist and be a directory", **result
        )

    if (
        osp.samefile(base_dir, overlay_dir)
        or util.is_inside(base_dir, overlay_dir)
    ):
        module.fail_json(
            msg="base_dir must not be (inside) overlay_dir", **result
        )

    if backup_dir and util.exists(backup_dir) and not util.isdir(backup_dir):
        module.fail_json(
            msg="backup_dir has to be a directory", **result
        )

    if (
        backup_dir
        and util.exists(backup_dir)
        and len(os.listdir(backup_dir)) > 0
    ):
        module.fail_json(
            msg="backup_dir must be empty", **result
        )

    if backup_dir and util.is_inside(backup_dir, overlay_dir):
        module.fail_json(
            msg="backup_dir must not be (inside) overlay_dir", **result
        )


def mark_symlinked(translation: Tree):
    """Marks children if one of their parents is a symlink
    """
    def impl(tree: Tree) -> bool:
        tree.set_prop("symlinked", False)
        if osp.islink(tree):
            tree.apply_children(lambda t: t.set_prop("symlinked", True))
            return False  # Stop recursing
        else:
            return True  # Recurse into children

    translation.apply_children(impl, stopping=True)


def mark_overlaid(translation: Tree, relative_links: bool):
    """Marks trees that are already linked to the correct overlay file
    and adhere to the specified relative_links value.
    """
    def impl(tree: Tree) -> bool:
        if tree.props["symlinked"]:
            tree.apply(lambda t: t.set_prop("overlaid", False))
            return False  # Stop recursing
        elif util.points_to(tree, tree.props["original_path"]):
            tree.set_prop("overlaid", util.is_relative_link(
                tree) == relative_links)
            # Children have to be behind symlink -> consider them not overlaid
            tree.apply_children(lambda t: t.set_prop("overlaid", False))
            return False  # Stop recursing
        else:
            tree.set_prop("overlaid", False)
            return True  # Recurse into children

    translation.apply_children(impl, stopping=True)


def mark_broken(translation: Tree, overlay: Tree):
    """Marks symlinks that point to an incorrect overlay file.
    """
    def impl(tree: Tree):
        tree.set_prop(
            "broken", (
                not tree.props["symlinked"]
                and util.points_into(tree, overlay)
                and not tree.props["overlaid"]
            )
        )

    translation.apply_children(impl)


def mark_conflicting(translation: Tree):
    """Marks trees that have to be removed to create a complete overlay.
    """
    def impl(tree: Tree):
        tree.set_prop(
            "conflicting",
            not tree.props["symlinked"]
            and util.exists(tree)
            and not tree.props["is_dir"]
            and not tree.props["overlaid"]
            and not tree.props["broken"]
        )

    translation.apply_children(impl)


def mark_collapsed(translation: Tree):
    """Marks directories that are already correctly linked.
    """
    def impl(tree: Tree):
        tree.set_prop(
            "collapsed",
            tree.props["is_dir"] and tree.props["overlaid"]
        )

    translation.apply_children(impl)


def mark_collapsible(translation: Tree, replace: bool, overlay: Tree):
    """Marks directories that do not contain conflicting files and could
    therefore be replaced by a symlink into the overlay.
    """
    def impl(tree: Tree) -> bool:
        collapsible = (
            not tree.props["symlinked"]
            and tree.props["is_dir"]
            and (not tree.props["conflicting"] or replace)
        )
        if collapsible and osp.exists(tree):
            def replaceable(dir_path, file_names):
                paths = (osp.join(dir_path, name) for name in file_names)
                return all(
                    util.isdir(path)
                    or util.points_into(path, overlay)
                    or replace and tree.any(
                        lambda t: t.path == osp.abspath(path)
                    )

                    for path in paths
                )

            collapsible = all(
                replaceable(dir_path, file_names)
                for dir_path, dir_names, file_names in os.walk(tree)
            )

        if collapsible:
            tree.apply(
                lambda t: t.set_prop("collapsible", not t.props["symlinked"])
            )
            return False  # Stop recursing
        else:
            tree.set_prop("collapsible", False)
            return True  # Recurse into children

    translation.apply_children(impl, stopping=True)


def mark_removable(translation: Tree, collapse: bool, replace: bool):
    """Marks trees that are allowed to be removed.
    For linking to work, none of these files may remain in the base tree.
    """
    def impl(tree: Tree) -> bool:
        removable = (
            tree.props["broken"]
            or
            collapse
            and tree.props["collapsible"]
            and util.exists(tree)
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

    translation.apply_children(impl, stopping=True)


def mark_remove(translation: Tree):
    """Marks trees that will be recursively removed.
    Children of removed trees are not marked, because they are implicitly
    removed with their parents.
    """
    def impl(tree: Tree) -> bool:
        if tree.props["removable"]:
            tree.set_prop("remove", True)
            tree.apply_children(lambda t: t.set_prop("remove", False))
            return False  # Stop recursing
        else:
            tree.set_prop("remove", False)
            return True  # Recurse into children

    translation.apply_children(impl, stopping=True)


def mark_link(translation: Tree, collapse: bool):
    """Marks trees that are supposed to be linked to the overlay,
    but are currently missing.
    """
    def impl(tree: Tree) -> bool:
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

    translation.apply_children(impl, stopping=True)


def mark_stat(translation: Tree):
    """Marks trees that need matching mode and owner.
    """
    def impl(tree: Tree) -> bool:
        if tree.props["link"] or tree.props["overlaid"]:
            # Handle symlink stats
            matches = (
                util.exists(tree)
                and (
                    os.chmod not in os.supports_follow_symlinks
                    or util.equal_mode(tree.path, tree.props["original_path"])
                )
                and (
                    os.chown not in os.supports_follow_symlinks
                    or util.equal_owner(tree.path, tree.props["original_path"])
                )
            )
            tree.set_prop(
                "stat",
                tree.props["link"]  # New links are always adjusted
                or not matches
            )
            tree.apply_children(lambda t: t.set_prop("stat", False))
            return False  # Stop recursing
        else:
            # Handle directory stats
            matches = (
                util.exists(tree)
                and util.equal_mode(tree.path, tree.props["original_path"])
                and util.equal_owner(tree.path, tree.props["original_path"])
            )
            tree.set_prop(
                "stat",
                not matches
                and tree.any_children(
                    lambda t: t.props["link"] or t.props["overlaid"]
                )
            )
            return True  # Recurse into children

    translation.apply_children(impl, stopping=True)


def validate_conflicts(translation: Tree, module: AnsibleModule, result: Dict):
    """Warns or fails for found conflicts depending on 'conflict' and
    'warn_conflicts' settings.
    """
    conflicting = translation.filter_children(lambda t: t.props["conflicting"])
    if conflicting and module.params["conflict"] == "error":
        module.fail_json(
            msg=(
                "Found conflicts:\n"
                + '\n'.join(tree.path for tree in conflicting)
            ),
            **result
        )
    elif conflicting and module.params["warn_conflict"]:
        module.warn("Found conflicts:")
        for tree in conflicting:
            module.warn(tree.path)


def update_result(
    result: Dict,
    base_dir: os.PathLike,
    backup_dir: os.PathLike,
    remove: List[Tree],
    link: List[Tree],
    stat: List[Tree],
):
    """Adds lists of removed and newly linked paths as well as file/dir stat
    changes.
    """
    result["removed_trees"] = [tree.path for tree in remove]
    result["created_links"] = [tree.path for tree in link]
    result["changed_stats"] = [tree.path for tree in stat]
    result["changed"] = not (len(remove) == len(link) == len(stat) == 0)

    if backup_dir:
        backup_list = [
            tree.translate_path(base_dir, backup_dir)
            for tree in remove
            if tree.props["conflicting"]
        ]
        result["backed_up"] = backup_list


def remove_trees(
        remove: List[Tree],
        base_dir: os.PathLike,
        backup_dir: os.PathLike
):
    """Removes paths listed in `remove`.
    """
    for tree in remove:
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


def create_links(link: List[Tree], relative_links: bool):
    """Creates symlinks specified in `link`.
    The links are relative or absolute depending on `relative_links`.
    """
    for tree in link:
        os.makedirs(osp.dirname(tree), exist_ok=True)
        target = tree.props["original_path"]
        if relative_links:
            target = osp.relpath(target, osp.dirname(tree))
        os.symlink(target, tree)


def change_stats(stat: List[Tree]):
    """Changes stats of files specified in `stat` to those of their overlay
    counter parts.
    """
    for tree in stat:
        stat = os.stat(tree.props["original_path"], follow_symlinks=False)
        if not osp.islink(tree):
            os.chmod(tree, stat.st_mode)
            os.chown(tree, stat.st_uid, stat.st_gid)
        else:
            if os.chmod in os.supports_follow_symlinks:
                os.chmod(tree, stat.st_mode, follow_symlinks=False)
            if os.chown in os.supports_follow_symlinks:
                os.chown(tree, stat.st_uid, stat.st_gid, follow_symlinks=False)


def main():
    result = {"changed": False}

    module = setup_module()

    # Postfix backup path with current timestamp
    if module.params["backup_dir"]:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        module.params["backup_dir"] = osp.join(
            module.params["backup_dir"],
            timestamp
        )

    # Handle parameters
    validate_params(module, result)

    base_dir = module.params["base_dir"]
    overlay_dir = module.params["overlay_dir"]
    backup_dir = module.params["backup_dir"]

    collapse = module.params["collapse"]
    replace = module.params["conflict"] == "replace"
    relative_links = module.params["relative_links"]

    # Find directory tree of interest
    try:
        overlay = Tree.from_path(overlay_dir)
        translation = overlay.translate(overlay_dir, base_dir)
    except PermissionError as error:
        module.fail_json(msg=f"Error occured: {str(error)}", **result)

    # Mark tree properties
    mark_symlinked(translation)
    mark_overlaid(translation, relative_links=relative_links)
    mark_broken(translation, overlay=overlay)
    mark_conflicting(translation)
    mark_collapsed(translation)
    mark_collapsible(translation, replace=replace, overlay=overlay)
    mark_removable(translation, collapse=collapse, replace=replace)

    # Mark planned actions
    mark_remove(translation)
    mark_link(translation, collapse)
    mark_stat(translation)

    # Validate and report planned actions
    validate_conflicts(translation=translation, module=module, result=result)

    remove = translation.filter_children(lambda t: t.props["remove"])
    link = translation.filter_children(lambda t: t.props["link"])
    stat = translation.filter_children(lambda t: t.props["stat"])

    update_result(
        result=result,
        base_dir=base_dir,
        backup_dir=backup_dir,
        remove=remove,
        link=link,
        stat=stat
    )

    if module.check_mode:
        module.exit_json(**result)

    # Execute planned actions
    remove_trees(remove=remove, base_dir=base_dir, backup_dir=backup_dir)
    create_links(link=link, relative_links=relative_links)
    change_stats(stat=stat)

    module.exit_json(**result)


if __name__ == '__main__':
    main()
