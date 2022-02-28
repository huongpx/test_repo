# push to github
cd /home/huongpx/Python/test_repo
eval "$(ssh-agent -s)"
/usr/bin/ssh-add /home/huongpx/.ssh/id_cronGit
git push origin --all
