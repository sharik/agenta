# build docker

docker build -t sharikmaster/agenta:latest .

# verify version

docker run --rm sharikmaster/agenta:latest python --version
