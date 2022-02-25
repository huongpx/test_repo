#!/bin/zsh
cd /home/huongpx/Python/test_repo
echo "Add text at $(date +'%H:%M %d/%m')" >> text.txt
git add .
git commit -m "add some text: $(date +'%H:%M')"
git push -u origin master
echo "Done"

