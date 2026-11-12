# Sourced by the server-instance tasks (env-check, server-up). Brings /opt/sinder/server-instance to the tip of branch
# release/server (only dealdesk/ and deploy/ are checked out), then runs one root script from it.
# /opt/sinder/repo is not touched: the data service and its sync keep serving main to the live site.
. "$(dirname "$0")/_root.sh"
instance_run() {
  asroot sh -c '{ set -e; D=/opt/sinder/server-instance; U=$(git -C /opt/sinder/repo remote get-url origin)
    if [ ! -d $D/.git ]; then git clone -q --depth 1 --filter=blob:none --no-checkout -b release/server "$U" $D
      git -C $D sparse-checkout set dealdesk deploy; git -C $D checkout -q release/server
    else git -C $D fetch -q --depth 1 origin release/server && git -C $D reset -q --hard FETCH_HEAD; fi
    echo "server-instance at $(git -C $D log --oneline -1 | cut -c1-60)"; } 2>&1 | sed -E "s#://[^@/ ]*@#://***@#g"' 
  [ -z "$1" ] || asroot sh -c "bash /opt/sinder/server-instance/deploy/ops/$1"
}
