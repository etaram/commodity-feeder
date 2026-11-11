# Sourced by ops scripts. The runner user is in the docker group; asroot runs one command in the host's own
# namespaces as root. Used only by scripts committed in deploy/ops.
asroot() { docker run --rm --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- "$@"; }
