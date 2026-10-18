#!/bin/bash
set -euo pipefail

if [[ "$EUID" != 0 ]]; then
  echo 'Run the bootstrap through sudo on the target Ubuntu 24.04 server.' >&2
  exit 1
fi
if [[ "$#" != 3 ]]; then
  echo 'Usage: bootstrap-linux.sh SOURCE_DIRECTORY DOMAIN PRIVATE_ENV_FILE' >&2
  exit 1
fi
source_directory="$1"
domain="$2"
private_env="$3"
if [[ ! "$domain" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
  echo 'Invalid HTTPS domain.' >&2
  exit 1
fi
if [[ "$(uname -m)" != x86_64 ]]; then
  echo 'This release installs the official Linux x86_64 OpenMVS tools.' >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl unzip ca-certificates libgl1 libglib2.0-0 libgomp1 caddy
if ! id respace >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/respace-reconstruction --shell /usr/sbin/nologin respace
fi
install -d -m 0700 -o respace -g respace /var/lib/respace-reconstruction
install -d -m 0755 /opt/respace-reconstruction /opt/respace-reconstruction/openmvs
if [[ -f /etc/systemd/system/respace-reconstruction.service ]]; then
  systemctl stop respace-reconstruction
fi
cp -R "$source_directory/respace_reconstruction" /opt/respace-reconstruction/
cp "$source_directory/pyproject.toml" "$source_directory/requirements.lock" /opt/respace-reconstruction/
cp "$source_directory/setup-segmentation.sh" "$source_directory/setup-detection.sh" /opt/respace-reconstruction/
python3 -m venv /opt/respace-reconstruction/.venv
/opt/respace-reconstruction/.venv/bin/python -m pip install -r /opt/respace-reconstruction/requirements.lock -e /opt/respace-reconstruction
(cd /opt/respace-reconstruction && bash setup-segmentation.sh && bash setup-detection.sh)

if [[ ! -f /opt/respace-reconstruction/openmvs/.release-v2.4.0 ]]; then
  archive="$(mktemp --suffix=.zip)"
  trap 'rm -f "$archive"' EXIT
  curl -fsSL --retry 3 https://github.com/cdcseacave/openMVS/releases/download/v2.4.0/OpenMVS_Ubuntu_x64.zip -o "$archive"
  printf '7104ae1ddd6ca38fbca9e0e4a70b20af59e21e0b497eb7181c864fbf38ca8d00  %s\n' "$archive" | sha256sum -c -
  unzip -o "$archive" InterfaceCOLMAP RefineMesh TextureMesh -d /opt/respace-reconstruction/openmvs
  chmod 0755 /opt/respace-reconstruction/openmvs/InterfaceCOLMAP /opt/respace-reconstruction/openmvs/RefineMesh /opt/respace-reconstruction/openmvs/TextureMesh
  touch /opt/respace-reconstruction/openmvs/.release-v2.4.0
fi
for tool in InterfaceCOLMAP RefineMesh TextureMesh; do
  if ldd "/opt/respace-reconstruction/openmvs/$tool" | grep -q 'not found'; then
    echo "Missing system library required by $tool" >&2
    exit 1
  fi
done
/opt/respace-reconstruction/.venv/bin/python -c 'import open3d, fastapi; print("Python reconstruction dependencies loaded")'

install -m 0600 -o root -g root "$private_env" /etc/respace-reconstruction.env
install -m 0644 "$source_directory/deploy/respace-reconstruction.service" /etc/systemd/system/respace-reconstruction.service
cat > /etc/caddy/Caddyfile <<EOF
$domain {
    request_body {
        max_size 134217728
    }
    reverse_proxy 127.0.0.1:8008
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl daemon-reload
systemctl enable --now respace-reconstruction
systemctl enable caddy
systemctl restart caddy
systemctl is-active --quiet respace-reconstruction
echo 'Worker installed. Caddy is provisioning HTTPS; deployment verifies readiness next.'
