#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

VERSION=${1:?укажите версию: bash deploy.sh 5.0}
PREFIX=golenev-09
PORT=8027
REGISTRY=localhost:6009
IMAGE=$REGISTRY/$PREFIX/probe:$VERSION

if [ "$(docker info --format '{{.Swarm.LocalNodeState}}')" != active ]; then
  addr=$(docker run --rm --network host postgres:16-alpine ip -4 addr show eth0 | awk '/inet / {split($2,a,"/"); print a[1]; exit}')
  docker swarm init --advertise-addr "$addr"
fi

if ! docker container inspect "$PREFIX-registry" > /dev/null 2>&1; then
  docker run -d --restart unless-stopped --name "$PREFIX-registry" -p 6009:5000 -v "$PREFIX-registry:/var/lib/registry" registry:2
elif [ "$(docker inspect "$PREFIX-registry" --format '{{.State.Running}}')" != true ]; then
  docker start "$PREFIX-registry"
fi
until curl -sf "$REGISTRY/v2/" > /dev/null; do sleep 1; done

docker build --build-arg VERSION="$VERSION" -t "$IMAGE" .
docker push "$IMAGE"
VERSION="$VERSION" docker stack deploy --detach=false -c stack.yaml "$PREFIX"

SECONDS=0
until curl -sf -m 2 "127.0.0.1:$PORT/notes" > /dev/null; do
  if [ "$SECONDS" -ge 90 ]; then
    echo "приложение не ответило за 90 секунд" >&2
    exit 1
  fi
  sleep 2
done
curl -s "127.0.0.1:$PORT/notes"
printf '\n'
