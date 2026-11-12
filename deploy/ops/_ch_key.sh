# Sourced by enrich-start.sh and enrich-people.sh. When the repository secret COMPANIES_HOUSE_API_KEY exists, it is
# written to /opt/sinder/enrich/.ch.env (root only, mode 600) through standard input: it never appears in a command line
# or in the log. Without it the UK register (Companies House) stays off in the people lane.
if [ -n "${COMPANIES_HOUSE_API_KEY:-}" ]; then
  printf 'COMPANIES_HOUSE_API_KEY=%s\n' "$COMPANIES_HOUSE_API_KEY" | docker run -i --rm --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- \
    sh -c 'umask 077; mkdir -p /opt/sinder/enrich && cat > /opt/sinder/enrich/.ch.env.new && chmod 600 /opt/sinder/enrich/.ch.env.new && mv /opt/sinder/enrich/.ch.env.new /opt/sinder/enrich/.ch.env'
  echo "Companies House key: written from the repository secret"
else
  echo "Companies House key: the repository secret COMPANIES_HOUSE_API_KEY does not exist; the UK register stays off"
fi
