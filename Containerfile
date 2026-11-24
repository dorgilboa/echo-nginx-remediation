# Final image: installs our .deb into a minimal Debian base. This is the image we ship.
#
# SKELETON: the real content comes later. It must match nginx:1.25-bookworm exactly:
#   user, working directory, exposed ports (80), entrypoint (/docker-entrypoint.sh),
#   CMD ["nginx", "-g", "daemon off;"], stop signal and filesystem layout.
# It also installs the bumped libssl3 (3.0.22-1~deb12u2 or newer) from bookworm-security.
FROM debian:bookworm-slim
