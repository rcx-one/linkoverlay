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

try:
    from ansible.module_utils.linkoverlay import Tree
    from ansible.module_utils import linkoverlay as lo
except ImportError:
    pass

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
            + "C(overlay_dir) if they dont conflict with the C(base_dir).",

            "If disabled, will only create missing directories and symlinks "
            + "to leaves of the C(overlay_dir) tree in the C(base_dir)."
        ],
        "type": "bool",
        "required": False,
        "default": True,
    },
}


def main():
    result = {"changed": False}

    module = AnsibleModule(
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

    base_dir = module.params["base_dir"]
    overlay_dir = module.params["overlay_dir"]
    backup_dir = module.params["backup_dir"]

    if backup_dir:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_dir = osp.join(backup_dir, timestamp)

    collapse = module.params["collapse"]
    replace = module.params["conflict"] == "replace"
    relative_links = module.params["relative_links"]

    if not lo.isdir(base_dir):
        module.fail_json(
            msg="base_dir has to exist and be a directory", **result
        )

    if not lo.isdir(overlay_dir):
        module.fail_json(
            msg="overlay_dir has to exist and be a directory", **result
        )

    if (
        osp.samefile(base_dir, overlay_dir)
        or lo.is_inside(base_dir, overlay_dir)
    ):
        module.fail_json(
            msg="base_dir must not be (inside) overlay_dir", **result
        )

    if backup_dir and lo.exists(backup_dir) and not lo.isdir(backup_dir):
        module.fail_json(
            msg="backup_dir has to be a directory", **result
        )

    if (
        backup_dir
        and lo.exists(backup_dir)
        and len(os.listdir(backup_dir)) > 0
    ):
        module.fail_json(
            msg="backup_dir must be empty", **result
        )

    if backup_dir and lo.is_inside(backup_dir, overlay_dir):
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
        elif lo.points_to(tree, tree.props["original_path"]):
            tree.set_prop("overlaid", lo.is_relative_link(
                tree) == relative_links)
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
                and lo.points_into(tree, overlay)
                and not tree.props["overlaid"]
            )
        )

    def mark_conflicting(tree: Tree):
        """Marks trees that have to be removed to create a complete overlay.
        """
        tree.set_prop(
            "conflicting",
            not tree.props["symlinked"]
            and lo.exists(tree)
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
                    lo.isdir(path)
                    or lo.points_into(path, overlay)
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

    def mark_removable(tree: Tree) -> bool:
        """Marks trees that are allowed to be removed.
        For linking to work, none of these files may remain in the base tree.
        """
        removable = (
            tree.props["broken"]
            or
            collapse
            and tree.props["collapsible"]
            and lo.exists(tree)
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
        if tree.props["link"] or tree.props["overlaid"]:
            # Handle symlink stats
            matches = (
                lo.exists(tree)
                and (
                    os.chmod not in os.supports_follow_symlinks
                    or lo.equal_mode(tree.path, tree.props["original_path"])
                )
                and (
                    os.chown not in os.supports_follow_symlinks
                    or lo.equal_owner(tree.path, tree.props["original_path"])
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
                lo.exists(tree)
                and lo.equal_mode(tree.path, tree.props["original_path"])
                and lo.equal_owner(tree.path, tree.props["original_path"])
            )
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
                "Found conflicts:\n"
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

    result["changed"] = not (len(remove) == len(link) == len(stat) == 0)

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
