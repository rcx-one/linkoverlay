#!/usr/bin/env zsh
rm -rf test
mkdir test
pushd test

mkdir -p base/{empty.d,linked_abs.d,linked_rel.d,collapsible.d,filled.d,unrelated.d}
mkdir -p overlay/{empty.d,linked_abs.d,linked_rel.d,collapsible.d,collapsed.d,filled.d,missing.d}
mkdir backup

touch base/unrelated.f base/

touch base/conflict.f
touch overlay/conflict.f

ln -s unrelated.f base/conflict_link.f
touch overlay/conflict_link.f

touch overlay/linked_rel.d/linked.f
ln -s ../../overlay/linked_rel.d/linked.f base/linked_rel.d/linked.f
ln -s ../../overlay/linked_rel.d/broken.l base/linked_rel.d/broken.l

touch overlay/linked_abs.d/linked.f
ln -s $(realpath overlay/linked_abs.d/linked.f) base/linked_abs.d/linked.f
ln -s $(realpath overlay/linked_abs.d)/broken.l base/linked_abs.d/broken.l

touch overlay/collapsible.d/missing.f
ln -s ../../overlay/collapsible.d/broken.l base/collapsible.d/broken.l
mkdir base/collapsible.d/empty

ln -s ../overlay/collapsed.d base/

touch base/filled.d/conflict.f
touch overlay/filled.d/conflict.f

touch overlay/filled.d/linked.f
ln -s ../../overlay/filled.d/linked.f base/filled.d/linked.f

touch base/filled.d/unrelated.f
ln -s ../unrelated.f base/filled.d/unrelated.l

ln -s ../../overlay/moved.f base/filled.d/moved.f

touch overlay/missing.f
touch overlay/empty.d/missing.f
touch overlay/missing.d/missing.f
touch overlay/collapsed.d/missing.f
touch overlay/filled.d/missing.f
touch overlay/filled.d/moved.f

popd
