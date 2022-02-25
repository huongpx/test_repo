#!/bin/sh
cd /home/huongpx/Python/test_repo
echo "Add text" >> text.txt
git add .
git commit -m "add some text"
git push -u origin master

