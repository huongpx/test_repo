#!/bin/zsh

cd /home/huongpx/Python/test_repo
branches=()
eval "$(git for-each-ref --shell --format='branches+=(%(refname:short))' refs/heads/)"
for branch in "${branches[@]}"; do
    git checkout "$branch"
    echo "$branch"
    echo "Add text at $(date +'%H:%M %d/%m')" >> text.txt
    git add text.txt
    git commit -m "add some text: $(date +'%H:%M')"
done
